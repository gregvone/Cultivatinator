"""Focused browser administration, independent of cultivation authentication."""

import hmac
import anyio
from fastapi import Request, HTTPException
from .maintenance_protocol import MaintenanceError, read_key
from .backup_policy import BackupPolicy

COOKIE = "cultivatinator_backup_admin"


def policy(request):
    settings = request.app.state.settings
    return BackupPolicy(settings.backup_auth_mode, settings.trusted_networks)


def trusted_peer(request):
    configured = policy(request)
    # Also fail closed with native ASGI servers that might already have applied
    # proxy headers. Production disables that rewriting in trusted_lan mode.
    if any(
        name in request.headers
        for name in (
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-proto",
            "x-forwarded-host",
            "x-real-ip",
        )
    ):
        raise HTTPException(
            403,
            "Trusted LAN backup administration requires a direct connection without forwarding headers",
        )
    try:
        address = configured.require_peer(
            request.client.host if request.client else None
        )
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not configured.allows_host(request.url.hostname):
        raise HTTPException(
            403,
            "Use a configured LAN IP address or a private hostname (.local or single-label) for trusted LAN administration",
        )
    return address


def credentials(request):
    result = {
        "session": request.cookies.get(COOKIE, ""),
        "csrf": request.headers.get("x-backup-csrf", ""),
    }
    if policy(request).mode == "trusted_lan":
        result.update(auth_mode="trusted_lan", client=trusted_peer(request))
    return result


def browser_guard(request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin backup administration is not allowed")
    if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        raise HTTPException(403, "Use Backup & Restore from this application origin")


async def helper(request, operation, data=None):
    try:
        return await anyio.to_thread.run_sync(
            lambda: request.app.state.maintenance.call(operation, data)
        )
    except MaintenanceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


async def require_admin(request: Request):
    browser_guard(request)
    return await helper(
        request,
        "authorize",
        {
            **credentials(request),
            "write": request.method not in {"GET", "HEAD", "OPTIONS"},
        },
    )


def machine_authorized(request):
    supplied = request.headers.get("x-cultivatinator-maintenance", "")
    if not supplied:
        return False
    try:
        expected = read_key(request.app.state.settings.maintenance_key).decode()
    except (OSError, MaintenanceError):
        return False
    return hmac.compare_digest(supplied, expected)


async def admin_or_machine(request: Request):
    if not machine_authorized(request):
        await require_admin(request)
