"""Recorded facts, suppression lifecycle, paging, dates and backup compatibility."""

from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session
import pytest
from app import dashboard
from app.models import PhysicalCulture, Spawn, CultureLine, Strain, ActivityEvent
from app.container_models import CultivationState
from app.preparation_models import MaterialLifecycle
from app.config import Settings
from app.main import create_app
from app.backup_format import create_backup, check_archive
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn, stage, harvest


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    value = [datetime(2026, 2, 1, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(dashboard, "now", lambda: value[0])
    return value


def summary(client, **params):
    r = client.get("/api/dashboard/summary", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def add(
    client,
    kind="physical",
    phase=None,
    date=None,
    archived=False,
    material=None,
    lifecycle=None,
):
    code = ("AG" if kind == "physical" else "SP") + "-" + uuid4().hex[:12]
    with Session(client.app.state.engine) as s, s.begin():
        if not s.get(Strain, "ST-DASH"):
            s.add(
                Strain(
                    id="ST-DASH",
                    name="Dashboard Oyster",
                    normalized_name="dashboard oyster",
                )
            )
            s.flush()
            s.add(
                CultureLine(
                    id="CL-DASH",
                    strain_id="ST-DASH",
                    origin="purchased",
                    name="Recorded line",
                )
            )
            s.flush()
        row = (
            PhysicalCulture(
                id=code,
                line_id="CL-DASH",
                material_type=material or "agar_plate",
                registration_batch=str(uuid4()),
            )
            if kind == "physical"
            else Spawn(
                id=code,
                line_id="CL-DASH",
                material_type=material or "spawn_jar",
                stage=phase if phase in {"ready", "used"} else "colonizing",
            )
        )
        row.status = "archived" if archived else "active"
        s.add(row)
        s.flush()
        if phase:
            s.add(
                CultivationState(
                    **{kind + "_id": code},
                    phase=phase,
                    **(
                        {
                            (
                                "inoculation_date"
                                if phase == "colonizing"
                                else phase + "_date"
                            ): date
                        }
                        if date
                        else {}
                    ),
                )
            )
        if lifecycle:
            s.add(MaterialLifecycle(**{kind + "_id": code}, state=lifecycle))
    return code


def action(client, item, action="dismiss", **extra):
    r = client.post(
        "/api/dashboard/attention",
        json={k: item[k] for k in ["alert_id", "fingerprint"]}
        | dict(action=action, **extra),
    )
    assert r.status_code == 200, r.text


def rules(client):
    return {(a["record_id"], a["rule"]): a for a in summary(client)["attention_items"]}


def test_eligibility_missing_dates_terminal_archive_and_threshold_boundary(client):
    ready = add(client, phase="ready", date="2026-01-30")
    growing = add(client, phase="colonizing", date="2026-01-10")
    spawn_ready = add(client, "spawn", "ready")
    spawn_growing = add(client, "spawn", "colonizing", "2026-01-03")
    for phase, date in [
        ("colonizing", "2026-01-11"),
        ("colonizing", None),
        (None, None),
        ("used", "2025-01-01"),
        ("completed", "2025-01-01"),
        ("failed", "2025-01-01"),
        ("colonizing", "2026-03-01"),
    ]:
        add(client, phase=phase, date=date)
    add(client, material="lc_jar")
    add(client, phase="ready", archived=True)
    add(client, phase="ready", lifecycle="depleted")
    add(client, phase="colonizing", date="2026-01-01", lifecycle="failed")
    items = rules(client)
    assert set(items) == {
        (ready, "ready"),
        (growing, "agar_growing"),
        (spawn_ready, "ready"),
        (spawn_growing, "spawn_colonizing"),
    }
    assert items[(growing, "agar_growing")]["elapsed_days"] == 22
    assert (
        "P-" in items[(ready, "ready")]["title"]
        and "Dashboard Oyster" in items[(ready, "ready")]["title"]
    )
    assert summary(client)["counts"]["open_alerts"] == 4


def test_recent_failures_only_explicit_dates_last_seven_calendar_days(client):
    yes = [
        add(client, phase="failed", date="2026-01-26"),
        add(client, "spawn", "failed", "2026-02-01"),
    ]
    for date in ["2026-01-25", None, "2026-02-02"]:
        add(client, phase="failed", date=date)
    add(client, phase="failed", date="2026-02-01", archived=True)
    assert set(rules(client)) == {(code, "recent_failure") for code in yes}
    assert summary(client)["counts"]["active_cultures"] == 0


def test_snooze_expiry_undo_stale_rejection_and_restart(client, settings, clock):
    add(client, phase="ready")
    item = summary(client)["attention_items"][0]
    action(client, item, "snooze", days=3)
    assert summary(client)["counts"]["open_alerts"] == 0
    assert client.get("/api/dashboard/attention?hidden=true").json()["total"] == 1
    app = create_app(settings)
    with Session(app.state.engine) as s:
        assert dashboard.summary(s, settings, "UTC")["counts"]["open_alerts"] == 0
    app.state.engine.dispose()
    clock[0] += timedelta(days=3)
    assert summary(client)["counts"]["open_alerts"] == 1
    assert client.get("/api/dashboard/attention?hidden=true").json()["total"] == 0
    action(client, item)
    assert summary(client)["counts"]["open_alerts"] == 0
    action(client, item, "restore")
    assert summary(client)["counts"]["open_alerts"] == 1
    assert (
        client.post(
            "/api/dashboard/attention",
            json=dict(
                alert_id=item["alert_id"], fingerprint="0" * 64, action="dismiss"
            ),
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/dashboard/attention",
            json=dict(
                alert_id=item["alert_id"],
                fingerprint=item["fingerprint"],
                action="snooze",
                days=2,
            ),
        ).status_code
        == 422
    )


def test_dismiss_survives_refresh_unrelated_edits_and_photos_relevant_change_reactivates(
    client,
):
    code = add(client, phase="ready", date="2026-01-15")
    item = summary(client)["attention_items"][0]
    action(client, item)
    with Session(client.app.state.engine) as s, s.begin():
        s.get(PhysicalCulture, code).notes = "Unrelated note"
        for kind in ["edited", "photo_added", "physical_label"]:
            s.add(
                ActivityEvent(
                    physical_id=code, event_type=kind, description="Unrelated change"
                )
            )
    assert summary(client)["counts"]["open_alerts"] == 0
    assert summary(client)["counts"]["open_alerts"] == 0
    with Session(client.app.state.engine) as s, s.begin():
        s.scalar(
            select(CultivationState).where(CultivationState.physical_id == code)
        ).ready_date = "2026-01-31"
        s.add(
            ActivityEvent(
                physical_id=code,
                event_type="ready",
                description="Explicit new readiness",
            )
        )
    assert summary(client)["counts"]["open_alerts"] == 1
    assert summary(client)["attention_items"][0]["fingerprint"] != item["fingerprint"]


def test_fruiting_current_flush_next_action_terminal_states_and_stage_links(client):
    code = spawn(client)[0]["id"]
    assert {(code, "fruiting_colonizing"), (code, "fruiting_action")} <= set(
        rules(client)
    )
    stage(client, code, "pinning", "2026-01-03")
    assert (code, "pinning") in rules(client)
    stage(client, code, "fruiting", "2026-01-05")
    assert (code, "fruiting") in rules(client)
    harvest(client, code)
    old = rules(client)[(code, "fruiting_action")]
    action(client, old)
    stage(client, code, "next_flush", "2026-01-31")
    new = rules(client)[(code, "fruiting_action")]
    assert new["recorded_date"] == "2026-01-31" and new["elapsed_days"] == 1
    assert new["fingerprint"] != old["fingerprint"] and (code, "pinning") not in rules(
        client
    )
    stages = summary(client)["stage_overview"]
    item = next(
        s for s in stages if s["group"] == "fruiting" and s["stage"] == "pinning"
    )
    assert (
        item["count"] == 1
        and item["target"] == "/cultivation?view=fruiting&fruiting=pinning"
    )
    assert sum(s["count"] for s in stages) == 1
    stage(client, code, "complete", "2026-02-01")
    assert summary(client)["counts"]["fruiting_units"] == 0 and not rules(client)


def test_preferences_validate_disable_persist_without_cultivation_writes(
    client, settings
):
    code = add(client, phase="colonizing", date="2026-01-01")
    prefs = client.get("/api/dashboard/preferences").json()
    assert prefs["agar_growing"] == dict(enabled=True, days=21)
    for value in [0, 366, 1.5, True, "10"]:
        assert (
            client.put(
                "/api/dashboard/preferences",
                json={**prefs, "agar_growing": dict(enabled=True, days=value)},
            ).status_code
            == 422
        )
    prefs["agar_growing"]["enabled"] = False
    assert client.put(
        "/api/dashboard/preferences", json=prefs
    ).status_code == 200 and not rules(client)
    with Session(client.app.state.engine) as s:
        assert (
            s.scalar(
                select(CultivationState).where(CultivationState.physical_id == code)
            ).inoculation_date
            == "2026-01-01"
        )
        assert s.scalar(select(ActivityEvent.id)) is None
    assert (settings.data_dir / "settings/dashboard.json").exists()
    assert client.get("/api/dashboard/preferences").json() == prefs


def test_activity_timestamps_deterministic_pages_filter_and_archive(client):
    code = add(client, phase="ready", archived=True)
    with Session(client.app.state.engine) as s, s.begin():
        for i in range(40):
            s.add(
                ActivityEvent(
                    physical_id=code,
                    event_type="ready",
                    occurred_at="2026-02-01T11:00:00+00:00",
                    description=f"Earlier cultivation date 2026-01-01; event {i}",
                )
            )
    data = summary(client)["recent_activity"]
    assert len(data) == 15
    assert [e["event_id"] for e in data] == sorted(
        (e["event_id"] for e in data), reverse=True
    )
    assert all(
        e["occurred_at"].startswith("2026-02-01T11:")
        and e["archived"]
        and code in e["target"]
        and "Dashboard Oyster" in e["title"]
        for e in data
    )
    one = client.get("/api/dashboard/activity?page_size=25").json()
    two = client.get("/api/dashboard/activity?page=2&page_size=25").json()
    assert one["total"] == 40 and len(two["items"]) == 15
    assert not {e["event_id"] for e in one["items"]} & {
        e["event_id"] for e in two["items"]
    }
    assert client.get("/api/dashboard/activity?record_type=spawn").json()["total"] == 0
    for query in ["page=0", "page_size=51", "record_type=invalid"]:
        assert client.get("/api/dashboard/activity?" + query).status_code == 422


def test_harvest_current_values_coverage_boundaries_revisions_and_timezone(
    client, clock
):
    code = spawn(client)[0]["id"]
    stage(client, code, "pinning")
    stage(client, code, "fruiting", "2026-01-02")
    entries = [
        harvest(client, code, harvest_date=d, wet_grams=w)
        for d, w in [
            ("2026-01-02", "1000"),
            ("2026-01-03", "0"),
            ("2026-01-15", None),
            ("2026-02-01", "12.345"),
            ("2026-02-02", "2000"),
        ]
    ]
    h = entries[3]
    response = client.post(
        f"/api/fruiting/harvests/{h['id']}/edit",
        json=dict(
            request_key=str(uuid4()),
            expected_revision=h["revision"],
            harvest_date="2026-02-01",
            wet_grams="20.125",
        ),
    )
    assert response.status_code == 200, response.text
    assert summary(client)["harvest_summary"] == dict(
        start_date="2026-01-03",
        end_date="2026-02-01",
        timezone="UTC",
        harvest_count=3,
        wet_weight_count=2,
        wet_grams="20.125",
        fruiting_count=1,
    )
    clock[0] = datetime(2026, 2, 1, 1, tzinfo=timezone.utc)
    local = summary(client, timezone="America/New_York")["harvest_summary"]
    assert local["start_date"] == "2026-01-02" and local["end_date"] == "2026-01-31"
    assert local["harvest_count"] == 3 and local["wet_grams"] == "1000"
    assert client.get("/api/dashboard/summary?timezone=Invalid/Zone").status_code == 422


def test_bounded_payload_constant_query_count_and_pagination(client):
    for _ in range(35):
        add(client, phase="ready")
    statements = []

    def count(*args):
        statements.append(args[2])

    event.listen(client.app.state.engine, "before_cursor_execute", count)
    try:
        result = summary(client)
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", count)
    assert (
        result["counts"]["open_alerts"] == 35
        and len(result["attention_items"]) == 25
        and len(result["active_cultivation"]) == 24
    )
    assert len(statements) <= 15
    page = client.get("/api/dashboard/attention?page=2").json()
    assert page["total"] == 35 and len(page["items"]) == 10


def test_settings_backup_roundtrip_schema_unchanged_and_corruption_visible(
    client, settings
):
    add(client, phase="ready")
    item = summary(client)["attention_items"][0]
    action(client, item)
    prefs = client.get("/api/dashboard/preferences").json()
    prefs["pinning"]["days"] = 35
    client.put("/api/dashboard/preferences", json=prefs)
    artifact = create_backup(settings.data_dir)
    verified = check_archive(artifact.path)
    try:
        with TestClient(
            create_app(
                Settings(data_dir=verified.root, frontend_dir=settings.frontend_dir)
            )
        ) as restored:
            assert restored.get("/api/health").json()["migrations"] == "current"
            assert restored.get("/api/dashboard/preferences").json() == prefs
            assert summary(restored)["counts"]["open_alerts"] == 0
            assert (
                restored.get("/api/dashboard/attention?hidden=true").json()["total"]
                == 1
            )
    finally:
        verified.cleanup()
        artifact.cleanup()
    (settings.data_dir / "settings/dashboard.json").write_text("broken")
    assert client.get("/api/dashboard/summary").status_code == 503
    assert client.get("/api/dashboard/preferences").status_code == 503


def test_disabled_rule_keeps_dismissal_when_another_alert_is_changed(client):
    code = add(client, phase="colonizing", date="2026-01-01")
    other = add(client, phase="ready")
    action(client, rules(client)[(code, "agar_growing")])
    prefs = client.get("/api/dashboard/preferences").json()
    prefs["agar_growing"]["enabled"] = False
    client.put("/api/dashboard/preferences", json=prefs)
    action(client, rules(client)[(other, "ready")], "snooze", days=1)
    prefs["agar_growing"]["enabled"] = True
    client.put("/api/dashboard/preferences", json=prefs)
    assert not rules(client)
    assert client.get("/api/dashboard/attention?hidden=true").json()["total"] == 2


def test_recent_fruiting_failures_and_no_harvest_measurements(client):
    code = spawn(client)[0]["id"]
    stage(client, code, "failed", "2026-01-30")
    items = rules(client)
    assert set(items) == {(code, "recent_failure")}
    assert "F-01" in items[(code, "recent_failure")]["title"]
    assert summary(client)["harvest_summary"]["wet_grams"] is None
    assert summary(client)["harvest_summary"]["wet_weight_count"] == 0


def test_legacy_fruiting_placeholder_is_unrecorded_not_a_ready_stage(client):
    response = client.post("/api/provenance/grows", json={"containers": [{}]})
    assert response.status_code == 201, response.text
    code = response.json()["containers"][0]["id"]
    data = summary(client)
    assert data["counts"]["fruiting_units"] == 1
    assert not data["attention_items"]
    assert (
        next(r for r in data["active_cultivation"] if r["record_id"] == code)["stage"]
        == "unrecorded"
    )
    assert all(s["count"] == 0 for s in data["stage_overview"])


def test_unmeasured_harvest_is_counted_without_fabricated_zero(client):
    code = spawn(client)[0]["id"]
    stage(client, code, "pinning", "2026-01-03")
    stage(client, code, "fruiting", "2026-01-04")
    harvest(client, code)
    data = summary(client)["harvest_summary"]
    assert data["harvest_count"] == 1 and data["fruiting_count"] == 1
    assert data["wet_weight_count"] == 0 and data["wet_grams"] is None


def test_activity_order_preserves_microseconds_and_equivalent_offset_instants(client):
    code = add(client)
    times = [
        "2026-02-01T11:00:00.000002+00:00",
        "2026-02-01T11:00:00.000001+00:00",
        "2026-02-01T06:00:00.000002-05:00",
        "2026-02-01T10:59:59.999999+00:00",
    ]
    ids = []
    with Session(client.app.state.engine) as session, session.begin():
        for timestamp in times:
            item = ActivityEvent(
                physical_id=code,
                event_type="created",
                occurred_at=timestamp,
                description="Precise recorded timestamp",
            )
            session.add(item)
            session.flush()
            ids.append(item.id)
    events = client.get("/api/dashboard/activity").json()["items"]
    assert [item["event_id"] for item in events] == [ids[2], ids[0], ids[1], ids[3]]
