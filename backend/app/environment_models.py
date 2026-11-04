"""Manual monitoring is independent of legacy grow configuration snapshots."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import now


class EnvironmentalProfile(Base):
    __tablename__ = "environmental_profiles"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("revision > 0"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    species: Mapped[str | None] = mapped_column(String(200))
    targets: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class FruitingTent(Base):
    __tablename__ = "fruiting_tents"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')"),
        CheckConstraint("revision > 0"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("environmental_profiles.id")
    )


class ProfileAssignment(Base):
    __tablename__ = "environment_profile_assignments"
    __table_args__ = (Index("ix_env_assignment_time", "tent_id", "assigned_at", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tent_id: Mapped[str] = mapped_column(ForeignKey("fruiting_tents.id"))
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("environmental_profiles.id")
    )
    assigned_at: Mapped[str] = mapped_column(String(40), default=now)
    snapshot: Mapped[str] = mapped_column(Text)


class EnvironmentalReading(Base):
    __tablename__ = "environmental_readings"
    __table_args__ = (
        Index("ix_env_reading_time", "tent_id", "observed_at", "id"),
        CheckConstraint("temperature_f BETWEEN -148 AND 212"),
        CheckConstraint("humidity BETWEEN 0 AND 100"),
        CheckConstraint("co2 IS NULL OR co2 BETWEEN 0 AND 1000000"),
        CheckConstraint("humidifier IS NULL OR humidifier BETWEEN 0 AND 10"),
        CheckConstraint("fan IS NULL OR fan BETWEEN 0 AND 10"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tent_id: Mapped[str] = mapped_column(ForeignKey("fruiting_tents.id"))
    observed_at: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    temperature_f: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    co2: Mapped[float | None] = mapped_column(Float)
    humidifier: Mapped[int | None] = mapped_column(Integer)
    fan: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("environmental_profiles.id")
    )
    snapshot: Mapped[str] = mapped_column(Text)
    evaluations: Mapped[str] = mapped_column(Text)
    replaces_id: Mapped[int | None] = mapped_column(
        ForeignKey("environmental_readings.id"), unique=True
    )
    correction_reason: Mapped[str | None] = mapped_column(Text)


class TentOccupancy(Base):
    __tablename__ = "tent_occupancies"
    __table_args__ = (
        CheckConstraint("left_at IS NULL OR left_at > entered_at"),
        CheckConstraint("revision > 0"),
        Index("ix_env_occupancy_container", "fruiting_id", "entered_at", "left_at"),
        Index("ix_env_occupancy_tent", "tent_id", "entered_at", "left_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tent_id: Mapped[str] = mapped_column(ForeignKey("fruiting_tents.id"))
    fruiting_id: Mapped[str] = mapped_column(ForeignKey("fruiting_containers.id"))
    entered_at: Mapped[str] = mapped_column(String(40))
    left_at: Mapped[str | None] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class EnvironmentAudit(Base):
    __tablename__ = "environment_audits"
    __table_args__ = (Index("ix_env_audit_owner", "entity_type", "entity_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(32))
    operation_id: Mapped[str] = mapped_column(ForeignKey("inventory_operations.id"))
    recorded_at: Mapped[str] = mapped_column(String(40), default=now)
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class EnvironmentWarning(Base):
    __tablename__ = "environment_warnings"
    __table_args__ = (CheckConstraint("metric IN ('temperature_f','humidity','co2')"),)
    tent_id: Mapped[str] = mapped_column(
        ForeignKey("fruiting_tents.id"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(String(30), primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("environmental_readings.id"))
    state: Mapped[str] = mapped_column(String(20))


class EnvironmentWarningEvent(Base):
    __tablename__ = "environment_warning_events"
    __table_args__ = (Index("ix_env_warning_history", "tent_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tent_id: Mapped[str] = mapped_column(ForeignKey("fruiting_tents.id"))
    metric: Mapped[str] = mapped_column(String(30))
    operation_id: Mapped[str] = mapped_column(ForeignKey("inventory_operations.id"))
    recorded_at: Mapped[str] = mapped_column(String(40), default=now)
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
