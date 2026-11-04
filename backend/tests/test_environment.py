"""Environmental history, deterministic warnings and isolated backup acceptance."""

from uuid import uuid4
import json
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app import environment as env
from app.database import migration_config, Base, make_engine
from app.config import Settings
from app.main import create_app
from app.environment_models import EnvironmentalReading, TentOccupancy
from app.models import FruitingContainer, GrowBatch
from app.backup_format import create_backup, check_archive
from test_foundation import client, settings  # noqa: F401


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    value = ["2025-01-01T00:00:00.000000+00:00"]
    monkeypatch.setattr(env, "clock", lambda: value[0])
    return value


def post(client, path, **data):
    response = client.post(
        "/api/environment/" + path, json={"request_key": str(uuid4()), **data}
    )
    assert response.status_code == 200, response.text
    return response.json()


def put(client, path, **data):
    response = client.put(
        "/api/environment/" + path, json={"request_key": str(uuid4()), **data}
    )
    assert response.status_code == 200, response.text
    return response.json()


def get(client, path):
    response = client.get("/api/environment/" + path)
    assert response.status_code == 200, response.text
    return response.json()


def setup(client, targets=None):
    tent = post(client, "tents", name="Boom Room 2")
    profile = post(
        client,
        "profiles",
        name="Mixed Fruiting",
        targets=targets
        or {
            "temperature_f_min": 60,
            "temperature_f_max": 80,
            "humidity_min": 80,
            "humidity_max": 95,
            "co2_max": 1000,
        },
    )
    tent = post(
        client,
        f"tents/{tent['id']}/profile",
        profile_id=profile["id"],
        expected_revision=tent["revision"],
    )
    return tent, profile


def read(client, tent, day=2, **values):
    return post(
        client,
        f"tents/{tent['id']}/readings",
        observed_at=f"2025-01-{day:02d}T12:00:00Z",
        temperature_f=values.pop("temperature_f", 70),
        humidity=values.pop("humidity", 90),
        **values,
    )


def overview(client, tent):
    return get(client, f"tents/{tent['id']}/overview")


def test_blank_profiles_no_seed_multi_tent_and_revision_conflicts(client):
    assert get(client, "tents") == get(client, "profiles") == []
    a = post(client, "tents", name="Boom Room 2")
    b = post(client, "tents", name="Second tent")
    assert a["id"] != b["id"]
    p = post(client, "profiles", name="User draft")
    assert all(v is None for v in p["targets"].values())
    a = post(
        client,
        f"tents/{a['id']}/profile",
        profile_id=p["id"],
        expected_revision=a["revision"],
    )
    r = read(client, a, temperature_f=25, humidity=2)
    assert r["evaluations"] == {}
    assert overview(client, a)["warnings"] == []
    edited = put(
        client,
        "tents/" + a["id"],
        name="Renamed",
        description="test",
        status="archived",
        expected_revision=a["revision"],
    )
    assert edited["revision"] == a["revision"] + 1
    assert (
        client.put(
            "/api/environment/tents/" + a["id"],
            json={
                "request_key": str(uuid4()),
                "name": "Stale",
                "expected_revision": a["revision"],
            },
        ).status_code
        == 409
    )
    assert len(get(client, f"tents/{a['id']}/readings")["items"]) == 1
    assert (
        client.post(
            f"/api/environment/tents/{a['id']}/readings",
            json={
                "request_key": str(uuid4()),
                "observed_at": "2025-01-05T00:00:00Z",
                "temperature_f": 60,
                "humidity": 50,
            },
        ).status_code
        == 409
    )


def test_metric_persistence_independent_resolution_omitted_co2_and_profile_switch(
    client, clock
):
    t, p = setup(client)
    read(client, t, 2, temperature_f=50, humidity=50, co2=1500)
    assert {w["metric"] for w in overview(client, t)["warnings"]} == set(env.METRICS)
    read(client, t, 3, humidity=50)
    assert {w["metric"] for w in overview(client, t)["warnings"]} == {"humidity", "co2"}
    read(client, t, 4)
    assert {w["metric"] for w in overview(client, t)["warnings"]} == {"co2"}
    q = post(client, "profiles", name="Draft")
    clock[0] = "2025-01-05T00:00:00.000000+00:00"
    t = post(
        client,
        f"tents/{t['id']}/profile",
        profile_id=q["id"],
        expected_revision=t["revision"],
    )
    read(client, t, 6, co2=0)
    assert overview(client, t)["warnings"][0]["metric"] == "co2"
    t = post(
        client,
        f"tents/{t['id']}/profile",
        profile_id=p["id"],
        expected_revision=t["revision"],
    )
    read(client, t, 7, co2=1000)
    assert overview(client, t)["warnings"] == []
    history = get(client, f"tents/{t['id']}/history")
    assert len(history["items"]) >= 6 and history["assignments"]


