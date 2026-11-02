"""Exact converted stock accounting and compatibility with deployed history."""

from decimal import Decimal
import hashlib
import json
import sqlite3
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.database import migration_config
from app.main import create_app
from test_foundation import client, settings  # noqa: F401
from test_preparation import (
    stock,
    post,
    prepare,
    setup_preparation,
    list_stock,
    lc_source,
    inoculate,
)


@pytest.mark.parametrize("category", ["ingredient", "consumable", "equipment", "other"])
def test_generic_inventory_storage_and_no_sample_stock(client, category):
    assert client.get("/api/preparation/stock").json() == []
    item = stock(
        client,
        name="Actual supply",
        category=category,
        unit="each",
        available="2",
        storage_location="Shelf A",
        notes="Counted",
    )
    assert item["unit"] == "count" and item["available"] == "2.000"
    assert item["storage_location"] == "Shelf A"
    assert list_stock(client)[item["id"]] == item
    assert len(client.get("/api/preparation/transactions").json()) == 1


@pytest.mark.parametrize(
    "unit,amount,expected,base",
    [
        ("mg", "100", ".100", "g"),
        ("g", "5", "5", "g"),
        ("kg", "2", "2", "kg"),
        ("oz", "1", "28.349523125", "g"),
        ("lb", "2", "907.18474", "g"),
        ("mL", "5", "5", "mL"),
        ("L", "2", "2", "L"),
        ("us_fl_oz", "32", "946.352946", "mL"),
        ("us_cup", "1", "236.5882365", "mL"),
    ],
)
def test_opening_units_are_converted_exactly_and_audited(
    client, unit, amount, expected, base
):
    item = stock(client, unit=unit, available=amount)
    assert item["unit"] == base and Decimal(item["available"]) == Decimal(expected)
    entry = client.get("/api/preparation/transactions").json()[0]
    assert Decimal(entry["after_quantity"]) == Decimal(expected)
    assert Decimal(entry["amount"]) == Decimal(expected)


def test_converted_debits_replays_tiny_remaining_and_insufficient_balance(client):
    raw = stock(client, unit="lb", available="1")
    _, pool = setup_preparation(client, "agar_plate", 4)
    body = {
        "material_type": "agar_plate",
        "count": 1,
        "container_item_id": pool["id"],
        "ingredients": [{"item_id": raw["id"], "quantity": "15.999", "unit": "oz"}],
    }
    first = post(client, "prepare", body, key="precise-converted-batch")
    assert post(client, "prepare", body, key="precise-converted-batch") == first
    remainder = Decimal(".028349523125")
    assert Decimal(list_stock(client)[raw["id"]]["available"]) == remainder
    body["ingredients"][0]["quantity"] = ".002"
    before = list_stock(client)
    post(client, "prepare", body, 409)
    assert list_stock(client) == before
    body["ingredients"][0]["quantity"] = ".001"
    post(client, "prepare", body)
    assert Decimal(list_stock(client)[raw["id"]]["available"]) == 0
    entries = client.get("/api/preparation/transactions?item_id=" + raw["id"]).json()
    assert Decimal(entries[0]["before_quantity"]) == remainder
    assert Decimal(entries[0]["amount"]) == -remainder


@pytest.mark.parametrize(
    "source,target", [("g", "mL"), ("mL", "oz"), ("count", "g"), ("plate", "count")]
)
def test_cross_dimension_recipe_and_adjustment_rejected_without_writes(
    client, source, target
):
    item = stock(client, unit=source, available="100")
    before = list_stock(client)
    recipe = {
        "name": "Invalid conversion",
        "recipe_type": "agar",
        "batch_yield": 1,
        "ingredients": [{"item_id": item["id"], "quantity": "1", "unit": target}],
    }
    post(client, "recipes", recipe, 422)
    post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": "1",
            "unit": target,
            "expected_revision": item["revision"],
            "reason": "Measured",
        },
        422,
    )
    assert list_stock(client) == before
    assert len(client.get("/api/preparation/transactions").json()) == 1


