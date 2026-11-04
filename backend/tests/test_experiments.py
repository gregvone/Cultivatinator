"""Experiment foundation, scientific timing, schema preservation and backups."""

import json
from datetime import datetime, timezone, date
from uuid import uuid4
import pytest
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app import experiments as exp
from app.experiment_models import (
    ExperimentUnit,
    ExperimentMembership,
    ExperimentTrial,
    ExperimentPlanRevision,
)
from app.database import Base, make_engine, migration_config
from app.backup_format import create_backup, check_archive, schema_catalog
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn


def plan(category="substrate"):
    return dict(
        title="Fruiting comparison",
        category=category,
        primary_variable="Substrate formulation",
        primary_outcome="completed_wet_yield",
        hypotheses="A may produce more recorded yield",
        groups=[
            dict(name="Control", treatment="A", control=True),
            dict(name="Comparison", treatment="B"),
        ],
        advanced=dict(
            allocation_schedule="Randomize recorded units before treatment",
            minimum_readings=3,
        ),
    )


def post(client, path="", status=200, key=None, **data):
    response = client.post(
        "/api/experiments" + path, json={"request_key": key or str(uuid4()), **data}
    )
    assert response.status_code == status, response.text
    return response.json()


def create(client, **kwargs):
    return post(client, status=201, plan=plan(**kwargs))


def action(client, row, action, **kwargs):
    return post(
        client,
        f"/{row['id']}/actions",
        expected_revision=row["revision"],
        action=action,
        reason="Recorded test action",
        **kwargs,
    )


@pytest.mark.parametrize("category", ["substrate", "genetics", "conditions"])
def test_plan_lifecycle_and_original_history(client, category):
    row = create(client, category=category)
    assert row["state"] == "draft" and row["classification"] == "uncertain"
    original = row["plan"]
    row = action(client, row, "plan")
    row = action(client, row, "start", treatment_date="2025-01-01")
    assert row["classification"] == "retrospective"
    changed = {**row["plan"], "title": "Revised question"}
    row = post(
        client,
        f"/{row['id']}/plan-revisions",
        plan=changed,
        expected_revision=row["revision"],
        reason="Post-start correction",
    )
    assert row["post_start_amendment"] and row["classification"] == "retrospective"
    row = action(client, row, "complete")
    row = action(client, row, "archive")
    assert row["state"] == "completed" and row["archived"] == 1
    row = action(client, row, "restore")
    history = client.get(f"/api/experiments/{row['id']}/history").json()
    assert history["plans"][-1]["snapshot"] == original
    assert history["plan_total"] == 3 and history["audit_total"] == 7
    assert history["audits"][0]["after"]["archived"] == 0


def test_replay_stale_conflict_and_cancel(client):
    key = str(uuid4())
    row = post(client, status=201, key=key, plan=plan())
    committed = action(client, row, "plan")
    assert post(client, status=201, key=key, plan=plan()) == row
    post(client, status=409, key=key, plan={**plan(), "title": "Changed"})
    post(
        client,
        f"/{row['id']}/actions",
        status=409,
        expected_revision=1,
        action="cancel",
        reason="stale",
    )
    cancelled = action(client, committed, "cancel")
    post(
        client,
        f"/{row['id']}/actions",
        status=409,
        expected_revision=cancelled["revision"],
        action="start",
        reason="invalid",
        treatment_date="2025-01-01",
    )
    assert client.get("/api/experiments").json()["total"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"groups": [{"name": "A", "treatment": "A"}]},
        {"primary_variable": ""},
        {"primary_outcome": ["failure_rate", "cycle_days"]},
        {"scope": "agar"},
        {"category": "breeding"},
        {
            "groups": [
                {"name": "A", "treatment": "A", "control": True},
                {"name": "a", "treatment": "B", "control": True},
            ]
        },
        {"secondary_outcomes": ["completed_wet_yield"]},
        {"advanced": {"minimum_readings": 0}},
    ],
)
def test_validation_no_mutation(client, change):
    post(client, status=422, plan={**plan(), **change})
    assert client.get("/api/experiments").json()["total"] == 0


def test_group_identity_validation_and_history_sql_protection(client):
    row = create(client)
    other = create(client)
    changed = row["plan"]
    changed["groups"][0]["id"] = other["plan"]["groups"][0]["id"]
    post(
        client,
        f"/{row['id']}/plan-revisions",
        status=422,
        plan=changed,
        expected_revision=1,
        reason="wrong owner",
    )
    engine = client.app.state.engine
    for table in [
        "experiment_plan_revisions",
        "experiment_audits",
        "experiment_groups",
    ]:
        for sql in [
            f"DELETE FROM {table}",
            f"UPDATE {table} SET experiment_id=experiment_id",
        ]:
            with pytest.raises(IntegrityError), engine.begin() as c:
                c.exec_driver_sql(sql)
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.exec_driver_sql("UPDATE experiments SET category='invalid'")


