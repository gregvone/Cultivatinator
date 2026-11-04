"""Manual-first ingestion, immutable evaluations and explicit occupancy intervals."""

from datetime import datetime, timezone, timedelta
import json
import math
from typing import Annotated, Literal
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import (
    Field,
    AwareDatetime,
    BeforeValidator,
    field_validator,
    model_validator,
)
from sqlalchemy import select, func, exists, or_
from sqlalchemy.orm import Session, aliased
from .library_schemas import Input, Text, Notes
from .preparation_schemas import Command
from .preparation import execute, get
from .library import allocate
from .fruiting import row_dict
from .models import FruitingContainer
from .environment_models import (
    EnvironmentalProfile as Profile,
    FruitingTent as Tent,
    ProfileAssignment,
    EnvironmentalReading as Reading,
    TentOccupancy as Occupancy,
    EnvironmentAudit as Audit,
    EnvironmentWarning as Warning,
    EnvironmentWarningEvent as WarningEvent,
)

router = APIRouter(prefix="/api/environment", tags=["Environment"])
METRICS = ("temperature_f", "humidity", "co2")
UNITS = {"temperature_f": "°F", "humidity": "% RH", "co2": "ppm"}


def finite_number(value):
    # JSON parsers may accept NaN/Infinity or overflowed exponents. Reject those
    # directly so validation responses never attempt to serialize a nonfinite input.
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(422, "Measurement and target values must be finite numbers")
    return value


Temperature = Annotated[
    float,
    BeforeValidator(finite_number),
    Field(ge=-148, le=212, allow_inf_nan=False, strict=True),
]
Humidity = Annotated[
    float,
    BeforeValidator(finite_number),
    Field(ge=0, le=100, allow_inf_nan=False, strict=True),
]
CO2 = Annotated[
    float,
    BeforeValidator(finite_number),
    Field(ge=0, le=1000000, allow_inf_nan=False, strict=True),
]
Name = Annotated[Text, Field(min_length=1)]


def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def clock():
    return utc(datetime.now(timezone.utc))


class Targets(Input):
    temperature_f_min: Temperature | None = None
    temperature_f_max: Temperature | None = None
    humidity_min: Humidity | None = None
    humidity_max: Humidity | None = None
    co2_min: CO2 | None = None
    co2_max: CO2 | None = None

    @model_validator(mode="after")
    def ranges(self):
        for metric in METRICS:
            low, high = getattr(self, metric + "_min"), getattr(self, metric + "_max")
            if low is not None and high is not None and low > high:
                raise ValueError(f"{metric}: minimum must not exceed maximum")
        return self


class ProfileData(Command):
    name: Name
    species: Text | None = None
    targets: Targets = Field(default_factory=Targets)
    notes: Notes | None = None
    status: Literal["active", "archived"] = "active"


class ProfileEdit(ProfileData):
    expected_revision: int = Field(ge=1)


class TentData(Command):
    name: Name
    description: Notes | None = None
    status: Literal["active", "archived"] = "active"


class TentEdit(TentData):
    expected_revision: int = Field(ge=1)


class AssignProfile(Command):
    profile_id: Text | None
    expected_revision: int = Field(ge=1)


class ReadingData(Command):
    observed_at: AwareDatetime
    temperature_f: Temperature
    humidity: Humidity
    co2: CO2 | None = None
    humidifier: int | None = Field(default=None, ge=0, le=10, strict=True)
    fan: int | None = Field(default=None, ge=0, le=10, strict=True)
    notes: Notes | None = None

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        if value.year < 1900 or value > datetime.now(timezone.utc) + timedelta(
            minutes=5
        ):
            raise ValueError(
                "Observation must be between 1900 and the present (5 minute clock tolerance)"
            )
        return value


class Correction(ReadingData):
    reason: Annotated[Notes, Field(min_length=1)]