def test_legacy_kg_and_liter_stock_accept_compatible_recipe_and_addition(client):
    raw = stock(client, unit="kg", available="1")
    _, pool = setup_preparation(client, "spawn_jar", 2)
    batch = prepare(
        client,
        raw,
        pool,
        1,
        ingredients=[{"item_id": raw["id"], "quantity": "1", "unit": "lb"}],
    )
    assert batch["materials"][0]["stage"] == "ready"
    assert Decimal(list_stock(client)[raw["id"]]["available"]) == Decimal(".54640763")
    water = stock(client, unit="L", available="1")
    updated = post(
        client,
        f"stock/{water['id']}/adjust",
        {
            "mode": "add",
            "quantity": "1",
            "unit": "us_fl_oz",
            "expected_revision": water["revision"],
            "reason": "Measured addition",
        },
        200,
    )
    assert Decimal(updated["available"]) == Decimal("1.0295735295625")


def test_volume_conversion_for_lc_fill_preserves_line_and_depletes_exactly(client):
    source = lc_source(client)
    stock(
        client,
        category="source",
        unit="us_fl_oz",
        available="1",
        source_kind="physical",
        source_id=source["id"],
    )
    raw, supply = setup_preparation(client, "lc_syringe", 2)
    batch = prepare(client, raw, supply, 2)
    result = inoculate(
        client, source, batch["materials"], usage_per_container=".5", unit="us_fl_oz"
    )
    assert all(row["stage"] == "inoculated" for row in result["materials"])
    original = client.get("/api/library/physical/" + source["id"]).json()
    assert (
        original["lifecycle"] == "depleted"
        and Decimal(original["remaining_quantity"]) == 0
    )
    for row in result["materials"]:
        destination = client.get("/api/library/physical/" + row["id"]).json()
        assert Decimal(destination["remaining_quantity"]) == Decimal("14.78676478125")
        assert destination["line_id"] == source["line_id"]
    assert len(client.get("/api/library/lines").json()) == 1


def test_reconciliation_matches_live_allocations_and_one_time_release(client):
    raw, pool = setup_preparation(client, "agar_plate", 20)
    batch = prepare(client, raw, pool, 13)
    source = lc_source(client, "100")
    inoculate(client, source, batch["materials"][:8])
    row = client.get("/api/preparation/pools").json()[0]
    assert row == {
        "item_id": pool["id"],
        "name": pool["name"],
        "available": "7.000",
        "ready": 5,
        "inoculated": 8,
        "preparing": 0,
        "other_reserved": 0,
        "reserved": 13,
        "total": "20.000",
    }
    post(
        client,
        f"materials/{batch['materials'][0]['id']}/finish",
        {"action": "complete", "reason": "Transfers finished"},
        200,
    )
    post(
        client,
        f"materials/{batch['materials'][0]['id']}/finish",
        {"action": "complete", "reason": "Duplicate"},
        409,
    )
    row = client.get("/api/preparation/pools").json()[0]
    assert (
        row["available"] == "8.000"
        and row["inoculated"] == 7
        and row["total"] == "20.000"
    )


def test_substrate_variants_are_definitions_only(client):
    raw, pool = setup_preparation(client, "spawn_bag")
    body = {
        "name": "Oyster substrate",
        "recipe_type": "substrate",
        "batch_yield": 5,
        "ingredients": [{"item_id": raw["id"], "quantity": "1", "unit": "lb"}],
    }
    first = post(client, "recipes", body)
    second = post(client, "recipes", {**body, "name": "Low supplement substrate"})
    assert first["id"] != second["id"]
    before = list_stock(client)
    post(
        client,
        "prepare",
        {
            "material_type": "spawn_bag",
            "container_item_id": pool["id"],
            "count": 1,
            "recipe_id": first["id"],
        },
        422,
    )
    assert (
        list_stock(client) == before
        and client.get("/api/preparation/materials").json() == []
    )


