"""Pinning notes and exact flush-scoped photographs; no historical backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0012_pinning_photos"
down_revision = "0011_fruiting"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fruiting_flushes", sa.Column("pinning_notes", sa.Text()))
    op.create_table(
        "pinning_photos",
        sa.Column(
            "photo_id",
            sa.String(36),
            sa.ForeignKey("photo_attachments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fruiting_id", sa.String(32), nullable=False),
        sa.Column("flush_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fruiting_id", "flush_number"],
            ["fruiting_flushes.fruiting_id", "fruiting_flushes.number"],
        ),
    )
    op.create_index(
        "ix_pinning_photos_flush", "pinning_photos", ["fruiting_id", "flush_number"]
    )
    op.execute(
        "CREATE TRIGGER valid_pinning_photo BEFORE INSERT ON pinning_photos WHEN NOT EXISTS (SELECT 1 FROM fruiting_flushes f JOIN photo_attachments p ON p.id=NEW.photo_id WHERE f.fruiting_id=NEW.fruiting_id AND f.number=NEW.flush_number AND f.pinning_date IS NOT NULL AND p.fruiting_id=NEW.fruiting_id) BEGIN SELECT RAISE(ABORT, 'Pinning photo must belong to its recorded flush event'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_pinning_photo BEFORE UPDATE ON pinning_photos BEGIN SELECT RAISE(ABORT, 'Pinning photo relationships are permanent'); END"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM pinning_photos) + (SELECT count(*) FROM fruiting_flushes WHERE pinning_notes IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Pinning photo or notes history exists; restore a matching stopped-data backup"
        )
    op.execute("DROP TRIGGER immutable_pinning_photo")
    op.execute("DROP TRIGGER valid_pinning_photo")
    op.drop_table("pinning_photos")
    op.drop_column("fruiting_flushes", "pinning_notes")
