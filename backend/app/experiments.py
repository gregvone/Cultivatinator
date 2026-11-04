"""Experiment plan commands. No cultivation/occupancy mutation occurs here."""

import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .preparation import execute, get
from .library import allocate
from .fruiting import row_dict
from .experiment_models import (
    Experiment,
    ExperimentGroup,
    ExperimentPlanRevision as Revision,
    ExperimentAudit as Audit,
    ExperimentUnit,
)
from .experiment_schemas import (
    CreateExperiment,
    EditPlan,
    Action,
    ExperimentOut,
    ExperimentPage,
    HistoryPage,
)

router = APIRouter(prefix="/api/experiments", tags=["Experiments"])


def clock():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def latest(s, code):
    return s.scalar(
        select(Revision)
        .where(Revision.experiment_id == code)
        .order_by(Revision.revision.desc())
        .limit(1)
    )


def output(s, row):
    plan = latest(s, row.id)
    return {
        **row_dict(row),
        "plan": json.loads(plan.snapshot),
        "plan_revision": plan.revision,
        "post_start_amendment": row.start_plan_revision is not None
        and plan.revision != row.start_plan_revision,
        "classification_basis": "Timing of committed plan and recorded treatment-unit allocations; no independent replication claim. Missing allocations remain uncertain.",
    }


def check(row, expected):
    if row.revision != expected:
        raise HTTPException(409, "Experiment changed; reload before editing")


def audit(s, op, row, action, before, reason):
    after = output(s, row)
    s.add(
        Audit(
            experiment_id=row.id,
            operation_id=op.id,
            recorded_at=clock(),
            action=action,
            before=json.dumps(before) if before else None,
            after=json.dumps(after),
            reason=reason,
        )
    )
    return after


def save_plan(s, op, row, plan, reason, committed):
    snap = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
    for group in snap["groups"]:
        if group.get("id"):
            record = s.get(ExperimentGroup, group["id"])
            if not record or record.experiment_id != row.id:
                raise HTTPException(422, "Group does not belong to this experiment")
        else:
            group["id"] = allocate(s, "EG")
            s.add(ExperimentGroup(id=group["id"], experiment_id=row.id))
    timestamp = clock()
    s.add(
        Revision(
            experiment_id=row.id,
            revision=row.revision,
            snapshot=json.dumps(snap),
            recorded_at=timestamp,
            committed_at=timestamp if committed else None,
            allocation_committed_at=None,
            reason=reason,
            operation_id=op.id,
        )
    )
    s.flush()


