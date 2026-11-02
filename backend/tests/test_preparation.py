from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import pytest
from sqlalchemy import text, event as sql_event
from sqlalchemy.exc import IntegrityError
from alembic import command
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_library import receive, upload


def post(client, path, body, status=201, key=None):
    payload = {"request_key": key or str(uuid4()), **body}
    r = client.post("/api/preparation/" + path, json=payload)
    assert r.status_code == status, r.text
    return r.json()


def stock(
    client,
    name="Ingredient",
    category="ingredient",
    unit="g",
    available="1000",
    **values,
):
    return post(
        client,
        "stock",
        dict(
            name=name,
            category=category,
            unit=unit,
            available=available,
            reason="Confirmed opening stock",
            **values,
        ),
    )


def setup_preparation(client, kind="spawn_bag", capacity=10, ingredient_balance="1000"):
    raw = stock(client, available=ingredient_balance)
    container = stock(
        client,
        name=kind,
        category=(
            "reusable"
            if kind in {"agar_plate", "lc_jar", "spawn_jar"}
            else "consumable"
        ),
        unit="count",
        available=str(capacity),
        container_type=kind,
    )
    return raw, container


def prepare(client, raw, container, count=5, **values):
    body = {
        "material_type": container["container_type"],
        "count": count,
        "container_item_id": container["id"],
        "ingredients": (
            []
            if container["container_type"] == "lc_syringe"
            else [{"item_id": raw["id"], "quantity": str(count * 10), "unit": "g"}]
        ),
        **values,
    }
    return post(client, "prepare", body)


def lc_source(client, remaining=None):
    source = receive(
        client,
        count=1,
        material={"material_type": "lc_jar", "quantity": "999", "unit": "mL"},
    )["physical"][0]
    if remaining is not None:
        stock(
            client,
            name="Source LC",
            category="source",
            unit="mL",
            available=remaining,
            source_kind="physical",
            source_id=source["id"],
        )
    return source


def inoculate(client, source, materials, **values):
    return post(
        client,
        "inoculate",
        {
            "prepared_ids": [r["id"] for r in materials],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "5",
            "unit": "mL",
            **values,
        },
    )


def list_stock(client):
    return {r["id"]: r for r in client.get("/api/preparation/stock").json()}


def test_prepare_ingredients_readiness_individual_ids_and_idempotency(client):
    raw, container = setup_preparation(client, "agar_plate", 20)
    body = {
        "material_type": "agar_plate",
        "count": 10,
        "container_item_id": container["id"],
        "ingredients": [{"item_id": raw["id"], "quantity": "5.125", "unit": "g"}],
        "preparation_date": "2026-01-01",
        "processing": {
            "method": "Instant Pot",
            "duration_minutes": 30,
            "pressure_psi": "15",
        },
        "use_by": "2026-01-31",
    }
    first = post(client, "prepare", body, key="prepare-request")
    repeat = post(client, "prepare", body, key="prepare-request")
    assert first == repeat
    assert len(first["materials"]) == 10
    assert [r["id"] for r in first["materials"]] == [f"AG-{i:04}" for i in range(1, 11)]
    assert all(
        r["stage"] == "ready" and r["physical_id"] is None for r in first["materials"]
    )
    assert client.get("/api/library/lines").json() == []
    assert list_stock(client)[raw["id"]]["available"] == "994.875"
    assert list_stock(client)[container["id"]]["available"] == "10.000"
    rows = client.get("/api/preparation/materials").json()
    assert sum(r["stage"] == "ready" for r in rows) == 10
    assert rows[0]["expired"] is True
    assert rows[0]["snapshot"]["processing"]["method"] == "Instant Pot"
    post(client, "prepare", {**body, "count": 1}, 409, key="prepare-request")


