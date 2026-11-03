from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from io import BytesIO
import hashlib
import json
import shutil
import sqlite3
import stat
import zipfile
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.backup_format import (
    BackupError,
    Limits,
    check_archive,
    create_backup,
    staging_base,
    revision,
    inspect_database,
)
from test_foundation import client, settings  # noqa: F401
from test_fruiting import spawn, stage, harvest, detail
from test_library import image_bytes, upload
from test_pinning_photos import attach as pin_photo
from test_provenance import establish


def archive_bytes(client):
    r = client.get("/api/backups/download")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return r.content


def save(tmp_path, data):
    path = tmp_path / "backup.zip"
    path.write_bytes(data)
    return path


def rebuilt(data, edit=None, add=None, remove=None):
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(
        output, "w"
    ) as target:
        for item in source.infolist():
            if item.filename == remove:
                continue
            content = source.read(item)
            if edit:
                content = edit(item.filename, content)
            target.writestr(item, content)
        if add:
            target.writestr(*add)
    return output.getvalue()


def mutate_manifest(data, update):
    def edit(name, content):
        if name == "manifest.json":
            doc = json.loads(content)
            update(doc)
            return json.dumps(doc).encode()
        return content

    return rebuilt(data, edit=edit)


def test_empty_backup_inventory_checksums_excludes_checkout_wal_and_cleanup(
    client, settings, tmp_path
):
    root = settings.data_dir
    (root / ".git").mkdir()
    (root / ".git/HEAD").write_text("source")
    for name in ["compose.yaml", ".env", "README.md"]:
        (root / name).write_text("DO NOT TOUCH")
    data = archive_bytes(client)
    manifest = check_archive(save(tmp_path, data), extract=False)
    assert manifest["migration_revision"] == revision()
    assert manifest["format_version"] == 1
    assert set(manifest["directories"]) == {"database", "photos", "files", "settings"}
    with zipfile.ZipFile(BytesIO(data)) as z:
        assert set(z.namelist()) == {
            "database/",
            "photos/",
            "files/",
            "settings/",
            "database/cultivatinator.sqlite3",
            "manifest.json",
        }
        for name, entry in manifest["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry["sha256"]
    assert list(staging_base(root).iterdir()) == []
    assert (
        client.get("/api/backups/download", params={"path": "/etc/passwd"}).status_code
        == 400
    )


def test_complete_dataset_roundtrip_lineage_flushes_events_photos_files_settings(
    client, settings, tmp_path
):
    row = spawn(client, count=2)[0]
    code = row["id"]
    stage(client, code, "pinning", "2026-01-03")
    p1 = pin_photo(client, code, 1)
    stage(client, code, "fruiting", "2026-01-05")
    fruit = client.post(
        f"/api/fruiting/records/{code}/flushes/1/fruiting/photos",
        files={"file": ("fruit.png", image_bytes(), "image/png")},
    ).json()
    h1 = harvest(client, code, wet_grams="100")
    hp = client.post(
        f"/api/fruiting/harvests/{h1['id']}/photos",
        files={"file": ("harvest.png", image_bytes(), "image/png")},
    ).json()
    stage(client, code, "next_flush", "2026-01-10")
    p2 = pin_photo(client, code, 2)
    stage(client, code, "fruiting", "2026-01-12")
    harvest(client, code, harvest_date="2026-01-15", wet_grams="50")
    stage(client, code, "complete", "2026-01-20")
    complete = client.post(
        f"/api/fruiting/records/{code}/completion/photos",
        files={"file": ("complete.png", image_bytes(), "image/png")},
    ).json()
    clone = establish(client, {"kind": "fruiting", "id": code}, name="Retained clone")
    before = detail(client, code)
    ancestry = client.get(f"/api/provenance/lines/{clone['line']['id']}").json()
    (settings.data_dir / "files/nested").mkdir()
    (settings.data_dir / "files/nested/note.txt").write_text("persistent files")
    (settings.data_dir / "settings/custom.json").write_text('{"retained":true}')
    verified = check_archive(save(tmp_path, archive_bytes(client)))
    try:
        assert (
            verified.root / "files/nested/note.txt"
        ).read_text() == "persistent files"
        assert (
            verified.root / "settings/custom.json"
        ).read_text() == '{"retained":true}'
        with TestClient(
            create_app(
                Settings(data_dir=verified.root, frontend_dir=settings.frontend_dir)
            )
        ) as restored:
            assert restored.get("/api/health").status_code == 200
            assert detail(restored, code) == before
            assert (
                restored.get(f"/api/provenance/lines/{clone['line']['id']}").json()
                == ancestry
            )
            for photo in [p1, p2, fruit, hp, complete]:
                assert restored.get(photo["url"]).content == image_bytes()
                assert restored.get(photo["thumbnail_url"]).content.startswith(b"RIFF")
    finally:
        verified.cleanup()


def test_wal_commits_are_captured_and_uncommitted_writer_waits(
    client, settings, tmp_path
):
    connection = sqlite3.connect(settings.database_path, check_same_thread=False)
    try:
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO strains (id,name,normalized_name,status,created_at) VALUES ('STR-WAL','WAL strain','wal strain','active','2026-01-01')"
        )
        with ThreadPoolExecutor() as pool:
            future = pool.submit(archive_bytes, client)
            assert not future.done()
            connection.commit()
            verified = check_archive(save(tmp_path, future.result(timeout=30)))
        try:
            with sqlite3.connect(
                verified.root / "database/cultivatinator.sqlite3"
            ) as conn:
                assert conn.execute(
                    "SELECT name FROM strains WHERE id='STR-WAL'"
                ).fetchone() == ("WAL strain",)
        finally:
            verified.cleanup()
    finally:
        connection.close()


