from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import sqlite3
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from alembic import command
from app.main import create_app
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_direct_creation import recipe, create
from test_preparation import lc_source, post
from test_library import receive, upload


def action(client, kind, code, action, expected=200, key=None, **extra):
    r = client.post(
        f"/api/containers/records/{kind}/{code}/state",
        json={
            "request_key": key or str(uuid4()),
            "action": action,
            "action_date": "2026-11-01",
            **extra,
        },
    )
    assert r.status_code == expected, r.text
    return r.json()


def jars(client, material="agar_plate", count=1, **extra):
    source = lc_source(client)
    formula = recipe(client, "grain" if material.startswith("spawn") else "agar")
    return create(client, material, source, formula, count=count, **extra)["materials"]


def available(client, kind="agar_plate"):
    return client.get(
        "/api/containers/available", params={"material_type": kind}
    ).json()


def test_lowest_available_reuse_new_choice_and_permanent_history(client):
    rows = jars(client, count=3)
    assert [r["physical_label"] for r in rows] == ["P-01", "P-02", "P-03"]
    assert all(r["growth_stage"] == "colonizing" for r in rows)
    assert all(r["inoculation_date"] == "2026-11-01" for r in rows)
    action(client, "physical", rows[1]["id"], "failed")
    assert available(client)["available"] == ["P-02"]
    reused = jars(client)[0]
    assert reused["physical_label"] == "P-02" and reused["id"] != rows[1]["id"]
    old = client.get("/api/library/physical/" + rows[1]["id"]).json()
    assert (
        old["physical_label"] == "P-02"
        and old["label_occupied"] is False
        and old["lifecycle"] == "failed"
    )
    action(client, "physical", rows[0]["id"], "failed")
    new = jars(client, label_choices=[{"new_label": True}])[0]
    assert new["physical_label"] == "P-04"
    assert jars(client)[0]["physical_label"] == "P-01"
    assert upload(client, "physical", old["id"]).status_code == 201
    history = client.get(f"/api/containers/records/physical/{old['id']}").json()
    assert history["assignments"][0]["release_date"] == "2026-11-01"


def test_manual_occupied_conflict_rolls_back_all_bulk_allocations(client):
    first = jars(client)[0]
    source = lc_source(client, "100")
    formula = recipe(client)
    before = available(client)
    create(
        client,
        "agar_plate",
        source,
        formula,
        count=2,
        usage_per_container="5",
        label_choices=[{"new_label": True}, {"label": first["physical_label"]}],
        status=409,
    )
    assert available(client) == before
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "100.000"
    )
    assert len(client.get("/api/preparation/materials").json()) == 1


def test_manual_free_label_is_reserved_ahead_of_automatic_bulk_choices(client):
    first = jars(client, count=3)
    action(client, "physical", first[0]["id"], "failed")
    action(client, "physical", first[1]["id"], "failed")
    rows = jars(client, count=2, label_choices=[{}, {"label": "P-01"}])
    assert [r["physical_label"] for r in rows] == ["P-02", "P-01"]


def test_concurrent_allocations_and_idempotent_bulk_retries(client):
    source = lc_source(client, "100")
    formula = recipe(client, "grain")

    def submit(index):
        return create(
            client,
            "spawn_jar",
            source,
            formula,
            count=3,
            usage_per_container="1",
            key=f"label-concurrent-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    labels = [r["physical_label"] for result in results for r in result["materials"]]
    assert len(labels) == len(set(labels)) == 6
    assert submit(0) == results[0]
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "94.000"
    )


