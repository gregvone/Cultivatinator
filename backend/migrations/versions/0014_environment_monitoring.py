"""Add manual environmental monitoring; no cultivation data is changed."""

from alembic import op
import sqlalchemy as sa

revision = "0014_environment_monitoring"
down_revision = "0013_journal_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "environmental_profiles",
        sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("species", sa.String(length=200), nullable=True),
        sa.Column("targets", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('active','archived')"),
        sa.CheckConstraint("revision > 0"),
    )
    op.create_table(
        "fruiting_tents",
        sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("environmental_profiles.id"),
            nullable=True,
        ),
        sa.CheckConstraint("revision > 0"),
        sa.CheckConstraint("status IN ('active','archived')"),
    )
    op.create_table(
        "environment_profile_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tent_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_tents.id"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("environmental_profiles.id"),
            nullable=True,
        ),
        sa.Column("assigned_at", sa.String(length=40), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_env_assignment_time",
        "environment_profile_assignments",
        ["tent_id", "assigned_at", "id"],
    )
    op.create_table(
        "environmental_readings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tent_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_tents.id"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("temperature_f", sa.Float(), nullable=False),
        sa.Column("humidity", sa.Float(), nullable=False),
        sa.Column("co2", sa.Float(), nullable=True),
        sa.Column("humidifier", sa.Integer(), nullable=True),
        sa.Column("fan", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("environmental_profiles.id"),
            nullable=True,
        ),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("evaluations", sa.Text(), nullable=False),
        sa.Column(
            "replaces_id",
            sa.Integer(),
            sa.ForeignKey("environmental_readings.id"),
            nullable=True,
        ),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("humidity BETWEEN 0 AND 100"),
        sa.CheckConstraint("temperature_f BETWEEN -148 AND 212"),
        sa.CheckConstraint("co2 IS NULL OR co2 BETWEEN 0 AND 1000000"),
        sa.CheckConstraint("humidifier IS NULL OR humidifier BETWEEN 0 AND 10"),
        sa.CheckConstraint("fan IS NULL OR fan BETWEEN 0 AND 10"),
        sa.UniqueConstraint("replaces_id"),
    )
    op.create_index(
        "ix_env_reading_time",
        "environmental_readings",
        ["tent_id", "observed_at", "id"],
    )
    op.create_table(
        "tent_occupancies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tent_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_tents.id"),
            nullable=False,
        ),
        sa.Column(
            "fruiting_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_containers.id"),
            nullable=False,
        ),
        sa.Column("entered_at", sa.String(length=40), nullable=False),
        sa.Column("left_at", sa.String(length=40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("left_at IS NULL OR left_at > entered_at"),
        sa.CheckConstraint("revision > 0"),
    )
    op.create_index(
        "ix_env_occupancy_container",
        "tent_occupancies",
        ["fruiting_id", "entered_at", "left_at"],
    )
    op.create_index(
        "ix_env_occupancy_tent",
        "tent_occupancies",
        ["tent_id", "entered_at", "left_at"],
    )
    op.create_table(
        "environment_audits",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=32), nullable=False),
        sa.Column(
            "operation_id",
            sa.String(length=32),
            sa.ForeignKey("inventory_operations.id"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_env_audit_owner", "environment_audits", ["entity_type", "entity_id", "id"]
    )
    op.create_table(
        "environment_warnings",
        sa.Column(
            "tent_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_tents.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("metric", sa.String(length=30), primary_key=True, nullable=False),
        sa.Column(
            "reading_id",
            sa.Integer(),
            sa.ForeignKey("environmental_readings.id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.CheckConstraint("metric IN ('temperature_f','humidity','co2')"),
    )
    op.create_table(
        "environment_warning_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tent_id",
            sa.String(length=32),
            sa.ForeignKey("fruiting_tents.id"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(length=30), nullable=False),
        sa.Column(
            "operation_id",
            sa.String(length=32),
            sa.ForeignKey("inventory_operations.id"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_env_warning_history", "environment_warning_events", ["tent_id", "id"]
    )
    op.execute(
        "CREATE TRIGGER env_occupancy_overlap_insert BEFORE INSERT ON tent_occupancies WHEN EXISTS (SELECT 1 FROM tent_occupancies o WHERE o.fruiting_id=NEW.fruiting_id AND o.id != COALESCE(NEW.id,-1) AND (o.left_at IS NULL OR NEW.entered_at < o.left_at) AND (NEW.left_at IS NULL OR o.entered_at < NEW.left_at)) BEGIN SELECT RAISE(ABORT,'Overlapping tent occupancy'); END"
    )
    op.execute(
        "CREATE TRIGGER env_occupancy_overlap_update BEFORE UPDATE ON tent_occupancies WHEN EXISTS (SELECT 1 FROM tent_occupancies o WHERE o.fruiting_id=NEW.fruiting_id AND o.id != COALESCE(NEW.id,-1) AND (o.left_at IS NULL OR NEW.entered_at < o.left_at) AND (NEW.left_at IS NULL OR o.entered_at < NEW.left_at)) BEGIN SELECT RAISE(ABORT,'Overlapping tent occupancy'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environmental_readings_update BEFORE UPDATE ON environmental_readings BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environmental_readings_delete BEFORE DELETE ON environmental_readings BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_profile_assignments_update BEFORE UPDATE ON environment_profile_assignments BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_profile_assignments_delete BEFORE DELETE ON environment_profile_assignments BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_audits_update BEFORE UPDATE ON environment_audits BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_audits_delete BEFORE DELETE ON environment_audits BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_warning_events_update BEFORE UPDATE ON environment_warning_events BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_environment_warning_events_delete BEFORE DELETE ON environment_warning_events BEGIN SELECT RAISE(ABORT,'Monitoring history is append-only'); END"
    )


def downgrade():
    tables = [
        "environmental_profiles",
        "fruiting_tents",
        "environment_profile_assignments",
        "environmental_readings",
        "tent_occupancies",
        "environment_audits",
        "environment_warnings",
        "environment_warning_events",
    ]
    for table in tables:
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar():
            raise RuntimeError(
                "Environmental history exists; restore a matching stopped-data backup"
            )
    for table in reversed(tables):
        op.drop_table(table)
