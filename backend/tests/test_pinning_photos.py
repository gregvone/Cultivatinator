from uuid import uuid4
import sqlite3
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.main import create_app
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn, fruit, stage, harvest, detail, cmd
from test_library import image_bytes, upload


def photo_path(code, number):
    return f"/api/fruiting/records/{code}/flushes/{number}/pinning/photos"


def attach(client, code, number, data=None, expected=201):
    response = client.post(
        photo_path(code, number),
        files={
            "file": ("pin.png", image_bytes() if data is None else data, "image/png")
        },
    )
    assert response.status_code == expected, response.text
    return response.json()


def test_pinning_optional_photos_notes_and_retry_preserve_event(client):
    row = spawn(client)[0]
    code = row["id"]
    cmd(
        client,
        f"records/{code}/stage",
        {
            "action": "pinning",
            "action_date": "2026-01-03",
            "notes": "Pins first observed",
        },
        key="pinning-event-photos",
    )
    assert client.get(photo_path(code, 1)).json() == []
    before = detail(client, code)
    attach(client, code, 1, data=b"invalid image", expected=422)
    assert detail(client, code) == before
    first = attach(client, code, 1)
    second = attach(client, code, 1)
    images = client.get(photo_path(code, 1)).json()
    assert {p["id"] for p in images} == {first["id"], second["id"]}
    assert detail(client, code)["flushes"][0]["pinning_date"] == "2026-01-03"
    assert detail(client, code)["flushes"][0]["pinning_notes"] == "Pins first observed"
    assert detail(client, code)["record"]["label_occupied"]
    replay = cmd(
        client,
        f"records/{code}/stage",
        {
            "action": "pinning",
            "action_date": "2026-01-03",
            "notes": "Pins first observed",
        },
        key="pinning-event-photos",
    )
    assert replay["run"]["current_flush"] == 1
    activity = client.get("/api/library/fruiting/" + code + "/activity").json()
    assert sum(e["event_type"] == "pinning" for e in activity) == 1


def test_next_flush_and_separate_grows_never_share_pinning_photos(client):
    one = fruit(client)
    first = attach(client, one["id"], 1)
    harvest(client, one["id"])
    stage(client, one["id"], "next_flush", "2026-01-10", notes="Second flush pins")
    second = attach(client, one["id"], 2)
    other = spawn(client)[0]
    stage(client, other["id"], "pinning", "2026-01-03")
    third = attach(client, other["id"], 1)
    assert [p["id"] for p in client.get(photo_path(one["id"], 1)).json()] == [
        first["id"]
    ]
    assert [p["id"] for p in client.get(photo_path(one["id"], 2)).json()] == [
        second["id"]
    ]
    assert [p["id"] for p in client.get(photo_path(other["id"], 1)).json()] == [
        third["id"]
    ]
    assert (
        detail(client, one["id"])["flushes"][1]["pinning_notes"] == "Second flush pins"
    )
    assert client.get(photo_path(one["physical_label"], 1)).status_code == 404


def test_adding_and_removing_later_does_not_change_pinning_date_or_harvest_photos(
    client,
):
    row = fruit(client)
    entry = harvest(client, row["id"])
    photo = attach(client, row["id"], 1)
    assert client.get(f"/api/fruiting/harvests/{entry['id']}/photos").json() == []
    stage(client, row["id"], "complete", "2026-01-10")
    later = attach(client, row["id"], 1)
    assert client.post(f"/api/library/photos/{later['id']}/cover").status_code == 200
    assert client.delete(f"/api/library/photos/{photo['id']}").status_code == 204
    assert [p["id"] for p in client.get(photo_path(row["id"], 1)).json()] == [
        later["id"]
    ]
    data = detail(client, row["id"])
    assert data["flushes"][0]["pinning_date"] == "2026-01-03"
    assert data["run"]["completed_date"] == "2026-01-10"
    history = client.get("/api/library/fruiting/" + row["id"] + "/activity").json()
    assert any(
        e["event_type"] == "photo_removed" and "Pinning, flush 1" in e["description"]
        for e in history
    )