def test_backdated_equal_timestamp_order_offsets_and_snapshots(client, clock):
    t, p = setup(client)
    bad = read(client, t, 5, humidity=40)
    read(client, t, 3)
    assert overview(client, t)["warnings"][0]["reading_id"] == bad["id"]
    good = read(client, t, 5)
    assert overview(client, t)["warnings"] == []
    same = post(
        client,
        f"tents/{t['id']}/readings",
        observed_at="2025-01-05T07:00:00-05:00",
        temperature_f=70,
        humidity=30,
    )
    assert same["observed_at"] == good["observed_at"]
    assert overview(client, t)["warnings"][0]["reading_id"] == same["id"]
    clock[0] = "2025-01-06T00:00:00.000000+00:00"
    put(
        client,
        "profiles/" + p["id"],
        expected_revision=p["revision"],
        name="Changed limits",
        targets={"humidity_min": 10, "humidity_max": 50},
    )
    assert overview(client, t)["warnings"]
    late = read(client, t, 4, humidity=40)
    assert late["snapshot"]["name"] == "Mixed Fruiting"
    newer = read(client, t, 7, humidity=40)
    assert newer["snapshot"]["name"] == "Changed limits"
    assert overview(client, t)["warnings"] == []
    original = next(
        r
        for r in get(client, f"tents/{t['id']}/readings")["items"]
        if r["id"] == bad["id"]
    )
    assert original["snapshot"]["targets"]["humidity_min"] == 80
    before_assignment = post(
        client,
        f"tents/{t['id']}/readings",
        observed_at="2024-12-31T23:00:00Z",
        temperature_f=20,
        humidity=1,
    )
    assert before_assignment["evaluations"] == {}


def test_corrections_are_append_only_reconstruct_state_and_preserve_original_outcomes(
    client,
):
    t, p = setup(client)
    bad = read(client, t, 2, humidity=40)
    good = read(client, t, 4)
    corrected = post(
        client,
        f"tents/{t['id']}/readings/{good['id']}/correct",
        observed_at="2025-01-04T12:00:00Z",
        temperature_f=70,
        humidity=50,
        reason="Transcription error",
    )
    assert overview(client, t)["warnings"][0]["reading_id"] == corrected["id"]
    read(client, t, 6)
    post(
        client,
        f"tents/{t['id']}/readings/{bad['id']}/correct",
        observed_at="2025-01-02T12:00:00Z",
        temperature_f=70,
        humidity=10,
        reason="Historical correction",
    )
    assert overview(client, t)["warnings"] == []
    history = get(client, f"tents/{t['id']}/readings")["items"]
    original = next(r for r in history if r["id"] == good["id"])
    assert (
        original["evaluations"]["humidity"] == "normal"
        and original["superseded_by"] == corrected["id"]
    )
    assert (
        get(client, f"tents/{t['id']}/history")["items"][0]["after"]["state"]
        == "normal"
    )
    response = client.post(
        f"/api/environment/tents/{t['id']}/readings/{good['id']}/correct",
        json={
            "request_key": str(uuid4()),
            "observed_at": "2025-01-04T12:00:00Z",
            "temperature_f": 70,
            "humidity": 90,
            "reason": "Again",
        },
    )
    assert response.status_code == 409
    with client.app.state.engine.begin() as c:
        with pytest.raises(IntegrityError):
            c.execute(
                text("UPDATE environmental_readings SET humidity=99 WHERE id=:id"),
                {"id": good["id"]},
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("temperature_f", "NaN"),
        ("temperature_f", True),
        ("humidity", False),
        ("temperature_f", "Infinity"),
        ("humidity", 101),
        ("humidity", -1),
        ("co2", -1),
        ("co2", "nan"),
        ("humidifier", 11),
        ("fan", 1.5),
        ("fan", True),
        ("observed_at", "2025-01-01T00:00:00"),
        ("observed_at", "1899-01-01T00:00:00Z"),
        ("observed_at", "2099-01-01T00:00:00Z"),
    ],
)
def test_invalid_readings_are_rejected_without_mutation(client, field, value):
    t = post(client, "tents", name="Test")
    body = {
        "request_key": str(uuid4()),
        "observed_at": "2025-01-03T00:00:00Z",
        "temperature_f": 70,
        "humidity": 90,
        field: value,
    }
    assert (
        client.post(f"/api/environment/tents/{t['id']}/readings", json=body).status_code
        == 422
    )
    assert get(client, f"tents/{t['id']}/readings")["total"] == 0


