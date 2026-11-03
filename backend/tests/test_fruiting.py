from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
import pytest
from alembic import command
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_direct_creation import recipe
from test_library import image_bytes


def cmd(client, path, data, status=200, key=None):
    response = client.post(
        "/api/fruiting/" + path, json={"request_key": key or str(uuid4()), **data}
    )
    assert response.status_code == status, response.text
    return response.json()


def source(client, material="spawn_jar", stage="ready"):
    existing = next(
        (
            r
            for r in client.get("/api/library/strains").json()
            if r["name"] == "Fruiting Oyster"
        ),
        None,
    )
    response = client.post(
        "/api/provenance/acquisitions",
        json={
            "entry_type": material,
            "stage": stage,
            "line": {},
            **(
                {"strain_id": existing["id"]}
                if existing
                else {"inline_strain": {"name": "Fruiting Oyster"}}
            ),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["records"][0]


def spawn(client, count=1, src=None, formula=None, **extra):
    src = src or source(client)
    formula = formula or recipe(client, "substrate")
    key = extra.pop("key", None)
    result = cmd(
        client,
        "create",
        {
            "spawn_id": src["id"],
            "recipe_id": formula["id"],
            "count": count,
            "spawning_date": "2026-01-01",
            **extra,
        },
        201,
        key=key,
    )
    return result["containers"]


def detail(client, code):
    return client.get("/api/fruiting/records/" + code).json()


def stage(client, code, action, day="2026-01-02", **extra):
    key = extra.pop("key", None)
    return cmd(
        client,
        f"records/{code}/stage",
        {"action": action, "action_date": day, **extra},
        key=key,
    )


def fruit(client):
    row = spawn(client)[0]
    stage(client, row["id"], "pinning", "2026-01-03")
    stage(client, row["id"], "fruiting", "2026-01-05")
    return row


def harvest(client, code, **extra):
    return cmd(
        client, f"records/{code}/harvests", {"harvest_date": "2026-01-07", **extra}, 201
    )


def test_one_spawn_many_fruits_consumption_labels_snapshots_and_idempotency(client):
    src = source(client)
    formula = recipe(client, "substrate")
    rows = spawn(client, 3, src, formula, key="bulk-spawn-retry")
    assert [r["physical_label"] for r in rows] == ["F-01", "F-02", "F-03"]
    assert len({r["id"] for r in rows}) == 3
    listing = client.get("/api/fruiting/")
    assert listing.status_code == 200
    assert {r["id"] for r in listing.json()} == {r["id"] for r in rows}
    assert all(
        r["fruiting_stage"] == "colonizing" and r["current_flush"] == 1 for r in rows
    )
    assert spawn(client, 3, src, formula, key="bulk-spawn-retry") == rows
    old = client.get("/api/library/spawn/" + src["id"]).json()
    assert old["stage"] == old["lifecycle"] == "used" and not old["label_occupied"]
    for row in rows:
        d = detail(client, row["id"])
        assert d["source"]["id"] == src["id"]
        assert row["strain_name"] == "Fruiting Oyster"
        assert d["run"]["recipe_snapshot"]["name"] == formula["name"]
        assert d["flushes"][0]["pinning_date"] is None
        assert d["run"]["environment_snapshot"] is None
        p = client.get("/api/provenance/fruiting/" + row["id"]).json()
        assert sum(r["record"]["id"] == src["id"] for r in p["relationships"]) == 1
        assert p["provenance_mode"].startswith("Recorded spawning")
        assert p["origin_date"] == "2026-01-01"
    assert (
        client.get("/api/preparation/recipes/" + formula["id"]).json()["used"] is True
    )
    cmd(client, "create", {"spawn_id": src["id"], "recipe_id": formula["id"]}, 409)
    assert client.get("/api/containers/available?material_type=spawn_jar").json()[
        "available"
    ] == ["J-01"]


def test_invalid_mixed_failed_and_nonready_sources_do_not_create_anything(client):
    src = source(client, stage="colonizing")
    formula = recipe(client, "substrate")
    cmd(client, "create", {"spawn_id": src["id"], "recipe_id": formula["id"]}, 409)
    cmd(
        client,
        "create",
        {
            "spawn_id": src["id"],
            "recipe_id": formula["id"],
            "source_ids": [src["id"], "SJ-other"],
        },
        422,
    )
    r = client.post(
        f"/api/containers/records/spawn/{src['id']}/state",
        json={"request_key": str(uuid4()), "action": "failed"},
    )
    assert r.status_code == 200
    cmd(client, "create", {"spawn_id": src["id"], "recipe_id": formula["id"]}, 409)
    assert client.get("/api/library/fruiting").json() == []


def test_atomic_failure_rolls_back_sources_labels_ids_and_reservations(client):
    src = source(client)
    formula = recipe(client, "substrate")
    hits = []

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO fruiting_containers"):
            hits.append(1)
            if len(hits) == 2:
                raise RuntimeError("Injected destination failure")

    event.listen(client.app.state.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="Injected"):
        spawn(client, 3, src, formula)
    event.remove(client.app.state.engine, "before_cursor_execute", fail)
    assert client.get("/api/library/fruiting").json() == []
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "ready"
    assert (
        client.get("/api/containers/available?material_type=tray").json()["next_label"]
        == "F-01"
    )
    assert spawn(client, 1, src, formula)[0]["id"] == "FR-0001"


def test_concurrent_consumption_has_one_winner(client):
    src = source(client)
    formula = recipe(client, "substrate")

    def submit(index):
        return client.post(
            "/api/fruiting/create",
            json={
                "request_key": f"concurrent-grow-{index}",
                "spawn_id": src["id"],
                "recipe_id": formula["id"],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(client.get("/api/library/fruiting").json()) == 1


def test_flushes_multiple_harvests_dry_edit_totals_and_timing(client):
    row = fruit(client)
    one = harvest(
        client,
        row["id"],
        wet_grams="100.125",
        potency=4,
        potency_notes="Subjective assessment",
        notes="First picking",
    )
    two = harvest(client, row["id"], wet_grams="50", harvest_date="2026-01-08")
    d = detail(client, row["id"])
    assert d["record"]["label_occupied"] and d["run"]["stage"] == "harvest"
    assert d["results"]["dry_grams"] is None
    assert d["results"]["wet_grams"] == "150.125"
    assert d["results"]["days_to_first_pinning"] == 2
    assert d["results"]["days_to_first_harvest"] == 6
    stage(client, row["id"], "next_flush", "2026-01-10")
    stage(client, row["id"], "fruiting", "2026-01-12")
    three = harvest(client, row["id"], harvest_date="2026-01-15")
    d = stage(client, row["id"], "complete", "2026-01-17", notes="No more flushes")
    assert (
        d["results"]["flushes_with_harvests"] == 2 and d["results"]["cycle_days"] == 16
    )
    assert not d["record"]["label_occupied"]
    updated = cmd(
        client,
        f"harvests/{one['id']}/edit",
        {
            "expected_revision": 1,
            "harvest_date": one["harvest_date"],
            "wet_grams": "100.125",
            "dry_grams": "10",
            "potency": 4,
            "potency_notes": one["potency_notes"],
            "notes": one["notes"],
        },
    )
    assert updated["dry_grams"] == "10.000"
    d = detail(client, row["id"])
    assert (
        d["results"]["dry_grams"] == "10.000"
        and d["results"]["dry_measured_count"] == 1
    )
    assert d["flushes"][1]["wet_grams"] is None
    history = client.get(f"/api/fruiting/harvests/{one['id']}/history").json()
    assert [r["snapshot"]["dry_grams"] for r in history] == [None, "10.000"]
    assert len(d["harvests"]) == 3
    assert cmd(client, f"records/{row['id']}/stage", {"action": "complete"}, 409)
    assert cmd(client, f"harvests/{one['id']}/edit", {"expected_revision": 1}, 409)


@pytest.mark.parametrize(
    "fields",
    [
        {"wet_grams": "-1"},
        {"dry_grams": "NaN"},
        {"potency": 0},
        {"potency": 6},
        {"potency": 2.5},
        {"wet_grams": "0.0001"},
    ],
)
def test_harvest_validation(client, fields):
    row = fruit(client)
    cmd(
        client,
        f"records/{row['id']}/harvests",
        {"harvest_date": "2026-01-07", **fields},
        422,
    )
    assert detail(client, row["id"])["harvests"] == []
    assert detail(client, row["id"])["record"]["label_occupied"]


def test_unknown_weights_stay_unknown_zero_is_measured(client):
    row = fruit(client)
    harvest(client, row["id"])
    d = detail(client, row["id"])
    assert d["results"]["wet_grams"] is None and d["results"]["wet_measured_count"] == 0
    harvest(client, row["id"], wet_grams="0")
    assert detail(client, row["id"])["results"]["wet_grams"] == "0.000"


def test_environment_default_and_changes_are_snapshots(client):
    assert client.get("/api/fruiting/environment").json()["environment"] is None
    env = {
        "tent_name": "One tent",
        "temperature": "22",
        "temperature_unit": "C",
        "humidity": "85",
        "fae": "Low fan",
        "humidifier": "As needed",
    }
    cmd(client, "environment", {"expected_revision": 0, "environment": env})
    row = fruit(client)
    cmd(
        client,
        "environment",
        {"expected_revision": 1, "environment": {**env, "humidity": "90"}},
    )
    d = detail(client, row["id"])
    assert d["run"]["environment_snapshot"]["humidity"] == "85"
    cmd(
        client,
        f"records/{row['id']}/environment",
        {
            "change_date": "2026-01-06",
            "notes": "Increase FAE after growth",
            "environment": {**env, "fae": "Medium fan"},
        },
    )
    d = detail(client, row["id"])
    assert d["environment"]["fae"] == "Medium fan"
    assert d["run"]["environment_snapshot"]["fae"] == "Low fan"
    assert len(d["environment_changes"]) == 1
    cmd(client, "environment", {"expected_revision": 1, "environment": env}, 409)


def test_harvest_photos_exact_association_existing_photo_management(client):
    row = fruit(client)
    one = harvest(client, row["id"])
    two = harvest(client, row["id"])
    response = client.post(
        f"/api/fruiting/harvests/{one['id']}/photos",
        files={"file": ("harvest.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 201, response.text
    photo = response.json()
    assert client.get(photo["url"]).status_code == 200
    assert len(client.get(f"/api/fruiting/harvests/{one['id']}/photos").json()) == 1
    assert client.get(f"/api/fruiting/harvests/{two['id']}/photos").json() == []
    assert client.post(f"/api/library/photos/{photo['id']}/cover").status_code == 200
    assert client.delete(f"/api/library/photos/{photo['id']}").status_code == 204
    activity = client.get(f"/api/library/fruiting/{row['id']}/activity").json()
    assert any(
        e["event_type"] == "photo_removed" and one["id"] in e["description"]
        for e in activity
    )
    assert client.get(f"/api/fruiting/harvests/{one['id']}/photos").json() == []


def test_release_once_disposable_bags_and_label_reuse(client):
    src = source(client, "spawn_bag")
    row = spawn(client, src=src)[0]
    d = stage(client, row["id"], "failed", key="fail-grow-once")
    assert not d["record"]["label_occupied"]
    assert stage(client, row["id"], "failed", key="fail-grow-once") == d
    assert spawn(client)[0]["physical_label"] == "F-01"
    assert (
        client.get("/api/containers/available?material_type=spawn_bag").json()[
            "available"
        ]
        == []
    )
    bag = spawn(client, material_type="bag")[0]
    stage(client, bag["id"], "failed")
    assert spawn(client, material_type="bag")[0]["physical_label"] == "FD-02"


def test_legacy_fruiting_no_fabrication_and_explicit_future_actions(client, settings):
    row = client.post(
        "/api/provenance/grows",
        json={"containers": [{"material_type": "tray", "stage": "fruiting"}]},
    ).json()["containers"][0]
    d = detail(client, row["id"])
    assert d["legacy"] and d["run"] is None and d["harvests"] == []
    assert (
        d["results"]["wet_grams"] is None
        and d["results"]["days_to_first_pinning"] is None
    )
    harvest(client, row["id"])
    d = detail(client, row["id"])
    assert d["run"]["spawning_date"] is None and d["run"]["source_spawn_id"] is None
    assert d["flushes"][0]["pinning_date"] is None
    assert d["results"]["days_to_first_harvest"] is None
    command.check(migration_config(settings))


def test_stage_order_dates_legacy_completion_and_recipe_history(client):
    row = spawn(client)[0]
    code = row["id"]
    cmd(client, f"records/{code}/stage", {"action": "fruiting"}, 409)
    stage(client, code, "pinning", "2026-01-03")
    cmd(
        client,
        f"records/{code}/stage",
        {"action": "fruiting", "action_date": "2026-01-02"},
        422,
    )
    stage(client, code, "fruiting", "2026-01-05")
    one = harvest(client, code)
    before = detail(client, code)["run"]["recipe_snapshot"]
    r = client.patch("/api/library/fruiting/" + code, json={"stage": "finished"})
    assert r.status_code == 200
    d = detail(client, code)
    assert d["run"]["stage"] == "completed" and not d["record"]["label_occupied"]
    assert d["run"]["recipe_snapshot"] == before
    assert d["run"]["completed_date"] is None
    assert d["results"]["cycle_days"] is None


def test_operational_provenance_snapshots_and_harvest_history_are_db_protected(client):
    row = fruit(client)
    second = source(client)
    one = harvest(client, row["id"])
    batch = client.get("/api/library/fruiting/" + row["id"]).json()["batch_id"]
    statements = [
        (
            "UPDATE fruiting_runs SET recipe_snapshot='{}' WHERE fruiting_id=:code",
            {"code": row["id"]},
        ),
        ("DELETE FROM harvest_revisions WHERE harvest_id=:code", {"code": one["id"]}),
        (
            "UPDATE harvest_entries SET flush_number=9 WHERE id=:code",
            {"code": one["id"]},
        ),
        (
            "INSERT INTO fruiting_sources (fruiting_id,spawn_id,batch_id) VALUES (:code,:spawn,:batch)",
            {"code": row["id"], "spawn": second["id"], "batch": batch},
        ),
        ("DELETE FROM fruiting_sources WHERE fruiting_id=:code", {"code": row["id"]}),
    ]
    for sql, params in statements:
        with pytest.raises(IntegrityError):
            with client.app.state.engine.begin() as connection:
                connection.execute(text(sql), params)


def test_new_environment_note_does_not_invent_legacy_biology(client):
    row = client.post("/api/provenance/grows", json={"containers": [{}]}).json()[
        "containers"
    ][0]
    cmd(
        client,
        f"records/{row['id']}/environment",
        {"notes": "Observed fresh air change", "change_date": "2026-01-03"},
    )
    d = detail(client, row["id"])
    assert d["run"]["stage"] == "unrecorded"
    assert (
        d["run"]["spawning_date"] is None and d["run"]["environment_snapshot"] is None
    )
    assert d["flushes"][0]["pinning_date"] is None
    stage(client, row["id"], "pinning", "2026-01-04")
    assert detail(client, row["id"])["run"]["stage"] == "pinning"


def test_substrate_edit_retains_original_snapshot_and_archived_recipe_cannot_be_reused(
    client,
):
    formula = recipe(client, "substrate")
    row = spawn(client, formula=formula)[0]
    before = detail(client, row["id"])["run"]["recipe_snapshot"]
    payload = {
        key: value
        for key, value in formula.items()
        if key
        not in {"id", "revision", "created_at", "updated_at", "used", "is_lc_default"}
    }
    response = client.put(
        "/api/preparation/recipes/" + formula["id"],
        json={
            **payload,
            "name": "Revised substrate",
            "status": "archived",
            "expected_revision": formula["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    assert detail(client, row["id"])["run"]["recipe_snapshot"] == before
    src = source(client)
    cmd(client, "create", {"spawn_id": src["id"], "recipe_id": formula["id"]}, 422)
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "ready"


def test_direct_spawn_reservation_closes_once_and_migration_history_guard(
    client, settings
):
    from test_container_labels import jars, action

    source_row = jars(client, "spawn_jar")[0]
    action(client, "spawn", source_row["id"], "ready")
    row = spawn(client, src=source_row, spawning_date="2026-11-02")[0]
    assert (
        client.get("/api/library/spawn/" + source_row["id"]).json()["lifecycle"]
        == "used"
    )
    assert (
        client.get("/api/preparation/materials/" + source_row["id"]).json()["stage"]
        == "completed"
    )
    assert detail(client, row["id"])["run"]["spawning_date"] == "2026-11-02"
    with pytest.raises(RuntimeError, match="Fruiting history exists"):
        command.downgrade(migration_config(settings), "0010_containers")


def test_populated_0010_upgrade_keeps_unlabeled_legacy_fruiting_records(settings):
    import sqlite3
    from fastapi.testclient import TestClient
    from app.main import create_app

    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0010_containers")
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO grow_batches (id,status,created_at,batch_origin,allocation_mode) VALUES ('GB-0090','active','2026-01-01','prepared','shared')"
        )
        connection.execute(
            "INSERT INTO fruiting_containers (id,batch_id,material_type,stage,status,created_at,notes) VALUES ('FR-0090','GB-0090','tray','fruiting','active','2026-01-01','Earlier history')"
        )
        connection.execute("INSERT INTO identity_sequences VALUES ('FR',90)")
    with TestClient(create_app(settings)) as client:
        old = detail(client, "FR-0090")
        assert old["run"] is None and old["record"]["physical_label"] is None
        assert (
            old["record"]["notes"] == "Earlier history"
            and old["record"]["created_at"] == "2026-01-01"
        )
        assert old["harvests"] == [] and old["environment"] is None
        assert spawn(client)[0]["id"] == "FR-0091"
        assert detail(client, "FR-0090") == old
    command.check(migration_config(settings))
