"""Optional Playwright/Chromium acceptance using an isolated temporary workspace."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="cultivatinator-experiments-") as tmp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {
            **os.environ,
            "CULTIVATINATOR_DATA_DIR": str(Path(tmp) / "data"),
            "CULTIVATINATOR_FRONTEND_DIR": str(ROOT / "frontend/dist"),
        }
        log = open(Path(tmp) / "app.log", "w+")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "backend",
            env=environment,
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    if urlopen(base + "/api/health", timeout=1).status == 200:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                log.seek(0)
                raise RuntimeError(log.read())
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=(
                        sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium"
                    ),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    timezone_id="America/New_York",
                )
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on(
                    "response",
                    lambda r: (
                        print(r.status, r.url, r.text()[:1000], flush=True)
                        if r.status >= 400
                        else None
                    ),
                )
                page.goto(base + "/experiments")
                expect(
                    page.get_by_text("No experiments yet.", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="New experiment", exact=True).click()
                page.get_by_label("Experiment title", exact=True).fill(
                    "Browser substrate trial"
                )
                page.get_by_label("Experiment category", exact=False).select_option(
                    "substrate"
                )
                page.get_by_label("Primary variable", exact=True).fill(
                    "Substrate formulation"
                )
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_label("Group 1 treatment", exact=True).fill(
                    "Recipe revision A"
                )
                page.get_by_label("Group 2 treatment", exact=True).fill(
                    "Recipe revision B"
                )
                page.get_by_role("button", name="Add group", exact=True).click()
                page.get_by_label("Group 3 name", exact=True).fill("Third group")
                page.get_by_label("Group 3 treatment", exact=True).fill(
                    "Recipe revision C"
                )
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_text(
                    "Advanced scientific settings (optional)", exact=True
                ).click()
                page.get_by_label("Allocation schedule", exact=True).fill(
                    "Allocate units before treatment; concrete enrollment deferred"
                )
                page.get_by_label("Minimum readings", exact=True).fill("3")
                page.get_by_role("button", name="Save draft", exact=True).click()
                expect(
                    page.get_by_role(
                        "heading", name="Browser substrate trial", exact=True, level=1
                    )
                ).to_be_visible()
                page.get_by_label("Action reason", exact=True).fill(
                    "Original plan ready"
                )
                page.get_by_role("button", name="Commit plan", exact=True).click()
                expect(
                    page.get_by_role("button", name="Start experiment", exact=True)
                ).to_be_visible()
                page.get_by_label("Actual treatment start (date)", exact=True).fill(
                    "2025-01-01"
                )
                page.get_by_label("Action reason", exact=True).fill(
                    "Historical treatment comparison"
                )
                page.get_by_role("button", name="Start experiment", exact=True).click()
                expect(page.get_by_text("retrospective", exact=True)).to_be_visible()
                page.get_by_role("button", name="Edit plan", exact=True).click()
                page.get_by_label("Experiment title", exact=True).fill(
                    "Browser amended plan"
                )
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_label("Revision reason", exact=True).fill(
                    "Clarify question after start"
                )
                page.get_by_role("button", name="Save revision", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Browser amended plan", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_text("Post-start amendment.", exact=False)
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Plan and audit history", exact=True
                ).click()
                expect(
                    page.get_by_text("Plan 1 · Draft · Created draft", exact=True)
                ).to_be_visible()
                page.get_by_text("Plan 1 · Draft · Created draft", exact=True).click()
                expect(
                    page.get_by_text("Original plans and revisions", exact=True)
                ).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                page.emulate_media(reduced_motion="reduce")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), "Mobile overflow"
                page.get_by_label("Action reason", exact=True).fill(
                    "Finished recording comparison"
                )
                page.get_by_role(
                    "button", name="Complete experiment", exact=True
                ).click()
                expect(
                    page.get_by_role("button", name="Edit plan", exact=True)
                ).to_have_count(0)
                page.get_by_label("Action reason", exact=True).fill(
                    "Retain historical plan"
                )
                page.get_by_role(
                    "button", name="Archive experiment", exact=True
                ).click()
                expect(
                    page.get_by_role("button", name="Restore experiment", exact=True)
                ).to_be_visible()
                page.get_by_label("Action reason", exact=True).fill(
                    "Review archived plan"
                )
                page.get_by_role(
                    "button", name="Restore experiment", exact=True
                ).click()
                expect(
                    page.get_by_role("button", name="Archive experiment", exact=True)
                ).to_be_visible()
                assert not errors, errors
                browser.close()
                print(
                    "Experiment browser acceptance passed: guided setup, groups/advanced settings, commitment, retrospective start, amendment/history, completion/archive/restore, mobile and reduced motion."
                )
        finally:
            process.terminate()
            process.wait(timeout=15)
            log.close()


if __name__ == "__main__":
    main()
