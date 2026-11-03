from concurrent.futures import ThreadPoolExecutor
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.main import create_app
from app.database import migration_config, make_engine
from test_foundation import client, settings  # noqa: F401
from test_library import upload, receive


def post(client, path, data, status=201):
    r = client.post("/api/provenance/" + path, json=data)
    assert r.status_code == status, r.text
    return r.json()


def acquisition(client, entry="spawn_jar", **values):
    return post(client, "acquisitions", {"entry_type": entry, "line": {}, **values})


def provenance(client, record):
    response = client.get(f"/api/provenance/{record['kind']}/{record['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def establish(client, source, **values):
    return post(client, f"{source['kind']}/{source['id']}/establish", values)


def grow(client, ids, mode="shared", allocations=None):
    return post(
        client,
        "grows",
        {
            "source_ids": ids,
            "allocation_mode": mode,
            "containers": [
                {"source_ids": sources} for sources in (allocations or [[]])
            ],
        },
    )


def test_universal_acquisition_identity_and_no_fabricated_history(client):
    jar = acquisition(
        client, inline_strain={"name": "Oyster"}, acquisition_date="2026-10-01"
    )
    assert jar["records"][0]["id"] == "SJ-0001"
    assert jar["records"][0]["stage"] == "ready"
    assert jar["line"]["strain_id"] == "STR-0001"
    p = provenance(client, jar["line"])
    assert p["origin_type"] == "external" and p["ancestry_status"] == "unknown"
    assert p["parents"] == [] and p["origin_date"] is None
    bag = acquisition(client, "spawn_bag", stage="colonizing", count=2)
    assert [r["id"] for r in bag["records"]] == ["SB-0001", "SB-0002"]
    assert bag["records"][0]["stage"] == "colonizing"
    acquired = acquisition(
        client, "fruiting_bag", count=2, inline_strain={"name": "Lion mane"}
    )
    assert acquired["batch"]["id"] == "GB-0001"
    assert acquired["batch"]["batch_origin"] == "acquired"
    assert [r["id"] for r in acquired["records"]] == ["FR-0001", "FR-0002"]
    p = provenance(client, acquired["records"][0])
    assert p["origin_type"] == "acquired"
    assert [
        r["record"]["id"] for r in p["relationships"] if r["record"]["kind"] == "lines"
    ] == [acquired["line"]["id"]]
    # No recipe, inoculation, or invented spawn record was generated.
    assert len(client.get("/api/library/spawn").json()) == 3


def test_culture_acquisition_and_existing_line_validation(client):
    original = receive(client, count=1)
    added = post(
        client,
        "acquisitions",
        {"entry_type": "spawn_jar", "existing_line_id": original["line"]["id"]},
    )
    assert added["line"]["id"] == original["line"]["id"]
    assert len(client.get("/api/library/lines").json()) == 1
    r = client.post(
        "/api/provenance/acquisitions",
        json={
            "entry_type": "spawn_jar",
            "line": {},
            "inline_strain": {"name": "Rollback"},
            "quantity": "1",
        },
    )
    assert r.status_code == 422
    assert client.get("/api/library/strains").json() == []
    acquisition(client, "culture", material={"material_type": "agar_plate", "count": 2})
    # Existing Culture Library endpoints still use permanent AG identifiers.
    assert {
        r["id"]
        for r in client.get("/api/library/physical").json()
        if r["material_type"] == "agar_plate"
    } == {"AG-0001", "AG-0002"}


def test_collect_and_independent_spore_establishment(client):
    acquired = acquisition(client, "fruiting_block", inline_strain={"name": "Chestnut"})
    fruiting = acquired["records"][0]
    spore = post(
        client,
        f"fruiting/{fruiting['id']}/collect",
        {"collection_date": "2026-10-01", "quantity": "1", "unit": "print"},
    )
    assert spore["strain_id"] == acquired["line"]["strain_id"]
    first = establish(
        client,
        spore,
        material={"material_type": "agar_plate"},
        origin_date="2026-10-15",
    )
    second = establish(client, spore, unknown_strain=True)
    assert first["line"]["id"] != second["line"]["id"]
    assert second["line"]["strain_id"] is None
    assert first["physical"][0]["id"].startswith("AG-")
    p = provenance(client, first["line"])
    assert p["origin_type"] == "spores" and p["ancestry_status"] == "uncertain"
    assert p["parents"] == [
        {"parent_id": acquired["line"]["id"], "confidence": "possible"}
    ]
    assert p["origin_date"] == "2026-10-15"
    descendants = provenance(client, spore)["relationships"]
    assert {
        r["record"]["id"] for r in descendants if r["record"]["kind"] == "lines"
    } == {first["line"]["id"], second["line"]["id"]}
    unknown = client.post("/api/library/spores", json={}).json()
    assert (
        provenance(client, establish(client, unknown)["line"])["ancestry_status"]
        == "unknown"
    )


def test_single_line_clone_and_isolate(client):
    a = acquisition(client, "fruiting_bag")
    clone = establish(client, a["records"][0], name="Successful clone")
    p = provenance(client, clone["line"])
    assert p["origin_type"] == "clone" and p["ancestry_status"] == "confirmed"
    assert p["parents"] == [{"parent_id": a["line"]["id"], "confidence": "confirmed"}]
    isolate = establish(
        client,
        clone["line"],
        name="Selected isolate",
        material={"material_type": "slant"},
    )
    assert isolate["line"]["strain_id"] == clone["line"]["strain_id"]
    assert provenance(client, isolate["line"])["origin_type"] == "isolate"
    # Routine material registration does not create a new line.
    before = len(client.get("/api/library/lines").json())
    receive(client, existing_line_id=clone["line"]["id"], line=None, count=1)
    assert len(client.get("/api/library/lines").json()) == before
    assert any(
        r["record"]["id"] == isolate["line"]["id"]
        for r in provenance(client, clone["line"])["relationships"]
    )


def test_mixed_shared_provenance_clone_and_controlled_correction(client):
    a = acquisition(client, inline_strain={"name": "Oyster"})
    b = acquisition(client, "spawn_bag", inline_strain={"name": "Chestnut"})
    ids = [a["records"][0]["id"], b["records"][0]["id"]]
    batch = grow(client, ids, allocations=[[], []])
    assert len(batch["warnings"]) == 2
    fruiting = batch["containers"][0]
    clone = establish(client, fruiting)["line"]
    p = provenance(client, clone)
    assert p["ancestry_status"] == "uncertain" and clone["strain_id"] is None
    assert {x["parent_id"] for x in p["parents"]} == {a["line"]["id"], b["line"]["id"]}
    spore = post(client, f"fruiting/{fruiting['id']}/collect", {})
    assert spore["strain_id"] is None
    assert len(client.get("/api/library/strains").json()) == 2
    corrected = client.put(
        f"/api/provenance/lines/{clone['id']}/ancestry",
        json={
            "expected_revision": p["revision"],
            "reason": "Source tray label verified",
            "parents": [{"parent_id": a["line"]["id"], "confidence": "confirmed"}],
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["ancestry_status"] == "confirmed"
    stale = client.put(
        f"/api/provenance/lines/{clone['id']}/ancestry",
        json={
            "expected_revision": p["revision"],
            "reason": "Stale edit",
            "parents": [],
        },
    )
    assert stale.status_code == 409
    history = client.get(f"/api/library/lines/{clone['id']}/activity").json()
    text_history = " ".join(h["description"] for h in history)
    assert "possible" in text_history and "Source tray label verified" in text_history
    assert a["line"]["id"] in text_history and b["line"]["id"] in text_history
    for spawn in a["records"] + b["records"]:
        assert (
            client.get(f"/api/library/spawn/{spawn['id']}").json()["stage"] == "ready"
        )
    # Documenting another batch is not a second consumption event; consumption is deferred.
    other = grow(client, ids)
    assert other["batch"]["id"] != batch["batch"]["id"]


def test_specific_allocation_reuse_within_batch_and_unknown(client):
    a = acquisition(client, count=2)
    ids = [r["id"] for r in a["records"]]
    batch = grow(client, ids, "specific", [[ids[0]], [ids[0], ids[1]], []])
    counts = []
    for container in batch["containers"]:
        p = provenance(client, container)
        counts.append(
            len([r for r in p["relationships"] if r["record"]["kind"] == "spawn"])
        )
    assert counts == [1, 2, 0]
    unknown = establish(client, batch["containers"][2])["line"]
    assert provenance(client, unknown)["ancestry_status"] == "unknown"
    assert post(
        client,
        "grows",
        {
            "source_ids": ids,
            "allocation_mode": "specific",
            "containers": [{"source_ids": ["SJ-9999"]}],
        },
        422,
    )
    assert post(
        client, "grows", {"source_ids": [ids[0], ids[0]], "containers": [{}]}, 422
    )
    assert post(
        client,
        "grows",
        {"source_ids": ids, "containers": [{"source_ids": [ids[0]]}]},
        422,
    )


def test_cycle_rejection_in_api_and_database(client):
    root = acquisition(client)["line"]
    child = establish(client, root)["line"]
    grandchild = establish(client, child)["line"]
    p = provenance(client, root)
    for parent in [root["id"], grandchild["id"]]:
        result = client.put(
            f"/api/provenance/lines/{root['id']}/ancestry",
            json={
                "expected_revision": p["revision"],
                "reason": "Must reject",
                "parents": [{"parent_id": parent, "confidence": "possible"}],
            },
        )
        assert result.status_code == 422, result.text
    with pytest.raises(IntegrityError):
        with client.app.state.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO line_parents VALUES (:line,:parent,'possible')"),
                dict(line=root["id"], parent=grandchild["id"]),
            )
    assert provenance(client, root)["parents"] == []


@pytest.mark.parametrize(
    "entry,kind",
    [("spawn_jar", "spawn"), ("fruiting_bag", "batches"), ("fruiting_bag", "fruiting")],
)
def test_new_record_photos_archive_restore(client, entry, kind):
    a = acquisition(client, entry)
    row = a["batch"] if kind == "batches" else a["records"][0]
    photo = upload(client, kind, row["id"])
    assert photo.status_code == 201, photo.text
    before = provenance(client, row)
    for status in ["archived", "active"]:
        changed = client.post(
            f"/api/library/{kind}/{row['id']}/status", json={"status": status}
        )
        assert changed.status_code == 200
        assert client.get(photo.json()["url"]).status_code == 200
        assert provenance(client, row)["relationships"] == before["relationships"]
    if kind == "spawn":
        p = client.patch(
            f"/api/library/spawn/{row['id']}", json={"stage": "colonizing"}
        )
        assert p.status_code == 200
        assert (
            client.patch(
                f"/api/library/spawn/{row['id']}", json={"stage": "fruiting"}
            ).status_code
            == 422
        )


def test_registration_rollback_and_foreign_key_allocation(client):
    a = acquisition(client)
    before = len(client.get("/api/library/batches").json())
    post(
        client,
        "grows",
        {"source_ids": [a["records"][0]["id"], "SJ-invalid"], "containers": [{}]},
        404,
    )
    assert len(client.get("/api/library/batches").json()) == before
    one = grow(client, [a["records"][0]["id"]])
    two = grow(client, [])
    with pytest.raises(IntegrityError):
        with client.app.state.engine.begin() as c:
            c.execute(
                text("INSERT INTO fruiting_sources VALUES (:fruit,:spawn,:batch)"),
                dict(
                    fruit=two["containers"][0]["id"],
                    spawn=a["records"][0]["id"],
                    batch=one["batch"]["id"],
                ),
            )


def test_concurrent_acquisitions_and_dashboard(client):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: acquisition(client), range(4)))
    assert len({a["records"][0]["id"] for a in results}) == 4
    acquisition(client, "fruiting_bag", count=2)
    counts = client.get("/api/dashboard/summary").json()["counts"]
    assert counts["spawn_containers"] == 4 and counts["fruiting_units"] == 2


