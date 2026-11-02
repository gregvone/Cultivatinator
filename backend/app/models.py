"""Culture Library records. Archiving never removes identities or relationships."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
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


OWNER_CHECK = "(strain_id IS NOT NULL) + (line_id IS NOT NULL) + (spore_id IS NOT NULL) + (physical_id IS NOT NULL) = 1"


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
            for key in ("strain_id", "line_id", "spore_id", "physical_id")
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