def test_recipe_scaling_defaults_override_and_history_snapshot(client):
    raw, container = setup_preparation(client, "lc_jar")
    data = {
        "name": "LC medium",
        "recipe_type": "lc",
        "batch_yield": 10,
        "ingredients": [{"item_id": raw["id"], "quantity": "12.345", "unit": "g"}],
        "instructions": "Original instructions",
        "processing": {"method": "Pressure cooker", "duration_minutes": 45},
        "shelf_life_days": 30,
    }
    recipe = post(client, "recipes", data)
    batch = post(
        client,
        "prepare",
        {
            "material_type": "lc_jar",
            "count": 5,
            "container_item_id": container["id"],
            "recipe_id": recipe["id"],
            "preparation_date": "2026-01-01",
        },
    )
    snapshot = batch["materials"][0]["snapshot"]
    assert snapshot["ingredients"][0]["quantity"] == "6.173"
    assert snapshot["use_by"] == "2026-01-31"
    assert snapshot["recipe"]["instructions"] == "Original instructions"
    edited = client.put(
        "/api/preparation/recipes/" + recipe["id"],
        json={
            **data,
            "name": "Edited",
            "instructions": "New",
            "status": "archived",
            "expected_revision": recipe["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert edited.status_code == 200, edited.text
    assert (
        client.get("/api/preparation/materials/" + batch["materials"][0]["id"]).json()[
            "snapshot"
        ]
        == snapshot
    )
    post(
        client,
        "prepare",
        {
            "material_type": "lc_jar",
            "count": 1,
            "container_item_id": container["id"],
            "recipe_id": recipe["id"],
        },
        422,
    )
    override = prepare(
        client,
        raw,
        container,
        1,
        processing={"method": "Custom"},
        shelf_life_days=7,
        preparation_date="2026-01-01",
        use_by="2026-02-01",
    )
    assert override["materials"][0]["use_by"] == "2026-02-01"


@pytest.mark.parametrize("insufficient", ["ingredient", "container"])
def test_insufficient_stock_rolls_back_every_record_and_deduction(client, insufficient):
    raw, container = setup_preparation(
        client,
        "spawn_jar",
        capacity=1 if insufficient == "container" else 20,
        ingredient_balance="1" if insufficient == "ingredient" else "1000",
    )
    before = list_stock(client)
    body = {
        "material_type": "spawn_jar",
        "count": 5,
        "container_item_id": container["id"],
        "ingredients": [{"item_id": raw["id"], "quantity": "25", "unit": "g"}],
    }
    post(client, "prepare", body, 409)
    assert list_stock(client) == before
    assert client.get("/api/preparation/materials").json() == []
    assert not any(
        t["entry_type"] in {"reserve", "consume"}
        for t in client.get("/api/preparation/transactions").json()
    )


def test_unknown_balances_and_adjustment_audit_are_not_invented(client):
    raw, container = setup_preparation(client, ingredient_balance=None)
    prepare(client, raw, container, 2)
    assert list_stock(client)[raw["id"]]["available"] is None
    item = list_stock(client)[raw["id"]]
    item = post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "add",
            "quantity": "5",
            "expected_revision": item["revision"],
            "reason": "Unknown delivery added",
        },
        200,
    )
    assert item["available"] is None
    corrected = post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": "50.125",
            "expected_revision": item["revision"],
            "reason": "Weighed remaining stock",
        },
        200,
    )
    assert corrected["available"] == "50.125"
    post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": "1",
            "expected_revision": item["revision"],
            "reason": "Stale",
        },
        409,
    )
    history = client.get("/api/preparation/transactions?item_id=" + item["id"]).json()
    assert (
        history[0]["reason"] == "Weighed remaining stock"
        and history[0]["before_quantity"] is None
    )
    with pytest.raises(IntegrityError):
        with client.app.state.engine.begin() as c:
            c.execute(
                text("DELETE FROM stock_transactions WHERE id=:id"),
                {"id": history[0]["id"]},
            )


