"""2C.2 revised Inventory → Preparation → Quick Create acceptance check. Uses a disposable database; build UI first.
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
with tempfile.TemporaryDirectory(prefix="cultivatinator-preparation-browser-") as temp:
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

                # An outside LC is a legitimate acquisition; all preparation accounting below uses the UI.
                source = post(
                    "/api/library/receive-culture",
                    {
                        "inline_strain": {"name": "Browser Oyster"},
                        "line": {},
                        "material": {"material_type": "lc_jar"},
                    },
                )["physical"][0]

                def open_stock(name, category, quantity, unit="g", container_type=None):
                    page.goto(base + "/inventory/stock")
                    page.get_by_role(
                        "button", name="+ Add Inventory", exact=True
                    ).click()
                    page.get_by_label("Inventory name *", exact=True).fill(name)
                    page.get_by_label("Inventory category").select_option(category)
                    if container_type:
                        page.get_by_label("Container supply type").select_option(
                            container_type
                        )
                    page.get_by_label("Inventory unit").select_option(unit)
                    page.get_by_label(
                        (
                            "Confirmed free container count *"
                            if category == "reusable"
                            else "Confirmed available quantity (blank = unknown)"
                        ),
                        exact=True,
                    ).fill(quantity)
                    page.get_by_label("Opening balance reason *", exact=True).fill(
                        "Counted and confirmed opening stock"
                    )
                    page.get_by_role("button", name="Add Inventory", exact=True).click()
                    expect(
                        page.get_by_text("Opening inventory recorded.", exact=True)
                    ).to_be_visible()
                    return next(
                        r
                        for r in page.request.get(
                            base + "/api/preparation/stock"
                        ).json()
                        if r["name"] == name
                    )

                grain = open_stock("Grain", "ingredient", "2", "lb")
                assert grain["available"] == "907.18474"
                bags = open_stock(
                    "Sterile bags", "consumable", "10", "count", "spawn_bag"
                )
                agar = open_stock("Agar powder", "ingredient", "1", "oz")
                assert agar["available"] == "28.349523125"
                volume = open_stock("Liquid ingredient", "ingredient", "32", "us_fl_oz")
                assert volume["available"] == "946.352946"
                pool = open_stock(
                    "Clean plates", "reusable", "20", "count", "agar_plate"
                )
                # Legacy acquisition quantities were not imported as remaining source volume.
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["remaining_quantity"]
                    is None
                )
                page.goto(base + "/culture-library/physical/" + source["id"])
                page.get_by_role(
                    "button", name="Correct Remaining Culture Material", exact=True
                ).click()
                page.get_by_label(
                    "Measured remaining quantity (blank = unknown)", exact=True
                ).fill("25")
                page.get_by_label("Measurement correction reason *", exact=True).fill(
                    "Measured 25 mL remaining"
                )
                page.get_by_role(
                    "button", name="Save Measured Balance", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "Remaining Culture Material: 25.000 mL", exact=False
                    )
                ).to_be_visible()
                source_stock = next(
                    r
                    for r in page.request.get(base + "/api/preparation/stock").json()
                    if r["physical_id"] == source["id"]
                )
                page.goto(base + "/recipes")
                page.get_by_role("button", name="New Recipe", exact=True).click()
                page.get_by_label("Recipe name *", exact=True).fill("Five grain bags")
                page.get_by_label("Recipe type").select_option("grain")
                page.get_by_label("Recipe yield (containers) *", exact=True).fill("5")
                page.get_by_role("button", name="Add Ingredient", exact=True).click()
                page.get_by_label("Ingredient 1 *").select_option(grain["id"])
                page.get_by_label("Ingredient 1 quantity (g) *", exact=True).fill("500")
                page.get_by_label("Processing method").select_option("instant_pot")
                page.get_by_label("Duration (minutes)", exact=True).fill("90")
                page.get_by_role("button", name="Save Recipe", exact=True).click()
                expect(
                    page.get_by_role("button", name="New Recipe", exact=True)
                ).to_be_visible()
                recipe = page.request.get(base + "/api/preparation/recipes").json()[0]
                page.get_by_role("button", name="New Recipe", exact=True).click()
                page.get_by_label("Recipe name *", exact=True).fill("Low grain variant")
                page.get_by_label("Recipe type").select_option("grain")
                page.get_by_label("Recipe yield (containers) *", exact=True).fill("5")
                page.get_by_role("button", name="Add Ingredient", exact=True).click()
                page.get_by_label("Ingredient 1 *").select_option(grain["id"])
                page.get_by_label("Ingredient 1 quantity (g) *", exact=True).fill("250")
                page.get_by_role("button", name="Save Recipe", exact=True).click()
                page.get_by_label("Compare Five grain bags", exact=True).check()
                page.get_by_label("Compare Low grain variant", exact=True).check()
                expect(
                    page.get_by_role("heading", name="Recipe Comparison", exact=True)
                ).to_be_visible()
                expect(page.get_by_role("table")).to_contain_text("500 Grams (g)")
                expect(page.get_by_role("table")).to_contain_text("250 Grams (g)")
                page.goto(base + "/inventory/prepared/prepare")
                page.get_by_label("Preparation container type").select_option(
                    "spawn_bag"
                )
                page.get_by_label(
                    "Number of prepared containers (1–100) *", exact=True
                ).fill("5")
                page.get_by_label("Reusable pool or disposable supply").select_option(
                    bags["id"]
                )
                page.get_by_label("Saved recipe (optional)").select_option(recipe["id"])
                expect(
                    page.get_by_label("Ingredient 1 quantity (g) *", exact=True)
                ).to_have_value("500.000")
                page.get_by_role("button", name="Prepare Materials", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                prepared = page.request.get(base + "/api/preparation/materials").json()
                assert len(prepared) == 5 and all(
                    r["stage"] == "ready" for r in prepared
                )
                expect(
                    page.get_by_text("Ready to Inoculate · Batch", exact=False)
                ).to_have_count(5)
                page.goto(
                    base
                    + f"/quick-create/spawn?source_kind=physical&source_id={source['id']}"
                )
                expect(page.get_by_label("Source material", exact=True)).to_have_value(
                    "physical:" + source["id"]
                )
                expect(
                    page.get_by_label(
                        "Number of prepared containers (1–100) *", exact=True
                    )
                ).to_have_count(0)
                expect(
                    page.get_by_role("button", name="Prepare Containers", exact=True)
                ).to_have_count(0)
                page.get_by_role(
                    "button", name="Select Up to 100 Ready Containers", exact=True
                ).click()
                page.get_by_label("Source usage per container *", exact=True).fill("5")
                expect(
                    page.get_by_text(
                        "Selected: 5 · Total source requirement: 25.000 mL", exact=True
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Inoculate Selected Containers", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                spawn = page.request.get(base + "/api/library/spawn").json()
                assert len(spawn) == 5 and all(
                    r["line_id"] == source["line_id"] and r["stage"] == "colonizing"
                    for r in spawn
                )
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["lifecycle"]
                    == "depleted"
                )
                assert len(page.request.get(base + "/api/library/lines").json()) == 1
                page.goto(base + "/quick-create/lc-syringe")
                expect(page.get_by_label("Source material", exact=True)).to_be_visible()
                assert (
                    source["id"]
                    not in page.get_by_label("Source material", exact=True).inner_text()
                )
                page.goto(base + "/culture-library/physical/" + source["id"])
                page.get_by_role(
                    "button", name="Correct Remaining Culture Material", exact=True
                ).click()
                page.get_by_label(
                    "Measured remaining quantity (blank = unknown)", exact=True
                ).fill("30")
                page.get_by_label("Measurement correction reason *", exact=True).fill(
                    "Verified volume correction"
                )
                page.get_by_role(
                    "button", name="Save Measured Balance", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "Remaining Culture Material: 30.000 mL", exact=False
                    )
                ).to_be_visible()
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["lifecycle"]
                    == "active"
                )
                # Prepare two reusable agar plates, inoculate them separately, then release each exactly once.
                page.goto(base + "/inventory/prepared/prepare")
                page.get_by_label(
                    "Number of prepared containers (1–100) *", exact=True
                ).fill("2")
                page.get_by_label("Reusable pool or disposable supply").select_option(
                    pool["id"]
                )
                page.get_by_role("button", name="Add Ingredient", exact=True).click()
                page.get_by_label("Ingredient 1 *").select_option(agar["id"])
                page.get_by_label("Ingredient 1 quantity (g) *", exact=True).fill("10")
                page.get_by_role("button", name="Prepare Materials", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                plates = [
                    r
                    for r in page.request.get(
                        base + "/api/preparation/materials"
                    ).json()
                    if r["material_type"] == "agar_plate"
                ]
                expect(
                    page.get_by_text("Ready to Inoculate · Batch", exact=False)
                ).to_have_count(2)
                page.goto(
                    base
                    + f"/quick-create/agar-plate?source_kind=physical&source_id={source['id']}"
                )
                page.get_by_role("checkbox", name=plates[0]["id"], exact=False).check()
                page.get_by_label("Source usage per container *", exact=True).fill("5")
                page.get_by_role(
                    "button", name="Inoculate Selected Containers", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                state = next(
                    r
                    for r in page.request.get(base + "/api/preparation/pools").json()
                    if r["item_id"] == pool["id"]
                )
                assert (
                    state["available"] == "18.000"
                    and state["ready"] == 1
                    and state["inoculated"] == 1
                    and state["total"] == "20.000"
                )
                page.goto(
                    base
                    + f"/quick-create/agar-plate?source_kind=physical&source_id={plates[0]['id']}"
                )
                page.get_by_role("checkbox", name=plates[1]["id"], exact=False).check()
                page.get_by_role(
                    "button", name="Inoculate Selected Containers", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + plates[0]["id"]
                    ).json()["lifecycle"]
                    == "active"
                )
                for i, row in enumerate(plates):
                    page.goto(base + "/culture-library/physical/" + row["id"])
                    page.get_by_label("Lifecycle action").select_option(
                        "complete" if i == 0 else "failed"
                    )
                    page.get_by_label("Lifecycle reason *", exact=True).fill(
                        "Finished transfers" if i == 0 else "Observed failed culture"
                    )
                    page.get_by_role(
                        "button", name="Confirm Lifecycle Action", exact=True
                    ).click()
                    expect(
                        page.get_by_text(
                            "Lifecycle: completed" if i == 0 else "Lifecycle: failed",
                            exact=False,
                        )
                    ).to_be_visible()
                    assert (
                        page.get_by_role(
                            "button", name="Confirm Lifecycle Action", exact=True
                        ).count()
                        == 0
                    )
                assert (
                    next(
                        r
                        for r in page.request.get(
                            base + "/api/preparation/stock"
                        ).json()
                        if r["id"] == pool["id"]
                    )["available"]
                    == "20.000"
                )
                page.goto(base + "/inventory/transactions")
                expect(
                    page.get_by_text("Verified volume correction", exact=True).first
                ).to_be_visible()
                page.screenshot(
                    path="/tmp/cultivatinator-preparation-desktop.png", full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base + "/inventory/prepared")
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile overflow"
                page.goto(base + "/inventory/stock")
                expect(
                    page.get_by_role(
                        "heading", name="Reusable Container Pools", exact=True
                    )
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Pool table mobile overflow"
                page.goto(base + "/recipes")
                page.get_by_label("Compare Five grain bags", exact=True).check()
                page.get_by_label("Compare Low grain variant", exact=True).check()
                expect(
                    page.get_by_role("heading", name="Recipe Comparison", exact=True)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Recipe comparison mobile overflow"
                page.screenshot(
                    path="/tmp/cultivatinator-preparation-mobile.png", full_page=True
                )
                page.get_by_role("button", name="Open navigation", exact=True).click()
                page.get_by_role("link", name="Inventory", exact=True).first.click()
                expect(
                    page.get_by_role("link", name="Receive Acquisition", exact=True)
                ).to_be_visible()
                assert not errors, errors
                browser.close()
                print(
                    "Milestone 2C.2 browser smoke passed: generic inventory, recipe scaling, automatic readiness, five separate spawn bags, one 25mL deduction, depletion/correction, partial agar transfers, terminal release, audit, desktop/mobile"
                )

        finally:
            process.terminate()
            process.wait(timeout=10)
