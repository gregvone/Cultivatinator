"""Track recipe edit dates without modifying prior preparation snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0008_recipes"
down_revision = "0007_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "preparation_recipes", sa.Column("updated_at", sa.String(40), nullable=True)
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM preparation_recipes WHERE updated_at IS NOT NULL"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Recipe edit history exists; restore a matching stopped-data backup"
        )
    op.drop_column("preparation_recipes", "updated_at")
