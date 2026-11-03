"""Read-only reporting contracts. Decimal values serialize as strings."""

from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel


class Average(BaseModel):
    value: Decimal | None
    sample_count: int
    missing_count: int


class Statistics(BaseModel):
    completed: int
    failed: int
    terminal_count: int
    failure_rate_percent: Decimal | None
    qualifying_containers: int
    excluded_incomplete_wet: int
    average_wet_grams: Decimal | None
    qualifying_wet_total_grams: Decimal | None
    total_known_wet_grams: Decimal | None
    completed_known_wet_grams: Decimal | None
    failed_known_wet_grams: Decimal | None
    wet_measured_containers: int
    wet_measurement_count: int
    harvest_count: int
    distinct_spawn_sources: int
    containers_without_known_spawn: int
    average_dry_grams: Average
    days_to_first_pinning: Average
    days_to_first_harvest: Average
    cycle_days: Average


class Observation(BaseModel):
    id: str
    label: str | None
    name: str | None
    outcome: Literal["completed", "failed", "active"]
    outcome_date: str | None
    archived: bool
    legacy: bool
    strain_identity: Literal["known", "mixed", "partial", "unknown"]
    line_identity: Literal["known", "mixed", "partial", "unknown"]
    strain_ids: list[str]
    line_ids: list[str]
    spawn_ids: list[str]
    strain_names: list[str]
    line_names: list[str]
    species: str | None
    recipe_id: str | None
    recipe_name: str | None
    recipe_revision: int | None
    harvest_count: int
    wet_measurement_count: int
    known_wet_grams: Decimal | None
    complete_wet: bool
    known_dry_grams: Decimal | None
    complete_dry: bool
    days_to_first_pinning: int | None
    days_to_first_harvest: int | None
    cycle_days: int | None


class RevisionResult(BaseModel):
    revision: int | None
    name: str
    snapshot: dict[str, Any]
    stats: Statistics
    record_ids: list[str]


class Comparison(BaseModel):
    key: str
    name: str
    identity: str
    ranked: bool
    preliminary: bool
    stats: Statistics
    record_ids: list[str]
    revisions: list[RevisionResult]


class FlushResult(BaseModel):
    number: int
    containers_reached: int
    qualifying_containers: int
    excluded_incomplete_wet: int
    average_wet_grams: Decimal | None
    total_known_wet_grams: Decimal | None
    record_ids: list[str]
    qualifying_record_ids: list[str]


class PerformanceReport(BaseModel):
    group_by: Literal["strain", "line", "recipe"]
    period: dict[str, str | None]
    options: dict[str, Any]
    summary: Statistics
    groups: list[Comparison]
    flushes: list[FlushResult]
    records: list[Observation]
    active_records: list[Observation]
    matching_containers: int
    terminal_containers_outside_period: int
    undated_terminal_excluded: int
    legacy_containers: int
