"""Real enrollment, multi-recipe safety, provenance synchronization and corrections."""

from datetime import datetime, timezone
from uuid import uuid4
import json
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app import experiments as exp
from app import experiment_enrollment as en
from app.experiment_models import (
    ExperimentMembership as Member,
    ExperimentUnit as Unit,
    ExperimentEnrollmentEvent as Event,
    ExperimentGroup,
)
from app.fruiting_models import FruitingRun
from app.database import migration_config, Base
from app.backup_format import create_backup, check_archive
from test_foundation import client, settings  # noqa: F401
from test_experiments import create, action, post
from test_fruiting import spawn, source, stage, harvest
from test_direct_creation import recipe


def setup(client, category="substrate"):
    return action(client, create(client, category=category), "plan")


def participants(client, row):
    response = client.get(f"/api/experiments/{row['id']}/participants")
    assert response.status_code == 200, response.text
    return response.json()


def command_for(client, row, path, status=200, key=None, **data):
    p = participants(client, row)
    return post(
        client,
        f"/{row['id']}/{path}",
        status=status,
        key=key,
        expected_revision=p["revision"],
        reason="Confirmed test assignment",
        **data,
    )


def enroll(client, row, fr, group=0, status=200, **kw):
    p = participants(client, row)
    fact = next(c for c in p["candidates"] if c["fruiting_id"] == fr["id"])
    return command_for(
        client,
        row,
        "enroll",
        status=status,
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][group]["id"],
        fruiting_id=fr["id"],
        fingerprint=fact["fingerprint"],
        **kw,
    )


def rule(client, row, source_id, group=0, kind="spawn"):
    return command_for(
        client,
        row,
        "source-rules",
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][group]["id"],
        source_kind=kind,
        source_id=source_id,
    )


def allocation(client, row, src, recipes):
    return command_for(
        client,
        row,
        "creation-allocations",
        plan_revision=row["plan_revision"],
        spawn_id=src["id"],
        destinations=[
            dict(group_id=g["id"], recipe_id=r["id"], count=1)
            for g, r in zip(row["plan"]["groups"], recipes)
        ],
    )


def test_real_enrollment_overlap_shared_sources_and_repeated_observations(client):
    frs = spawn(client, 2)
    row = setup(client)
    other = setup(client)
    a = enroll(client, row, frs[0])
    enroll(client, row, frs[1], group=1)
    enroll(client, other, frs[0])
    p = participants(client, row)
    assert p["counts"]["containers"] == 2 and p["counts"]["treatment_units"] == 2
    assert p["counts"]["known_spawn_sources"] == 1
    assert p["counts"]["classification_counts"]["retrospective"] == 2
    assert all(m["flush_count"] == 1 for m in p["items"])
    stage(client, frs[0]["id"], "pinning", "2026-01-03")
    stage(client, frs[0]["id"], "fruiting", "2026-01-04")
    harvest(client, frs[0]["id"], harvest_date="2026-01-05", wet_grams="10")
    stage(client, frs[0]["id"], "next_flush", "2026-01-06")
    observed = participants(client, row)
    assert observed["counts"]["treatment_units"] == 2
    assert (
        next(m for m in observed["items"] if m["fruiting_id"] == frs[0]["id"])[
            "flush_count"
        ]
        == 2
    )
    assert client.get("/api/reports/performance").status_code == 200


def test_enrollment_replay_stale_evidence_and_unit_owner(client):
    frs = spawn(client, 2)
    row = setup(client)
    p = participants(client, row)
    f = p["candidates"][0]
    key = str(uuid4())
    payload = dict(
        expected_revision=p["revision"],
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][0]["id"],
        fruiting_id=f["fruiting_id"],
        fingerprint=f["fingerprint"],
        reason="Link",
    )
    a = post(client, f"/{row['id']}/enroll", key=key, **payload)
    assert post(client, f"/{row['id']}/enroll", key=key, **payload) == a
    post(client, f"/{row['id']}/enroll", status=409, **payload)
    fresh = participants(client, row)
    f2 = fresh["candidates"][0]
    command_for(
        client,
        row,
        "enroll",
        status=409,
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][0]["id"],
        fruiting_id=f2["fruiting_id"],
        fingerprint="stale",
    )
    command_for(
        client,
        row,
        "enroll",
        status=422,
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][0]["id"],
        fruiting_id=f2["fruiting_id"],
        fingerprint=f2["fingerprint"],
        unit_id=a["membership"]["unit_id"],
    )
    with pytest.raises(IntegrityError), Session(
        client.app.state.engine
    ) as s, s.begin():
        s.add(
            Member(
                experiment_id=row["id"],
                unit_id=a["membership"]["unit_id"],
                fruiting_id=f2["fruiting_id"],
                exposure_start="2026-01-01",
                classification="uncertain",
                evidence="{}",
            )
        )


