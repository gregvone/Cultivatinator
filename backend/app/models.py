"""Culture Library records. Archiving never removes identities or relationships."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def now():
    return datetime.now(timezone.utc).isoformat()


class IdentitySequence(Base):
    __tablename__ = "identity_sequences"
    prefix: Mapped[str] = mapped_column(String(8), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class RecordFields:
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False, index=True
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now, nullable=False)


class Strain(RecordFields, Base):
    __tablename__ = "strains"
    __table_args__ = (CheckConstraint("status IN ('active','archived')"),)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)


class AcquisitionFields:
    strain_id: Mapped[str | None] = mapped_column(ForeignKey("strains.id"), index=True)
    supplier: Mapped[str | None] = mapped_column(String(200))
    supplier_reference: Mapped[str | None] = mapped_column(String(200))
    acquisition_date: Mapped[str | None] = mapped_column(String(10))


class CultureLine(RecordFields, AcquisitionFields, Base):
    __tablename__ = "culture_lines"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("origin IN ('purchased','gifted','other')"),
    )
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    supplier_batch: Mapped[str | None] = mapped_column(String(200))


class QuantityFields:
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    storage_location: Mapped[str | None] = mapped_column(String(200))


class SporeSource(RecordFields, AcquisitionFields, QuantityFields, Base):
    __tablename__ = "spore_sources"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint(
            "material_type IN ('spore_print','spore_syringe','spore_swab','other_spore')"
        ),
        CheckConstraint("quantity IS NULL OR quantity >= 0"),
        CheckConstraint("quantity IS NULL OR unit IS NOT NULL"),
    )
    material_type: Mapped[str] = mapped_column(String(30), nullable=False)


class PhysicalCulture(RecordFields, QuantityFields, Base):
    __tablename__ = "physical_cultures"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint(
            "material_type IN ('lc_syringe','lc_jar','agar_plate','slant','other_culture')"
        ),
        CheckConstraint("quantity IS NULL OR quantity >= 0"),
        CheckConstraint("quantity IS NULL OR unit IS NOT NULL"),
        CheckConstraint("purchase_price IS NULL OR purchase_price >= 0"),
    )
    line_id: Mapped[str] = mapped_column(
        ForeignKey("culture_lines.id"), nullable=False, index=True
    )
    material_type: Mapped[str] = mapped_column(String(30), nullable=False)
    acquisition_date: Mapped[str | None] = mapped_column(String(10))
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    registration_batch: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )


class Spawn(RecordFields, QuantityFields, AcquisitionFields, Base):
    supplier_batch: Mapped[str | None] = mapped_column(String(200))
    __tablename__ = "spawn"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("material_type IN ('spawn_jar','spawn_bag')"),
        CheckConstraint("stage IN ('ready','colonizing','used')"),
        CheckConstraint("quantity IS NULL OR quantity >= 0"),
        CheckConstraint("quantity IS NULL OR unit IS NOT NULL"),
    )
    line_id: Mapped[str] = mapped_column(ForeignKey("culture_lines.id"), index=True)
    material_type: Mapped[str] = mapped_column(String(30))
    stage: Mapped[str] = mapped_column(String(20), default="ready")


class GrowBatch(RecordFields, Base):
    supplier: Mapped[str | None] = mapped_column(String(200))
    supplier_reference: Mapped[str | None] = mapped_column(String(200))
    supplier_batch: Mapped[str | None] = mapped_column(String(200))
    __tablename__ = "grow_batches"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("batch_origin IN ('acquired','prepared')"),
        CheckConstraint("allocation_mode IN ('shared','specific')"),
        CheckConstraint(
            "(batch_origin = 'acquired' AND line_id IS NOT NULL) OR (batch_origin = 'prepared' AND line_id IS NULL)"
        ),
    )
    batch_origin: Mapped[str] = mapped_column(String(20))
    allocation_mode: Mapped[str] = mapped_column(String(20))
    line_id: Mapped[str | None] = mapped_column(
        ForeignKey("culture_lines.id"), index=True
    )
    acquisition_date: Mapped[str | None] = mapped_column(String(10))


class BatchSource(Base):
    __tablename__ = "batch_sources"
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("grow_batches.id"), primary_key=True
    )
    spawn_id: Mapped[str] = mapped_column(
        ForeignKey("spawn.id"), primary_key=True, index=True
    )


class FruitingContainer(RecordFields, QuantityFields, Base):
    __tablename__ = "fruiting_containers"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("material_type IN ('tray','bag','block','other')"),
        CheckConstraint("stage IN ('colonizing','ready','fruiting','finished')"),
        CheckConstraint("quantity IS NULL OR quantity >= 0"),
        CheckConstraint("quantity IS NULL OR unit IS NOT NULL"),
        UniqueConstraint("batch_id", "id"),
    )
    batch_id: Mapped[str] = mapped_column(ForeignKey("grow_batches.id"), index=True)
    material_type: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(20), default="ready")
    acquisition_date: Mapped[str | None] = mapped_column(String(10))


class FruitingSource(Base):
    __tablename__ = "fruiting_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "spawn_id"],
            ["batch_sources.batch_id", "batch_sources.spawn_id"],
        ),
        ForeignKeyConstraint(
            ["batch_id", "fruiting_id"],
            ["fruiting_containers.batch_id", "fruiting_containers.id"],
        ),
    )
    fruiting_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    spawn_id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    batch_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class SporeCollection(Base):
    __tablename__ = "spore_collections"
    spore_id: Mapped[str] = mapped_column(
        ForeignKey("spore_sources.id"), primary_key=True
    )
    fruiting_id: Mapped[str] = mapped_column(
        ForeignKey("fruiting_containers.id"), index=True
    )
    collection_date: Mapped[str | None] = mapped_column(String(10))


class LineOrigin(Base):
    __tablename__ = "line_origins"
    __table_args__ = (
        CheckConstraint(
            "origin_type IN ('external','spores','clone','isolate','other')"
        ),
        CheckConstraint(
            "(origin_type = 'spores' AND spore_id IS NOT NULL AND fruiting_id IS NULL) OR (origin_type = 'clone' AND fruiting_id IS NOT NULL AND spore_id IS NULL) OR (origin_type IN ('external','isolate','other') AND spore_id IS NULL AND fruiting_id IS NULL)"
        ),
    )
    line_id: Mapped[str] = mapped_column(
        ForeignKey("culture_lines.id"), primary_key=True
    )
    origin_type: Mapped[str] = mapped_column(String(20))
    spore_id: Mapped[str | None] = mapped_column(
        ForeignKey("spore_sources.id"), index=True
    )
    fruiting_id: Mapped[str | None] = mapped_column(
        ForeignKey("fruiting_containers.id"), index=True
    )
    origin_date: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class LineParent(Base):
    __tablename__ = "line_parents"
    __table_args__ = (
        CheckConstraint("line_id != parent_id"),
        CheckConstraint("confidence IN ('confirmed','possible')"),
        Index(
            "uq_confirmed_parent",
            "line_id",
            unique=True,
            sqlite_where=text("confidence = 'confirmed'"),
        ),
    )
    line_id: Mapped[str] = mapped_column(
        ForeignKey("culture_lines.id"), primary_key=True
    )
    parent_id: Mapped[str] = mapped_column(
        ForeignKey("culture_lines.id"), primary_key=True, index=True
    )
    confidence: Mapped[str] = mapped_column(String(20))


class OwnerFields:
    strain_id: Mapped[str | None] = mapped_column(ForeignKey("strains.id"), index=True)
    line_id: Mapped[str | None] = mapped_column(
        ForeignKey("culture_lines.id"), index=True
    )
    spore_id: Mapped[str | None] = mapped_column(
        ForeignKey("spore_sources.id"), index=True
    )
    physical_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_cultures.id"), index=True
    )

    spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("grow_batches.id"), index=True
    )
    fruiting_id: Mapped[str | None] = mapped_column(
        ForeignKey("fruiting_containers.id"), index=True
    )


OWNER_CHECK = "(strain_id IS NOT NULL) + (line_id IS NOT NULL) + (spore_id IS NOT NULL) + (physical_id IS NOT NULL) + (spawn_id IS NOT NULL) + (batch_id IS NOT NULL) + (fruiting_id IS NOT NULL) = 1"


class PhotoAttachment(OwnerFields, Base):
    __tablename__ = "photo_attachments"
    __table_args__ = (
        CheckConstraint(OWNER_CHECK),
        CheckConstraint("is_cover IN (0,1)"),
        *[
            Index(
                f"uq_photo_cover_{key}",
                key,
                unique=True,
                sqlite_where=text(f"is_cover = 1 AND {key} IS NOT NULL"),
            )
            for key in (
                "strain_id",
                "line_id",
                "spore_id",
                "physical_id",
                "spawn_id",
                "batch_id",
                "fruiting_id",
            )
        ],
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    thumbnail: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_cover: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now, nullable=False)


class ActivityEvent(OwnerFields, Base):
    __tablename__ = "activity_events"
    __table_args__ = (CheckConstraint(OWNER_CHECK),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[str] = mapped_column(
        String(40), default=now, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)


# Alembic and application startup share this metadata registry.
from . import preparation_models  # noqa: E402,F401

from . import container_models  # noqa: E402,F401

from .fruiting_models import (
    FruitingRun,
    FruitingFlush,
    HarvestEntry,
    HarvestRevision,
    FruitingEnvironment,
    FruitingEnvironmentChange,
    HarvestPhoto,
)  # noqa: E402,F401
