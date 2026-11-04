"""Stopped-data restore coordinator. Standard library only; CLI runs on the host."""

from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import time
import urllib.request
from .maintenance_protocol import read_key
from .backup_format import (
    ROOTS,
    DATABASE,
    RUNTIME_LOCK,
    RESTORE_MARKER,
    BackupError,
    check_archive,
    create_backup,
    dataset_entries,
    ensure_space,
    lease,
    connect,
    VERSION,
    Limits,
)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def journal(operation, data):
    temp = operation / "operation.json.tmp"
    with temp.open("w") as file:
        json.dump(data, file, sort_keys=True, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp, operation / "operation.json")
    sync_directory(operation)


def restore_marker(root, operation, remove=False):
    marker = root / RESTORE_MARKER
    if marker.exists() or marker.is_symlink():
        if marker.is_symlink() or marker.stat().st_size > 8192:
            raise BackupError(
                "Unsafe restore marker; preserve recovery files and inspect manually"
            )
        value = json.loads(marker.read_text())
        if value != {"operation": str(operation)}:
            raise BackupError(
                "A different restore operation is incomplete; recover it first"
            )
        if remove:
            marker.unlink()
            sync_directory(root)
        return
    if remove:
        return
    with marker.open("x") as file:
        json.dump({"operation": str(operation)}, file)
        file.flush()
        os.fsync(file.fileno())
    sync_directory(root)


def move(source, target):
    if source.is_symlink() or target.exists() or target.is_symlink():
        raise BackupError("Unsafe/conflicting restore directory")
    os.rename(source, target)
    sync_directory(source.parent)
    sync_directory(target.parent)


def permissions(root):
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(parent) / name
            if path.is_symlink():
                raise BackupError("Symlinks are not allowed in restore staging")
            os.chown(path, 10001, 10001)
            os.chmod(path, 0o750 if path.is_dir() else 0o640)
            if path.is_file():
                with path.open("rb") as file:
                    os.fsync(file.fileno())
        sync_directory(parent)
    os.chown(root, 10001, 10001)
    os.chmod(root, 0o750)


def require_root():
    if os.geteuid() != 0:
        raise BackupError(
            "Restore requires sudo/root to verify host processes and preserve UID/GID 10001. Verification does not require root."
        )


def assert_no_writers(root):
    """Host /proc check complements the lifetime process lease and Compose stop."""
    inodes = set()
    for suffix in ["", "-wal", "-shm"]:
        path = Path(str(root / DATABASE) + suffix)
        if path.exists():
            st = path.stat()
            inodes.add((st.st_dev, st.st_ino))
    try:
        for process in Path("/proc").iterdir():
            if not process.name.isdecimal() or int(process.name) == os.getpid():
                continue
            try:
                for fd in (process / "fd").iterdir():
                    try:
                        st = fd.stat()
                    except FileNotFoundError:
                        continue
                    if (st.st_dev, st.st_ino) in inodes:
                        raise BackupError(
                            f"Process {process.name} still has the live SQLite database open; stop it before restore"
                        )
            except (FileNotFoundError, ProcessLookupError):
                continue
    except PermissionError as exc:
        raise BackupError(
            "Cannot inspect host process descriptors; restore must run as host root with /proc access"
        ) from exc
    if not (root / DATABASE).exists():
        return  # Interrupted cutover may have moved database/ to retained originals.
    with connect((root / DATABASE).as_uri() + "?mode=rw", uri=True, timeout=0) as conn:
        try:
            conn.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            raise BackupError("Live database is still busy; restore refused") from exc
        finally:
            conn.rollback()


