from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from io import BytesIO
import hashlib
import json
import os
import tempfile
import threading
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.backup_format import BackupError, check_archive, create_backup
from app.backup_schedule import DEFAULT_SCHEDULE, bounds, validate_schedule
from app.backup_store import BackupStore, atomic_json
from app.maintenance_protocol import HelperClient, MaintenanceError
from app.maintenance_service import AdminStore, MaintenanceService, Server

PASSWORD = "A long private cultivation passphrase"
BOOTSTRAP = "one-time-local-deployment-code"


@pytest.fixture
def administration(tmp_path):
    root = tmp_path / "installation"
    root.mkdir()
    state = tmp_path / "helper-state"
    state.mkdir()
    (state / "session.key").write_text("b" * 64)
    (state / "bootstrap.sha256").write_text(
        hashlib.sha256(BOOTSTRAP.encode()).hexdigest()
    )
    with tempfile.TemporaryDirectory(prefix="ct-helper-") as temporary:
        runtime = Path(temporary)
        key = runtime / "channel.key"
        key.write_text("a" * 64)
        config = {
            "data_root": str(root),
            "state_root": str(state),
            "compose_file": str(tmp_path / "frozen-compose.json"),
            "key_file": str(key),
            "socket_file": str(runtime / "control.sock"),
        }
        service = MaintenanceService(config)
        with Server(
            runtime / "control.sock", service, allowed_uid=os.getuid()
        ) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            settings = Settings(
                data_dir=root,
                frontend_dir=tmp_path / "frontend",
                maintenance_socket=runtime / "control.sock",
                maintenance_key=key,
            )
            app = create_app(settings)
            app.state.maintenance = HelperClient(
                runtime / "control.sock", key, expected_uid=os.getuid()
            )
            with TestClient(app) as client:
                yield client, service, root, state
            server.shutdown()
            thread.join(timeout=5)


def unlock(client):
    response = client.post(
        "/api/backups/admin/setup",
        json={"passphrase": PASSWORD, "bootstrap": BOOTSTRAP},
    )
    assert response.status_code == 200, response.text
    client.headers["X-Backup-CSRF"] = response.json()["csrf"]
    return response


def saved(client, **choices):
    response = client.post("/api/backups/create", json=choices)
    assert response.status_code == 200, response.text
    return response.json()


def test_first_setup_unlock_csrf_cookie_scope_and_root_private_hashed_sessions(
    administration,
):
    client, service, root, state = administration
    assert client.get("/api/backups/admin/session").json() == {
        "available": True,
        "configured": False,
        "unlocked": False,
    }
    assert (
        client.post(
            "/api/backups/admin/setup",
            json={"passphrase": PASSWORD, "bootstrap": "wrong"},
        ).status_code
        == 401
    )
    response = unlock(client)
    cookie = response.headers["set-cookie"]
    assert (
        "HttpOnly" in cookie
        and "SameSite=strict" in cookie
        and "Path=/api/backups" in cookie
    )
    assert "session" not in response.json()
    assert PASSWORD not in (state / "admin.json").read_text()
    assert (
        client.cookies.get("cultivatinator_backup_admin")
        not in (state / "admin.json").read_text()
    )
    assert not (state / "bootstrap.sha256").exists()
    assert client.get("/api/backups/admin/session").json()["unlocked"]
    assert (
        client.post(
            "/api/backups/admin/setup",
            json={"passphrase": PASSWORD, "bootstrap": BOOTSTRAP},
        ).status_code
        == 409
    )
    assert client.post("/api/backups/admin/lock").status_code == 200
    assert client.get("/api/backups/catalog").status_code == 401
    response = client.post("/api/backups/admin/unlock", json={"passphrase": PASSWORD})
    assert response.status_code == 200
    # Credentials/sessions survive a helper restart and are outside restored roots.
    reopened = AdminStore(state)
    assert reopened.authorize(client.cookies.get("cultivatinator_backup_admin"))[
        "unlocked"
    ]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/catalog"),
        ("get", "/download"),
        ("post", "/prepare"),
        ("post", "/create"),
        ("put", "/schedule"),
        ("post", "/restore/upload"),
        ("get", "/restore/status"),
    ],
)
def test_backup_endpoints_fail_closed_without_administrator(
    administration, method, path
):
    client, service, root, state = administration
    assert getattr(client, method)("/api/backups" + path).status_code == 401