@pytest.mark.parametrize(
    "targets",
    [
        {"temperature_f_min": 80, "temperature_f_max": 60},
        {"humidity_min": 101},
        {"co2_max": -5},
        {"humidity_min": "nan"},
    ],
)
def test_profile_validation(client, targets):
    assert (
        client.post(
            "/api/environment/profiles",
            json={"request_key": str(uuid4()), "name": "Invalid", "targets": targets},
        ).status_code
        == 422
    )
    assert get(client, "profiles") == []


def test_idempotency_and_timezone_dst_instants(client):
    t, p = setup(client)
    body = {
        "request_key": str(uuid4()),
        "observed_at": "2025-11-02T01:30:00-04:00",
        "temperature_f": 70,
        "humidity": 90,
    }
    path = f"/api/environment/tents/{t['id']}/readings"
    r = client.post(path, json=body)
    assert r.status_code == 200
    assert client.post(path, json=body).json() == r.json()
    body["humidity"] = 50
    assert client.post(path, json=body).status_code == 409
    body["request_key"] = str(uuid4())
    body["observed_at"] = "2025-11-02T01:30:00-05:00"
    second = client.post(path, json=body).json()
    assert r.json()["observed_at"] == "2025-11-02T05:30:00.000000+00:00"
    assert second["observed_at"] == "2025-11-02T06:30:00.000000+00:00"
    assert overview(client, t)["warnings"][0]["reading_id"] == second["id"]


def container(client):
    with Session(client.app.state.engine) as s, s.begin():
        s.add(GrowBatch(id="GB-ENV", batch_origin="prepared", allocation_mode="shared"))
        s.flush()
        s.add(
            FruitingContainer(
                id="FR-ENV", batch_id="GB-ENV", material_type="tray", stage="ready"
            )
        )
    return "FR-ENV"


def test_occupancy_overlap_reentry_exact_correlation_and_audit(client):
    t, p = setup(client)
    other = post(client, "tents", name="Other")
    fr = container(client)
    initial = get(client, "occupancy")["total"]
    assert initial == 0
    a = post(
        client,
        f"tents/{t['id']}/occupancy",
        fruiting_id=fr,
        entered_at="2025-01-02T12:00:00Z",
        left_at="2025-01-04T12:00:00Z",
    )
    for tid in [t["id"], other["id"]]:
        assert (
            client.post(
                f"/api/environment/tents/{tid}/occupancy",
                json={
                    "request_key": str(uuid4()),
                    "fruiting_id": fr,
                    "entered_at": "2025-01-03T12:00:00Z",
                },
            ).status_code
            == 409
        )
    read(client, t, 1)
    r = read(client, t, 2)
    read(client, t, 3)
    read(client, t, 4)
    history = get(client, f"containers/{fr}/readings")
    assert [x["observed_at"] for x in history["items"]] == [
        "2025-01-03T12:00:00.000000+00:00",
        r["observed_at"],
    ]
    b = post(
        client,
        f"tents/{other['id']}/occupancy",
        fruiting_id=fr,
        entered_at="2025-01-04T12:00:00Z",
        left_at="2025-01-05T00:00:00Z",
    )
    post(
        client,
        f"tents/{t['id']}/occupancy",
        fruiting_id=fr,
        entered_at="2025-01-06T00:00:00Z",
    )
    a = put(
        client,
        f"tents/{t['id']}/occupancy/{a['id']}",
        fruiting_id=fr,
        entered_at="2025-01-01T12:00:00Z",
        left_at="2025-01-04T12:00:00Z",
        expected_revision=a["revision"],
        reason="Correct entry",
    )
    assert (
        get(client, f"audit/tent_occupancies/{a['id']}")["items"][0]["reason"]
        == "Correct entry"
    )
    with Session(client.app.state.engine) as s:
        row = s.get(FruitingContainer, fr)
        assert row.stage == "ready" and row.batch_id == "GB-ENV"
    with client.app.state.engine.begin() as c:
        with pytest.raises(IntegrityError):
            c.execute(
                text(
                    "INSERT INTO tent_occupancies(tent_id,fruiting_id,entered_at,revision) VALUES (:t,:f,'2025-01-03T00:00:00.000000+00:00',1)"
                ),
                {"t": other["id"], "f": fr},
            )


