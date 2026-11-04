from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.backup_access import admin_or_machine
from app.backup_format import BackupError, create_backup, check_archive, ROOTS
import app.restore_workspace as maintenance

REAL_REQUIRE_ROOT = maintenance.require_root


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "installation"
    root.mkdir()
    settings = Settings(data_dir=root, frontend_dir=tmp_path / "frontend")
    app = create_app(settings)
    app.dependency_overrides[admin_or_machine] = lambda: None
    app.state.maintenance = SimpleNamespace(call=lambda *args: {'active': False})
    with TestClient(app) as client:
        r = client.post("/api/library/strains", json={"name": "Original point"})
        assert r.status_code == 201
        (root / "files/retained.txt").write_text("original point")
        data = client.get("/api/backups/download")
        assert data.status_code == 200, data.text
        archive = tmp_path / "older.zip"
        archive.write_bytes(data.content)
        client.post("/api/library/strains", json={"name": "Latest committed"})
        (root / "files/retained.txt").write_text("latest committed")
    (root / ".git").mkdir()
    (root / ".git/HEAD").write_text("checkout untouched")
    for name in ["compose.yaml", ".env", "README.md"]:
        (root / name).write_text("SOURCE UNTOUCHED")
    # Unit-level restore state machine runs unprivileged. Real UID/GID, process,
    # Compose, startup and ownership checks are exercised by the Docker smoke.
    monkeypatch.setattr(maintenance, "require_root", lambda: None)
    monkeypatch.setattr(maintenance, "permissions", lambda path: None)
    monkeypatch.setattr(maintenance.os, "fchown", lambda *args: None)
    checks = []
    monkeypatch.setattr(
        maintenance, "assert_no_writers", lambda path: checks.append(path)
    )
    return root, archive, settings, checks


class FakeCompose:
    was_running = True

    def __init__(self, root, fail_start=False):
        self.root = root
        self.stopped = False
        self.calls = []
        self.fail_start = fail_start

    def stop(self):
        self.stopped = True
        self.calls.append("stop")

    def start(self):
        self.stopped = False
        self.calls.append("start")

    def health(self):
        self.calls.append("health")
        if self.fail_start:
            self.fail_start = False
            raise BackupError("Simulated new startup failure")

    def safety_backup(self, path):
        self.calls.append("safety")
        artifact = create_backup(self.root)
        try:
            shutil.copyfile(artifact.path, path)
        finally:
            artifact.cleanup()
        check_archive(path, extract=False)


def names(root):
    with sqlite3.connect(root / "database/cultivatinator.sqlite3") as db:
        return [r[0] for r in db.execute("SELECT name FROM strains ORDER BY id")]


def unchanged_source(root):
    assert (root / ".git/HEAD").read_text() == "checkout untouched"
    for name in ["compose.yaml", ".env", "README.md"]:
        assert (root / name).read_text() == "SOURCE UNTOUCHED"


def test_successful_restore_only_four_directories_with_independent_recovery_copy(
    installation,
):
    root, archive, settings, checks = installation
    controller = FakeCompose(root)
    operation = maintenance.restore(
        archive,
        root,
        root / "compose.yaml",
        confirm="REPLACE-PERSISTENT-DATA",
        controller=controller,
    )
    assert names(root) == ["Original point"]
    assert (root / "files/retained.txt").read_text() == "original point"
    assert controller.calls == ["safety", "stop", "start", "health"]
    assert checks == [root]
    assert names(operation / "original") == ["Original point", "Latest committed"]
    assert (operation / "original/files/retained.txt").read_text() == "latest committed"
    check_archive(operation / "pre-restore.zip", extract=False)
    assert (
        json.loads((operation / "operation.json").read_text())["state"] == "completed"
    )
    unchanged_source(root)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("failure", ["start", "rename", "interrupt"])
def test_failures_roll_back_and_preserve_new_and_original_datasets(
    installation, monkeypatch, failure
):
    root, archive, settings, checks = installation
    controller = FakeCompose(root, fail_start=failure == "start")
    move = maintenance.move
    triggered = False

    def fail_once(source, target):
        nonlocal triggered
        if (
            not triggered
            and source.name == "database"
            and source.parent.name.startswith("cultivatinator-verify-")
        ):
            triggered = True
            if failure == "interrupt":
                raise KeyboardInterrupt("Simulated interruption")
            if failure == "rename":
                raise OSError("Simulated rename failure")
        return move(source, target)

    if failure != "start":
        monkeypatch.setattr(maintenance, "move", fail_once)
    with pytest.raises(BackupError, match="original data retained/restored"):
        maintenance.restore(
            archive,
            root,
            root / "compose.yaml",
            confirm="REPLACE-PERSISTENT-DATA",
            controller=controller,
        )
    assert names(root) == ["Original point", "Latest committed"]
    assert (root / "files/retained.txt").read_text() == "latest committed"
    operations = list((root.parent / "installation-recovery").iterdir())
    assert len(operations) == 1
    assert (operations[0] / "pre-restore.zip").exists()
    assert (
        json.loads((operations[0] / "operation.json").read_text())["state"]
        == "rolled_back"
    )
    unchanged_source(root)