def test_cross_origin_csrf_expiration_and_rate_limits(administration):
    client, service, root, state = administration
    unlock(client)
    assert (
        client.post(
            "/api/backups/create", json={}, headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/backups/catalog", headers={"sec-fetch-site": "cross-site"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/backups/create", json={}, headers={"X-Backup-CSRF": ""}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/backups/create", json={}, headers={"X-Backup-CSRF": "wrong"}
        ).status_code
        == 403
    )
    document = service.admin.load()
    next(iter(document["sessions"].values()))["expires"] = time.time() - 1
    atomic_json(state / "admin.json", document)
    assert client.get("/api/backups/catalog").status_code == 401
    service.admin.attempts.clear()
    for _ in range(5):
        assert (
            client.post(
                "/api/backups/admin/unlock",
                json={"passphrase": "incorrect long password"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/backups/admin/unlock", json={"passphrase": PASSWORD}
        ).status_code
        == 429
    )


@pytest.mark.parametrize("save,download", [(True, False), (False, True), (True, True)])
def test_manual_destinations_one_artifact_catalog_download_and_no_recursive_backup(
    administration, save, download
):
    client, service, root, state = administration
    unlock(client)
    result = saved(client, save=save, download=download)
    assert bool(result["stored"]) == save and bool(result["download_url"]) == download
    listed = client.get("/api/backups/catalog").json()
    assert len(listed["backups"]) == int(save)
    if download:
        downloaded = client.get(result["download_url"])
        assert downloaded.status_code == 200
        with zipfile.ZipFile(BytesIO(downloaded.content)) as archive:
            assert not any(path.startswith("backups/") for path in archive.namelist())
        assert client.get(result["download_url"]).status_code == 404
    if save:
        row = result["stored"]
        server = client.get(f"/api/backups/catalog/{row['id']}/download")
        assert server.status_code == 200
        if download:
            assert server.content == downloaded.content
        assert listed["storage"]["used_bytes"] == len(server.content)
        assert listed["storage"]["available_bytes"] > 0
        assert (
            client.post(f"/api/backups/catalog/{row['id']}/verify").status_code == 200
        )
        assert (
            client.request(
                "DELETE",
                f"/api/backups/catalog/{row['id']}",
                json={"confirmation": "wrong"},
            ).status_code
            == 400
        )
        assert (
            client.request(
                "DELETE",
                f"/api/backups/catalog/{row['id']}",
                json={"confirmation": "DELETE-BACKUP"},
            ).status_code
            == 200
        )
        assert client.get("/api/backups/catalog").json()["backups"] == []


def test_reject_destinations_and_arbitrary_paths_corrupted_missing_archives(
    administration,
):
    client, service, root, state = administration
    unlock(client)
    assert (
        client.post(
            "/api/backups/create", json={"save": False, "download": False}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/backups/create", json={"path": "/etc/passwd"}).status_code
        == 422
    )
    value = saved(client)["stored"]
    path = root / "backups" / value["filename"]
    path.write_bytes(b"corrupt")
    listed = client.get("/api/backups/catalog").json()["backups"][0]
    assert listed["validation"] == "changed"
    assert client.post(f"/api/backups/catalog/{value['id']}/verify").status_code == 400
    assert (
        client.get("/api/backups/catalog").json()["backups"][0]["validation"]
        == "invalid"
    )
    path.unlink()
    assert (
        client.get("/api/backups/catalog").json()["backups"][0]["validation"]
        == "missing_or_unsafe"
    )
    assert (
        client.get("/api/backups/catalog/../../etc/passwd/download").status_code != 200
    )


def test_upload_and_stored_preview_validate_without_restore_or_implicit_retention(
    administration,
):
    client, service, root, state = administration
    unlock(client)
    value = saved(client)
    data = client.get(value["download_url"]).content
    preview = client.post(
        "/api/backups/restore/stored", json={"id": value["stored"]["id"]}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["compatibility"] == "verified"
    assert service.latest() is None
    assert (
        client.post(
            "/api/backups/restore/confirm",
            json={
                "preview_id": preview.json()["id"],
                "request_id": str(uuid4()),
                "confirmation": "no",
            },
        ).status_code
        == 400
    )
    assert (
        client.delete(
            "/api/backups/restore/preview/" + preview.json()["id"]
        ).status_code
        == 200
    )
    uploaded = client.post(
        "/api/backups/restore/upload",
        content=data,
        headers={"content-type": "application/zip"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["source"] == "upload"
    assert len(client.get("/api/backups/catalog").json()["backups"]) == 1
    assert list((root / "backups/.control/uploads").iterdir()) == []
    client.delete("/api/backups/restore/preview/" + uploaded.json()["id"])
    retained = client.post("/api/backups/restore/upload?retain=true", content=data)
    assert retained.status_code == 200
    assert len(client.get("/api/backups/catalog").json()["backups"]) == 2
    assert (
        client.post("/api/backups/restore/upload", content=b"not a zip").status_code
        == 400
    )
    assert service.latest() is None


def test_helper_rejects_arbitrary_operations_and_symlinked_restore_sources(
    administration, tmp_path
):
    client, service, root, state = administration
    unlock(client)
    auth = {
        "session": client.cookies.get("cultivatinator_backup_admin"),
        "csrf": client.headers["X-Backup-CSRF"],
    }
    with pytest.raises(MaintenanceError, match="Unsupported"):
        service.dispatch("shell", {**auth, "command": "rm -rf /"})
    with pytest.raises(BackupError):
        service.dispatch(
            "prepare_restore", {**auth, "source": "/etc/passwd", "id": str(uuid4())}
        )
    value = saved(client)["stored"]
    path = root / "backups" / value["filename"]
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(OSError):
        service.safe_source("stored", value["id"])
    with pytest.raises(BackupError):
        service.safe_source("stored", "../../etc/passwd")
    assert (
        client.post(
            "/api/backups/restore/stored",
            json={"id": value["id"], "docker_target": "anything"},
        ).status_code
        == 422
    )


def test_restore_request_idempotency_authoritative_status_and_active_delete_protection(
    administration, monkeypatch
):
    client, service, root, state = administration
    unlock(client)
    value = saved(client)["stored"]
    preview = client.post(
        "/api/backups/restore/stored", json={"id": value["id"]}
    ).json()
    started = threading.Event()
    finish = threading.Event()
    count = []

    def perform(operation):
        count.append(operation["id"])
        service.update(operation, "preparing_safety_backup")
        started.set()
        assert finish.wait(10)
        service.update(operation, "complete", "Healthy")

    monkeypatch.setattr(service, "perform", perform)
    code = str(uuid4())
    payload = {
        "preview_id": preview["id"],
        "request_id": code,
        "confirmation": "REPLACE-PERSISTENT-DATA",
    }
    response = client.post("/api/backups/restore/confirm", json=payload)
    assert response.status_code == 200, response.text
    assert started.wait(5)
    # Direct helper retry models a lost HTTP response. It returns the same job.
    auth = {
        "session": client.cookies.get("cultivatinator_backup_admin"),
        "csrf": client.headers["X-Backup-CSRF"],
    }
    assert service.dispatch("restore", {**payload, **auth})["id"] == code
    assert client.post("/api/backups/create", json={}).status_code == 409
    assert (
        client.request(
            "DELETE",
            f"/api/backups/catalog/{value['id']}",
            json={"confirmation": "DELETE-BACKUP"},
        ).status_code
        == 409
    )
    assert client.get("/api/backups/restore/status").json()["operation"]["id"] == code
    finish.set()
    service.worker.join(timeout=5)
    assert count == [code]
    assert (
        client.get("/api/backups/restore/status").json()["operation"]["status"]
        == "complete"
    )


def test_machine_freeze_blocks_mutations_but_keeps_admin_and_protected_capture(
    administration,
):
    client, service, root, state = administration
    unlock(client)
    assert (
        client.post(
            "/api/backups/maintenance/freeze", json={"enabled": True}
        ).status_code
        == 403
    )
    headers = {"X-Cultivatinator-Maintenance": "a" * 64}
    assert (
        client.post(
            "/api/backups/maintenance/freeze", json={"enabled": True}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post("/api/library/strains", json={"name": "blocked"}).status_code == 503
    )
    assert client.get("/api/backups/admin/session").status_code == 200
    assert client.get("/api/backups/download", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/backups/maintenance/freeze", json={"enabled": False}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post("/api/library/strains", json={"name": "allowed"}).status_code == 201
    )


def test_weekly_timezone_dst_gap_overlap_and_default():
    assert DEFAULT_SCHEDULE == {
        "enabled": True,
        "weekday": 6,
        "time": "03:00",
        "timezone": "America/New_York",
        "retention": 12,
    }
    previous, next_run = bounds(
        DEFAULT_SCHEDULE, datetime(2026, 11, 2, tzinfo=timezone.utc)
    )
    assert previous == datetime(2026, 11, 1, 8, tzinfo=timezone.utc)
    assert next_run == datetime(2026, 11, 8, 8, tzinfo=timezone.utc)
    spring = {**DEFAULT_SCHEDULE, "time": "02:30"}
    previous, _ = bounds(spring, datetime(2026, 3, 9, tzinfo=timezone.utc))
    assert previous == datetime(2026, 3, 8, 7, tzinfo=timezone.utc)  # gap -> 03:00
    fall = {**DEFAULT_SCHEDULE, "time": "01:30"}
    previous, next_run = bounds(fall, datetime(2026, 11, 1, 7, tzinfo=timezone.utc))
    assert previous == datetime(
        2026, 11, 1, 5, 30, tzinfo=timezone.utc
    )  # first 01:30 only
    assert next_run > previous + timedelta(days=6)
    with pytest.raises(ValueError):
        validate_schedule({**DEFAULT_SCHEDULE, "timezone": "invalid/zone"})


def test_schedule_missed_runs_restart_identity_failure_and_retention(
    administration, monkeypatch
):
    client, service, root, state = administration
    unlock(client)
    manager = client.app.state.backup_manager
    schedule = manager.store.schedule()
    schedule["created_at"] = "2026-01-01T00:00:00+00:00"
    atomic_json(manager.store.schedule_path, schedule)
    # Invoke on the application's event loop, like the actual scheduler.
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    client.portal.call(manager.tick, now)
    first = manager.store.list()
    assert len(first) == 1 and first[0]["kind"] == "weekly"
    client.portal.call(manager.tick, now)
    assert len(manager.store.list()) == 1
    # Re-open persisted catalog/schedule to simulate a process restart.
    reopened = BackupStore(root)
    assert reopened.schedule()["last_success"]["backup_id"] == first[0]["id"]
    # Crash after publish/before schedule update is deduplicated from the receipt.
    schedule = reopened.schedule()
    schedule["last_occurrence"] = None
    atomic_json(reopened.schedule_path, schedule)
    client.portal.call(manager.tick, now)
    assert len(manager.store.list()) == 1
    manual = saved(client, save=True, download=False)["stored"]
    artifact = create_backup(root)
    try:
        for _ in range(12):
            manager.store.save(artifact.path, "weekly")
    finally:
        artifact.cleanup()
    assert len([v for v in manager.store.list() if v["kind"] == "weekly"]) == 13
    manager.store.prune(12)
    assert len([v for v in manager.store.list() if v["kind"] == "weekly"]) == 12
    assert manager.store.info(manual["id"])["kind"] == "manual"
    before = [v["id"] for v in manager.store.list()]

    def failed(*args, **kwargs):
        raise BackupError("Injected storage failure")

    monkeypatch.setattr(manager.store, "save", failed)
    client.portal.call(manager.tick, now + timedelta(days=7))
    assert [v["id"] for v in manager.store.list()] == before
    assert (
        manager.store.schedule()["last_failure"]["message"]
        == "Injected storage failure"
    )
    # Retention does not touch backups in an active restore or manual/recovery data.
    victim = next(v for v in manager.store.list() if v["kind"] == "weekly")
    manager.store.prune(1, protected=[victim["id"]])
    assert manager.store.info(victim["id"])["validation"] == "verified"


def test_schedule_edits_preserve_outside_data_and_report_pruning_errors(
    administration, monkeypatch
):
    client, service, root, state = administration
    unlock(client)
    result = client.put(
        "/api/backups/schedule", json={**DEFAULT_SCHEDULE, "enabled": False}
    )
    assert result.status_code == 200
    assert result.json()["next_run"] is None
    assert (
        client.put(
            "/api/backups/schedule", json={**DEFAULT_SCHEDULE, "time": "99:00"}
        ).status_code
        == 400
    )
    assert (root / "backups/.control/schedule.json").exists()
    store = client.app.state.backup_manager.store
    artifact = create_backup(root)
    try:
        for _ in range(2):
            store.save(artifact.path, "weekly")
    finally:
        artifact.cleanup()
    monkeypatch.setattr(
        store, "delete", lambda code: (_ for _ in ()).throw(PermissionError("denied"))
    )
    with pytest.raises(BackupError, match="pruning failed"):
        store.prune(1)


def test_signed_channel_rejects_bad_signature_replay_wrong_peer_and_arbitrary_parameters(
    administration,
):
    from app.maintenance_protocol import UnixConnection, signature

    client, service, root, state = administration
    socket_path = client.app.state.settings.maintenance_socket
    body = json.dumps(
        {"operation": "status", "data": {}, "time": int(time.time()), "nonce": "e" * 48}
    ).encode()

    def call(auth):
        connection = UnixConnection(socket_path, expected_uid=os.getuid())
        try:
            connection.request(
                "POST", "/v1/control", body, {"X-Cultivatinator-Signature": auth}
            )
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    assert call("incorrect") == 403
    assert call(signature(service.key, body)) == 200
    assert call(signature(service.key, body)) == 403
    with pytest.raises(MaintenanceError, match="unexpected owner"):
        HelperClient(
            socket_path,
            client.app.state.settings.maintenance_key,
            expected_uid=os.getuid() + 1,
        ).call("status")
    with pytest.raises(MaintenanceError, match="Unsupported"):
        service.dispatch("status", {"path": "/etc/passwd"})


def test_partial_archives_are_hidden_and_publication_recovered_without_duplicate_occurrence(
    administration, monkeypatch
):
    client, service, root, state = administration
    unlock(client)
    store = client.app.state.backup_manager.store
    artifact = create_backup(root)
    original = os.link
    observed = []

    def link(source, target, **kwargs):
        observed.append(store.list())
        return original(source, target, **kwargs)

    monkeypatch.setattr(os, "link", link)
    try:
        saved_value = store.save(artifact.path, "weekly", "2026-11-01T08:00:00+00:00")
    finally:
        artifact.cleanup()
    assert observed == [[]]
    receipt = store.catalog / (saved_value["id"] + ".json")
    value = json.loads(receipt.read_text())
    value["pending"] = True
    atomic_json(receipt, value)
    assert store.list() == []
    reopened = BackupStore(root)
    assert reopened.list()[0]["id"] == saved_value["id"]
    assert not reopened.list()[0]["pending"]


def test_missed_backup_retries_helper_startup_failure_after_backoff_without_duplicate(
    administration, monkeypatch
):
    client, service, root, state = administration
    manager = client.app.state.backup_manager
    settings = manager.store.schedule()
    settings["created_at"] = "2026-01-01T00:00:00+00:00"
    atomic_json(manager.store.schedule_path, settings)
    original = manager.helper_status
    attempts = []

    async def status():
        attempts.append(True)
        if len(attempts) == 1:
            raise MaintenanceError("Helper is starting")
        return await original()

    monkeypatch.setattr(manager, "helper_status", status)
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    client.portal.call(manager.tick, now)
    assert manager.store.list() == []
    assert manager.store.schedule()["last_failure"]["message"] == "Helper is starting"
    client.portal.call(manager.tick, now + timedelta(minutes=14))
    assert len(attempts) == 1
    client.portal.call(manager.tick, now + timedelta(minutes=15))
    client.portal.call(manager.tick, now + timedelta(minutes=16))
    assert len(manager.store.list()) == 1 and len(attempts) == 2
    assert manager.store.schedule()["last_failure"] is None


def test_helper_does_not_report_success_until_maintenance_release_succeeds(
    administration, monkeypatch
):
    import app.maintenance_service as module

    client, service, root, state = administration
    operation = root.parent / "completed-operation"
    operation.mkdir()
    atomic_json(operation / "operation.json", {"state": "completed"})
    value = {"id": str(uuid4()), "preview_id": str(uuid4()), "status": "verifying"}
    atomic_json(state / "latest.json", {"id": value["id"]})

    class Controller:
        fail = True

        def unfreeze(self):
            if self.fail:
                raise OSError("Maintenance release unavailable")

        def start(self):
            pass

        def health(self):
            pass

    controller = Controller()
    service.controller_factory = lambda: controller

    def completed(*args, progress, **kwargs):
        progress("verifying_health", operation)

    monkeypatch.setattr(module, "restore", completed)
    service.perform(value)
    assert service.latest()["status"] == "recovery_required"
    controller.fail = False
    service.resume()
    assert service.latest()["status"] == "complete"


def test_aged_archive_read_access_time_does_not_invalidate_content(administration):
    client, service, root, state = administration
    unlock(client)
    value = saved(client, save=True, download=False)["stored"]
    path = root / "backups" / value["filename"]
    info = path.stat()
    os.utime(path, ns=(info.st_atime_ns - 172800 * 10**9, info.st_mtime_ns))
    assert client.post(f"/api/backups/catalog/{value['id']}/verify").status_code == 200
    preview = client.post("/api/backups/restore/stored", json={"id": value["id"]})
    assert preview.status_code == 200


def test_failed_uploaded_retention_cleans_unpresented_helper_preview(
    administration, monkeypatch
):
    client, service, root, state = administration
    unlock(client)
    data = client.get(saved(client, save=False, download=True)["download_url"]).content
    store = client.app.state.backup_manager.store

    def denied(*args):
        raise OSError("Server copy could not be retained")

    monkeypatch.setattr(store, "save", denied)
    response = client.post("/api/backups/restore/upload?retain=true", content=data)
    assert response.status_code == 400
    assert list(service.previews.iterdir()) == []
    assert list(store.uploads.iterdir()) == []


@pytest.mark.parametrize("source", ["stored", "upload"])
@pytest.mark.parametrize("request_id", [None, "", "not-a-uuid"])
def test_invalid_http_restore_request_id_starts_no_job_and_preview_can_be_cancelled(
    administration, source, request_id
):
    client, service, root, state = administration
    unlock(client)
    backup = saved(client)
    if source == "stored":
        response = client.post(
            "/api/backups/restore/stored", json={"id": backup["stored"]["id"]}
        )
    else:
        data = client.get(backup["download_url"]).content
        response = client.post("/api/backups/restore/upload", content=data)
    assert response.status_code == 200
    preview_id = response.json()["id"]
    payload = {"preview_id": preview_id, "confirmation": "REPLACE-PERSISTENT-DATA"}
    if request_id is not None:
        payload["request_id"] = request_id
    rejected = client.post("/api/backups/restore/confirm", json=payload)
    assert rejected.status_code == 422
    assert any(
        error["loc"] == ["body", "request_id"] for error in rejected.json()["detail"]
    )
    assert service.latest() is None
    assert (
        client.delete("/api/backups/restore/preview/" + preview_id).status_code == 200
    )
    assert list(service.previews.iterdir()) == []
    assert len(client.get("/api/backups/catalog").json()["backups"]) == 1
