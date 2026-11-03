"""Coordinated temporary backup downloads; browser restore is deliberately absent."""

import anyio
import threading
import time
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse
from .backup_format import BackupError, create_backup

router = APIRouter(prefix="/api/backups", tags=["Complete workspace backup"])
TTL = 300


class MutationGate:
    def __init__(self, app, gate):
        self.app, self.gate = app, gate

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            async with self.gate:
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class Download(FileResponse):
    def __init__(self, artifact):
        self.artifact = artifact
        super().__init__(
            artifact.path,
            media_type="application/zip",
            filename=artifact.filename,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self.artifact.cleanup)


async def capture(request):
    cancelled = threading.Event()
    artifact = None

    async def watch():
        while not await request.is_disconnected():
            await anyio.sleep(0.2)
        cancelled.set()

    try:
        failure = None
        async with anyio.create_task_group() as group:
            group.start_soon(watch)
            try:
                artifact = await anyio.to_thread.run_sync(
                    lambda: create_backup(
                        request.app.state.settings.data_dir, cancelled.is_set
                    )
                )
            except (BackupError, OSError) as exc:
                failure = exc
            finally:
                group.cancel_scope.cancel()
        if failure:
            raise failure
        return artifact
    except (BackupError, OSError) as exc:
        if artifact:
            artifact.cleanup()
        raise HTTPException(503, f"Backup was not created: {exc}") from exc
    except BaseException:
        cancelled.set()
        if artifact:
            artifact.cleanup()
        raise


@router.get("/download")
async def download(request: Request):
    if request.query_params:
        raise HTTPException(
            400, "Backup download does not accept filesystem paths or parameters"
        )
    async with request.app.state.mutation_gate:
        artifact = await capture(request)
    return Download(artifact)


@router.post("/prepare", status_code=201)
async def prepare(request: Request):
    # MutationGate already covers this whole POST. Do not acquire it twice.
    artifact = await capture(request)
    token = str(uuid4())
    request.app.state.backups[token] = (time.monotonic() + TTL, artifact)
    return {
        "download_url": f"/api/backups/prepared/{token}",
        "filename": artifact.filename,
        "size_bytes": artifact.path.stat().st_size,
        "expires_in_seconds": TTL,
    }


@router.get("/prepared/{token}")
async def prepared(token: UUID, request: Request):
    item = request.app.state.backups.pop(str(token), None)
    if item is None:
        raise HTTPException(
            404, "Backup download expired or was already used; prepare another backup"
        )
    expires, artifact = item
    if expires < time.monotonic():
        artifact.cleanup()
        raise HTTPException(410, "Backup expired; prepare another backup")
    return Download(artifact)


@router.delete("/prepared/{token}", status_code=204)
async def cancel(token: UUID, request: Request):
    item = request.app.state.backups.pop(str(token), None)
    if item:
        item[1].cleanup()


async def expire_backups(app):
    while True:
        await anyio.sleep(15)
        for token, (expires, artifact) in list(app.state.backups.items()):
            if expires < time.monotonic():
                app.state.backups.pop(token, None)
                await anyio.to_thread.run_sync(artifact.cleanup)