def test_group_ownership_and_historical_plan_membership(client):
    frs = spawn(client, 2)
    row = setup(client)
    other = setup(client)
    p = participants(client, row)
    f = p["candidates"][0]
    command_for(
        client,
        row,
        "enroll",
        status=422,
        plan_revision=row["plan_revision"],
        group_id=other["plan"]["groups"][0]["id"],
        fruiting_id=f["fruiting_id"],
        fingerprint=f["fingerprint"],
    )
    oldgroup = row["plan"]["groups"][0]["id"]
    changed = {
        **row["plan"],
        "groups": [row["plan"]["groups"][1], {"name": "New", "treatment": "C"}],
    }
    row2 = post(
        client,
        f"/{row['id']}/plan-revisions",
        plan=changed,
        expected_revision=p["revision"],
        reason="Revised plan",
    )
    command_for(
        client,
        row2,
        "enroll",
        status=422,
        plan_revision=row2["plan_revision"],
        group_id=oldgroup,
        fruiting_id=f["fruiting_id"],
        fingerprint=f["fingerprint"],
    )
    command_for(
        client,
        row2,
        "enroll",
        plan_revision=row["plan_revision"],
        group_id=oldgroup,
        fruiting_id=f["fruiting_id"],
        fingerprint=f["fingerprint"],
    )
    assert participants(client, row)["items"][0]["group_name"] == "Control"


def test_multi_recipe_creation_snapshot_labels_exact_replay_and_ordinary_unchanged(
    client, monkeypatch
):
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-01T00:00:00.000000+00:00")
    monkeypatch.setattr(en, "clock", lambda: "2026-01-01T00:00:00.000000+00:00")
    row = setup(client)
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    allocated = allocation(client, row, src, rs)
    monkeypatch.setattr(en, "clock", lambda: "2026-01-03T00:00:00.000000+00:00")
    key = str(uuid4())
    payload = dict(
        expected_revision=allocated["revision"],
        reason="Create assigned destinations",
        allocation_id=allocated["allocation"]["id"],
        spawning_date="2026-01-02",
        treatment_start="2026-01-02T12:00:00Z",
    )
    result = post(client, f"/{row['id']}/fruiting", status=201, key=key, **payload)
    assert len(result["containers"]) == 2
    assert [m["classification"] for m in result["memberships"]] == [
        "prospective",
        "prospective",
    ]
    assert (
        post(client, f"/{row['id']}/fruiting", status=201, key=key, **payload) == result
    )
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "used"
    with Session(client.app.state.engine) as s:
        runs = list(
            s.scalars(
                select(FruitingRun)
                .where(FruitingRun.source_spawn_id == src["id"])
                .order_by(FruitingRun.fruiting_id)
            )
        )
        assert [r.recipe_id for r in runs] == [r["id"] for r in rs]
        assert all(json.loads(r.recipe_snapshot)["revision"] == 1 for r in runs)
        assert all(json.loads(r.recipe_snapshot)["used"] is False for r in runs)
    ordinary = spawn(client, 2)
    assert len(ordinary) == 2 and len({fr["physical_label"] for fr in ordinary}) == 2


