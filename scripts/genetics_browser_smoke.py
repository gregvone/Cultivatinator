"""Genetics acceptance on a disposable local database; build frontend first.
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
with tempfile.TemporaryDirectory(prefix="cultivatinator-genetics-browser-") as temp:
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

                page.goto(base + "/genetics")
                expect(
                    page.get_by_text("No culture lines in this family.", exact=False)
                ).to_be_visible()
                root = post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_jar",
                        "line": {"name": "Original Oyster"},
                        "inline_strain": {"name": "Oyster"},
                    },
                )
                child = post(
                    f"/api/provenance/lines/{root['line']['id']}/establish",
                    {"name": "First isolate"},
                )["line"]
                post(
                    "/api/provenance/acquisitions",
                    {
                        "entry_type": "spawn_jar",
                        "line": {"name": "Independent Oyster"},
                        "strain_id": root["line"]["strain_id"],
                    },
                )
                post(
                    "/api/provenance/acquisitions",
                    {"entry_type": "spawn_jar", "line": {"name": "Unknown source"}},
                )
                grow = post(
                    "/api/provenance/grows",
                    {
                        "source_ids": [root["records"][0]["id"]],
                        "allocation_mode": "shared",
                        "containers": [{}],
                    },
                )
                clone = post(
                    f"/api/provenance/fruiting/{grow['containers'][0]['id']}/establish",
                    {"name": "Recorded clone"},
                )["line"]
                post(f"/api/library/lines/{child['id']}/status", {"status": "archived"})
                from io import BytesIO
                from PIL import Image

                image = BytesIO()
                Image.new("RGB", (80, 60), "olive").save(image, "PNG")
                upload = page.request.post(
                    base + f"/api/library/lines/{root['line']['id']}/photos",
                    multipart={
                        "file": {
                            "name": "culture.png",
                            "mimeType": "image/png",
                            "buffer": image.getvalue(),
                        }
                    },
                )
                assert upload.status == 201, upload.text()
                page.reload()
                root_node = page.get_by_role(
                    "button",
                    name="Original Oyster · " + root["line"]["id"],
                    exact=False,
                )
                expect(root_node).to_be_visible()
                assert root_node.locator("img").evaluate(
                    "(el)=>el.complete && el.naturalWidth > 0"
                )
                root_node.click()
                detail = page.get_by_role("complementary")
                expect(
                    detail.get_by_role("heading", name="Original Oyster", exact=True)
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Collapse descendants", exact=True
                ).click()
                expect(
                    page.get_by_role(
                        "button", name="First isolate · " + child["id"], exact=False
                    )
                ).to_have_count(0)
                page.get_by_role("button", name="Expand All").click()
                page.get_by_role("button", name="Reset View").click()
                page.get_by_role("button", name="Zoom Out").click()
                expect(page.locator(".genetic-world")).to_have_class(
                    "genetic-world close"
                )
                page.get_by_role("button", name="Zoom Out").click()
                expect(page.locator(".genetic-world")).to_have_class(
                    "genetic-world medium"
                )
                for _ in range(4):
                    page.get_by_role("button", name="Zoom Out").click()
                expect(page.locator(".genetic-world")).to_have_class(
                    "genetic-world far"
                )
                page.get_by_role("button", name="Fit to Screen").click()
                detail.get_by_role("button", name="Create Isolate", exact=True).click()
                detail.get_by_label("Optional name", exact=True).fill("Browser isolate")
                detail.get_by_role("button", name="Save", exact=True).click()
                expect(
                    detail.get_by_role("heading", name="Browser isolate", exact=True)
                ).to_be_visible()
                # New line is selected without leaving the tree; it has no invented clone source.
                expect(
                    detail.get_by_role(
                        "button", name="Establish Tissue Clone", exact=True
                    )
                ).to_have_count(0)
                page.get_by_role("searchbox").fill("Original Oyster")
                page.locator(".genetic-results button").click()
                detail.get_by_role("combobox").select_option(
                    grow["containers"][0]["id"]
                )
                detail.get_by_role(
                    "button", name="Establish Tissue Clone", exact=True
                ).click()
                detail.get_by_label("Optional name", exact=True).fill("Browser clone")
                detail.get_by_role("button", name="Save", exact=True).click()
                expect(
                    detail.get_by_role("heading", name="Browser clone", exact=True)
                ).to_be_visible()
                saved = next(
                    n
                    for n in get("/api/genetics")["nodes"]
                    if n["name"] == "Browser clone"
                )
                assert (
                    saved["origin_type"] == "clone"
                    and saved["source"]["id"] == grow["containers"][0]["id"]
                )
                page.screenshot(
                    path="/tmp/cultivatinator-genetics-desktop.png", full_page=True
                )
                page.get_by_role("button", name="Magic Kingdom", exact=True).click()
                page.get_by_role("searchbox").fill("Unknown source")
                page.locator(".genetic-results button").click()
                detail.get_by_role(
                    "button", name="Focus on This Family", exact=True
                ).click()
                expect(page.get_by_role("combobox").first).to_have_value("unknown")
                # Pan and wheel zoom retain selected-node context.
                tree = page.locator(".genetic-canvas")
                world = page.locator(".genetic-world")
                box = tree.bounding_box()
                before = world.get_attribute("style")
                page.mouse.move(box["x"] + 10, box["y"] + 10)
                page.mouse.down()
                page.mouse.move(box["x"] + 55, box["y"] + 45, steps=5)
                page.mouse.up()
                assert world.get_attribute("style") != before
                before = world.get_attribute("style")
                page.mouse.wheel(0, -120)
                page.wait_for_timeout(100)
                assert world.get_attribute("style") != before
                # Keyboard alternative and reduced-motion mobile layout.
                page.emulate_media(reduced_motion="reduce")
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_text("Accessible relationship list", exact=False).click()
                page.locator(".genetic-list button").first.focus()
                page.keyboard.press("Enter")
                expect(
                    detail.get_by_role("heading", name="Unknown source", exact=True)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile page overflow"
                page.screenshot(
                    path="/tmp/cultivatinator-genetics-mobile.png", full_page=True
                )
                tree.scroll_into_view_if_needed()
                box = tree.bounding_box()
                before = world.get_attribute("style")
                cdp = page.context.new_cdp_session(page)
                points = [{"x": box["x"] + 50, "y": box["y"] + 80, "id": 1}]
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {"type": "touchStart", "touchPoints": points},
                )
                points[0]["x"] += 40
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {"type": "touchMove", "touchPoints": points},
                )
                cdp.send(
                    "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
                )
                assert world.get_attribute("style") != before
                assert not errors, errors
                browser.close()
                print(
                    "Genetics browser smoke passed: roots, photos, archive, collapse, zoom, isolate refresh, kingdom, search, focus, keyboard, mobile and reduced motion"
                )
        finally:
            process.terminate()
            process.wait(timeout=15)
