"""Generic supply categories, storage and exact converted quantities.

No historical transactions, preparation stages or IDs are rewritten.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_inventory"
down_revision = "0006_history"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    stock = sa.Table("stock_items", metadata, autoload_with=connection)
    category_check = next(
        c
        for c in stock.constraints
        if isinstance(c, sa.CheckConstraint)
        and str(c.sqltext).startswith("category IN")
    )
    stock.constraints.remove(category_check)
    stock.append_constraint(
        sa.CheckConstraint(
            "category IN ('ingredient','consumable','reusable','source','equipment','other')"
        )
    )
    with op.batch_alter_table(
        "stock_items", copy_from=stock, recreate="always"
    ) as batch:
        batch.add_column(sa.Column("storage_location", sa.String(200)))
        batch.add_column(sa.Column("available_exact", sa.String(64)))
    for name in ("amount_exact", "before_exact", "after_exact"):
        op.add_column("stock_transactions", sa.Column(name, sa.String(64)))
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Inventory migration failed foreign-key validation")


def downgrade():
    # Do not discard precise balances, locations or new categories on rollback.
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM stock_items WHERE available_exact IS NOT NULL OR storage_location IS NOT NULL OR category IN ('equipment','other')) + (SELECT count(*) FROM stock_transactions WHERE amount_exact IS NOT NULL OR before_exact IS NOT NULL OR after_exact IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "New inventory data exists; restore a matching stopped-data backup"
        )
    for name in ("amount_exact", "before_exact", "after_exact"):
        op.drop_column("stock_transactions", name)
    connection = op.get_bind()
    stock = sa.Table("stock_items", sa.MetaData(), autoload_with=connection)
    check = next(
        c
        for c in stock.constraints
        if isinstance(c, sa.CheckConstraint)
        and str(c.sqltext).startswith("category IN")
    )
    stock.constraints.remove(check)
    stock.append_constraint(
        sa.CheckConstraint(
            "category IN ('ingredient','consumable','reusable','source')"
        )
    )
    with op.batch_alter_table(
        "stock_items", copy_from=stock, recreate="always"
    ) as batch:
        batch.drop_column("available_exact")
        batch.drop_column("storage_location")