def test_atomic_rollback_on_late_timing_error_and_source_still_ready(
    client, monkeypatch
):
    row = setup(client)
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    a = allocation(client, row, src, rs)
    command_for(
        client,
        row,
        "fruiting",
        status=422,
        allocation_id=a["allocation"]["id"],
        spawning_date="2026-01-01",
        treatment_start="2026-01-03T12:00:00Z",
    )
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "ready"
    assert participants(client, row)["total"] == 0
    with client.app.state.engine.connect() as c:
        assert (
            c.exec_driver_sql("SELECT count(*) FROM fruiting_containers").scalar() == 0
        )
        assert (
            c.exec_driver_sql(
                "SELECT count(*) FROM label_assignments WHERE fruiting_id IS NOT NULL"
            ).scalar()
            == 0
        )


def test_rule_links_future_ordinary_creation_and_stopped_rule_is_a_review(client):
    row = setup(client)
    src = source(client)
    saved = rule(client, row, src["id"])
    frs = spawn(client, 2, src=src)
    p = participants(client, row)
    assert p["total"] == 2 and all(
        m["evidence"]["origin"] == "lineage" for m in p["items"]
    )
    assert p["counts"]["known_spawn_sources"] == 1
    command_for(client, row, f"source-rules/{saved['rule']['id']}/stop")
    assert all(
        m["evidence"]["status"] == "needs_review"
        for m in participants(client, row)["items"]
    )


def test_conflicting_rules_and_partial_shared_ancestry_require_review(client):
    row = setup(client, category="genetics")
    a = source(client)
    b = source(client)
    # Register a real legacy mixed-source grow; manual provenance never consumes spawn.
    response = client.post(
        "/api/provenance/grows",
        json={
            "source_ids": [a["id"], b["id"]],
            "allocation_mode": "shared",
            "containers": [{}],
        },
    )
    assert response.status_code == 201, response.text
    fr = response.json()["containers"][0]
    rule(client, row, a["id"])
    p = participants(client, row)
    assert p["total"] == 0
    candidate = next(c for c in p["candidates"] if c["fruiting_id"] == fr["id"])
    assert candidate["suggestion"]["automatic"] is False
    rule(client, row, b["id"], 1)
    assert (
        "conflicting"
        in next(
            c
            for c in participants(client, row)["candidates"]
            if c["fruiting_id"] == fr["id"]
        )["suggestion"]["reason"]
    )
    linked = enroll(client, row, fr)
    assert linked["membership"]["evidence"]["status"] == "needs_review"


def test_source_ancestry_correction_flags_without_reassigning_and_review_is_audited(
    client,
):
    row = setup(client, category="genetics")
    src = source(client)
    rule(client, row, src["id"])
    fr = spawn(client, 1, src=src)[0]
    p = participants(client, row)
    before = p["items"][0]
    line = before["sources"]["line_ids"][0]
    other = source(client)
    parent = client.get("/api/library/spawn/" + other["id"]).json()["line_id"]
    # Use the public ancestry correction workflow, which uses library.transaction.
    history = client.get("/api/provenance/lines/" + line).json()
    response = client.put(
        "/api/provenance/lines/" + line + "/ancestry",
        json={
            "expected_revision": history["revision"],
            "reason": "Document confirmed parent",
            "parents": [{"parent_id": parent, "confidence": "confirmed"}],
        },
    )
    assert response.status_code == 200, response.text
    p = participants(client, row)
    current = p["items"][0]
    assert (
        current["group_id"] == before["group_id"]
        and current["classification"] == before["classification"]
    )
    assert current["evidence"]["status"] == "needs_review"
    reviewed = command_for(
        client,
        row,
        f"participants/{current['id']}/review",
        decision="keep",
        fingerprint=current["sources"]["fingerprint"],
    )
    assert reviewed["membership"]["evidence"]["status"] == "confirmed"
    response = client.get(f"/api/experiments/{row['id']}/enrollment-history").json()
    assert any(e["action"] == "review_required" for e in response["items"])
    with pytest.raises(IntegrityError), client.app.state.engine.begin() as c:
        c.exec_driver_sql("DELETE FROM experiment_enrollment_events")


def test_conditions_cannot_invent_independent_container_units(client):
    row = setup(client, category="conditions")
    fr = spawn(client)[0]
    enroll(client, row, fr, status=409)
    assert participants(client, row)["total"] == 0