def test_bulk_partial_inoculation_uses_25ml_once_and_preserves_line(client):
    raw, container = setup_preparation(client, "spawn_bag")
    batch = prepare(client, raw, container, 8)
    source = lc_source(client, "100")
    selected = batch["materials"][:5]
    body = {
        "prepared_ids": [r["id"] for r in selected],
        "source_kind": "physical",
        "source_id": source["id"],
        "usage_per_container": "5",
        "unit": "mL",
        "inoculation_date": "2026-01-02",
    }
    a = post(client, "inoculate", body, key="bulk-inoculation")
    b = post(client, "inoculate", body, key="bulk-inoculation")
    assert a == b
    assert [m["spawn_id"] for m in a["materials"]] == [
        f"SB-{i:04}" for i in range(1, 6)
    ]
    rows = client.get("/api/library/spawn").json()
    assert len(rows) == 5 and all(
        r["line_id"] == source["line_id"] and r["stage"] == "colonizing" for r in rows
    )
    assert len(client.get("/api/library/lines").json()) == 1
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "75.000"
    )
    assert (
        sum(
            r["stage"] == "ready"
            for r in client.get("/api/preparation/materials").json()
        )
        == 3
    )
    assert all(m["source"]["id"] == source["id"] for m in a["materials"])
    uses = [
        t
        for t in client.get("/api/preparation/transactions").json()
        if t["entry_type"] == "usage"
    ]
    assert len(uses) == 1 and uses[0]["amount"] == "-25.000"
    post(client, "inoculate", body, 409)
    failed_id = selected[0]["id"]
    post(
        client,
        "records/spawn/" + failed_id + "/finish",
        {"action": "failed", "reason": "Explicit failure"},
        200,
    )
    edited = client.patch(
        "/api/library/spawn/" + failed_id,
        json={"notes": "Retained historical description", "stage": "colonizing"},
    )
    assert edited.status_code == 200, edited.text
    assert (
        client.patch(
            "/api/library/spawn/" + failed_id, json={"stage": "ready"}
        ).status_code
        == 409
    )


def test_lc_depletion_correction_and_unknown_source_quantities(client):
    raw, container = setup_preparation(client, "lc_syringe")
    batch = prepare(client, raw, container, 3)
    source = lc_source(client, "10")
    result = inoculate(client, source, batch["materials"][:2])
    depleted = client.get("/api/library/physical/" + source["id"]).json()
    assert (
        depleted["lifecycle"] == "depleted"
        and depleted["remaining_quantity"] == "0.000"
    )
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [batch["materials"][2]["id"]],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "1",
            "unit": "mL",
        },
        409,
    )
    for dest in result["materials"]:
        assert (
            client.get("/api/library/physical/" + dest["physical_id"]).json()[
                "remaining_quantity"
            ]
            == "5.000"
        )
    item = list_stock(client)[depleted["stock_item_id"]]
    post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": "20",
            "expected_revision": item["revision"],
            "reason": "Corrected measured volume",
        },
        200,
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["lifecycle"]
        == "active"
    )
    unknown = lc_source(client)
    inoculate(client, unknown, batch["materials"][2:])
    row = client.get("/api/library/physical/" + unknown["id"]).json()
    assert (
        row["quantity"] == "999.000"
        and row["remaining_quantity"] is None
        and row["lifecycle"] == "active"
    )


def test_pool_release_complete_failure_and_plate_remains_after_transfer(client):
    raw, container = setup_preparation(client, "agar_plate", 20)
    batch = prepare(client, raw, container, 3)
    source = lc_source(client)
    first = inoculate(client, source, batch["materials"][:1])["materials"][0]
    agar = client.get("/api/library/physical/" + first["physical_id"]).json()
    inoculate(
        client, agar, batch["materials"][1:2], unit="plate", usage_per_container=None
    )
    assert (
        client.get("/api/library/physical/" + agar["id"]).json()["lifecycle"]
        == "active"
    )
    finish = {
        "action": "complete",
        "action_date": "2026-01-02",
        "reason": "Finished use",
    }
    post(
        client,
        "materials/" + first["id"] + "/finish",
        finish,
        200,
        key="finish-container",
    )
    post(
        client,
        "materials/" + first["id"] + "/finish",
        finish,
        200,
        key="finish-container",
    )
    assert list_stock(client)[container["id"]]["available"] == "18.000"
    post(
        client,
        "materials/" + first["id"] + "/finish",
        {**finish, "action": "failed"},
        409,
    )
    post(
        client,
        "materials/" + batch["materials"][2]["id"] + "/finish",
        {"action": "failed", "reason": "Processing failure"},
        200,
    )
    assert list_stock(client)[container["id"]]["available"] == "19.000"
    assert (
        client.get("/api/library/physical/" + agar["id"]).json()["lifecycle"]
        == "completed"
    )
    assert upload(client, "physical", agar["id"]).status_code == 201


