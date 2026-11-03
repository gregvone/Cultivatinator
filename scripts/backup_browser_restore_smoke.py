"""Real browser → signed Unix helper → Compose restore, using disposable data only.
Build cultivatinator:milestone-2d2 first. Requires optional Playwright/Chromium,
local Docker/Compose, and python:3.12-slim-bookworm. Never targets Debian.
"""

from pathlib import Path
from uuid import uuid4
from io import BytesIO
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
ENV = {
    key: value
    for key, value in os.environ.items()
    if key
    not in {
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    }
}
image = os.environ.get("CULTIVATINATOR_TEST_IMAGE", "cultivatinator:milestone-2d2")
temp = Path(tempfile.mkdtemp(prefix="cultivatinator-browser-restore-"))
root = temp / "installation"
runtime = temp / "runtime"
state = temp / "helper-state"
for directory in [root, runtime, state]:
    directory.mkdir()
project = "cultivatinator-browser-" + uuid4().hex[:10]
helper_name = project + "-helper"
with socket.socket() as socket_probe:
    socket_probe.bind(("127.0.0.1", 0))
    port = socket_probe.getsockname()[1]
base = f"http://127.0.0.1:{port}"
compose = root / "compose.yaml"
compose.write_text(
    f"""name: {project}
services:
  app:
    image: {image}
    restart: unless-stopped
    ports: ["127.0.0.1:{port}:8085"]
    volumes: ["{root}:/data", "{runtime}:/run/cultivatinator-maintenance:ro"]
"""
)
(root / ".git").mkdir()
(root / ".git/HEAD").write_text("UNCHANGED GIT")
(root / ".env").write_text("UNCHANGED CONFIG")
(root / "README.md").write_text("UNCHANGED SOURCE")
sentinels = {
    p: p.read_bytes()
    for p in [compose, root / ".git/HEAD", root / ".env", root / "README.md"]
}


def docker(*args):
    return subprocess.check_output(
        [*DOCKER, *map(str, args)], env=ENV, text=True, stderr=subprocess.STDOUT
    ).strip()


def root_command(code):
    return docker(
        "run",
        "--rm",
        "--user",
        "0:0",
        "--mount",
        f"type=bind,src={temp},dst={temp}",
        "python:3.12-slim-bookworm",
        "python",
        "-c",
        code,
    )


# Test-only fault injection lives outside the app mount and administrative API.
launcher = temp / "helper-test-runner.py"
launcher.write_text(
    f"""
from pathlib import Path
import os,subprocess,sys
installed=Path('/opt/helper-installed')
if not installed.exists():
    Path('/etc/systemd/system').mkdir(parents=True,exist_ok=True)
    stub=Path('/usr/local/bin/systemctl');stub.write_text('#!/bin/sh\\nexit 0\\n');stub.chmod(0o700)
    subprocess.run([sys.executable,'/repo/scripts/install_backup_helper.py','install','--data-root',{str(root)!r},'--compose-file',{str(compose)!r}],check=True)
    installed.touch()
sys.path.insert(0,'/opt/cultivatinator-maintenance/backend')
import app.maintenance_service as service
import app.restore_workspace as engine
from app.backup_format import BackupError
state=Path('/var/lib/cultivatinator-maintenance')
original_controller=service.MaintenanceService.controller
def controller(self):
    result=original_controller(self)
    real_health=result.health
    def health():
        marker=state/'fail-next-health'
        if marker.exists():
            marker.unlink();raise BackupError('Injected disposable startup-health failure')
        return real_health()
    result.health=health
    return result
service.MaintenanceService.controller=controller
real_move=engine.move
def move(source,target):
    real_move(source,target)
    marker=state/'interrupt-next-cutover'
    if marker.exists() and source.name=='database' and target.parent.name=='original':
        marker.unlink();os._exit(86)
engine.move=move
sys.argv=['helper','--config','/etc/cultivatinator-maintenance/config.json']
service.main()
"""
)

