import pytest
from alembic import command
from app.config import Settings
from app.database import migration_config
from app.main import create_app
from app.schemas import DashboardSummary, Health
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", frontend_dir=tmp_path / "frontend")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def test_health_and_database(client, settings):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert Health.model_validate(response.json()).migrations == "current"
    assert settings.database_path.exists()
    assert all(
        (settings.data_dir / name).is_dir() for name in ("photos", "files", "settings")
    )
    assert set(inspect(client.app.state.engine).get_table_names()) == {
        "alembic_version",
        "identity_sequences",
        "strains",
        "culture_lines",
        "spore_sources",
        "physical_cultures",
        "photo_attachments",
        "activity_events",
        "spawn",
        "grow_batches",
        "batch_sources",
        "fruiting_containers",
        "fruiting_sources",
        "spore_collections",
        "line_origins",
        "line_parents",
        "stock_items",
        "inventory_operations",
        "stock_transactions",
        "preparation_recipes",
        "lc_media_default",
        "fruiting_runs",
        "fruiting_flushes",
        "harvest_entries",
        "harvest_revisions",
        "fruiting_environment",
        "fruiting_environment_changes",
        "harvest_photos",
        "pinning_photos",
        "journal_photos",
        "experiments",
        "experiment_groups",
        "experiment_plan_revisions",
        "experiment_units",
        "experiment_memberships",
        "experiment_trials",
        "experiment_audits",
        "environmental_profiles",
        "fruiting_tents",
        "environment_profile_assignments",
        "environmental_readings",
        "tent_occupancies",
        "environment_audits",
        "environment_warnings",
        "environment_warning_events",
        "container_labels",
        "label_assignments",
        "cultivation_states",
        "preparation_batches",
        "prepared_materials",
        "container_reservations",
        "material_lifecycles",
        "material_transfers",
    }


def test_dashboard_empty_contract(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    summary = DashboardSummary.model_validate(response.json())
    assert summary.counts.model_dump() == dict(
        active_cultures=0, spawn_containers=0, fruiting_units=0, open_alerts=0
    )
    assert all(
        response.json()[key] == []
        for key in (
            "attention_items",
            "active_cultivation",
            "recent_activity",
            "environmental_observations",
        )
    )


def test_safe_metadata_and_unknown_api(client):
    assert client.get("/api/app/info").json() == dict(
        name="Cultivatinator",
        version="0.1.0",
        environment="development",
        storage="SQLite · persistent local storage",
    )
    assert client.get("/api/missing").status_code == 404
    assert "/api/dashboard/summary" in client.get("/openapi.json").json()["paths"]


def test_migrations_repeat_and_persist(settings):
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/health").status_code == 200
    command.downgrade(migration_config(settings), "base")
    command.upgrade(migration_config(settings), "head")
    with TestClient(create_app(settings)) as client:
        with client.app.state.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                == "0015_grow_experiments"
            )


def test_unhealthy_database_is_sanitized(client):
    with client.app.state.engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["migrations"] == "outdated"


def test_spa_fallback(settings):
    settings.frontend_dir.mkdir()
    (settings.frontend_dir / "index.html").write_text("<html>application</html>")
    with TestClient(create_app(settings)) as client:
        assert client.get("/laboratory").text == "<html>application</html>"
        assert client.get("/api/missing").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404


def test_database_failure_is_unavailable_and_sanitized(client, monkeypatch):
    def fail_connect():
        raise RuntimeError("private database path must not be exposed")

    monkeypatch.setattr(client.app.state.engine, "connect", fail_connect)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "unavailable",
        "migrations": "unavailable",
    }
    assert "private" not in response.text