def test_spore_inoculation_creates_pending_independent_establishments(client):
    raw, container = setup_preparation(client, "agar_plate")
    batch = prepare(client, raw, container, 2)
    spore = client.post("/api/library/spores", json={}).json()
    inoculate(
        client,
        spore,
        batch["materials"],
        source_kind="spores",
        unit="print",
        usage_per_container=None,
    )
    assert client.get("/api/library/lines").json() == []
    assert client.get("/api/library/physical").json() == []
    established = []
    for prepared in batch["materials"]:
        r = client.post(
            "/api/provenance/spores/" + spore["id"] + "/establish",
            json={"prepared_id": prepared["id"]},
        )
        assert r.status_code == 201, r.text
        established.append(r.json())
    assert established[0]["line"]["id"] != established[1]["line"]["id"]
    assert {r["physical"][0]["id"] for r in established} == {
        r["id"] for r in batch["materials"]
    }
    assert (
        client.get("/api/provenance/lines/" + established[0]["line"]["id"]).json()[
            "parents"
        ]
        == []
    )
    duplicate = client.post(
        "/api/provenance/spores/" + spore["id"] + "/establish",
        json={"prepared_id": batch["materials"][0]["id"]},
    )
    assert duplicate.status_code == 409
    assert len(client.get("/api/library/lines").json()) == 2


def test_invalid_readiness_source_units_and_atomic_write_failure(client):
    raw, container = setup_preparation(client, "spawn_bag")
    batch = prepare(client, raw, container, 2)
    source = lc_source(client, "100")
    with client.app.state.engine.begin() as connection:
        connection.execute(text("UPDATE prepared_materials SET stage='preparing'"))
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [m["id"] for m in batch["materials"]],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "5",
            "unit": "mL",
        },
        409,
    )
    post(
        client,
        "ready",
        {"prepared_ids": [row["id"] for row in batch["materials"]]},
        200,
    )
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [m["id"] for m in batch["materials"]],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "5",
            "unit": "g",
        },
        422,
    )
    before = list_stock(client)

    inserted = []

    def reject(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO spawn"):
            inserted.append(parameters)
            if len(inserted) == 2:
                raise RuntimeError("Simulated persistence failure")

    sql_event.listen(client.app.state.engine, "before_cursor_execute", reject)
    with pytest.raises(RuntimeError, match="Simulated"):
        inoculate(client, source, batch["materials"])
    sql_event.remove(client.app.state.engine, "before_cursor_execute", reject)
    assert list_stock(client) == before
    assert client.get("/api/library/spawn").json() == []
    assert all(
        m["stage"] == "ready" for m in client.get("/api/preparation/materials").json()
    )


def test_concurrent_pool_capacity_and_idempotent_inoculation(client):
    raw, container = setup_preparation(client, "spawn_jar", 5)
    body = {
        "material_type": "spawn_jar",
        "count": 5,
        "container_item_id": container["id"],
        "ingredients": [{"item_id": raw["id"], "quantity": "50", "unit": "g"}],
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    "/api/preparation/prepare",
                    json={**body, "request_key": str(uuid4())},
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    materials = client.get("/api/preparation/materials").json()
    source = lc_source(client, "25")
    payload = {
        "prepared_ids": [m["id"] for m in materials],
        "source_kind": "physical",
        "source_id": source["id"],
        "usage_per_container": "5",
        "unit": "mL",
        "request_key": "concurrent-inoculation",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post("/api/preparation/inoculate", json=payload),
                range(2),
            )
        )
    assert (
        all(r.status_code == 201 for r in results)
        and results[0].json() == results[1].json()
    )
    assert len(client.get("/api/library/spawn").json()) == 5


def test_opening_pools_are_explicit_and_invalid_quantities_rejected(client):
    assert client.get("/api/preparation/stock").json() == []
    post(
        client,
        "stock",
        {
            "name": "Plates",
            "category": "reusable",
            "unit": "count",
            "available": None,
            "container_type": "agar_plate",
            "reason": "Opening",
        },
        422,
    )
    post(
        client,
        "stock",
        {
            "name": "Plates",
            "category": "reusable",
            "unit": "count",
            "available": "0.5",
            "container_type": "agar_plate",
            "reason": "Opening",
        },
        422,
    )
    stock(
        client,
        "Shoebox trays",
        "reusable",
        "count",
        "6",
        container_type="fruiting_tray",
    )
    assert len(client.get("/api/preparation/stock").json()) == 1
    assert client.get("/api/library/fruiting").json() == []


def test_migration_restart_preserves_preparation_stock_and_existing_photos(settings):
    with TestClient(create_app(settings)) as client:
        source = lc_source(client, "50")
        photo = upload(client, "physical", source["id"]).json()
        original = client.get(photo["url"]).content
        raw, container = setup_preparation(client, "spawn_jar", 6)
        batch = prepare(client, raw, container, 5)
        inoculate(client, source, batch["materials"])
    with TestClient(create_app(settings)) as client:
        assert client.get(photo["url"]).content == original
        assert len(client.get("/api/preparation/materials").json()) == 5
        assert list_stock(client)[container["id"]]["available"] == "1.000"
        assert (
            client.get("/api/library/physical/" + source["id"]).json()[
                "remaining_quantity"
            ]
            == "25.000"
        )
    command.check(migration_config(settings))
    with pytest.raises(RuntimeError, match="inventory data exists"):
        command.downgrade(migration_config(settings), "0004_acquisition")


def test_committed_audit_and_snapshot_are_immutable(client):
    raw, container = setup_preparation(client, "spawn_bag")
    prepare(client, raw, container, 1)
    for query in [
        "UPDATE inventory_operations SET result='{}'",
        "DELETE FROM inventory_operations",
        "UPDATE preparation_batches SET snapshot='{}'",
    ]:
        with pytest.raises(IntegrityError):
            with client.app.state.engine.begin() as c:
                c.execute(text(query))
    assert client.get("/api/preparation/operations").status_code == 200


def test_measured_inventory_cannot_be_retyped_and_liquid_syringe_conserves_volume(
    client,
):
    source = lc_source(client, "10")
    assert (
        client.patch(
            "/api/library/physical/" + source["id"],
            json={"material_type": "agar_plate"},
        ).status_code
        == 409
    )
    raw, container = setup_preparation(client, "lc_syringe")
    batch = prepare(client, raw, container, 1)
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [batch["materials"][0]["id"]],
            "source_kind": "physical",
            "source_id": source["id"],
            "usage_per_container": "5",
            "unit": "mL",
            "destination_volume_ml": "20",
        },
        422,
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "10.000"
    )


