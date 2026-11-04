from pathlib import Path
from uuid import uuid4
import json
import time
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.backup_policy import BackupPolicy
from app.backup_store import atomic_json
from app.maintenance_protocol import MaintenanceError
from app import server
from test_backup_administration import (
    administration,
    saved,
    unlock,
    PASSWORD,
    BOOTSTRAP,
)

LAN = pytest.mark.parametrize(
    "administration",
    [{"auth_mode": "trusted_lan", "trusted_networks": "192.168.68.0/24"}],
    indirect=True,
)


def session(client):
    response = client.get("/api/backups/admin/session")
    assert response.status_code == 200, response.text
    value = response.json()
    client.headers["X-Backup-CSRF"] = value["csrf"]
    return value


@pytest.mark.parametrize(
    "mode,networks",
    [
        ("trusted_lan", ""),
        ("typo", ""),
        ("trusted_lan", "invalid"),
        ("trusted_lan", "0.0.0.0/0"),
        ("trusted_lan", "192.168.68.1/24"),
    ],
)
def test_invalid_or_unrestricted_configuration_fails_closed(mode, networks):
    with pytest.raises(ValidationError):
        Settings(backup_auth_mode=mode, trusted_networks=networks)


def test_password_is_default_and_explicit_lan_ipv4_ipv6_are_checked(monkeypatch):
    monkeypatch.delenv("CULTIVATINATOR_BACKUP_AUTH_MODE", raising=False)
    monkeypatch.delenv("CULTIVATINATOR_TRUSTED_NETWORKS", raising=False)
    assert Settings().backup_auth_mode == "password"
    policy = BackupPolicy("trusted_lan", "192.168.68.0/24,fd00:68::/64")
    assert policy.require_peer("192.168.68.25") == "192.168.68.25"
    assert policy.require_peer("::ffff:192.168.68.25") == "192.168.68.25"
    assert policy.require_peer("fd00:68::123") == "fd00:68::123"
    for address in [
        "192.168.69.25",
        "127.0.0.1",
        "172.17.0.1",
        "2001:db8::1",
        "invalid",
    ]:
        with pytest.raises(ValueError):
            policy.require_peer(address)


@pytest.mark.parametrize(
    "mode,proxy_headers", [("password", True), ("trusted_lan", False)]
)
def test_production_server_only_disables_proxy_rewriting_for_trusted_lan(
    monkeypatch, mode, proxy_headers
):
    monkeypatch.setenv("CULTIVATINATOR_BACKUP_AUTH_MODE", mode)
    monkeypatch.setenv("CULTIVATINATOR_TRUSTED_NETWORKS", "192.168.68.0/24")
    calls = []
    monkeypatch.setattr(
        server.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs)
    )
    server.main()
    assert calls[0]["proxy_headers"] is proxy_headers
    assert calls[0]["workers"] == 1


@LAN
def test_trusted_session_opens_without_password_and_never_returns_maintenance_secret(
    administration,
):
    client, service, root, state = administration
    value = session(client)
    assert value["auth_mode"] == "trusted_lan" and value["unlocked"]
    assert value["trusted_networks"] == ["192.168.68.0/24"]
    assert "session" not in value and "a" * 64 not in json.dumps(value)
    assert not (state / "admin.json").exists()
    assert (state / "trusted-sessions.json").exists()
    assert client.get("/api/backups/catalog").status_code == 200
    assert (
        client.post(
            "/api/backups/admin/unlock", json={"passphrase": PASSWORD}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/backups/admin/setup",
            json={"passphrase": PASSWORD, "bootstrap": BOOTSTRAP},
        ).status_code
        == 409
    )
    assert client.post("/api/backups/admin/lock").status_code == 409


@LAN
@pytest.mark.parametrize(
    "address",
    ["192.168.69.25", "203.0.113.10", "127.0.0.1", "172.17.0.1", "2001:db8::1"],
)
def test_outside_client_rejected_even_with_an_existing_cookie(administration, address):
    client, service, root, state = administration
    session(client)
    client._transport.client = (address, 45000)
    for method, path in [
        ("GET", "/admin/session"),
        ("GET", "/catalog"),
        ("GET", "/download"),
        ("POST", "/create"),
        ("POST", "/restore/upload"),
        ("POST", "/restore/confirm"),
        ("PUT", "/schedule"),
    ]:
        assert client.request(method, "/api/backups" + path, json={}).status_code == 403


@LAN
@pytest.mark.parametrize(
    "header",
    [
        "X-Forwarded-For",
        "Forwarded",
        "X-Real-IP",
        "X-Forwarded-Proto",
        "X-Forwarded-Host",
    ],
)
def test_forwarded_client_claims_cannot_grant_access(administration, header):
    client, service, root, state = administration
    session(client)
    # Even if an ASGI server has already rewritten the peer to a LAN address,
    # forwarded requests fail closed rather than trusting the supplied address.
    assert (
        client.get(
            "/api/backups/catalog", headers={header: "192.168.68.25"}
        ).status_code
        == 403
    )
    client._transport.client = ("203.0.113.10", 45000)
    assert (
        client.get(
            "/api/backups/admin/session", headers={header: "192.168.68.25"}
        ).status_code
        == 403
    )


