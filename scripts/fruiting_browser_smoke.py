"""2C.3 spawning, fruiting and harvest browser acceptance check. Uses a disposable database; build UI first.
Run: .venv/bin/python scripts/preparation_browser_smoke.py /usr/bin/chromium
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
with tempfile.TemporaryDirectory(prefix="cultivatinator-fruiting-browser-") as temp:
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
                page.set_default_timeout(10000)
                page.add_init_script(
                    "Object.defineProperty(Crypto.prototype, 'randomUUID', {value: undefined, configurable: true})"
                )
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def post(path, data):
                    response = page.request.post(base + path, data=data)
                    assert response.status == 201, response.text()
                    return response.json()

                from uuid import uuid4
                from io import BytesIO
                from PIL import Image

                def command(path, data, status=200):
                    r = page.request.post(
                        base + "/api/fruiting/" + path,
                        data={"request_key": str(uuid4()), **data},
                    )
                    assert r.status == status, r.text()
                    return r.json()

                page.goto(base + "/settings")
                page.get_by_text(
                    "Configure fruiting tent (optional)", exact=True
                ).click()
                page.get_by_label("Tent name", exact=True).fill("One browser tent")
                page.get_by_label("Target temperature", exact=True).fill("22")
                page.get_by_label("Temperature unit", exact=True).select_option("C")
                page.get_by_label("Target relative humidity (%)", exact=True).fill("85")
                page.get_by_label("FAE fan setting / schedule", exact=True).fill(
                    "Low fan"
                )
                page.get_by_role(
                    "button", name="Save Fruiting Environment", exact=True
                ).click()
                expect(
                    page.get_by_text("Environment saved for future grows.", exact=True)
                ).to_be_visible()
                recipe = post(
                    "/api/preparation/recipes",
                    {
                        "request_key": str(uuid4()),
                        "name": "Browser substrate",
                        "recipe_type": "substrate",
                        "batch_yield": 1,
                        "ingredients": [
                            {"name": "Hardwood", "quantity": "1000", "unit": "g"}
                        ],
                    },
                )
                source = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_bag",
                        "line": {},
                        "inline_strain": {"name": "Browser Fruiting Oyster"},
                    },
                )["records"][0]
                page.goto(
                    base
                    + "/quick-create/fruiting-container?source_kind=spawn&source_id="
                    + source["id"]
                )
                page.get_by_label("Substrate recipe *", exact=True).select_option(
                    recipe["id"]
                )
                page.get_by_label("Number of fruiting containers *", exact=True).fill(
                    "3"
                )
                page.get_by_label("Spawning date *", exact=True).fill("2026-01-01")
                page.get_by_role(
                    "button", name="Create Fruiting Containers", exact=True
                ).click()
                expect(
                    page.get_by_role(
                        "heading", name="Created 3 fruiting containers", exact=True
                    )
                ).to_be_visible()
                expect(
                    page.get_by_label("Physical labels for copying", exact=True)
                ).to_have_value("F-01, F-02, F-03")
                expect(
                    page.get_by_role("button", name="Copy Labels", exact=True)
                ).to_be_visible()
                link = page.get_by_role("link", name="Open F-01", exact=True)
                code = link.get_attribute("href").rsplit("/", 1)[1]
                link.click()
                expect(page.get_by_role("heading", level=1)).to_contain_text("F-01")
                expect(
                    page.get_by_text("Current Status: Colonizing", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Current flush: 1", exact=True)).to_be_visible()
                assert (
                    page.request.get(
                        base + "/api/library/spawn/" + source["id"]
                    ).json()["stage"]
                    == "used"
                )

                image = BytesIO()
                Image.new("RGB", (20, 20), "#558899").save(image, format="PNG")

                def picture(name):
                    return {
                        "name": name,
                        "mimeType": "image/png",
                        "buffer": image.getvalue(),
                    }

                def action(label, day, photos=None, retry=False):
                    page.get_by_role("button", name=label, exact=True).click()
                    page.get_by_label("Stage date *", exact=True).fill(day)
                    if photos:
                        page.get_by_label(
                            (
                                "Fruiting photos (optional)"
                                if label == "Mark Fruiting"
                                else (
                                    "Grow Completed photos (optional)"
                                    if label == "Finish Grow"
                                    else "Pinning photos (optional)"
                                )
                            ),
                            exact=True,
                        ).set_input_files([picture(name) for name in photos])
                    page.get_by_role(
                        "button", name="Save Grow Status", exact=True
                    ).click()
                    if retry:
                        expect(
                            page.get_by_text(
                                "retry.png: Simulated photo upload failure", exact=True
                            )
                        ).to_be_visible()
                        expect(
                            page.get_by_text("Grow Completed saved.", exact=True)
                        ).to_be_visible()
                        assert not current()["record"]["label_occupied"]
                        page.get_by_role(
                            "button", name="Retry remaining photos", exact=True
                        ).click()
                        expect(
                            page.get_by_role(
                                "button", name="Retry remaining photos", exact=True
                            )
                        ).to_have_count(0)
                        history = page.request.get(
                            base + f"/api/library/fruiting/{code}/activity"
                        ).json()
                        assert sum(e["event_type"] == "complete" for e in history) == 1

                def current():
                    return page.request.get(
                        base + "/api/fruiting/records/" + code
                    ).json()

                action("Mark Pinning", "2026-01-03", ["pin-one.png", "pin-two.png"])
                expect(
                    page.get_by_text("Current Status: Pinning", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("button", name="Mark Fruiting", exact=True)
                ).to_be_enabled()
                assert (
                    len(
                        page.request.get(
                            base
                            + f"/api/fruiting/records/{code}/flushes/1/pinning/photos"
                        ).json()
                    )
                    == 2
                )
                pinning_card = page.get_by_role(
                    "heading", name="Pinning — 2026-01-03", exact=True
                ).locator("..")
                expect(
                    pinning_card.get_by_role(
                        "button", name="Open photograph 1", exact=True
                    )
                ).to_be_visible()
                action(
                    "Mark Fruiting", "2026-01-05", ["fruit-one.png", "fruit-two.png"]
                )
                expect(
                    page.get_by_text("Current Status: Fruiting", exact=True)
                ).to_be_visible()

                def record_harvest(
                    day, wet, dry=None, potency=None, photos=None, retry=False
                ):
                    page.get_by_role(
                        "button", name="Record Harvest", exact=True
                    ).click()
                    page.get_by_label("Harvest date *", exact=True).fill(day)
                    page.get_by_label("Wet weight (g, optional)", exact=True).fill(wet)
                    if dry:
                        page.get_by_label("Dry weight (g, optional)", exact=True).fill(
                            dry
                        )
                    if potency:
                        page.get_by_label(
                            "Subjective medicinal potency (optional)", exact=True
                        ).select_option(potency)
                        page.get_by_label("Potency notes", exact=True).fill(
                            "Subjective grower trial"
                        )
                    if photos:
                        page.get_by_label(
                            "Harvest photos (optional)", exact=True
                        ).set_input_files([picture(name) for name in photos])
                    page.get_by_role("button", name="Save Harvest", exact=True).click()
                    if retry:
                        expect(
                            page.get_by_text(
                                "retry.png: Simulated photo upload failure", exact=True
                            )
                        ).to_be_visible()
                        expect(
                            page.get_by_text("Harvest HR-0001 saved.", exact=True)
                        ).to_be_visible()
                        assert len(current()["harvests"]) == 1
                        assert (
                            len(
                                page.request.get(
                                    base + "/api/fruiting/harvests/HR-0001/photos"
                                ).json()
                            )
                            == 1
                        )
                        page.get_by_role(
                            "button", name="Retry remaining photos", exact=True
                        ).click()
                        expect(
                            page.get_by_role(
                                "button", name="Retry remaining photos", exact=True
                            )
                        ).to_have_count(0)
                        assert len(current()["harvests"]) == 1

                    expect(
                        page.get_by_role("heading", name="Record Harvest", exact=True)
                    ).to_have_count(0)
                    expect(
                        page.get_by_text("Current Status: Harvest", exact=True)
                    ).to_be_visible()

                failed_uploads = []

                def fail_once(route):
                    if (
                        b"retry.png" in (route.request.post_data_buffer or b"")
                        and not failed_uploads
                    ):
                        failed_uploads.append(route.request.url)
                        route.fulfill(
                            status=422,
                            content_type="application/json",
                            body='{"detail":"Simulated photo upload failure"}',
                        )
                    else:
                        route.continue_()

                page.route("**/api/fruiting/harvests/*/photos", fail_once)
                record_harvest(
                    "2026-01-07",
                    "100",
                    potency="4",
                    photos=["inline-harvest.png", "retry.png"],
                    retry=True,
                )
                assert len(failed_uploads) == 1
                record_harvest("2026-01-08", "50")
                first = current()["harvests"][0]
                card = page.get_by_role(
                    "heading", name=f"Harvest {first['id']} · 2026-01-07", exact=True
                ).locator("..")
                image = BytesIO()
                Image.new("RGB", (20, 20), "#558899").save(image, format="PNG")
                card.get_by_label("Attach photographs", exact=True).set_input_files(
                    [
                        {
                            "name": "harvest-one.png",
                            "mimeType": "image/png",
                            "buffer": image.getvalue(),
                        },
                        {
                            "name": "harvest-two.png",
                            "mimeType": "image/png",
                            "buffer": image.getvalue(),
                        },
                    ]
                )
                expect(
                    card.get_by_text("2 photograph(s) attached", exact=True)
                ).to_be_visible()
                assert (
                    len(
                        page.request.get(
                            base + f"/api/fruiting/harvests/{first['id']}/photos"
                        ).json()
                    )
                    == 4
                )
                card.get_by_role("button", name="Open photograph 1", exact=True).click()
                expect(
                    page.get_by_role("dialog", name="Photograph viewer", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Close photograph", exact=True).click()
                page.get_by_role(
                    "button", name="Edit Harvest " + first["id"], exact=True
                ).click()
                page.get_by_label("Dry weight (g, optional)", exact=True).fill("10")
                page.get_by_role(
                    "button", name="Save Harvest Changes", exact=True
                ).click()
                expect(
                    page.get_by_text("Wet: 100.000 g · Dry: 10.000 g", exact=True)
                ).to_be_visible()
                assert current()["record"]["label_occupied"]
                action("Next Flush", "2026-01-10", ["second-flush.png"])
                expect(page.get_by_text("Current flush: 2", exact=True)).to_be_visible()
                expect(
                    page.get_by_text("Current Status: Pinning", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("button", name="Mark Fruiting", exact=True)
                ).to_be_enabled()
                assert (
                    len(
                        page.request.get(
                            base
                            + f"/api/fruiting/records/{code}/flushes/2/pinning/photos"
                        ).json()
                    )
                    == 1
                )
                assert (
                    len(
                        page.request.get(
                            base
                            + f"/api/fruiting/records/{code}/flushes/1/pinning/photos"
                        ).json()
                    )
                    == 2
                )
                action("Mark Fruiting", "2026-01-12", ["fruit-flush-two.png"])
                expect(
                    page.get_by_text("Current Status: Fruiting", exact=True)
                ).to_be_visible()
                record_harvest("2026-01-15", "80", dry="8")
                page.get_by_text("Fruiting environment", exact=True).click()
                page.get_by_role(
                    "button", name="Record Environment Change", exact=True
                ).click()
                page.get_by_label("Environment change date *", exact=True).fill(
                    "2026-01-14"
                )
                page.get_by_label("Reason for environment change *", exact=True).fill(
                    "Increase humidity after observations"
                )
                page.get_by_label("Target relative humidity (%)", exact=True).fill("90")
                page.get_by_role(
                    "button", name="Save Environment Change", exact=True
                ).click()
                expect(
                    page.get_by_role(
                        "button", name="Save Environment Change", exact=True
                    )
                ).to_have_count(0)
                assert current()["run"]["environment_snapshot"]["humidity"] == "85"
                assert current()["environment"]["humidity"] == "90"
                assert current()["record"]["label_occupied"]
                failed_uploads.clear()
                page.route("**/api/fruiting/records/*/completion/photos", fail_once)
                action(
                    "Finish Grow",
                    "2026-01-17",
                    ["completed-one.png", "retry.png"],
                    retry=True,
                )
                expect(
                    page.get_by_text("Current Status: Completed", exact=True)
                ).to_be_visible()
                for event, count in [
                    ("flushes/1/pinning", 2),
                    ("flushes/2/pinning", 1),
                    ("flushes/1/fruiting", 2),
                    ("flushes/2/fruiting", 1),
                    ("completion", 2),
                ]:
                    assert (
                        len(
                            page.request.get(
                                base + f"/api/fruiting/records/{code}/{event}/photos"
                            ).json()
                        )
                        == count
                    )
                for name, count in [
                    ("Fruiting — 2026-01-05", 2),
                    ("Fruiting — 2026-01-12", 1),
                    ("Grow Completed — 2026-01-17", 2),
                ]:
                    section = page.get_by_role(
                        "heading", name=name, exact=True
                    ).locator("..")
                    expect(
                        section.get_by_role(
                            "button", name="Open photograph 1", exact=True
                        )
                    ).to_be_visible()
                    assert (
                        section.get_by_role(
                            "button", name="Open photograph", exact=False
                        ).count()
                        == count
                    )
                result = current()
                assert result["results"]["wet_grams"] == "230.000"
                assert result["results"]["dry_grams"] == "18.000"
                assert result["results"]["cycle_days"] == 16
                assert result["results"]["days_to_first_pinning"] == 2
                assert result["results"]["days_to_first_harvest"] == 6
                assert not result["record"]["label_occupied"]
                page.goto(base + "/cultivation")
                expect(
                    page.locator(f'a[href="/culture-library/fruiting/{code}"]')
                ).to_have_count(0)
                page.get_by_label("Show fruiting records", exact=True).select_option(
                    "completed"
                )
                expect(
                    page.locator(f'a[href="/culture-library/fruiting/{code}"]')
                ).to_be_visible()
                page.goto(base + "/settings")
                page.get_by_text(
                    "Configure fruiting tent (optional)", exact=True
                ).click()
                page.get_by_label("Target relative humidity (%)", exact=True).fill("95")
                page.get_by_role(
                    "button", name="Save Fruiting Environment", exact=True
                ).click()
                expect(
                    page.get_by_text("Environment saved for future grows.", exact=True)
                ).to_be_visible()
                next_source = post(
                    "/api/provenance/acquisitions",
                    {"entry_type": "spawn_jar", "line": {}},
                )["records"][0]
                new = command(
                    "create",
                    {
                        "spawn_id": next_source["id"],
                        "recipe_id": recipe["id"],
                        "spawning_date": "2026-02-01",
                    },
                    201,
                )["containers"][0]
                assert new["physical_label"] == "F-01" and new["id"] != code
                assert (
                    page.request.get(
                        base + "/api/fruiting/records/" + new["id"]
                    ).json()["run"]["environment_snapshot"]["humidity"]
                    == "95"
                )
                assert current()["run"]["environment_snapshot"]["humidity"] == "85"
                page.set_viewport_size({"width": 390, "height": 844})
                for route in (
                    "/culture-library/fruiting/" + code,
                    "/cultivation",
                    "/settings",
                    "/quick-create/fruiting-container",
                ):
                    page.goto(base + route)
                    expect(page.locator("h1")).to_be_visible()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), (route + " mobile overflow")
                page.screenshot(
                    path="/tmp/cultivatinator-fruiting-mobile.png", full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "Milestone 2C.3 browser smoke passed: one spawn to three F labels, dated stages, two flushes, multiple harvests, subjective potency, inline Pinning/Next Flush/Fruiting/Harvest/Finish Grow photos, exact multi-photo uploads, safe failed-upload retry, later dry weights, original/current environment, explicit completion, totals/timing, label reuse/history, desktop/mobile; no page errors"
                )

        finally:
            process.terminate()
            process.wait(timeout=10)