def test_migrate_2a_preserves_records_photos_history_and_sequences(settings):
    settings.database_path.parent.mkdir(parents=True)
    config = migration_config(settings)
    command.upgrade(config, "0002_culture_library")
    engine = make_engine(settings)
    original = b"original retained photo bytes"
    (settings.data_dir / "photos").mkdir()
    (settings.data_dir / "photos" / "original.png").write_bytes(original)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO strains (id,name,normalized_name,status,created_at) VALUES ('STR-0007','Historic','historic','active','2025-01-01')"
            )
        )
        c.execute(
            text(
                "INSERT INTO culture_lines (id,strain_id,origin,supplier,status,created_at) VALUES ('CL-0009','STR-0007','gifted','Original supplier','active','2025-01-02')"
            )
        )
        c.execute(
            text(
                "INSERT INTO physical_cultures (id,line_id,material_type,registration_batch,status,created_at) VALUES ('AG-0011','CL-0009','agar_plate','old-batch','active','2025-01-03')"
            )
        )
        c.execute(text("INSERT INTO identity_sequences VALUES ('CL',9)"))
        c.execute(
            text(
                "INSERT INTO photo_attachments (id,physical_id,filename,thumbnail,media_type,is_cover,created_at) VALUES ('photo','AG-0011','original.png','thumb.webp','image/png',1,'2025-01-04')"
            )
        )
        c.execute(
            text(
                "INSERT INTO activity_events (line_id,occurred_at,event_type,description) VALUES ('CL-0009','2025-01-02','created','Original activity')"
            )
        )
    engine.dispose()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as client:
        line = client.get("/api/library/lines/CL-0009").json()
        assert line["origin"] == "gifted" and line["supplier"] == "Original supplier"
        assert provenance(client, line)["parents"] == []
        assert (
            client.get("/api/library/physical/AG-0011/photos").json()[0]["id"]
            == "photo"
        )
        assert client.get("/api/library/photos/photo/original").content == original
        assert (
            client.get("/api/library/lines/CL-0009/activity").json()[0]["description"]
            == "Original activity"
        )
        assert acquisition(client)["line"]["id"] == "CL-0010"
    command.check(config)
    with pytest.raises(RuntimeError, match="Physical label or lifecycle history exists"):
        command.downgrade(config, "0002_culture_library")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/library/lines/CL-0009").status_code == 200


