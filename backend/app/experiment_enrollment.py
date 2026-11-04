"""Fruiting enrollment and precommitted creation; trial scheduling remains deferred."""

import json
import hashlib
from datetime import date, datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .library_schemas import Input, Text
from .preparation_schemas import Command
from .preparation import execute, get, recipe_out
from .library import allocate
from .models import FruitingContainer, Spawn, PhysicalCulture, CultureLine
from .fruiting_models import FruitingRun, FruitingFlush
from .preparation_models import Recipe
from .fruiting import SpawnToBulk, create_fruiting, row_dict
from .experiment_models import (
    Experiment,
    ExperimentPlanRevision as Plan,
    ExperimentUnit as Unit,
    ExperimentMembership as Member,
    ExperimentSourceRule as Rule,
    ExperimentCreationAllocation as Allocation,
    ExperimentEnrollmentEvent as Event,
)
from .experiments import clock, latest, check, classify
from .experiment_schemas import Name
from .experiment_lineage import provenance, proposal
from .experiment_enrollment_schemas import (
    ParticipantsOut,
    EnrollmentResult,
    CreationResult,
)

router = APIRouter(prefix="/api/experiments", tags=["Experiment participants"])


class RevisionCommand(Command):
    expected_revision: int = Field(ge=1)
    reason: Name


class Enrollment(RevisionCommand):
    plan_revision: int = Field(ge=1)
    group_id: Text
    fruiting_id: Text
    fingerprint: Text
    treatment_start: AwareDatetime | None = None
    treatment_date: date | None = None
    unit_id: Text | None = None

    @model_validator(mode="after")
    def timing(self):
        if self.treatment_start and self.treatment_date:
            raise ValueError("Choose an instant or date, not both")
        return self


class SourceRule(RevisionCommand):
    plan_revision: int = Field(ge=1)
    group_id: Text
    source_kind: Literal["spawn", "physical", "line"]
    source_id: Text


class Destination(Input):
    group_id: Text
    recipe_id: Text
    count: int = Field(ge=1, le=100)


class CreationAllocation(RevisionCommand):
    plan_revision: int = Field(ge=1)
    spawn_id: Text
    destinations: list[Destination] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def total(self):
        if sum(d.count for d in self.destinations) > 100:
            raise ValueError("At most 100 containers per command")
        return self


class FruitingCreation(RevisionCommand):
    allocation_id: Text
    spawning_date: date
    treatment_start: AwareDatetime | None = None
    material_type: Literal["tray", "bag", "block"] = "tray"


class Review(RevisionCommand):
    decision: Literal["keep", "exclude", "reassign"]
    group_id: Text | None = None
    plan_revision: int | None = Field(default=None, ge=1)
    fingerprint: Text


def writable(s, code, data):
    row = get(s, Experiment, code)
    check(row, data.expected_revision)
    if row.archived or row.state not in {"planned", "running"}:
        raise HTTPException(409, "Use an unarchived Planned or Running experiment")
    return row


def valid_group(s, row, revision, group):
    plan = get(s, Plan, (row.id, revision))
    if not plan.committed_at:
        raise HTTPException(
            409, "Commit the applicable plan before allocating treatments"
        )
    if group not in {g["id"] for g in json.loads(plan.snapshot)["groups"]}:
        raise HTTPException(422, "Group is not in this historical plan revision")
    return plan


def event(s, row, member, action, before, after, reason, op=None):
    s.add(
        Event(
            experiment_id=row.id,
            membership_id=member.id if member else None,
            operation_id=op.id if op else None,
            recorded_at=clock(),
            action=action,
            before=json.dumps(before) if before is not None else None,
            after=json.dumps(after),
            reason=reason,
        )
    )


def snapshot(member):
    return {**row_dict(member), "evidence": json.loads(member.evidence)}


def rule_dict(r):
    kind = "spawn" if r.spawn_id else "physical" if r.physical_id else "line"
    return dict(
        id=r.id,
        group_id=r.group_id,
        kind=kind,
        source_id=r.spawn_id or r.physical_id or r.line_id,
        recorded_at=r.recorded_at,
        plan_revision=r.plan_revision,
        active=r.active,
    )


