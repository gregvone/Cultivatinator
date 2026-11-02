from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from app import library, photos
from app.database import migration_config
from app.main import create_app
from app.models import ActivityEvent, IdentitySequence, PhotoAttachment, PhysicalCulture
from test_foundation import client, settings  # noqa: F401 -- shared isolated fixtures


def strain(client, name="Test strain"):
    r = client.post("/api/library/strains", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def receive(client, strain_id=None, count=3, **kwargs):
    payload = {
        "strain_id": strain_id,
        "line": {"supplier": "Supplier one"},
        "material": {"count": count, "quantity": "10.125", "unit": "mL"},
    }
    payload.update(kwargs)
    r = client.post("/api/library/receive-culture", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def image_bytes(fmt="PNG"):
    data = BytesIO()
    Image.new("RGB", (900, 300), "#669988").save(data, format=fmt)
    return data.getvalue()


def upload(client, kind, code, data=None):
    return client.post(
        f"/api/library/{kind}/{code}/photos",
        files={
            "file": (
                "../../evil.bin",
                data if data is not None else image_bytes(),
                "application/octet-stream",
            )
        },
    )


def test_strain_lifecycle_duplicate_search_relationships(client):
    assert client.get("/api/library/strains").json() == []
    s = strain(client, "  Blue   Oyster  ")
    assert s["name"] == "Blue Oyster"
    assert (
        client.post(
            "/api/library/strains", json={"name": "ＢＬＵＥ oyster"}
        ).status_code
        == 409
    )
    assert client.post("/api/library/strains", json={"name": "   "}).status_code == 422
    data = receive(client, s["id"])
    spore = client.post(
        "/api/library/spores",
        json={"strain_id": s["id"], "material_type": "spore_print"},
    ).json()
    assert (
        client.patch(
            f"/api/library/strains/{s['id']}",
            json={"notes": "Reference notes", "scientific_name": "Reference name"},
        ).status_code
        == 200
    )
    assert client.get("/api/library/strains?q=BLUE%20OYSTER").json()[0]["id"] == s["id"]
    summary = client.get(f"/api/library/strains/{s['id']}").json()
    assert (
        summary["line_count"],
        summary["physical_count"],
        summary["spore_count"],
    ) == (1, 3, 1)
    assert (
        client.post(
            f"/api/library/strains/{s['id']}/status", json={"status": "archived"}
        ).status_code
        == 200
    )
    assert client.get("/api/library/strains").json() == []
    assert client.get(f"/api/library/lines/{data['line']['id']}").status_code == 200
    assert client.get(f"/api/library/spores/{spore['id']}").status_code == 200
    assert (
        client.post("/api/library/spores", json={"strain_id": s["id"]}).status_code
        == 409
    )
    assert (
        client.post("/api/library/strains", json={"name": "blue oyster"}).status_code
        == 409
    )
    client.post(f"/api/library/strains/{s['id']}/status", json={"status": "active"})
    assert client.get("/api/library/strains").json()[0]["id"] == s["id"]
    events = client.get(f"/api/library/strains/{s['id']}/activity").json()
    assert {e["event_type"] for e in events} == {
        "created",
        "edited",
        "archived",
        "restored",
    }


def test_acquisitions_physical_edit_archive_dashboard(client):
    s = strain(client)
    first = receive(client, s["id"])
    second = receive(client, s["id"], material=None)
    assert first["line"]["id"] != second["line"]["id"]
    assert [p["id"] for p in first["physical"]] == ["LC-0001", "LC-0002", "LC-0003"]
    assert len({p["registration_batch"] for p in first["physical"]}) == 1
    assert first["physical"][0]["quantity"] == "10.125"
    extra = receive(
        client, s["id"], line=None, existing_line_id=first["line"]["id"], count=2
    )
    assert extra["physical"][0]["id"] == "LC-0004"
    assert len(client.get("/api/library/lines").json()) == 2
    assert (
        len(client.get(f"/api/library/physical?line_id={first['line']['id']}").json())
        == 5
    )
    item = first["physical"][0]
    url = f"/api/library/physical/{item['id']}"
    edited = client.patch(
        url,
        json={
            "name": "Individual A",
            "quantity": "8.250",
            "unit": "mL",
            "purchase_price": "12.34",
            "storage_location": "Cold shelf",
        },
    ).json()
    assert edited["line_id"] == first["line"]["id"]
    assert edited["quantity"] == "8.250" and edited["purchase_price"] == "12.34"
    assert client.patch(url, json={"line_id": second["line"]["id"]}).status_code == 422
    assert client.patch(url, json={"material_type": "spore_print"}).status_code == 422
    assert client.patch(url, json={"unit": None}).status_code == 422
    assert len(client.get("/api/library/physical?q=individual").json()) == 1
    assert len(client.get("/api/library/physical?material_type=lc_syringe").json()) == 5
    counts = client.get("/api/dashboard/summary").json()["counts"]
    assert counts == dict(
        active_cultures=5, spawn_containers=0, fruiting_units=0, open_alerts=0
    )
    client.post(url + "/status", json={"status": "archived"})
    assert client.get("/api/dashboard/summary").json()["counts"]["active_cultures"] == 4
    client.post(
        f"/api/library/lines/{first['line']['id']}/status", json={"status": "archived"}
    )
    assert client.get(url).json()["line_id"] == first["line"]["id"]
    assert len(client.get("/api/library/physical?status=all").json()) == 5
    client.post(url + "/status", json={"status": "active"})
    assert client.get(url).json()["id"] == item["id"]


def test_spores_unknown_inline_and_no_line_creation(client):
    s = strain(client)
    for payload in (
        {
            "strain_id": s["id"],
            "material_type": "spore_print",
            "quantity": "3",
            "unit": "print",
        },
        {"material_type": "spore_swab"},
        {
            "inline_strain": {"name": "Inline strain"},
            "material_type": "spore_syringe",
            "quantity": "1.5",
            "unit": "mL",
        },
    ):
        r = client.post("/api/library/spores", json=payload)
        assert r.status_code == 201, r.text
        item = r.json()
        assert (
            client.post(
                f"/api/library/spores/{item['id']}/status", json={"status": "archived"}
            ).status_code
            == 200
        )
        assert client.get(f"/api/library/spores/{item['id']}").status_code == 200
        assert (
            client.post(
                f"/api/library/spores/{item['id']}/status", json={"status": "active"}
            ).status_code
            == 200
        )
    assert client.get("/api/library/lines").json() == []
    assert client.get("/api/library/physical").json() == []
    assert client.get("/api/dashboard/summary").json()["counts"]["active_cultures"] == 0
    assert len(client.get("/api/library/spores?material_type=spore_print").json()) == 1


@pytest.mark.parametrize(
    "material",
    [
        {"count": 0},
        {"count": 101},
        {"count": 1.5},
        {"quantity": "NaN", "unit": "mL"},
        {"quantity": "-1", "unit": "mL"},
        {"quantity": "0.0001", "unit": "mL"},
        {"quantity": "1"},
        {"purchase_price": "1.001"},
    ],
)
def test_bad_quantities_do_not_register(client, material):
    r = client.post(
        "/api/library/receive-culture",
        json={
            "inline_strain": {"name": "Should not persist"},
            "line": {},
            "material": material,
        },
    )
    assert r.status_code == 422, r.text
    assert client.get("/api/library/strains").json() == []
    assert client.get("/api/library/lines").json() == []


def test_invalid_relationship_rolls_back_inline_strain(client):
    first = receive(client, material=None)
    r = client.post(
        "/api/library/receive-culture",
        json={
            "inline_strain": {"name": "Never saved"},
            "existing_line_id": first["line"]["id"],
            "material": {},
        },
    )
    assert r.status_code == 422
    assert client.get("/api/library/strains").json() == []
    assert (
        client.post(
            "/api/library/receive-culture", json={"line": {}, "strain_id": "STR-9999"}
        ).status_code
        == 404
    )


def test_mid_batch_failure_rolls_back_every_record(client, monkeypatch):
    original = library.event
    count = 0

    def fail(session, kind, *args):
        nonlocal count
        if kind == "physical":
            count += 1
            if count == 2:
                raise RuntimeError("simulated failure")
        return original(session, kind, *args)

    monkeypatch.setattr(library, "event", fail)
    with pytest.raises(RuntimeError, match="simulated failure"):
        receive(client, inline_strain={"name": "Atomic strain"})
    for kind in ("strains", "lines", "physical"):
        assert client.get(f"/api/library/{kind}").json() == []
    with Session(client.app.state.engine) as session:
        assert session.scalars(select(IdentitySequence)).all() == []
        assert session.scalars(select(ActivityEvent)).all() == []


def test_concurrent_identifier_allocation(client):
    with ThreadPoolExecutor(max_workers=5) as pool:
        result = list(
            pool.map(
                lambda i: receive(
                    client, material={"count": 3, "material_type": "agar_plate"}
                ),
                range(5),
            )
        )
    ids = [p["id"] for result in result for p in result["physical"]]
    assert len(ids) == len(set(ids)) == 15
    assert len({r["line"]["id"] for r in result}) == 5


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_valid_photo_content_thumbnail_original_and_cover(client, settings, fmt):
    s = strain(client)
    raw = image_bytes(fmt)
    first = upload(client, "strains", s["id"], raw)
    assert first.status_code == 201, first.text
    p = first.json()
    assert p["is_cover"]
    assert client.get(p["url"]).content == raw
    thumb = client.get(p["thumbnail_url"])
    assert thumb.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(thumb.content)) as image:
        assert max(image.size) <= 640
    second = upload(client, "strains", s["id"]).json()
    assert not second["is_cover"]
    assert client.post(f"/api/library/photos/{second['id']}/cover").json()["is_cover"]
    client.post(f"/api/library/strains/{s['id']}/status", json={"status": "archived"})
    assert client.get(p["url"]).status_code == 200
    assert (
        client.get(f"/api/library/strains/{s['id']}").json()["cover"]["id"]
        == second["id"]
    )
    assert client.delete(f"/api/library/photos/{second['id']}").status_code == 204
    assert (
        client.get(f"/api/library/strains/{s['id']}").json()["cover"]["id"] == p["id"]
    )
    assert len(list((settings.data_dir / "photos").iterdir())) == 2
    assert client.delete(f"/api/library/photos/{p['id']}").status_code == 204
    assert client.get(f"/api/library/strains/{s['id']}").json()["cover"] is None
    assert list((settings.data_dir / "photos").iterdir()) == []
    assert client.get(p["url"]).status_code == 404


def test_photos_for_all_records_and_rejected_uploads(client, settings):
    data = receive(client)
    spore = client.post("/api/library/spores", json={}).json()
    for kind, code in [
        ("lines", data["line"]["id"]),
        ("physical", data["physical"][0]["id"]),
        ("spores", spore["id"]),
    ]:
        assert upload(client, kind, code).status_code == 201
    s = strain(client)
    for raw in (
        b"not an image",
        b"<svg></svg>",
        image_bytes("GIF"),
        image_bytes()[:50],
    ):
        assert upload(client, "strains", s["id"], raw).status_code == 422
    assert (
        upload(client, "strains", s["id"], b"x" * (10 * 1024 * 1024 + 1)).status_code
        == 413
    )
    huge = BytesIO()
    Image.new("RGB", (12001, 2)).save(huge, format="PNG")
    assert upload(client, "strains", s["id"], huge.getvalue()).status_code == 422
    assert upload(client, "strains", "STR-9999").status_code == 404
    assert len(list((settings.data_dir / "photos").iterdir())) == 6
    with Session(client.app.state.engine) as session:
        p = session.scalar(select(PhotoAttachment))
        p.filename = "../outside.png"
        session.commit()
        photo_id = p.id
    assert client.get(f"/api/library/photos/{photo_id}/original").status_code == 404


def test_failed_upload_cleanup_and_failed_removal_restores_files(
    client, settings, monkeypatch
):
    s = strain(client)

    def fail(*args):
        raise RuntimeError("simulated event failure")

    with monkeypatch.context() as patch:
        patch.setattr(photos, "event", fail)
        with pytest.raises(RuntimeError):
            upload(client, "strains", s["id"])
    assert list((settings.data_dir / "photos").iterdir()) == []
    p = upload(client, "strains", s["id"]).json()
    with monkeypatch.context() as patch:
        patch.setattr(photos, "event", fail)
        with pytest.raises(RuntimeError):
            client.delete(f"/api/library/photos/{p['id']}")
    assert client.get(p["url"]).status_code == 200
    assert len(client.get(f"/api/library/strains/{s['id']}/photos").json()) == 1
    assert len(list((settings.data_dir / "photos").iterdir())) == 2


def test_upgrade_milestone_one_and_restart_preserves_files(settings):
    settings.database_path.parent.mkdir(parents=True)
    (settings.data_dir / "settings").mkdir()
    marker = settings.data_dir / "settings" / "existing.txt"
    marker.write_text("keep")
    command.upgrade(migration_config(settings), "0001_foundation")
    with TestClient(create_app(settings)) as client:
        s = strain(client)
        p = upload(client, "strains", s["id"]).json()
        receive(client, s["id"], count=1)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["migrations"] == "current"
        assert client.get(p["url"]).status_code == 200
        assert (
            client.get("/api/dashboard/summary").json()["counts"]["active_cultures"]
            == 1
        )
        command.check(migration_config(settings))
    assert marker.read_text() == "keep"
