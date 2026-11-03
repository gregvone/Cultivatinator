"""Focused browser administration, independent of cultivation authentication."""

import hmac
import anyio
from fastapi import Request, HTTPException
from .maintenance_protocol import MaintenanceError, read_key

COOKIE = "cultivatinator_backup_admin"


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
            "session": request.cookies.get(COOKIE, ""),
            "csrf": request.headers.get("x-backup-csrf", ""),
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
