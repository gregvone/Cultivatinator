"""Typed library endpoints and atomic acquisition workflows."""

from contextlib import contextmanager
from datetime import date
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import (
    ActivityEvent,
    Spawn,
    GrowBatch,
    FruitingContainer,
    LineOrigin,
    CultureLine,
    IdentitySequence,
    PhotoAttachment,
    PhysicalCulture,
    SporeSource,
    Strain,
)
from .provenance_sources import fruiting_strain_identity
from .library_schemas import (
    ActivityOut,
    EditRecord,
    Kind,
    PhotoOut,
    ReceiveCulture,
    ReceiveResult,
    RecordOut,
    SporeInput,
    StatusInput,
    StrainInput,
    normalized,
)

router = APIRouter(prefix="/api/library", tags=["Culture Library"])
MODELS = {
    "strains": Strain,
    "lines": CultureLine,
    "spores": SporeSource,
    "physical": PhysicalCulture,
    "spawn": Spawn,
    "batches": GrowBatch,
    "fruiting": FruitingContainer,
}
OWNER = {
    "strains": "strain_id",
    "lines": "line_id",
    "spores": "spore_id",
    "physical": "physical_id",
    "spawn": "spawn_id",
    "batches": "batch_id",
    "fruiting": "fruiting_id",
}
PREFIX = {
    "lc_syringe": "LC",
    "lc_jar": "LC",
    "agar_plate": "AG",
    "slant": "SL",
    "other_culture": "PC",
}


@contextmanager
def transaction(request):
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        try:
            with session.begin():
                # SQLite has one writer. Lock before reads to serialize identity,
                # cover and relationship decisions, including concurrent requests.
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                yield session
        except IntegrityError as exc:
            raise HTTPException(
                409,
                "Conflicting record. Strain names must be unique, including archived names.",
            ) from exc


def allocate(session, prefix):
    statement = insert(IdentitySequence).values(prefix=prefix, value=1)
    number = session.scalar(
        statement.on_conflict_do_update(
            index_elements=["prefix"], set_={"value": IdentitySequence.value + 1}
        ).returning(IdentitySequence.value)
    )
    return f"{prefix}-{number:04d}"


def record(session, kind, code, active=False):
    result = session.get(MODELS[kind], code)
    if result is None:
        raise HTTPException(404, "Record not found")
    if active and result.status != "active":
        raise HTTPException(409, "Restore the archived record before selecting it")
    return result


def event(session, kind, code, action, description):
    session.add(
        ActivityEvent(**{OWNER[kind]: code}, event_type=action, description=description)
    )


def photo_out(photo):
    return PhotoOut(
        id=photo.id,
        is_cover=bool(photo.is_cover),
        url=f"/api/library/photos/{photo.id}/original",
        thumbnail_url=f"/api/library/photos/{photo.id}/thumbnail",
    )


def output(session, kind, row):
    values = {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns
        if c.name != "normalized_name"
    }
    values["kind"] = kind
    strain_id = values.get("strain_id")
    if kind in ("physical", "spawn"):
        line = session.get(CultureLine, row.line_id)
        strain_id = line.strain_id
        if kind == "physical":
            values["supplier"] = line.supplier
            values["supplier_reference"] = line.supplier_reference
        values["strain_id"] = strain_id
    if strain_id:
        values["strain_name"] = session.get(Strain, strain_id).name
    if kind == "fruiting":
        values.update(fruiting_strain_identity(session, row))
    cover = session.scalar(
        select(PhotoAttachment).where(
            getattr(PhotoAttachment, OWNER[kind]) == row.id,
            PhotoAttachment.is_cover == 1,
        )
    )
    values["cover"] = photo_out(cover) if cover else None
    if kind == "strains":
        values["line_count"] = session.scalar(
            select(func.count())
            .select_from(CultureLine)
            .where(CultureLine.strain_id == row.id)
        )
        values["spore_count"] = session.scalar(
            select(func.count())
            .select_from(SporeSource)
            .where(SporeSource.strain_id == row.id)
        )
        values["physical_count"] = session.scalar(
            select(func.count())
            .select_from(PhysicalCulture)
            .join(CultureLine, PhysicalCulture.line_id == CultureLine.id)
            .where(CultureLine.strain_id == row.id)
        )
    return RecordOut(**values)