class Compose:
    def __init__(self, file, root, service="app"):
        self.file = Path(file).resolve(strict=True)
        self.root = Path(root).resolve(strict=True)
        self.service = service
        key_file = Path("/run/cultivatinator-maintenance/channel.key")
        self.maintenance_key = (
            read_key(key_file).decode() if key_file.exists() else None
        )
        if not re.fullmatch("[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}", service):
            raise BackupError("Invalid Compose service name")
        # Host /proc and local filesystem checks must refer to the same machine
        # as Docker. Never inherit a remote context or DOCKER_HOST here.
        self.docker = ["docker", "--host=unix:///var/run/docker.sock"]
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
            }
        }
        self.command = [*self.docker, "compose", "-f", str(self.file)]
        config = json.loads(self.run("config", "--format", "json"))
        definition = config.get("services", {}).get(service, {})
        binds = [v for v in definition.get("volumes", []) if v.get("target") == "/data"]
        if (
            len(binds) != 1
            or binds[0].get("type") != "bind"
            or Path(binds[0]["source"]).resolve() != self.root
        ):
            raise BackupError("Compose /data bind mount does not match --data-root")
        ids = self.run("ps", "-a", "-q", service).split()
        if len(ids) != 1 or not re.fullmatch("[a-f0-9]{12,64}", ids[0]):
            raise BackupError(
                "Expected exactly one existing Compose application container; create/review the matching installation first"
            )
        self.id = ids[0]
        info = self.inspect()
        mounts = [v for v in info["Mounts"] if v.get("Destination") == "/data"]
        if (
            len(mounts) != 1
            or mounts[0].get("Type") != "bind"
            or Path(mounts[0]["Source"]).resolve() != self.root
        ):
            raise BackupError("Existing container has a different /data mount")
        if info["Config"].get("User") != "10001:10001":
            raise BackupError("Expected application UID/GID 10001:10001")
        self.was_running = info["State"]["Running"]
        ports = info.get("HostConfig", {}).get("PortBindings", {}).get("8085/tcp") or []
        if len(ports) != 1 or ports[0].get("HostIp") not in {
            "",
            "0.0.0.0",
            "127.0.0.1",
            "::",
        }:
            raise BackupError(
                "Restore requires an existing locally reachable published application port"
            )
        self.port = int(ports[0]["HostPort"])

    def run(self, *args):
        try:
            return subprocess.check_output(
                [*self.command, *args],
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                env=self.environment,
            ).strip()
        except (subprocess.SubprocessError, OSError) as exc:
            raise BackupError(
                f"Compose command failed ({' '.join(args)}); inspect docker compose logs before proceeding"
            ) from exc

    def inspect(self):
        try:
            return json.loads(
                subprocess.check_output(
                    [*self.docker, "inspect", self.id],
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    env=self.environment,
                )
            )[0]
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            raise BackupError(
                "Cannot inspect the existing application container"
            ) from exc

    def stop(self):
        self.run("stop", "--timeout", "30", self.service)
        state = self.inspect()["State"]
        if state["Running"] or state.get("Pid", 0):
            raise BackupError("Compose application process did not stop")

    def start(self):
        self.run("start", self.service)

    def open(self, path, timeout=120, data=None):
        # Only a verified local port belonging to this exact Compose container.
        headers = {"Content-Type": "application/json"}
        if self.maintenance_key:
            headers["X-Cultivatinator-Maintenance"] = self.maintenance_key
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}" + path, data=data, headers=headers
        )
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=timeout
        )

    def freeze(self):
        if self.maintenance_key:
            with self.open(
                "/api/backups/maintenance/freeze", data=b'{"enabled":true}'
            ) as response:
                response.read()

    def unfreeze(self):
        if self.maintenance_key:
            with self.open(
                "/api/backups/maintenance/freeze", timeout=5, data=b'{"enabled":false}'
            ) as response:
                response.read()

    def health(self):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with self.open("/api/health", 2) as r:
                    health = json.load(r)
                with self.open("/api/app/info", 2) as r:
                    info = json.load(r)
                if (
                    health
                    == {"status": "ok", "database": "ok", "migrations": "current"}
                    and info.get("version") == VERSION
                ):
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        raise BackupError(
            "Application did not become healthy with the expected database/application version"
        )

    def safety_backup(self, path):
        self.freeze()
        try:
            with self.open("/api/backups/download", 1800) as source, path.open(
                "xb"
            ) as output:
                if source.headers.get_content_type() != "application/zip":
                    raise BackupError(
                        "The running image does not support complete backup; use the matching 2D.2 image"
                    )
                total = 0
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > Limits().archive_bytes:
                        raise BackupError("Safety backup exceeds archive limits")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise BackupError(
                "Could not download a pre-restore backup from the running application; no replacement performed"
            ) from exc
        check_archive(path, extract=False)


