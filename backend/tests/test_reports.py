from uuid import uuid4
from decimal import Decimal
import json
import pytest
from sqlalchemy import event, text
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn, stage, harvest, cmd, source
from test_provenance import acquisition, grow
from test_direct_creation import recipe


def report(client, **filters):
    r = client.get("/api/reports/performance", params=filters)
    assert r.status_code == 200, r.text
    return r.json()


def finish(
    client, row, weights=(("100",),), outcome="complete", closing="2026-01-20", dry=None
):
    code = row["id"]
    if weights:
        stage(client, code, "pinning", "2026-01-03")
        stage(client, code, "fruiting", "2026-01-05")
        for number, entries in enumerate(weights, 1):
            if number > 1:
                stage(client, code, "next_flush", "2026-01-10")
                stage(client, code, "fruiting", "2026-01-12")
            for weight in entries:
                harvest(
                    client,
                    code,
                    wet_grams=weight,
                    dry_grams=dry,
                    harvest_date="2026-01-07" if number == 1 else "2026-01-15",
                )
    if outcome != "active":
        stage(client, code, outcome, closing)
    return code


def test_empty_report_no_zero_averages_or_mutations(client):
    before = client.get("/api/library/fruiting").json()
    queries = []

    def capture(conn, cursor, sql, params, ctx, many):
        queries.append(sql)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        data = report(client)
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
    assert data["summary"]["average_wet_grams"] is None
    assert data["summary"]["total_known_wet_grams"] is None
    assert data["summary"]["failure_rate_percent"] is None
    assert data["groups"] == data["records"] == data["flushes"] == []
    assert len([q for q in queries if q.lstrip().upper().startswith("SELECT")]) == 4
    assert not any(
        q.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE"))
        for q in queries
    )
    assert client.get("/api/library/fruiting").json() == before
    assert client.post("/api/reports/performance").status_code == 405


def test_completed_per_container_average_shared_spawn_partial_zero_failed_active(
    client,
):
    rows = spawn(client, count=2)
    finish(client, rows[0], (("100", "50"), ("100",)), dry="10")
    finish(client, rows[1], (("150",),), dry="15")
    finish(client, spawn(client)[0], (("0",),), dry="0")
    finish(client, spawn(client)[0], (("25", None),))
    finish(client, spawn(client)[0], ())
    finish(client, spawn(client)[0], (("40",),), outcome="failed")
    active = finish(client, spawn(client)[0], (("800",),), outcome="active")
    data = report(client)
    stats = data["summary"]
    assert stats["completed"] == 5 and stats["failed"] == 1
    assert stats["terminal_count"] == 6
    assert stats["qualifying_containers"] == 3
    assert stats["excluded_incomplete_wet"] == 2
    assert Decimal(stats["average_wet_grams"]) == Decimal("133.333")
    assert Decimal(stats["qualifying_wet_total_grams"]) == 400
    assert Decimal(stats["total_known_wet_grams"]) == 465
    assert Decimal(stats["failed_known_wet_grams"]) == 40
    assert stats["wet_measurement_count"] == 7 and stats["harvest_count"] == 8
    assert stats["distinct_spawn_sources"] == 2
    assert Decimal(stats["failure_rate_percent"]) == Decimal("16.667")
    assert stats["average_dry_grams"] == {
        "value": "15.000",
        "sample_count": 3,
        "missing_count": 2,
    }
    assert stats["days_to_first_pinning"] == {
        "value": "2.000",
        "sample_count": 4,
        "missing_count": 1,
    }
    assert stats["days_to_first_harvest"] == {
        "value": "6.000",
        "sample_count": 4,
        "missing_count": 1,
    }
    assert stats["cycle_days"] == {
        "value": "19.000",
        "sample_count": 5,
        "missing_count": 0,
    }
    assert [r["id"] for r in data["active_records"]] == [active]
    assert active not in data["groups"][0]["record_ids"]
    assert data["groups"][0]["ranked"] and not data["groups"][0]["preliminary"]
    f1, f2 = data["flushes"]
    assert (
        f1["containers_reached"],
        f1["qualifying_containers"],
        f1["excluded_incomplete_wet"],
    ) == (5, 3, 2)
    assert Decimal(f1["average_wet_grams"]) == 100
    assert (f2["containers_reached"], f2["qualifying_containers"]) == (1, 1)
    assert Decimal(f2["average_wet_grams"]) == 100
    assert len(report(client, group_by="line")["groups"]) == 5


def test_decimal_weights_use_exact_milligram_sums(client):
    row = spawn(client)[0]
    finish(client, row, (("0.100", "0.200", "0.001"),))
    stats = report(client)["summary"]
    assert stats["average_wet_grams"] == "0.301"
    assert Decimal(stats["total_known_wet_grams"]) == Decimal("0.301")


