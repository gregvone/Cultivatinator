"""One explicitly designated LC media default; preserve all existing recipes."""

from alembic import op
import sqlalchemy as sa

revision = "0009_lc_default"
down_revision = "0008_recipes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lc_media_default",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recipe_id",
            sa.String(32),
            sa.ForeignKey("preparation_recipes.id"),
            nullable=False,
            unique=True,
        ),
        sa.CheckConstraint("id = 1"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM lc_media_default")).scalar():
        raise RuntimeError(
            "An LC Media default is configured; preserve its configuration before rollback"
        )
    op.drop_table("lc_media_default")
