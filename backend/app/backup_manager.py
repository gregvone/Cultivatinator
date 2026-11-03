"""One-process backup jobs; weekly state survives application/data restores."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import logging
import anyio
from .backup_format import BackupError, create_backup
from .backup_schedule import bounds
from .backup_store import BackupStore, atomic_json, utcnow
from .maintenance_protocol import MaintenanceError

log = logging.getLogger(__name__)


class BackupManager:
    def __init__(self, app):
        self.app = app
        self.store = BackupStore(app.state.settings.data_dir)
        self.lock = anyio.Lock()
        self.job = None

    async def helper_status(self):
        return await anyio.to_thread.run_sync(
            lambda: self.app.state.maintenance.call("status")
        )

    @asynccontextmanager
    async def exclusive(self, operation, allow_restore=False):
        try:
            self.lock.acquire_nowait()
        except anyio.WouldBlock as exc:
            raise BackupError("Another backup operation is in progress") from exc
        try:
            try:
                status = await self.helper_status()
            except MaintenanceError as exc:
                raise BackupError(str(exc)) from exc
            if status.get("active") and not allow_restore:
                raise BackupError(
                    "A restore is in progress; backup changes are unavailable"
                )
            self.job = operation
            yield
        finally:
            self.job = None
            self.lock.release()

    async def tick(self, now=None):
        now = now or utcnow()
        state = self.store.schedule()
        schedule = state["schedule"]
        if not schedule["enabled"]:
            return
        due, _ = bounds(schedule, now)
        key = due.isoformat()
        if (
            due < datetime.fromisoformat(state["created_at"])
            or state["last_occurrence"] == key
        ):
            return
        if (
            (
                state.get("last_failure", {}).get("occurrence")
                if state.get("last_failure")
                else None
            )
            == key
            and state.get("retry_after")
            and now < datetime.fromisoformat(state["retry_after"])
        ):
            return
        # A crash after publishing the ZIP and before schedule bookkeeping must
        # not make a second archive for the same occurrence.
        existing = next(
            (
                v
                for v in self.store.list()
                if v["kind"] == "weekly"
                and v.get("occurrence") == key
                and v["validation"] == "verified"
            ),
            None,
        )
        try:
            async with self.exclusive("automatic backup"):
                state = self.store.schedule()
                if state["last_occurrence"] == key:
                    return
                if existing:
                    saved = existing
                else:
                    async with self.app.state.mutation_gate:
                        artifact = await anyio.to_thread.run_sync(
                            lambda: create_backup(self.app.state.settings.data_dir)
                        )
                    try:
                        saved = await anyio.to_thread.run_sync(
                            lambda: self.store.save(artifact.path, "weekly", key)
                        )
                    finally:
                        artifact.cleanup()
                state.update(
                    last_occurrence=key,
                    last_success={
                        "created_at": saved["created_at"],
                        "backup_id": saved["id"],
                    },
                    last_failure=None,
                    retry_after=None,
                )
                atomic_json(self.store.schedule_path, state)
                await anyio.to_thread.run_sync(
                    lambda: self.store.prune(schedule["retention"])
                )
        except (BackupError, MaintenanceError, OSError, ValueError) as exc:
            log.error("Automatic backup failed: %s", exc)
            state = self.store.schedule()
            # Retry the latest due occurrence after bounded backoff. This also
            # handles helper startup order without losing a whole week's backup.
            state.update(
                last_failure={
                    "at": now.isoformat(),
                    "message": str(exc),
                    "occurrence": key,
                },
                retry_after=(now + timedelta(minutes=15)).isoformat(),
            )
            atomic_json(self.store.schedule_path, state)

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Backup scheduler could not read or persist its state")
            await anyio.sleep(30)