class OccupancyData(Command):
    fruiting_id: Text
    entered_at: AwareDatetime
    left_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def dates(self):
        for value in (self.entered_at, self.left_at):
            if value is not None:
                ReadingData.timestamp(value)
        if self.left_at is not None and self.left_at <= self.entered_at:
            raise ValueError("Removal must be after entry")
        return self


class OccupancyEdit(OccupancyData):
    expected_revision: int = Field(ge=1)
    reason: Annotated[Notes, Field(min_length=1)]


def revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, "Record changed; reload before saving")


def audit(s, op, row, before=None, reason=None):
    s.flush()
    s.add(
        Audit(
            entity_type=row.__tablename__,
            entity_id=str(row.id),
            operation_id=op.id,
            before=json.dumps(before) if before else None,
            after=json.dumps(row_dict(row)),
            reason=reason,
        )
    )


def profile_out(row):
    return {**row_dict(row), "targets": json.loads(row.targets)}


def snapshot(profile):
    return (
        profile_out(profile) if profile else {"id": None, "name": None, "targets": {}}
    )


def assign(s, tent, profile):
    s.add(
        ProfileAssignment(
            tent_id=tent.id,
            profile_id=profile.id if profile else None,
            assigned_at=clock(),
            snapshot=json.dumps(snapshot(profile)),
        )
    )


def applicable(s, tent_id, observed_at):
    row = s.scalar(
        select(ProfileAssignment)
        .where(
            ProfileAssignment.tent_id == tent_id,
            ProfileAssignment.assigned_at <= observed_at,
        )
        .order_by(ProfileAssignment.assigned_at.desc(), ProfileAssignment.id.desc())
        .limit(1)
    )
    return json.loads(row.snapshot) if row else snapshot(None)


def evaluate(data, limits):
    result = {}
    for metric in METRICS:
        value = getattr(data, metric)
        low, high = limits.get(metric + "_min"), limits.get(metric + "_max")
        if value is None or low is None and high is None:
            continue
        result[metric] = (
            "low"
            if low is not None and value < low
            else "high" if high is not None and value > high else "normal"
        )
    return result


def valid_readings():
    correction = aliased(Reading)
    return select(Reading).where(
        ~exists(select(correction.id).where(correction.replaces_id == Reading.id))
    )


def warning_state(s, tent_id, op):
    # Three indexed, bounded queries: latest applicable observation per metric.
    # A missing value/target cannot clear another observation's warning.
    for metric in METRICS:
        query = valid_readings().where(
            Reading.tent_id == tent_id,
            func.json_extract(Reading.evaluations, "$." + metric).is_not(None),
        )
        latest = s.scalar(
            query.order_by(Reading.observed_at.desc(), Reading.id.desc()).limit(1)
        )
        state = json.loads(latest.evaluations)[metric] if latest else "unconfigured"
        existing = s.get(Warning, (tent_id, metric))
        after = {"state": state, "reading_id": latest.id if latest else None}
        before = (
            {"state": existing.state, "reading_id": existing.reading_id}
            if existing
            else None
        )
        if before == after or existing is None and latest is None:
            continue
        s.add(
            WarningEvent(
                tent_id=tent_id,
                metric=metric,
                operation_id=op.id,
                before=json.dumps(before) if before else None,
                after=json.dumps(after),
            )
        )
        if latest:
            if existing:
                existing.state, existing.reading_id = state, latest.id
            else:
                s.add(
                    Warning(
                        tent_id=tent_id,
                        metric=metric,
                        state=state,
                        reading_id=latest.id,
                    )
                )
        elif existing:
            s.delete(existing)


def reading_out(s, row, occupants=False):
    result = {
        **row_dict(row),
        "snapshot": json.loads(row.snapshot),
        "evaluations": json.loads(row.evaluations),
    }
    result["superseded_by"] = s.scalar(
        select(Reading.id).where(Reading.replaces_id == row.id)
    )
    if occupants:
        result["fruiting_ids"] = list(
            s.scalars(
                select(Occupancy.fruiting_id).where(
                    Occupancy.tent_id == row.tent_id,
                    Occupancy.entered_at <= row.observed_at,
                    or_(
                        Occupancy.left_at.is_(None), Occupancy.left_at > row.observed_at
                    ),
                )
            )
        )
    return result


