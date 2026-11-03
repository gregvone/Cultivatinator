"""Authenticated, bounded Unix-socket transport; standard library only."""

from pathlib import Path
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import struct
import time


class MaintenanceError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def signature(key, payload):
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def read_key(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as file:
        value = file.read(129)
    if len(value) != 64 or not all(c in b"0123456789abcdef" for c in value):
        raise MaintenanceError("Invalid maintenance channel key")
    return value


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=1800, expected_uid=0):
        super().__init__("localhost", timeout=timeout)
        self.path, self.expected_uid = str(path), expected_uid

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)
        _, uid, _ = struct.unpack(
            "3i", self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        if uid != self.expected_uid:
            self.sock.close()
            raise MaintenanceError("Maintenance socket has an unexpected owner")


class HelperClient:
    def __init__(self, socket_path, key_path, expected_uid=0):
        self.socket_path, self.key_path = Path(socket_path), Path(key_path)
        self.expected_uid = expected_uid

    def call(self, operation, data=None):
        connection = None
        try:
            key = read_key(self.key_path)
            payload = json.dumps(
                {
                    "operation": operation,
                    "data": data or {},
                    "time": int(time.time()),
                    "nonce": secrets.token_hex(24),
                },
                separators=(",", ":"),
            ).encode()
            connection = UnixConnection(
                self.socket_path, expected_uid=self.expected_uid
            )
            connection.request(
                "POST",
                "/v1/control",
                payload,
                {
                    "Content-Type": "application/json",
                    "X-Cultivatinator-Signature": signature(key, payload),
                },
            )
            response = connection.getresponse()
            raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise MaintenanceError("Maintenance response exceeds limit")
            value = json.loads(raw)
            if response.status != 200:
                raise MaintenanceError(
                    value.get("detail", "Maintenance operation failed"), response.status
                )
            return value
        except MaintenanceError:
            raise
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise MaintenanceError(
                "Maintenance helper unavailable. Complete the one-time Debian helper setup or inspect its service status."
            ) from exc
        finally:
            if connection:
                connection.close()