def test_upgrade_preserves_old_preparing_ledger_reservation_snapshot_and_retry(
    settings,
):
    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0006_history")
    payload = {
        "request_key": "historical-opening",
        "name": "Old plates",
        "category": "reusable",
        "unit": "count",
        "available": "20",
        "container_type": "agar_plate",
        "source_kind": None,
        "source_id": None,
        "notes": None,
        "reason": "Counted",
    }
    fingerprint = hashlib.sha256(
        ("stock_opening" + json.dumps(payload, sort_keys=True)).encode()
    ).hexdigest()
    snapshot = {
        "ingredients": [],
        "recipe": None,
        "processing": {},
        "container_name": "Old plates",
        "preparation_date": "2026-01-01",
        "notes": "Historical",
    }
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO stock_items (id,name,category,unit,available,container_type,status,revision,created_at) VALUES ('INV-0042','Old plates','reusable','count',19,'agar_plate','active',2,'2026-01-01')"
        )
        result = {
            "id": "INV-0042",
            "name": "Old plates",
            "category": "reusable",
            "unit": "count",
            "available": "20.000",
            "container_type": "agar_plate",
            "physical_id": None,
            "spore_id": None,
            "notes": None,
            "status": "active",
            "revision": 1,
            "created_at": "2026-01-01",
        }
        connection.execute(
            "INSERT INTO inventory_operations VALUES (?,?,?,?,?,?,?)",
            (
                "OP-0042",
                payload["request_key"],
                fingerprint,
                "stock_opening",
                json.dumps(payload),
                json.dumps(result),
                "2026-01-01",
            ),
        )
        connection.execute(
            "INSERT INTO stock_transactions (operation_id,item_id,entry_type,amount,unit,before_quantity,after_quantity,reason,created_at) VALUES ('OP-0042','INV-0042','reserve',-1,'count',20,19,'Historical preparation','2026-01-01')"
        )
        connection.execute(
            "INSERT INTO preparation_batches VALUES ('PB-0042','OP-0042',NULL,?,'2026-01-01')",
            (json.dumps(snapshot),),
        )
        connection.execute(
            "INSERT INTO prepared_materials VALUES ('AG-0042','PB-0042','agar_plate','preparing',NULL,NULL,NULL,'2026-01-01')"
        )
        connection.execute(
            "INSERT INTO container_reservations VALUES ('AG-0042','INV-0042',0)"
        )
        before_ledger = connection.execute(
            "SELECT * FROM stock_transactions"
        ).fetchall()
    with TestClient(create_app(settings)) as client:
        old = client.get("/api/preparation/materials/AG-0042").json()
        assert (
            old["stage"] == "preparing"
            and old["created_at"] == "2026-01-01"
            and old["snapshot"] == snapshot
        )
        assert post(client, "stock", payload)["available"] == "20.000"
        pool = client.get("/api/preparation/pools").json()[0]
        assert pool["preparing"] == 1 and pool["total"] == "20.000"
        post(client, "ready", {"prepared_ids": [old["id"]]}, 200)
        assert client.get("/api/preparation/materials/AG-0042").json() == {
            **old,
            "stage": "ready",
        }
        assert list_stock(client)["INV-0042"]["available"] == "19.000"
        with client.app.state.engine.connect() as connection:
            after = connection.exec_driver_sql(
                "SELECT * FROM stock_transactions"
            ).fetchall()
            assert [tuple(row[:10]) for row in after] == before_ledger
            assert (
                connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            )
        with pytest.raises(IntegrityError):
            with client.app.state.engine.begin() as connection:
                connection.execute(
                    text("UPDATE stock_transactions SET reason='Rewritten'")
                )
    command.check(migration_config(settings))
