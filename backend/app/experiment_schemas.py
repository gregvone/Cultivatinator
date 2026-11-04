"""Typed foundation contracts; enrollment/trial commands are deferred."""

from datetime import date
from typing import Annotated, Literal
from pydantic import AwareDatetime, Field, model_validator, field_validator
from fastapi import HTTPException
import math
from .library_schemas import Input, Text, Notes
from .preparation_schemas import Command

Name = Annotated[Text, Field(min_length=1)]
Outcome = Literal[
    "completed_wet_yield",
    "completed_dry_yield",
    "days_to_pinning",
    "days_to_first_harvest",
    "cycle_days",
    "failure_rate",
]


class Advanced(Input):
    allocation_schedule: Notes | None = None
    blocking: Notes | None = None
    eligibility: Notes | None = None
    exclusions: Notes | None = None
    observation_window: Notes | None = None
    minimum_readings: int | None = Field(default=None, ge=1, le=1000000)
    maximum_gap_hours: float | None = Field(
        default=None, gt=0, le=87600, allow_inf_nan=False
    )

    @field_validator("maximum_gap_hours", mode="before")
    @classmethod
    def finite(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            raise HTTPException(422, "Coverage settings must be finite")
        return value


class Group(Input):
    id: Text | None = None
    name: Name
    treatment: Name
    control: bool = False


class Plan(Input):
    title: Name
    category: Literal["substrate", "genetics", "conditions"]
    scope: Literal["fruiting"] = "fruiting"
    primary_variable: Name
    primary_outcome: Outcome
    secondary_outcomes: list[Outcome] = Field(default_factory=list, max_length=5)
    hypotheses: Notes | None = None
    groups: list[Group] = Field(min_length=2, max_length=20)
    advanced: Advanced = Field(default_factory=Advanced)

    @model_validator(mode="after")
    def unique(self):
        if len({g.name.casefold() for g in self.groups}) != len(self.groups):
            raise ValueError("Group names must be distinct")
        if sum(g.control for g in self.groups) > 1:
            raise ValueError("Select at most one control group")
        ids = [g.id for g in self.groups if g.id]
        if len(set(ids)) != len(ids):
            raise ValueError("Group IDs must be distinct")
        if self.primary_outcome in self.secondary_outcomes or len(
            set(self.secondary_outcomes)
        ) != len(self.secondary_outcomes):
            raise ValueError("Outcomes must be distinct")
        return self


class CreateExperiment(Command):
    plan: Plan


class EditPlan(CreateExperiment):
    expected_revision: int = Field(ge=1)
    reason: Name


class Action(Command):
    expected_revision: int = Field(ge=1)
    action: Literal["plan", "start", "complete", "cancel", "archive", "restore"]
    reason: Name
    treatment_start: AwareDatetime | None = None
    treatment_date: date | None = None

    @model_validator(mode="after")
    def timing(self):
        supplied = int(self.treatment_start is not None) + int(
            self.treatment_date is not None
        )
        if (self.action == "start" and supplied != 1) or (
            self.action != "start" and supplied
        ):
            raise ValueError(
                "Start requires exactly one treatment instant or calendar date; other actions accept neither"
            )
        return self


class ExperimentOut(Input):
    id: str
    category: str
    scope: Literal["fruiting"]
    state: str
    revision: int
    archived: int
    created_at: str
    started_at: str | None
    treatment_start: str | None
    timing_precision: str | None
    classification: Literal["prospective", "retrospective", "uncertain"]
    start_plan_revision: int | None
    plan: Plan
    plan_revision: int
    post_start_amendment: bool
    classification_basis: str


class ExperimentPage(Input):
    items: list[ExperimentOut]
    total: int
    page: int
    page_size: int


class PlanRevisionOut(Input):
    experiment_id: str
    revision: int
    snapshot: Plan
    committed_at: str | None
    allocation_committed_at: str | None
    recorded_at: str
    reason: str
    operation_id: str


class AuditOut(Input):
    id: int
    experiment_id: str
    operation_id: str
    recorded_at: str
    action: str
    before: dict | None
    after: dict
    reason: str


class HistoryPage(Input):
    plans: list[PlanRevisionOut]
    audits: list[AuditOut]
    plan_total: int
    audit_total: int
    page: int
    page_size: int
