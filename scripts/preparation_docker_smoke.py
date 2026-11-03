"""Verify the local 2C.2 image as UID 10001, then recreate it with retained data.
Build first; usage: python3 scripts/preparation_docker_smoke.py cultivatinator:milestone-2c2
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
name = "cultivatinator-2c2-smoke-" + uuid4().hex[:10]
volume = name + "-data"
image = sys.argv[1] if len(sys.argv) > 1 else "cultivatinator:milestone-2c2"


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

    def command(path, data):
        return request(
            "/api/preparation/" + path, {"request_key": str(uuid4()), **data}
        )

    lc = request(
        "/api/library/receive-culture",
        {"line": {}, "material": {"material_type": "lc_jar"}},
    )["physical"][0]
    command(
        "stock",
        {
            "name": "LC balance",
            "category": "source",
            "unit": "mL",
            "available": "25",
            "source_kind": "physical",
            "source_id": lc["id"],
            "reason": "Measured",
        },
    )
    grain = command(
        "stock",
        {
            "name": "Grain",
            "category": "ingredient",
            "unit": "g",
            "available": "1000",
            "reason": "Weighed",
        },
    )
    jars = command(
        "stock",
        {
            "name": "Reusable jars",
            "category": "reusable",
            "container_type": "spawn_jar",
            "unit": "count",
            "available": "5",
            "reason": "Counted",
        },
    )
    recipe = command(
        "recipes",
        {
            "name": "Grain recipe",
            "recipe_type": "grain",
            "batch_yield": 5,
            "ingredients": [{"item_id": grain["id"], "quantity": "500", "unit": "g"}],
        },
    )
    prepared = command(
        "prepare",
        {
            "material_type": "spawn_jar",
            "count": 5,
            "container_item_id": jars["id"],
            "recipe_id": recipe["id"],
        },
    )
    assert all(row["stage"] == "ready" for row in prepared["materials"])
    inoc_payload = {
        "prepared_ids": [r["id"] for r in prepared["materials"]],
        "source_kind": "physical",
        "source_id": lc["id"],
        "usage_per_container": "5",
        "unit": "mL",
        "request_key": "docker-restart-inoculation",
    }
    inoculated = command("inoculate", inoc_payload)
    failed = prepared["materials"][0]["id"]
    command(
        "materials/" + failed + "/finish",
        {"action": "failed", "reason": "Explicit lifecycle test"},
    )
    direct_source = request(
        "/api/library/receive-culture",
        {"line": {}, "material": {"material_type": "agar_plate"}},
    )["physical"][0]

    def mark_ready(code):
        return request(
            f"/api/containers/records/physical/{code}/state",
            {"request_key": str(uuid4()), "action": "ready"},
        )

    mark_ready(direct_source["id"])
    direct_recipe = command(
        "recipes",
        {
            "name": "Untracked agar formula",
            "recipe_type": "agar",
            "batch_yield": 2,
            "ingredients": [{"name": "Agar", "quantity": "10", "unit": "g"}],
            "notes": "Retained formula",
        },
    )
    direct_payload = {
        "request_key": "docker-direct-retry",
        "material_type": "agar_plate",
        "recipe_id": direct_recipe["id"],
        "source_kind": "physical",
        "source_id": direct_source["id"],
        "count": 2,
        "inoculation_date": "2026-11-01",
        "unit": "plate",
    }
    direct_result = command("create", direct_payload)
    assert all(row["stage"] == "inoculated" for row in direct_result["materials"])
    media_default = command(
        "recipes",
        {
            "name": "Retained LC Media",
            "recipe_type": "lc",
            "batch_yield": 1,
            "ingredients": [{"name": "Media nutrient", "quantity": "1", "unit": "g"}],
        },
    )
    command(
        "lc-default",
        {
            "recipe_id": media_default["id"],
            "expected_revision": media_default["revision"],
        },
    )
    # A consumed plate cannot supply a later operation. Explicitly ready one
    # of the new agar destinations for the LC operation.
    jar_source = direct_result["materials"][0]
    mark_ready(jar_source["id"])
    jar_payload = {
        "request_key": "docker-auto-media-jar",
        "material_type": "lc_jar",
        "source_kind": "physical",
        "source_id": jar_source["id"],
        "count": 1,
        "inoculation_date": "2026-11-01",
        "destination_volume_ml": "100",
        "unit": "plate",
    }
    jar_result = command("create", jar_payload)
    jar_id = jar_result["materials"][0]["id"]
    syringe_payload = {
        "request_key": "docker-inherited-media-syringes",
        "material_type": "lc_syringe",
        "source_kind": "physical",
        "source_id": jar_id,
        "count": 2,
        "usage_per_container": "5",
        "unit": "mL",
        "inoculation_date": "2026-11-01",
    }
    syringe_result = command("create", syringe_payload)
    assert all(
        row["snapshot"]["media_origin"] == "source_transfer"
        and row["snapshot"]["recipe"]["name"] == "Retained LC Media"
        for row in syringe_result["materials"]
    )

    # Operational 2C.3 writes share the same retained volume as older history.
    def fruit_command(path, data, key=None):
        return request(
            "/api/fruiting/" + path, {"request_key": key or str(uuid4()), **data}
        )

    tent = {
        "tent_name": "Retained single tent",
        "temperature": "22",
        "temperature_unit": "C",
        "humidity": "85",
        "fae": "Low fan",
    }
    fruit_command("environment", {"expected_revision": 0, "environment": tent})
    substrate = command(
        "recipes",
        {
            "name": "Retained Substrate",
            "recipe_type": "substrate",
            "batch_yield": 1,
            "ingredients": [{"name": "Hardwood", "quantity": "1000", "unit": "g"}],
        },
    )
    grow_payload = {
        "spawn_id": a["records"][0]["id"],
        "recipe_id": substrate["id"],
        "count": 2,
        "spawning_date": "2026-01-01",
    }
    grown = fruit_command("create", grow_payload, "docker-operational-grow")
    grow_id = grown["containers"][0]["id"]
    other_grow = grown["containers"][1]["id"]

    def grow_stage(action, day):
        return fruit_command(
            f"records/{grow_id}/stage", {"action": action, "action_date": day}
        )

    grow_stage("pinning", "2026-01-03")
    grow_stage("fruiting", "2026-01-05")
    harvest_one = fruit_command(
        f"records/{grow_id}/harvests",
        {
            "harvest_date": "2026-01-07",
            "wet_grams": "100",
            "potency": 4,
            "potency_notes": "Subjective grower assessment",
        },
    )
    fruit_command(
        f"records/{grow_id}/harvests", {"harvest_date": "2026-01-08", "wet_grams": "50"}
    )
    fruit_command(
        f"harvests/{harvest_one['id']}/edit",
        {
            "expected_revision": 1,
            "harvest_date": "2026-01-07",
            "wet_grams": "100",
            "dry_grams": "10",
            "potency": 4,
            "potency_notes": "Subjective grower assessment",
        },
    )
    grow_stage("next_flush", "2026-01-10")
    grow_stage("fruiting", "2026-01-12")
    fruit_command(
        f"records/{grow_id}/harvests",
        {"harvest_date": "2026-01-14", "wet_grams": "80", "dry_grams": "8"},
    )
    fruit_command(
        f"records/{grow_id}/environment",
        {
            "change_date": "2026-01-06",
            "notes": "Observed humidity adjustment",
            "environment": {**tent, "humidity": "88"},
        },
    )
    fruit_command(
        "environment",
        {"expected_revision": 1, "environment": {**tent, "humidity": "90"}},
    )
    harvest_req = urllib.request.Request(
        base + f"/api/fruiting/harvests/{harvest_one['id']}/photos",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(harvest_req) as response:
        harvest_photo = json.load(response)

    def pinning_photo(number):
        req = urllib.request.Request(
            base + f"/api/fruiting/records/{grow_id}/flushes/{number}/pinning/photos",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    pinning_one = [pinning_photo(1), pinning_photo(1)]
    pinning_two = pinning_photo(2)
    grow_before = request(f"/api/fruiting/records/{grow_id}")
    harvest_history_before = request(
        f"/api/fruiting/harvests/{harvest_one['id']}/history"
    )
    assert grow_before["record"]["label_occupied"]
    assert grow_before["results"]["wet_grams"] == "230.000"
    assert grow_before["results"]["dry_grams"] == "18.000"
    assert grow_before["run"]["environment_snapshot"]["humidity"] == "85"
    assert grow_before["environment"]["humidity"] == "88"
    source_before = request("/api/library/physical/" + direct_source["id"])
    assert source_before["lifecycle"] == "used" and not source_before["label_occupied"]
    depleted_before = request("/api/library/physical/" + lc["id"])
    assert (
        depleted_before["label_occupied"] and depleted_before["lifecycle"] == "depleted"
    )
    label_history = request(f"/api/containers/records/physical/{direct_source['id']}")
    label_availability = request("/api/containers/available?material_type=agar_plate")
    ledger_before = request("/api/preparation/transactions")
    snapshots_before = request("/api/preparation/materials")
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
    assert request(f"/api/library/spawn/{a['records'][0]['id']}")["stage"] == "used"
    with urllib.request.urlopen(base + photo["url"]) as r:
        assert r.read() == png.getvalue()
    assert (
        request(f"/api/library/fruiting/{fruit['id']}/photos")[0]["id"] == photo["id"]
    )
    assert request("/api/library/physical/" + direct_source["id"]) == source_before
    assert request("/api/library/physical/" + lc["id"]) == depleted_before
    assert (
        request(f"/api/containers/records/physical/{direct_source['id']}")
        == label_history
    )
    assert (
        request("/api/containers/available?material_type=agar_plate")
        == label_availability
    )
    assert request("/api/preparation/materials") == snapshots_before
    assert request("/api/preparation/transactions") == ledger_before
    assert (
        next(r for r in request("/api/preparation/stock") if r["id"] == jars["id"])[
            "available"
        ]
        == "1.000"
    )
    assert request("/api/library/physical/" + lc["id"])["lifecycle"] == "depleted"
    assert request("/api/library/spawn/" + failed)["lifecycle"] == "failed"
    assert command("inoculate", inoc_payload) == inoculated
    assert command("create", direct_payload) == direct_result
    assert request("/api/preparation/lc-default")["recipe"]["id"] == media_default["id"]
    assert command("create", jar_payload) == jar_result
    assert command("create", syringe_payload) == syringe_result
    assert request("/api/library/physical/" + jar_id)["remaining_quantity"] == "90.000"
    assert (
        request("/api/preparation/recipes/" + direct_recipe["id"])["notes"]
        == "Retained formula"
    )
    assert all(
        request("/api/library/physical/" + row["id"])["line_id"]
        == direct_source["line_id"]
        for row in direct_result["materials"]
    )
    assert request("/api/preparation/transactions") == ledger_before
    assert request(f"/api/fruiting/records/{grow_id}") == grow_before
    assert (
        request(f"/api/fruiting/harvests/{harvest_one['id']}/history")
        == harvest_history_before
    )
    assert request("/api/fruiting/environment")["environment"]["humidity"] == "90"
    assert (
        request(f"/api/fruiting/harvests/{harvest_one['id']}/photos")[0]["id"]
        == harvest_photo["id"]
    )
    with urllib.request.urlopen(base + harvest_photo["url"]) as response:
        assert response.read() == png.getvalue()
    assert {
        p["id"]
        for p in request(f"/api/fruiting/records/{grow_id}/flushes/1/pinning/photos")
    } == {p["id"] for p in pinning_one}
    assert [
        p["id"]
        for p in request(f"/api/fruiting/records/{grow_id}/flushes/2/pinning/photos")
    ] == [pinning_two["id"]]
    for pin in [*pinning_one, pinning_two]:
        with urllib.request.urlopen(base + pin["url"]) as response:
            assert response.read() == png.getvalue()
    assert (
        request(f"/api/fruiting/records/{grow_id}")["flushes"][0]["pinning_date"]
        == "2026-01-03"
    )
    assert fruit_command("create", grow_payload, "docker-operational-grow") == grown
    ended = fruit_command(
        f"records/{grow_id}/stage",
        {"action": "complete", "action_date": "2026-01-17"},
        "docker-finish-grow",
    )
    assert (
        not ended["record"]["label_occupied"] and ended["results"]["cycle_days"] == 16
    )
    assert (
        fruit_command(
            f"records/{grow_id}/stage",
            {"action": "complete", "action_date": "2026-01-17"},
            "docker-finish-grow",
        )
        == ended
    )
    assert request("/api/containers/available?material_type=tray")["available"] == [
        grown["containers"][0]["physical_label"]
    ]
    fruit_command(
        f"records/{other_grow}/stage", {"action": "failed", "action_date": "2026-01-17"}
    )
    print(
        "Milestones 2C.2/2C.3 Docker smoke passed: non-root port 8085, 2B data/photos/FR identity, immutable preparation snapshots and ledger, depletion, one-time release, direct creation without container stock, recipe definitions, LC default/inherited media and idempotency, operational single-source grows, flushes, harvest edits/history/photos, environment snapshots and explicit label release preserved across recreation"
    )
finally:
    subprocess.run([*DOCKER, "rm", "-f", name], capture_output=True)
    subprocess.run([*DOCKER, "volume", "rm", volume], capture_output=True)