def test_acquisition_metadata_on_existing_lines_and_atomic_rollback(client):
    original = receive(client, count=1)
    payload = {
        "entry_type": "spawn_jar",
        "existing_line_id": original["line"]["id"],
        "supplier": "New container supplier",
        "supplier_reference": "REF-2",
        "supplier_batch": "Lot-2",
    }
    jar = post(client, "acquisitions", payload)["records"][0]
    assert (
        jar["supplier"] == "New container supplier" and jar["supplier_batch"] == "Lot-2"
    )
    batch = post(client, "acquisitions", {**payload, "entry_type": "fruiting_bag"})[
        "batch"
    ]
    assert batch["supplier_reference"] == "REF-2" and batch["supplier_batch"] == "Lot-2"
    post(
        client,
        "acquisitions",
        {**payload, "inline_strain": {"name": "Must roll back"}},
        422,
    )
    assert client.get("/api/library/strains").json() == []
    assert (
        client.get(f"/api/library/lines/{original['line']['id']}").json()["supplier"]
        == "Supplier one"
    )


def test_archived_parent_keeps_descendant_navigation(client):
    root = acquisition(client)["line"]
    child = establish(client, root)["line"]
    for status in ["archived", "active"]:
        assert (
            client.post(
                f"/api/library/lines/{root['id']}/status", json={"status": status}
            ).status_code
            == 200
        )
        assert provenance(client, child)["parents"] == [
            {"parent_id": root["id"], "confidence": "confirmed"}
        ]
        assert any(
            r["record"]["id"] == child["id"]
            for r in provenance(client, root)["relationships"]
        )
    post(
        client,
        "acquisitions",
        {"entry_type": "culture", "existing_line_id": root["id"]},
        422,
    )
