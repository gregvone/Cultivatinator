#!/usr/bin/env python3
"""One-time, reviewed Debian host installation. Normal operations use Settings."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CODE = Path("/opt/cultivatinator-maintenance")
ETC = Path("/etc/cultivatinator-maintenance")
STATE = Path("/var/lib/cultivatinator-maintenance")
RUNTIME = Path("/run/cultivatinator-maintenance")
sys.path.insert(0, str(ROOT / "backend"))
from app.backup_policy import BackupPolicy

UNIT = Path("/etc/systemd/system/cultivatinator-maintenance.service")
MODULES = [
    "__init__.py",
    "version.py",
    "backup_format.py",
    "backup_policy.py",
    "backup_schema.json",
    "backup_store.py",
    "backup_schedule.py",
    "restore_workspace.py",
    "maintenance_protocol.py",
    "maintenance_service.py",
]


def private_file(path, content, mode=0o600, group=0):
    temporary = path.with_name("." + path.name + "-" + secrets.token_hex(8))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "w") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.chown(temporary, 0, group)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def secret(path):
    if not path.exists():
        private_file(path, secrets.token_hex(32))
    if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise RuntimeError("Unsafe private maintenance state permissions")


def bootstrap(reset=False):
    path = STATE / "bootstrap.sha256"
    if reset:
        (STATE / "admin.json").unlink(missing_ok=True)
    if not (STATE / "admin.json").exists() and (reset or not path.exists()):
        code = secrets.token_urlsafe(24)
        private_file(path, hashlib.sha256(code.encode()).hexdigest())
        return code
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "reset-admin"])
    parser.add_argument(
        "--data-root", type=Path, default=Path("/storage/tv/cultivatinator")
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path("/storage/tv/cultivatinator/compose.yaml"),
    )
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this one-time installer with sudo on the Debian Docker host")
    if args.action == "reset-admin":
        if args.confirm != "RESET-BACKUP-ADMIN":
            parser.error(
                "Reset requires --confirm RESET-BACKUP-ADMIN; it revokes all backup-admin sessions"
            )
        subprocess.run(
            ["systemctl", "stop", "cultivatinator-maintenance.service"], check=True
        )
        code = bootstrap(reset=True)
        subprocess.run(
            ["systemctl", "start", "cultivatinator-maintenance.service"], check=True
        )
        print("Administrator reset. One-time browser setup code: " + code)
        return
    root = args.data_root.resolve(strict=True)
    compose = args.compose_file.resolve(strict=True)
    if root == Path("/") or not root.is_dir():
        parser.error("Use the configured Cultivatinator persistent data root")
    for path in [CODE, ETC, STATE, RUNTIME]:
        if path.is_symlink():
            parser.error("Maintenance paths must not be symlinks")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(path, 0, 0)
        os.chmod(path, 0o700)
    if (STATE / "latest.json").exists():
        value = json.loads((STATE / "latest.json").read_text())
        status = json.loads(
            (STATE / "operations" / (value["id"] + ".json")).read_text()
        )["status"]
        if status not in {"complete", "rolled_back", "failed"}:
            parser.error(
                "Finish/recover the current restore before updating the helper"
            )
    # Only the local daemon and the operator-selected trusted Compose file are
    # read during installation. The running helper uses a root-owned snapshot.
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
    }
    resolved = json.loads(
        subprocess.check_output(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "compose",
                "--project-directory",
                str(compose.parent),
                "-f",
                str(compose),
                "config",
                "--format",
                "json",
            ],
            env=environment,
            text=True,
        )
    )
    definition = resolved.get("services", {}).get("app", {})
    binds = [v for v in definition.get("volumes", []) if v.get("target") == "/data"]
    if (
        len(binds) != 1
        or binds[0].get("type") != "bind"
        or Path(binds[0]["source"]).resolve() != root
    ):
        parser.error("Compose app /data must bind the configured data root")
    configured_environment = definition.get("environment", {})
    policy = BackupPolicy(
        configured_environment.get("CULTIVATINATOR_BACKUP_AUTH_MODE") or "password",
        configured_environment.get("CULTIVATINATOR_TRUSTED_NETWORKS") or "",
    )
    subprocess.run(
        ["systemctl", "stop", "cultivatinator-maintenance.service"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    private_file(ETC / "compose.json", json.dumps(resolved, indent=2))
    backend = CODE / "backend"
    app = backend / "app"
    app.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in MODULES:
        private_file(app / name, (ROOT / "backend/app" / name).read_text())
    scripts = CODE / "scripts"
    scripts.mkdir(mode=0o700, exist_ok=True)
    private_file(
        scripts / "workspace_backup.py",
        (ROOT / "scripts/workspace_backup.py").read_text(),
    )
    versions = backend / "migrations/versions"
    versions.mkdir(mode=0o700, parents=True, exist_ok=True)
    for old in versions.glob("*.py"):
        old.unlink()
    for source in (ROOT / "backend/migrations/versions").glob("*.py"):
        private_file(versions / source.name, source.read_text())
    private_file(
        CODE / "run.py",
        "from pathlib import Path\nimport sys\nsys.path.insert(0, str(Path(__file__).resolve().parent / 'backend'))\nfrom app.maintenance_service import main\nmain()\n",
    )
    for name in ["channel.key", "session.key"]:
        secret(STATE / name)
    # Stable directory inode: app has a read-only bind of this directory.
    os.chown(RUNTIME, 0, 10001)
    os.chmod(RUNTIME, 0o750)
    private_file(
        RUNTIME / "channel.key", (STATE / "channel.key").read_text(), 0o640, 10001
    )
    backups = root / "backups"
    if backups.is_symlink():
        parser.error("backups/ must not be a symlink")
    if not backups.exists():
        backups.mkdir(mode=0o700)
        os.chown(backups, 10001, 10001)
    config = {
        "backup_auth_mode": policy.mode,
        "trusted_networks": ",".join(policy.cidrs),
        "data_root": str(root),
        "compose_file": str(ETC / "compose.json"),
        "state_root": str(STATE),
        "recovery_root": str(root.parent / (root.name + "-recovery")),
        "socket_file": str(RUNTIME / "control.sock"),
        "key_file": str(RUNTIME / "channel.key"),
    }
    private_file(ETC / "config.json", json.dumps(config, indent=2))
    unit = f"""[Unit]