def warnings(s, tent_id=None):
    q = (
        select(Warning, Tent, Reading)
        .join(Tent, Tent.id == Warning.tent_id)
        .join(Reading, Reading.id == Warning.reading_id)
        .where(Warning.state.in_(["low", "high"]))
    )
    if tent_id:
        q = q.where(Tent.id == tent_id)
    return [
        dict(
            tent_id=t.id,
            tent_name=t.name,
            archived=t.status == "archived",
            metric=w.metric,
            state=w.state,
            reading_id=r.id,
            value=getattr(r, w.metric),
            unit=UNITS[w.metric],
            observed_at=r.observed_at,
            snapshot=json.loads(r.snapshot),
        )
        for w, t, r in s.execute(q.order_by(Tent.id, Warning.metric))
    ]


def attention(s):
    return [
        dict(
            record_id=w["tent_id"],
            title=w["tent_name"],
            target="/environment?tent=" + w["tent_id"],
            archived=w["archived"],
            stage=None,
            alert_id=f"environment:{w['tent_id']}:{w['metric']}",
            rule="environment",
            category="Environmental warning",
            severity="warning",
            recorded_date=w["observed_at"],
            elapsed_days=None,
            description=f"{w['metric'].replace('_f','').replace('_',' ').title()} recorded {w['state']}: {w['value']:g} {w['unit']}. Warning persists until a newer applicable measurement is within range.",
        )
        for w in warnings(s)
    ]


@router.get("/profiles")
def profiles(request: Request):
    with Session(request.app.state.engine) as s:
        return [
            profile_out(r)
            for r in s.scalars(select(Profile).order_by(Profile.name, Profile.id))
        ]


@router.post("/profiles")
def create_profile(data: ProfileData, request: Request):
    def work(s, op):
        row = Profile(
            id=allocate(s, "EP"),
            **data.model_dump(exclude={"request_key", "targets"}),
            targets=data.targets.model_dump_json(),
        )
        s.add(row)
        audit(s, op, row)
        return profile_out(row)

    return execute(request, data, "environment.profile.create", work)


@router.put("/profiles/{code}")
def edit_profile(code: str, data: ProfileEdit, request: Request):
    def work(s, op):
        row = get(s, Profile, code)
        revision(row, data.expected_revision)
        before = row_dict(row)
        for k, v in data.model_dump(
            exclude={"request_key", "expected_revision", "targets"}
        ).items():
            setattr(row, k, v)
        row.targets = data.targets.model_dump_json()
        row.revision += 1
        audit(s, op, row, before)
        # Profile edits become effective now; old observations keep old limits.
        for tent in s.scalars(select(Tent).where(Tent.profile_id == code)):
            assign(s, tent, row)
        return profile_out(row)

    return execute(request, data, "environment.profile.edit:" + code, work)


@router.get("/tents")
def tents(request: Request):
    with Session(request.app.state.engine) as s:
        return [
            row_dict(r) for r in s.scalars(select(Tent).order_by(Tent.name, Tent.id))
        ]


@router.post("/tents")
def create_tent(data: TentData, request: Request):
    def work(s, op):
        row = Tent(id=allocate(s, "ET"), **data.model_dump(exclude={"request_key"}))
        s.add(row)
        audit(s, op, row)
        return row_dict(row)

    return execute(request, data, "environment.tent.create", work)


@router.put("/tents/{code}")
def edit_tent(code: str, data: TentEdit, request: Request):
    def work(s, op):
        row = get(s, Tent, code)
        revision(row, data.expected_revision)
        before = row_dict(row)
        for k, v in data.model_dump(
            exclude={"request_key", "expected_revision"}
        ).items():
            setattr(row, k, v)
        row.revision += 1
        audit(s, op, row, before)
        return row_dict(row)

    return execute(request, data, "environment.tent.edit:" + code, work)


