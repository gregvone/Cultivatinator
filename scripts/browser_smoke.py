"""Optional end-to-end check: build frontend first; install Playwright separately.

Runs only against a disposable local database, never an existing deployment.
Usage: python scripts/browser_smoke.py [path-to-chromium]
"""

from io import BytesIO
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import os
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="cultivatinator-browser-") as temp:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with open(Path(temp) / "server.log", "w+") as log:
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
            env={**os.environ, "CULTIVATINATOR_DATA_DIR": temp},
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(
                        base + "/api/health", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Application failed readiness")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=(
                        sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium"
                    ),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/culture-library")
                expect(
                    page.get_by_text("Your strain catalog starts here.")
                ).to_be_visible()
                page.get_by_role("link", name="Add Strain", exact=True).click()
                page.get_by_label("Strain name *", exact=True).fill(
                    "Browser verification strain"
                )
                page.get_by_role("button", name="Create strain").click()
                expect(
                    page.get_by_role("heading", name="Browser verification strain")
                ).to_be_visible()
                # Create actual image bytes instead of trusting a fixture's extension.
                from PIL import Image

                buffer = BytesIO()
                Image.new("RGB", (900, 600), "#558899").save(buffer, format="PNG")
                png = buffer.getvalue()
                page.get_by_label("Attach photographs").set_input_files(
                    [
                        {"name": "one.png", "mimeType": "image/png", "buffer": png},
                        {"name": "two.png", "mimeType": "image/png", "buffer": png},
                    ]
                )
                expect(page.get_by_text("2 photograph(s) attached")).to_be_visible()
                page.get_by_role("button", name="Use as cover").click()
                expect(
                    page.get_by_text("Cover photograph updated", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Open photograph 1").click()
                expect(page.get_by_role("dialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.get_by_role("dialog")).not_to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Remove", exact=True).last.click()
                expect(
                    page.get_by_text("Photograph removed", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("button", name="Open photograph 1")
                ).to_be_visible()
                expect(page.locator(".photo-grid figure")).to_have_count(1)
                page.goto(base + "/inventory/receive-culture?strain=STR-0001")
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_label("Supplier / source").fill("Browser supplier")
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_label("Register physical containers now").check()
                page.get_by_label("Number of containers (1–100) *", exact=True).fill(
                    "3"
                )
                page.get_by_label("Starting Quantity per container (optional)").fill(
                    "10"
                )
                page.get_by_role("button", name="Continue", exact=True).click()
                expect(page.get_by_text("3 × Liquid culture syringe")).to_be_visible()
                page.get_by_role("button", name="Confirm registration").click()
                expect(
                    page.get_by_role("heading", name="Individual physical containers")
                ).to_be_visible()
                expect(page.locator(".related-panel .record-list li")).to_have_count(3)
                page.locator(
                    'a[href="/culture-library/physical/LC-0001"]'
                ).first.click()
                expect(
                    page.get_by_text("Starting Quantity", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Edit information").click()
                page.get_by_label("Storage location").fill("Browser shelf")
                page.get_by_role("button", name="Save changes").click()
                expect(page.get_by_text("Browser shelf", exact=True)).to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Archive record", exact=True).click()
                expect(
                    page.get_by_role("button", name="Restore record")
                ).to_be_visible()
                assert (
                    page.request.get(base + "/api/dashboard/summary").json()["counts"][
                        "active_cultures"
                    ]
                    == 2
                )
                page.get_by_role("button", name="Restore record").click()
                expect(
                    page.get_by_role("button", name="Archive record")
                ).to_be_visible()
                page.goto(base + "/")
                expect(page.get_by_test_id("active_cultures")).to_have_text("3")
                page.goto(base + "/culture-library/receive-spores")
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_role("button", name="Continue", exact=True).click()
                page.get_by_role("button", name="Confirm registration").click()
                expect(
                    page.get_by_text(
                        "Spore source registered. No culture line was created."
                    )
                ).to_be_visible()
                page.goto(base + "/culture-library")
                expect(page.locator(".strain-card")).to_have_count(1)
                page.screenshot(path="/tmp/cultivatinator-desktop.png", full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                expect(page.locator(".strain-card")).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile horizontal overflow"
                page.screenshot(path="/tmp/cultivatinator-mobile.png", full_page=True)
                page.get_by_role("button", name="Open navigation").click()
                page.get_by_role("link", name="Dashboard", exact=True).click()
                expect(page.get_by_test_id("active_cultures")).to_have_text("3")
                assert not errors, errors
                browser.close()
            print(
                "PASS: browser strain creation, multiple photo uploads, cover, viewer, guided 3-container registration, physical edit, spore-only registration, dashboard, desktop/mobile navigation"
            )
        finally:
            process.terminate()
            process.wait(timeout=10)
