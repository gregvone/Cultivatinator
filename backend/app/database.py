from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings):
    engine = create_engine(
        "sqlite:///" + str(settings.database_path),
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")

    return engine


def migration_config(settings: Settings) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["configured_url"] = True
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option(
        "sqlalchemy.url",
        ("sqlite:///" + str(settings.database_path)).replace("%", "%%"),
    )
    return config


def initialize(settings: Settings, engine) -> None:
    for directory in ("database", "photos", "files", "settings"):
        (settings.data_dir / directory).mkdir(parents=True, exist_ok=True)
    # One application process runs migrations before serving any requests.
    command.upgrade(migration_config(settings), "head")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")


def get_session(request: Request):
    # Future write operations should use `with session.begin()` for atomicity.
    factory = sessionmaker(bind=request.app.state.engine)
    with factory() as session:
        yield session