def test_treatment_evidence_and_backdating(client, monkeypatch):
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-01T00:00:00.000000+00:00")
    row = action(client, create(client), "plan")
    # Reserved tables are populated directly to exercise later-phase evidence,
    # not exposed through a premature enrollment workflow.
    frs = spawn(client, 2)
    with Session(client.app.state.engine) as s, s.begin():
        for i, (fr, g) in enumerate(zip(frs, row["plan"]["groups"])):
            s.add(
                ExperimentUnit(
                    id=f"U{i}",
                    experiment_id=row["id"],
                    plan_revision=row["plan_revision"],
                    recorded_at=exp.clock(),
                    group_id=g["id"],
                    kind="container",
                    fruiting_id=fr["id"],
                    allocated_at=exp.clock(),
                )
            )
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-03T00:00:00.000000+00:00")
    row = action(client, row, "start", treatment_start="2026-01-02T00:00:00Z")
    assert row["classification"] == "prospective"
    # Actual unit participation still requires later-phase review; this is timing only.
    row2 = action(client, create(client), "plan")
    row2 = action(client, row2, "start", treatment_start="2026-01-01T00:00:00Z")
    assert row2["classification"] == "retrospective"
    row3 = action(client, create(client), "plan")
    row3 = action(client, row3, "start", treatment_date="2026-01-03")
    assert row3["classification"] == "uncertain"


def test_missing_allocations_future_and_same_instant(client, monkeypatch):
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-01T00:00:00.000000+00:00")
    row = action(client, create(client), "plan")
    post(
        client,
        f"/{row['id']}/actions",
        status=422,
        expected_revision=row["revision"],
        action="start",
        reason="future",
        treatment_start="2026-01-02T00:00:00Z",
    )
    monkeypatch.setattr(exp, "clock", lambda: "2026-01-03T00:00:00.000000+00:00")
    row = action(client, row, "start", treatment_start="2026-01-02T00:00:00Z")
    assert row["classification"] == "uncertain"  # Schedule text is not evidence.
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert (
        exp.classify(instant.isoformat(), [instant.isoformat()], instant, "instant")
        == "uncertain"
    )


def test_shared_unit_crossover_schema_and_no_copied_harvests(client):
    row = create(client, category="conditions")
    frs = spawn(client, 2)
    tent = client.post(
        "/api/environment/tents",
        json={"request_key": str(uuid4()), "name": "Trial tent"},
    ).json()
    with Session(client.app.state.engine) as s, s.begin():
        for i, g in enumerate(row["plan"]["groups"]):
            s.add(
                ExperimentTrial(
                    id=f"T{i}",
                    experiment_id=row["id"],
                    group_id=g["id"],
                    tent_id=tent["id"],
                    starts_at=f"2026-01-0{i+1}T00:00:00.000000+00:00",
                    ends_at=f"2026-01-0{i+2}T00:00:00.000000+00:00",
                    revision=1,
                    treatment_snapshot="{}",
                )
            )
        s.flush()
        for i, g in enumerate(row["plan"]["groups"]):
            s.add(
                ExperimentUnit(
                    id=f"U{i}",
                    experiment_id=row["id"],
                    plan_revision=row["plan_revision"],
                    recorded_at=exp.clock(),
                    group_id=g["id"],
                    kind="tent_trial",
                    trial_id=f"T{i}",
                    allocated_at="2025-12-01T00:00:00.000000+00:00",
                )
            )
        s.flush()
        for i in range(2):
            for fr in frs:
                s.add(
                    ExperimentMembership(
                        experiment_id=row["id"],
                        unit_id=f"U{i}",
                        fruiting_id=fr["id"],
                        exposure_start=f"2026-01-0{i+1}T00:00:00.000000+00:00",
                        exposure_end=f"2026-01-0{i+2}T00:00:00.000000+00:00",
                        classification="uncertain",
                        evidence="{}",
                    )
                )
    with Session(client.app.state.engine) as s:
        assert s.scalar(select(text("count(*)")).select_from(ExperimentUnit)) == 2
        assert s.scalar(select(text("count(*)")).select_from(ExperimentMembership)) == 4
    assert client.get("/api/reports/performance").status_code == 200
    # A unit cannot claim a different group's trial.
    with pytest.raises(IntegrityError), Session(
        client.app.state.engine
    ) as s, s.begin():
        s.add(
            ExperimentUnit(
                id="bad",
                experiment_id=row["id"],
                plan_revision=row["plan_revision"],
                recorded_at=exp.clock(),
                group_id=row["plan"]["groups"][0]["id"],
                kind="tent_trial",
                trial_id="T1",
                allocated_at=exp.clock(),
            )
        )


