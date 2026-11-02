"""Additive inventory/preparation records; legacy quantities stay descriptive."""

from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import now


class StockItem(Base):
    __tablename__ = "stock_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('ingredient','consumable','reusable','source','equipment','other')"
        ),
        CheckConstraint("available IS NULL OR available >= 0"),
        CheckConstraint(
            "category != 'reusable' OR (available IS NOT NULL AND unit = 'count')"
        ),
        CheckConstraint(
            "(category = 'source' AND (physical_id IS NOT NULL) + (spore_id IS NOT NULL) = 1) OR (category != 'source' AND physical_id IS NULL AND spore_id IS NULL)"
        ),
        CheckConstraint("status IN ('active','archived')"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), index=True)
    unit: Mapped[str] = mapped_column(String(20))
    available: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    available_exact: Mapped[str | None] = mapped_column(String(64))
    storage_location: Mapped[str | None] = mapped_column(String(200))
    container_type: Mapped[str | None] = mapped_column(String(30))
    physical_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_cultures.id"), unique=True
    )
    spore_id: Mapped[str | None] = mapped_column(
        ForeignKey("spore_sources.id"), unique=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class InventoryOperation(Base):
    __tablename__ = "inventory_operations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    operation_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), index=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("stock_items.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(20))
    before_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    after_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    amount_exact: Mapped[str | None] = mapped_column(String(64))
    before_exact: Mapped[str | None] = mapped_column(String(64))
    after_exact: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Recipe(Base):
    __tablename__ = "preparation_recipes"
    __table_args__ = (CheckConstraint("status IN ('active','archived')"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    recipe_type: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[str | None] = mapped_column(String(40))
    contents: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class PreparationBatch(Base):
    __tablename__ = "preparation_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), unique=True
    )
    recipe_id: Mapped[str | None] = mapped_column(
        ForeignKey("preparation_recipes.id"), index=True
    )
    snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class PreparedMaterial(Base):
    __tablename__ = "prepared_materials"
    __table_args__ = (
        CheckConstraint(
            "material_type IN ('agar_plate','lc_jar','lc_syringe','spawn_jar','spawn_bag')"
        ),
        CheckConstraint(
            "stage IN ('preparing','ready','inoculated','completed','failed')"
        ),
        CheckConstraint("(physical_id IS NOT NULL) + (spawn_id IS NOT NULL) <= 1"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("preparation_batches.id"), index=True
    )
    material_type: Mapped[str] = mapped_column(String(30))
    stage: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    use_by: Mapped[str | None] = mapped_column(String(10))
    physical_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_cultures.id"), unique=True
    )
    spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"), unique=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ContainerReservation(Base):
    __tablename__ = "container_reservations"
    __table_args__ = (CheckConstraint("released IN (0,1)"),)
    prepared_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_materials.id"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("stock_items.id"), index=True)
    released: Mapped[int] = mapped_column(Integer, default=0)


class MaterialLifecycle(Base):
    __tablename__ = "material_lifecycles"
    __table_args__ = (
        CheckConstraint("(physical_id IS NOT NULL) + (spawn_id IS NOT NULL) = 1"),
        CheckConstraint("state IN ('active','depleted','completed','failed')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    physical_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_cultures.id"), unique=True
    )
    spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"), unique=True)
    state: Mapped[str] = mapped_column(String(20))


class MaterialTransfer(Base):
    __tablename__ = "material_transfers"
    __table_args__ = (
        CheckConstraint(
            "(physical_source_id IS NOT NULL) + (spore_source_id IS NOT NULL) = 1"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), index=True
    )
    prepared_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_materials.id"), unique=True
    )
    physical_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_cultures.id"), index=True
    )
    spore_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("spore_sources.id"), index=True
    )
    transfer_date: Mapped[str | None] = mapped_column(String(10))
    usage_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(20))
