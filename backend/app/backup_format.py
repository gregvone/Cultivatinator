"""Portable backup format and verification. Standard library only, also used on Debian."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import ast
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import struct
import tempfile
import time
import zipfile
from .version import VERSION

ROOTS = ("database", "photos", "files", "settings")
DATABASE = "database/cultivatinator.sqlite3"
FORMAT = 1
RUNTIME_LOCK = ".cultivatinator-runtime.lock"
RESTORE_MARKER = ".cultivatinator-restore-in-progress.json"
MANIFEST_LIMIT = 4 * 1024 * 1024
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


@contextmanager
def connect(*args, **kwargs):
    connection = sqlite3.connect(*args, **kwargs)
    try:
        yield connection
    finally:
        connection.close()


def staging_base(root):
    digest = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:16]
    base = (
        Path(tempfile.gettempdir()) / f"cultivatinator-backups-{os.getuid()}-{digest}"
    )
    base.mkdir(mode=0o700, exist_ok=True)
    if (
        base.is_symlink()
        or base.stat().st_uid != os.getuid()
        or base.stat().st_mode & 0o077
    ):
        raise BackupError("Unsafe backup staging directory permissions")
    return base


def clean_stale_backups(root):
    # Called only while holding the exclusive application lease at startup.
    for path in staging_base(root).iterdir():
        if (
            path.name.startswith("cultivatinator-backup-")
            and path.is_dir()
            and not path.is_symlink()
        ):
            shutil.rmtree(path)


@dataclass(frozen=True)
class Limits:
    entries: int = 100000
    total_bytes: int = 32 * 1024**3
    file_bytes: int = 8 * 1024**3
    archive_bytes: int = 40 * 1024**3
    ratio: int = 1000


def revision():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    heads, parents = set(), set()
    for file in versions.glob("*.py"):
        for node in ast.parse(file.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {
                        "revision",
                        "down_revision",
                    }:
                        value = ast.literal_eval(node.value)
                        if target.id == "revision":
                            heads.add(value)
                        elif value:
                            parents.update(
                                value if isinstance(value, tuple) else [value]
                            )
    heads -= parents
    if len(heads) != 1:
        raise BackupError("Installed application must have exactly one migration head")
    return heads.pop()


def safe_path(name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or "\x00" in name
        or len(name) > 1000
    ):
        raise BackupError("Unsafe archive path")
    if (
        name.startswith("/")
        or name.endswith("/")
        or any(x in {"", ".", ".."} for x in name.split("/"))
    ):
        raise BackupError(f"Unsafe archive path: {name!r}")
    parts = PurePosixPath(name).parts
    if parts[0] not in ROOTS or any(":" in p for p in parts):
        raise BackupError(
            f"Archive path outside the four application directories: {name!r}"
        )
    return name


def ensure_space(path, needed):
    if shutil.disk_usage(path).free < needed + 16 * 1024**2:
        raise BackupError(
            f"Insufficient disk space: need at least {needed + 16 * 1024**2} free bytes at {path}"
        )


@contextmanager
def lease(root, name=RUNTIME_LOCK):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size or info.st_nlink != 1:
            raise BackupError(
                "Workspace lock must be an empty regular file without hard links"
            )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupError(
                "Workspace is in use by another application/maintenance process"
            ) from exc
        yield fd
    finally:
        os.close(fd)


def normalized_schema(sql, kind):
    sql = re.sub(r"\s+", " ", sql).strip()
    if kind != "table":
        return sql
    # Alembic's reflected foreign-key constraints can be emitted in different
    # orders in different Python processes. Order of top-level table clauses
    # does not change their meaning; column/constraint contents remain exact.
    start, end = sql.index("("), sql.rindex(")")
    body = sql[start + 1 : end]
    parts, current, depth, quote = [], [], 0, None
    for char in body:
        if quote:
            if char == quote:
                quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0 and quote is None:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return sql[:start] + "(" + ", ".join(sorted(parts)) + ")" + sql[end + 1 :]


def schema_catalog(connection):
    return [
        list(row[:3]) + [normalized_schema(row[3], row[0])]
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]


def archive_header(path, limits):
    # Bound central-directory parsing before ZipFile can allocate entry objects.
    with Path(path).open("rb") as file:
        file.seek(0, 2)
        length = file.tell()
        file.seek(max(0, length - 65557))
        tail = file.read()
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail) - offset < 22:
            raise BackupError("Truncated/missing ZIP end record")
        end = struct.unpack("<4s4H2LH", tail[offset : offset + 22])
        if end[1] or end[2] or end[3] != end[4] or len(tail) - offset != 22 + end[7]:
            raise BackupError("Multipart/malformed ZIP is unsupported")
        count, size = end[4], end[5]
        if count == 65535 or size == 0xFFFFFFFF or end[6] == 0xFFFFFFFF:
            eocd = length - len(tail) + offset
            if eocd < 20:
                raise BackupError("Malformed ZIP64 locator")
            file.seek(eocd - 20)
            locator = struct.unpack("<4sLQL", file.read(20))
            if locator[0] != b"PK\x06\x07" or locator[1] or locator[3] != 1:
                raise BackupError("Unsupported ZIP64 locator")
            file.seek(locator[2])
            raw = file.read(56)
            if len(raw) != 56:
                raise BackupError("Truncated ZIP64 end record")
            record = struct.unpack("<4sQ2H2L4Q", raw)
            if (
                record[0] != b"PK\x06\x06"
                or record[4]
                or record[5]
                or record[6] != record[7]
            ):
                raise BackupError("Unsupported ZIP64 end record")
            count, size = record[7], record[8]
        if count > limits.entries or size > 16 * 1024**2:
            raise BackupError("ZIP central directory exceeds metadata limits")


def inspect_database(path, inventory=None, cancelled=None):
    cancelled = cancelled or (lambda: False)
    deadline = time.monotonic() + 60
    try:
        with connect(
            Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5
        ) as conn:
            conn.enable_load_extension(False)
            conn.set_progress_handler(
                lambda: int(time.monotonic() > deadline or cancelled()), 10000
            )
            conn.execute("PRAGMA trusted_schema=OFF")
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise BackupError("SQLite integrity check failed")
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise BackupError("SQLite foreign-key check failed")
            rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
            if rows != [(revision(),)]:
                raise BackupError(
                    "Database migration revision is incompatible with this checkout"
                )
            expected = json.loads(
                Path(__file__).with_name("backup_schema.json").read_text()
            )
            if schema_catalog(conn) != expected:
                raise BackupError(
                    "Database schema does not match the installed application, despite its migration label"
                )
            # Checksums alone do not establish that database photo references are recoverable.
            photos = conn.execute(
                "SELECT filename, thumbnail FROM photo_attachments"
            ).fetchall()
            for pair in photos:
                for filename in pair:
                    if (
                        not isinstance(filename, str)
                        or "/" in filename
                        or "\\" in filename
                    ):
                        raise BackupError("Unsafe photograph filename in database")
                    name = safe_path("photos/" + filename)
                    if inventory is not None and name not in inventory:
                        raise BackupError(
                            f"Database references a missing photograph or thumbnail: {name}"
                        )
            return rows[0][0]
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite snapshot verification failed: {exc}") from exc


def dataset_entries(root):
    root = Path(root)
    directories, files = [], []
    for top in ROOTS:
        base = root / top
        if base.is_symlink() or not base.is_dir():
            raise BackupError(f"Missing or unsafe data directory: {top}")
        directories.append(top)
        for parent, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".cache"})
            for name in [*dirs, *sorted(names)]:
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if relative in {
                    DATABASE + "-wal",
                    DATABASE + "-shm",
                    DATABASE + "-journal",
                }:
                    continue
                if name.endswith(".removed") and name.startswith("."):
                    continue
                safe_path(relative)
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    directories.append(relative)
                elif stat.S_ISREG(mode):
                    files.append((relative, path))
                else:
                    raise BackupError(
                        f"Symlinks and special files cannot be backed up: {relative}"
                    )
    return sorted(directories), sorted(files)


@dataclass
class Artifact:
    temporary: tempfile.TemporaryDirectory
    path: Path
    filename: str

    def cleanup(self):
        self.temporary.cleanup()


def create_backup(root, cancelled=None, stage_parent=None):
    """Caller must hold the HTTP mutation gate or prove the application is stopped."""
    cancelled = cancelled or (lambda: False)
    root = Path(root).resolve()
    temporary = tempfile.TemporaryDirectory(
        prefix="cultivatinator-backup-", dir=stage_parent or staging_base(root)
    )
    stage = Path(temporary.name)
    try:
        if any(stage.is_relative_to(root / p) for p in ROOTS):
            raise BackupError("Backup staging must be outside persistent data")
        dirs, files = dataset_entries(root)
        wal = Path(str(root / DATABASE) + "-wal")
        database_size = (root / DATABASE).stat().st_size + (
            wal.stat().st_size if wal.exists() else 0
        )
        media_size = sum(p.stat().st_size for name, p in files if name != DATABASE)
        ensure_space(stage, 3 * database_size + 2 * media_size + MANIFEST_LIMIT)
        snapshot = stage / "snapshot.sqlite3"
        # The separate reservation blocks out-of-band SQLite writers. The source
        # backup connection stays read-only; backing up a writer transaction hangs.
        with connect(root / DATABASE, timeout=30) as reservation:
            reservation.execute("BEGIN IMMEDIATE")
            try:
                deadline = time.monotonic() + 900

                def check(*args):
                    if cancelled():
                        raise BackupError("Backup cancelled")
                    if time.monotonic() > deadline:
                        raise BackupError(
                            "Database snapshot timed out; retry during a quieter period"
                        )

                with connect(
                    (root / DATABASE).as_uri() + "?mode=ro", uri=True
                ) as source, connect(snapshot) as target:
                    source.backup(target, pages=256, progress=check, sleep=0.01)
                    target.execute("PRAGMA journal_mode=DELETE")
                db_revision = inspect_database(snapshot, cancelled=cancelled)
                archive = stage / "workspace.zip"
                inventory = {}
                seen = set()
                with zipfile.ZipFile(
                    archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True
                ) as zipout:
                    for name in dirs:
                        if name.casefold() in seen:
                            raise BackupError("Case-conflicting dataset paths")
                        seen.add(name.casefold())
                        info = zipfile.ZipInfo(name + "/")
                        info.create_system = 3
                        info.external_attr = (stat.S_IFDIR | 0o700) << 16
                        zipout.writestr(info, b"")
                    for name, path in files:
                        check()
                        if name.casefold() in seen:
                            raise BackupError("Case-conflicting dataset paths")
                        seen.add(name.casefold())
                        if name == DATABASE:
                            path = snapshot
                        before = path.stat(follow_symlinks=False)
                        if not stat.S_ISREG(before.st_mode):
                            raise BackupError("Data changed during backup")
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                        digest = hashlib.sha256()
                        size = 0
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                        with os.fdopen(fd, "rb") as source, zipout.open(
                            info, "w", force_zip64=True
                        ) as output:
                            if (
                                os.fstat(source.fileno()).st_ino,
                                os.fstat(source.fileno()).st_dev,
                            ) != (before.st_ino, before.st_dev):
                                raise BackupError("Data changed during backup")
                            while chunk := source.read(CHUNK):
                                check()
                                output.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                        after = path.stat(follow_symlinks=False)
                        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                            after.st_size,
                            after.st_mtime_ns,
                            after.st_ino,
                        ):
                            raise BackupError(
                                "An external process changed data during backup; retry in maintenance"
                            )
                        inventory[name] = {"size": size, "sha256": digest.hexdigest()}
                    inspect_database(snapshot, inventory, cancelled=cancelled)
                    manifest = {
                        "format_version": FORMAT,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "application": "Cultivatinator",
                        "application_version": VERSION,
                        "migration_revision": db_revision,
                        "compatibility": {
                            "restore_protocol": 1,
                            "database": DATABASE,
                            "directories": list(ROOTS),
                        },
                        "directories": dirs,
                        "files": inventory,
                    }
                    encoded = json.dumps(
                        manifest, sort_keys=True, ensure_ascii=False
                    ).encode()
                    if len(encoded) > MANIFEST_LIMIT:
                        raise BackupError(
                            "Backup inventory exceeds the supported manifest size"
                        )
                    zipout.writestr("manifest.json", encoded)
                # Apply the same structural/size constraints that the host verifier uses.
                check_archive(
                    archive, extract=False, stage_parent=stage, cancelled=cancelled
                )
            finally:
                reservation.rollback()
        return Artifact(
            temporary,
            archive,
            "cultivatinator-backup-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + ".zip",
        )
    except BaseException:
        temporary.cleanup()
        raise


def no_duplicate_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Duplicate manifest key")
        result[key] = value
    return result


@dataclass
class Verified:
    temporary: tempfile.TemporaryDirectory
    root: Path
    manifest: dict

    def cleanup(self):
        self.temporary.cleanup()


def check_archive(
    archive, extract=True, stage_parent=None, limits=Limits(), cancelled=None
):
    """Validate all bytes before exposing a dataset; never extract into a live root."""
    cancelled = cancelled or (lambda: False)
    temporary = tempfile.TemporaryDirectory(
        prefix="cultivatinator-verify-", dir=stage_parent
    )
    stage = Path(temporary.name)
    try:
        if Path(archive).stat().st_size > limits.archive_bytes:
            raise BackupError("Archive exceeds compressed-size limit")
        archive_header(archive, limits)
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            if len(infos) > limits.entries:
                raise BackupError("Archive has too many entries")
            names = {}
            folded = set()
            total = 0
            for info in infos:
                raw = info.filename
                if raw != info.orig_filename:
                    raise BackupError("Malformed archive entry name")
                name = raw[:-1] if info.is_dir() else raw
                if name != "manifest.json":
                    safe_path(name)
                if name in names or name.casefold() in folded:
                    raise BackupError("Duplicate/conflicting archive paths")
                names[name] = info
                folded.add(name.casefold())
                mode = info.external_attr >> 16
                if info.flag_bits & 1 or info.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    raise BackupError("Encrypted/unsupported ZIP entry")
                kind = stat.S_IFMT(mode)
                if (
                    kind not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or info.is_dir() != (kind == stat.S_IFDIR)
                    and kind != 0
                ):
                    raise BackupError("Symlink or special/conflicting archive entry")
                if (
                    info.file_size > limits.file_bytes
                    or info.file_size / max(1, info.compress_size) > limits.ratio
                ):
                    raise BackupError("ZIP decompression limits exceeded")
                if info.is_dir() and info.file_size:
                    raise BackupError("Directory entry contains file data")
                total += info.file_size
            if total > limits.total_bytes:
                raise BackupError("Archive exceeds total uncompressed-size limit")
            meta = names.get("manifest.json")
            if not meta or meta.file_size > MANIFEST_LIMIT or meta.is_dir():
                raise BackupError("Missing/oversized manifest")
            manifest = json.loads(
                source.read(meta), object_pairs_hook=no_duplicate_json
            )
            if (
                not isinstance(manifest, dict)
                or type(manifest.get("format_version")) is not int
                or manifest["format_version"] != FORMAT
            ):
                raise BackupError("Unsupported backup format version")
            if (
                manifest.get("application") != "Cultivatinator"
                or manifest.get("application_version") != VERSION
                or manifest.get("migration_revision") != revision()
            ):
                raise BackupError(
                    "Backup application/database version is incompatible; use a matching checkout/image"
                )
            if manifest.get("compatibility") != {
                "restore_protocol": 1,
                "database": DATABASE,
                "directories": list(ROOTS),
            }:
                raise BackupError("Unsupported backup compatibility metadata")
            stamp = datetime.fromisoformat(manifest.get("created_at", ""))
            if stamp.tzinfo is None:
                raise BackupError("Backup timestamp must include timezone")
            inventory = manifest.get("files")
            dirs = manifest.get("directories")
            if (
                not isinstance(inventory, dict)
                or not isinstance(dirs, list)
                or not all(isinstance(d, str) for d in dirs)
                or len(set(dirs)) != len(dirs)
            ):
                raise BackupError("Malformed file inventory")
            if not set(ROOTS).issubset(dirs) or DATABASE not in inventory:
                raise BackupError("Backup is missing required application data")
            if set(names) != (set(inventory) | set(dirs) | {"manifest.json"}) or set(
                inventory
            ) & set(dirs):
                raise BackupError("Missing/unlisted/conflicting archive members")
            for name in [*dirs, *inventory]:
                safe_path(name)
                parent = PurePosixPath(name).parent
                while str(parent) != ".":
                    if str(parent) not in dirs:
                        raise BackupError(
                            "Missing directory or file/directory path conflict"
                        )
                    parent = parent.parent
                if (name in dirs) != names[name].is_dir():
                    raise BackupError("File/directory inventory conflict")
            # A standalone snapshot must never be accompanied by SQLite sidecars.
            if any(
                name in inventory
                for name in [
                    DATABASE + "-wal",
                    DATABASE + "-shm",
                    DATABASE + "-journal",
                ]
            ):
                raise BackupError("SQLite transient sidecars are not supported")
            ensure_space(stage, total)
            for name in sorted(dirs):
                (stage / name).mkdir(parents=True, exist_ok=True, mode=0o700)
            for name, entry in inventory.items():
                if cancelled():
                    raise BackupError("Backup cancelled")
                if (
                    not isinstance(entry, dict)
                    or set(entry) != {"size", "sha256"}
                    or type(entry["size"]) is not int
                    or entry["size"] < 0
                    or not isinstance(entry["sha256"], str)
                    or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])
                ):
                    raise BackupError("Malformed checksum inventory")
                if names[name].file_size != entry["size"]:
                    raise BackupError("File size does not match inventory")
                digest = hashlib.sha256()
                size = 0
                # Even validation-only uses private staging for SQLite checks.
                with source.open(names[name]) as content, (stage / name).open(
                    "xb"
                ) as output:
                    while chunk := content.read(CHUNK):
                        if cancelled():
                            raise BackupError("Backup cancelled")
                        size += len(chunk)
                        if size > entry["size"]:
                            raise BackupError("Decompressed file exceeds declared size")
                        digest.update(chunk)
                        output.write(chunk)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise BackupError(f"Checksum verification failed: {name}")
            inspect_database(stage / DATABASE, inventory, cancelled=cancelled)
        if not extract:
            temporary.cleanup()
            return manifest
        return Verified(temporary, stage, manifest)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        sqlite3.Error,
        zipfile.BadZipFile,
        RuntimeError,
        EOFError,
        struct.error,
    ) as exc:
        temporary.cleanup()
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Backup validation failed: {exc}") from exc
    except BaseException:
        temporary.cleanup()
        raise
