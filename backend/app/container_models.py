"""Reusable physical labels are independent of permanent biological identities."""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

OWNER_CHECK = "(physical_id IS NOT NULL) + (spawn_id IS NOT NULL) + (fruiting_id IS NOT NULL) + (prepared_id IS NOT NULL) = 1"


class ContainerLabel(Base):
    __tablename__ = "container_labels"
    __table_args__ = (
        UniqueConstraint("container_type", "number"),
        CheckConstraint("number > 0"),
        CheckConstraint("reusable IN (0,1)"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_type: Mapped[str] = mapped_column(String(30))
    number: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    reusable: Mapped[int] = mapped_column(Integer)


class ContainerOwner:
    physical_id: Mapped[str | None] = mapped_column(ForeignKey("physical_cultures.id"))
    spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"))
    fruiting_id: Mapped[str | None] = mapped_column(
        ForeignKey("fruiting_containers.id")
    )
    prepared_id: Mapped[str | None] = mapped_column(ForeignKey("prepared_materials.id"))


class LabelAssignment(ContainerOwner, Base):
    __tablename__ = "label_assignments"
    __table_args__ = (
        CheckConstraint(OWNER_CHECK),
        Index(
            "uq_occupied_container_label",
            "label_id",
            unique=True,
            sqlite_where=text("released_at IS NULL"),
        ),
        *[
            Index(
                f"uq_active_label_{key}",
                key,
                unique=True,
                sqlite_where=text(f"released_at IS NULL AND {key} IS NOT NULL"),
            )
            for key in ("physical_id", "spawn_id", "fruiting_id", "prepared_id")
        ],
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("container_labels.id"), index=True)
    assigned_at: Mapped[str] = mapped_column(String(40))
    released_at: Mapped[str | None] = mapped_column(String(40))
    release_date: Mapped[str | None] = mapped_column(String(10))
    release_reason: Mapped[str | None] = mapped_column(String(500))


class CultivationState(ContainerOwner, Base):
    __tablename__ = "cultivation_states"
    __table_args__ = (
        CheckConstraint(OWNER_CHECK),
        CheckConstraint("phase IN ('colonizing','ready','used','completed','failed')"),
        *[
            UniqueConstraint(key)
            for key in ("physical_id", "spawn_id", "fruiting_id", "prepared_id")
        ],
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(20))
    inoculation_date: Mapped[str | None] = mapped_column(String(10))
    ready_date: Mapped[str | None] = mapped_column(String(10))
    used_date: Mapped[str | None] = mapped_column(String(10))
    completed_date: Mapped[str | None] = mapped_column(String(10))
    failed_date: Mapped[str | None] = mapped_column(String(10))
