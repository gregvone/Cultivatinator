from io import BytesIO
import json
from PIL import Image
from sqlalchemy import event
from test_foundation import client, settings  # noqa: F401
from test_provenance import acquisition, establish, grow


def graph(client):
    r = client.get("/api/genetics")
    assert r.status_code == 200, r.text
    return r.json()


def photo(client, kind, code):
    f = BytesIO()
    Image.new("RGB", (30, 30), "green").save(f, "PNG")
    r = client.post(
        f"/api/library/{kind}/{code}/photos",
        files={"file": ("culture.png", f.getvalue(), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_roots_unknown_archived_and_only_recorded_parents(client):
    a = acquisition(client, inline_strain={"name": "Oyster"})
    root = a["line"]
    second = acquisition(client, strain_id=root["strain_id"])["line"]
    child = establish(client, root, name="Selected isolate")["line"]
    unknown = acquisition(client)["line"]
    assert (
        client.post(
            f"/api/library/lines/{root['id']}/status", json={"status": "archived"}
        ).status_code
        == 200
    )
    data = graph(client)
    assert (
        next(n for n in data["nodes"] if n["id"] == root["id"])["status"] == "archived"
    )
    assert not next(n for n in data["nodes"] if n["id"] == root["id"])["can_isolate"]
    assert len(data["nodes"]) == 4
    assert data["edges"] == [
        {"line_id": child["id"], "parent_id": root["id"], "confidence": "confirmed"}
    ]
    assert (
        next(n for n in data["nodes"] if n["id"] == unknown["id"])["strain_id"] is None
    )
    assert second["id"] not in {e["line_id"] for e in data["edges"]}
    grow(client, [a["records"][0]["id"]])
    assert graph(client)["edges"] == data["edges"]


def test_possible_clone_sources_and_no_invented_source(client):
    a, b = acquisition(client), acquisition(client)
    g = grow(client, [a["records"][0]["id"], b["records"][0]["id"]])
    fruit = g["containers"][0]
    clone = establish(client, fruit)["line"]
    data = graph(client)
    assert {e["confidence"] for e in data["edges"]} == {"possible"}
    assert len(data["edges"]) == 2
    for n in data["nodes"][:2]:
        assert n["fruiting_sources"][0]["id"] == fruit["id"]
    c = next(n for n in data["nodes"] if n["id"] == clone["id"])
    assert c["source"] == {"kind": "fruiting", "id": fruit["id"]}
    assert c["fruiting_sources"] == []


def test_photo_priority_ownership_restart_and_missing_fallback(client, settings):
    a = acquisition(client, inline_strain={"name": "Oyster"})
    line = a["line"]["id"]
    cover = photo(client, "strains", a["line"]["strain_id"])
    own = photo(client, "spawn", a["records"][0]["id"])
    assert graph(client)["nodes"][0]["photo_source"] == "strain cover"
    path = f"/api/genetics/lines/{line}/photo"
    assert client.put(path, json={"photo_id": cover["id"]}).status_code == 422
    assert client.put(path, json={"photo_id": own["id"]}).status_code == 200
    assert graph(client)["nodes"][0]["photo_source"] == "representative"
    assert (
        json.loads((settings.data_dir / "settings/genetics.json").read_text())[
            "photos"
        ][line]
        == own["id"]
    )
    from app.genetics import choices

    assert choices(settings).photos[line] == own["id"]
    from app.backup_format import create_backup, check_archive
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    artifact = create_backup(settings.data_dir)
    verified = check_archive(artifact.path)
    try:
        with TestClient(
            create_app(
                Settings(data_dir=verified.root, frontend_dir=settings.frontend_dir)
            )
        ) as restored:
            assert graph(restored)["nodes"][0]["photo"]["id"] == own["id"]
    finally:
        verified.cleanup()
        artifact.cleanup()
    line_photo = photo(client, "lines", line)
    assert graph(client)["nodes"][0]["photo"]["id"] == line_photo["id"]
    client.delete(f"/api/library/photos/{line_photo['id']}")
    assert graph(client)["nodes"][0]["photo"]["id"] == own["id"]
    client.delete(f"/api/library/photos/{own['id']}")
    assert graph(client)["nodes"][0]["photo"]["id"] == cover["id"]


def test_query_count_and_corrupt_settings(client, settings):
    for _ in range(8):
        acquisition(client)
    queries = []

    def count(*args):
        queries.append(1)

    event.listen(client.app.state.engine, "before_cursor_execute", count)
    try:
        assert len(graph(client)["nodes"]) == 8
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", count)
    assert len(queries) <= 11
    (settings.data_dir / "settings/genetics.json").write_text("broken")
    assert client.get("/api/genetics").status_code == 503
