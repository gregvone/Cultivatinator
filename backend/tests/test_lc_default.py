"""Automatic LC media selection is independent of measured culture volume."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_foundation import client, settings  # noqa: F401
from test_direct_creation import recipe, create
from test_preparation import post, lc_source, list_stock


def designate(client, r):
    return post(
        client,
        "lc-default",
        {"recipe_id": r["id"], "expected_revision": r["revision"]},
        200,
    )


def test_no_invented_default_and_required_one_time_setup(client):
    assert client.get("/api/preparation/lc-default").json() == {"recipe": None}
    assert client.get("/api/preparation/recipes").json() == []
    source = lc_source(client)
    create(client, "lc_jar", source, status=409)
    # Merely saving an LC formula does not silently designate it.
    media = recipe(client, "lc")
    create(client, "lc_jar", source, media, status=409)
    assert client.get("/api/preparation/materials").json() == []
    designated = designate(client, media)
    assert designated["recipe"]["is_lc_default"] is True
    result = create(client, "lc_jar", source, count=2, destination_volume_ml="100")
    for row in result["materials"]:
        assert row["snapshot"]["recipe_id"] == media["id"]
        assert row["snapshot"]["media_origin"] == "prepared"
        assert (
            client.get("/api/library/physical/" + row["id"]).json()[
                "remaining_quantity"
            ]
            == "100.000"
        )
    assert all(item["category"] == "source" for item in list_stock(client).values())


def test_only_one_designated_active_default_and_typed_validation(client):
    agar = recipe(client, "agar")
    post(
        client,
        "lc-default",
        {"recipe_id": agar["id"], "expected_revision": agar["revision"]},
        422,
    )
    formulas = [recipe(client, "lc", name="Media " + str(i)) for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda r: designate(client, r), formulas))
    current = client.get("/api/preparation/lc-default").json()["recipe"]
    assert current["id"] in {r["id"] for r in formulas}
    assert (
        sum(r["is_lc_default"] for r in client.get("/api/preparation/recipes").json())
        == 1
    )
    with client.app.state.engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM lc_media_default").scalar()
            == 1
        )
    post(
        client, "lc-default", {"recipe_id": current["id"], "expected_revision": 99}, 409
    )


def edit_recipe(client, r, **values):
    body = {
        key: r[key]
        for key in (
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
            **values,
            "expected_revision": r["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_default_edits_preserve_snapshots_and_syringes_inherit_original_media(client):
    donor = lc_source(client)
    media = recipe(client, "lc", name="Original medium")
    designate(client, media)
    jar = create(client, "lc_jar", donor, count=1, destination_volume_ml="100")[
        "materials"
    ][0]
    original_snapshot = jar["snapshot"]
    edited = edit_recipe(
        client,
        media,
        name="Edited medium",
        ingredients=[{"name": "New ingredient", "quantity": "5", "unit": "g"}],
    )
    second = create(client, "lc_jar", donor, count=1)["materials"][0]
    assert second["snapshot"]["recipe"]["name"] == "Edited medium"
    assert second["snapshot"]["recipe_revision"] == 2
    # Filling from the earlier jar inherits its old immutable formulation.
    result = create(
        client,
        "lc_syringe",
        {"id": jar["id"]},
        count=2,
        usage_per_container="5",
        key="fill-syringes-once",
    )
    assert (
        create(
            client,
            "lc_syringe",
            {"id": jar["id"]},
            count=2,
            usage_per_container="5",
            key="fill-syringes-once",
        )
        == result
    )
    for row in result["materials"]:
        snapshot = row["snapshot"]
        assert snapshot["recipe"]["name"] == "Original medium"
        assert snapshot["recipe_revision"] == 1
        assert (
            snapshot["media_origin"] == "source_transfer"
            and snapshot["media_source_id"] == jar["id"]
        )
        assert (
            snapshot["ingredients"] == []
            and snapshot["processing"] == {}
            and snapshot["preparation_date"] is None
        )
    assert (
        client.get("/api/library/physical/" + jar["id"]).json()["remaining_quantity"]
        == "90.000"
    )
    assert (
        client.get("/api/preparation/materials/" + jar["id"]).json()["snapshot"]
        == original_snapshot
    )
    archived = edit_recipe(client, edited, status="archived")
    assert archived["is_lc_default"] is False
    assert client.get("/api/preparation/lc-default").json()["recipe"] is None
    # A default is unnecessary for transferred media, even if its definition is archived.
    inherited = create(
        client,
        "lc_syringe",
        {"id": result["materials"][0]["id"]},
        count=1,
        usage_per_container="1",
    )["materials"][0]
    assert inherited["snapshot"]["recipe"]["name"] == "Original medium"
    create(client, "lc_jar", donor, status=409)


def test_acquired_syringe_source_does_not_invent_media_from_default(client):
    source = lc_source(client, "25")
    media = recipe(client, "lc")
    designate(client, media)
    result = create(client, "lc_syringe", source, count=5, usage_per_container="5")
    assert all(
        row["snapshot"]["recipe"] is None and row["snapshot"]["recipe_id"] is None
        for row in result["materials"]
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["lifecycle"]
        == "depleted"
    )
    create(client, "lc_syringe", source, count=1, usage_per_container="1", status=409)


def test_known_volume_batch_usage_and_correction_remain_precise(client):
    source = lc_source(client, "100")
    grain = recipe(client, "grain")
    result = create(
        client,
        "spawn_bag",
        source,
        grain,
        count=5,
        usage_per_container="5",
        key="five-bags-culture-usage",
    )
    assert (
        create(
            client,
            "spawn_bag",
            source,
            grain,
            count=5,
            usage_per_container="5",
            key="five-bags-culture-usage",
        )
        == result
    )
    record = client.get("/api/library/physical/" + source["id"]).json()
    assert record["remaining_quantity"] == "75.000"
    before = list_stock(client)
    create(
        client,
        "spawn_bag",
        source,
        grain,
        count=5,
        usage_per_container="20",
        status=409,
    )
    assert list_stock(client) == before
    item = before[record["stock_item_id"]]
    post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": "0",
            "expected_revision": item["revision"],
            "reason": "Measured empty",
        },
        200,
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["lifecycle"]
        == "depleted"
    )
    item = list_stock(client)[item["id"]]
    post(
        client,
        f"stock/{item['id']}/adjust",
        {
            "mode": "correct",
            "quantity": None,
            "expected_revision": item["revision"],
            "reason": "Measurement uncertain",
        },
        200,
    )
    record = client.get("/api/library/physical/" + source["id"]).json()
    assert record["remaining_quantity"] is None and record["lifecycle"] == "active"
    create(client, "spawn_jar", source, grain, count=1)
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        is None
    )


def test_default_cannot_be_deleted_or_silently_retyped(client):
    media = recipe(client, "lc")
    designate(client, media)
    response = client.request(
        "DELETE",
        "/api/preparation/recipes/" + media["id"],
        json={"expected_revision": media["revision"], "request_key": str(uuid4())},
    )
    assert response.status_code == 409
    response = client.put(
        "/api/preparation/recipes/" + media["id"],
        json={
            key: media[key]
            for key in (
                "name",
                "batch_yield",
                "ingredients",
                "instructions",
                "processing",
                "shelf_life_days",
            )
        }
        | {
            "recipe_type": "agar",
            "expected_revision": media["revision"],
            "request_key": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert (
        client.get("/api/preparation/lc-default").json()["recipe"]["id"] == media["id"]
    )


def test_0008_upgrade_does_not_choose_or_rewrite_old_lc_and_default_survives_restart(
    settings,
):
    import sqlite3
    from fastapi.testclient import TestClient
    from alembic import command
    from app.main import create_app
    from app.database import migration_config

    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0008_recipes")
    original = {
        "name": "Historical LC Media",
        "recipe_type": "lc",
        "batch_yield": 5,
        "ingredients": [{"name": "Nutrient", "quantity": "5", "unit": "g"}],
        "instructions": "Original formulation",
        "processing": {},
        "shelf_life_days": None,
    }
    encoded = json.dumps(original)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO preparation_recipes VALUES ('RCP-0090','Historical LC Media','lc',?,1,'active','2026-01-01',NULL)",
            (encoded,),
        )
    with TestClient(create_app(settings)) as first:
        assert first.get("/api/preparation/lc-default").json()["recipe"] is None
        media = first.get("/api/preparation/recipes/RCP-0090").json()
        assert media["updated_at"] is None
        designate(first, media)
        source = lc_source(first)
    with TestClient(create_app(settings)) as second:
        assert (
            second.get("/api/preparation/lc-default").json()["recipe"]["id"]
            == "RCP-0090"
        )
        created = create(second, "lc_jar", source, count=1)["materials"][0]
        assert created["snapshot"]["recipe"] == original
        with second.app.state.engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT contents FROM preparation_recipes WHERE id='RCP-0090'"
                ).scalar()
                == encoded
            )
            assert (
                connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            )
    command.check(migration_config(settings))


def test_default_change_does_not_change_committed_response_or_deduct_twice(client):
    source = lc_source(client, "100")
    first = recipe(client, "lc", name="First media")
    designate(client, first)
    result = create(
        client,
        "lc_jar",
        source,
        count=2,
        usage_per_container="2",
        key="jar-default-retry",
    )
    replacement = recipe(client, "lc", name="Replacement media")
    designate(client, replacement)
    assert (
        create(
            client,
            "lc_jar",
            source,
            count=2,
            usage_per_container="2",
            key="jar-default-retry",
        )
        == result
    )
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "96.000"
    )
    assert all(
        row["snapshot"]["recipe"]["name"] == "First media"
        for row in result["materials"]
    )
    fresh = create(client, "lc_jar", source, count=1, usage_per_container="2")
    assert fresh["materials"][0]["snapshot"]["recipe"]["name"] == "Replacement media"