def test_missing_harvest_is_not_measured_zero_and_small_samples_are_preliminary(client):
    finish(client, spawn(client)[0], ())
    data = report(client)
    assert data["summary"]["average_wet_grams"] is None
    assert data["summary"]["qualifying_containers"] == 0
    assert not data["groups"][0]["ranked"]
    finish(client, spawn(client)[0], (("0",),))
    data = report(client)
    assert data["summary"]["average_wet_grams"] == "0.000"
    assert data["groups"][0]["preliminary"] and data["groups"][0]["ranked"]


def test_exact_line_attribution_same_strain_mixed_lines_and_unknowns(client):
    a = acquisition(client, inline_strain={"name": "Oyster"})
    b = acquisition(client, strain_id=a["line"]["strain_id"])
    unknown = acquisition(client)
    other = acquisition(client, inline_strain={"name": "Chestnut"})
    rows = []
    for ids in [
        [a["records"][0]["id"], b["records"][0]["id"]],
        [a["records"][0]["id"], other["records"][0]["id"]],
        [a["records"][0]["id"], unknown["records"][0]["id"]],
        [unknown["records"][0]["id"]],
    ]:
        row = grow(client, ids)["containers"][0]
        finish(client, row)
        rows.append(row)
    data = report(client)
    assert [r["strain_identity"] for r in data["records"]] == [
        "known",
        "mixed",
        "partial",
        "unknown",
    ]
    assert [r["line_identity"] for r in data["records"]] == [
        "mixed",
        "mixed",
        "mixed",
        "known",
    ]
    assert [g["key"] for g in data["groups"] if g["ranked"]] == [a["line"]["strain_id"]]
    lines = report(client, group_by="line")
    # The explicitly tracked unknown-strain line is a real line, not invented ancestry.
    assert [g["key"] for g in lines["groups"] if g["ranked"]] == [unknown["line"]["id"]]
    filtered = report(client, strain_id=a["line"]["strain_id"])
    assert [r["id"] for r in filtered["records"]] == [rows[0]["id"]]


def test_specific_allocations_and_acquired_fruiting_line_without_spawn(client):
    a = acquisition(client, inline_strain={"name": "Oyster"})
    b = acquisition(client, inline_strain={"name": "Chestnut"})
    ids = [a["records"][0]["id"], b["records"][0]["id"]]
    allocated = grow(client, ids, mode="specific", allocations=[[ids[0]], [ids[1]]])[
        "containers"
    ]
    for row in allocated:
        finish(client, row)
    acquired = acquisition(
        client,
        "fruiting_bag",
        existing_line_id=a["line"]["id"],
        strain_id=a["line"]["strain_id"],
        line=None,
    )["records"][0]
    finish(client, acquired)
    data = report(client)
    assert data["records"][0]["spawn_ids"] == [ids[0]]
    assert data["records"][1]["spawn_ids"] == [ids[1]]
    acq = next(r for r in data["records"] if r["id"] == acquired["id"])
    assert acq["line_ids"] == [a["line"]["id"]] and acq["spawn_ids"] == []
    oyster = next(g for g in data["groups"] if g["key"] == a["line"]["strain_id"])
    assert oyster["stats"]["containers_without_known_spawn"] == 1


def test_species_filter_requires_all_sources_to_have_same_recorded_scientific_name(
    client,
):
    a = acquisition(
        client,
        inline_strain={"name": "Oyster", "scientific_name": "Pleurotus ostreatus"},
    )
    b = acquisition(
        client,
        inline_strain={"name": "Blue Oyster", "scientific_name": "Pleurotus ostreatus"},
    )
    c = acquisition(client, inline_strain={"name": "Unknown species"})
    for sources in [
        [a["records"][0]["id"]],
        [a["records"][0]["id"], b["records"][0]["id"]],
        [a["records"][0]["id"], c["records"][0]["id"]],
    ]:
        finish(client, grow(client, sources)["containers"][0])
    data = report(client, species="Pleurotus ostreatus")
    assert len(data["records"]) == 2
    assert len([g for g in data["groups"] if g["ranked"]]) == 1
    assert data["options"]["species"] == ["Pleurotus ostreatus"]


def test_terminal_date_filter_inclusive_failure_dates_and_active_separate(client):
    first = spawn(client)[0]
    finish(client, first, closing="2026-01-20")
    second = spawn(client)[0]
    finish(client, second, outcome="failed", closing="2026-02-01")
    active = spawn(client)[0]
    data = report(client, start_date="2026-01-20", end_date="2026-01-20")
    assert [r["id"] for r in data["records"]] == [first["id"]]
    assert data["summary"]["failed"] == 0
    assert data["terminal_containers_outside_period"] == 1
    assert data["active_records"][0]["id"] == active["id"]
    data = report(client, start_date="2026-02-01")
    assert data["summary"]["failed"] == 1 and data["summary"]["completed"] == 0
    assert data["summary"]["average_wet_grams"] is None
    assert data["summary"]["total_known_wet_grams"] == "100"


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-03-01", "end_date": "2026-01-01"},
        {"start_date": "invalid"},
        {"strain_id": "STR-missing"},
        {"species": "Guessed"},
        {"group_by": "potency"},
    ],
)
def test_invalid_filters_are_read_only_validation_errors(client, params):
    assert client.get("/api/reports/performance", params=params).status_code == 422