def test_migration_preserves_0014_and_exact_catalog(settings, tmp_path):
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = migration_config(settings)
    command.upgrade(cfg, "0014_environment_monitoring")
    engine = make_engine(settings)
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO fruiting_tents VALUES ('ET-preserved','Original tent',NULL,'active',1,NULL)"
        )
        c.exec_driver_sql(
            "INSERT INTO environmental_readings (id,tent_id,observed_at,created_at,temperature_f,humidity,source,snapshot,evaluations) VALUES (1,'ET-preserved','2025-01-01T00:00:00.000000+00:00','2025-01-01T00:00:00.000000+00:00',70,90,'manual','{}','{}')"
        )
    with engine.connect() as c:
        before = {
            t: list(c.exec_driver_sql(f"SELECT * FROM {t}"))
            for t in ["fruiting_tents", "environmental_readings"]
        }
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        assert not compare_metadata(MigrationContext.configure(c), Base.metadata)
        for t, rows in before.items():
            assert list(c.exec_driver_sql(f"SELECT * FROM {t}")) == rows
    import sqlite3
    from pathlib import Path

    with sqlite3.connect(settings.database_path) as c:
        assert schema_catalog(c) == json.loads(
            (Path(exp.__file__).parent / "backup_schema.json").read_text()
        )
    engine.dispose()


def test_backup_roundtrip_and_populated_downgrade_refusal(client, settings, tmp_path):
    row = action(client, create(client), "plan")
    artifact = create_backup(settings.data_dir)
    try:
        check_archive(artifact.path, tmp_path / "verified")
    finally:
        artifact.cleanup()
    with pytest.raises(RuntimeError, match="Refusing to discard"):
        command.downgrade(migration_config(settings), "0014_environment_monitoring")


def test_draft_edit_and_planned_revision_preserve_original(client):
    row = create(client)
    original = row["plan"]
    revised = {
        **original,
        "hypotheses": "Revised before treatment",
        "advanced": {
            "blocking": "Same spawn source",
            "eligibility": "Known line",
            "exclusions": "Missing recipe",
            "observation_window": "Whole grow",
            "minimum_readings": 4,
            "maximum_gap_hours": 48,
        },
        "secondary_outcomes": ["failure_rate"],
    }
    row = post(
        client,
        f"/{row['id']}/plan-revisions",
        plan=revised,
        expected_revision=row["revision"],
        reason="Improve plan",
    )
    assert row["plan"]["advanced"]["maximum_gap_hours"] == 48
    assert not row["post_start_amendment"]
    row = action(client, row, "plan")
    history = client.get(f"/api/experiments/{row['id']}/history").json()
    assert history["plans"][-1]["snapshot"] == original
    assert history["plans"][0]["committed_at"]
    row = action(client, row, "archive")
    post(
        client,
        f"/{row['id']}/plan-revisions",
        status=409,
        plan=row["plan"],
        expected_revision=row["revision"],
        reason="Archived edit",
    )
    assert (
        client.get(f"/api/experiments/{row['id']}/history?page=2").json()["plans"] == []
    )
    assert client.get("/api/experiments/not-found").status_code == 404


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e999"])
def test_nonfinite_coverage_safely_rejected(client, value):
    payload = json.dumps({"request_key": str(uuid4()), "plan": plan()})
    payload = payload.replace('"minimum_readings": 3', '"maximum_gap_hours": ' + value)
    response = client.post(
        "/api/experiments",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_start_validation_requires_aware_actual_treatment(client):
    row = action(client, create(client), "plan")
    for extra in [
        {},
        {"treatment_start": "2026-01-01T00:00:00"},
        {"treatment_start": "2026-01-01T00:00:00Z", "treatment_date": "2026-01-01"},
        {"treatment_date": "1899-01-01"},
    ]:
        post(
            client,
            f"/{row['id']}/actions",
            status=422,
            expected_revision=row["revision"],
            action="start",
            reason="Invalid treatment",
            **extra,
        )
    assert client.get(f"/api/experiments/{row['id']}").json()["state"] == "planned"


def test_backdated_allocation_recording_is_not_prospective():
    instant = datetime(2026, 1, 2, tzinfo=timezone.utc)
    # The integration passes max(allocated_at, recorded_at), so later recording wins.
    assert (
        exp.classify(
            "2026-01-01T00:00:00+00:00",
            ["2026-01-03T00:00:00+00:00"],
            instant,
            "instant",
        )
        == "retrospective"
    )
    assert (
        exp.classify("2026-01-01T00:00:00+00:00", [None], instant, "instant")
        == "uncertain"
    )


def test_guided_client_collection_url_accepts_trailing_slash(client):
    # Shared libraryApi/useInventoryCommand constructs this collection URL.
    row = post(client, "/", status=201, plan=plan())
    assert row["state"] == "draft"
    assert client.get("/api/experiments").json()["total"] == 1