@pytest.mark.parametrize("source_type", ["agar_plate", "lc_jar"])
def test_lc_container_inoculation_preserves_line_from_agar_or_lc(client, source_type):
    raw, container = setup_preparation(client, "lc_jar", 2)
    batch = prepare(client, raw, container, 1)
    source = receive(client, count=1, material={"material_type": source_type})[
        "physical"
    ][0]
    result = inoculate(
        client,
        source,
        batch["materials"],
        unit="plate" if source_type == "agar_plate" else "mL",
        usage_per_container=None if source_type == "agar_plate" else "1",
        destination_volume_ml="50",
    )
    destination = client.get(
        "/api/library/physical/" + result["materials"][0]["physical_id"]
    ).json()
    assert (
        destination["material_type"] == "lc_jar"
        and destination["line_id"] == source["line_id"]
    )
    assert destination["remaining_quantity"] == "50.000"
    assert len(client.get("/api/library/lines").json()) == 1


def test_terminal_lifecycle_excludes_dashboard_and_closes_stock_without_losing_balance(
    client,
):
    source = lc_source(client, "30")
    assert client.get("/api/dashboard/summary").json()["counts"]["active_cultures"] == 1
    post(
        client,
        "records/physical/" + source["id"] + "/finish",
        {"action": "failed", "reason": "Explicit failure"},
        200,
    )
    assert client.get("/api/dashboard/summary").json()["counts"]["active_cultures"] == 0
    row = client.get("/api/library/physical/" + source["id"]).json()
    assert row["remaining_quantity"] == "30.000" and row["lifecycle"] == "failed"
    assert list_stock(client)[row["stock_item_id"]]["status"] == "archived"
    assert (
        client.get("/api/preparation/transactions").json()[0]["entry_type"] == "closed"
    )


def test_invalid_history_kind_is_validated(client):
    assert client.get("/api/preparation/records/invalid/ID").status_code == 422


def test_spore_to_grain_rejected_without_consumption_or_line_creation(client):
    raw, container = setup_preparation(client, "spawn_bag")
    batch = prepare(client, raw, container, 1)
    spore = client.post("/api/library/spores", json={}).json()
    before = list_stock(client)
    post(
        client,
        "inoculate",
        {
            "prepared_ids": [batch["materials"][0]["id"]],
            "source_kind": "spores",
            "source_id": spore["id"],
            "unit": "print",
        },
        422,
    )
    assert list_stock(client) == before
    assert client.get("/api/library/lines").json() == []
    assert client.get("/api/preparation/materials").json()[0]["stage"] == "ready"
