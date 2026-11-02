from alembic import context
from app.config import Settings
from app.database import Base
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = Base.metadata
if not config.attributes.get("configured_url"):
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.set_main_option(
        "sqlalchemy.url",
        ("sqlite:///" + str(settings.database_path)).replace("%", "%%"),
    )

if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
