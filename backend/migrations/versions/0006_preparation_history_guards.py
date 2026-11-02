"""Protect committed operation history, batch snapshots and transfer sources."""

from alembic import op
import sqlalchemy as sa

revision = "0006_history"
down_revision = "0005_preparation"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("preparation_batches", "material_transfers"):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Preparation history is immutable'); END"
            )
    # An operation response is finalized once inside its creating transaction.
    op.execute(
        "CREATE TRIGGER immutable_operation_update BEFORE UPDATE ON inventory_operations WHEN OLD.result != '{}' BEGIN SELECT RAISE(ABORT, 'Committed operation history is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_operation_delete BEFORE DELETE ON inventory_operations BEGIN SELECT RAISE(ABORT, 'Committed operation history is immutable'); END"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM inventory_operations"))
        .scalar()
    ):
        raise RuntimeError(
            "Preparation/inventory data exists; restore a matching stopped-data backup"
        )
    for table in ("preparation_batches", "material_transfers"):
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER immutable_{table}_{action}")
    op.execute("DROP TRIGGER immutable_operation_update")
    op.execute("DROP TRIGGER immutable_operation_delete")