def timing(s, fr, instant=None, day=None):
    run = s.get(FruitingRun, fr.id)
    actual_date = run.spawning_date if run else fr.acquisition_date
    if instant:
        if instant > datetime.fromisoformat(clock()):
            raise HTTPException(422, "Actual treatment cannot be in the future")
        if actual_date:
            # Legacy cultivation dates have no timezone. Preserve their precision:
            # an aware instant must fit that calendar day in some valid UTC offset.
            midnight = datetime.fromisoformat(actual_date).replace(tzinfo=timezone.utc)
            if (
                not midnight - timedelta(hours=14)
                <= instant
                < midnight + timedelta(hours=38)
            ):
                raise HTTPException(
                    422,
                    "Treatment instant is incompatible with the recorded fruiting treatment date",
                )
        return (
            instant.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            "instant",
        )
    value = day.isoformat() if day else actual_date
    if day and actual_date and value != actual_date:
        raise HTTPException(
            422, "Treatment date must match the recorded fruiting treatment date"
        )
    if value and value < "1900-01-01":
        raise HTTPException(422, "Treatment dates must be 1900 or later")
    if (
        value
        and value
        > (datetime.fromisoformat(clock()) + timedelta(hours=14)).date().isoformat()
    ):
        raise HTTPException(422, "Actual treatment cannot be in the future")
    return value, "date"


def add_member(
    s,
    row,
    plan,
    group,
    fr,
    facts,
    allocated_at,
    origin,
    op=None,
    instant=None,
    day=None,
    unit=None,
    extra=None,
):
    if s.scalar(
        select(Member.id).where(
            Member.experiment_id == row.id, Member.fruiting_id == fr.id
        )
    ):
        raise HTTPException(
            409,
            "This container is already enrolled; use review to correct its assignment",
        )
    if row.category == "conditions" and (not unit or unit.kind != "tent_trial"):
        raise HTTPException(
            409,
            "Condition observations require an existing shared tent-trial unit; setup is deferred to 2H.3",
        )
    if unit:
        if (
            unit.experiment_id != row.id
            or unit.group_id != group
            or unit.plan_revision != plan.revision
        ):
            raise HTTPException(422, "Unit does not belong to this group and plan")
        if unit.kind == "container" and unit.fruiting_id != fr.id:
            raise HTTPException(
                422, "A container unit can only refer to its own fruiting container"
            )
        if unit.kind == "batch" and unit.batch_id != fr.batch_id:
            raise HTTPException(422, "Container does not belong to this batch unit")
    elif row.category == "conditions":
        raise HTTPException(
            409,
            "Select an existing shared tent-trial unit; environmental trial setup belongs to 2H.3",
        )
    start, precision = timing(s, fr, instant, day)
    classification = (
        classify(
            plan.committed_at,
            [allocated_at],
            (
                datetime.fromisoformat(start)
                if precision == "instant"
                else date.fromisoformat(start)
            ),
            precision,
        )
        if start
        else "uncertain"
    )
    if not unit:
        unit = Unit(
            id=allocate(s, "EU"),
            experiment_id=row.id,
            plan_revision=plan.revision,
            group_id=group,
            kind="container",
            fruiting_id=fr.id,
            allocated_at=allocated_at,
            recorded_at=clock(),
            block=",".join(facts["spawn_ids"]) or None,
        )
        s.add(unit)
        s.flush()
    evidence = dict(
        origin=origin,
        group_id=group,
        status="confirmed",
        plan_revision=plan.revision,
        source_fingerprint=facts["fingerprint"],
        sources=facts,
        allocated_at=allocated_at,
        treatment_start=start,
        timing_precision=precision,
        original_classification=classification,
    )
    evidence.update(extra or {})
    if row.category == "genetics" and (
        facts["ambiguous"] or len(facts["line_ids"]) != 1
    ):
        evidence.update(
            status="needs_review",
            review_reason="Mixed or uncertain ancestry is not eligible for a pure genetics comparison",
        )
    member = Member(
        experiment_id=row.id,
        unit_id=unit.id,
        fruiting_id=fr.id,
        exposure_start=(
            start
            if precision == "instant"
            else (start + "T00:00:00.000000+00:00" if start else clock())
        ),
        exposure_end=None,
        classification=classification,
        evidence=json.dumps(evidence),
    )
    s.add(member)
    s.flush()
    event(
        s,
        row,
        member,
        "enrolled",
        None,
        snapshot(member),
        "Confirmed fruiting participation",
        op,
    )
    return member


