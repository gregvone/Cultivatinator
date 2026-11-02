"""Verify the local 2B image as UID 10001, then recreate it with retained data.
Build first; usage: python3 scripts/lineage_docker_smoke.py cultivatinator:milestone-2b
Creates and removes only a uniquely named test container and Docker volume.
"""

from io import BytesIO
import json
import subprocess
import sys
import time
from uuid import uuid4
import urllib.request
from PIL import Image

DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
name = "cultivatinator-2b-smoke-" + uuid4().hex[:10]
volume = name + "-data"
image = sys.argv[1] if len(sys.argv) > 1 else "cultivatinator:milestone-2b"


def docker(*args):
    return subprocess.check_output([*DOCKER, *args], text=True).strip()


def start():
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--security-opt",
        "no-new-privileges:true",
        "--cap-drop",
        "ALL",
        "-p",
        "127.0.0.1::8085",
        "--mount",
        f"type=volume,src={volume},dst=/data",
        image,
    )
    port = json.loads(
        docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", name)
    )["8085/tcp"][0]["HostPort"]
    base = "http://127.0.0.1:" + port
    for _ in range(100):
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return base
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Container failed readiness: " + docker("logs", name))


def request(path, data=None):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


try:
    docker("volume", "create", volume)
    base = start()
    assert docker("exec", name, "id", "-u") == "10001"
    with urllib.request.urlopen(base + "/culture-library") as r:
        assert '<div id="root">' in r.read().decode()
    a = request(
        "/api/provenance/acquisitions",
        {
            "entry_type": "spawn_jar",
            "line": {},
            "inline_strain": {"name": "Container persistence strain"},
        },
    )
    batch = request(
        "/api/provenance/grows",
        {"source_ids": [a["records"][0]["id"]], "containers": [{}]},
    )
    fruit = batch["containers"][0]
    clone = request(
        f"/api/provenance/fruiting/{fruit['id']}/establish", {"name": "Retained clone"}
    )
    png = BytesIO()
    Image.new("RGB", (20, 20), "#558899").save(png, format="PNG")
    boundary = "cultivatinator-smoke-boundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + png.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        base + f"/api/library/fruiting/{fruit['id']}/photos",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as r:
        photo = json.load(r)
    docker("stop", name)
    docker("rm", name)
    base = start()
    assert request("/api/health") == {
        "status": "ok",
        "database": "ok",
        "migrations": "current",
    }
    assert request("/api/library/strains")[0]["name"] == "Container persistence strain"
    p = request(f"/api/provenance/lines/{clone['line']['id']}")
    assert p["parents"] == [{"parent_id": a["line"]["id"], "confidence": "confirmed"}]
    assert request(f"/api/library/spawn/{a['records'][0]['id']}")["stage"] == "ready"
    with urllib.request.urlopen(base + photo["url"]) as r:
        assert r.read() == png.getvalue()
    assert (
        request(f"/api/library/fruiting/{fruit['id']}/photos")[0]["id"] == photo["id"]
    )
    print(
        "Milestone 2B Docker smoke passed: UID 10001, port 8085, SPA/API, migrations, retained records/ancestry/photos after container recreation; spawn stays Ready"
    )
finally:
    subprocess.run([*DOCKER, "rm", "-f", name], capture_output=True)
    subprocess.run([*DOCKER, "volume", "rm", volume], capture_output=True)
