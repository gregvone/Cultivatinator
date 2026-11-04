"""Milestone 2G acceptance against a disposable local workspace, never Debian."""

from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="cultivatinator-environment-") as temp:
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
                    if (
                        urllib.request.urlopen(base + "/api/health", timeout=1).status
                        == 200
                    ):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Disposable app failed to start")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/usr/bin/chromium",
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    timezone_id="America/New_York",
                )
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))

                def post(path, **data):
                    response = page.request.post(
                        base + "/api/environment/" + path,
                        data={"request_key": str(uuid4()), **data},
                    )
                    assert response.status == 200, response.text()
                    return response.json()

                page.goto(base + "/environment")
                expect(page.get_by_text("No tents yet.", exact=False)).to_be_visible()
                page.get_by_label("Tent name", exact=True).fill("Boom Room 2")
                page.get_by_label("Tent name", exact=True).locator(
                    "xpath=ancestor::form"
                ).get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Boom Room 2", exact=True)
                ).to_be_visible()
                tent = page.request.get(base + "/api/environment/tents").json()[0]
                profile = post(
                    "profiles",
                    name="Mixed Fruiting",
                    targets={
                        "temperature_f_min": 60,
                        "temperature_f_max": 80,
                        "humidity_min": 80,
                        "humidity_max": 95,
                        "co2_max": 1200,
                    },
                )
                post(
                    f"tents/{tent['id']}/profile",
                    profile_id=profile["id"],
                    expected_revision=tent["revision"],
                )
                page.reload()
                page.get_by_label("Temperature (°F)", exact=True).fill("70")
                page.get_by_label("Relative humidity (% RH)", exact=True).fill("40")
                page.get_by_label("Humidifier controller level", exact=False).fill("3")
                page.get_by_label("Reading notes", exact=True).fill(
                    "Browser observation"
                )
                page.get_by_label("Observed at (local time)", exact=True).locator(
                    "xpath=ancestor::form"
                ).get_by_role("button", name="Save", exact=True).click()
                expect(page.get_by_label("Environmental warnings")).to_contain_text(
                    "Relative humidity: low"
                )
                expect(
                    page.get_by_role(
                        "img",
                        name="Relative humidity recorded observations; accessible values in table below",
                    )
                ).to_be_visible()
                page.get_by_text("Reading #1", exact=True).click()
                expect(
                    page.get_by_text("Browser observation", exact=True)
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Correct reading #1", exact=True
                ).click()
                correction = page.get_by_role("region", name="Correct reading")
                correction.get_by_label("Relative humidity (% RH)", exact=True).fill(
                    "45"
                )
                correction.get_by_label("Correction reason", exact=True).fill(
                    "Correct transcription"
                )
                correction.get_by_role("button", name="Save", exact=True).click()
                expect(page.get_by_text("Superseded by #2", exact=True)).to_be_visible()
                page.goto(base + "/")
                expect(
                    page.get_by_role("link", name="Boom Room 2", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="Boom Room 2", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Boom Room 2", exact=True)
                ).to_be_visible()
                # A newer applicable observation resolves only the recorded humidity issue.
                post(
                    f"tents/{tent['id']}/readings",
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    temperature_f=70,
                    humidity=90,
                )
                page.reload()
                expect(
                    page.get_by_text("No open warnings.", exact=False)
                ).to_be_visible()
                page.get_by_text("Tent occupancy", exact=True).click()
                expect(
                    page.get_by_text("No tent assignments recorded.", exact=True)
                ).to_be_visible()
                acquisition = page.request.post(
                    base + "/api/provenance/acquisitions",
                    data={
                        "entry_type": "spawn_jar",
                        "line": {"name": "Browser Oyster"},
                    },
                )
                assert acquisition.status == 201, acquisition.text()
                grow = page.request.post(
                    base + "/api/provenance/grows",
                    data={
                        "source_ids": [acquisition.json()["records"][0]["id"]],
                        "allocation_mode": "shared",
                        "containers": [{}],
                    },
                )
                assert grow.status == 201, grow.text()
                fruiting_id = grow.json()["containers"][0]["id"]
                page.reload()
                page.get_by_text("Tent occupancy", exact=True).click()
                page.get_by_label("Fruiting container", exact=True).select_option(
                    fruiting_id
                )
                page.get_by_label("Entered tent (local time)", exact=True).fill(
                    page.evaluate(
                        "() => {const d=new Date(Date.now()-300000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}"
                    )
                )
                page.get_by_label("Fruiting container", exact=True).locator(
                    "xpath=ancestor::form"
                ).get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_text("1 containers currently assigned", exact=False)
                ).to_be_visible()
                page.get_by_text("Tent occupancy", exact=True).click()
                page.get_by_role("link", name=fruiting_id, exact=True).last.click()
                page.get_by_role(
                    "button", name="Tent occupancy & recorded conditions", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "Measurements taken during explicit occupancy periods",
                        exact=False,
                    )
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="Boom Room 2", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="Boom Room 2", exact=True).click()

                # Native dropdown options have explicit dark-theme foreground/background.
                style = page.get_by_label("Fruiting tent", exact=True).evaluate(
                    "(e)=>({color:getComputedStyle(e.options[0]).color,background:getComputedStyle(e.options[0]).backgroundColor})"
                )
                assert style["color"] != style["background"]
                page.emulate_media(reduced_motion="reduce")
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_label("Fruiting tent", exact=True).focus()
                page.keyboard.press("ArrowDown")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), "Mobile overflow"
                page.get_by_label("History time range", exact=True).select_option(
                    "custom"
                )
                page.get_by_label("Range start (local)", exact=True).fill(
                    "2025-01-01T00:00"
                )
                page.get_by_label("Range end (local)", exact=True).fill(
                    "2025-01-02T00:00"
                )
                page.get_by_role("button", name="Apply range", exact=True).click()
                expect(
                    page.get_by_text("No observations in this range.", exact=True)
                ).to_be_visible()
                assert not errors, errors
                browser.close()
                print(
                    "Environment browser smoke passed: empty state, create tent, manual reading, saved targets, persistent warning/dashboard link, correction, resolution, charts/table, range, occupancy empty state, dropdowns, keyboard, reduced motion and mobile."
                )
        finally:
            process.terminate()
            process.wait(timeout=15)
