"""Operational fruiting history, kept separate from legacy manual registrations."""

from decimal import Decimal
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import now


class FruitingRun(Base):
    __tablename__ = "fruiting_runs"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('unrecorded','colonizing','pinning','fruiting','harvest','completed','failed')"
        ),
        CheckConstraint("current_flush > 0"),
        CheckConstraint("spawn_grams IS NULL OR spawn_grams >= 0"),
        CheckConstraint("substrate_grams IS NULL OR substrate_grams >= 0"),
    )
    fruiting_id: Mapped[str] = mapped_column(
        ForeignKey("fruiting_containers.id"), primary_key=True
    )
    operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_operations.id")
    )
    source_spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"))
    recipe_id: Mapped[str | None] = mapped_column(
        ForeignKey("preparation_recipes.id"), index=True
    )
    recipe_snapshot: Mapped[str | None] = mapped_column(Text)
    environment_snapshot: Mapped[str | None] = mapped_column(Text)
    spawning_date: Mapped[str | None] = mapped_column(String(10))
    spawn_grams: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    substrate_grams: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    stage: Mapped[str] = mapped_column(String(20))
    current_flush: Mapped[int] = mapped_column(Integer, default=1)
    completed_date: Mapped[str | None] = mapped_column(String(10))
    failed_date: Mapped[str | None] = mapped_column(String(10))
    closing_notes: Mapped[str | None] = mapped_column(Text)


class FruitingFlush(Base):
    __tablename__ = "fruiting_flushes"
    __table_args__ = (CheckConstraint("number > 0"),)
    fruiting_id: Mapped[str] = mapped_column(
        ForeignKey("fruiting_runs.fruiting_id"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    pinning_date: Mapped[str | None] = mapped_column(String(10))
    pinning_notes: Mapped[str | None] = mapped_column(Text)
    fruiting_date: Mapped[str | None] = mapped_column(String(10))


class HarvestEntry(Base):
    __tablename__ = "harvest_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fruiting_id", "flush_number"],
            ["fruiting_flushes.fruiting_id", "fruiting_flushes.number"],
        ),
        CheckConstraint("wet_grams IS NULL OR wet_grams >= 0"),
        CheckConstraint("dry_grams IS NULL OR dry_grams >= 0"),
        CheckConstraint("potency IS NULL OR potency BETWEEN 1 AND 5"),
        CheckConstraint("revision > 0"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fruiting_id: Mapped[str] = mapped_column(String(32), index=True)
    flush_number: Mapped[int] = mapped_column(Integer)
    harvest_date: Mapped[str] = mapped_column(String(10))
    wet_grams: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    dry_grams: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    potency: Mapped[int | None] = mapped_column(Integer)
    potency_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class HarvestRevision(Base):
    __tablename__ = "harvest_revisions"
    __table_args__ = (UniqueConstraint("harvest_id", "revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    harvest_id: Mapped[str] = mapped_column(
        ForeignKey("harvest_entries.id"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), unique=True
    )
    snapshot: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(String(40), default=now)


class FruitingEnvironment(Base):
    __tablename__ = "fruiting_environment"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    settings: Mapped[str] = mapped_column(Text)


class FruitingEnvironmentChange(Base):
    __tablename__ = "fruiting_environment_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fruiting_id: Mapped[str] = mapped_column(
        ForeignKey("fruiting_runs.fruiting_id"), index=True
    )
    change_date: Mapped[str] = mapped_column(String(10))
    settings: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(String(40), default=now)


class HarvestPhoto(Base):
    __tablename__ = "harvest_photos"
    photo_id: Mapped[str] = mapped_column(
        ForeignKey("photo_attachments.id", ondelete="CASCADE"), primary_key=True
    )
    harvest_id: Mapped[str] = mapped_column(
        ForeignKey("harvest_entries.id"), index=True
    )


class PinningPhoto(Base):
    __tablename__ = "pinning_photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fruiting_id", "flush_number"],
            ["fruiting_flushes.fruiting_id", "fruiting_flushes.number"],
        ),
        Index("ix_pinning_photos_flush", "fruiting_id", "flush_number"),
    )
    photo_id: Mapped[str] = mapped_column(
        ForeignKey("photo_attachments.id", ondelete="CASCADE"), primary_key=True
    )
    fruiting_id: Mapped[str] = mapped_column(String(32))
    flush_number: Mapped[int] = mapped_column(Integer)