try:
    root_command(
        f"import os;os.chown({str(root)!r},10001,10001);os.chmod({str(root)!r},0o755);os.chown({str(runtime)!r},0,10001);os.chmod({str(runtime)!r},0o750)"
    )
    docker("compose", "-f", compose, "up", "-d")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1440, "height": 1100}
        )
        page = context.new_page()
        # Chrome on an HTTP LAN origin exposes getRandomValues but not randomUUID.
        page.add_init_script(
            "Object.defineProperty(Crypto.prototype, 'randomUUID', {value: undefined, configurable: true})"
        )
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for _ in range(150):
            try:
                if context.request.get(base + "/api/health").ok:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Disposable application did not start")
        # Launch the installed root-owned host code in a root controller container;
        # only systemctl is stubbed because this disposable container has no init.
        docker(
            "run",
            "-d",
            "--name",
            helper_name,
            "--restart",
            "unless-stopped",
            "--user",
            "0:0",
            "--network",
            "host",
            "--pid",
            "host",
            "--cap-add",
            "SYS_PTRACE",
            "--mount",
            f"type=bind,src={temp},dst={temp}",
            "--mount",
            f"type=bind,src={ROOT},dst=/repo,readonly",
            "--mount",
            f"type=bind,src={runtime},dst=/run/cultivatinator-maintenance",
            "--mount",
            f"type=bind,src={state},dst=/var/lib/cultivatinator-maintenance",
            "--mount",
            "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
            "--mount",
            "type=bind,src=/usr/local/bin/docker,dst=/usr/local/bin/docker,readonly",
            "--mount",
            "type=bind,src=/usr/libexec/docker/cli-plugins/docker-compose,dst=/usr/libexec/docker/cli-plugins/docker-compose,readonly",
            "python:3.12-slim-bookworm",
            "python",
            "-u",
            str(launcher),
        )
        for _ in range(100):
            if (
                context.request.get(base + "/api/backups/admin/session")
                .json()
                .get("available")
            ):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError(
                "Disposable helper failed: " + docker("logs", helper_name)
            )
        logs = docker("logs", helper_name)
        bootstrap = re.search(
            r"One-time browser setup code \(store privately until used\): (\S+)", logs
        ).group(1)
        page.goto(base + "/settings")
        assert page.evaluate("typeof crypto.randomUUID") == "undefined"
        assert page.evaluate("typeof crypto.getRandomValues") == "function"
        page.get_by_label("One-time setup code", exact=True).fill(bootstrap)
        page.get_by_label("Administrator passphrase", exact=True).fill(
            "Disposable browser backup password"
        )
        page.get_by_role(
            "button", name="Set Administrator Passphrase", exact=True
        ).click()
        expect(
            page.get_by_role("button", name="Create Backup", exact=True)
        ).to_be_visible()
        expect(page.get_by_label("Time zone", exact=True)).to_have_value(
            "America/New_York"
        )
        guest = playwright.request.new_context()
        assert guest.get(base + "/api/backups/download").status == 401
        assert guest.post(base + "/api/backups/create", data={}).status == 401
        guest.dispose()

        def post(path, data):
            response = context.request.post(base + path, data=data)
            assert response.ok, response.text()
            return response.json()

        def command(path, data):
            return post(path, {"request_key": str(uuid4()), **data})

        source = post(
            "/api/provenance/acquisitions",
            {
                "entry_type": "spawn_bag",
                "line": {},
                "inline_strain": {"name": "Snapshot Oyster"},
            },
        )
        recipe = command(
            "/api/preparation/recipes",
            {
                "name": "Snapshot substrate",
                "recipe_type": "substrate",
                "batch_yield": 1,
                "ingredients": [{"name": "Hardwood", "quantity": "1000", "unit": "g"}],
            },
        )
        fruit = command(
            "/api/fruiting/create",
            {
                "spawn_id": source["records"][0]["id"],
                "recipe_id": recipe["id"],
                "count": 2,
                "spawning_date": "2026-01-01",
            },
        )["containers"][0]["id"]
        command(
            f"/api/fruiting/records/{fruit}/stage",
            {"action": "pinning", "action_date": "2026-01-03"},
        )
        png = BytesIO()
        Image.new("RGB", (30, 30), "#667799").save(png, "PNG")
        photo = context.request.post(
            base + f"/api/fruiting/records/{fruit}/flushes/1/pinning/photos",
            multipart={
                "file": {
                    "name": "pinning.png",
                    "mimeType": "image/png",
                    "buffer": png.getvalue(),
                }
            },
        ).json()
        root_command(
            f"from pathlib import Path;import os;r=Path({str(root)!r});(r/'files/retained.txt').write_text('Snapshot A');(r/'settings/retained.json').write_text('{{\"snapshot\":\"A\"}}');[os.chown(r/p,10001,10001) for p in ['files/retained.txt','settings/retained.json']]"
        )
        page.route(
            "**/api/backups/create",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"detail":"Injected disposable disk failure"}',
            ),
            times=1,
        )
        page.get_by_role("button", name="Create Backup", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("disk failure")
        with page.expect_download() as pending_download:
            page.get_by_role("button", name="Create Backup", exact=True).click()
        archive = temp / "browser-download.zip"
        pending_download.value.save_as(archive)
        assert pending_download.value.failure() is None
        expect(
            page.get_by_text(
                "does not confirm that the file was saved externally", exact=False
            )
        ).to_be_visible()
        rows = page.locator(".backup-entry")
        expect(rows).to_have_count(1)
        csrf = context.request.get(base + "/api/backups/admin/session").json()["csrf"]
        saved = context.request.get(base + "/api/backups/catalog").json()["backups"][0]
        stored = context.request.get(
            base + f"/api/backups/catalog/{saved['id']}/download"
        )
        assert stored.body() == archive.read_bytes()
        # CLI remains standard-library-only in a container without app dependencies.
        verification = docker(
            "exec",
            helper_name,
            "python",
            "-I",
            "/opt/cultivatinator-maintenance/scripts/workspace_backup.py",
            "verify",
            archive,
        )
        assert "VALID:" in verification and "0013_journal_photos" in verification
        rows.get_by_role("button", name="Verify", exact=True).click()
        expect(page.get_by_text("Stored backup verified.", exact=True)).to_be_visible()

        def mutate_current(name):
            post("/api/library/strains", {"name": name})

        def start_stored_restore():
            rows.get_by_role("button", name="Restore", exact=True).click()
            confirmation = page.get_by_role(
                "region", name="Confirm cultivation restore"
            )
            expect(confirmation).to_be_visible()
            expect(
                page.get_by_role(
                    "button", name="Restore and Replace Current Data", exact=True
                )
            ).to_be_disabled()
            page.get_by_role(
                "checkbox",
                name="I understand that current cultivation data will be replaced.",
                exact=True,
            ).check()
            with page.expect_response("**/api/backups/restore/confirm") as accepted:
                page.get_by_role(
                    "button", name="Restore and Replace Current Data", exact=True
                ).click()
            assert accepted.value.ok, accepted.value.text()
            return accepted.value.json()["id"]

        def outcome(label, expected_id):
            for _ in range(200):
                try:
                    result = context.request.get(
                        base + "/api/backups/restore/status"
                    ).json()["operation"]
                    if result["id"] == expected_id and result["status"] in {
                        "complete",
                        "rolled_back",
                        "failed",
                        "recovery_required",
                    }:
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            expect(
                page.get_by_role("heading", name="Restore: " + label, exact=True)
            ).to_be_visible(timeout=120000)
            return context.request.get(base + "/api/backups/restore/status").json()[
                "operation"
            ]

        mutate_current("After snapshot")
        before_started = json.loads(
            docker("inspect", docker("compose", "-f", compose, "ps", "-q", "app"))
        )[0]["State"]["StartedAt"]
        request_id = start_stored_restore()
        operation = outcome("Complete", request_id)
        assert operation["status"] == "complete"
        assert len(context.request.get(base + "/api/library/strains").json()) == 1
        after_started = json.loads(
            docker("inspect", docker("compose", "-f", compose, "ps", "-q", "app"))
        )[0]["State"]["StartedAt"]
        assert before_started != after_started
        assert (
            len(context.request.get(base + "/api/backups/catalog").json()["backups"])
            == 1
        )
        assert context.request.get(base + photo["url"]).body() == png.getvalue()
        assert context.request.get(base + photo["thumbnail_url"]).ok
        root_command(
            f"from pathlib import Path;r=Path({str(root)!r});assert (r/'files/retained.txt').read_text()=='Snapshot A';assert (r/'settings/retained.json').read_text()=='{{\"snapshot\":\"A\"}}';assert (Path({operation['recovery_operation']!r})/'pre-restore.zip').is_file()"
        )
        for file, content in sentinels.items():
            assert file.read_bytes() == content
        # Upload route uses the same preview/confirmation/restore engine and does
        # not retain a second catalog entry unless explicitly requested.
        mutate_current("After first restore")
        page.get_by_role("button", name="Restore from ZIP", exact=False).click()
        page.get_by_label("Backup ZIP", exact=True).set_input_files(archive)
        page.get_by_role("button", name="Upload and Verify ZIP", exact=True).click()
        expect(page.get_by_text("Uploaded ZIP", exact=True)).to_be_visible(
            timeout=30000
        )
        page.get_by_role(
            "checkbox",
            name="I understand that current cultivation data will be replaced.",
            exact=True,
        ).check()
        with page.expect_response("**/api/backups/restore/confirm") as accepted:
            page.get_by_role(
                "button", name="Restore and Replace Current Data", exact=True
            ).click()
        outcome("Complete", accepted.value.json()["id"])
        assert len(context.request.get(base + "/api/library/strains").json()) == 1
        assert (
            len(context.request.get(base + "/api/backups/catalog").json()["backups"])
            == 1
        )

        # Real failed startup rolls back original current data and reconnects.
        mutate_current("Retain on rollback")
        docker(
            "exec",
            helper_name,
            "touch",
            "/var/lib/cultivatinator-maintenance/fail-next-health",
        )
        request_id = start_stored_restore()
        rolled_back = outcome("Rolled back", request_id)
        assert rolled_back["status"] == "rolled_back"
        assert len(context.request.get(base + "/api/library/strains").json()) == 2
        # Abrupt helper termination after moving database/ is recovered by the
        # restarted helper, then the same browser obtains the authoritative result.
        previous_id = rolled_back["id"]
        docker(
            "exec",
            helper_name,
            "touch",
            "/var/lib/cultivatinator-maintenance/interrupt-next-cutover",
        )
        request_id = start_stored_restore()
        for _ in range(150):
            try:
                result = context.request.get(
                    base + "/api/backups/restore/status"
                ).json()["operation"]
                if result["id"] != previous_id and result["status"] == "rolled_back":
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise AssertionError("Interrupted helper did not recover the application")
        outcome("Rolled back", request_id)
        assert len(context.request.get(base + "/api/library/strains").json()) == 2
        assert not (root / ".cultivatinator-restore-in-progress.json").exists()
        assert json.loads(docker("inspect", helper_name))[0]["RestartCount"] >= 1
        app_info = json.loads(
            docker("inspect", docker("compose", "-f", compose, "ps", "-q", "app"))
        )[0]
        assert app_info["Config"]["User"] == "10001:10001"
        assert not any(
            m["Destination"] == "/var/run/docker.sock" for m in app_info["Mounts"]
        )
        assert (
            len(context.request.get(base + "/api/backups/catalog").json()["backups"])
            == 1
        )
        for width in [390, 768]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert (
                page.get_by_role(
                    "button", name="Create Backup", exact=True
                ).bounding_box()["height"]
                >= 44
            )
        page.screenshot(
            path="/tmp/cultivatinator-browser-backup-restore.png", full_page=True
        )
        rows.get_by_role("button", name="Delete", exact=True).click()
        expect(
            page.get_by_role("button", name="Confirm Delete Backup", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Keep Backup", exact=True).click()
        expect(rows).to_have_count(1)
        assert not errors, errors
        browser.close()
    print(
        "Browser restore smoke passed: installed root-owned helper, setup/session/CSRF, all download validation, same-artifact save/download, stored and uploaded restore, real stop/restart/reconnect, retained archive/history/photographs, rollback, abrupt helper restart recovery, source/config sentinels, isolated socket/no app Docker socket, phone/tablet and no page errors"
    )
finally:
    for command in [("rm", "-f", helper_name), ("compose", "-f", compose, "down")]:
        try:
            docker(*command)
        except subprocess.SubprocessError:
            pass
    try:
        root_command(
            f"import os;from pathlib import Path;r=Path({str(temp)!r});[(os.chown(p,{os.getuid()},{os.getgid()}),os.chmod(p,0o700 if p.is_dir() else 0o600)) for p in [r,*r.rglob('*')] if not p.is_symlink()]"
        )
        shutil.rmtree(temp)
    except Exception:
        print("Disposable test files retained for inspection at", temp)