@pytest.mark.parametrize(
    "destination,recipe_type",
    [
        ("agar_plate", "agar"),
        ("lc_jar", "lc"),
        ("spawn_jar", "grain"),
        ("spawn_bag", "grain"),
    ],
)
def test_one_ready_agar_consumed_once_for_entire_operation(
    client, destination, recipe_type
):
    source = jars(client)[0]
    formula = recipe(client, recipe_type)
    if recipe_type == "lc":
        post(
            client,
            "lc-default",
            {"recipe_id": formula["id"], "expected_revision": formula["revision"]},
            200,
        )
    create(
        client,
        destination,
        {"id": source["id"]},
        formula,
        count=5,
        unit="plate",
        status=409,
    )
    action(client, "physical", source["id"], "ready", key="mark-ready-operation")
    ready = client.get("/api/library/physical/" + source["id"]).json()
    assert ready["growth_stage"] == "ready" and ready["ready_date"] == "2026-11-01"
    result = create(
        client,
        destination,
        ready,
        formula,
        count=5,
        unit="plate",
        key="consume-plate-bulk",
    )
    assert (
        create(
            client,
            destination,
            ready,
            formula,
            count=5,
            unit="plate",
            key="consume-plate-bulk",
        )
        == result
    )
    used = client.get("/api/library/physical/" + source["id"]).json()
    assert used["lifecycle"] == "used" and used["used_date"] == "2026-11-01"
    assert (
        used["label_occupied"] is False
        and source["physical_label"] in available(client)["available"]
    )
    assert len({r["physical_label"] for r in result["materials"]}) == 5
    assert all(r["source"]["id"] == source["id"] for r in result["materials"])
    create(client, destination, ready, formula, count=1, unit="plate", status=409)
    action(client, "physical", source["id"], "ready", expected=409)
    with client.app.state.engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM label_assignments WHERE physical_id=:id"),
                {"id": source["id"]},
            ).scalar()
            == 1
        )