@router.post("/tents/{code}/profile")
def set_profile(code: str, data: AssignProfile, request: Request):
    def work(s, op):
        tent = get(s, Tent, code)
        revision(tent, data.expected_revision)
        p = get(s, Profile, data.profile_id) if data.profile_id else None
        if p and p.status != "active":
            raise HTTPException(409, "Choose an active profile")
        before = row_dict(tent)
        tent.profile_id = p.id if p else None
        tent.revision += 1
        assign(s, tent, p)
        audit(s, op, tent, before)
        return row_dict(tent)

    return execute(request, data, "environment.profile.assign:" + code, work)


@router.get("/tents/{code}/overview")
def overview(code: str, request: Request):
    with Session(request.app.state.engine) as s:
        tent = get(s, Tent, code)
        latest = {}
        for metric in METRICS:
            row = s.scalar(
                valid_readings()
                .where(Reading.tent_id == code, getattr(Reading, metric).is_not(None))
                .order_by(Reading.observed_at.desc(), Reading.id.desc())
                .limit(1)
            )
            latest[metric] = (
                {"value": getattr(row, metric), "observed_at": row.observed_at}
                if row
                else None
            )
        at = clock()
        count = s.scalar(
            select(func.count())
            .select_from(Occupancy)
            .where(
                Occupancy.tent_id == code,
                Occupancy.entered_at <= at,
                or_(Occupancy.left_at.is_(None), Occupancy.left_at > at),
            )
        )
        return dict(
            tent=row_dict(tent),
            profile=(
                profile_out(s.get(Profile, tent.profile_id))
                if tent.profile_id
                else None
            ),
            latest=latest,
            warnings=warnings(s, code),
            occupancy_count=count,
        )


@router.post("/tents/{code}/readings")
def add_reading(code: str, data: ReadingData, request: Request):
    return ingest(code, data, request)


def ingest(code, data, request, original_id=None):
    def work(s, op):
        tent = get(s, Tent, code)
        if tent.status != "active" and original_id is None:
            raise HTTPException(409, "Restore tent before recording new readings")
        original = get(s, Reading, original_id) if original_id else None
        if original and original.tent_id != code:
            raise HTTPException(404, "Reading not found in this tent")
        if original and s.scalar(
            select(Reading.id).where(Reading.replaces_id == original.id)
        ):
            raise HTTPException(
                409, "Reading was already corrected; correct its replacement"
            )
        observed = utc(data.observed_at)
        snap = (
            json.loads(original.snapshot) if original else applicable(s, code, observed)
        )
        row = Reading(
            tent_id=code,
            **data.model_dump(exclude={"request_key", "observed_at", "reason"}),
            observed_at=observed,
            created_at=clock(),
            snapshot=json.dumps(snap),
            profile_id=snap["id"],
            evaluations=json.dumps(evaluate(data, snap["targets"])),
            replaces_id=original_id,
            correction_reason=getattr(data, "reason", None),
        )
        s.add(row)
        s.flush()
        warning_state(s, code, op)
        audit(s, op, row, reason=getattr(data, "reason", None))
        return reading_out(s, row, True)

    return execute(
        request, data, "environment.reading:" + code + ":" + str(original_id), work
    )


@router.post("/tents/{code}/readings/{reading_id}/correct")
def correct_reading(code: str, reading_id: int, data: Correction, request: Request):
    return ingest(code, data, request, reading_id)


