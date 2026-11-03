"""Fruiting and completion journal photos; preserve previous event history."""

from alembic import op
import sqlalchemy as sa

revision = "0013_journal_photos"
down_revision = "0012_pinning_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fruiting_flushes", sa.Column("fruiting_notes", sa.Text()))
    op.create_table(
        "journal_photos",
        sa.Column(
            "photo_id",
            sa.String(36),
            sa.ForeignKey("photo_attachments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "fruiting_id",
            sa.String(32),
            sa.ForeignKey("fruiting_runs.fruiting_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("flush_number", sa.Integer()),
        sa.ForeignKeyConstraint(
            ["fruiting_id", "flush_number"],
            ["fruiting_flushes.fruiting_id", "fruiting_flushes.number"],
        ),
        sa.CheckConstraint(
            "(event_type = 'fruiting' AND flush_number IS NOT NULL) OR (event_type = 'completed' AND flush_number IS NULL)"
        ),
    )
    op.create_index(
        "ix_journal_photos_event",
        "journal_photos",
        ["fruiting_id", "event_type", "flush_number"],
    )
    op.execute(
        "CREATE TRIGGER valid_journal_photo BEFORE INSERT ON journal_photos WHEN NOT EXISTS (SELECT 1 FROM photo_attachments p JOIN fruiting_runs r ON r.fruiting_id=NEW.fruiting_id WHERE p.id=NEW.photo_id AND p.fruiting_id=NEW.fruiting_id AND ((NEW.event_type='completed' AND r.completed_date IS NOT NULL AND NEW.flush_number IS NULL) OR (NEW.event_type='fruiting' AND EXISTS (SELECT 1 FROM fruiting_flushes f WHERE f.fruiting_id=NEW.fruiting_id AND f.number=NEW.flush_number AND f.fruiting_date IS NOT NULL)))) BEGIN SELECT RAISE(ABORT, 'Journal photo must belong to its recorded event'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_journal_photo BEFORE UPDATE ON journal_photos BEGIN SELECT RAISE(ABORT, 'Journal photo relationships are permanent'); END"
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM journal_photos) + (SELECT count(*) FROM fruiting_flushes WHERE fruiting_notes IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Journal photo or notes history exists; restore a matching stopped-data backup"
        )
    op.execute("DROP TRIGGER immutable_journal_photo")
    op.execute("DROP TRIGGER valid_journal_photo")
    op.drop_table("journal_photos")
    op.drop_column("fruiting_flushes", "fruiting_notes")