def test_failed_destination_transaction_keeps_source_ready_label_occupied(client):
    source = jars(client)[0]
    action(client, "physical", source["id"], "ready")
    formula = recipe(client, "grain")
    inserts = []

    def fail_second(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO spawn"):
            inserts.append(parameters)
            if len(inserts) == 2:
                raise RuntimeError("Injected label rollback")

    event.listen(client.app.state.engine, "before_cursor_execute", fail_second)
    with pytest.raises(RuntimeError, match="Injected"):
        create(
            client, "spawn_jar", {"id": source["id"]}, formula, count=5, unit="plate"
        )
    event.remove(client.app.state.engine, "before_cursor_execute", fail_second)
    record = client.get("/api/library/physical/" + source["id"]).json()
    assert record["growth_stage"] == "ready" and record["label_occupied"] is True
    assert available(client, "spawn_jar")["next_label"] == "J-01"
    assert client.get("/api/library/spawn").json() == []


def test_spawn_ready_failed_and_disposable_labels_never_reused(client):
    jar = jars(client, "spawn_jar")[0]
    assert jar["physical_label"] == "J-01" and jar["growth_stage"] == "colonizing"
    action(client, "spawn", jar["id"], "ready")
    assert client.get("/api/library/spawn/" + jar["id"]).json()["stage"] == "ready"
    action(client, "spawn", jar["id"], "failed", key="failed-spawn-label")
    action(client, "spawn", jar["id"], "failed", key="failed-spawn-label")
    action(client, "spawn", jar["id"], "failed", expected=409)
    assert jars(client, "spawn_jar")[0]["physical_label"] == "J-01"
    bag = jars(client, "spawn_bag")[0]
    action(client, "spawn", bag["id"], "failed")
    assert jars(client, "spawn_bag")[0]["physical_label"] == "B-02"
    assert available(client, "spawn_bag")["available"] == []


def test_lc_depletion_does_not_release_jar_but_retirement_does(client):
    source = lc_source(client, "10")
    assert source["physical_label"] == "L-01"
    syringes = create(client, "lc_syringe", source, count=2, usage_per_container="5")[
        "materials"
    ]
    record = client.get("/api/library/physical/" + source["id"]).json()
    assert record["lifecycle"] == "depleted" and record["label_occupied"]
    assert available(client, "lc_jar")["available"] == []
    action(client, "physical", source["id"], "complete")
    assert available(client, "lc_jar")["available"] == ["L-01"]
    assert len({r["physical_label"] for r in syringes}) == 2
    assert all(r["physical_label"].startswith("LS-") for r in syringes)
    action(client, "physical", syringes[0]["id"], "failed")
    assert available(client, "lc_syringe")["available"] == []


def test_fruiting_labels_archive_and_explicit_cycle_end_only(client):
    spawn = client.post(
        "/api/provenance/acquisitions", json={"entry_type": "spawn_jar", "line": {}}
    ).json()["records"][0]
    response = client.post(
        "/api/provenance/grows",
        json={
            "source_ids": [spawn["id"]],
            "containers": [
                {"material_type": "tray"},
                {"material_type": "other", "label_choice": {"reusable": True}},
                {"material_type": "bag"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    rows = response.json()["containers"]
    assert [r["physical_label"] for r in rows] == ["F-01", "F-02", "FD-01"]
    client.post(
        f"/api/library/fruiting/{rows[0]['id']}/status", json={"status": "archived"}
    )
    assert available(client, "tray")["available"] == []
    client.post(
        f"/api/library/fruiting/{rows[0]['id']}/status", json={"status": "active"}
    )
    client.patch(f"/api/library/fruiting/{rows[0]['id']}", json={"stage": "fruiting"})
    assert available(client, "tray")["available"] == []
    action(client, "fruiting", rows[0]["id"], "complete")
    assert available(client, "tray")["available"] == ["F-01"]
    action(client, "fruiting", rows[2]["id"], "failed")
    assert available(client, "bag")["available"] == []
    assert client.get("/api/library/spawn/" + spawn["id"]).json()["stage"] == "ready"
    assert (
        client.get("/api/library/spawn/" + spawn["id"]).json()["label_occupied"] is True
    )


def test_archive_keeps_label_occupied_and_number_expands(client):
    source = lc_source(client)
    formula = recipe(client, "grain")
    rows = create(client, "spawn_bag", source, formula, count=100)["materials"]
    assert rows[-1]["physical_label"] == "B-100"
    first = jars(client)[0]
    client.post(
        f"/api/library/physical/{first['id']}/status", json={"status": "archived"}
    )
    assert first["physical_label"] not in available(client)["available"]
    assert jars(client)[0]["physical_label"] == "P-02"


def test_legacy_records_are_unlabeled_until_explicit_assignment_and_ready(settings):
    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0009_lc_default")
    with sqlite3.connect(settings.database_path) as c:
        c.execute(
            "INSERT INTO culture_lines (id,origin,status,created_at) VALUES ('CL-0090','purchased','active','2026-01-01')"
        )
        c.execute(
            "INSERT INTO physical_cultures (id,line_id,material_type,registration_batch,status,created_at) VALUES ('AG-0090','CL-0090','agar_plate','old','active','2026-01-01')"
        )
        c.execute("INSERT INTO identity_sequences VALUES ('AG',90)")
    with TestClient(create_app(settings)) as client:
        old = client.get("/api/library/physical/AG-0090").json()
        assert old["physical_label"] is None and old["growth_stage"] is None
        assert old["created_at"] == "2026-01-01"
        assert old["ready_date"] is None
        media = recipe(client, "agar")
        create(client, "agar_plate", old, media, count=1, unit="plate", status=409)
        r = client.post(
            "/api/containers/records/physical/AG-0090/label",
            json={"request_key": "assign-existing-label"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["physical_label"] == "P-01"
        action(client, "physical", "AG-0090", "ready")
        created = create(
            client, "agar_plate", {"id": "AG-0090"}, media, count=1, unit="plate"
        )["materials"][0]
        assert created["id"] == "AG-0091" and created["physical_label"] == "P-02"
        assert (
            client.get("/api/library/physical/AG-0090").json()["physical_label"]
            == "P-01"
        )
    command.check(migration_config(settings))


def test_label_history_cannot_be_deleted_or_rewritten(client):
    row = jars(client)[0]
    action(client, "physical", row["id"], "failed")
    for statement in (
        "DELETE FROM label_assignments",
        "DELETE FROM container_labels",
        "UPDATE container_labels SET code='P-99'",
        "UPDATE label_assignments SET released_at=NULL",
    ):
        with pytest.raises(IntegrityError):
            with client.app.state.engine.begin() as c:
                c.execute(text(statement))


def test_pending_spore_agar_failure_releases_label_without_establishing_line(client):
    spore = client.post("/api/library/spores", json={}).json()
    row = create(
        client,
        "agar_plate",
        spore,
        recipe(client),
        count=1,
        source_kind="spores",
        unit="print",
    )["materials"][0]
    action(client, "prepared", row["id"], "failed")
    assert available(client)["available"] == ["P-01"]
    assert client.get("/api/library/lines").json() == []
    response = client.post(
        f"/api/provenance/spores/{spore['id']}/establish",
        json={"prepared_id": row["id"]},
    )
    assert response.status_code == 409
    assert jars(client)[0]["physical_label"] == "P-01"


def test_registering_explicitly_finished_fruiting_record_keeps_label_history(client):
    response = client.post(
        "/api/provenance/grows",
        json={"containers": [{"material_type": "tray", "stage": "finished"}]},
    )
    assert response.status_code == 201, response.text
    row = response.json()["containers"][0]
    assert row["physical_label"] == "F-01" and not row["label_occupied"]
    assert row["growth_stage"] == "completed"
    assert available(client, "tray")["available"] == ["F-01"]


def test_concurrent_manual_label_conflict_has_one_winner(client):
    freed = jars(client)[0]
    action(client, "physical", freed["id"], "failed")
    source = lc_source(client, "20")
    formula = recipe(client)

    def submit(index):
        return client.post(
            "/api/preparation/create",
            json={
                "request_key": f"manual-race-{index}",
                "material_type": "agar_plate",
                "source_kind": "physical",
                "source_id": source["id"],
                "recipe_id": formula["id"],
                "count": 1,
                "unit": "mL",
                "usage_per_container": "5",
                "inoculation_date": "2026-11-01",
                "label_choices": [{"label": "P-01"}],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert "occupied" in next(r for r in results if r.status_code == 409).text
    assert (
        client.get("/api/library/physical/" + source["id"]).json()["remaining_quantity"]
        == "15.000"
    )
    assert len(client.get("/api/preparation/materials").json()) == 2


def test_explicit_label_change_preserves_history_and_conflict_rolls_back(client):
    first, other = jars(client, count=2)
    path = f"/api/containers/records/physical/{first['id']}/label"
    response = client.post(
        path, json={"request_key": "change-conflict", "label": "P-02"}
    )
    assert response.status_code == 409
    assert client.get("/api/library/physical/" + first["id"]).json()["label_occupied"]
    assert available(client)["available"] == []
    response = client.post(
        path, json={"request_key": "explicit-new-label", "new_label": True}
    )
    assert response.status_code == 200 and response.json()["physical_label"] == "P-03"
    history = client.get(f"/api/containers/records/physical/{first['id']}").json()
    assert [r["code"] for r in history["assignments"]] == ["P-01", "P-03"]
    assert history["assignments"][0]["released_at"] is not None
    assert history["assignments"][1]["released_at"] is None
    assert available(client)["available"] == ["P-01"]
    action(client, "physical", first["id"], "failed")
    assert client.post(path, json={"request_key": "terminal-label"}).status_code == 409


def test_manual_fruiting_labels_reserve_requested_free_labels_before_auto(client):
    first = client.post(
        "/api/provenance/grows",
        json={"containers": [{"material_type": "tray"}, {"material_type": "tray"}]},
    ).json()["containers"]
    for row in first:
        action(client, "fruiting", row["id"], "complete")
    response = client.post(
        "/api/provenance/grows",
        json={
            "containers": [
                {"material_type": "tray"},
                {"material_type": "tray", "label_choice": {"label": "F-01"}},
            ]
        },
    )
    assert response.status_code == 201, response.text
    assert [r["physical_label"] for r in response.json()["containers"]] == [
        "F-02",
        "F-01",
    ]


@pytest.mark.parametrize(
    "destination,recipe_type",
    [
        ("agar_plate", "agar"),
        ("lc_jar", "lc"),
        ("spawn_jar", "grain"),
    ],
)
def test_agar_readiness_views_agree_and_stale_selected_source_is_rejected(
    client, destination, recipe_type
):
    source = jars(client)[0]
    formula = recipe(client, recipe_type)
    if recipe_type == "lc":
        post(
            client,
            "lc-default",
            {"recipe_id": formula["id"], "expected_revision": formula["revision"]},
            200,
        )

    def views():
        detail = client.get("/api/library/physical/" + source["id"]).json()
        listing = next(
            r
            for r in client.get("/api/library/physical").json()
            if r["id"] == source["id"]
        )
        growing = next(
            r
            for r in client.get("/api/preparation/growing?workspace=laboratory").json()
            if r["id"] == source["id"]
        )
        return [detail, listing, growing]

    assert all(
        r["growth_stage"] == "colonizing" and r["ready_date"] is None for r in views()
    )
    assert all(
        r["status"] == "active" for r in views()
    )  # Visibility does not imply Ready.
    create(client, destination, source, formula, count=2, unit="plate", status=409)
    action(client, "physical", source["id"], "ready")
    assert all(
        r["growth_stage"] == "ready" and r["ready_date"] == "2026-11-01"
        for r in views()
    )
    selected = views()[0]
    action(client, "physical", source["id"], "failed")
    before = client.get("/api/preparation/materials").json()
    labels_before = available(client, destination)
    create(client, destination, selected, formula, count=2, unit="plate", status=409)
    assert client.get("/api/preparation/materials").json() == before
    assert available(client, destination) == labels_before
    assert all(
        r["growth_stage"] == "failed" and not r["label_occupied"] for r in views()
    )
    assert "P-01" in available(client)["available"]
