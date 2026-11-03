"""Read-only performance dashboard acceptance. Uses a disposable database.
Run: .venv/bin/python scripts/reports_browser_smoke.py /usr/bin/chromium
"""

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
with tempfile.TemporaryDirectory(prefix="cultivatinator-reports-browser-") as temp:
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
                raise RuntimeError("Application did not start")
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
                errors = []
                page.on(
                    "pageerror",
                    lambda err: (
                        errors.append(str(err)),
                        print("Browser error:", str(err)),
                    ),
                )

                def get(path):
                    r = page.request.get(base + path)
                    assert r.status == 200, r.text()
                    return r.json()

                def post(path, data, method="POST"):
                    r = page.request.fetch(base + path, method=method, data=data)
                    assert r.status in [200, 201], r.text()
                    return r.json()

                def command(path, data, method="POST"):
                    return post(path, {"request_key": str(uuid4()), **data}, method)

                page.goto(base + "/reports")
                expect(
                    page.get_by_text(
                        "Insufficient measured completed-grow data for a useful yield comparison. Missing measurements stay Unknown.",
                        exact=True,
                    )
                ).to_be_visible()
                assert (
                    get("/api/reports/performance")["summary"]["average_wet_grams"]
                    is None
                )
                formula = command(
                    "/api/preparation/recipes",
                    {
                        "name": "Original Hardwood",
                        "recipe_type": "substrate",
                        "batch_yield": 1,
                        "ingredients": [
                            {"name": "Hardwood", "quantity": "1000", "unit": "g"}
                        ],
                        "instructions": "Original snapshot instructions",
                    },
                )
                source = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_bag",
                        "line": {},
                        "inline_strain": {
                            "name": "Browser Oyster",
                            "scientific_name": "Pleurotus ostreatus",
                        },
                    },
                )

                def spawn(src, count):
                    return command(
                        "/api/fruiting/create",
                        {
                            "spawn_id": src,
                            "recipe_id": formula["id"],
                            "count": count,
                            "spawning_date": "2026-01-01",
                        },
                    )["containers"]

                def stage(code, action, day):
                    return command(
                        f"/api/fruiting/records/{code}/stage",
                        {"action": action, "action_date": day},
                    )

                def harvest(code, wet, day="2026-01-07", dry=None):
                    return command(
                        f"/api/fruiting/records/{code}/harvests",
                        {"harvest_date": day, "wet_grams": wet, "dry_grams": dry},
                    )

                def fruit(code):
                    stage(code, "pinning", "2026-01-03")
                    stage(code, "fruiting", "2026-01-05")

                rows = spawn(source["records"][0]["id"], 3)
                one, two, active = [r["id"] for r in rows]
                fruit(one)
                harvest(one, "100")
                harvest(one, "50")
                stage(one, "next_flush", "2026-01-10")
                stage(one, "fruiting", "2026-01-12")
                harvest(one, "100", "2026-01-15")
                stage(one, "complete", "2026-01-20")
                fruit(two)
                harvest(two, "0", dry="0")
                stage(two, "complete", "2026-02-20")
                fruit(active)
                harvest(active, "1000")
                formula = command(
                    f"/api/preparation/recipes/{formula['id']}",
                    {
                        **{
                            k: v
                            for k, v in formula.items()
                            if k
                            not in [
                                "id",
                                "revision",
                                "created_at",
                                "updated_at",
                                "used",
                                "is_lc_default",
                            ]
                        },
                        "expected_revision": formula["revision"],
                        "name": "Current Editable Hardwood",
                        "instructions": "New snapshot instructions",
                    },
                    "PUT",
                )
                second = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_jar",
                        "line": {},
                        "strain_id": source["line"]["strain_id"],
                    },
                )
                newer = spawn(second["records"][0]["id"], 2)
                done, failed = [r["id"] for r in newer]
                fruit(done)
                harvest(done, "400", dry="40")
                stage(done, "complete", "2026-03-20")
                fruit(failed)
                harvest(failed, "50")
                stage(failed, "failed", "2026-03-21")
                unknown = post(
                    "/api/provenance/acquisitions",
                    {"entry_type": "spawn_bag", "line": {}},
                )
                partial = spawn(unknown["records"][0]["id"], 1)[0]["id"]
                fruit(partial)
                harvest(partial, "25")
                harvest(partial, None)
                stage(partial, "complete", "2026-03-22")
                before = {
                    code: get(f"/api/fruiting/records/{code}")
                    for code in [one, two, active, done, failed, partial]
                }
                page.reload()

                def card(name):
                    return page.get_by_role("heading", name=name, exact=True).locator(
                        "xpath=ancestor::section[1]"
                    )

                expect(card("Average completed-container wet yield")).to_contain_text(
                    "216.667 g"
                )
                expect(card("Total known wet harvest weight")).to_contain_text("725 g")
                expect(
                    card("Completed fruiting containers").locator("strong")
                ).to_have_text("4")
                expect(
                    card("Failed fruiting containers").locator("strong")
                ).to_have_text("1")
                expect(page.locator(".report-coverage")).to_contain_text(
                    "3 qualifying containers share 2 distinct known spawn sources"
                )
                chart = page.get_by_text(
                    "Average measured wet yield per completed container", exact=True
                ).locator("..")
                expect(chart.get_by_text("Browser Oyster", exact=True)).to_be_visible()
                expect(
                    chart.get_by_text("Unknown provenance", exact=True)
                ).to_have_count(0)
                comparison = page.get_by_role(
                    "button", name="Comparison data & grow records", exact=False
                )
                comparison.focus()
                page.keyboard.press("Enter")
                table = page.get_by_role(
                    "table", name="Strain comparisons · All time", exact=True
                )
                expect(table).to_be_visible()
                table.get_by_role("button", name="4 grow record(s)", exact=True).click()
                link = table.locator(f'a[href="/culture-library/fruiting/{one}"]')
                expect(link).to_be_visible()
                link.click()
                expect(page.get_by_role("heading", level=1)).to_contain_text(
                    rows[0]["physical_label"]
                )
                page.goto(base + "/reports")
                expect(
                    page.get_by_role("heading", level=1, name="Reports", exact=True)
                ).to_be_visible()
                page.get_by_label("Group Results By", exact=True).select_option(
                    "recipe"
                )
                page.get_by_role("button", name="Apply filters", exact=True).click()
                expect(
                    page.get_by_role(
                        "heading", name="Substrate recipe performance", exact=True
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Comparison data & grow records", exact=False
                ).click()
                page.get_by_role(
                    "button", name="2 saved recipe revision(s)", exact=True
                ).click()
                rev = page.get_by_role(
                    "button", name="Revision 1 — Original Hardwood", exact=False
                )
                rev.click()
                expect(
                    page.get_by_text("Original snapshot instructions", exact=True)
                ).to_be_visible()
                page.get_by_label("Time Range", exact=True).select_option("custom")
                page.get_by_label("Start date", exact=True).fill("2026-01-01")
                page.get_by_label("End date", exact=True).fill("2026-01-31")
                page.get_by_role("button", name="Apply filters", exact=True).click()
                expect(card("Average completed-container wet yield")).to_contain_text(
                    "250 g"
                )
                expect(page.locator(".report-period")).to_contain_text(
                    "1 eligible terminal records"
                )
                page.get_by_label("Species / Strain", exact=True).select_option(
                    "species:Pleurotus ostreatus"
                )
                page.get_by_label("Group Results By", exact=True).select_option("line")
                page.get_by_label("Time Range", exact=True).select_option("all")
                page.get_by_role("button", name="Apply filters", exact=True).click()
                expect(
                    page.get_by_role(
                        "heading", name="Genetic culture line performance", exact=True
                    )
                ).to_be_visible()
                expect(card("Average completed-container wet yield")).to_contain_text(
                    "216.667 g"
                )
                expect(
                    page.get_by_text("Preliminary", exact=True).first
                ).to_be_visible()
                page.get_by_role("button", name="Growth speed", exact=False).click()
                expect(
                    page.get_by_role(
                        "table", name="Growth speed by genetic culture line", exact=True
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Flush performance", exact=False
                ).click()
                expect(
                    page.get_by_role(
                        "table", name="Flush measurement coverage", exact=True
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Outcomes & active grows", exact=False
                ).click()
                expect(
                    page.get_by_text("Active grows now: 1.", exact=False)
                ).to_be_visible()
                page.screenshot(
                    path="/tmp/cultivatinator-performance-desktop.png", full_page=True
                )
                for width in [390, 768]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), f"Reports overflow at {width}"
                    assert (
                        page.get_by_role(
                            "button", name="Apply filters", exact=True
                        ).bounding_box()["height"]
                        >= 44
                    )
                page.screenshot(
                    path="/tmp/cultivatinator-performance-mobile.png", full_page=True
                )
                for code, value in before.items():
                    assert (
                        get(f"/api/fruiting/records/{code}") == value
                    ), "Reporting changed grow history"
                assert not errors, errors
                browser.close()
                print(
                    "Reports browser smoke passed: empty/known/zero/partial data, shared spawn counts, failed versus active, recorded period/species/line/recipe filters, original recipe revisions, permanent FR links, keyboard tables, timing/flush/outcome coverage, desktop/phone/tablet; no mutations or page errors"
                )
        finally:
            process.terminate()
            process.wait(timeout=10)