def rule_signature(rules):
    return hashlib.sha256(
        json.dumps(sorted(rules, key=lambda r: r["id"]), sort_keys=True).encode()
    ).hexdigest()


def synchronize(s, op=None):
    """Called inside domain transactions. GET never writes; confirmed assignments stay put."""
    s.flush()
    rows = list(s.scalars(select(Experiment)))
    if not rows:
        return
    members = list(s.scalars(select(Member)))
    rules = list(s.scalars(select(Rule).where(Rule.active == 1)))
    if not members and not rules:
        return
    facts = provenance(s)
    for row in rows:
        changed = False
        existing = {m.fruiting_id: m for m in members if m.experiment_id == row.id}
        for fr_id, m in existing.items():
            ev = json.loads(m.evidence)
            if ev.get("status") == "excluded" or not ev.get("source_fingerprint"):
                continue
            applicable = [
                rule_dict(r)
                for r in rules
                if r.experiment_id == row.id
                and r.plan_revision == ev.get("plan_revision")
            ]
            suggested = (
                proposal(facts[fr_id], applicable, row.category)
                if ev.get("origin") == "lineage"
                else None
            )
            rule_conflict = (
                ev.get("origin") == "lineage"
                and ev.get("acknowledged_rules") != rule_signature(applicable)
                and (
                    not suggested
                    or not suggested["automatic"]
                    or s.get(Unit, m.unit_id).group_id not in suggested["group_ids"]
                )
            )
            if (
                facts[fr_id]["fingerprint"] != ev["source_fingerprint"] or rule_conflict
            ) and ev.get("status") != "needs_review":
                before = snapshot(m)
                ev["status"] = "needs_review"
                ev["review_reason"] = (
                    "Provenance or source assignment changed; confirmed group retained"
                )
                m.evidence = json.dumps(ev)
                event(
                    s,
                    row,
                    m,
                    "review_required",
                    before,
                    snapshot(m),
                    ev["review_reason"],
                    op,
                )
                changed = True
        current = latest(s, row.id)
        active = [
            rule_dict(r)
            for r in rules
            if r.experiment_id == row.id and r.plan_revision == current.revision
        ]
        if (
            current.committed_at
            and not row.archived
            and row.state in {"planned", "running"}
        ):
            for fr_id, f in facts.items():
                if fr_id in existing:
                    continue
                suggestion = proposal(f, active, row.category)
                if suggestion and suggestion["automatic"]:
                    fr = s.get(FruitingContainer, fr_id)
                    add_member(
                        s,
                        row,
                        current,
                        suggestion["group_ids"][0],
                        fr,
                        f,
                        suggestion["allocated_at"],
                        "lineage",
                        op,
                        extra={
                            "rule_ids": suggestion["rule_ids"],
                            "acknowledged_rules": rule_signature(active),
                        },
                    )
                    changed = True
        if changed:
            row.revision += 1
    s.flush()


