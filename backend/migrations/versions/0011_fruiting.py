"""Operational spawning, flushes, harvests and one optional tent; no backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0011_fruiting"
down_revision = "0010_containers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fruiting_runs",
        sa.Column(
            "fruiting_id",
            sa.String(32),
            sa.ForeignKey("fruiting_containers.id"),
            primary_key=True,
        ),
        sa.Column(
            "operation_id", sa.String(32), sa.ForeignKey("inventory_operations.id")
        ),
        sa.Column("source_spawn_id", sa.String(32), sa.ForeignKey("spawn.id")),
        sa.Column("recipe_id", sa.String(32), sa.ForeignKey("preparation_recipes.id")),
        sa.Column("recipe_snapshot", sa.Text()),
        sa.Column("environment_snapshot", sa.Text()),
        sa.Column("spawning_date", sa.String(10)),
        sa.Column("spawn_grams", sa.Numeric(14, 3)),
        sa.Column("substrate_grams", sa.Numeric(14, 3)),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("current_flush", sa.Integer(), nullable=False),
        sa.Column("completed_date", sa.String(10)),
        sa.Column("failed_date", sa.String(10)),
        sa.Column("closing_notes", sa.Text()),
        sa.CheckConstraint(
            "stage IN ('unrecorded','colonizing','pinning','fruiting','harvest','completed','failed')"
        ),
        sa.CheckConstraint("current_flush > 0"),
        sa.CheckConstraint("spawn_grams IS NULL OR spawn_grams >= 0"),
        sa.CheckConstraint("substrate_grams IS NULL OR substrate_grams >= 0"),
    )
    op.create_index("ix_fruiting_runs_recipe_id", "fruiting_runs", ["recipe_id"])
    op.create_table(
        "fruiting_flushes",
        sa.Column(
            "fruiting_id",
            sa.String(32),
            sa.ForeignKey("fruiting_runs.fruiting_id"),
            primary_key=True,
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("pinning_date", sa.String(10)),
        sa.Column("fruiting_date", sa.String(10)),
        sa.CheckConstraint("number > 0"),
    )
    op.create_table(
        "harvest_entries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("fruiting_id", sa.String(32), nullable=False),
        sa.Column("flush_number", sa.Integer(), nullable=False),
        sa.Column("harvest_date", sa.String(10), nullable=False),
        sa.Column("wet_grams", sa.Numeric(14, 3)),
        sa.Column("dry_grams", sa.Numeric(14, 3)),
        sa.Column("potency", sa.Integer()),
        sa.Column("potency_notes", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["fruiting_id", "flush_number"],
            ["fruiting_flushes.fruiting_id", "fruiting_flushes.number"],
        ),
        sa.CheckConstraint("wet_grams IS NULL OR wet_grams >= 0"),
        sa.CheckConstraint("dry_grams IS NULL OR dry_grams >= 0"),
        sa.CheckConstraint("potency IS NULL OR potency BETWEEN 1 AND 5"),
        sa.CheckConstraint("revision > 0"),
    )
    op.create_index(
        "ix_harvest_entries_fruiting_id", "harvest_entries", ["fruiting_id"]
    )
    op.create_table(
        "harvest_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "harvest_id",
            sa.String(32),
            sa.ForeignKey("harvest_entries.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "operation_id",
            sa.String(32),
            sa.ForeignKey("inventory_operations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("harvest_id", "revision"),
    )
    op.create_index(
        "ix_harvest_revisions_harvest_id", "harvest_revisions", ["harvest_id"]
    )
    op.create_table(
        "fruiting_environment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1"),
    )
    op.create_table(
        "fruiting_environment_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fruiting_id",
            sa.String(32),
            sa.ForeignKey("fruiting_runs.fruiting_id"),
            nullable=False,
        ),
        sa.Column("change_date", sa.String(10), nullable=False),
        sa.Column("settings", sa.Text()),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.String(40), nullable=False),
    )
    op.create_index(
        "ix_fruiting_environment_changes_fruiting_id",
        "fruiting_environment_changes",
        ["fruiting_id"],
    )
    op.create_table(
        "harvest_photos",
        sa.Column(
            "photo_id",
            sa.String(36),
            sa.ForeignKey("photo_attachments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "harvest_id",
            sa.String(32),
            sa.ForeignKey("harvest_entries.id"),
            nullable=False,
        ),
    )
    op.create_index("ix_harvest_photos_harvest_id", "harvest_photos", ["harvest_id"])
    # Snapshots and permanent harvest ownership must not be rewritten by edits.
    op.execute(
        "CREATE TRIGGER immutable_fruiting_origin BEFORE UPDATE ON fruiting_runs WHEN NEW.operation_id IS NOT OLD.operation_id OR NEW.source_spawn_id IS NOT OLD.source_spawn_id OR NEW.recipe_id IS NOT OLD.recipe_id OR NEW.recipe_snapshot IS NOT OLD.recipe_snapshot OR NEW.environment_snapshot IS NOT OLD.environment_snapshot OR NEW.spawning_date IS NOT OLD.spawning_date OR NEW.spawn_grams IS NOT OLD.spawn_grams OR NEW.substrate_grams IS NOT OLD.substrate_grams BEGIN SELECT RAISE(ABORT, 'Fruiting origin snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_harvest_owner BEFORE UPDATE ON harvest_entries WHEN NEW.fruiting_id != OLD.fruiting_id OR NEW.flush_number != OLD.flush_number OR NEW.created_at != OLD.created_at BEGIN SELECT RAISE(ABORT, 'Harvest ownership is permanent'); END"
    )
    for table in ("harvest_revisions", "fruiting_environment_changes"):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Fruiting history is immutable'); END"
            )
    op.execute(
        "CREATE TRIGGER single_operational_spawn BEFORE INSERT ON fruiting_sources WHEN EXISTS (SELECT 1 FROM fruiting_runs r WHERE r.fruiting_id=NEW.fruiting_id AND r.operation_id IS NOT NULL AND r.source_spawn_id != NEW.spawn_id) BEGIN SELECT RAISE(ABORT, 'An operational fruiting container has one spawn source'); END"
    )
    op.execute(
        "CREATE TRIGGER single_operational_spawn_update BEFORE UPDATE ON fruiting_sources WHEN EXISTS (SELECT 1 FROM fruiting_runs r WHERE r.fruiting_id=OLD.fruiting_id AND r.operation_id IS NOT NULL) BEGIN SELECT RAISE(ABORT, 'Operational spawn provenance is immutable'); END"
    )

    op.execute(
        "CREATE TRIGGER operational_spawn_on_registration BEFORE INSERT ON fruiting_runs WHEN NEW.operation_id IS NOT NULL AND ((SELECT count(*) FROM fruiting_sources WHERE fruiting_id=NEW.fruiting_id) != 1 OR NOT EXISTS (SELECT 1 FROM fruiting_sources WHERE fruiting_id=NEW.fruiting_id AND spawn_id=NEW.source_spawn_id)) BEGIN SELECT RAISE(ABORT, 'An operational grow must retain exactly its selected spawn source'); END"
    )
    op.execute(
        "CREATE TRIGGER single_operational_spawn_delete BEFORE DELETE ON fruiting_sources WHEN EXISTS (SELECT 1 FROM fruiting_runs r WHERE r.fruiting_id=OLD.fruiting_id AND r.operation_id IS NOT NULL) BEGIN SELECT RAISE(ABORT, 'Operational spawn provenance is permanent'); END"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM fruiting_runs) + (SELECT count(*) FROM fruiting_environment)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Fruiting history exists; restore a matching stopped-data backup"
        )
    for name in (
        "single_operational_spawn_delete",
        "operational_spawn_on_registration",
        "single_operational_spawn_update",
        "single_operational_spawn",
        "immutable_harvest_owner",
        "immutable_fruiting_origin",
        "immutable_harvest_revisions_update",
        "immutable_harvest_revisions_delete",
        "immutable_fruiting_environment_changes_update",
        "immutable_fruiting_environment_changes_delete",
    ):
        op.execute(f"DROP TRIGGER {name}")
    for table in (
        "harvest_photos",
        "fruiting_environment_changes",
        "fruiting_environment",
        "harvest_revisions",
        "harvest_entries",
        "fruiting_flushes",
        "fruiting_runs",
    ):
        op.drop_table(table)