@router.get("/tents/{code}/readings")
def reading_history(
    code: str,
    request: Request,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    page: int = Query(1, ge=1, le=1000000),
    page_size: int = Query(100, ge=1, le=500),
):
    if start and end and start > end:
        raise HTTPException(422, "Start must precede end")
    with Session(request.app.state.engine) as s:
        get(s, Tent, code)
        q = select(Reading).where(Reading.tent_id == code)
        if start:
            q = q.where(Reading.observed_at >= utc(start))
        if end:
            q = q.where(Reading.observed_at <= utc(end))
        total = s.scalar(select(func.count()).select_from(q.subquery()))
        rows = s.scalars(
            q.order_by(Reading.observed_at.desc(), Reading.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        # Bounded history; batch correlate occupancy and corrections, no per-point queries.
        occupants = (
            list(
                s.scalars(
                    select(Occupancy).where(
                        Occupancy.tent_id == code,
                        Occupancy.entered_at
                        <= max((r.observed_at for r in rows), default=""),
                        or_(
                            Occupancy.left_at.is_(None),
                            Occupancy.left_at
                            > min((r.observed_at for r in rows), default=""),
                        ),
                    )
                )
            )
            if rows
            else []
        )
        replaced = dict(
            s.execute(
                select(Reading.replaces_id, Reading.id).where(
                    Reading.replaces_id.in_([r.id for r in rows])
                )
            ).all()
        )
        items = []
        for r in rows:
            item = {
                **row_dict(r),
                "snapshot": json.loads(r.snapshot),
                "evaluations": json.loads(r.evaluations),
                "superseded_by": replaced.get(r.id),
                "fruiting_ids": [
                    o.fruiting_id
                    for o in occupants
                    if o.entered_at <= r.observed_at
                    and (o.left_at is None or r.observed_at < o.left_at)
                ],
            }
            items.append(item)
        return dict(items=items, total=total, page=page, page_size=page_size)


@router.get("/tents/{code}/history")
def alert_history(code: str, request: Request, page: int = Query(1, ge=1, le=1000000)):
    with Session(request.app.state.engine) as s:
        get(s, Tent, code)
        q = select(WarningEvent).where(WarningEvent.tent_id == code)
        return dict(
            items=[
                {
                    **row_dict(r),
                    "before": json.loads(r.before) if r.before else None,
                    "after": json.loads(r.after),
                }
                for r in s.scalars(
                    q.order_by(WarningEvent.id.desc()).offset((page - 1) * 50).limit(50)
                )
            ],
            total=s.scalar(select(func.count()).select_from(q.subquery())),
            page=page,
            page_size=50,
            assignments=[
                {**row_dict(a), "snapshot": json.loads(a.snapshot)}
                for a in s.scalars(
                    select(ProfileAssignment)
                    .where(ProfileAssignment.tent_id == code)
                    .order_by(ProfileAssignment.id.desc())
                    .limit(100)
                )
            ],
        )


@router.get("/containers")
def containers(
    request: Request,
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1, le=1000000),
):
    with Session(request.app.state.engine) as s:
        from .dashboard import records

        ids = list(
            s.scalars(
                select(FruitingContainer.id)
                .where(FruitingContainer.id.contains(q, autoescape=True))
                .order_by(FruitingContainer.id)
                .offset((page - 1) * 50)
                .limit(50)
            )
        )
        return [
            dict(id=r["record_id"], title=r["title"])
            for r in records(s, {"fruiting": set(ids)}, archived=True).values()
        ]


@router.get("/occupancy")
def occupancy(
    request: Request,
    tent_id: str | None = None,
    fruiting_id: str | None = None,
    page: int = Query(1, ge=1, le=1000000),
):
    with Session(request.app.state.engine) as s:
        q = select(Occupancy, Tent.name).join(Tent, Tent.id == Occupancy.tent_id)
        if tent_id:
            q = q.where(Occupancy.tent_id == tent_id)
        if fruiting_id:
            q = q.where(Occupancy.fruiting_id == fruiting_id)
        total = s.scalar(select(func.count()).select_from(q.subquery()))
        return dict(
            items=[
                {**row_dict(o), "tent_name": name}
                for o, name in s.execute(
                    q.order_by(Occupancy.entered_at.desc(), Occupancy.id.desc())
                    .offset((page - 1) * 50)
                    .limit(50)
                )
            ],
            total=total,
            page=page,
            page_size=50,
        )


def save_occupancy(s, op, tent, data, ident=None):
    get(s, FruitingContainer, data.fruiting_id)
    row = get(s, Occupancy, ident) if ident else None
    if row and (row.tent_id != tent.id or row.fruiting_id != data.fruiting_id):
        raise HTTPException(
            409, "Occupancy identity is permanent; create a new interval for a move"
        )
    if row:
        revision(row, data.expected_revision)
    entered, left = utc(data.entered_at), utc(data.left_at) if data.left_at else None
    overlap = select(Occupancy.id).where(
        Occupancy.fruiting_id == data.fruiting_id,
        or_(Occupancy.left_at.is_(None), Occupancy.left_at > entered),
    )
    if left:
        overlap = overlap.where(Occupancy.entered_at < left)
    if row:
        overlap = overlap.where(Occupancy.id != row.id)
    if s.scalar(overlap.limit(1)):
        raise HTTPException(
            409, "This container already occupies a tent during that interval"
        )
    before = row_dict(row) if row else None
    if not row:
        if tent.status != "active":
            raise HTTPException(409, "Restore tent before assigning occupancy")
        row = Occupancy(
            tent_id=tent.id,
            fruiting_id=data.fruiting_id,
            entered_at=entered,
            left_at=left,
        )
        s.add(row)
    else:
        row.entered_at, row.left_at, row.revision = entered, left, row.revision + 1
    audit(s, op, row, before, getattr(data, "reason", None))
    return row_dict(row)


@router.post("/tents/{code}/occupancy")
def add_occupancy(code: str, data: OccupancyData, request: Request):
    return execute(
        request,
        data,
        "environment.occupancy.create:" + code,
        lambda s, op: save_occupancy(s, op, get(s, Tent, code), data),
    )


@router.put("/tents/{code}/occupancy/{ident}")
def edit_occupancy(code: str, ident: int, data: OccupancyEdit, request: Request):
    return execute(
        request,
        data,
        "environment.occupancy.edit:" + str(ident),
        lambda s, op: save_occupancy(s, op, get(s, Tent, code), data, ident),
    )


@router.get("/audit/{entity_type}/{entity_id}")
def audit_history(
    entity_type: str,
    entity_id: str,
    request: Request,
    page: int = Query(1, ge=1, le=1000000),
):
    with Session(request.app.state.engine) as s:
        q = select(Audit).where(
            Audit.entity_type == entity_type, Audit.entity_id == entity_id
        )
        return dict(
            items=[
                {
                    **row_dict(a),
                    "before": json.loads(a.before) if a.before else None,
                    "after": json.loads(a.after),
                }
                for a in s.scalars(
                    q.order_by(Audit.id.desc()).offset((page - 1) * 50).limit(50)
                )
            ],
            total=s.scalar(select(func.count()).select_from(q.subquery())),
            page=page,
            page_size=50,
        )


@router.get("/containers/{code}/readings")
def container_readings(
    code: str, request: Request, page: int = Query(1, ge=1, le=1000000)
):
    with Session(request.app.state.engine) as s:
        get(s, FruitingContainer, code)
        q = valid_readings().where(
            exists(
                select(Occupancy.id).where(
                    Occupancy.fruiting_id == code,
                    Occupancy.tent_id == Reading.tent_id,
                    Occupancy.entered_at <= Reading.observed_at,
                    or_(
                        Occupancy.left_at.is_(None),
                        Occupancy.left_at > Reading.observed_at,
                    ),
                )
            )
        )
        rows = s.scalars(
            q.order_by(Reading.observed_at.desc(), Reading.id.desc())
            .offset((page - 1) * 50)
            .limit(50)
        )
        return dict(
            items=[
                {
                    **row_dict(r),
                    "snapshot": json.loads(r.snapshot),
                    "evaluations": json.loads(r.evaluations),
                    "superseded_by": None,
                    "fruiting_ids": [code],
                }
                for r in rows
            ],
            total=s.scalar(select(func.count()).select_from(q.subquery())),
            page=page,
            page_size=50,
        )
