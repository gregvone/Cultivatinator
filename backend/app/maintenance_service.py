"""Root-owned host helper. No TCP listener; fixed targets; standard library only."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import UnixStreamServer, ThreadingMixIn
from uuid import uuid4
import argparse
import collections
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import socket
import stat
import struct
import threading
import time
from .backup_format import (
    BackupError,
    Limits,
    check_archive,
    ensure_space,
    RESTORE_MARKER,
    lease,
)
from .backup_store import atomic_json, identifier, NAME, file_identity
from .maintenance_protocol import MaintenanceError, signature, read_key
from .restore_workspace import Compose, restore, recover

log = logging.getLogger(__name__)
SESSION_SECONDS = 1800


class AdminStore:
    def __init__(self, root):
        self.root = root
        self.path = root / "admin.json"
        self.lock = threading.RLock()
        self.attempts = collections.defaultdict(collections.deque)
        self.secret = read_key(root / "session.key")

    def load(self):
        if not self.path.exists():
            return {"credential": None, "sessions": {}}
        return json.loads(self.path.read_text())

    def csrf(self, token):
        return signature(self.secret, ("csrf:" + token).encode())

    def authorize(self, token, csrf="", write=False):
        with self.lock:
            state = self.load()
            entry = state["sessions"].get(hashlib.sha256(token.encode()).hexdigest())
            if not entry or entry["expires"] <= time.time():
                raise MaintenanceError("Unlock Backup & Restore administration", 401)
            if write and not hmac.compare_digest(csrf, self.csrf(token)):
                raise MaintenanceError(
                    "Invalid administration confirmation token; unlock again", 403
                )
            return {
                "configured": True,
                "unlocked": True,
                "csrf": self.csrf(token),
                "expires_at": entry["expires"],
            }

    def throttle(self, client):
        now = time.time()
        for scope, limit in [(client[:100], 5), ("*", 20)]:
            attempts = self.attempts[scope]
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= limit:
                raise MaintenanceError(
                    "Too many administration attempts. Wait one minute.", 429
                )
        for scope in [client[:100], "*"]:
            self.attempts[scope].append(now)
        # Bound unauthenticated address bookkeeping.
        if len(self.attempts) > 1000:
            for key in list(self.attempts):
                if not self.attempts[key] or self.attempts[key][-1] < now - 60:
                    self.attempts.pop(key, None)

    @staticmethod
    def digest(passphrase, salt):
        return hashlib.scrypt(
            passphrase.encode(),
            salt=bytes.fromhex(salt),
            n=32768,
            r=8,
            p=1,
            dklen=32,
            maxmem=64 * 1024**2,
        ).hex()

    def login(self, data, setup=False):
        with self.lock:
            self.throttle(str(data.get("client", "unknown")))
            state = self.load()
            passphrase = data.get("passphrase", "")
            if not isinstance(passphrase, str) or not 12 <= len(passphrase) <= 1024:
                raise MaintenanceError(
                    "Use an administrator passphrase of 12 to 1024 characters", 400
                )
            if setup:
                if state["credential"]:
                    raise MaintenanceError("Administrator is already configured", 409)
                supplied = data.get("bootstrap", "")
                bootstrap = self.root / "bootstrap.sha256"
                if (
                    not isinstance(supplied, str)
                    or not bootstrap.exists()
                    or not hmac.compare_digest(
                        hashlib.sha256(supplied.encode()).hexdigest(),
                        bootstrap.read_text().strip(),
                    )
                ):
                    raise MaintenanceError("Invalid one-time setup code", 401)
                salt = secrets.token_hex(16)
                state["credential"] = {
                    "salt": salt,
                    "scrypt": self.digest(passphrase, salt),
                }
            else:
                credential = state["credential"]
                if not credential or not hmac.compare_digest(
                    self.digest(passphrase, credential["salt"]), credential["scrypt"]
                ):
                    raise MaintenanceError("Incorrect administrator passphrase", 401)
            now = time.time()
            state["sessions"] = {
                k: v for k, v in state["sessions"].items() if v["expires"] > now
            }
            if len(state["sessions"]) >= 16:
                oldest = min(
                    state["sessions"], key=lambda k: state["sessions"][k]["expires"]
                )
                state["sessions"].pop(oldest)
            token = secrets.token_urlsafe(48)
            state["sessions"][hashlib.sha256(token.encode()).hexdigest()] = {
                "expires": now + SESSION_SECONDS
            }
            atomic_json(self.path, state)
            if setup:
                (self.root / "bootstrap.sha256").unlink(missing_ok=True)
            return {"session": token, **self.authorize(token)}

    def logout(self, data):
        with self.lock:
            self.authorize(data.get("session", ""), data.get("csrf", ""), True)
            state = self.load()
            state["sessions"].pop(
                hashlib.sha256(data["session"].encode()).hexdigest(), None
            )
            atomic_json(self.path, state)
        return {"unlocked": False}


class MaintenanceService:
    def __init__(self, config, controller_factory=None):
        self.config = config
        self.root = Path(config["data_root"]).resolve(strict=True)
        self.state = Path(config["state_root"])
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.previews = self.state / "previews"
        self.operations = self.state / "operations"
        for directory in [self.previews, self.operations]:
            directory.mkdir(mode=0o700, exist_ok=True)
        self.admin = AdminStore(self.state)
        self.key = read_key(config["key_file"])
        self.lock = threading.RLock()
        self.controller_factory = controller_factory or self.controller
        self.worker = None

    def controller(self):
        controller = Compose(self.config["compose_file"], self.root)
        controller.maintenance_key = self.key.decode()
        return controller

    def latest(self):
        pointer = self.state / "latest.json"
        if not pointer.exists():
            return None
        code = identifier(json.loads(pointer.read_text())["id"])
        return json.loads((self.operations / (code + ".json")).read_text())

    def status(self, code=None):
        if code:
            path = self.operations / (identifier(code) + ".json")
            value = json.loads(path.read_text()) if path.exists() else None
        else:
            value = self.latest()
        return {
            "available": True,
            "configured": bool(self.admin.load()["credential"]),
            "active": bool(
                value and value["status"] not in {"complete", "rolled_back", "failed"}
            ),
            "operation": value,
        }

    def update(self, value, status, message=None, recovery_operation=None):
        value.update(status=status, updated_at=datetime.now(timezone.utc).isoformat())
        if message is not None:
            value["message"] = message
        if recovery_operation:
            value["recovery_operation"] = str(recovery_operation)
        atomic_json(self.operations / (value["id"] + ".json"), value)

    def safe_source(self, kind, code):
        """Walk app-writable names with pinned O_NOFOLLOW directory descriptors."""
        identifier(code)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors = [fd]
        try:
            for name in ["backups", ".control"]:
                fd = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                descriptors.append(fd)
            if kind == "stored":
                catalog_fd = os.open(
                    "catalog", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                descriptors.append(catalog_fd)
                receipt_fd = os.open(
                    code + ".json",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=catalog_fd,
                )
                with os.fdopen(receipt_fd, "rb") as content:
                    receipt_info = os.fstat(content.fileno())
                    if (
                        not stat.S_ISREG(receipt_info.st_mode)
                        or receipt_info.st_nlink != 1
                    ):
                        raise BackupError("Unsafe catalog metadata")
                    raw = content.read(65537)
                if len(raw) > 65536:
                    raise BackupError("Oversized catalog metadata")
                receipt = json.loads(raw)
                match = NAME.fullmatch(receipt.get("filename", ""))
                if (
                    not match
                    or match[3] != code.replace("-", "")
                    or receipt.get("id") != code
                    or receipt.get("pending")
                ):
                    raise BackupError("Invalid managed backup selection")
                # backups/ descriptor remains pinned, even if app renames .control.
                selected = os.open(
                    receipt["filename"],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptors[1],
                )
            elif kind == "upload":
                upload_fd = os.open(
                    "uploads", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                descriptors.append(upload_fd)
                selected = os.open(
                    code + ".zip",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=upload_fd,
                )
            else:
                raise BackupError("Unsupported restore source")
            info = os.fstat(selected)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size > Limits().archive_bytes
            ):
                os.close(selected)
                raise BackupError("Unsafe or oversized restore source")
            return os.fdopen(selected, "rb"), info
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def clean_previews(self):
        current = self.latest()
        for metadata in self.previews.glob("*.json"):
            try:
                if (
                    current
                    and self.status()["active"]
                    and current["preview_id"] == metadata.stem
                ):
                    continue
                value = json.loads(metadata.read_text())
                if value["expires"] < time.time():
                    metadata.with_suffix(".zip").unlink(missing_ok=True)
                    metadata.unlink()
            except (OSError, ValueError, KeyError):
                continue

    def prepare(self, data):
        with self.lock:
            if self.status()["active"]:
                raise MaintenanceError("A restore is already running", 409)
            self.clean_previews()
            if len(list(self.previews.glob("*.json"))) >= 2:
                raise MaintenanceError(
                    "Two restore previews are already staged; cancel one first", 409
                )
            code = str(uuid4())
            archive = self.previews / (code + ".zip")
            try:
                source, before = self.safe_source(data.get("source"), data.get("id"))
                with source, archive.open("xb") as output:
                    os.chmod(archive, 0o600)
                    ensure_space(self.previews, before.st_size)
                    shutil.copyfileobj(source, output, 1024 * 1024)
                    if file_identity(os.fstat(source.fileno())) != file_identity(
                        before
                    ):
                        raise BackupError("Restore source changed while staging")
                    output.flush()
                    os.fsync(output.fileno())
                manifest = check_archive(archive, extract=False)
                value = {
                    "id": code,
                    "source": data["source"],
                    "backup_id": data["id"] if data["source"] == "stored" else None,
                    "size_bytes": archive.stat().st_size,
                    "created_at": manifest["created_at"],
                    "application_version": manifest["application_version"],
                    "migration_revision": manifest["migration_revision"],
                    "compatibility": "verified",
                    "expires": time.time() + 900,
                }
                atomic_json(archive.with_suffix(".json"), value)
                return value
            except BaseException:
                archive.unlink(missing_ok=True)
                raise

    def begin(self, data):
        identifier(data.get("request_id"))
        code = identifier(data.get("preview_id"))
        if data.get("confirmation") != "REPLACE-PERSISTENT-DATA":
            raise MaintenanceError("Explicit replacement confirmation is required", 400)
        with self.lock:
            existing = self.operations / (data["request_id"] + ".json")
            if existing.exists():
                value = json.loads(existing.read_text())
                if value["preview_id"] != code:
                    raise MaintenanceError(
                        "Restore request key was reused for another preview", 409
                    )
                return value
            if self.status()["active"]:
                raise MaintenanceError("A restore is already running", 409)
            metadata = self.previews / (code + ".json")
            if not metadata.exists():
                raise MaintenanceError(
                    "Restore preview not found; verify the backup again", 404
                )
            preview = json.loads(metadata.read_text())
            if preview["expires"] < time.time():
                raise MaintenanceError("Restore preview expired; verify it again", 410)
            value = {
                "id": data["request_id"],
                "preview_id": code,
                "backup_id": preview["backup_id"],
                "status": "verifying",
                "message": "Verifying the selected backup before replacement",
            }
            self.update(value, "verifying")
            atomic_json(self.state / "latest.json", {"id": value["id"]})
            self.worker = threading.Thread(
                target=self.perform, args=(value,), daemon=True
            )
            self.worker.start()
            return value

    def perform(self, value):
        controller = None
        archive = self.previews / (value["preview_id"] + ".zip")
        try:
            controller = self.controller_factory()
            restore(
                archive,
                self.root,
                self.config["compose_file"],
                self.config.get("recovery_root"),
                "REPLACE-PERSISTENT-DATA",
                controller=controller,
                progress=lambda phase, operation=None: self.update(
                    value, phase, recovery_operation=operation
                ),
            )
            controller.unfreeze()
            self.update(
                value,
                "complete",
                "Restore complete. The application and database are healthy; safety recovery files are retained.",
            )
        except BaseException as exc:
            log.error("Restore operation %s failed: %s", value["id"], exc)
            recovery_path = value.get("recovery_operation")
            state = None
            if recovery_path and (Path(recovery_path) / "operation.json").exists():
                state = json.loads(
                    (Path(recovery_path) / "operation.json").read_text()
                ).get("state")
            outcome = (
                "rolled_back"
                if state in {"rolled_back", "unchanged"}
                else (
                    "recovery_required"
                    if state
                    in {"replacing", "replaced", "recovery_required", "completed"}
                    or (self.root / RESTORE_MARKER).exists()
                    else "failed"
                )
            )
            self.update(value, outcome, str(exc))
        finally:
            if controller:
                try:
                    controller.unfreeze()
                except Exception:
                    pass
            if value["status"] != "recovery_required":
                archive.unlink(missing_ok=True)
                archive.with_suffix(".json").unlink(missing_ok=True)

    def resume(self):
        value = self.latest()
        if not value or value["status"] in {"complete", "rolled_back", "failed"}:
            return
        try:
            path = value.get("recovery_operation")
            controller = self.controller_factory()
            if path:
                info = json.loads((Path(path) / "operation.json").read_text())
                if info["state"] in {"replacing", "replaced", "recovery_required"}:
                    self.update(
                        value,
                        "restoring_data",
                        "Recovering original data after helper interruption",
                    )
                    recover(
                        path,
                        self.root,
                        self.config["compose_file"],
                        "REPLACE-PERSISTENT-DATA",
                        controller=controller,
                    )
                    self.update(
                        value,
                        "rolled_back",
                        "Original data recovered after interruption; recovery files retained.",
                    )
                elif info["state"] == "completed":
                    controller.start()
                    controller.health()
                    self.update(
                        value,
                        "complete",
                        "Completed restore verified after helper restart.",
                    )
                else:
                    controller.start()
                    controller.health()
                    self.update(
                        value,
                        "rolled_back",
                        "Original installation restarted; cutover had not completed.",
                    )
            elif (self.root / RESTORE_MARKER).exists():
                raise BackupError(
                    "An interruption marker exists without a matching helper operation; use emergency host recovery"
                )
            else:
                controller.start()
                controller.health()
                self.update(
                    value,
                    "failed",
                    "Restore interrupted before data replacement. Original installation restarted.",
                )
            controller.unfreeze()
        except BaseException as exc:
            self.update(
                value,
                "recovery_required",
                f"Automatic recovery could not finish: {exc}. Preserve recovery files and use the documented host recovery procedure.",
            )

    def dispatch(self, operation, data):
        fields = {
            "status": {"id"},
            "setup": {"passphrase", "bootstrap", "client"},
            "unlock": {"passphrase", "bootstrap", "client"},
            "authorize": {"session", "csrf", "write"},
            "lock": {"session", "csrf"},
            "prepare_restore": {"session", "csrf", "source", "id"},
            "cancel_preview": {"session", "csrf", "id"},
            "restore": {"session", "csrf", "preview_id", "request_id", "confirmation"},
        }
        if operation not in fields or set(data) - fields[operation]:
            raise MaintenanceError(
                "Unsupported maintenance operation or parameters", 400
            )
        if operation == "status":
            return self.status(data.get("id"))
        if operation in {"setup", "unlock"}:
            return self.admin.login(data, setup=operation == "setup")
        if operation == "authorize":
            return self.admin.authorize(
                data.get("session", ""), data.get("csrf", ""), data.get("write", False)
            )
        if operation == "lock":
            return self.admin.logout(data)
        self.admin.authorize(data.get("session", ""), data.get("csrf", ""), True)
        if operation == "prepare_restore":
            return self.prepare(data)
        if operation == "cancel_preview":
            code = identifier(data.get("id"))
            with self.lock:
                current = self.latest()
                if (
                    current
                    and current["preview_id"] == code
                    and self.status()["active"]
                ):
                    raise MaintenanceError("Restore is using this preview", 409)
                (self.previews / (code + ".zip")).unlink(missing_ok=True)
                (self.previews / (code + ".json")).unlink(missing_ok=True)
            return {"cancelled": True}
        if operation == "restore":
            return self.begin(data)
        raise MaintenanceError("Unsupported maintenance operation", 400)


class Server(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, path, service, allowed_uid=10001):
        self.service, self.allowed_uid = service, allowed_uid
        self.nonces = {}
        self.nonce_lock = threading.Lock()
        self.last_cleanup = 0
        self.requests = threading.BoundedSemaphore(8)
        super().__init__(str(path), Handler)
        os.chmod(path, 0o660)

    def process_request(self, request, client_address):
        if not self.requests.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.requests.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.requests.release()

    def service_actions(self):
        if time.monotonic() - self.last_cleanup > 30 and self.service.lock.acquire(
            blocking=False
        ):
            try:
                self.service.clean_previews()
                self.last_cleanup = time.monotonic()
            finally:
                self.service.lock.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log tokens, passphrases or request bodies.

    def do_POST(self):
        try:
            _, uid, _ = struct.unpack(
                "3i",
                self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12),
            )
            if uid not in {0, self.server.allowed_uid} or self.path != "/v1/control":
                raise MaintenanceError("Unauthorized maintenance channel", 403)
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16384:
                raise MaintenanceError("Invalid maintenance request size", 413)
            self.connection.settimeout(10)
            raw = self.rfile.read(length)
            if not hmac.compare_digest(
                signature(self.server.service.key, raw),
                self.headers.get("X-Cultivatinator-Signature", ""),
            ):
                raise MaintenanceError("Unauthorized maintenance channel", 403)
            payload = json.loads(raw)
            if (
                type(payload.get("time")) is not int
                or abs(time.time() - payload["time"]) > 60
            ):
                raise MaintenanceError("Expired maintenance request", 403)
            nonce = payload.get("nonce", "")
            if not isinstance(nonce, str) or len(nonce) != 48:
                raise MaintenanceError("Invalid maintenance nonce", 403)
            with self.server.nonce_lock:
                self.server.nonces = {
                    k: v for k, v in self.server.nonces.items() if v > time.time() - 120
                }
                if nonce in self.server.nonces or len(self.server.nonces) >= 10000:
                    raise MaintenanceError(
                        "Replayed or excessive maintenance request", 403
                    )
                self.server.nonces[nonce] = time.time()
            if not isinstance(payload.get("data"), dict):
                raise MaintenanceError("Invalid maintenance operation data", 400)
            result = self.server.service.dispatch(
                payload.get("operation"), payload["data"]
            )
            self.respond(200, result)
        except MaintenanceError as exc:
            self.respond(exc.status, {"detail": str(exc)})
        except (BackupError, OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Maintenance validation failed: %s", exc)
            self.respond(
                400,
                {
                    "detail": (
                        str(exc)
                        if isinstance(exc, BackupError)
                        else "Maintenance validation failed; inspect service logs and selected backup"
                    )
                },
            )
        except Exception:
            log.exception("Maintenance operation failed")
            self.respond(
                500,
                {
                    "detail": "Maintenance operation failed; inspect the host service logs"
                },
            )

    def respond(self, status, result):
        content = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Maintenance service must run as host root")
    config = json.loads(args.config.read_text())
    # /run is recreated on host boot. Keep its directory inode on ordinary
    # service restarts so the app's read-only directory bind stays connected.
    runtime = Path(config["socket_file"]).parent
    runtime.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(runtime, 0, 10001)
    os.chmod(runtime, 0o750)
    key_file = Path(config["key_file"])
    if not key_file.exists():
        private_key = read_key(Path(config["state_root"]) / "channel.key")
        fd = os.open(
            key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640
        )
        with os.fdopen(fd, "wb") as output:
            output.write(private_key)
            output.flush()
            os.fsync(output.fileno())
        os.chown(key_file, 0, 10001)
    service = MaintenanceService(config)
    socket_path = Path(config["socket_file"])
    with lease(service.state, ".helper.lock"):
        if socket_path.exists():
            if not socket_path.is_socket():
                raise BackupError("Maintenance socket path is not a socket")
            socket_path.unlink()
        with Server(socket_path, service) as server:
            os.chown(socket_path, 0, 10001)
            service.worker = threading.Thread(target=service.resume, daemon=True)
            service.worker.start()
            server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
