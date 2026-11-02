"""2C.2 direct cultivation and recipe workspace browser acceptance check. Uses a disposable database; build UI first.
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

                # A legitimate acquired culture is used as the physical source.
                # Every new recipe and direct cultivation operation below uses the UI.
                source = post(
                    "/api/library/receive-culture",
                    {
                        "inline_strain": {"name": "Browser Oyster"},
                        "line": {},
                        "material": {"material_type": "lc_jar"},
                    },
                )["physical"][0]
                page.goto(base + "/culture-library/physical/" + source["id"])
                page.get_by_role(
                    "button", name="Correct Remaining Culture Material", exact=True
                ).click()
                page.get_by_label(
                    "Measured remaining quantity (blank = unknown)", exact=True
                ).fill("100")
                page.get_by_label("Measurement correction reason *", exact=True).fill(
                    "Measured culture volume"
                )
                page.get_by_role(
                    "button", name="Save Measured Balance", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "Remaining Culture Material: 100.000 mL", exact=False
                    )
                ).to_be_visible()

                def add_recipe(category, name, recipe_type=None):
                    page.goto(base + "/recipes/" + category)
                    page.get_by_role("link", name="Add Recipe", exact=True).click()
                    page.get_by_label("Recipe name *", exact=True).fill(name)
                    if recipe_type:
                        page.get_by_label("Recipe type").select_option(recipe_type)
                    page.get_by_label("Short description", exact=True).fill(
                        "Browser formulation"
                    )
                    page.get_by_label("Yield (containers) *", exact=True).fill("5")
                    page.get_by_label("Ingredient 1 name *", exact=True).fill(
                        "Nutrient"
                    )
                    page.get_by_label("Ingredient 1 quantity *", exact=True).fill("10")
                    page.get_by_label("Preparation instructions", exact=True).fill(
                        "Prepare and sterilize"
                    )
                    page.get_by_label("Recipe notes", exact=True).fill("Original notes")
                    page.get_by_role("button", name="Save Recipe", exact=True).click()
                    expect(
                        page.get_by_role("heading", name=name, exact=True)
                    ).to_be_visible()
                    return next(
                        r
                        for r in page.request.get(
                            base + "/api/preparation/recipes"
                        ).json()
                        if r["name"] == name
                    )

                page.goto(base + "/recipes")
                for category in ("Agar", "Spawn Seed", "Substrate"):
                    expect(
                        page.get_by_role("heading", name=category, exact=True)
                    ).to_be_visible()
                agar = add_recipe("agar", "Standard Agar")
                grain = add_recipe("spawn-seed", "Standard Grain", "grain")
                media = add_recipe("spawn-seed", "LC Medium", "lc")
                substrate = add_recipe("substrate", "Substrate definition")
                page.get_by_role("button", name="Duplicate Recipe", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Edit Recipe", exact=True)
                ).to_be_visible()
                page.get_by_label("Recipe name *", exact=True).fill(
                    "Substrate experiment"
                )
                page.get_by_role("button", name="Save Recipe", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Substrate experiment", exact=True)
                ).to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Delete Recipe", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Substrate Recipes", exact=True)
                ).to_be_visible()
                assert all(
                    r["name"] != "Substrate experiment"
                    for r in page.request.get(base + "/api/preparation/recipes").json()
                )
                page.goto(base + "/recipes/spawn-seed")
                page.get_by_label("Recipe subtype").select_option("lc")
                expect(
                    page.get_by_role("link", name="LC Medium", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="Standard Grain", exact=True)
                ).to_have_count(0)
                # No ingredients or reusable containers have been registered.
                assert all(
                    s["category"] == "source"
                    for s in page.request.get(base + "/api/preparation/stock").json()
                )

                def direct(operation, recipe_id, count, usage=None, material_type=None):
                    page.goto(
                        base
                        + f"/quick-create/{operation}?source_kind=physical&source_id={source['id']}"
                    )
                    if material_type:
                        page.get_by_label("Material type").select_option(material_type)
                    if recipe_id:
                        page.locator("#recipe_id").select_option(recipe_id)
                    expect(
                        page.get_by_label("Source material", exact=True)
                    ).to_have_value("physical:" + source["id"])
                    page.get_by_label("Number of containers *", exact=True).fill(
                        str(count)
                    )
                    assert page.get_by_label(
                        "Inoculation date *", exact=True
                    ).input_value()
                    if usage:
                        page.get_by_label(
                            "Source usage per container *", exact=True
                        ).fill(usage)
                    expect(
                        page.get_by_label("Reusable pool or disposable supply")
                    ).to_have_count(0)
                    page.get_by_role(
                        "button",
                        name="Create "
                        + {
                            "agar-plate": "Agar plate",
                            "spawn": (
                                "Spawn bag"
                                if material_type == "spawn_bag"
                                else "Spawn jar"
                            ),
                            "lc-container": "LC container / jar",
                            "lc-syringe": "LC syringe",
                        }[operation],
                        exact=True,
                    ).click()
                    try:
                        expect(
                            page.get_by_role(
                                "heading",
                                name=f"Created {count} {'record' if count == 1 else 'records'}",
                                exact=True,
                            )
                        ).to_be_visible()
                    except AssertionError:
                        print(
                            "Creation alerts:",
                            page.get_by_role("alert").all_text_contents(),
                        )
                        print(
                            "Form validation:",
                            page.locator("form").evaluate_all(
                                "forms => forms.flatMap(form => Array.from(form.elements).map(e => ({name: e.name, value: e.value, valid: e.checkValidity(), message: e.validationMessage})))"
                            ),
                        )
                        page.screenshot(
                            path="/tmp/cultivatinator-direct-failure.png",
                            full_page=True,
                        )
                        raise
                    ids = (
                        page.get_by_label("Generated IDs for copying", exact=True)
                        .input_value()
                        .split(", ")
                    )
                    assert len(ids) == count and len(set(ids)) == count
                    for code in ids:
                        expect(
                            page.get_by_role("link", name="Open " + code, exact=True)
                        ).to_be_visible()
                    page.get_by_role("button", name="Copy IDs", exact=True).click()
                    return ids

                plates = direct("agar-plate", agar["id"], 3, "2")
                bags = direct("spawn", grain["id"], 5, "4", "spawn_bag")
                jars = direct("spawn", grain["id"], 2, "3", "spawn_jar")
                lc = direct("lc-container", media["id"], 1, "2")
                syringes = direct("lc-syringe", None, 2, "5")
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["remaining_quantity"]
                    == "56.000"
                )
                assert len(page.request.get(base + "/api/library/lines").json()) == 1
                assert all(
                    r["stage"] == "colonizing"
                    for r in page.request.get(base + "/api/library/spawn").json()
                )
                page.goto(base + "/laboratory")
                expect(
                    page.get_by_role(
                        "link", name=plates[0] + " · Agar plate", exact=True
                    )
                ).to_be_visible()
                page.goto(base + "/cultivation")
                expect(
                    page.get_by_role("link", name=bags[0] + " · Spawn bag", exact=True)
                ).to_be_visible()
                page.get_by_label("Show records").select_option("spawn_jar")
                expect(
                    page.get_by_role("link", name=jars[0] + " · Spawn jar", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name=bags[0] + " · Spawn bag", exact=True)
                ).to_have_count(0)
                page.goto(base + "/culture-library/physical/" + plates[0])
                expect(
                    page.get_by_role(
                        "heading", name="Recipe: Standard Agar", exact=True
                    )
                ).to_be_visible()
                page.goto(base + "/recipes/detail/" + agar["id"])
                expect(
                    page.get_by_role("button", name="Archive Recipe", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("button", name="Delete Recipe", exact=True)
                ).to_have_count(0)
                page.get_by_role("link", name="Edit Recipe", exact=True).click()
                page.get_by_label("Recipe notes", exact=True).fill("Edited notes")
                page.get_by_role("button", name="Save Recipe", exact=True).click()
                expect(page.get_by_text("Edited notes", exact=True)).to_be_visible()
                snapshot = page.request.get(
                    base + "/api/preparation/materials/" + plates[0]
                ).json()["snapshot"]
                assert snapshot["recipe"]["notes"] == "Original notes"
                page.get_by_role("button", name="Archive Recipe", exact=True).click()
                expect(
                    page.get_by_text("Agar · Agar · Archived", exact=False)
                ).to_be_visible()
                # Optional stock is visible immediately and can be edited without changing its balance.
                page.goto(base + "/inventory")
                page.get_by_role("button", name="+ Add Inventory", exact=True).click()
                page.get_by_label("Inventory name *", exact=True).fill("Grain supply")
                page.get_by_label("Inventory unit").select_option("lb")
                page.get_by_label(
                    "Confirmed available quantity (blank = unknown)", exact=True
                ).fill("2")
                page.get_by_label("Storage location (optional)", exact=True).fill(
                    "Shelf A"
                )
                page.get_by_label("Opening balance reason *", exact=True).fill(
                    "Purchased"
                )
                page.get_by_role("button", name="Add Inventory", exact=True).click()
                expect(
                    page.get_by_role("button", name="Edit Grain supply", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Edit Grain supply", exact=True).click()
                page.get_by_label("Item name *", exact=True).fill("Measured grain")
                page.get_by_label("Storage location", exact=True).fill("Shelf B")
                page.get_by_label("Edit reason *", exact=True).fill(
                    "Corrected label and location"
                )
                page.get_by_role("button", name="Save Item", exact=True).click()
                expect(
                    page.get_by_role("button", name="Edit Measured grain", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Storage: Shelf B", exact=True)).to_be_visible()
                # A previous prepared-material operation can still finish using its original ID.
                from uuid import uuid4

                def operation(path, body):
                    return post(
                        "/api/preparation/" + path,
                        {"request_key": str(uuid4()), **body},
                    )

                pool = operation(
                    "stock",
                    {
                        "name": "Historical plates",
                        "category": "reusable",
                        "unit": "count",
                        "available": "2",
                        "container_type": "agar_plate",
                        "reason": "Historical pool",
                    },
                )
                raw = next(
                    s
                    for s in page.request.get(base + "/api/preparation/stock").json()
                    if s["name"] == "Measured grain"
                )
                old = operation(
                    "prepare",
                    {
                        "material_type": "agar_plate",
                        "count": 1,
                        "container_item_id": pool["id"],
                        "ingredients": [
                            {"item_id": raw["id"], "quantity": "1", "unit": "g"}
                        ],
                    },
                )["materials"][0]
                page.goto(base + "/inventory/prepared/inoculate")
                page.get_by_label("Source material").select_option(
                    "physical:" + source["id"]
                )
                page.get_by_role("checkbox", name=old["id"], exact=False).check()
                page.get_by_label("Source usage per container *", exact=True).fill("1")
                page.get_by_role(
                    "button", name="Inoculate Selected Containers", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="Prepared Materials", exact=True)
                ).to_be_visible()
                assert (
                    page.request.get(base + "/api/library/physical/" + old["id"]).status
                    == 200
                )
                page.set_viewport_size({"width": 390, "height": 844})
                for path in (
                    "/recipes",
                    "/recipes/spawn-seed",
                    "/laboratory",
                    "/cultivation",
                    "/inventory",
                    "/quick-create/agar-plate",
                ):
                    page.goto(base + path)
                    expect(page.locator("h1")).to_be_visible()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    ), (path + " mobile overflow")
                page.screenshot(
                    path="/tmp/cultivatinator-direct-mobile.png", full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "Final 2C.2 workflow browser smoke passed: three recipe categories and LC subtype, duplicate/delete/archive, direct agar/spawn/LC/syringe creation, permanent IDs, lineage, LC balance, growing views, visible/editable optional stock, historical prepared inoculation, desktop/mobile; no page errors"
                )

        finally:
            process.terminate()
            process.wait(timeout=10)
