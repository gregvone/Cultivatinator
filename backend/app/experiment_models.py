"""Experiment associations never replace production records."""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint("category IN ('substrate','genetics','conditions')"),
        CheckConstraint("scope = 'fruiting'"),
        CheckConstraint(
            "state IN ('draft','planned','running','completed','cancelled')"
        ),
        CheckConstraint("revision > 0"),
        CheckConstraint("archived IN (0,1)"),
        CheckConstraint(
            "classification IN ('prospective','retrospective','uncertain')"
        ),
        CheckConstraint(
            "timing_precision IS NULL OR timing_precision IN ('instant','date')"
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    category: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20), default="fruiting")
    state: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    archived: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40))
    treatment_start: Mapped[str | None] = mapped_column(String(40))
    timing_precision: Mapped[str | None] = mapped_column(String(10))
    classification: Mapped[str] = mapped_column(String(20), default="uncertain")
    start_plan_revision: Mapped[int | None] = mapped_column(Integer)


class ExperimentPlanRevision(Base):
    __tablename__ = "experiment_plan_revisions"
    __table_args__ = (CheckConstraint("revision > 0"),)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[str] = mapped_column(Text)
    committed_at: Mapped[str | None] = mapped_column(String(40))
    allocation_committed_at: Mapped[str | None] = mapped_column(String(40))
    recorded_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), unique=True
    )


class ExperimentGroup(Base):
    __tablename__ = "experiment_groups"
    __table_args__ = (UniqueConstraint("experiment_id", "id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)


class ExperimentTrial(Base):
    __tablename__ = "experiment_trials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "group_id"],
            ["experiment_groups.experiment_id", "experiment_groups.id"],
        ),
        UniqueConstraint("experiment_id", "id"),
        UniqueConstraint("experiment_id", "group_id", "id"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at"),
        CheckConstraint("revision > 0"),
        Index("ix_experiment_trial_tent_time", "tent_id", "starts_at", "ends_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    group_id: Mapped[str] = mapped_column(String(32))
    tent_id: Mapped[str] = mapped_column(ForeignKey("fruiting_tents.id"))
    starts_at: Mapped[str] = mapped_column(String(40))
    ends_at: Mapped[str | None] = mapped_column(String(40))
    treatment_snapshot: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)


class ExperimentUnit(Base):
    __tablename__ = "experiment_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "plan_revision"],
            [
                "experiment_plan_revisions.experiment_id",
                "experiment_plan_revisions.revision",
            ],
        ),
        ForeignKeyConstraint(
            ["experiment_id", "group_id"],
            ["experiment_groups.experiment_id", "experiment_groups.id"],
        ),
        ForeignKeyConstraint(
            ["experiment_id", "group_id", "trial_id"],
            [
                "experiment_trials.experiment_id",
                "experiment_trials.group_id",
                "experiment_trials.id",
            ],
        ),
        UniqueConstraint("experiment_id", "id"),
        UniqueConstraint("experiment_id", "fruiting_id"),
        UniqueConstraint("experiment_id", "batch_id"),
        UniqueConstraint("experiment_id", "trial_id"),
        CheckConstraint("kind IN ('container','batch','tent_trial')"),
        CheckConstraint(
            "(kind='container' AND fruiting_id IS NOT NULL AND batch_id IS NULL AND trial_id IS NULL) OR (kind='batch' AND batch_id IS NOT NULL AND fruiting_id IS NULL AND trial_id IS NULL) OR (kind='tent_trial' AND trial_id IS NOT NULL AND fruiting_id IS NULL AND batch_id IS NULL)"
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    plan_revision: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[str] = mapped_column(String(40))
    group_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(20))
    fruiting_id: Mapped[str | None] = mapped_column(
        ForeignKey("fruiting_containers.id")
    )
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("grow_batches.id"))
    trial_id: Mapped[str | None] = mapped_column(String(32))
    block: Mapped[str | None] = mapped_column(String(200))
    allocated_at: Mapped[str] = mapped_column(String(40))


class ExperimentMembership(Base):
    __tablename__ = "experiment_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "unit_id"],
            ["experiment_units.experiment_id", "experiment_units.id"],
        ),
        UniqueConstraint("experiment_id", "unit_id", "fruiting_id", "exposure_start"),
        CheckConstraint("exposure_end IS NULL OR exposure_end > exposure_start"),
        CheckConstraint(
            "classification IN ('prospective','retrospective','uncertain')"
        ),
        Index("ix_experiment_membership_fruiting", "fruiting_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    unit_id: Mapped[str] = mapped_column(String(32))
    fruiting_id: Mapped[str] = mapped_column(ForeignKey("fruiting_containers.id"))
    exposure_start: Mapped[str] = mapped_column(String(40))
    exposure_end: Mapped[str | None] = mapped_column(String(40))
    classification: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str] = mapped_column(Text)


class ExperimentAudit(Base):
    __tablename__ = "experiment_audits"
    __table_args__ = (Index("ix_experiment_audit_history", "experiment_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), unique=True
    )
    recorded_at: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)


class ExperimentSourceRule(Base):
    __tablename__ = "experiment_source_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "plan_revision"],
            [
                "experiment_plan_revisions.experiment_id",
                "experiment_plan_revisions.revision",
            ],
        ),
        ForeignKeyConstraint(
            ["experiment_id", "group_id"],
            ["experiment_groups.experiment_id", "experiment_groups.id"],
        ),
        CheckConstraint(
            "(spawn_id IS NOT NULL) + (physical_id IS NOT NULL) + (line_id IS NOT NULL) = 1"
        ),
        CheckConstraint("active IN (0,1)"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[str] = mapped_column(String(32))
    spawn_id: Mapped[str | None] = mapped_column(ForeignKey("spawn.id"))
    physical_id: Mapped[str | None] = mapped_column(ForeignKey("physical_cultures.id"))
    line_id: Mapped[str | None] = mapped_column(ForeignKey("culture_lines.id"))
    recorded_at: Mapped[str] = mapped_column(String(40))
    active: Mapped[int] = mapped_column(Integer, default=1)


class ExperimentCreationAllocation(Base):
    __tablename__ = "experiment_creation_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "plan_revision"],
            [
                "experiment_plan_revisions.experiment_id",
                "experiment_plan_revisions.revision",
            ],
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    spawn_id: Mapped[str] = mapped_column(ForeignKey("spawn.id"))
    destinations: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(String(40))
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_operations.id"), unique=True
    )


class ExperimentEnrollmentEvent(Base):
    __tablename__ = "experiment_enrollment_events"
    __table_args__ = (Index("ix_enrollment_history", "experiment_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiment_memberships.id")
    )
    operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_operations.id")
    )
    recorded_at: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