def test_dashboard_counts_pagination_archived_warnings_and_bounded_queries(client):
    t, p = setup(client)
    for n in range(9):
        tent = post(client, "tents", name="Tent " + str(n))
        tent = post(
            client,
            f"tents/{tent['id']}/profile",
            profile_id=p["id"],
            expected_revision=tent["revision"],
        )
        read(client, tent, 2, temperature_f=40, humidity=10, co2=2000)
    summary = client.get("/api/dashboard/summary").json()
    assert summary["counts"]["open_alerts"] == 27
    assert summary["attention_total"] == 27 and len(summary["attention_items"]) == 25
    page = client.get("/api/dashboard/attention?page=2").json()
    assert page["total"] == 27 and len(page["items"]) == 2
    assert all(a["target"].startswith("/environment?tent=") for a in page["items"])
    put(
        client,
        f"tents/{tent['id']}",
        name=tent["name"],
        status="archived",
        expected_revision=tent["revision"],
    )
    assert client.get("/api/dashboard/summary").json()["counts"]["open_alerts"] == 27
    assert len(get(client, f"tents/{tent['id']}/readings?page_size=1")["items"]) == 1


def test_upgrade_fresh_schema_drift_and_backup_roundtrip(settings, tmp_path):
    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0013_journal_photos")
    engine = make_engine(settings)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO grow_batches(id,batch_origin,allocation_mode,status,created_at) VALUES ('GB-OLD','prepared','shared','active','2025-01-01')"
            )
        )
        c.execute(
            text(
                "INSERT INTO fruiting_containers (id,batch_id,material_type,stage,status,created_at) VALUES ('FR-OLD','GB-OLD','tray','ready','active','2025-01-01')"
            )
        )
    with TestClient(create_app(settings)) as c:
        assert get(c, "tents") == []
        t, p = setup(c)
        original = read(c, t, 2, humidity=40)
        replacement = post(
            c,
            f"tents/{t['id']}/readings/{original['id']}/correct",
            observed_at=original["observed_at"],
            temperature_f=70,
            humidity=45,
            reason="Backup traceability",
        )
        occupancy = post(
            c,
            f"tents/{t['id']}/occupancy",
            fruiting_id="FR-OLD",
            entered_at="2025-01-01T00:00:00Z",
        )
        with c.app.state.engine.connect() as con:
            assert (
                compare_metadata(MigrationContext.configure(con), Base.metadata) == []
            )
            assert (
                con.execute(
                    text("SELECT stage FROM fruiting_containers WHERE id='FR-OLD'")
                ).scalar()
                == "ready"
            )
        artifact = create_backup(settings.data_dir)
        verified = check_archive(artifact.path)
        try:
            with TestClient(
                create_app(
                    Settings(data_dir=verified.root, frontend_dir=settings.frontend_dir)
                )
            ) as restored:
                assert overview(restored, t)["warnings"][0]["metric"] == "humidity"
                assert get(restored, f"tents/{t['id']}/readings")["total"] == 2
                assert get(restored, "occupancy")["items"][0]["id"] == occupancy["id"]
                assert (
                    get(restored, "containers/FR-OLD/readings")["items"][0]["id"]
                    == replacement["id"]
                )
                assert get(restored, f"audit/tent_occupancies/{occupancy['id']}")[
                    "items"
                ]
                assert get(restored, f"tents/{t['id']}/history")["items"]
        finally:
            verified.cleanup()
            artifact.cleanup()
    with pytest.raises(RuntimeError, match="Environmental history exists"):
        command.downgrade(migration_config(settings), "0013_journal_photos")
    engine.dispose()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e999"])
def test_nonfinite_json_tokens_are_safely_rejected(client, value):
    tent = post(client, "tents", name="Finite inputs only")
    body = (
        '{"request_key":"'
        + str(uuid4())
        + '","observed_at":"2025-01-02T00:00:00Z","temperature_f":'
        + value
        + ',"humidity":90}'
    )
    response = client.post(
        "/api/environment/tents/" + tent["id"] + "/readings",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert get(client, f"tents/{tent['id']}/readings")["total"] == 0
