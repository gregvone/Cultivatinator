"""Browser backup administration. No user-provided filesystem or Docker targets."""

from pathlib import Path
from uuid import UUID, uuid4
import os
import time
import anyio
from fastapi import APIRouter, Request, Response, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import FileResponse
from .backup_access import (
    COOKIE,
    browser_guard,
    helper,
    require_admin,
    credentials,
    policy,
    trusted_peer,
)
from .backup_format import BackupError, Limits, ensure_space
from .backup_store import utcnow
from .backups import capture, TTL

router = APIRouter(prefix="/api/backups", tags=["Backup administration"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Unlock(Input):
    passphrase: str = Field(min_length=12, max_length=1024)
    bootstrap: str = Field(default="", max_length=256)


class Create(Input):
    save: bool = True
    download: bool = True


class Delete(Input):
    confirmation: str


class Selection(Input):
    id: UUID


class Restore(Input):
    preview_id: UUID
    request_id: UUID
    confirmation: str


class Schedule(Input):
    enabled: bool
    weekday: int = Field(ge=0, le=6)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(min_length=1, max_length=100)
    retention: int = Field(ge=1, le=52)


def session_cookie(request, response, token):
    response.set_cookie(
        COOKIE,
        token,
        max_age=1800,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/api/backups",
    )


def fail(exc):
    raise HTTPException(409 if "in progress" in str(exc) else 400, str(exc)) from exc


@router.get("/admin/session")
async def session(request: Request, response: Response):
    browser_guard(request)
    configured = policy(request)
    client = trusted_peer(request) if configured.mode == "trusted_lan" else None
    response.headers["Cache-Control"] = "no-store"
    try:
        status = await helper(request, "status")
        if status.get("auth_mode", "password") != configured.mode or (
            configured.mode == "trusted_lan"
            and status.get("trusted_networks") != configured.cidrs
        ):
            raise HTTPException(
                503,
                "Backup authentication configuration differs from the maintenance helper. Re-run the helper installer with the current Compose configuration.",
            )
    except HTTPException as exc:
        return {
            "available": False,
            "configured": False,
            "unlocked": False,
            "detail": str(exc.detail),
        }
    if configured.mode == "trusted_lan":
        result = await helper(
            request,
            "trusted_session",
            {"client": client, "session": request.cookies.get(COOKIE, "")},
        )
        token = result.pop("session")
        session_cookie(request, response, token)
        return {
            "available": True,
            "auth_mode": "trusted_lan",
            "trusted_networks": configured.cidrs,
            **result,
        }
    if request.cookies.get(COOKIE):
        try:
            return {
                "available": True,
                **await helper(request, "authorize", credentials(request)),
            }
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
    return {"available": True, "configured": status["configured"], "unlocked": False}


async def login(action, data, request, response):
    browser_guard(request)
    if policy(request).mode == "trusted_lan":
        trusted_peer(request)
        raise HTTPException(
            409, "Trusted LAN mode does not use password setup or unlock"
        )
    result = await helper(
        request,
        action,
        {
            **data.model_dump(),
            "client": request.client.host if request.client else "unknown",
        },
    )
    token = result.pop("session")
    session_cookie(request, response, token)
    response.headers["Cache-Control"] = "no-store"
    return {"available": True, **result}


@router.post("/admin/setup")
async def setup(data: Unlock, request: Request, response: Response):
    return await login("setup", data, request, response)


@router.post("/admin/unlock")
async def unlock(data: Unlock, request: Request, response: Response):
    return await login("unlock", data, request, response)


@router.post("/admin/lock", dependencies=[Depends(require_admin)])
async def lock(request: Request, response: Response):
    if policy(request).mode == "trusted_lan":
        raise HTTPException(409, "Trusted LAN mode does not have a password lock")
    await helper(request, "lock", credentials(request))
    response.delete_cookie(
        COOKIE, path="/api/backups", httponly=True, samesite="strict"
    )
    return {"unlocked": False}


@router.get("/catalog", dependencies=[Depends(require_admin)])
async def catalog(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    manager = request.app.state.backup_manager
    return {
        "backups": manager.store.list(),
        "storage": manager.store.usage(),
        "schedule": manager.store.schedule_info(),
        "job": manager.job,
        **await helper(request, "status"),
    }


@router.post("/create", dependencies=[Depends(require_admin)])
async def create(data: Create, request: Request):
    if not data.save and not data.download:
        raise HTTPException(422, "Choose at least one backup destination")
    manager = request.app.state.backup_manager
    artifact = None
    try:
        async with manager.exclusive("manual backup"):
            # MutationGate holds the entire HTTP POST, including capture and save.
            artifact = await capture(request)
            result = {"stored": None, "download_url": None}
            if data.save:
                result["stored"] = await anyio.to_thread.run_sync(
                    lambda: manager.store.save(artifact.path)
                )
            if data.download:
                token = str(uuid4())
                request.app.state.backups[token] = (time.monotonic() + TTL, artifact)
                result.update(
                    download_url=f"/api/backups/prepared/{token}",
                    filename=artifact.filename,
                    expires_in_seconds=TTL,
                )
                artifact = None
            return result
    except (BackupError, OSError) as exc:
        fail(exc)
    finally:
        if artifact:
            artifact.cleanup()


@router.post("/catalog/{code}/verify", dependencies=[Depends(require_admin)])
async def verify(code: UUID, request: Request):
    manager = request.app.state.backup_manager
    try:
        async with manager.exclusive("archive verification"):
            return await anyio.to_thread.run_sync(
                lambda: manager.store.verify(str(code))
            )
    except (BackupError, OSError) as exc:
        fail(exc)


class ManagedDownload(FileResponse):
    def __init__(self, manager, code):
        self.manager, self.code = manager, code
        # Resolve only after acquiring the operation lock below.
        super().__init__(
            "unused",
            media_type="application/zip",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def __call__(self, scope, receive, send):
        try:
            async with self.manager.exclusive("stored backup download"):
                value = self.manager.store.info(self.code)
                if value["validation"] != "verified":
                    raise BackupError(
                        "Verify this archive before downloading or restoring it"
                    )
                path, _ = self.manager.store.path(self.code)
                self.path = path
                self.headers["content-disposition"] = (
                    f'attachment; filename="{value["filename"]}"'
                )
                await super().__call__(scope, receive, send)
        except (BackupError, OSError) as exc:
            fail(exc)


@router.get("/catalog/{code}/download", dependencies=[Depends(require_admin)])
async def download(code: UUID, request: Request):
    return ManagedDownload(request.app.state.backup_manager, str(code))


@router.delete("/catalog/{code}", dependencies=[Depends(require_admin)])
async def delete(code: UUID, data: Delete, request: Request):
    if data.confirmation != "DELETE-BACKUP":
        raise HTTPException(400, "Explicit backup deletion confirmation is required")
    manager = request.app.state.backup_manager
    try:
        async with manager.exclusive("backup deletion"):
            await anyio.to_thread.run_sync(lambda: manager.store.delete(str(code)))
        return {"deleted": str(code)}
    except (BackupError, OSError) as exc:
        fail(exc)


@router.put("/schedule", dependencies=[Depends(require_admin)])
async def schedule(data: Schedule, request: Request):
    manager = request.app.state.backup_manager
    try:
        async with manager.exclusive("schedule update"):
            return manager.store.update_schedule(data.model_dump())
    except (BackupError, OSError, ValueError) as exc:
        fail(exc)


@router.post("/restore/stored", dependencies=[Depends(require_admin)])
async def stored_restore(data: Selection, request: Request):
    manager = request.app.state.backup_manager
    try:
        async with manager.exclusive("restore preview"):
            return await helper(
                request,
                "prepare_restore",
                {**credentials(request), "source": "stored", "id": str(data.id)},
            )
    except (BackupError, OSError) as exc:
        fail(exc)


@router.post("/restore/upload", dependencies=[Depends(require_admin)])
async def uploaded_restore(request: Request, retain: bool = False):
    manager = request.app.state.backup_manager
    path = manager.store.uploads / (str(uuid4()) + ".zip")
    count = 0
    try:
        async with manager.exclusive("restore upload and verification"):
            length = request.headers.get("content-length")
            if length and (
                not length.isdecimal() or int(length) > Limits().archive_bytes
            ):
                raise HTTPException(413, "Restore upload exceeds the archive limit")
            if length:
                ensure_space(path.parent, int(length))
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as output:
                async for chunk in request.stream():
                    count += len(chunk)
                    if count > Limits().archive_bytes:
                        raise HTTPException(
                            413, "Restore upload exceeds the archive limit"
                        )
                    ensure_space(path.parent, len(chunk))
                    await anyio.to_thread.run_sync(lambda: output.write(chunk))
                output.flush()
                os.fsync(output.fileno())
            if not count:
                raise HTTPException(400, "Select a nonempty backup ZIP")
            preview = await helper(
                request,
                "prepare_restore",
                {**credentials(request), "source": "upload", "id": path.stem},
            )
            if retain:
                try:
                    preview["retained_backup"] = await anyio.to_thread.run_sync(
                        lambda: manager.store.save(path)
                    )
                except BaseException:
                    with anyio.CancelScope(shield=True):
                        await helper(
                            request,
                            "cancel_preview",
                            {**credentials(request), "id": preview["id"]},
                        )
                    raise
            return preview
    except (BackupError, OSError) as exc:
        fail(exc)
    finally:
        path.unlink(missing_ok=True)


@router.delete("/restore/preview/{code}", dependencies=[Depends(require_admin)])
async def cancel_preview(code: UUID, request: Request):
    return await helper(
        request, "cancel_preview", {**credentials(request), "id": str(code)}
    )


@router.post("/restore/confirm", dependencies=[Depends(require_admin)])
async def confirm(data: Restore, request: Request):
    manager = request.app.state.backup_manager
    try:
        async with manager.exclusive("restore submission", allow_restore=True):
            return await helper(
                request,
                "restore",
                {
                    **credentials(request),
                    "preview_id": str(data.preview_id),
                    "request_id": str(data.request_id),
                    "confirmation": data.confirmation,
                },
            )
    except (BackupError, OSError) as exc:
        fail(exc)


@router.get("/restore/status", dependencies=[Depends(require_admin)])
async def restore_status(
    request: Request, response: Response, operation_id: UUID | None = None
):
    response.headers["Cache-Control"] = "no-store"
    return await helper(
        request, "status", {"id": str(operation_id)} if operation_id else {}
    )
