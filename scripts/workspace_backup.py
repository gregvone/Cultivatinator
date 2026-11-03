#!/usr/bin/env python3
"""Debian host verifier/restore CLI. Python standard library; no pip install needed."""
from pathlib import Path
import argparse
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.backup_format import BackupError, check_archive
from app.restore_workspace import restore, recover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    verify = subs.add_parser(
        "verify",
        help="Verify archive bytes, compatibility, SQLite integrity, foreign keys and photographs",
    )
    verify.add_argument("archive", type=Path)
    for name in ["restore", "recover"]:
        command = subs.add_parser(name)
        command.add_argument("archive" if name == "restore" else "operation", type=Path)
        command.add_argument(
            "--data-root", type=Path, default=Path("/storage/tv/cultivatinator")
        )
        command.add_argument(
            "--compose-file",
            type=Path,
            default=Path("/storage/tv/cultivatinator/compose.yaml"),
        )
        command.add_argument("--confirm", choices=["REPLACE-PERSISTENT-DATA"])
        if name == "restore":
            command.add_argument("--recovery-dir", type=Path)
    args = parser.parse_args()

    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"Interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupt)
    try:
        if args.command == "verify":
            manifest = check_archive(args.archive, extract=False)
            print(
                f"VALID: format {manifest['format_version']}, application {manifest['application_version']}, migration {manifest['migration_revision']}, {len(manifest['files'])} checksummed files; SQLite integrity, foreign keys and photo references verified"
            )
        elif args.command == "restore":
            result = restore(
                args.archive,
                args.data_root,
                args.compose_file,
                args.recovery_dir,
                args.confirm,
            )
            print(
                f"Restore healthy. Retain independent pre-restore.zip and original directories at: {result}"
            )
        else:
            result = recover(
                args.operation, args.data_root, args.compose_file, args.confirm
            )
            print(f"Original data recovered; retained recovery files: {result}")
    except (BackupError, OSError, ValueError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