def test_membership_classifications_can_be_mixed_and_review_never_promotes(
    client, monkeypatch
):
    # Existing records receive retrospective timing when enrollment follows treatment.
    fr = spawn(client)[0]
    row = setup(client)
    a = enroll(client, row, fr)
    assert a["membership"]["classification"] == "retrospective"
    p = participants(client, row)
    m = p["items"][0]
    r = command_for(
        client,
        row,
        f"participants/{m['id']}/review",
        decision="reassign",
        group_id=row["plan"]["groups"][1]["id"],
        plan_revision=row["plan_revision"],
        fingerprint=m["sources"]["fingerprint"],
    )
    assert r["membership"]["classification"] == "retrospective"
    assert r["membership"]["evidence"]["group_id"] == row["plan"]["groups"][1]["id"]


def test_schema_drift_backup_and_existing_0015_memberships(client, settings, tmp_path):
    row = setup(client)
    fr = spawn(client)[0]
    enroll(client, row, fr)
    with client.app.state.engine.connect() as c:
        assert not compare_metadata(MigrationContext.configure(c), Base.metadata)
    artifact = create_backup(settings.data_dir)
    try:
        check_archive(artifact.path, tmp_path / "verified")
    finally:
        artifact.cleanup()
    assert command.current(migration_config(settings)) is None


def test_physical_transfer_chain_automatically_associates_descendants(client):
    from test_library import receive
    from test_direct_creation import create as create_material

    physical = receive(client, count=1, material={"material_type": "agar_plate"})[
        "physical"
    ][0]
    ready = client.post(
        f"/api/containers/records/physical/{physical['id']}/state",
        json={"request_key": str(uuid4()), "action": "ready"},
    )
    assert ready.status_code == 200, ready.text
    row = setup(client, category="genetics")
    rule(client, row, physical["id"], kind="physical")
    grain = recipe(client, "grain")
    made = create_material(client, "spawn_jar", physical, grain, count=1, unit="plate")[
        "materials"
    ][0]
    ready = client.post(
        f"/api/containers/records/spawn/{made['id']}/state",
        json={"request_key": str(uuid4()), "action": "ready"},
    )
    assert ready.status_code == 200, ready.text
    fr = spawn(client, 1, src=made)[0]
    p = participants(client, row)
    assert p["total"] == 1 and p["items"][0]["fruiting_id"] == fr["id"]
    assert "physical:" + physical["id"] in p["items"][0]["sources"]["leaves"][0]


def test_possible_genetic_parent_is_not_physical_provenance_or_pure_automatic_attribution(
    client,
):
    src = source(client)
    other = source(client)
    line = client.get("/api/library/spawn/" + src["id"]).json()["line_id"]
    parent = client.get("/api/library/spawn/" + other["id"]).json()["line_id"]
    revision = client.get("/api/provenance/lines/" + line).json()["revision"]
    response = client.put(
        "/api/provenance/lines/" + line + "/ancestry",
        json={
            "expected_revision": revision,
            "reason": "Possible only",
            "parents": [{"parent_id": parent, "confidence": "possible"}],
        },
    )
    assert response.status_code == 200, response.text
    row = setup(client, category="genetics")
    rule(client, row, line, kind="line")
    fr = spawn(client, 1, src=src)[0]
    p = participants(client, row)
    assert p["total"] == 0
    fact = next(c for c in p["candidates"] if c["fruiting_id"] == fr["id"])
    assert fact["ambiguous"] and not fact["suggestion"]["automatic"]
    assert "line:" + parent not in fact["leaves"][0]


def test_mixed_classifications_and_same_day_uncertainty(client, monkeypatch):
    old = spawn(client)[0]
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-02T00:00:00.000000+00:00")
    monkeypatch.setattr(en, "clock", lambda: "2026-01-02T00:00:00.000000+00:00")
    row = setup(client)
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    a = allocation(client, row, src, rs)
    monkeypatch.setattr(en, "clock", lambda: "2026-01-03T12:00:00.000000+00:00")
    command_for(
        client,
        row,
        "fruiting",
        status=201,
        allocation_id=a["allocation"]["id"],
        spawning_date="2026-01-03",
        treatment_start="2026-01-03T11:00:00Z",
    )
    enroll(client, row, old, treatment_start="2026-01-01T12:00:00Z")
    p = participants(client, row)
    assert p["classification_summary"] == "mixed"
    assert (
        p["counts"]["classification_counts"]["prospective"] == 2
        and p["counts"]["classification_counts"]["retrospective"] == 1
    )
    same = spawn(client, 1, spawning_date="2026-01-03")[0]
    enrolled = enroll(client, row, same)
    assert enrolled["membership"]["classification"] == "uncertain"