def test_original_recipe_identity_and_snapshots_revision_changes_not_current_contents(
    client,
):
    formula = recipe(client, "substrate")
    first = spawn(client, formula=formula)[0]
    finish(client, first, dry="10")
    updated = client.put(
        f"/api/preparation/recipes/{formula['id']}",
        json={
            **{
                k: v
                for k, v in formula.items()
                if k
                not in [
                    "id",
                    "revision",
                    "created_at",
                    "updated_at",
                    "used",
                    "is_lc_default",
                ]
            },
            "request_key": str(uuid4()),
            "expected_revision": formula["revision"],
            "name": "Renamed substrate",
            "instructions": "Changed instructions",
        },
    )
    assert updated.status_code == 200, updated.text
    newer = updated.json()
    second = spawn(client, formula=newer)[0]
    finish(client, second, (("300",),), dry="30")
    data = report(client, group_by="recipe")
    assert len(data["groups"]) == 1
    group = data["groups"][0]
    assert group["key"] == formula["id"]
    assert group["name"] == formula["name"]
    assert Decimal(group["stats"]["average_wet_grams"]) == 200
    assert [r["revision"] for r in group["revisions"]] == [1, 2]
    assert group["revisions"][0]["snapshot"]["name"] == formula["name"]
    assert group["revisions"][1]["snapshot"]["instructions"] == "Changed instructions"
    assert group["revisions"][0]["record_ids"] == [first["id"]]


def test_legacy_finished_records_remain_unknown_undated_and_reused_labels_do_not_merge(
    client,
):
    original = acquisition(client, "fruiting_bag")["records"][0]
    with client.app.state.engine.begin() as c:
        c.execute(
            text("UPDATE fruiting_containers SET stage='finished' WHERE id=:id"),
            {"id": original["id"]},
        )
    data = report(client)
    assert data["summary"]["completed"] == 1
    assert data["summary"]["average_wet_grams"] is None
    assert data["records"][0]["outcome_date"] is None
    assert data["records"][0]["recipe_id"] is None
    assert data["summary"]["cycle_days"]["sample_count"] == 0
    assert report(client, start_date="2026-01-01")["undated_terminal_excluded"] == 1
    one = spawn(client)[0]
    finish(client, one, (("100",),))
    # Archive is record visibility, never exclusion of real history.
    assert (
        client.post(
            f"/api/library/fruiting/{one['id']}/status", json={"status": "archived"}
        ).status_code
        == 200
    )
    two = spawn(client)[0]
    finish(client, two, (("300",),))
    assert one["physical_label"] == two["physical_label"]
    data = report(client)
    assert data["summary"]["qualifying_containers"] == 2
    assert Decimal(data["summary"]["average_wet_grams"]) == 200
    assert {r["id"] for r in data["records"]} == {original["id"], one["id"], two["id"]}


def test_partial_strain_identity_and_legacy_timing_are_not_invented(
    client,
):
    a = acquisition(client, inline_strain={"name": "Known"})
    b = acquisition(client)
    row = grow(client, [a["records"][0]["id"], b["records"][0]["id"]])["containers"][0]
    finish(client, row)
    data = report(client)
    assert data["records"][0]["strain_identity"] == "partial"
    assert data["records"][0]["line_identity"] == "mixed"
    assert not data["groups"][0]["ranked"]
    assert data["summary"]["days_to_first_pinning"]["sample_count"] == 0
    assert data["summary"]["days_to_first_harvest"]["sample_count"] == 0
    assert data["summary"]["cycle_days"]["value"] is None


def test_query_count_remains_constant_for_multiple_containers(client):
    for row in spawn(client, count=4):
        finish(client, row)
    queries = []

    def capture(conn, cursor, sql, params, ctx, many):
        if sql.lstrip().upper().startswith("SELECT"):
            queries.append(sql)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        data = report(client, group_by="recipe")
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
    assert data["summary"]["qualifying_containers"] == 4
    assert len(queries) == 4


def test_dry_measurements_never_fill_missing_wet_weights(client):
    row = spawn(client)[0]
    finish(client, row, ((None,),), dry="20")
    data = report(client, group_by="recipe")
    assert data["summary"]["qualifying_containers"] == 0
    assert data["summary"]["average_wet_grams"] is None
    assert data["summary"]["total_known_wet_grams"] is None
    assert data["summary"]["average_dry_grams"] == {
        "value": "20.000",
        "sample_count": 1,
        "missing_count": 0,
    }
    assert data["groups"][0]["stats"]["average_dry_grams"]["value"] == "20.000"
    assert data["flushes"][0]["qualifying_containers"] == 0
    assert data["flushes"][0]["average_wet_grams"] is None