def test_backup_waits_for_upload_and_removal_rollback_file_recovery(
    client, settings, tmp_path, monkeypatch
):
    import app.photos as photos

    row = spawn(client)[0]
    entered, release = Event(), Event()
    original = photos.event

    def pause(*args, **kwargs):
        if args[3] == "photo_attached":
            entered.set()
            assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(photos, "event", pause)
    with ThreadPoolExecutor() as pool:
        sending = pool.submit(upload, client, "fruiting", row["id"])
        assert entered.wait(10)
        backup = pool.submit(archive_bytes, client)
        assert not backup.done()
        release.set()
        photo = sending.result(timeout=10).json()
        data = backup.result(timeout=30)
    check_archive(save(tmp_path, data), extract=False)

    def fail(*args, **kwargs):
        if args[3] == "photo_removed":
            raise HTTPException(503, "Simulated rollback")
        return original(*args, **kwargs)

    monkeypatch.setattr(photos, "event", fail)
    restoring, recover_files = Event(), Event()
    rename = Path.rename

    def pause_restore(path, target):
        if path.name.endswith(".removed"):
            restoring.set()
            assert recover_files.wait(10)
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", pause_restore)
    with ThreadPoolExecutor() as pool:
        deletion = pool.submit(client.delete, f"/api/library/photos/{photo['id']}")
        assert restoring.wait(10)
        backup = pool.submit(archive_bytes, client)
        assert not backup.done()
        recover_files.set()
        assert deletion.result(timeout=10).status_code == 503
        data = backup.result(timeout=30)
    verified = check_archive(save(tmp_path, data))
    try:
        originals = list((verified.root / "photos").glob("*.png"))
        thumbnails = list((verified.root / "photos").glob("*.webp"))
        assert len(originals) == len(thumbnails) == 1
        assert originals[0].read_bytes() == image_bytes()
        assert thumbnails[0].read_bytes().startswith(b"RIFF")
    finally:
        verified.cleanup()
    assert client.get(photo["url"]).content == image_bytes()


def test_prepared_download_one_use_expiry_cancel_and_cleanup(client, settings):
    import time

    r = client.post("/api/backups/prepare")
    assert r.status_code == 201, r.text
    target = r.json()["download_url"]
    assert client.get(target).status_code == 200
    assert client.get(target).status_code == 404
    r = client.post("/api/backups/prepare")
    token = r.json()["download_url"].rsplit("/", 1)[1]
    _, artifact = client.app.state.backups[token]
    client.app.state.backups[token] = (time.monotonic() - 1, artifact)
    assert client.get(r.json()["download_url"]).status_code == 410
    r = client.post("/api/backups/prepare")
    assert client.delete(r.json()["download_url"]).status_code == 204
    assert not client.app.state.backups
    assert list(staging_base(settings.data_dir).iterdir()) == []


def test_cancelled_capture_disk_error_and_missing_photo_are_clear_and_clean(
    client, settings, monkeypatch
):
    with pytest.raises(BackupError, match="cancelled"):
        create_backup(settings.data_dir, lambda: True)
    assert list(staging_base(settings.data_dir).iterdir()) == []
    import app.backup_format as fmt

    saved = fmt.ensure_space
    monkeypatch.setattr(
        fmt,
        "ensure_space",
        lambda *args: (_ for _ in ()).throw(BackupError("Insufficient disk space")),
    )
    r = client.post("/api/backups/prepare")
    assert r.status_code == 503 and "Insufficient disk" in r.text
    monkeypatch.setattr(fmt, "ensure_space", saved)
    row = spawn(client)[0]
    photo = upload(client, "fruiting", row["id"]).json()
    with sqlite3.connect(settings.database_path) as db:
        name = db.execute(
            "SELECT filename FROM photo_attachments WHERE id=?", (photo["id"],)
        ).fetchone()[0]
    (settings.data_dir / "photos" / name).unlink()
    r = client.get("/api/backups/download")
    assert r.status_code == 503 and "missing photograph" in r.text
    assert list(staging_base(settings.data_dir).iterdir()) == []


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "photos/../../outside",
        "photos\\outside",
        "files//bad",
        "files/./bad",
        "C:/bad",
        ".git/HEAD",
    ],
)
def test_zip_paths_are_rejected_before_live_extraction(client, tmp_path, name):
    data = rebuilt(archive_bytes(client), add=(name, b"bad"))
    with pytest.raises(BackupError):
        check_archive(save(tmp_path, data))


