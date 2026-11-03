"""Managed archives and durable control metadata outside restored directories."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
import json
import os
import re
import shutil
import stat
from .backup_format import BackupError, check_archive, ensure_space, Limits
from .backup_schedule import DEFAULT_SCHEDULE, validate_schedule, bounds

NAME = re.compile(r"(manual|weekly)-(\d{8}T\d{6}Z)-([0-9a-f]{32})\.zip\Z")


def file_identity(info):
    # Reading a valid archive may update atime (not content) on Debian relatime.
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def utcnow():
    return datetime.now(timezone.utc)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + "-" + uuid4().hex)
    try:
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as file:
            json.dump(value, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def identifier(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (TypeError, ValueError, AttributeError) as exc:
        raise BackupError("Invalid managed backup identifier") from exc
    return value


def directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise BackupError("Backup control directories must be real directories")
    return path


class BackupStore:
    def __init__(self, root):
        self.root = directory(Path(root) / "backups")
        self.control = directory(self.root / ".control")
        self.catalog = directory(self.control / "catalog")
        self.uploads = directory(self.control / "uploads")
        self.schedule_path = self.control / "schedule.json"
        if not self.schedule_path.exists():
            atomic_json(
                self.schedule_path,
                {
                    "schedule": dict(DEFAULT_SCHEDULE),
                    "created_at": utcnow().isoformat(),
                    "last_occurrence": None,
                    "last_success": None,
                    "last_failure": None,
                },
            )
        # A killed writer cannot publish a partial ZIP. Hidden temporary files
        # are never catalogued; cleanup only this process's reserved filenames.
        for path in self.root.glob(".partial-*.zip"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
        for path in self.uploads.glob("*.zip"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
        for receipt in self.catalog.glob("*.json"):
            try:
                value = self.receipt(receipt.stem)
                if value.get("pending"):
                    path = self.root / value["filename"]
                    if path.exists() and not path.is_symlink():
                        check_archive(path, extract=False)
                        value["pending"] = False
                        atomic_json(receipt, value)
                    else:
                        receipt.unlink()
            except (OSError, BackupError, ValueError):
                continue

    def schedule(self):
        if self.schedule_path.is_symlink():
            raise BackupError("Unsafe scheduling metadata")
        value = json.loads(self.schedule_path.read_text())
        validate_schedule(value["schedule"])
        return value

    def update_schedule(self, value):
        current = self.schedule()
        current["schedule"] = validate_schedule(value)
        # Schedule edits take effect prospectively, without inventing missed runs.
        current["created_at"] = utcnow().isoformat()
        current["last_occurrence"] = None
        current["retry_after"] = None
        atomic_json(self.schedule_path, current)
        return self.schedule_info()

    def schedule_info(self):
        value = self.schedule()
        value["next_run"] = (
            bounds(value["schedule"], utcnow())[1].isoformat()
            if value["schedule"]["enabled"]
            else None
        )
        return value

    def receipt(self, code):
        identifier(code)
        path = self.catalog / (code + ".json")
        if path.is_symlink() or not path.is_file():
            raise BackupError("Managed backup not found")
        value = json.loads(path.read_text())
        match = NAME.fullmatch(value.get("filename", ""))
        if (
            not match
            or str(UUID(match[3])) != code
            or value.get("id") != code
            or value.get("kind") != match[1]
        ):
            raise BackupError("Invalid managed backup metadata")
        return value

    def path(self, code):
        value = self.receipt(code)
        path = self.root / value["filename"]
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BackupError("Managed archive is missing or unsafe")
        return path, value

    def info(self, code):
        value = self.receipt(code)
        try:
            path, _ = self.path(code)
            info = path.stat()
            if (
                info.st_size != value["size_bytes"]
                or info.st_mtime_ns != value["mtime_ns"]
            ):
                value["validation"] = "changed"
        except (BackupError, OSError):
            value["validation"] = "missing_or_unsafe"
        return value

    def list(self):
        values = []
        for path in self.catalog.glob("*.json"):
            try:
                value = self.info(path.stem)
                if not value.get("pending"):
                    values.append(value)
            except (BackupError, OSError, ValueError, KeyError):
                continue
        return sorted(values, key=lambda v: (v["created_at"], v["id"]), reverse=True)

    def save(self, source, kind="manual", occurrence=None):
        if kind not in {"manual", "weekly"}:
            raise BackupError("Invalid backup kind")
        ensure_space(self.root, source.stat().st_size)
        code = str(uuid4())
        filename = f"{kind}-{utcnow().strftime('%Y%m%dT%H%M%SZ')}-{UUID(code).hex}.zip"
        partial = self.root / (".partial-" + UUID(code).hex + ".zip")
        final = self.root / filename
        try:
            fd = os.open(
                partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as output, source.open("rb") as content:
                shutil.copyfileobj(content, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            manifest = check_archive(partial, extract=False)
            info = partial.stat()
            value = {
                "id": code,
                "filename": filename,
                "kind": kind,
                "created_at": manifest["created_at"],
                "size_bytes": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "validation": "verified",
                "verified_at": utcnow().isoformat(),
                "application_version": manifest["application_version"],
                "migration_revision": manifest["migration_revision"],
                "occurrence": occurrence,
            }
            value["pending"] = True
            # Durable intent is invisible until the fully verified final link exists.
            # Restart can reconstruct successful schedule identity from this receipt.
            atomic_json(self.catalog / (code + ".json"), value)
            os.link(partial, final, follow_symlinks=False)  # exclusive: never overwrite
            partial.unlink()
            value["pending"] = False
            atomic_json(self.catalog / (code + ".json"), value)
            descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return value
        except BaseException:
            if not final.exists():
                (self.catalog / (code + ".json")).unlink(missing_ok=True)
            raise
        finally:
            partial.unlink(missing_ok=True)

    def verify(self, code):
        path, value = self.path(code)
        before = path.stat()
        try:
            manifest = check_archive(path, extract=False)
            if file_identity(path.stat()) != file_identity(before):
                raise BackupError("Archive changed during verification")
            value.update(
                validation="verified",
                verified_at=utcnow().isoformat(),
                size_bytes=before.st_size,
                mtime_ns=before.st_mtime_ns,
                application_version=manifest["application_version"],
                migration_revision=manifest["migration_revision"],
            )
        except BackupError as exc:
            value.update(
                validation="invalid",
                validation_error=str(exc),
                size_bytes=before.st_size,
                mtime_ns=before.st_mtime_ns,
            )
            atomic_json(self.catalog / (code + ".json"), value)
            raise
        value.pop("validation_error", None)
        atomic_json(self.catalog / (code + ".json"), value)
        return value

    def delete(self, code):
        value = self.receipt(code)
        path = self.root / value["filename"]
        if path.is_symlink():
            raise BackupError("Unsafe managed archive; deletion refused")
        path.unlink(missing_ok=True)
        (self.catalog / (code + ".json")).unlink()

    def prune(self, retention, protected=()):
        automatic = [
            value
            for value in self.list()
            if value["kind"] == "weekly" and value["validation"] == "verified"
        ]
        failures = []
        for value in automatic[retention:]:
            if value["id"] in protected:
                continue
            try:
                self.delete(value["id"])
            except (OSError, BackupError) as exc:
                failures.append(f"{value['filename']}: {exc}")
        if failures:
            raise BackupError(
                "Backup saved, but retention pruning failed: " + "; ".join(failures)
            )

    def usage(self):
        # Count only managed archives, not arbitrary files in the installation.
        values = self.list()
        total = sum(
            v["size_bytes"] for v in values if v["validation"] != "missing_or_unsafe"
        )
        return {
            "used_bytes": total,
            "available_bytes": shutil.disk_usage(self.root).free,
        }
