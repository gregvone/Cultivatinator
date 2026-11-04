"""Responses for fruiting participation; timing and ancestry remain explicit."""

from typing import Any, Literal
from .library_schemas import Input

Classification = Literal["prospective", "retrospective", "uncertain"]


class SourceFactsOut(Input):
    fruiting_id: str
    batch_id: str
    spawn_ids: list[str]
    line_ids: list[str]
    leaves: list[list[str]]
    ambiguous: bool
    ancestry: dict[str, list[Any]]
    fingerprint: str


class SuggestionOut(Input):
    group_ids: list[str]
    reason: str
    automatic: bool
    allocated_at: str
    rule_ids: list[str]


class CandidateOut(SourceFactsOut):
    suggestion: SuggestionOut | None


class MembershipOut(Input):
    id: int
    experiment_id: str
    unit_id: str
    fruiting_id: str
    exposure_start: str
    exposure_end: str | None
    classification: Classification
    evidence: dict[str, Any]


class ParticipantOut(MembershipOut):
    group_id: str
    group_name: str
    unit_kind: Literal["container", "batch", "tent_trial"]
    plan_revision: int
    flush_count: int
    sources: SourceFactsOut


class RuleOut(Input):
    id: str
    group_id: str
    kind: Literal["spawn", "physical", "line"]
    source_id: str
    recorded_at: str
    plan_revision: int
    active: int


class CountsOut(Input):
    containers: int
    treatment_units: int
    known_spawn_sources: int
    classification_counts: dict[Classification, int]


class ParticipantsOut(Input):
    items: list[ParticipantOut]
    total: int
    page: int
    page_size: int
    candidates: list[CandidateOut]
    candidate_total: int
    rules: list[RuleOut]
    revision: int
    plan_revision: int
    counts: CountsOut
    classification_summary: Literal[
        "prospective", "retrospective", "uncertain", "mixed"
    ]
    unit_warning: str


class EnrollmentResult(Input):
    membership: MembershipOut
    revision: int


class CreationResult(Input):
    operation_id: str
    containers: list[dict[str, Any]]
    memberships: list[MembershipOut]
    revision: int
