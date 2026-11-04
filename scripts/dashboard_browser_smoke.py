"""Dashboard acceptance on a disposable local database; build frontend first.
Run: .venv/bin/python scripts/dashboard_browser_smoke.py /usr/bin/chromium
"""

from datetime import date
from pathlib import Path
from uuid import uuid4
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="cultivatinator-dashboard-browser-") as temp:
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
                raise RuntimeError("Disposable application did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=(
                        sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium"
                    ),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1100},
                    timezone_id="America/New_York",
                )
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def post(path, data):
                    result = page.request.post(base + path, data=data)
                    assert result.status in [200, 201], result.text()
                    return result.json()

                def get(path):
                    result = page.request.get(base + path)
                    assert result.status == 200, result.text()
                    return result.json()

                page.goto(base)
                expect(
                    page.get_by_text(
                        "No items currently require attention.", exact=True
                    )
                ).to_be_visible()
                assert page.get_by_text("Growing Conditions", exact=True).count() == 0
                plate = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "culture",
                        "material": {"material_type": "agar_plate", "count": 1},
                        "line": {},
                        "inline_strain": {"name": "Dashboard Browser Oyster"},
                    },
                )["records"][0]
                post(
                    f"/api/containers/records/physical/{plate['id']}/state",
                    {
                        "request_key": str(uuid4()),
                        "action": "ready",
                        "action_date": "2026-01-01",
                    },
                )
                page.reload()
                expect(page.get_by_test_id("open_alerts")).to_have_text("1")
                region = page.get_by_role("region", name="Needs Attention")
                region.get_by_role(
                    "button", name="Needs Attention", exact=False
                ).click()
                card = page.get_by_role("link", name="Open Alerts", exact=False)
                card.focus()
                page.keyboard.press("Enter")
                expect(region).to_be_focused()
                assert (
                    region.get_by_role(
                        "button",
                        name=__import__("re").compile("Snooze|Dismiss|Undo|Restore"),
                    ).count()
                    == 0
                )
                assert (
                    region.get_by_role(
                        "link",
                        name=__import__("re").compile("snoozed|dismissed|hidden"),
                    ).count()
                    == 0
                )
                page.reload()
                expect(page.get_by_test_id("open_alerts")).to_have_text("1")
                page.get_by_role("link", name="View all attention items (1)").click()
                expect(
                    page.get_by_role("heading", name="Needs Attention")
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="P-01 · Dashboard Browser Oyster")
                ).to_be_visible()
                page.get_by_role("link", name="Back to Dashboard").click()
                expect(page.get_by_test_id("open_alerts")).to_have_text("1")
                page.get_by_role("link", name="Active Cultures", exact=False).click()
                expect(page.get_by_label("Show records")).to_have_value("active")
                expect(page.get_by_text("P-01 · Agar plate")).to_be_visible()
                page.goto(base)
                page.get_by_role("link", name="Laboratory · Ready", exact=False).click()
                expect(page.get_by_label("Show records")).to_have_value("ready")
                page.goto(base + "/activity")
                expect(page.get_by_role("heading", name="All Activity")).to_be_visible()
                expect(page.locator("time").first).to_have_attribute(
                    "datetime",
                    get("/api/dashboard/activity")["items"][0]["occurred_at"],
                )
                page.get_by_label("Record type").select_option("physical")
                expect(page).to_have_url(
                    __import__("re").compile("record_type=physical")
                )
                page.goto(base + "/settings")
                page.get_by_role(
                    "button", name="Attention Preferences", exact=False
                ).click()
                page.get_by_label("Pinning threshold (days)").fill("30")
                page.get_by_role("button", name="Save attention preferences").click()
                expect(page.get_by_text("Attention preferences saved.")).to_be_visible()
                assert get("/api/dashboard/preferences")["pinning"]["days"] == 30
                page.goto(base)
                page.screenshot(
                    path="/tmp/cultivatinator-dashboard-desktop.png", full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                page.reload()
                expect(
                    page.get_by_role("link", name="Open Alerts", exact=False)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
                page.screenshot(
                    path="/tmp/cultivatinator-dashboard-mobile.png", full_page=True
                )
                page.route(
                    "**/api/dashboard/summary?*",
                    lambda route: route.fulfill(
                        status=503, content_type="application/json", body="{}"
                    ),
                )
                page.reload()
                expect(page.get_by_role("alert")).to_be_visible()
                page.unroute("**/api/dashboard/summary?*")
                page.get_by_role("button", name="Retry connection").click()
                expect(page.get_by_test_id("open_alerts")).to_have_text("1")
                post(
                    f"/api/containers/records/physical/{plate['id']}/state",
                    {
                        "request_key": str(uuid4()),
                        "action": "failed",
                        "action_date": date.today().isoformat(),
                        "reason": "Explicit lifecycle resolution",
                    },
                )
                page.reload()
                expect(page.get_by_test_id("open_alerts")).to_have_text("0")
                expect(
                    page.get_by_text(
                        "No items currently require attention.", exact=True
                    )
                ).to_be_visible()
                page.get_by_role("button", name="Recent Activity", exact=False).click()
                expect(page.get_by_text("failed", exact=True)).to_be_visible()
                assert not errors, errors
                browser.close()
                print(
                    "Dashboard browser acceptance passed: condition visibility/resolution and no suppression controls, filters, activity, preferences, mobile/keyboard and error recovery."
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