@router.get("/{code}/participants", response_model=ParticipantsOut)
def participants(
    code: str,
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query("", max_length=200),
):
    with Session(request.app.state.engine) as s:
        row = get(s, Experiment, code)
        facts = provenance(s)
        members = list(
            s.scalars(
                select(Member).where(Member.experiment_id == code).order_by(Member.id)
            )
        )
        units = {
            u.id: u for u in s.scalars(select(Unit).where(Unit.experiment_id == code))
        }
        rules = [
            rule_dict(r)
            for r in s.scalars(select(Rule).where(Rule.experiment_id == code))
        ]
        current = latest(s, code)
        active = [
            r for r in rules if r["active"] and r["plan_revision"] == current.revision
        ]
        enrolled = {m.fruiting_id for m in members}
        plans = {
            p.revision: json.loads(p.snapshot)
            for p in s.scalars(select(Plan).where(Plan.experiment_id == code))
        }
        flush_counts = dict(
            s.execute(
                select(FruitingFlush.fruiting_id, func.count()).group_by(
                    FruitingFlush.fruiting_id
                )
            ).all()
        )
        items = []
        for m in members[(page - 1) * 50 : page * 50]:
            unit = units[m.unit_id]
            items.append(
                {
                    **snapshot(m),
                    "group_id": unit.group_id,
                    "unit_kind": unit.kind,
                    "group_name": next(
                        (
                            g["name"]
                            for g in plans[unit.plan_revision]["groups"]
                            if g["id"] == unit.group_id
                        ),
                        unit.group_id,
                    ),
                    "plan_revision": unit.plan_revision,
                    "flush_count": flush_counts.get(m.fruiting_id, 0),
                    "sources": facts[m.fruiting_id],
                }
            )
        candidates = []
        for fr_id, f in facts.items():
            if fr_id in enrolled or q.casefold() not in fr_id.casefold():
                continue
            suggestion = proposal(f, active, row.category)
            candidates.append({**f, "suggestion": suggestion})
        confirmed = [
            m for m in members if json.loads(m.evidence).get("status") != "excluded"
        ]
        classes = {m.classification for m in confirmed}
        return dict(
            items=items,
            total=len(members),
            page=page,
            page_size=50,
            candidates=candidates[(page - 1) * 50 : page * 50],
            candidate_total=len(candidates),
            rules=rules,
            revision=row.revision,
            plan_revision=current.revision,
            counts={
                "containers": len({m.fruiting_id for m in confirmed}),
                "treatment_units": len({m.unit_id for m in confirmed}),
                "known_spawn_sources": len(
                    {
                        src
                        for m in confirmed
                        for src in facts[m.fruiting_id]["spawn_ids"]
                    }
                ),
                "classification_counts": {
                    c: sum(m.classification == c for m in confirmed)
                    for c in ["prospective", "retrospective", "uncertain"]
                },
            },
            classification_summary=(
                next(iter(classes))
                if len(classes) == 1
                else "mixed" if classes else "uncertain"
            ),
            unit_warning="Treatment-unit counts are assignment counts, not proof of statistical independence. Shared sources and repeated flushes are not new trials.",
        )


@router.post("/{code}/enroll", response_model=EnrollmentResult)
def enroll(code: str, data: Enrollment, request: Request):
    def work(s, op):
        row = writable(s, code, data)
        plan = valid_group(s, row, data.plan_revision, data.group_id)
        fr = get(s, FruitingContainer, data.fruiting_id)
        facts = provenance(s)[fr.id]
        if facts["fingerprint"] != data.fingerprint:
            raise HTTPException(409, "Provenance changed; reload before confirming")
        unit = get(s, Unit, data.unit_id) if data.unit_id else None
        warnings = []
        if facts["ambiguous"] or (
            row.category == "genetics" and len(facts["line_ids"]) != 1
        ):
            warnings.append(
                "Mixed or uncertain ancestry: retain for review, not a pure genetic comparison"
            )
        m = add_member(
            s,
            row,
            plan,
            data.group_id,
            fr,
            facts,
            max(unit.allocated_at, unit.recorded_at) if unit else clock(),
            "manual",
            op,
            data.treatment_start,
            data.treatment_date,
            unit,
            extra=(
                {"status": "needs_review", "review_reason": "; ".join(warnings)}
                if warnings
                else None
            ),
        )
        row.revision += 1
        s.flush()
        return dict(membership=snapshot(m), revision=row.revision)

    return execute(request, data, "experiment.enroll:" + code, work)


@router.post("/{code}/source-rules")
def source_rule(code: str, data: SourceRule, request: Request):
    def work(s, op):
        row = writable(s, code, data)
        valid_group(s, row, data.plan_revision, data.group_id)
        if row.category == "conditions":
            raise HTTPException(
                409, "Environmental associations require shared trial units in 2H.3"
            )
        get(
            s,
            {"spawn": Spawn, "physical": PhysicalCulture, "line": CultureLine}[
                data.source_kind
            ],
            data.source_id,
        )
        rule = Rule(
            id=allocate(s, "ER"),
            experiment_id=code,
            plan_revision=data.plan_revision,
            group_id=data.group_id,
            recorded_at=clock(),
            **{data.source_kind + "_id": data.source_id}
        )
        s.add(rule)
        s.flush()
        row.revision += 1
        event(s, row, None, "source_rule", None, rule_dict(rule), data.reason, op)
        synchronize(s, op)
        return dict(rule=rule_dict(rule), revision=row.revision)

    return execute(request, data, "experiment.rule:" + code, work)