def test_invalid_archive_disk_permission_and_confirmation_fail_before_stop(
    installation, monkeypatch
):
    root, archive, settings, checks = installation
    controller = FakeCompose(root)
    with pytest.raises(BackupError, match="confirmation"):
        maintenance.restore(
            archive, root, root / "compose.yaml", confirm="NO", controller=controller
        )
    assert controller.calls == []

    def no_space(*args):
        raise BackupError("Insufficient disk space")

    monkeypatch.setattr(maintenance, "ensure_space", no_space)
    with pytest.raises(BackupError, match="Insufficient disk"):
        maintenance.restore(
            archive,
            root,
            root / "compose.yaml",
            confirm="REPLACE-PERSISTENT-DATA",
            controller=controller,
        )
    assert controller.calls == [] and names(root) == [
        "Original point",
        "Latest committed",
    ]
    archive.write_bytes(b"corrupt")
    with pytest.raises(BackupError):
        maintenance.restore(
            archive,
            root,
            root / "compose.yaml",
            confirm="REPLACE-PERSISTENT-DATA",
            controller=controller,
        )
    unchanged_source(root)


def test_interrupted_cutover_recovers_originals_with_database_directory_missing(
    installation,
):
    root, archive, settings, checks = installation
    controller = FakeCompose(root)
    operation = root.parent / "retained-operation"
    operation.mkdir()
    (operation / "original").mkdir()
    (operation / "failed").mkdir()
    # Simulate SIGKILL immediately after moving the original database directory.
    maintenance.move(root / "database", operation / "original/database")
    maintenance.journal(
        operation,
        {
            "format_version": 1,
            "root": str(root),
            "compose_file": str(root / "compose.yaml"),
            "directories": list(ROOTS),
            "state": "replacing",
        },
    )
    maintenance.recover(
        operation,
        root,
        root / "compose.yaml",
        confirm="REPLACE-PERSISTENT-DATA",
        controller=controller,
    )
    assert names(root) == ["Original point", "Latest committed"]
    assert (
        json.loads((operation / "operation.json").read_text())["state"] == "rolled_back"
    )
    unchanged_source(root)


def test_restore_refuses_a_still_running_writer_without_replacement(
    installation, monkeypatch
):
    root, archive, settings, checks = installation
    controller = FakeCompose(root)

    def busy(root):
        raise BackupError("Process still has live SQLite database open")

    monkeypatch.setattr(maintenance, "assert_no_writers", busy)
    with pytest.raises(BackupError, match="original data retained/restored"):
        maintenance.restore(
            archive,
            root,
            root / "compose.yaml",
            confirm="REPLACE-PERSISTENT-DATA",
            controller=controller,
        )
    assert names(root) == ["Original point", "Latest committed"]
    unchanged_source(root)


def test_permissions_and_root_guard_are_explicit(installation, monkeypatch):
    root, archive, settings, checks = installation
    controller = FakeCompose(root)
    mkdir = Path.mkdir

    def denied_probe(path, *args, **kwargs):
        if path.name.startswith(".cultivatinator-permission-"):
            raise PermissionError("Read-only installation root")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied_probe)
    with pytest.raises(BackupError, match="not writable"):
        maintenance.restore(
            archive,
            root,
            root / "compose.yaml",
            confirm="REPLACE-PERSISTENT-DATA",
            controller=controller,
        )
    assert controller.calls == []
    assert names(root) == ["Original point", "Latest committed"]
    unchanged_source(root)
    # Use the actual guard, independently of unit-state-machine patches.
    monkeypatch.setattr(maintenance.os, "geteuid", lambda: 1000)
    with pytest.raises(BackupError, match="sudo/root"):
        REAL_REQUIRE_ROOT()


def test_compose_always_targets_local_host_despite_inherited_remote_context(
    tmp_path, monkeypatch
):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}")
    for name in [
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ]:
        monkeypatch.setenv(name, "remote-selector")
    calls = []

    def output(command, **kwargs):
        calls.append(command)
        assert command[:2] == ["docker", "--host=unix:///var/run/docker.sock"]
        assert not any(
            key in kwargs["env"]
            for key in [
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
            ]
        )
        if "config" in command:
            return json.dumps(
                {
                    "services": {
                        "app": {
                            "volumes": [
                                {
                                    "type": "bind",
                                    "target": "/data",
                                    "source": str(tmp_path),
                                }
                            ]
                        }
                    }
                }
            )
        if "ps" in command:
            return "a" * 64
        return json.dumps(
            [
                {
                    "Mounts": [
                        {
                            "Type": "bind",
                            "Destination": "/data",
                            "Source": str(tmp_path),
                        }
                    ],
                    "Config": {"User": "10001:10001"},
                    "State": {"Running": True},
                    "HostConfig": {
                        "PortBindings": {
                            "8085/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8085"}]
                        }
                    },
                }
            ]
        )

    monkeypatch.setattr(maintenance.subprocess, "check_output", output)
    controller = maintenance.Compose(compose, tmp_path)
    assert controller.was_running and controller.port == 8085
    assert len(calls) == 3


def test_incomplete_restore_marker_blocks_startup_before_creating_missing_data(
    installation,
):
    root, archive, settings, checks = installation
    operation = root.parent / "power-loss"
    operation.mkdir()
    (operation / "original").mkdir()
    (operation / "failed").mkdir()
    maintenance.journal(
        operation,
        {
            "format_version": 1,
            "root": str(root),
            "compose_file": str(root / "compose.yaml"),
            "directories": list(ROOTS),
            "state": "replacing",
        },
    )
    maintenance.restore_marker(root, operation)
    maintenance.move(root / "database", operation / "original/database")
    with pytest.raises(BackupError, match="Incomplete restore"):
        with TestClient(create_app(settings)):
            pass
    assert not (root / "database").exists()
    maintenance.recover(
        operation,
        root,
        root / "compose.yaml",
        confirm="REPLACE-PERSISTENT-DATA",
        controller=FakeCompose(root),
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
