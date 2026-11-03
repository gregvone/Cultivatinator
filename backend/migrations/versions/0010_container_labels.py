"""Reusable physical labels and explicit cultivation phases; no historical backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0010_containers"
down_revision = "0009_lc_default"
branch_labels = None
depends_on = None
OWNER_CHECK = "(physical_id IS NOT NULL) + (spawn_id IS NOT NULL) + (fruiting_id IS NOT NULL) + (prepared_id IS NOT NULL) = 1"


def owners():
    return [
        sa.Column(column, sa.String(32), sa.ForeignKey(target))
        for column, target in (
            ("physical_id", "physical_cultures.id"),
            ("spawn_id", "spawn.id"),
            ("fruiting_id", "fruiting_containers.id"),
            ("prepared_id", "prepared_materials.id"),
        )
    ]


def upgrade():
    op.create_table(
        "container_labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("container_type", sa.String(30), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("reusable", sa.Integer(), nullable=False),
        sa.UniqueConstraint("container_type", "number"),
        sa.CheckConstraint("number > 0"),
        sa.CheckConstraint("reusable IN (0,1)"),
    )
    op.create_table(
        "label_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "label_id",
            sa.Integer(),
            sa.ForeignKey("container_labels.id"),
            nullable=False,
        ),
        *owners(),
        sa.Column("assigned_at", sa.String(40), nullable=False),
        sa.Column("released_at", sa.String(40)),
        sa.Column("release_date", sa.String(10)),
        sa.Column("release_reason", sa.String(500)),
        sa.CheckConstraint(OWNER_CHECK),
    )
    op.create_index("ix_label_assignments_label_id", "label_assignments", ["label_id"])
    op.create_index(
        "uq_occupied_container_label",
        "label_assignments",
        ["label_id"],
        unique=True,
        sqlite_where=sa.text("released_at IS NULL"),
    )
    for key in ("physical_id", "spawn_id", "fruiting_id", "prepared_id"):
        op.create_index(
            f"uq_active_label_{key}",
            "label_assignments",
            [key],
            unique=True,
            sqlite_where=sa.text(f"released_at IS NULL AND {key} IS NOT NULL"),
        )
    op.create_table(
        "cultivation_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        *owners(),
        sa.Column("phase", sa.String(20), nullable=False),
        *[
            sa.Column(field, sa.String(10))
            for field in (
                "inoculation_date",
                "ready_date",
                "used_date",
                "completed_date",
                "failed_date",
            )
        ],
        sa.CheckConstraint(OWNER_CHECK),
        sa.CheckConstraint(
            "phase IN ('colonizing','ready','used','completed','failed')"
        ),
        *[
            sa.UniqueConstraint(key)
            for key in ("physical_id", "spawn_id", "fruiting_id", "prepared_id")
        ],
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER immutable_container_labels_{action.lower()} BEFORE {action} ON container_labels BEGIN SELECT RAISE(ABORT, 'Physical label definitions are permanent'); END"
        )
    op.execute(
        "CREATE TRIGGER immutable_label_assignment_delete BEFORE DELETE ON label_assignments BEGIN SELECT RAISE(ABORT, 'Physical label history is permanent'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_label_assignment_identity BEFORE UPDATE ON label_assignments WHEN NEW.label_id != OLD.label_id OR NEW.assigned_at != OLD.assigned_at OR OLD.released_at IS NOT NULL OR COALESCE(NEW.physical_id,NEW.spawn_id,NEW.fruiting_id,NEW.prepared_id) != COALESCE(OLD.physical_id,OLD.spawn_id,OLD.fruiting_id,OLD.prepared_id) BEGIN SELECT RAISE(ABORT, 'Physical assignment history cannot be rewritten'); END"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM container_labels) + (SELECT count(*) FROM cultivation_states)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Physical label or lifecycle history exists; restore a matching stopped-data backup"
        )
    op.execute("DROP TRIGGER immutable_label_assignment_identity")
    op.execute("DROP TRIGGER immutable_label_assignment_delete")
    for action in ("update", "delete"):
        op.execute(f"DROP TRIGGER immutable_container_labels_{action}")
    op.drop_table("cultivation_states")
    op.drop_table("label_assignments")
    op.drop_table("container_labels")