Description=Cultivatinator restricted backup maintenance helper
Requires=docker.service
After=docker.service

[Service]
Type=simple
User=root
Group=10001
UMask=0027
WorkingDirectory={CODE}
ExecStart=/usr/bin/python3 -I {CODE}/run.py --config {ETC}/config.json
Restart=on-failure
RestartSec=3
TimeoutStopSec=120
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths={root.parent} {STATE} {RUNTIME}
RuntimeDirectory=cultivatinator-maintenance
RuntimeDirectoryMode=0750
RuntimeDirectoryPreserve=yes
CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER CAP_SYS_PTRACE

[Install]
WantedBy=multi-user.target
"""
    private_file(UNIT, unit, 0o644)
    code = bootstrap() if policy.mode == "password" else None
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "enable", "--now", "cultivatinator-maintenance.service"],
        check=True,
    )
    print(
        "Helper installed. Recreate the app with the reviewed Compose file, then open Settings → Backup & Restore."
    )
    if policy.mode == "trusted_lan":
        print(
            "Trusted LAN mode: clients in "
            + ", ".join(policy.cidrs)
            + " can administer backups and restores without a password. Existing password credentials are retained."
        )
    elif code:
        print("One-time browser setup code (store privately until used): " + code)
    elif not (STATE / "admin.json").exists():
        print(
            "An unused setup code already exists. If lost, use the documented reset-admin command."
        )
    else:
        print("Existing administrator credentials and backup history retained.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("Setup failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