@router.post("/{code}/creation-allocations")
def creation_allocation(code: str, data: CreationAllocation, request: Request):
    def work(s, op):
        row = writable(s, code, data)
        if row.category == "conditions":
            raise HTTPException(
                409, "Environmental creation needs shared trial-unit setup in 2H.3"
            )
        get(s, Spawn, data.spawn_id)
        if (
            row.category == "genetics"
            and len({d.group_id for d in data.destinations}) > 1
        ):
            raise HTTPException(
                422,
                "One spawn source has one genetic identity; create it in one genetics group per operation",
            )
        destinations = []
        for d in data.destinations:
            valid_group(s, row, data.plan_revision, d.group_id)
            recipe = get(s, Recipe, d.recipe_id)
            if recipe.recipe_type != "substrate" or recipe.status != "active":
                raise HTTPException(422, "Select active substrate recipes")
            destinations.append({**d.model_dump(), "recipe_revision": recipe.revision})
        allocation = Allocation(
            id=allocate(s, "EA"),
            experiment_id=code,
            plan_revision=data.plan_revision,
            spawn_id=data.spawn_id,
            destinations=json.dumps(destinations),
            recorded_at=clock(),
            operation_id=op.id,
        )
        s.add(allocation)
        row.revision += 1
        s.flush()
        event(
            s,
            row,
            None,
            "creation_allocation",
            None,
            row_dict(allocation),
            data.reason,
            op,
        )
        return dict(allocation=row_dict(allocation), revision=row.revision)

    return execute(request, data, "experiment.allocate:" + code, work)


@router.post("/{code}/fruiting", status_code=201, response_model=CreationResult)
def create(code: str, data: FruitingCreation, request: Request):
    def work(s, op):
        row = writable(s, code, data)
        allocation = get(s, Allocation, data.allocation_id)
        if allocation.experiment_id != code:
            raise HTTPException(422, "Allocation belongs to another experiment")
        if latest(s, code).revision != allocation.plan_revision:
            raise HTTPException(409, "Plan changed; review and save new assignments")
        ds = json.loads(allocation.destinations)
        groups = []
        recipes = []
        for d in ds:
            valid_group(s, row, allocation.plan_revision, d["group_id"])
            recipe = get(s, Recipe, d["recipe_id"])
            if recipe.revision != d["recipe_revision"]:
                raise HTTPException(
                    409, "Recipe changed; review and save new assignments"
                )
            groups += [d["group_id"]] * d["count"]
            recipes += [d["recipe_id"]] * d["count"]
        ordinary = SpawnToBulk(
            request_key=data.request_key,
            spawn_id=allocation.spawn_id,
            recipe_id=recipes[0],
            count=len(recipes),
            spawning_date=data.spawning_date,
            material_type=data.material_type,
        )
        result = create_fruiting(s, op, ordinary, recipes)
        facts = provenance(s)
        plan = s.get(Plan, (code, allocation.plan_revision))
        members = []
        for item, group in zip(result["containers"], groups):
            m = add_member(
                s,
                row,
                plan,
                group,
                s.get(FruitingContainer, item["id"]),
                facts[item["id"]],
                allocation.recorded_at,
                "experiment_creation",
                op,
                data.treatment_start,
                extra={"allocation_id": allocation.id},
            )
            members.append(snapshot(m))
        row.revision += 1
        s.flush()
        return {**result, "memberships": members, "revision": row.revision}

    return execute(request, data, "experiment.fruiting:" + code, work)


