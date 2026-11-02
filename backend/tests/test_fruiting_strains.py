"""FR identity is a read-only view of physical contributions, not genetic ancestry."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from app.main import create_app
from test_foundation import client, settings  # noqa: F401
from test_provenance import acquisition, grow, provenance
from test_library import upload


def sources(client, names):
    strains, records = {}, []
    for name in names:
        identity = {}
        if name is not None:
            identity = (
                {"strain_id": strains[name]}
                if name in strains
                else {"inline_strain": {"name": name}}
            )
        acquired = acquisition(client, **identity)
        if name is not None:
            strains[name] = acquired["line"]["strain_id"]
        records.append(acquired["records"][0])
    return records, strains


def assert_identity(client, fruiting, state, names):
    detail = client.get(f"/api/library/fruiting/{fruiting['id']}")
    assert detail.status_code == 200, detail.text
    row = detail.json()
    listed = next(
        r
        for r in client.get("/api/library/fruiting?status=all").json()
        if r["id"] == row["id"]
    )
    for value in (fruiting, row, listed):
        assert value["strain_identification"] == state
        assert sorted(s["name"] for s in value["contributing_strains"]) == sorted(names)
        if state == "known":
            assert value["strain_name"] == names[0]
            assert value["strain_id"] == value["contributing_strains"][0]["id"]
        else:
            assert value["strain_id"] is None and value["strain_name"] is None
    linked = {
        r["record"]["name"]
        for r in provenance(client, row)["relationships"]
        if r["record"]["kind"] == "strains"
    }
    assert linked == set(names)
    return row


@pytest.mark.parametrize(
    "names,state,known",
    [
        (["Oyster"], "known", ["Oyster"]),
        (["Oyster", "Oyster"], "known", ["Oyster"]),
        (["Oyster", "Chestnut"], "mixed", ["Oyster", "Chestnut"]),
        (["Oyster", None], "partial", ["Oyster"]),
        (["Oyster", "Chestnut", None], "partial", ["Oyster", "Chestnut"]),
        ([None, None], "unknown", []),
        ([], "unknown", []),
    ],
)
def test_shared_strain_identity_from_actual_sources(client, names, state, known):
    spawn, strains = sources(client, names)
    batch = grow(client, [s["id"] for s in spawn], allocations=[[], []])
    for fruiting in batch["containers"]:
        assert_identity(client, fruiting, state, known)
    p = provenance(client, batch["containers"][0])
    if len(spawn) > 1:
        assert (
            "Mixed culture lines: provenance does not imply hybridization"
            in p["warnings"]
        )
    if len(strains) > 1:
        assert "Mixed named strains: no synthetic strain is created" in p["warnings"]
    assert len(client.get("/api/library/strains").json()) == len(strains)
    assert len(client.get("/api/library/lines").json()) == len(spawn)


def test_specific_allocations_do_not_inherit_other_batch_sources(client):
    spawn, _ = sources(client, ["Oyster", "Chestnut", None])
    a, b, u = [s["id"] for s in spawn]
    batch = grow(client, [a, b, u], "specific", [[a], [b], [a, b], [a, u], [u], []])
    expected = [
        ("known", ["Oyster"]),
        ("known", ["Chestnut"]),
        ("mixed", ["Oyster", "Chestnut"]),
        ("partial", ["Oyster"]),
        ("unknown", []),
        ("unknown", []),
    ]
    for fruiting, (state, names) in zip(batch["containers"], expected):
        assert_identity(client, fruiting, state, names)


@pytest.mark.parametrize("known", [True, False])
def test_acquired_fruiting_uses_acquired_line(client, known):
    batch = acquisition(
        client,
        "fruiting_bag",
        **({"inline_strain": {"name": "Acquired Oyster"}} if known else {}),
    )
    assert_identity(
        client,
        batch["records"][0],
        "known" if known else "unknown",
        ["Acquired Oyster"] if known else [],
    )


def snapshot(engine):
    with engine.connect() as c:
        return {
            table: c.execute(text(f'SELECT * FROM "{table}" ORDER BY rowid')).all()
            for table in inspect(engine).get_table_names()
        }


def test_historical_fruiting_resolves_after_restart_without_backfill(settings):
    with TestClient(create_app(settings)) as client:
        spawn, _ = sources(client, ["Historic Oyster"])
        batch = grow(client, [spawn[0]["id"]])["batch"]
        # Pre-correction 2B schema has no stored FR strain identity. Insert that
        # historical shape directly, without the corrected registration serializer.
        with client.app.state.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO fruiting_containers (id,batch_id,material_type,stage,status,created_at) VALUES ('FR-9000',:batch,'tray','ready','active','2026-01-01')"
                ),
                {"batch": batch["id"]},
            )
        assert upload(client, "fruiting", "FR-9000").status_code == 201
        for kind, code in [
            ("spawn", spawn[0]["id"]),
            ("lines", spawn[0]["line_id"]),
            ("fruiting", "FR-9000"),
        ]:
            assert (
                client.post(
                    f"/api/library/{kind}/{code}/status", json={"status": "archived"}
                ).status_code
                == 200
            )
        before = snapshot(client.app.state.engine)
    with TestClient(create_app(settings)) as client:
        row = client.get("/api/library/fruiting/FR-9000").json()
        assert_identity(client, row, "known", ["Historic Oyster"])
        assert row["status"] == "archived"
        assert snapshot(client.app.state.engine) == before