def create_strain(session, data):
    values = data.model_dump()
    strain = Strain(
        id=allocate(session, "STR"), normalized_name=normalized(data.name), **values
    )
    session.add(strain)
    session.flush()
    event(session, "strains", strain.id, "created", "Strain catalog entry created")
    return strain


def resolve_strain(session, strain_id, inline):
    if inline:
        return create_strain(session, inline).id
    if strain_id:
        record(session, "strains", strain_id, active=True)
    return strain_id


@router.post("/strains", response_model=RecordOut, status_code=201)
def add_strain(data: StrainInput, request: Request):
    with transaction(request) as session:
        return output(session, "strains", create_strain(session, data))


@router.post("/receive-culture", response_model=ReceiveResult, status_code=201)
def receive_culture(data: ReceiveCulture, request: Request):
    with transaction(request) as session:
        strain_id = resolve_strain(session, data.strain_id, data.inline_strain)
        if data.existing_line_id:
            line = record(session, "lines", data.existing_line_id, active=True)
            if line.strain_id != strain_id:
                raise HTTPException(
                    422,
                    "Culture line must belong to the selected strain (or both must be unknown)",
                )
        else:
            values = data.line.model_dump(mode="json")
            line = CultureLine(
                id=allocate(session, "CL"), strain_id=strain_id, **values
            )
            session.add(line)
            session.flush()
            session.add(LineOrigin(line_id=line.id, origin_type="external"))
            event(
                session,
                "lines",
                line.id,
                "created",
                "Independent acquired culture line registered",
            )
        physical = []
        if data.material:
            material = data.material.model_dump(exclude={"count"})
            batch = str(uuid4())
            for _ in range(data.material.count):
                item = PhysicalCulture(
                    id=allocate(session, PREFIX[data.material.material_type]),
                    line_id=line.id,
                    acquisition_date=line.acquisition_date,
                    registration_batch=batch,
                    **material,
                )
                session.add(item)
                session.flush()
                event(
                    session,
                    "physical",
                    item.id,
                    "created",
                    f"Physical culture registered under {line.id}; quantity is a starting quantity",
                )
                physical.append(output(session, "physical", item))
            event(
                session,
                "lines",
                line.id,
                "material_registered",
                f"{len(physical)} physical culture container(s) registered",
            )
        return ReceiveResult(line=output(session, "lines", line), physical=physical)


@router.post("/spores", response_model=RecordOut, status_code=201)
def add_spores(data: SporeInput, request: Request):
    with transaction(request) as session:
        strain_id = resolve_strain(session, data.strain_id, data.inline_strain)
        values = data.model_dump(exclude={"inline_strain", "strain_id"})
        if isinstance(values["acquisition_date"], date):
            values["acquisition_date"] = values["acquisition_date"].isoformat()
        item = SporeSource(id=allocate(session, "SP"), strain_id=strain_id, **values)
        session.add(item)
        session.flush()
        event(
            session,
            "spores",
            item.id,
            "created",
            "Spore source registered; no established culture line created",
        )
        return output(session, "spores", item)


