import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic import command
from app.database import migration_config
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn, fruit, stage, harvest, detail
from test_library import image_bytes, upload


def path(code, kind, number=1):
    event = f"flushes/{number}/fruiting" if kind == "fruiting" else "completion"
    return f"/api/fruiting/records/{code}/{event}/photos"


def attach(client, code, kind, number=1, data=None, status=201):
    r = client.post(
        path(code, kind, number),
        files={
            "file": (
                "journal.png",
                image_bytes() if data is None else data,
                "image/png",
            )
        },
    )
    assert r.status_code == status, r.text
    return r.json()


@pytest.mark.parametrize("kind", ["fruiting", "complete"])
def test_optional_journal_photos_failed_upload_retry_and_idempotency(client, kind):
    row = spawn(client)[0]
    code = row["id"]
    stage(client, code, "pinning", "2026-01-03")
    result = stage(
        client, code, kind, "2026-01-05", notes="Journal notes", key="journal-event"
    )
    assert client.get(path(code, kind)).json() == []
    before = detail(client, code)
    attach(client, code, kind, data=b"bad image", status=422)
    assert detail(client, code) == before
    photos = [attach(client, code, kind) for _ in range(2)]
    assert {p["id"] for p in client.get(path(code, kind)).json()} == {
        p["id"] for p in photos
    }
    assert (
        stage(
            client, code, kind, "2026-01-05", notes="Journal notes", key="journal-event"
        )
        == result
    )
    data = detail(client, code)
    if kind == "fruiting":
        assert data["flushes"][0]["fruiting_date"] == "2026-01-05"
        assert data["flushes"][0]["fruiting_notes"] == "Journal notes"
        assert data["record"]["label_occupied"]
        stage(client, code, "complete", "2026-01-10")
    else:
        assert data["run"]["completed_date"] == "2026-01-05"
        assert data["run"]["closing_notes"] == "Journal notes"
        assert not data["record"]["label_occupied"]
    # Later edits remain available after completion/archive without editing dates.
    client.post(f"/api/library/fruiting/{code}/archive")
    saved = detail(client, code)
    later = attach(client, code, kind)
    assert client.delete(f"/api/library/photos/{photos[0]['id']}").status_code == 204
    assert {p["id"] for p in client.get(path(code, kind)).json()} == {
        photos[1]["id"],
        later["id"],
    }
    assert detail(client, code)["run"] == saved["run"]
    assert detail(client, code)["flushes"] == saved["flushes"]
    events = client.get(f"/api/library/fruiting/{code}/activity").json()
    assert sum(e["event_type"] == kind for e in events) == 1


def test_fruiting_photos_use_exact_flush_and_never_reused_label(client):
    row = fruit(client)
    code = row["id"]
    first = attach(client, code, "fruiting")
    h = harvest(client, code)
    stage(client, code, "next_flush", "2026-01-10")
    attach(client, code, "fruiting", 2, status=409)
    stage(client, code, "fruiting", "2026-01-12", notes="Second fruiting")
    second = attach(client, code, "fruiting", 2)
    assert [p["id"] for p in client.get(path(code, "fruiting", 1)).json()] == [
        first["id"]
    ]
    assert [p["id"] for p in client.get(path(code, "fruiting", 2)).json()] == [
        second["id"]
    ]
    assert client.get(f"/api/fruiting/harvests/{h['id']}/photos").json() == []
    stage(client, code, "complete", "2026-01-15")
    closing = attach(client, code, "complete")
    other = spawn(client)[0]
    assert other["physical_label"] == row["physical_label"]
    attach(client, other["id"], "complete", status=409)
    assert client.get(path(row["physical_label"], "complete")).status_code == 404
    assert client.get(path(code, "complete")).json()[0]["id"] == closing["id"]


def test_missing_unrecorded_events_rejected_without_orphans(client, settings):
    row = spawn(client)[0]
    code = row["id"]
    for kind in ["fruiting", "complete"]:
        attach(client, code, kind, status=409)
    attach(client, code, "fruiting", 2, status=404)
    attach(client, "FR-missing", "complete", status=404)
    assert list((settings.data_dir / "photos").iterdir()) == []
    assert client.get(path(code, "fruiting", 0)).status_code == 422


def test_db_enforces_journal_owner_event_and_immutable_links(client):
    one = fruit(client)
    other = spawn(client)[0]
    photo = upload(client, "fruiting", other["id"]).json()
    for kind, number, owner in [
        ("fruiting", 1, one["id"]),
        ("fruiting", 1, other["id"]),
        ("completed", None, other["id"]),
        ("completed", 1, other["id"]),
    ]:
        with pytest.raises(IntegrityError), client.app.state.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO journal_photos (photo_id,fruiting_id,event_type,flush_number) VALUES (:p,:f,:e,:n)"
                ),
                dict(p=photo["id"], f=owner, e=kind, n=number),
            )
    valid = attach(client, one["id"], "fruiting")
    with pytest.raises(IntegrityError), client.app.state.engine.begin() as c:
        c.execute(
            text("UPDATE journal_photos SET flush_number=2 WHERE photo_id=:p"),
            dict(p=valid["id"]),
        )


def test_populated_0012_upgrade_preserves_existing_event_photos_and_dates(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_pinning_photos import attach as pin_photo, photo_path

    with TestClient(create_app(settings)) as client:
        row = fruit(client)
        code = row["id"]
        pin = pin_photo(client, code, 1)
        h = harvest(client, code)
        r = client.post(
            f"/api/fruiting/harvests/{h['id']}/photos",
            files={"file": ("old.png", image_bytes(), "image/png")},
        )
        assert r.status_code == 201
        old = r.json()
        stage(client, code, "complete", "2026-01-10", notes="Original completion")
        before = detail(client, code)
    # Reconstruct the previous schema with real, populated 0012 relationships/files.
    command.downgrade(migration_config(settings), "0012_pinning_photos")
    with TestClient(create_app(settings)) as client:
        assert detail(client, code) == before
        assert client.get(photo_path(code, 1)).json()[0]["id"] == pin["id"]
        assert (
            client.get(f"/api/fruiting/harvests/{h['id']}/photos").json()[0]["id"]
            == old["id"]
        )
        for photo in [pin, old]:
            assert client.get(photo["url"]).content == image_bytes()
        assert client.get(path(code, "fruiting")).json() == []
        assert client.get(path(code, "complete")).json() == []
        assert detail(client, code)["flushes"][0]["fruiting_notes"] is None
        attach(client, code, "fruiting")
        attach(client, code, "complete")
    command.check(migration_config(settings))
    with pytest.raises(RuntimeError, match="Journal photo or notes history exists"):
        command.downgrade(migration_config(settings), "0012_pinning_photos")