@LAN
def test_origin_csrf_dns_rebinding_and_explicit_confirmation_remain_enforced(
    administration,
):
    client, service, root, state = administration
    session(client)
    assert (
        client.post(
            "/api/backups/create", json={}, headers={"Origin": "http://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/backups/admin/session", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/backups/admin/session",
            headers={"Host": "evil.invalid", "Origin": "http://evil.invalid"},
        ).status_code
        == 403
    )
    for csrf in ["", "invalid"]:
        assert (
            client.post(
                "/api/backups/create", json={}, headers={"X-Backup-CSRF": csrf}
            ).status_code
            == 403
        )
    value = saved(client)["stored"]
    assert (
        client.request(
            "DELETE",
            f"/api/backups/catalog/{value['id']}",
            json={"confirmation": "wrong"},
        ).status_code
        == 400
    )
    preview = client.post(
        "/api/backups/restore/stored", json={"id": value["id"]}
    ).json()
    assert (
        client.post(
            "/api/backups/restore/confirm",
            json={
                "preview_id": preview["id"],
                "request_id": str(uuid4()),
                "confirmation": "wrong",
            },
        ).status_code
        == 400
    )
    assert service.latest() is None
    assert (
        client.delete("/api/backups/restore/preview/" + preview["id"]).status_code
        == 200
    )


@LAN
def test_allowed_lan_backup_operations_download_upload_and_schedule(administration):
    client, service, root, state = administration
    session(client)
    original = client.app.state.backup_manager.store.schedule_info()["schedule"]
    value = saved(client)
    data = client.get(value["download_url"])
    assert data.status_code == 200
    stored_id = value["stored"]["id"]
    assert client.post(f"/api/backups/catalog/{stored_id}/verify").status_code == 200
    assert (
        client.get(f"/api/backups/catalog/{stored_id}/download").content == data.content
    )
    upload = client.post("/api/backups/restore/upload", content=data.content)
    assert upload.status_code == 200
    assert (
        client.delete("/api/backups/restore/preview/" + upload.json()["id"]).status_code
        == 200
    )
    assert client.put("/api/backups/schedule", json=original).status_code == 200
    assert (
        client.request(
            "DELETE",
            f"/api/backups/catalog/{stored_id}",
            json={"confirmation": "DELETE-BACKUP"},
        ).status_code
        == 200
    )
    assert client.get("/api/backups/catalog").json()["backups"] == []


@LAN
def test_expired_or_moved_session_requires_new_automatic_csrf_session(administration):
    client, service, root, state = administration
    first = session(client)
    cookie = client.cookies.get("cultivatinator_backup_admin")
    sessions = service.admin.trusted_sessions()
    next(iter(sessions.values()))["expires"] = time.time() - 1
    atomic_json(state / "trusted-sessions.json", sessions)
    assert client.get("/api/backups/catalog").status_code == 401
    second = session(client)
    assert first["csrf"] != second["csrf"]
    assert cookie != client.cookies.get("cultivatinator_backup_admin")
    client._transport.client = ("192.168.68.26", 45000)
    assert client.get("/api/backups/catalog").status_code == 401
    session(client)
    assert client.get("/api/backups/catalog").status_code == 200


def test_password_credentials_preserved_across_lan_mode_and_tokens_cannot_cross_modes(
    administration,
):
    client, service, root, state = administration
    unlock(client)
    password_cookie = client.cookies.get("cultivatinator_backup_admin")
    before = (state / "admin.json").read_bytes()
    service.policy = BackupPolicy("trusted_lan", "192.168.68.0/24")
    client.app.state.settings.backup_auth_mode = "trusted_lan"
    client.app.state.settings.trusted_networks = "192.168.68.0/24"
    client.base_url = "http://192.168.68.2:8085"
    client.cookies.clear()
    client._transport.client = ("192.168.68.25", 45000)
    session(client)
    trusted_cookie = client.cookies.get("cultivatinator_backup_admin")
    assert trusted_cookie != password_cookie
    saved(client)
    assert (state / "admin.json").read_bytes() == before
    service.policy = BackupPolicy()
    client.app.state.settings.backup_auth_mode = "password"
    assert client.get("/api/backups/catalog").status_code == 401
    # Existing credential works; no password reset or bootstrap is necessary.
    response = client.post("/api/backups/admin/unlock", json={"passphrase": PASSWORD})
    assert response.status_code == 200
    assert response.json()["unlocked"]


@LAN
def test_helper_independently_enforces_mode_and_network(administration):
    client, service, root, state = administration
    session(client)
    for address in ["203.0.113.10", "127.0.0.1"]:
        with pytest.raises(MaintenanceError) as rejected:
            service.dispatch("trusted_session", {"client": address})
        assert rejected.value.status == 403
    with pytest.raises(MaintenanceError) as mismatch:
        service.dispatch(
            "authorize",
            {
                "session": client.cookies.get("cultivatinator_backup_admin"),
                "auth_mode": "password",
            },
        )
    assert mismatch.value.status == 503
    service.policy = BackupPolicy()
    value = client.get("/api/backups/admin/session").json()
    assert not value["available"] and "differs" in value["detail"]