@router.get("/{kind}", response_model=list[RecordOut])
def list_records(
    kind: Kind,
    request: Request,
    q: str = Query("", max_length=200),
    status: Literal["active", "archived", "all"] = "active",
    strain_id: str | None = None,
    line_id: str | None = None,
    material_type: str | None = None,
    origin: str | None = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    model = MODELS[kind]
    with Session(request.app.state.engine) as session:
        statement = select(model)
        if status != "all":
            statement = statement.where(model.status == status)
        if kind in ("physical", "spawn"):
            statement = statement.join(CultureLine, model.line_id == CultureLine.id)
            if strain_id:
                statement = statement.where(CultureLine.strain_id == strain_id)
            if line_id:
                statement = statement.where(model.line_id == line_id)
        elif strain_id and hasattr(model, "strain_id"):
            statement = statement.where(model.strain_id == strain_id)
        if material_type and hasattr(model, "material_type"):
            statement = statement.where(model.material_type == material_type)
        if origin and kind == "lines":
            statement = statement.where(model.origin == origin)
        # Python casefold handles international strain names consistently with duplicate detection.
        rows = session.scalars(
            statement.order_by(model.created_at.desc(), model.id)
        ).all()
        results = []
        query = normalized(q)
        for row in rows:
            if query:
                values = [getattr(row, column.name) for column in row.__table__.columns]
                associated_strain = getattr(row, "strain_id", None)
                if kind in ("physical", "spawn"):
                    line = session.get(CultureLine, row.line_id)
                    associated_strain = line.strain_id
                    values.extend([line.supplier, line.supplier_reference])
                if associated_strain:
                    values.append(session.get(Strain, associated_strain).name)
                if query not in normalized(
                    " ".join(str(v) for v in values if v is not None)
                ):
                    continue
            results.append(row)
        return [output(session, kind, row) for row in results[offset : offset + limit]]


@router.get("/{kind}/{code}", response_model=RecordOut)
def get_record(kind: Kind, code: str, request: Request):
    with Session(request.app.state.engine) as session:
        return output(session, kind, record(session, kind, code))


@router.patch("/{kind}/{code}", response_model=RecordOut)
def edit_record(kind: Kind, code: str, data: EditRecord, request: Request):
    with transaction(request) as session:
        item = record(session, kind, code)
        values = data.model_dump(exclude_unset=True)
        allowed = set(item.__table__.columns.keys()) - {
            "id",
            "created_at",
            "status",
            "strain_id",
            "line_id",
            "registration_batch",
            "batch_id",
            "batch_origin",
            "allocation_mode",
            "normalized_name",
        }
        if values.keys() - allowed:
            raise HTTPException(422, "These fields do not apply to this record")
        if kind == "strains" and "name" in values:
            if not values["name"] or not normalized(values["name"]):
                raise HTTPException(422, "Strain name is required")
            try:
                values["name"] = StrainInput(name=values["name"]).name
            except ValidationError as exc:
                raise HTTPException(
                    422, "Strain name must be 1–200 characters after normalization"
                ) from exc
            item.normalized_name = normalized(values["name"])
        if "stage" in values and (
            values["stage"] is None
            or (kind == "spawn" and values["stage"] not in {"ready", "colonizing"})
        ):
            raise HTTPException(422, "Invalid stage for this record")
        if "material_type" in values:
            types = (
                PREFIX
                if kind == "physical"
                else (
                    {"spawn_jar", "spawn_bag"}
                    if kind == "spawn"
                    else (
                        {"tray", "bag", "block", "other"}
                        if kind == "fruiting"
                        else {
                            "spore_print",
                            "spore_syringe",
                            "spore_swab",
                            "other_spore",
                        }
                    )
                )
            )
            if values["material_type"] not in types:
                raise HTTPException(422, "Invalid material type")
        if "origin" in values and values["origin"] is None:
            raise HTTPException(422, "Origin is required")
        if kind in ("physical", "spores", "spawn", "fruiting"):
            quantity = values.get("quantity", item.quantity)
            unit = values.get("unit", item.unit)
            if quantity is not None and unit is None:
                raise HTTPException(422, "Select a unit for the registered quantity")
        changed = [
            key
            for key, value in values.items()
            if getattr(item, key)
            != (value.isoformat() if isinstance(value, date) else value)
        ]
        for key, value in values.items():
            setattr(item, key, value.isoformat() if isinstance(value, date) else value)
        session.flush()
        if changed:
            event(session, kind, code, "edited", "Updated " + ", ".join(changed))
        return output(session, kind, item)


@router.post("/{kind}/{code}/status", response_model=RecordOut)
def set_status(kind: Kind, code: str, data: StatusInput, request: Request):
    with transaction(request) as session:
        item = record(session, kind, code)
        if item.status != data.status:
            item.status = data.status
            event(
                session,
                kind,
                code,
                "archived" if data.status == "archived" else "restored",
                f"Record {data.status}; relationships and photos retained",
            )
        return output(session, kind, item)


@router.get("/{kind}/{code}/activity", response_model=list[ActivityOut])
def activity(kind: Kind, code: str, request: Request):
    with Session(request.app.state.engine) as session:
        record(session, kind, code)
        return session.scalars(
            select(ActivityEvent)
            .where(getattr(ActivityEvent, OWNER[kind]) == code)
            .order_by(ActivityEvent.id.desc())
        ).all()
