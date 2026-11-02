"""Optional 2B browser acceptance check. Uses a disposable database; build UI first.
Run: .venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
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
with tempfile.TemporaryDirectory(prefix="cultivatinator-quick-create-browser-") as temp:
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
                errors, writes = [], []
                page.on(
                    "pageerror",
                    lambda error: (
                        errors.append(str(error)),
                        print("Browser error:", str(error)),
                    ),
                )
                page.on(
                    "request",
                    lambda request: (
                        writes.append(request.url)
                        if request.method not in ("GET", "HEAD")
                        else None
                    ),
                )

                def post(path, data):
                    response = page.request.post(base + path, data=data)
                    assert response.status == 201, response.text()
                    return response.json()

                culture = post(
                    "/api/library/receive-culture",
                    {
                        "inline_strain": {"name": "Browser Oyster"},
                        "line": {},
                        "material": {"material_type": "lc_jar"},
                    },
                )
                post(
                    "/api/library/receive-culture",
                    {
                        "strain_id": culture["line"]["strain_id"],
                        "line": {},
                        "material": {"material_type": "agar_plate"},
                    },
                )
                spawn = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_jar",
                        "line": {},
                        "inline_strain": {"name": "Browser Chestnut"},
                    },
                )
                batch = post(
                    "/api/provenance/grows",
                    {"source_ids": [spawn["records"][0]["id"]], "containers": [{}]},
                )
                fr = batch["containers"][0]
                assert fr["strain_name"] == "Browser Chestnut"

                def counts():
                    return {
                        kind: len(
                            page.request.get(
                                base + "/api/library/" + kind + "?status=all"
                            ).json()
                        )
                        for kind in ["lines", "physical", "spawn", "fruiting", "spores"]
                    }

                before = counts()
                operations = [
                    ("agar-plate", "New Agar Plate"),
                    ("lc-syringe", "New LC Syringe"),
                    ("lc-container", "New LC Container / Jar"),
                    ("spawn", "New Spawn Jar / Bag"),
                    ("spore-print", "New Spore Print"),
                    ("fruiting-container", "New Fruiting Container"),
                ]
                for slug, label in operations:
                    print("Checking", slug)
                    page.goto(base + "/")
                    page.get_by_role("link", name=label, exact=True).click()
                    expect(
                        page.get_by_role("heading", name=label, exact=True)
                    ).to_be_visible()
                    expect(
                        page.get_by_label("Source material", exact=True)
                    ).to_be_visible()
                    if slug != "spore-print":
                        expect(
                            page.get_by_text("OPERATION NOT YET AVAILABLE", exact=True)
                        ).to_be_visible()
                        assert (
                            page.get_by_role("button", name="Save", exact=True).count()
                            == 0
                        )
                assert counts() == before
                assert not writes, writes
                page.goto(base + "/culture-library/physical/LC-0001")
                page.get_by_text("Create From This", exact=True).click()
                page.get_by_role("link", name="New LC Syringe", exact=True).click()
                expect(page.get_by_label("Source material", exact=True)).to_have_value(
                    "physical:LC-0001"
                )
                assert (
                    "AG-0001"
                    not in page.get_by_label("Source material", exact=True).inner_text()
                )
                page.goto(base + "/inventory")
                page.get_by_role("link", name="Receive Acquisition", exact=True).click()
                expect(page.get_by_label("Acquired material")).to_be_visible()
                page.goto(
                    base
                    + "/culture-library/receive-culture?strain=STR-0001&line=CL-0001"
                )
                expect(page).to_have_url(
                    base + "/inventory/receive-culture?strain=STR-0001&line=CL-0001"
                )
                expect(page.get_by_label("Strain selection")).to_have_value("existing")
                page.goto(base + "/culture-library")
                expect(page.locator(".strain-card")).to_have_count(2)
                assert (
                    page.get_by_role(
                        "link", name="Receive Acquisition", exact=True
                    ).count()
                    == 0
                )
                assert (
                    page.get_by_role("link", name="+ Add Strain", exact=True).count()
                    == 0
                )
                page.goto(base + "/culture-library/fruiting/" + fr["id"])
                expect(page.locator(".detail-panel")).to_contain_text(
                    "Browser Chestnut"
                )
                page.get_by_text("Create From This", exact=True).click()
                page.get_by_role("link", name="New Spore Print", exact=True).click()
                expect(page.get_by_label("Source material", exact=True)).to_have_value(
                    "fruiting:" + fr["id"]
                )
                page.get_by_label("Optional name", exact=True).fill(
                    "Quick collected print"
                )
                page.get_by_role(
                    "button", name="Register Spore Print", exact=True
                ).click()
                expect(
                    page.get_by_role(
                        "heading", name="Quick collected print", exact=True
                    )
                ).to_be_visible()
                assert counts()["spores"] == before["spores"] + 1
                assert counts()["lines"] == before["lines"]
                assert len(writes) == 1 and writes[0].endswith("/collect"), writes
                relation = page.request.get(
                    base + "/api/provenance/spores/SP-0001"
                ).json()
                assert any(
                    r["record"]["id"] == fr["id"] for r in relation["relationships"]
                )
                assert (
                    page.request.get(
                        base + "/api/library/spawn/" + spawn["records"][0]["id"]
                    ).json()["stage"]
                    == "ready"
                )
                page.goto(base + "/")
                page.screenshot(
                    path="/tmp/cultivatinator-quick-create-desktop.png", full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_role(
                    "link", name="New Fruiting Container", exact=True
                ).scroll_into_view_if_needed()
                page.screenshot(
                    path="/tmp/cultivatinator-quick-create-mobile.png", full_page=True
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile dashboard overflow"
                page.get_by_role(
                    "link", name="New Fruiting Container", exact=True
                ).click()
                page.get_by_label("Source material", exact=True).select_option(
                    "spawn:" + spawn["records"][0]["id"]
                )
                expect(
                    page.get_by_text("OPERATION NOT YET AVAILABLE", exact=True)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile workflow overflow"
                page.get_by_role("button", name="Open navigation", exact=True).click()
                page.get_by_role("link", name="Inventory", exact=True).click()
                expect(
                    page.get_by_role("link", name="Receive Acquisition", exact=True)
                ).to_be_visible()
                assert not errors, errors
                browser.close()
                print(
                    "Milestone 2C.1 browser smoke passed: six entries, read-only deferred actions, source filtering/preselection, Inventory, legacy redirect, clean catalog, real spore collection, 2B FR identity/provenance, desktop/mobile; no page errors"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
