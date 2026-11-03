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
                    page.get_by_role(
                        "link",
                        name=(
                            "Set Up LC Media"
                            if category == "lc-media"
                            else "Add Recipe"
                        ),
                        exact=True,
                    ).click()
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
                for category in ("LC Media", "Agar", "Spawn Seed", "Substrate"):
                    expect(
                        page.get_by_role("heading", name=category, exact=True)
                    ).to_be_visible()
                agar = add_recipe("agar", "Standard Agar")
                grain = add_recipe("spawn-seed", "Standard Grain", "grain")
                media = add_recipe("lc-media", "LC Medium", "lc")
                page.get_by_role(
                    "button", name="Use as Default LC Media", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "Default LC Media · automatically used for new LC containers",
                        exact=True,
                    )
                ).to_be_visible()
                assert (
                    page.request.get(base + "/api/preparation/lc-default").json()[
                        "recipe"
                    ]["id"]
                    == media["id"]
                )
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
                expect(
                    page.get_by_role("link", name="Standard Grain", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="LC Medium", exact=True)
                ).to_have_count(0)
                expect(page.get_by_label("Recipe subtype")).to_have_count(0)
                # No ingredients or reusable containers have been registered.
                assert all(
                    s["category"] == "source"
                    for s in page.request.get(base + "/api/preparation/stock").json()
                )

                def direct(
                    operation,
                    recipe_id,
                    count,
                    usage=None,
                    material_type=None,
                    starting_volume=None,
                    source_code=None,
                    physical_label=None,
                ):
                    source_code = source_code or source["id"]
                    page.goto(base + "/culture-library/physical/" + source_code)
                    page.get_by_text("Create From This", exact=True).click()
                    page.get_by_role(
                        "link",
                        name={
                            "agar-plate": "New Agar Plate",
                            "spawn": "New Spawn Jar / Bag",
                            "lc-container": "New LC Container / Jar",
                            "lc-syringe": "New LC Syringe",
                        }[operation],
                        exact=True,
                    ).click()
                    if material_type:
                        page.get_by_label("Material type").select_option(material_type)
                    if operation in {"agar-plate", "spawn"}:
                        page.locator("#recipe_id").select_option(recipe_id)
                    else:
                        expect(page.locator("#recipe_id")).to_have_count(0)
                    if starting_volume:
                        page.get_by_label(
                            "Measured total volume per destination (mL, optional)",
                            exact=True,
                        ).fill(starting_volume)
                    expect(
                        page.get_by_label("Source material", exact=True)
                    ).to_have_value("physical:" + source_code)
                    page.get_by_label("Number of containers *", exact=True).fill(
                        str(count)
                    )
                    assert page.get_by_label(
                        "Inoculation date *", exact=True
                    ).input_value()
                    if physical_label:
                        page.get_by_text(
                            "Physical labels · automatic lowest available (optional override)",
                            exact=True,
                        ).click()
                        page.get_by_label(
                            "Container 1 physical label", exact=True
                        ).select_option(physical_label)
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
                    if operation == "agar-plate":
                        expect(
                            page.get_by_text("Current Status: Germinating", exact=True)
                        ).to_have_count(count)
                    labels = (
                        page.get_by_label("Physical labels for copying", exact=True)
                        .input_value()
                        .split(", ")
                    )
                    assert len(labels) == count and len(set(labels)) == count
                    ids = []
                    for code in labels:
                        link = page.get_by_role("link", name="Open " + code, exact=True)
                        ids.append(link.get_attribute("href").rsplit("/", 1)[1])
                        expect(
                            page.get_by_role("link", name="Open " + code, exact=True)
                        ).to_be_visible()
                    page.get_by_role("button", name="Copy Labels", exact=True).click()
                    return ids

                bags = direct("spawn", grain["id"], 5, "5", "spawn_bag")
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["remaining_quantity"]
                    == "75.000"
                )
                plates = direct("agar-plate", agar["id"], 3, "2")
                jars = direct("spawn", grain["id"], 2, "3", "spawn_jar")
                lc = direct("lc-container", None, 1, "2", starting_volume="100")
                syringes = direct("lc-syringe", None, 2, "5", source_code=lc[0])
                assert (
                    page.request.get(
                        base + "/api/library/physical/" + source["id"]
                    ).json()["remaining_quantity"]
                    == "61.000"
                )
                assert (
                    page.request.get(base + "/api/library/physical/" + lc[0]).json()[
                        "remaining_quantity"
                    ]
                    == "90.000"
                )
                for code in syringes:
                    snapshot = page.request.get(
                        base + "/api/preparation/materials/" + code
                    ).json()["snapshot"]
                    assert snapshot["recipe"]["name"] == "LC Medium"
                    assert (
                        snapshot["media_origin"] == "source_transfer"
                        and snapshot["ingredients"] == []
                    )
                assert len(page.request.get(base + "/api/library/lines").json()) == 1
                assert all(
                    r["stage"] == "colonizing"
                    for r in page.request.get(base + "/api/library/spawn").json()
                )
                page.goto(base + "/laboratory")
                expect(
                    page.get_by_role("link", name="P-01 · Agar plate", exact=True)
                ).to_be_visible()
                plate_row = page.locator(".record-list > li").filter(
                    has=page.get_by_role("link", name="P-01 · Agar plate", exact=True)
                )
                expect(
                    plate_row.get_by_text("Current Status: Germinating", exact=True)
                ).to_be_visible()
                page.goto(
                    base
                    + "/quick-create/agar-plate?source_kind=physical&source_id="
                    + plates[0]
                )
                expect(
                    page.get_by_text("The linked source is unavailable", exact=False)
                ).to_be_visible()
                expect(
                    page.get_by_label("Source material").locator(
                        f'option[value="physical:{plates[0]}"]'
                    )
                ).to_have_count(0)
                expect(
                    page.get_by_role("button", name="Create Agar plate", exact=True)
                ).to_be_disabled()
                page.goto(base + "/cultivation")
                expect(
                    page.get_by_role("link", name="B-01 · Spawn bag", exact=True)
                ).to_be_visible()
                page.get_by_label("Show records").select_option("spawn_jar")
                expect(
                    page.get_by_role("link", name="J-01 · Spawn jar", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="B-01 · Spawn bag", exact=True)
                ).to_have_count(0)
                page.goto(base + "/culture-library/physical/" + plates[0])
                page.get_by_role(
                    "button", name="Preparation & Transfer History", exact=True
                ).click()
                expect(
                    page.get_by_role(
                        "heading", name="Recipe: Standard Agar", exact=True
                    )
                ).to_be_visible()
                # Everyday identities are physical labels; all links still use permanent IDs.
                expect(page.get_by_role("heading", level=1)).to_contain_text("P-01")
                expect(
                    page.get_by_role("button", name="Mark Ready", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_text("Current Status: Germinating", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_label("Lifecycle action", exact=False)
                ).to_have_count(0)
                expect(
                    page.get_by_role(
                        "button", name="Complete / Retire Container", exact=True
                    )
                ).to_have_count(0)
                page.get_by_role("button", name="Mark Ready", exact=True).click()
                page.get_by_label("Lifecycle date", exact=True).fill("2026-11-02")
                page.get_by_role("button", name="Save Status", exact=True).click()
                expect(
                    page.get_by_text("Ready date: 2026-11-02", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_text("Current Status: Ready", exact=True)
                ).to_be_visible()
                page.goto(base + "/laboratory")
                plate_row = page.locator(".record-list > li").filter(
                    has=page.get_by_role("link", name="P-01 · Agar plate", exact=True)
                )
                expect(
                    plate_row.get_by_text("Current Status: Ready", exact=True)
                ).to_be_visible()
                for operation_slug in ("agar-plate", "lc-container", "spawn"):
                    page.goto(
                        base
                        + f"/quick-create/{operation_slug}?source_kind=physical&source_id="
                        + plates[0]
                    )
                    expect(
                        page.get_by_label("Source material", exact=True)
                    ).to_have_value("physical:" + plates[0])
                    expect(
                        page.get_by_text("Current Status: Ready", exact=False)
                    ).to_be_visible()
                donor_jars = direct("spawn", grain["id"], 5, source_code=plates[0])
                donor = page.request.get(
                    base + "/api/library/physical/" + plates[0]
                ).json()
                assert donor["lifecycle"] == "used" and not donor["label_occupied"]
                for code in donor_jars:
                    row = page.request.get(base + "/api/library/spawn/" + code).json()
                    assert row["growth_stage"] == "colonizing"
                    assert (
                        page.request.get(
                            base + "/api/preparation/materials/" + code
                        ).json()["source"]["id"]
                        == plates[0]
                    )
                reused = direct("agar-plate", agar["id"], 1, "1")[0]
                assert reused != plates[0]
                assert (
                    page.request.get(base + "/api/library/physical/" + reused).json()[
                        "physical_label"
                    ]
                    == "P-01"
                )
                for code in (reused, plates[1]):
                    page.goto(base + "/culture-library/physical/" + code)
                    page.get_by_role("button", name="Mark Failed", exact=True).click()
                    # Reasons are optional for operational failure.
                    page.get_by_role("button", name="Save Status", exact=True).click()
                    expect(
                        page.get_by_role("button", name="Mark Failed", exact=True)
                    ).to_have_count(0)
                manual = direct(
                    "agar-plate", agar["id"], 1, "1", physical_label="P-02"
                )[0]
                assert (
                    page.request.get(base + "/api/library/physical/" + manual).json()[
                        "physical_label"
                    ]
                    == "P-02"
                )
                page.goto(base + "/culture-library/physical/" + plates[0])
                page.get_by_role(
                    "button", name="Preparation & Transfer History", exact=True
                ).click()
                expect(
                    page.get_by_role("button", name="Mark Ready", exact=True)
                ).to_have_count(0)
                expect(page.get_by_text("Used date:", exact=False)).to_be_visible()
                expect(
                    page.get_by_text("Current Status: Used", exact=True)
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
                # Inventory is absent; outside material has a dedicated workspace.
                page.goto(base + "/acquisitions")
                expect(
                    page.get_by_role("link", name="Receive Acquisition", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="Inventory", exact=True)
                ).to_have_count(0)
                expect(
                    page.get_by_role("button", name="+ Add Inventory", exact=True)
                ).to_have_count(0)
                page.goto(base + "/culture-library")
                expect(
                    page.get_by_role("link", name="Add Strain", exact=True)
                ).to_be_visible()
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
                raw = operation(
                    "stock",
                    {
                        "name": "Historical ingredient",
                        "category": "ingredient",
                        "unit": "g",
                        "available": "100",
                        "reason": "Existing test history",
                    },
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
                page.goto(base + "/history/materials/inoculate")
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
                # Unrecorded legacy/acquired readiness stays unknown until explicit action.
                legacy = post(
                    "/api/library/receive-culture",
                    {"line": {}, "material": {"material_type": "agar_plate"}},
                )["physical"][0]
                page.goto(base + "/culture-library/physical/" + legacy["id"])
                expect(
                    page.get_by_text(
                        "Current Status: Readiness not recorded", exact=True
                    )
                ).to_be_visible()
                expect(page.get_by_text("Ready date:", exact=False)).to_have_count(0)
                page.get_by_role("button", name="Mark Ready", exact=True).click()
                page.get_by_role("button", name="Save Status", exact=True).click()
                expect(
                    page.get_by_text("Current Status: Ready", exact=True)
                ).to_be_visible()
                page.goto(
                    base
                    + "/quick-create/agar-plate?source_kind=physical&source_id="
                    + legacy["id"]
                )
                # The earlier agar recipe is archived; make a fresh active definition.
                stale_recipe = operation(
                    "recipes",
                    {
                        "name": "Readiness check agar",
                        "recipe_type": "agar",
                        "batch_yield": 1,
                        "ingredients": [{"name": "Agar", "quantity": "1", "unit": "g"}],
                    },
                )
                page.reload()
                page.locator("#recipe_id").select_option(stale_recipe["id"])
                expect(page.get_by_label("Source material", exact=True)).to_have_value(
                    "physical:" + legacy["id"]
                )
                response = page.request.post(
                    base + f"/api/containers/records/physical/{legacy['id']}/state",
                    data={"request_key": str(uuid4()), "action": "failed"},
                )
                assert response.status == 200, response.text()
                creation_writes = []
                page.on(
                    "request",
                    lambda request: (
                        creation_writes.append(request.url)
                        if request.method == "POST"
                        and request.url.endswith("/api/preparation/create")
                        else None
                    ),
                )
                page.get_by_role("button", name="Create Agar plate", exact=True).click()
                expect(
                    page.get_by_text(
                        "This agar source is no longer eligible", exact=False
                    )
                ).to_be_visible()
                assert creation_writes == [], creation_writes
                page.goto(base + "/culture-library/physical/" + legacy["id"])
                expect(
                    page.get_by_text("Current Status: Failed", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Released", exact=False)).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                for path in (
                    "/recipes",
                    "/recipes/spawn-seed",
                    "/laboratory",
                    "/cultivation",
                    "/acquisitions",
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
                    "Final 2C.2 workflow browser smoke passed: four recipe categories and default LC Media, duplicate/delete/archive, direct agar/spawn/LC/syringe creation, physical labels, copy/manual override/reuse, Ready agar atomic bulk consumption, permanent IDs, lineage, LC balance, growing views, Acquisitions and no Inventory workspace, LC Create From This, historical prepared inoculation, desktop/mobile; no page errors"
                )

        finally:
            process.terminate()
            process.wait(timeout=10)