def classify(committed_at, allocations, treatment, precision):
    """Unknown unit identity/allocation cannot be replaced with a free-text schedule."""
    if precision == "date":
        # No timezone is known. Only classify retrospective when commitment is
        # later than every possible instant on that date (UTC-14 through UTC+14).
        end = datetime.combine(
            treatment, datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(hours=38)
        return (
            "retrospective"
            if committed_at and datetime.fromisoformat(committed_at) > end
            else "uncertain"
        )
    evidence = [committed_at, *allocations]
    known = [datetime.fromisoformat(t) for t in evidence if t]
    if any(t >= treatment for t in known):
        return "retrospective" if any(t > treatment for t in known) else "uncertain"
    if not committed_at or not allocations or any(t is None for t in allocations):
        return "uncertain"
    return "prospective"


@router.get("", response_model=ExperimentPage)
def listing(request: Request, page: int = Query(1, ge=1, le=1000000)):
    with Session(request.app.state.engine) as s:
        rows = s.scalars(
            select(Experiment)
            .order_by(Experiment.created_at.desc(), Experiment.id)
            .offset((page - 1) * 50)
            .limit(50)
        )
        return dict(
            items=[output(s, r) for r in rows],
            total=s.scalar(select(func.count()).select_from(Experiment)),
            page=page,
            page_size=50,
        )


@router.post(
    "/", response_model=ExperimentOut, status_code=201, include_in_schema=False
)
@router.post("", response_model=ExperimentOut, status_code=201)
def create(data: CreateExperiment, request: Request):
    def work(s, op):
        if any(g.id for g in data.plan.groups):
            raise HTTPException(422, "New experiment groups cannot have existing IDs")
        row = Experiment(
            id=allocate(s, "EX"),
            category=data.plan.category,
            created_at=clock(),
            revision=1,
        )
        s.add(row)
        s.flush()
        save_plan(s, op, row, data.plan, "Created draft", False)
        return audit(s, op, row, "create", None, "Created draft")

    return execute(request, data, "experiment.create", work)


@router.get("/{code}", response_model=ExperimentOut)
def detail(code: str, request: Request):
    with Session(request.app.state.engine) as s:
        return output(s, get(s, Experiment, code))


@router.post("/{code}/plan-revisions", response_model=ExperimentOut)
def edit(code: str, data: EditPlan, request: Request):
    def work(s, op):
        row = get(s, Experiment, code)
        check(row, data.expected_revision)
        if row.archived or row.state in {"completed", "cancelled"}:
            raise HTTPException(
                409, "Restore or use a nonterminal experiment before editing"
            )
        if data.plan.category != row.category:
            raise HTTPException(
                422, "Experiment category is permanent; create a separate experiment"
            )
        before = output(s, row)
        row.revision += 1
        save_plan(s, op, row, data.plan, data.reason, row.state != "draft")
        return audit(s, op, row, "plan_revision", before, data.reason)

    return execute(request, data, "experiment.plan:" + code, work)


@router.post("/{code}/actions", response_model=ExperimentOut)
def action(code: str, data: Action, request: Request):
    def work(s, op):
        row = get(s, Experiment, code)
        check(row, data.expected_revision)
        before = output(s, row)
        if data.action == "restore":
            if not row.archived:
                raise HTTPException(409, "Experiment is not archived")
            row.archived = 0
        elif data.action == "archive":
            if row.archived:
                raise HTTPException(409, "Experiment is already archived")
            row.archived = 1
        else:
            if row.archived:
                raise HTTPException(409, "Restore experiment first")
            allowed = {
                "plan": {"draft"},
                "start": {"planned"},
                "complete": {"running"},
                "cancel": {"draft", "planned", "running"},
            }
            if row.state not in allowed[data.action]:
                raise HTTPException(409, "This lifecycle transition is unavailable")
            if data.action == "plan":
                row.state = "planned"
                row.revision += 1
                save_plan(s, op, row, before["plan"], data.reason, True)
                return audit(s, op, row, "plan", before, data.reason)
            if data.action == "start":
                plan = latest(s, code)
                row.started_at = clock()
                row.timing_precision = "instant" if data.treatment_start else "date"
                row.treatment_start = (
                    data.treatment_start.astimezone(timezone.utc).isoformat(
                        timespec="microseconds"
                    )
                    if data.treatment_start
                    else data.treatment_date.isoformat()
                )
                if (
                    data.treatment_start
                    and data.treatment_start > datetime.fromisoformat(row.started_at)
                ):
                    raise HTTPException(
                        422,
                        "Start records an actual treatment; use Planned for future treatments",
                    )
                if (
                    data.treatment_date
                    and data.treatment_date
                    > datetime.fromisoformat(row.started_at).date()
                ) or row.treatment_start[:4] < "1900":
                    raise HTTPException(422, "Treatment must be between 1900 and now")
                units = list(
                    s.scalars(
                        select(ExperimentUnit).where(
                            ExperimentUnit.experiment_id == code,
                            ExperimentUnit.plan_revision == plan.revision,
                        )
                    )
                )
                group_ids = {g["id"] for g in before["plan"]["groups"]}
                complete_allocation = group_ids.issubset({u.group_id for u in units})
                row.classification = classify(
                    plan.committed_at,
                    (
                        [max(u.allocated_at, u.recorded_at) for u in units]
                        if complete_allocation
                        else [None]
                    ),
                    data.treatment_start or data.treatment_date,
                    row.timing_precision,
                )
                row.start_plan_revision = plan.revision
            row.state = {
                "start": "running",
                "complete": "completed",
                "cancel": "cancelled",
            }[data.action]
        row.revision += 1
        s.flush()
        return audit(s, op, row, data.action, before, data.reason)

    return execute(request, data, "experiment.action:" + code, work)


@router.get("/{code}/history", response_model=HistoryPage)
def history(code: str, request: Request, page: int = Query(1, ge=1, le=1000000)):
    with Session(request.app.state.engine) as s:
        get(s, Experiment, code)
        plans = select(Revision).where(Revision.experiment_id == code)
        audits = select(Audit).where(Audit.experiment_id == code)
        return dict(
            plans=[
                {**row_dict(r), "snapshot": json.loads(r.snapshot)}
                for r in s.scalars(
                    plans.order_by(Revision.revision.desc())
                    .offset((page - 1) * 50)
                    .limit(50)
                )
            ],
            audits=[
                {
                    **row_dict(r),
                    "before": json.loads(r.before) if r.before else None,
                    "after": json.loads(r.after),
                }
                for r in s.scalars(
                    audits.order_by(Audit.id.desc()).offset((page - 1) * 50).limit(50)
                )
            ],
            plan_total=s.scalar(select(func.count()).select_from(plans.subquery())),
            audit_total=s.scalar(select(func.count()).select_from(audits.subquery())),
            page=page,
            page_size=50,
        )
