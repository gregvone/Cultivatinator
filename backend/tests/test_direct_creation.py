from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
import json
import pytest
from sqlalchemy import event, text
from fastapi.testclient import TestClient
from alembic import command
from app.main import create_app
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_preparation import (
    post,
    stock,
    lc_source,
    list_stock,
    setup_preparation,
    prepare,
)
from test_library import receive, upload


def recipe(client, kind="agar", **extra):
    return post(
        client,
        "recipes",
        {
            "name": "User formula",
            "recipe_type": kind,
            "batch_yield": 5,
            "ingredients": [
                {"name": "Water", "quantity": "500", "unit": "mL"},
                {"name": "Nutrient", "quantity": "10", "unit": "g"},
            ],
            "instructions": "Prepare and sterilize",
            "notes": "Experiment",
            **extra,
        },
    )


def create(client, material, source, formula=None, status=201, key=None, **extra):
    return post(
        client,
        "create",
        {
            "material_type": material,
            "recipe_id": formula["id"] if formula else None,
            "source_kind": "physical",
            "source_id": source["id"],
            "count": 3,
            "inoculation_date": "2026-11-01",
            "unit": "mL",
            **extra,
        },
        status,
        key=key,
    )


@pytest.mark.parametrize("kind", ["agar", "grain", "lc", "substrate"])
def test_recipe_categories_allow_untracked_ingredients_and_edit_duplicate_delete(
    client, kind
):
    r = recipe(client, kind)
    assert client.get("/api/preparation/stock").json() == []
    detail = client.get("/api/preparation/recipes/" + r["id"]).json()
    assert detail["notes"] == "Experiment" and detail["used"] is False
    assert detail["updated_at"]
    duplicate = post(
        client,
        f"recipes/{r['id']}/duplicate",
        {"expected_revision": r["revision"]},
        key="duplicate-formula",
    )
    assert (
        post(
            client,
            f"recipes/{r['id']}/duplicate",
            {"expected_revision": r["revision"]},
            key="duplicate-formula",
        )
        == duplicate
    )
    assert duplicate["id"] != r["id"] and duplicate["name"].endswith("(copy)")
    body = {
        k: detail[k]
        for k in (
            "name",
            "recipe_type",
            "batch_yield",
            "ingredients",
            "instructions",
            "processing",
            "notes",
            "description",
            "shelf_life_days",
        )
    }
    updated = client.put(
        "/api/preparation/recipes/" + r["id"],
        json={
            **body,
            "name": "Edited",
            "expected_revision": r["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Edited" and updated.json()["revision"] == 2
    deleted = client.request(
        "DELETE",
        "/api/preparation/recipes/" + r["id"],
        json={"request_key": "delete-unused-recipe", "expected_revision": 2},
    )
    assert deleted.status_code == 200, deleted.text
    assert (
        client.request(
            "DELETE",
            "/api/preparation/recipes/" + r["id"],
            json={"request_key": "delete-unused-recipe", "expected_revision": 2},
        ).json()
        == deleted.json()
    )
    assert client.get("/api/preparation/recipes/" + r["id"]).status_code == 404


@pytest.mark.parametrize(
    "material,recipe_type,prefix",
    [
        ("agar_plate", "agar", "AG"),
        ("spawn_jar", "grain", "SJ"),
        ("spawn_bag", "grain", "SB"),
        ("lc_jar", "lc", "LC"),
    ],
)
def test_direct_bulk_no_inventory_permanent_ids_lineage_snapshot_and_date(
    client, material, recipe_type, prefix
):
    source = receive(client, count=1, material={"material_type": "agar_plate"})[
        "physical"
    ][0]
    ready = client.post(
        f"/api/containers/records/physical/{source["id"]}/state",
        json={"request_key": str(uuid4()), "action": "ready"},
    )
    assert ready.status_code == 200, ready.text
    r = recipe(client, recipe_type)
    if material == "lc_jar":
        post(
            client,
            "lc-default",
            {"recipe_id": r["id"], "expected_revision": r["revision"]},
            200,
        )
    result = create(
        client,
        material,
        source,
        r,
        unit="plate",
        notes="Cultivation notes",
        key="direct-creation-retry",
    )
    assert (
        create(
            client,
            material,
            source,
            r,
            unit="plate",
            notes="Cultivation notes",
            key="direct-creation-retry",
        )
        == result
    )
    assert len({row["id"] for row in result["materials"]}) == 3
    assert all(
        row["id"].startswith(prefix + "-") and row["stage"] == "inoculated"
        for row in result["materials"]
    )
    for row in result["materials"]:
        kind = "spawn" if material.startswith("spawn") else "physical"
        biological = client.get(f"/api/library/{kind}/{row['id']}").json()
        assert biological["line_id"] == source["line_id"]
        if kind == "spawn":
            assert biological["stage"] == "colonizing"
        assert (
            row["source"]["id"] == source["id"]
            and row["source"]["date"] == "2026-11-01"
        )
        assert row["snapshot"]["recipe"]["name"] == r["name"]
    with client.app.state.engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM container_reservations"
            ).scalar()
            == 0
        )
    assert not any(
        i["category"] != "source" for i in client.get("/api/preparation/stock").json()
    )
    assert all(
        t["entry_type"] not in {"reserve", "consume"}
        for t in client.get("/api/preparation/transactions").json()
    )
    assert len(client.get("/api/library/lines").json()) == 1
    assert (
        upload(
            client,
            "spawn" if material.startswith("spawn") else "physical",
            result["materials"][0]["id"],
        ).status_code
        == 201
    )


def test_known_lc_deducts_once_unknown_remains_unknown_and_recipe_stock_untouched(
    client,
):
    source = lc_source(client, "100")
    tracked = stock(client, available="0")
    r = recipe(
        client,
        "grain",
        ingredients=[{"item_id": tracked["id"], "quantity": "100", "unit": "g"}],
    )
    rows = create(client, "spawn_bag", source, r, count=5, usage_per_container="4")[
        "materials"
    ]
    assert len(rows) == 5 and list_stock(client)[tracked["id"]]["available"] == "0.000"
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "80.000"
    )
    create(
        client, "spawn_bag", source, r, count=5, usage_per_container="20", status=409
    )
    unknown = lc_source(client)
    create(client, "spawn_jar", unknown, r)
    assert (
        client.get("/api/library/physical/" + unknown["id"]).json()[
            "remaining_quantity"
        ]
        is None
    )


