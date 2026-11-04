"""Add experiment foundation without changing production records."""

from alembic import op
import sqlalchemy as sa

revision = "0015_grow_experiments"
down_revision = "0014_environment_monitoring"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("treatment_start", sa.String(length=40), nullable=True),
        sa.Column("timing_precision", sa.String(length=10), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("start_plan_revision", sa.Integer(), nullable=True),
        sa.CheckConstraint("category IN ('substrate','genetics','conditions')"),
        sa.CheckConstraint(
            "classification IN ('prospective','retrospective','uncertain')"
        ),
        sa.CheckConstraint("scope = 'fruiting'"),
        sa.CheckConstraint(
            "state IN ('draft','planned','running','completed','cancelled')"
        ),
        sa.CheckConstraint(
            "timing_precision IS NULL OR timing_precision IN ('instant','date')"
        ),
        sa.CheckConstraint("archived IN (0,1)"),
        sa.CheckConstraint("revision > 0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "experiment_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("operation_id", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["inventory_operations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index(
        "ix_experiment_audit_history",
        "experiment_audits",
        ["experiment_id", "id"],
        unique=False,
    )
    op.create_table(
        "experiment_groups",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "id"),
    )
    op.create_index(
        op.f("ix_experiment_groups_experiment_id"),
        "experiment_groups",
        ["experiment_id"],
        unique=False,
    )
    op.create_table(
        "experiment_plan_revisions",
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("committed_at", sa.String(length=40), nullable=True),
        sa.Column("allocation_committed_at", sa.String(length=40), nullable=True),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.String(length=32), nullable=False),
        sa.CheckConstraint("revision > 0"),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["inventory_operations.id"],
        ),
        sa.PrimaryKeyConstraint("experiment_id", "revision"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_table(
        "experiment_trials",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("group_id", sa.String(length=32), nullable=False),
        sa.Column("tent_id", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.String(length=40), nullable=False),
        sa.Column("ends_at", sa.String(length=40), nullable=True),
        sa.Column("treatment_snapshot", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at"),
        sa.CheckConstraint("revision > 0"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "group_id"],
            ["experiment_groups.experiment_id", "experiment_groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tent_id"],
            ["fruiting_tents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "group_id", "id"),
        sa.UniqueConstraint("experiment_id", "id"),
    )
    op.create_index(
        "ix_experiment_trial_tent_time",
        "experiment_trials",
        ["tent_id", "starts_at", "ends_at"],
        unique=False,
    )
    op.create_table(
        "experiment_units",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
        sa.Column("group_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("fruiting_id", sa.String(length=32), nullable=True),
        sa.Column("batch_id", sa.String(length=32), nullable=True),
        sa.Column("trial_id", sa.String(length=32), nullable=True),
        sa.Column("block", sa.String(length=200), nullable=True),
        sa.Column("allocated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "(kind='container' AND fruiting_id IS NOT NULL AND batch_id IS NULL AND trial_id IS NULL) OR (kind='batch' AND batch_id IS NOT NULL AND fruiting_id IS NULL AND trial_id IS NULL) OR (kind='tent_trial' AND trial_id IS NOT NULL AND fruiting_id IS NULL AND batch_id IS NULL)"
        ),
        sa.CheckConstraint("kind IN ('container','batch','tent_trial')"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["grow_batches.id"],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id", "group_id", "trial_id"],
            [
                "experiment_trials.experiment_id",
                "experiment_trials.group_id",
                "experiment_trials.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id", "group_id"],
            ["experiment_groups.experiment_id", "experiment_groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id", "plan_revision"],
            [
                "experiment_plan_revisions.experiment_id",
                "experiment_plan_revisions.revision",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["fruiting_id"],
            ["fruiting_containers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "batch_id"),
        sa.UniqueConstraint("experiment_id", "fruiting_id"),
        sa.UniqueConstraint("experiment_id", "id"),
        sa.UniqueConstraint("experiment_id", "trial_id"),
    )
    op.create_table(
        "experiment_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("unit_id", sa.String(length=32), nullable=False),
        sa.Column("fruiting_id", sa.String(length=32), nullable=False),
        sa.Column("exposure_start", sa.String(length=40), nullable=False),
        sa.Column("exposure_end", sa.String(length=40), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "classification IN ('prospective','retrospective','uncertain')"
        ),
        sa.CheckConstraint("exposure_end IS NULL OR exposure_end > exposure_start"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "unit_id"],
            ["experiment_units.experiment_id", "experiment_units.id"],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["fruiting_id"],
            ["fruiting_containers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_id", "unit_id", "fruiting_id", "exposure_start"
        ),
    )
    op.create_index(
        "ix_experiment_membership_fruiting",
        "experiment_memberships",
        ["fruiting_id"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_plan_revisions_update BEFORE UPDATE ON experiment_plan_revisions BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_plan_revisions_delete BEFORE DELETE ON experiment_plan_revisions BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_audits_update BEFORE UPDATE ON experiment_audits BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_audits_delete BEFORE DELETE ON experiment_audits BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_groups_update BEFORE UPDATE ON experiment_groups BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_experiment_groups_delete BEFORE DELETE ON experiment_groups BEGIN SELECT RAISE(ABORT,'Experiment history is immutable'); END"
    )


def downgrade():
    connection = op.get_bind()
    for table in [
        "experiment_memberships",
        "experiment_units",
        "experiment_trials",
        "experiment_audits",
        "experiment_groups",
        "experiment_plan_revisions",
        "experiments",
    ]:
        if connection.exec_driver_sql("SELECT 1 FROM " + table + " LIMIT 1").first():
            raise RuntimeError(
                "Refusing to discard experiment history; restore a matching backup"
            )
    for table in [
        "experiment_plan_revisions",
        "experiment_audits",
        "experiment_groups",
    ]:
        for action in ["update", "delete"]:
            op.execute("DROP TRIGGER immutable_" + table + "_" + action)
    for table in [
        "experiment_memberships",
        "experiment_units",
        "experiment_trials",
        "experiment_audits",
        "experiment_groups",
        "experiment_plan_revisions",
        "experiments",
    ]:
        op.drop_table(table)