def test_ready_source_recipe_and_plan_changes_abort_saved_creation(client):
    row = setup(client)
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    a = allocation(client, row, src, rs)
    changed = {**row["plan"], "hypotheses": "Amended"}
    p = participants(client, row)
    post(
        client,
        f"/{row['id']}/plan-revisions",
        plan=changed,
        expected_revision=p["revision"],
        reason="New plan",
    )
    command_for(
        client,
        row,
        "fruiting",
        status=409,
        allocation_id=a["allocation"]["id"],
        spawning_date="2026-01-01",
    )
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "ready"


def test_upgrade_0015_preserves_existing_experiment_rows(settings):
    from app.database import make_engine

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = migration_config(settings)
    command.upgrade(cfg, "0015_grow_experiments")
    engine = make_engine(settings)
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO inventory_operations VALUES ('OP-OLD','historic-key','hash','experiment.create','{}','{}','2026-01-01')"
        )
        c.exec_driver_sql(
            "INSERT INTO experiments VALUES ('EX-OLD','substrate','fruiting','planned',1,0,'2026-01-01',NULL,NULL,NULL,'uncertain',NULL)"
        )
        snap = {
            "title": "Preserved",
            "groups": [
                {"id": "EG-OLD", "name": "Original", "treatment": "A"},
                {"id": "EG-OTHER", "name": "Other", "treatment": "B"},
            ],
        }
        c.exec_driver_sql(
            "INSERT INTO experiment_plan_revisions VALUES ('EX-OLD',1,?,'2026-01-01',NULL,'2026-01-01','Original','OP-OLD')",
            (json.dumps(snap),),
        )
        c.exec_driver_sql("INSERT INTO experiment_groups VALUES ('EG-OLD','EX-OLD')")
        before = {
            t: c.exec_driver_sql("SELECT * FROM " + t).fetchall()
            for t in ["experiments", "experiment_plan_revisions", "experiment_groups"]
        }
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        for t, rows in before.items():
            assert c.exec_driver_sql("SELECT * FROM " + t).fetchall() == rows
        assert not compare_metadata(MigrationContext.configure(c), Base.metadata)
    engine.dispose()


def test_new_conflicting_rule_preserves_previously_confirmed_group(client):
    row = setup(client)
    src = source(client)
    rule(client, row, src["id"])
    spawn(client, src=src)
    before = participants(client, row)["items"][0]
    rule(client, row, src["id"], group=1)
    after = participants(client, row)["items"][0]
    assert before["group_id"] == after["group_id"]
    assert after["evidence"]["status"] == "needs_review"


def test_rule_unknown_id_validation_and_wrong_container_identity_constraint(client):
    row = setup(client)
    frs = spawn(client, 2)
    command_for(
        client,
        row,
        "source-rules",
        status=404,
        plan_revision=row["plan_revision"],
        group_id=row["plan"]["groups"][0]["id"],
        source_kind="spawn",
        source_id="SJ-MISSING",
    )
    m = enroll(client, row, frs[0])["membership"]
    with pytest.raises(IntegrityError), client.app.state.engine.begin() as c:
        c.exec_driver_sql(
            "UPDATE experiment_units SET fruiting_id=? WHERE id=?",
            (frs[1]["id"], m["unit_id"]),
        )


def test_genetics_creation_cannot_split_one_genetic_source_across_groups(client):
    row = setup(client, category="genetics")
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    command_for(
        client,
        row,
        "creation-allocations",
        status=422,
        plan_revision=row["plan_revision"],
        spawn_id=src["id"],
        destinations=[
            dict(group_id=g["id"], recipe_id=r["id"], count=1)
            for g, r in zip(row["plan"]["groups"], rs)
        ],
    )