def validate_root(root):
    root = Path(root).resolve(strict=True)
    if root == Path("/") or not (root / DATABASE).is_file():
        raise BackupError("--data-root must be the existing application data root")
    for name in ROOTS:
        path = root / name
        if (
            path.is_symlink()
            or not path.is_dir()
            or path.stat().st_dev != root.stat().st_dev
            or os.path.ismount(path)
        ):
            raise BackupError(
                "The four data directories must be real directories on the data-root filesystem"
            )
    # Validate readability and reject special entries before any shutdown/replacement.
    dataset_entries(root)
    return root


def restore(
    archive,
    root,
    compose_file,
    recovery=None,
    confirm=None,
    controller=None,
    progress=None,
):
    progress = progress or (lambda *args: None)
    progress("verifying")
    require_root()
    selected = Path(root).resolve(strict=True)
    marker = selected / RESTORE_MARKER
    if marker.exists() or marker.is_symlink():
        raise BackupError(
            "An interrupted restore is present; recover its retained originals before a new restore"
        )
    root = validate_root(selected)
    recovery = Path(recovery or root.parent / (root.name + "-recovery")).resolve()
    if (
        recovery == root
        or recovery.is_relative_to(root)
        or root.is_relative_to(recovery)
    ):
        raise BackupError(
            "Recovery directory must be a separate sibling/outside the installation"
        )
    recovery.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (
        recovery.is_symlink()
        or recovery.stat().st_dev != root.stat().st_dev
        or root.parent.stat().st_dev != root.stat().st_dev
    ):
        raise BackupError(
            "Recovery sibling and data root must share a filesystem for atomic directory rollback"
        )
    controller = controller or Compose(compose_file, root)
    verified = check_archive(archive, stage_parent=root.parent)
    try:
        current_size = sum(p.stat().st_size for _, p in dataset_entries(root)[1])
        ensure_space(root.parent, current_size + 16 * 1024**2)
        ensure_space(recovery, current_size + 16 * 1024**2)
        # Probe the exact filesystem permissions without touching any live file.
        probe = root / (".cultivatinator-permission-" + uuid4().hex)
        try:
            probe.mkdir()
            probe.rmdir()
        except OSError as exc:
            raise BackupError(
                "Data-root directory is not writable for safe directory replacement"
            ) from exc
        if confirm is None:
            answer = input(
                f"Replace ONLY database/, photos/, files/, settings/ in {root}? Type REPLACE-PERSISTENT-DATA: "
            )
        else:
            answer = confirm
        if answer != "REPLACE-PERSISTENT-DATA":
            raise BackupError(
                "Restore cancelled; explicit replacement confirmation was not supplied"
            )
        with lease(root, ".cultivatinator-restore.lock"):
            operation = recovery / (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + uuid4().hex[:12]
            )
            operation.mkdir(mode=0o700)
            original = operation / "original"
            original.mkdir()
            failed = operation / "failed"
            failed.mkdir()
            info = {
                "format_version": 1,
                "root": str(root),
                "compose_file": str(Path(compose_file).resolve()),
                "state": "prepared",
                "incoming": str(verified.root),
                "directories": list(ROOTS),
            }
            journal(operation, info)
            progress("preparing_safety_backup", operation)
            for name in ROOTS:
                permissions(verified.root / name)
            # Independent, verified online recovery copy before stopping. Original
            # directories additionally retain every commit made up to actual stop.
            if controller.was_running:
                controller.safety_backup(operation / "pre-restore.zip")
            stopped = False
            cutover = False
            try:
                stopped = True
                progress("stopping_application", operation)
                controller.stop()
                with lease(root) as fd:
                    os.fchown(fd, 10001, 10001)
                    assert_no_writers(root)
                    if not controller.was_running:
                        artifact = create_backup(root)
                        try:
                            shutil.copyfile(
                                artifact.path, operation / "pre-restore.zip"
                            )
                            with (operation / "pre-restore.zip").open("rb") as file:
                                os.fsync(file.fileno())
                        finally:
                            artifact.cleanup()
                    info["state"] = "replacing"
                    journal(operation, info)
                    restore_marker(root, operation)
                    cutover = True
                    progress("restoring_data", operation)
                    for name in ROOTS:
                        move(root / name, original / name)
                        move(verified.root / name, root / name)
                    info["state"] = "replaced"
                    journal(operation, info)
                    restore_marker(root, operation, remove=True)
                progress("restarting_application", operation)
                controller.start()
                progress("verifying_health", operation)
                controller.health()
                info["state"] = "completed"
                journal(operation, info)
                return operation
            except BaseException as error:
                # SIGINT/SIGTERM become exceptions in the CLI. SIGKILL/power loss
                # leave this journal and retained originals for `recover`.
                try:
                    if cutover:
                        controller.stop()
                        with lease(root):
                            assert_no_writers(root)
                            restore_marker(root, operation)
                            rollback_directories(root, operation)
                            restore_marker(root, operation, remove=True)
                        controller.start()
                        controller.health()
                        info["state"] = "rolled_back"
                    elif stopped:
                        restore_marker(root, operation, remove=True)
                        controller.start()
                        controller.health()
                        info["state"] = "unchanged"
                    else:
                        info["state"] = "unchanged"
                except BaseException as rollback_error:
                    info["state"] = "recovery_required"
                    info["error"] = str(rollback_error)
                    journal(operation, info)
                    raise BackupError(
                        f"Restore failed and automatic rollback could not complete. Preserve {operation}; run the documented recover command. {rollback_error}"
                    ) from error
                journal(operation, info)
                raise BackupError(
                    f"Restore failed; original data retained/restored. Recovery files: {operation}. {error}"
                ) from error
    finally:
        if hasattr(controller, "unfreeze"):
            try:
                controller.unfreeze()
            except OSError:
                pass  # Failed rollback may leave app stopped; preserve recovery state.
        verified.cleanup()


