"""Backup Settings acceptance, including real restricted-helper browser restores.
Run: .venv/bin/python scripts/backup_browser_smoke.py /usr/bin/chromium
Requires local Docker and a built cultivatinator:milestone-2d2 image. All data is
 disposable; the original browser entry point now includes the full restore flow.
"""

from pathlib import Path
import runpy

runpy.run_path(
    str(Path(__file__).with_name("backup_browser_restore_smoke.py")),
    run_name="__main__",
)