def test_symlinks_duplicates_conflicting_entries_and_decompression_limits(
    client, tmp_path
):
    data = archive_bytes(client)
    item = zipfile.ZipInfo("photos/link")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(BackupError, match="Symlink"):
        check_archive(save(tmp_path, rebuilt(data, add=(item, b"/etc/passwd"))))
    with pytest.warns(UserWarning):
        duplicate = rebuilt(data, add=("manifest.json", b"{}"))
    with pytest.raises(BackupError, match="Duplicate"):
        check_archive(save(tmp_path, duplicate))
    for limits in [
        Limits(total_bytes=1),
        Limits(file_bytes=1),
        Limits(entries=1),
        Limits(archive_bytes=1),
    ]:
        with pytest.raises(BackupError):
            check_archive(save(tmp_path, data), limits=limits)
    item = zipfile.ZipInfo("files/bomb")
    item.compress_type = zipfile.ZIP_DEFLATED
    with pytest.raises(BackupError, match="decompression"):
        check_archive(save(tmp_path, rebuilt(data, add=(item, b"0" * 2000000))))


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m.update(format_version=99),
        lambda m: m.update(format_version=True),
        lambda m: m.update(application_version="future"),
        lambda m: m.update(migration_revision="future"),
        lambda m: m.update(compatibility={}),
        lambda m: m.update(files=[]),
        lambda m: m.update(created_at="2026-01-01"),
        lambda m: m["files"]["database/cultivatinator.sqlite3"].update(sha256="0" * 64),
    ],
)
def test_manifest_versions_and_checksums_rejected(client, tmp_path, change):
    with pytest.raises(BackupError):
        check_archive(save(tmp_path, mutate_manifest(archive_bytes(client), change)))


def test_corrupt_truncated_missing_members_and_database_fk_schema_checks(
    client, tmp_path
):
    data = archive_bytes(client)
    for invalid in [
        b"not zip",
        data[:-30],
        rebuilt(data, remove="database/cultivatinator.sqlite3"),
    ]:
        with pytest.raises(BackupError):
            check_archive(save(tmp_path, invalid))
    stage = check_archive(save(tmp_path, data))
    try:
        path = stage.root / "database/cultivatinator.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute(
                "INSERT INTO culture_lines(id,strain_id,origin,status,created_at) VALUES ('CL-BAD','STR-MISSING','other','active','2026-01-01')"
            )
        with pytest.raises(BackupError, match="foreign-key"):
            inspect_database(path)
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM culture_lines WHERE id='CL-BAD'")
            db.execute("CREATE TABLE unexpected (id INTEGER)")
        with pytest.raises(BackupError, match="schema"):
            inspect_database(path)
    finally:
        stage.cleanup()


def test_runtime_lease_and_stale_staging_recovery(settings):
    with TestClient(create_app(settings)) as first:
        with pytest.raises(BackupError, match="in use"):
            with TestClient(create_app(settings)):
                pass
        assert first.get("/api/health").status_code == 200
    stale = staging_base(settings.data_dir) / "cultivatinator-backup-interrupted"
    stale.mkdir()
    (stale / "partial.zip").write_bytes(b"partial")
    with TestClient(create_app(settings)) as second:
        assert not stale.exists()


def test_disconnected_response_always_removes_download_artifact(tmp_path):
    import anyio
    import tempfile
    from app.backup_format import Artifact
    from app.backups import Download

    temporary = tempfile.TemporaryDirectory(dir=tmp_path)
    path = Path(temporary.name) / "file.zip"
    path.write_bytes(b"test")

    async def exercise():
        async def send(message):
            raise OSError("client disconnected")

        async def receive():
            return {"type": "http.disconnect"}

        with pytest.raises(Exception):
            await Download(Artifact(temporary, path, "backup.zip"))(
                {
                    "type": "http",
                    "method": "GET",
                    "headers": [],
                    "asgi": {"spec_version": "2.4"},
                },
                receive,
                send,
            )

    anyio.run(exercise)
    assert not path.exists()