def rollback_directories(root, operation):
    for parent in [operation / "original", operation / "failed"]:
        if parent.is_symlink() or not parent.is_dir():
            raise BackupError("Unsafe recovery directory")
    for name in ROOTS:
        old = operation / "original" / name
        if old.exists():
            if old.is_symlink() or not old.is_dir():
                raise BackupError("Unsafe original recovery directory")
            if (root / name).exists():
                move(root / name, operation / "failed" / name)
            move(old, root / name)


def recover(operation, root, compose_file, confirm=None, controller=None):
    require_root()
    root = Path(root).resolve(strict=True)
    operation = Path(operation).resolve(strict=True)
    if operation.is_relative_to(root):
        raise BackupError("Recovery files must be outside the installation")
    info = json.loads((operation / "operation.json").read_text())
    if (
        info.get("format_version") != 1
        or info.get("root") != str(root)
        or info.get("directories") != list(ROOTS)
        or info.get("compose_file") != str(Path(compose_file).resolve())
    ):
        raise BackupError(
            "Recovery journal does not match the explicitly selected installation"
        )
    if info.get("state") not in {"replacing", "replaced", "recovery_required"}:
        raise BackupError("Operation does not need interrupted-restore recovery")
    if confirm is None:
        confirm = input(
            f"Recover retained originals into {root}? Type REPLACE-PERSISTENT-DATA: "
        )
    if confirm != "REPLACE-PERSISTENT-DATA":
        raise BackupError("Recovery cancelled")
    controller = controller or Compose(compose_file, root)
    with lease(root, ".cultivatinator-restore.lock"):
        controller.stop()
        with lease(root) as fd:
            os.fchown(fd, 10001, 10001)
            assert_no_writers(root)
            restore_marker(root, operation)
            rollback_directories(root, operation)
            restore_marker(root, operation, remove=True)
        controller.start()
        controller.health()
        info["state"] = "rolled_back"
        journal(operation, info)
    return operation
