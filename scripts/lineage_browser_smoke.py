"""Optional 2B browser acceptance check. Uses a disposable database; build UI first.
Run: .venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
Requires optional Playwright tooling in the invoking virtualenv.
"""

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
with tempfile.TemporaryDirectory(prefix="cultivatinator-lineage-browser-") as temp:
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
                    with urllib.request.urlopen(base + "/api/health", timeout=1) as r:
                        if r.status == 200:
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
                page.goto(base + "/culture-library/acquire")
                page.get_by_label("Strain selection").select_option("new")
                page.get_by_label("Strain name *", exact=True).fill("Browser Oyster")
                page.get_by_label("Supplier / source").fill("Browser supplier")
                page.get_by_role(
                    "button", name="Review acquisition", exact=True
                ).click()
                page.get_by_role("button", name="Back", exact=True).click()
                expect(page.get_by_label("Supplier / source")).to_have_value(
                    "Browser supplier"
                )
                page.get_by_role(
                    "button", name="Review acquisition", exact=True
                ).click()
                page.get_by_role(
                    "button", name="Confirm acquisition", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="SJ-0001", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("ready", exact=True)).to_be_visible()
                page.goto(base + "/culture-library/register-grow")
                page.get_by_label(
                    "SJ-0001 · Browser Oyster · CL-0001 · ready", exact=True
                ).check()
                page.get_by_label("Source allocation").select_option("specific")
                page.get_by_label("SJ-0001 · CL-0001", exact=True).check()
                page.get_by_role(
                    "button", name="Add fruiting container", exact=True
                ).click()
                page.get_by_label("SJ-0001 · CL-0001", exact=True).last.check()
                page.get_by_role(
                    "button", name="Register manual provenance", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="GB-0001", exact=True)
                ).to_be_visible()
                page.get_by_role(
                    "link", name="FR-0001 · FR-0001 · active", exact=True
                ).click()
                page.get_by_role(
                    "button", name="Establish Tissue Clone", exact=True
                ).click()
                page.get_by_label("Optional name", exact=True).fill("Browser clone")
                page.get_by_label("Initial physical material (optional)").select_option(
                    "agar_plate"
                )
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Browser clone", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("confirmed", exact=True)).to_be_visible()
                page.get_by_role("button", name="Create Isolate", exact=True).click()
                page.get_by_label("Optional name", exact=True).fill("Browser isolate")
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Browser isolate", exact=True)
                ).to_be_visible()
                page.goto(base + "/culture-library/fruiting/FR-0001")
                page.get_by_role("button", name="Collect Spores", exact=True).click()
                page.get_by_label("Collection date (optional)").fill("2026-10-01")
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="SP-0001", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Establish Culture", exact=True).click()
                page.get_by_label("Optional name", exact=True).fill("Spore-derived one")
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Spore-derived one", exact=True)
                ).to_be_visible()
                page.goto(base + "/culture-library/spores/SP-0001")
                page.get_by_role("button", name="Establish Culture", exact=True).click()
                page.get_by_label("Optional name", exact=True).fill("Spore-derived two")
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Spore-derived two", exact=True)
                ).to_be_visible()
                # Set up a second source through the same typed API to check mixed UI warnings.
                r = page.request.post(
                    base + "/api/provenance/acquisitions",
                    data={
                        "entry_type": "spawn_bag",
                        "line": {},
                        "inline_strain": {"name": "Browser Chestnut"},
                    },
                )
                assert r.status == 201, r.text()
                second = r.json()["records"][0]["id"]
                r = page.request.post(
                    base + "/api/provenance/grows",
                    data={"source_ids": ["SJ-0001", second], "containers": [{}]},
                )
                assert r.status == 201, r.text()
                mixed = r.json()["containers"][0]
                page.goto(base + f"/culture-library/fruiting/{mixed['id']}")
                expect(
                    page.get_by_text(
                        "Mixed named strains: no synthetic strain is created",
                        exact=True,
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Establish Tissue Clone", exact=True
                ).click()
                page.get_by_label("Optional name", exact=True).fill(
                    "Mixed-source clone"
                )
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Mixed-source clone", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("uncertain", exact=True)).to_be_visible()
                expect(
                    page.get_by_text("Possible genetic parent", exact=True)
                ).to_have_count(2)
                page.get_by_role("button", name="Correct ancestry", exact=True).click()
                page.get_by_label(
                    "Confirmed parent (or restore unknown ancestry)"
                ).select_option("CL-0001")
                page.get_by_label("Correction reason *", exact=True).fill(
                    "Verified source label"
                )
                page.get_by_role("button", name="Save", exact=True).click()
                expect(page.get_by_text("confirmed", exact=True)).to_be_visible()
                expect(
                    page.get_by_text("Verified source label", exact=False)
                ).to_be_visible()
                assert (
                    page.request.get(base + "/api/library/spawn/SJ-0001").json()[
                        "stage"
                    ]
                    == "ready"
                )
                page.screenshot(
                    path="/tmp/cultivatinator-lineage-desktop.png", full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile overflow"
                page.screenshot(
                    path="/tmp/cultivatinator-lineage-mobile.png", full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "Milestone 2B browser smoke passed: acquisition, grow allocation, clone/isolate, collection, independent lines, mixed ancestry/correction, desktop/mobile; no browser errors"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
