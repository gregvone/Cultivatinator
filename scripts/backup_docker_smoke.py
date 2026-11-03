"""Exercise the real host maintenance CLI against a disposable Compose installation.
Run: .venv/bin/python scripts/backup_docker_smoke.py cultivatinator:milestone-2d2
Uses a root test controller with host PID/network access solely to emulate sudo,
inspect database descriptors and reach the local test app. Never targets Debian.
"""

from io import BytesIO
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
image = sys.argv[1] if len(sys.argv) > 1 else "cultivatinator:milestone-2d2"
temp = Path(tempfile.mkdtemp(prefix="cultivatinator-backup-compose-"))
root = temp / "installation"
root.mkdir()
project = "cultivatinator-backup-" + uuid4().hex[:10]
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
base = f"http://127.0.0.1:{port}"
compose = root / "compose.yaml"
compose.write_text(
    f"""name: {project}
services:
  app:
    image: {image}
    restart: unless-stopped
    ports: ["127.0.0.1:{port}:8085"]
    volumes: ["{root}:/data"]
"""
)
(root / ".git").mkdir()
(root / ".git/HEAD").write_text("ref: refs/heads/main\n")
(root / "README.md").write_text("UNRELATED CHECKOUT MUST REMAIN")
(root / ".env").write_text("SENTINEL=source-not-backed-up\n")
sentinels = {
    p: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [compose, root / ".git/HEAD", root / "README.md", root / ".env"]
}


def docker(*args):
    try:
        return subprocess.check_output(
            [*DOCKER, *args], text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        raise


def helper(code):
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


def controller_run(arguments):
    return docker(
        "run",
        "--rm",
        "--user",
        "0:0",
        "--network",
        "host",
        "--pid",
        "host",
        "--cap-add",
        "SYS_PTRACE",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "--mount",
        f"type=bind,src={temp},dst={temp}",
        "--mount",
        f"type=bind,src={ROOT},dst=/repo,readonly",
        "--mount",
        "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
        "--mount",
        "type=bind,src=/usr/local/bin/docker,dst=/usr/local/bin/docker,readonly",
        "--mount",
        "type=bind,src=/usr/libexec/docker/cli-plugins/docker-compose,dst=/usr/libexec/docker/cli-plugins/docker-compose,readonly",
        "python:3.12-slim-bookworm",
        "python",
        *map(str, arguments),
    )


def controller(*args):
    return controller_run(["/repo/scripts/workspace_backup.py", *args])


def get(path):
    with urllib.request.urlopen(base + path, timeout=120) as r:
        return json.load(r)


def post(path, data):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def command(path, data):
    return post(path, {"request_key": str(uuid4()), **data})


def attach(path):
    png = BytesIO()
    Image.new("RGB", (30, 30), "#667799").save(png, format="PNG")
    boundary = uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="original.png"\r\nContent-Type: image/png\r\n\r\n'
        ).encode()
        + png.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        base + path,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r), png.getvalue()