def test_lc_fill_depletion_and_known_usage_required(client):
    source = lc_source(client, "10")
    result = create(client, "lc_syringe", source, count=2, usage_per_container="5")
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["lifecycle"]
        == "depleted"
    )
    for row in result["materials"]:
        assert (
            client.get("/api/library/physical/" + row["id"]).json()[
                "remaining_quantity"
            ]
            == "5.000"
        )
    create(client, "lc_syringe", source, count=1, usage_per_container="1", status=409)
    another = lc_source(client, "100")
    create(client, "lc_syringe", another, status=422)


def test_wrong_recipe_and_used_recipe_archive_preserve_snapshot(client):
    source = lc_source(client)
    r = recipe(client)
    create(client, "spawn_jar", source, r, status=422)
    result = create(client, "agar_plate", source, r)
    snapshot = result["materials"][0]["snapshot"]
    assert client.get("/api/preparation/recipes/" + r["id"]).json()["used"] is True
    response = client.request(
        "DELETE",
        "/api/preparation/recipes/" + r["id"],
        json={"request_key": str(uuid4()), "expected_revision": r["revision"]},
    )
    assert response.status_code == 409 and "archive" in response.text
    body = {
        k: r[k]
        for k in (
            "name",
            "recipe_type",
            "batch_yield",
            "ingredients",
            "instructions",
            "processing",
            "shelf_life_days",
        )
    }
    response = client.put(
        "/api/preparation/recipes/" + r["id"],
        json={
            **body,
            "name": "New version",
            "status": "archived",
            "expected_revision": r["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    assert (
        client.get("/api/preparation/materials/" + result["materials"][0]["id"]).json()[
            "snapshot"
        ]
        == snapshot
    )
    create(client, "agar_plate", source, r, status=422)


def test_spore_direct_creation_remains_independent_pending_establishment(client):
    spore = client.post("/api/library/spores", json={}).json()
    r = recipe(client)
    rows = create(client, "agar_plate", spore, r, source_kind="spores", unit="print")[
        "materials"
    ]
    assert (
        client.get("/api/library/physical").json() == []
        and client.get("/api/library/lines").json() == []
    )
    assert all(row["physical_id"] is None for row in rows)
    assert sorted(row["physical_label"] for row in rows) == ["P-01", "P-02", "P-03"]
    assert all(row["growth_stage"] == "colonizing" for row in rows)
    assert all(row["inoculation_date"] == "2026-11-01" for row in rows)
    assert len(client.get("/api/preparation/growing?workspace=laboratory").json()) == 3
    line_ids = []
    for row in rows:
        response = client.post(
            f"/api/provenance/spores/{spore['id']}/establish",
            json={"prepared_id": row["id"]},
        )
        assert response.status_code == 201, response.text
        line_ids.append(response.json()["line"]["id"])
        physical = response.json()["physical"][0]
        assert physical["id"] == row["id"]
        assert physical["physical_label"] == row["physical_label"]
        assert physical["growth_stage"] == "colonizing" and physical["label_occupied"]
        history = client.get(f"/api/containers/records/physical/{row['id']}").json()
        assert len(history["assignments"]) == 1
    assert len(set(line_ids)) == 3


def test_atomic_creation_failure_rolls_back_balances_ids_history(client):
    source = lc_source(client, "100")
    r = recipe(client, "grain")
    before = list_stock(client)
    inserts = []

    def reject(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO spawn"):
            inserts.append(parameters)
            if len(inserts) == 2:
                raise RuntimeError("Injected second-container failure")

    event.listen(client.app.state.engine, "before_cursor_execute", reject)
    with pytest.raises(RuntimeError, match="Injected"):
        create(client, "spawn_jar", source, r, usage_per_container="5")
    event.remove(client.app.state.engine, "before_cursor_execute", reject)
    assert (
        list_stock(client) == before and client.get("/api/library/spawn").json() == []
    )
    assert client.get("/api/preparation/materials").json() == []
    assert (
        create(client, "spawn_jar", source, r, usage_per_container="5")["materials"][0][
            "id"
        ]
        == "SJ-0001"
    )


def test_concurrent_identical_direct_requests_create_once(client):
    source = lc_source(client, "100")
    r = recipe(client, "grain")

    def submit(_):
        return create(
            client,
            "spawn_bag",
            source,
            r,
            usage_per_container="5",
            key="same-bulk-request",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    assert len(client.get("/api/library/spawn").json()) == 3
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "85.000"
    )


def test_inventory_edit_visibility_balance_preserved_and_audited(client):
    item = stock(
        client, name="Actual ingredient", available="12", storage_location="Shelf A"
    )
    updated = client.put(
        "/api/preparation/stock/" + item["id"],
        json={
            "request_key": "stock-metadata-edit",
            "expected_revision": item["revision"],
            "name": "Renamed ingredient",
            "storage_location": "Shelf B",
            "notes": "Moved",
            "reason": "Corrected label",
        },
    )
    assert updated.status_code == 200, updated.text
    row = list_stock(client)[item["id"]]
    assert (
        row["name"] == "Renamed ingredient"
        and row["storage_location"] == "Shelf B"
        and row["available"] == "12.000"
    )
    assert (
        client.get("/api/preparation/transactions?item_id=" + item["id"]).json()[0][
            "reason"
        ]
        == "Corrected label"
    )


def test_growing_views_dates_terminal_states_and_legacy_compatibility(client):
    source = lc_source(client, "100")
    r = recipe(client, "grain")
    result = create(client, "spawn_jar", source, r, usage_per_container="5")
    first = result["materials"][0]
    post(
        client,
        f"materials/{first['id']}/finish",
        {"action": "failed", "reason": "Observed failure"},
        200,
    )
    rows = client.get("/api/preparation/growing?workspace=cultivation").json()
    assert len(rows) == 3 and any(row["lifecycle"] == "failed" for row in rows)
    assert all(row["cultivation"]["source"]["date"] == "2026-11-01" for row in rows)
    raw, container = setup_preparation(client, "agar_plate", 2)
    old = prepare(client, raw, container, 1)["materials"]
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [old[0]["id"]],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "5",
            "unit": "mL",
        },
    )
    assert (
        client.get("/api/preparation/materials/" + old[0]["id"]).json()["physical_id"]
        == old[0]["id"]
    )


def test_default_date_and_new_batches_have_new_ids(client):
    source = lc_source(client)
    formula = recipe(client)
    body = {
        "material_type": "agar_plate",
        "recipe_id": formula["id"],
        "source_kind": "physical",
        "source_id": source["id"],
        "count": 2,
        "unit": "mL",
    }
    first = post(client, "create", body)
    second = post(client, "create", body)
    assert {r["id"] for r in first["materials"]}.isdisjoint(
        {r["id"] for r in second["materials"]}
    )
    assert all(
        r["source"]["date"] == date.today().isoformat() for r in first["materials"]
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        is None
    )


def test_0007_recipe_upgrade_preserves_contents_and_committed_recipe_retry(settings):
    import hashlib
    import sqlite3

    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0007_inventory")
    old_payload = {
        "request_key": "old-recipe-request",
        "name": "Historical agar",
        "recipe_type": "agar",
        "batch_yield": 5,
        "ingredients": [{"item_id": "INV-0099", "quantity": "10", "unit": "g"}],
        "instructions": "Historical instructions",
        "processing": {
            "method": None,
            "duration_minutes": None,
            "temperature_c": None,
            "pressure_psi": None,
            "notes": None,
        },
        "shelf_life_days": None,
    }
    contents = {k: v for k, v in old_payload.items() if k != "request_key"}
    old_result = {
        **contents,
        "id": "RCP-0099",
        "revision": 1,
        "status": "active",
        "created_at": "2026-01-01",
    }
    fingerprint = hashlib.sha256(
        ("recipe_create" + json.dumps(old_payload, sort_keys=True)).encode()
    ).hexdigest()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO stock_items (id,name,category,unit,available,status,revision,created_at) VALUES ('INV-0099','Old agar powder','ingredient','g',0,'active',1,'2026-01-01')"
        )
        connection.execute(
            "INSERT INTO preparation_recipes VALUES ('RCP-0099','Historical agar','agar',?,1,'active','2026-01-01')",
            (json.dumps(contents),),
        )
        connection.execute(
            "INSERT INTO inventory_operations VALUES ('OP-0099',?,?, 'recipe_create',?,?, '2026-01-01')",
            (
                old_payload["request_key"],
                fingerprint,
                json.dumps(old_payload),
                json.dumps(old_result),
            ),
        )
    with TestClient(create_app(settings)) as client:
        r = client.get("/api/preparation/recipes/RCP-0099").json()
        assert r["updated_at"] is None and r["created_at"] == "2026-01-01"
        assert r["ingredients"][0]["name"] == "Old agar powder"
        retry = post(client, "recipes", old_payload)
        assert retry["id"] == "RCP-0099"
        source = lc_source(client)
        create(client, "agar_plate", source, r)
        with client.app.state.engine.connect() as connection:
            assert (
                json.loads(
                    connection.exec_driver_sql(
                        "SELECT contents FROM preparation_recipes WHERE id='RCP-0099'"
                    ).scalar()
                )
                == contents
            )
            assert (
                connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            )
    command.check(migration_config(settings))
