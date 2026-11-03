"""Settings backup download/error and responsive acceptance, using disposable data."""

from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.backup_format import check_archive

with tempfile.TemporaryDirectory(prefix="cultivatinator-backup-browser-") as temp:
    directory = Path(temp)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (directory / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "backend",
            env={**os.environ, "CULTIVATINATOR_DATA_DIR": str(directory / "data")},
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + "/api/health", timeout=1) as r:
                        if r.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=(
                        sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium"
                    ),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    accept_downloads=True, viewport={"width": 1440, "height": 1100}
                )
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/settings")
                page.route(
                    "**/api/backups/prepare",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"Backup was not created: simulated disk error"}',
                    ),
                    times=1,
                )
                page.get_by_role(
                    "button", name="Download Complete Backup", exact=True
                ).click()
                expect(page.get_by_role("alert")).to_contain_text(
                    "simulated disk error"
                )
                with page.expect_download() as waiting:
                    page.get_by_role(
                        "button", name="Download Complete Backup", exact=True
                    ).click()
                download = waiting.value
                archive = directory / "download.zip"
                download.save_as(archive)
                assert download.failure() is None
                manifest = check_archive(archive, extract=False)
                assert manifest["format_version"] == 1
                expect(page.get_by_role("status")).to_contain_text(
                    "does not confirm that the file was saved externally"
                )
                page.get_by_role(
                    "button", name="Restore safely on Debian", exact=True
                ).focus()
                page.keyboard.press("Enter")
                expect(
                    page.get_by_text(
                        "python3 /storage/tv/cultivatinator/scripts/workspace_backup.py verify /path/to/backup.zip",
                        exact=True,
                    )
                ).to_be_visible()
                for width in [390, 768]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), "Backup settings overflow"
                    assert (
                        page.get_by_role(
                            "button", name="Download Complete Backup", exact=True
                        ).bounding_box()["height"]
                        >= 44
                    )
                page.screenshot(
                    path="/tmp/cultivatinator-backup-settings.png", full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "Backup browser smoke passed: native ZIP download and validation, clear server errors/retry, external-copy wording, keyboard restore instructions, phone/tablet layout and touch targets; no page errors"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