try:
    helper(
        f"import os;os.chown({str(root)!r},10001,10001);os.chmod({str(root)!r},0o755)"
    )
    docker("compose", "-f", str(compose), "up", "-d")
    for _ in range(100):
        try:
            if get("/api/health")["status"] == "ok":
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError("Test application did not start")
    source = post(
        "/api/provenance/acquisitions",
        {
            "entry_type": "spawn_bag",
            "line": {},
            "inline_strain": {"name": "Backup Oyster"},
        },
    )
    recipe = command(
        "/api/preparation/recipes",
        {
            "name": "Backup substrate",
            "recipe_type": "substrate",
            "batch_yield": 1,
            "ingredients": [{"name": "Hardwood", "quantity": "1000", "unit": "g"}],
        },
    )
    grown = command(
        "/api/fruiting/create",
        {
            "spawn_id": source["records"][0]["id"],
            "recipe_id": recipe["id"],
            "count": 2,
            "spawning_date": "2026-01-01",
        },
    )["containers"]
    code = grown[0]["id"]

    def stage(action, day):
        return command(
            f"/api/fruiting/records/{code}/stage",
            {"action": action, "action_date": day},
        )

    stage("pinning", "2026-01-03")
    pin, png = attach(f"/api/fruiting/records/{code}/flushes/1/pinning/photos")
    stage("fruiting", "2026-01-05")
    h = command(
        f"/api/fruiting/records/{code}/harvests",
        {"harvest_date": "2026-01-07", "wet_grams": "100"},
    )
    harvest_photo, _ = attach(f"/api/fruiting/harvests/{h['id']}/photos")
    stage("next_flush", "2026-01-10")
    stage("fruiting", "2026-01-12")
    command(
        f"/api/fruiting/records/{code}/harvests",
        {"harvest_date": "2026-01-15", "wet_grams": "50"},
    )
    stage("complete", "2026-01-20")
    completed, _ = attach(f"/api/fruiting/records/{code}/completion/photos")
    helper(
        f"from pathlib import Path;import os;r=Path({str(root)!r});(r/'files/note.txt').write_text('retained file');(r/'settings/custom.json').write_text('{{\"retained\":true}}');[os.chown(r/p,10001,10001) for p in ['files/note.txt','settings/custom.json']]"
    )
    before = get(f"/api/fruiting/records/{code}")
    archive = temp / "complete.zip"
    with urllib.request.urlopen(base + "/api/backups/download", timeout=300) as r:
        archive.write_bytes(r.read())
    print(controller("verify", archive))
    extra = post("/api/library/strains", {"name": "After backup"})
    assert len(get("/api/library/strains")) == 2
    # Force a real post-cutover health failure, then verify automatic rollback
    # with the actual Compose controller, process checks and filesystem moves.
    fault = f"""
import sys
from pathlib import Path
sys.path.insert(0,'/repo/backend')
from app.restore_workspace import Compose,restore
from app.backup_format import BackupError
root=Path({str(root)!r});compose=Path({str(compose)!r});control=Compose(compose,root)
health=control.health
first=True
def fail_once():
 global first
 if first:
  first=False
  raise BackupError('Simulated new-dataset startup failure')
 health()
control.health=fail_once
try:
 restore(Path({str(archive)!r}),root,compose,confirm='REPLACE-PERSISTENT-DATA',controller=control)
 raise AssertionError('Failure injection did not run')
except BackupError as error:
 assert 'original data retained/restored' in str(error),str(error)
 print('Real Compose startup-failure rollback passed')
"""
    print(controller_run(["-c", fault]))
    assert len(get("/api/library/strains")) == 2
    # Terminate the host restorer after its first directory rename. The marker
    # and fsynced journal must allow the CLI to recover without creating a DB.
    abrupt = f"""
import sys,os
from pathlib import Path
sys.path.insert(0,'/repo/backend')
import app.restore_workspace as m
root=Path({str(root)!r});original=m.move
def interrupted(source,target):
 original(source,target)
 if source==root/'database' and target.parent.name=='original':
  print('INTERRUPTED_OPERATION='+str(target.parent.parent),flush=True)
  os._exit(86)
m.move=interrupted
m.restore(Path({str(archive)!r}),root,Path({str(compose)!r}),confirm='REPLACE-PERSISTENT-DATA')
"""
    try:
        controller_run(["-c", abrupt])
        raise AssertionError("Interrupted restore did not terminate")
    except subprocess.CalledProcessError as error:
        assert error.returncode == 86, error.output
        interrupted_operation = next(
            line.split("=", 1)[1]
            for line in error.output.splitlines()
            if line.startswith("INTERRUPTED_OPERATION=")
        )
    helper(
        f"from pathlib import Path;r=Path({str(root)!r});assert not (r/'database').exists();assert (r/'.cultivatinator-restore-in-progress.json').exists()"
    )
    print(
        controller(
            "recover",
            interrupted_operation,
            "--data-root",
            root,
            "--compose-file",
            compose,
            "--confirm",
            "REPLACE-PERSISTENT-DATA",
        )
    )
    assert len(get("/api/library/strains")) == 2
    result = controller(
        "restore",
        archive,
        "--data-root",
        root,
        "--compose-file",
        compose,
        "--confirm",
        "REPLACE-PERSISTENT-DATA",
    )
    print(result)
    operation = Path(result.split("at: ")[-1])
    assert len(get("/api/library/strains")) == 1
    assert get(f"/api/fruiting/records/{code}") == before
    for photo in [pin, harvest_photo, completed]:
        with urllib.request.urlopen(base + photo["url"]) as r:
            assert r.read() == png
        with urllib.request.urlopen(base + photo["thumbnail_url"]) as r:
            assert r.read().startswith(b"RIFF")
    print(
        helper(
            f"from pathlib import Path;import os,sqlite3;r=Path({str(root)!r});o=Path({str(operation)!r});assert (o/'pre-restore.zip').is_file();assert (o/'original/database/cultivatinator.sqlite3').is_file();assert (r/'files/note.txt').read_text()=='retained file';assert (r/'settings/custom.json').read_text()=='{{\"retained\":true}}';assert all(p.stat().st_uid==10001 and p.stat().st_gid==10001 for top in ['database','photos','files','settings'] for p in (r/top).rglob('*') if p.is_file());c=sqlite3.connect(o/'original/database/cultivatinator.sqlite3');assert c.execute(\"SELECT count(*) FROM strains WHERE name='After backup'\").fetchone()[0]==1;c.close();print('Recovery copy and original current data retained; restored file ownership is 10001:10001')"
        )
    )
    for path, digest in sentinels.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    print(
        "Backup Docker smoke passed: real stdlib CLI verification, local Compose stop/process fencing, four-directory restore, startup-failure rollback, abrupt-process recovery, non-root startup, retained independent recovery ZIP and originals, exact flush/harvest/completion photos, file/settings persistence and unchanged Git/source/Compose/.env"
    )
finally:
    try:
        docker("compose", "-f", str(compose), "down", "--timeout", "10")
    finally:
        try:
            helper(
                f"import os;from pathlib import Path;r=Path({str(temp)!r});[(os.chown(p,{os.getuid()},{os.getgid()}),os.chmod(p,0o700 if p.is_dir() else 0o600)) for p in r.rglob('*')];os.chmod(r,0o700)"
            )
        finally:
            __import__("shutil").rmtree(temp)
