"""Optional Playwright/Chromium acceptance using an isolated temporary workspace."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="cultivatinator-experiments-") as tmp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {
            **os.environ,
            "CULTIVATINATOR_DATA_DIR": str(Path(tmp) / "data"),
            "CULTIVATINATOR_FRONTEND_DIR": str(ROOT / "frontend/dist"),
        }
        log = open(Path(tmp) / "app.log", "w+")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "backend",
            env=environment,
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    if urlopen(base + "/api/health", timeout=1).status == 200:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                log.seek(0)
                raise RuntimeError(log.read())
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=(
                        sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium"
                    ),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    timezone_id="America/New_York",
                )
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on(
                    "response",
                    lambda r: (
                        print(r.status, r.url, r.text()[:1000], flush=True)
                        if r.status >= 400
                        else None
                    ),
                )
                from uuid import uuid4

                def post(path, **body):
                    response = page.request.post(
                        base + "/api/" + path,
                        data={"request_key": str(uuid4()), **body},
                    )
                    assert response.ok, response.text()
                    return response.json()

                strain = page.request.post(
                    base + "/api/provenance/acquisitions",
                    data={
                        "entry_type": "spawn_jar",
                        "stage": "ready",
                        "inline_strain": {"name": "Browser Oyster"},
                        "line": {},
                    },
                )
                assert strain.ok, strain.text()
                first = strain.json()["records"][0]
                line = first["line_id"]

                def new_spawn():
                    response = page.request.post(
                        base + "/api/provenance/acquisitions",
                        data={
                            "entry_type": "spawn_jar",
                            "stage": "ready",
                            "existing_line_id": line,
                            "strain_id": page.request.get(
                                base + "/api/library/lines/" + line
                            ).json()["strain_id"],
                        },
                    )
                    assert response.ok, response.text()
                    return response.json()["records"][0]

                a = post(
                    "preparation/recipes",
                    name="Browser substrate A",
                    recipe_type="substrate",
                    batch_yield=1,
                    ingredients=[
                        {"name": "Substrate A", "quantity": "100", "unit": "g"}
                    ],
                )
                b = post(
                    "preparation/recipes",
                    name="Browser substrate B",
                    recipe_type="substrate",
                    batch_yield=1,
                    ingredients=[
                        {"name": "Substrate B", "quantity": "100", "unit": "g"}
                    ],
                )
                old = post(
                    "fruiting/create",
                    spawn_id=first["id"],
                    recipe_id=a["id"],
                    count=1,
                    spawning_date="2025-01-01",
                )["containers"][0]
                ready = new_spawn()
                experiment = post(
                    "experiments",
                    plan={
                        "title": "Enrollment browser trial",
                        "category": "substrate",
                        "primary_variable": "Substrate formulation",
                        "primary_outcome": "completed_wet_yield",
                        "groups": [
                            {"name": "Control", "treatment": "A", "control": True},
                            {"name": "Comparison", "treatment": "B"},
                        ],
                    },
                )
                page.goto(base + "/experiments/" + experiment["id"])
                page.get_by_label("Action reason", exact=True).fill(
                    "Ready for participants"
                )
                page.get_by_role("button", name="Commit plan", exact=True).click()
                expect(
                    page.get_by_role("button", name="Link container", exact=True)
                ).to_be_visible()
                page.get_by_label("Fruiting container", exact=False).select_option(
                    old["id"]
                )
                page.get_by_role("button", name="Link container", exact=True).click()
                expect(
                    page.get_by_role("link", name=old["id"], exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Create new", exact=True).click()
                page.get_by_label("Ready spawn source", exact=False).select_option(
                    ready["id"]
                )
                page.get_by_label(
                    "Substrate recipe for group 1", exact=False
                ).select_option(a["id"])
                page.get_by_label(
                    "Substrate recipe for group 2", exact=False
                ).select_option(b["id"])
                page.get_by_role(
                    "button", name="Save assignments before treatment", exact=True
                ).click()
                expect(
                    page.get_by_text("Assignments saved as", exact=False)
                ).to_be_visible()
                page.get_by_text("Exact treatment time (optional)", exact=True).click()
                current_local = page.evaluate(
                    "() => {const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,23)}"
                )
                page.get_by_label(
                    "Actual treatment start (local time)", exact=True
                ).fill(current_local)
                page.get_by_role(
                    "button", name="Create assigned containers", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "3 containers · 3 assigned treatment units · 2 known spawn sources.",
                        exact=True,
                    )
                ).to_be_visible()
                expect(
                    page.get_by_text("Membership classification: mixed", exact=True)
                ).to_be_visible()
                detail = page.request.get(
                    base + "/api/experiments/" + experiment["id"] + "/participants"
                ).json()
                assert detail["counts"]["classification_counts"]["prospective"] == 2
                last = detail["items"][-1]
                page.get_by_text("Review " + last["fruiting_id"], exact=True).click()
                form = page.get_by_text(
                    "Review " + last["fruiting_id"], exact=True
                ).locator("..")
                form.get_by_label("Review decision", exact=False).select_option(
                    "exclude"
                )
                form.get_by_label("Review reason", exact=True).fill(
                    "Exclude from this comparison"
                )
                form.get_by_role("button", name="Save review", exact=True).click()
                expect(
                    page.get_by_text(
                        "2 containers · 2 assigned treatment units · 2 known spawn sources.",
                        exact=True,
                    )
                ).to_be_visible()
                page.get_by_role(
                    "button", name="Enrollment history", exact=True
                ).click()
                expect(page.get_by_text("review exclude", exact=False)).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                page.emulate_media(reduced_motion="reduce")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), "Mobile overflow"
                assert not errors, errors
                browser.close()
                print(
                    "Enrollment browser acceptance passed: existing records, precommitted multi-recipe creation, mixed classifications, shared sources, reviewed exclusions/history and mobile."
                )
        finally:
            process.terminate()
            process.wait(timeout=15)
            log.close()


if __name__ == "__main__":
    main()