@router.post("/{code}/participants/{ident}/review", response_model=EnrollmentResult)
def review(code: str, ident: int, data: Review, request: Request):
    def work(s, op):
        row = get(s, Experiment, code)
        check(row, data.expected_revision)
        if row.archived:
            raise HTTPException(
                409, "Restore the experiment before reviewing historical participation"
            )
        m = get(s, Member, ident)
        if m.experiment_id != code:
            raise HTTPException(404, "Participant not found in experiment")
        facts = provenance(s)[m.fruiting_id]
        if facts["fingerprint"] != data.fingerprint:
            raise HTTPException(409, "Provenance changed; reload before review")
        before = snapshot(m)
        ev = json.loads(m.evidence)
        if data.decision == "reassign":
            if not data.group_id or not data.plan_revision:
                raise HTTPException(
                    422, "Reassignment requires group and plan revision"
                )
            plan = valid_group(s, row, data.plan_revision, data.group_id)
            unit = s.get(Unit, m.unit_id)
            if unit.kind != "container":
                raise HTTPException(
                    409, "Shared treatment units require a trial-level review"
                )
            unit.group_id = data.group_id
            unit.plan_revision = plan.revision
            unit.allocated_at = clock()
            unit.recorded_at = clock()
            ev["group_id"] = data.group_id
            ev["allocated_at"] = unit.allocated_at
            # New allocation is recorded now; never upgrade the old classification.
            candidate = (
                classify(
                    plan.committed_at,
                    [clock()],
                    (
                        datetime.fromisoformat(ev["treatment_start"])
                        if ev.get("timing_precision") == "instant"
                        else (
                            date.fromisoformat(ev["treatment_start"])
                            if ev.get("treatment_start")
                            else None
                        )
                    ),
                    ev.get("timing_precision"),
                )
                if ev.get("treatment_start")
                else "uncertain"
            )
            m.classification = (
                "retrospective"
                if "retrospective" in {m.classification, candidate}
                else "uncertain"
            )
            ev["plan_revision"] = plan.revision
        ev["acknowledged_rules"] = rule_signature(
            [
                rule_dict(r)
                for r in s.scalars(
                    select(Rule).where(
                        Rule.experiment_id == code,
                        Rule.active == 1,
                        Rule.plan_revision == ev.get("plan_revision"),
                    )
                )
            ]
        )
        ev.update(
            status="excluded" if data.decision == "exclude" else "confirmed",
            source_fingerprint=facts["fingerprint"],
            sources=facts,
            review_reason=data.reason,
        )
        if (
            row.category == "genetics"
            and (facts["ambiguous"] or len(facts["line_ids"]) != 1)
            and data.decision != "exclude"
        ):
            ev.update(
                status="needs_review",
                review_reason="Mixed or uncertain ancestry remains unsuitable for a pure genetic comparison",
            )
        m.evidence = json.dumps(ev)
        row.revision += 1
        s.flush()
        event(
            s, row, m, "review_" + data.decision, before, snapshot(m), data.reason, op
        )
        return dict(membership=snapshot(m), revision=row.revision)

    return execute(request, data, "experiment.review:" + code, work)


@router.get("/{code}/enrollment-history")
def history(code: str, request: Request, page: int = Query(1, ge=1)):
    with Session(request.app.state.engine) as s:
        get(s, Experiment, code)
        q = select(Event).where(Event.experiment_id == code)
        return dict(
            items=[
                {
                    **row_dict(e),
                    "before": json.loads(e.before) if e.before else None,
                    "after": json.loads(e.after),
                }
                for e in s.scalars(
                    q.order_by(Event.id.desc()).offset((page - 1) * 50).limit(50)
                )
            ],
            total=s.scalar(select(func.count()).select_from(q.subquery())),
            page=page,
            page_size=50,
        )


@router.post("/{code}/source-rules/{rule_id}/stop")
def stop_rule(code: str, rule_id: str, data: RevisionCommand, request: Request):
    def work(s, op):
        row = writable(s, code, data)
        rule = get(s, Rule, rule_id)
        if rule.experiment_id != code:
            raise HTTPException(404, "Source rule not found in experiment")
        before = rule_dict(rule)
        rule.active = 0
        row.revision += 1
        s.flush()
        event(
            s,
            row,
            None,
            "source_rule_stopped",
            before,
            rule_dict(rule),
            data.reason,
            op,
        )
        synchronize(s, op)
        return dict(revision=row.revision)

    return execute(request, data, "experiment.rule.stop:" + code, work)