def test_missing_or_unrecorded_pinning_rejects_upload_without_orphans(client, settings):
    row = spawn(client)[0]
    attach(client, row["id"], 1, expected=409)
    attach(client, row["id"], 2, expected=404)
    assert client.get("/api/library/fruiting/" + row["id"] + "/photos").json() == []
    assert list((settings.data_dir / "photos").iterdir()) == []
    assert client.get(photo_path(row["id"], 0)).status_code == 422


def test_db_photo_relationship_rejects_other_grow_and_flush(client):
    one = fruit(client)
    other = spawn(client)[0]
    photo = upload(client, "fruiting", other["id"]).json()
    with pytest.raises(IntegrityError):
        with client.app.state.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO pinning_photos (photo_id,fruiting_id,flush_number) VALUES (:photo,:record,1)"
                ),
                {"photo": photo["id"], "record": one["id"]},
            )


def test_populated_0011_upgrade_preserves_dates_photos_and_no_pinning_guess(settings):
    settings.database_path.parent.mkdir(parents=True)
    command.upgrade(migration_config(settings), "0011_fruiting")
    with sqlite3.connect(settings.database_path) as c:
        c.execute(
            "INSERT INTO grow_batches (id,status,created_at,batch_origin,allocation_mode) VALUES ('GB-0090','active','2026-01-01','prepared','shared')"
        )
        c.execute(
            "INSERT INTO fruiting_containers (id,batch_id,material_type,stage,status,created_at) VALUES ('FR-0090','GB-0090','tray','fruiting','active','2026-01-01')"
        )
        c.execute(
            "INSERT INTO fruiting_runs (fruiting_id,stage,current_flush) VALUES ('FR-0090','fruiting',2)"
        )
        c.execute(
            "INSERT INTO fruiting_flushes (fruiting_id,number,pinning_date,fruiting_date) VALUES ('FR-0090',1,'2026-01-03','2026-01-05')"
        )
        c.execute(
            "INSERT INTO fruiting_flushes (fruiting_id,number,pinning_date) VALUES ('FR-0090',2,NULL)"
        )
        c.execute(
            "INSERT INTO harvest_entries (id,fruiting_id,flush_number,harvest_date,revision,created_at,updated_at) VALUES ('HR-0090','FR-0090',1,'2026-01-07',1,'2026-01-07','2026-01-07')"
        )
        c.execute(
            "INSERT INTO photo_attachments (id,filename,thumbnail,media_type,is_cover,created_at,fruiting_id) VALUES ('old-photo','legacy.png','legacy-thumb.webp','image/png',1,'2026-01-07','FR-0090')"
        )
        c.execute(
            "INSERT INTO harvest_photos (photo_id,harvest_id) VALUES ('old-photo','HR-0090')"
        )
    (settings.data_dir / "photos").mkdir()
    (settings.data_dir / "photos" / "legacy.png").write_bytes(image_bytes())
    (settings.data_dir / "photos" / "legacy-thumb.webp").write_bytes(
        image_bytes("WEBP")
    )
    with TestClient(create_app(settings)) as client:
        data = detail(client, "FR-0090")
        assert data["flushes"][0]["pinning_date"] == "2026-01-03"
        assert data["flushes"][0]["pinning_notes"] is None
        assert data["flushes"][1]["pinning_date"] is None
        assert client.get(photo_path("FR-0090", 1)).json() == []
        old = client.get("/api/fruiting/harvests/HR-0090/photos").json()
        assert [p["id"] for p in old] == ["old-photo"]
        assert client.get(old[0]["url"]).content == image_bytes()
        attach(client, "FR-0090", 1)
        attach(client, "FR-0090", 2, expected=409)
    command.check(migration_config(settings))
    with pytest.raises(RuntimeError, match="Pinning photo or notes history exists"):
        command.downgrade(migration_config(settings), "0011_fruiting")