def test_recipe_revision_change_invalidates_precommitted_creation(client):
    row = setup(client)
    src = source(client)
    rs = [recipe(client, "substrate"), recipe(client, "substrate")]
    a = allocation(client, row, src, rs)
    r = client.get("/api/preparation/recipes/" + rs[0]["id"]).json()
    fields = [
        "name",
        "recipe_type",
        "batch_yield",
        "ingredients",
        "instructions",
        "processing",
        "notes",
        "description",
        "shelf_life_days",
    ]
    response = client.put(
        "/api/preparation/recipes/" + r["id"],
        json={
            **{k: r[k] for k in fields},
            "expected_revision": r["revision"],
            "request_key": str(uuid4()),
            "name": "Revised recipe",
        },
    )
    assert response.status_code == 200, response.text
    command_for(
        client,
        row,
        "fruiting",
        status=409,
        allocation_id=a["allocation"]["id"],
        spawning_date="2026-01-01",
    )
    assert client.get("/api/library/spawn/" + src["id"]).json()["stage"] == "ready"


def test_explicit_keep_acknowledges_rule_conflict_until_new_evidence(client):
    row = setup(client)
    src = source(client)
    rule(client, row, src["id"])
    spawn(client, src=src)
    rule(client, row, src["id"], group=1)
    p = participants(client, row)
    m = p["items"][0]
    command_for(
        client,
        row,
        f"participants/{m['id']}/review",
        decision="keep",
        fingerprint=m["sources"]["fingerprint"],
    )
    source(client)  # Unrelated cultivation mutation must not undo explicit review.
    assert participants(client, row)["items"][0]["evidence"]["status"] == "confirmed"


def test_completed_experiment_retains_source_correction_warning_and_allows_audited_review(
    client,
):
    row = setup(client)
    src = source(client)
    rule(client, row, src["id"])
    spawn(client, src=src)
    current = client.get("/api/experiments/" + row["id"]).json()
    current = action(client, current, "start", treatment_date="2026-01-01")
    current = action(client, current, "complete")
    line = participants(client, row)["items"][0]["sources"]["line_ids"][0]
    other = source(client)
    parent = client.get("/api/library/spawn/" + other["id"]).json()["line_id"]
    rev = client.get("/api/provenance/lines/" + line).json()["revision"]
    response = client.put(
        "/api/provenance/lines/" + line + "/ancestry",
        json={
            "expected_revision": rev,
            "reason": "Correct completed history",
            "parents": [{"parent_id": parent, "confidence": "confirmed"}],
        },
    )
    assert response.status_code == 200, response.text
    p = participants(client, row)
    m = p["items"][0]
    assert m["evidence"]["status"] == "needs_review"
    result = command_for(
        client,
        row,
        f"participants/{m['id']}/review",
        decision="keep",
        fingerprint=m["sources"]["fingerprint"],
    )
    assert result["membership"]["evidence"]["status"] == "confirmed"
    assert client.get("/api/experiments/" + row["id"]).json()["state"] == "completed"


def test_genetics_creation_retains_uncertain_ancestry_for_review(client):
    src = source(client)
    other = source(client)
    line = client.get("/api/library/spawn/" + src["id"]).json()["line_id"]
    parent = client.get("/api/library/spawn/" + other["id"]).json()["line_id"]
    rev = client.get("/api/provenance/lines/" + line).json()["revision"]
    response = client.put(
        "/api/provenance/lines/" + line + "/ancestry",
        json={
            "expected_revision": rev,
            "reason": "Possible parent only",
            "parents": [{"parent_id": parent, "confidence": "possible"}],
        },
    )
    assert response.status_code == 200, response.text
    row = setup(client, category="genetics")
    r = recipe(client, "substrate")
    a = command_for(
        client,
        row,
        "creation-allocations",
        plan_revision=row["plan_revision"],
        spawn_id=src["id"],
        destinations=[
            {
                "group_id": row["plan"]["groups"][0]["id"],
                "recipe_id": r["id"],
                "count": 1,
            }
        ],
    )
    result = command_for(
        client,
        row,
        "fruiting",
        status=201,
        allocation_id=a["allocation"]["id"],
        spawning_date="2026-01-01",
    )
    assert result["memberships"][0]["evidence"]["status"] == "needs_review"
