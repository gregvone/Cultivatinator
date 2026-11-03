"""Single-source spawning, explicit flush transitions and measured harvest results."""

from datetime import date
from decimal import Decimal
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, UploadFile, Path
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .library_schemas import Input, Notes, Text, Quantity
from .preparation_schemas import Command, LabelChoice, FinishInput
from .models import (
    Spawn,
    FruitingContainer,
    GrowBatch,
    BatchSource,
    FruitingSource,
    PhotoAttachment,
    now,
)
from .fruiting_models import (
    FruitingRun,
    FruitingFlush,
    HarvestEntry,
    HarvestRevision,
    FruitingEnvironment,
    FruitingEnvironmentChange,
    HarvestPhoto,
    PinningPhoto,
)
from .preparation_models import Recipe, PreparedMaterial
from .library import record, output, allocate, event, photo_out
from .preparation import execute, recipe_out, get, finish, set_lifecycle
from .container_tracking import set_phase, release_label
from .material_state import material_state

router = APIRouter(prefix="/api/fruiting", tags=["Fruiting and harvests"])


class EnvironmentData(Input):
    tent_name: Text | None = None
    temperature: Decimal | None = Field(
        default=None, ge=-100, le=200, max_digits=6, decimal_places=2
    )
    temperature_unit: Literal["C", "F"] | None = None
    humidity: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    humidifier: Notes | None = None
    fae: Notes | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def unit(self):
        if self.temperature is not None and self.temperature_unit is None:
            raise ValueError("Select a temperature unit")
        return self


class EnvironmentSave(Command):
    expected_revision: int = Field(ge=0)
    environment: EnvironmentData


class SpawnToBulk(Command):
    spawn_id: Text
    recipe_id: Text
    count: int = Field(default=1, ge=1, le=100)
    spawning_date: date = Field(default_factory=date.today)
    spawn_grams: Quantity | None = None
    substrate_grams: Quantity | None = None
    material_type: Literal["tray", "bag", "block"] = "tray"
    label_choices: list[LabelChoice] | None = Field(
        default=None, min_length=1, max_length=100
    )
    notes: Notes | None = None


class StageAction(Command):
    action: Literal["pinning", "fruiting", "next_flush", "complete", "failed"]
    action_date: date = Field(default_factory=date.today)
    notes: Notes | None = None


class HarvestData(Input):
    harvest_date: date = Field(default_factory=date.today)
    wet_grams: Quantity | None = None
    dry_grams: Quantity | None = None
    potency: int | None = Field(default=None, ge=1, le=5, strict=True)
    potency_notes: Notes | None = None
    notes: Notes | None = None


class HarvestCreate(Command, HarvestData):
    pass


class HarvestEdit(HarvestCreate):
    expected_revision: int = Field(ge=1)


class EnvironmentChange(Command):
    change_date: date = Field(default_factory=date.today)
    notes: Notes = Field(min_length=1)
    environment: EnvironmentData | None = None


def decoded(value):
    return json.loads(value) if value is not None else None


def row_dict(row):
    return {
        c.name: (
            str(value) if isinstance(value := getattr(row, c.name), Decimal) else value
        )
        for c in row.__table__.columns
    }


def totals(harvests):
    result = {"harvest_count": len(harvests)}
    for field in ("wet_grams", "dry_grams"):
        measured = [
            getattr(h, field) for h in harvests if getattr(h, field) is not None
        ]
        result[field] = str(sum(measured, Decimal(0))) if measured else None
        result[field.replace("_grams", "_measured_count")] = len(measured)
    return result


def elapsed(start, end):
    return (
        (date.fromisoformat(end) - date.fromisoformat(start)).days
        if start and end
        else None
    )


def details(session, container):
    run = session.get(FruitingRun, container.id)
    harvests = list(
        session.scalars(
            select(HarvestEntry)
            .where(HarvestEntry.fruiting_id == container.id)
            .order_by(HarvestEntry.harvest_date, HarvestEntry.id)
        )
    )
    flushes = list(
        session.scalars(
            select(FruitingFlush)
            .where(FruitingFlush.fruiting_id == container.id)
            .order_by(FruitingFlush.number)
        )
    )
    changes = list(
        session.scalars(
            select(FruitingEnvironmentChange)
            .where(FruitingEnvironmentChange.fruiting_id == container.id)
            .order_by(
                FruitingEnvironmentChange.change_date, FruitingEnvironmentChange.id
            )
        )
    )
    first_pin = min((f.pinning_date for f in flushes if f.pinning_date), default=None)
    first_harvest = min((h.harvest_date for h in harvests), default=None)
    return {
        "record": output(session, "fruiting", container).model_dump(mode="json"),
        "legacy": run is None or run.operation_id is None,
        "run": (
            {
                **row_dict(run),
                "recipe_snapshot": decoded(run.recipe_snapshot),
                "environment_snapshot": decoded(run.environment_snapshot),
            }
            if run
            else None
        ),
        "source": (
            output(
                session, "spawn", session.get(Spawn, run.source_spawn_id)
            ).model_dump(mode="json")
            if run and run.source_spawn_id
            else None
        ),
        "flushes": [
            {
                **row_dict(f),
                **totals([h for h in harvests if h.flush_number == f.number]),
            }
            for f in flushes
        ],
        "harvests": [row_dict(h) for h in harvests],
        "environment_changes": [
            {**row_dict(c), "settings": decoded(c.settings)} for c in changes
        ],
        "environment": decoded(
            changes[-1].settings
            if changes
            else run.environment_snapshot if run else None
        ),
        "results": {
            **totals(harvests),
            "flushes_with_harvests": len({h.flush_number for h in harvests}),
            "first_harvest_date": first_harvest,
            "days_to_first_pinning": elapsed(
                run.spawning_date if run else None, first_pin
            ),
            "days_to_first_harvest": elapsed(
                run.spawning_date if run else None, first_harvest
            ),
            "cycle_days": (
                elapsed(run.spawning_date, run.completed_date)
                if run and run.stage == "completed"
                else None
            ),
        },
    }


def active_run(session, code):
    container = record(session, "fruiting", code, active=True)
    if container.stage == "finished" or material_state(session, "fruiting", code)[
        "lifecycle"
    ] in {"completed", "failed"}:
        raise HTTPException(
            409,
            "This grow has finished; harvest measurements and photos remain editable",
        )
    run = session.get(FruitingRun, code)
    if run is None:
        # Explicit first action on a legacy record: preserve unknown dates,
        # recipes, environment and source consumption rather than backfilling.
        run = FruitingRun(
            fruiting_id=code,
            stage=(
                container.stage
                if container.stage in {"fruiting", "colonizing"}
                else "unrecorded"
            ),
            current_flush=1,
        )
        session.add(run)
        session.flush()
        session.add(FruitingFlush(fruiting_id=code, number=1))
        session.flush()
    if run.stage in {"completed", "failed"}:
        raise HTTPException(409, "This grow is already terminal")
    return container, run


def check_date(run, value, earliest=None):
    lower = max(filter(None, [run.spawning_date, earliest]), default=None)
    if lower and value < lower:
        raise HTTPException(422, f"Date cannot precede {lower}")


@router.get("/environment")
def environment(request: Request):
    with Session(request.app.state.engine) as session:
        row = session.get(FruitingEnvironment, 1)
        return {
            "revision": row.revision if row else 0,
            "environment": decoded(row.settings) if row else None,
        }


@router.post("/environment")
def save_environment(data: EnvironmentSave, request: Request):
    def work(session, op):
        row = session.get(FruitingEnvironment, 1)
        if data.expected_revision != (row.revision if row else 0):
            raise HTTPException(
                409, "Environment settings changed; reload before saving"
            )
        if row is None:
            row = FruitingEnvironment(id=1, revision=0, settings="{}")
            session.add(row)
        row.revision += 1
        row.settings = data.environment.model_dump_json()
        session.flush()
        return {"revision": row.revision, "environment": decoded(row.settings)}

    return execute(request, data, "fruiting_environment", work)


@router.post("/create", status_code=201)
def spawn_to_bulk(data: SpawnToBulk, request: Request):
    def work(session, op):
        source = record(session, "spawn", data.spawn_id, active=True)
        state = material_state(session, "spawn", source.id)
        if source.stage != "ready" or state["lifecycle"] in {
            "used",
            "failed",
            "completed",
            "depleted",
        }:
            raise HTTPException(
                409, "Select one Ready spawn jar or bag; this source is unavailable"
            )
        recipe = get(session, Recipe, data.recipe_id)
        if recipe.status != "active" or recipe.recipe_type != "substrate":
            raise HTTPException(422, "Select an active Substrate recipe")
        if data.label_choices is not None and len(data.label_choices) != data.count:
            raise HTTPException(422, "Provide one label choice per fruiting container")
        snapshot = json.dumps(recipe_out(recipe, session))
        env = session.get(FruitingEnvironment, 1)
        batch = GrowBatch(
            id=allocate(session, "GB"),
            batch_origin="prepared",
            allocation_mode="specific",
            acquisition_date=data.spawning_date.isoformat(),
            notes=data.notes,
        )
        session.add(batch)
        session.flush()
        session.add(BatchSource(batch_id=batch.id, spawn_id=source.id))
        session.flush()
        session.info["reserved_label_codes"] = {
            c.label for c in data.label_choices or [] if c.label
        }
        items = []
        for index in range(data.count):
            container = FruitingContainer(
                id=allocate(session, "FR"),
                batch_id=batch.id,
                material_type=data.material_type,
                stage="colonizing",
                notes=data.notes,
            )
            if data.label_choices:
                session.info.setdefault("container_choices", {})[container.id] = (
                    data.label_choices[index].model_dump()
                )
            session.add(container)
            session.flush()
            session.add(
                FruitingSource(
                    fruiting_id=container.id, batch_id=batch.id, spawn_id=source.id
                )
            )
            session.flush()
            session.add(
                FruitingRun(
                    fruiting_id=container.id,
                    operation_id=op.id,
                    source_spawn_id=source.id,
                    recipe_id=recipe.id,
                    recipe_snapshot=snapshot,
                    environment_snapshot=env.settings if env else None,
                    spawning_date=data.spawning_date.isoformat(),
                    spawn_grams=data.spawn_grams,
                    substrate_grams=data.substrate_grams,
                    stage="colonizing",
                    current_flush=1,
                )
            )
            session.flush()
            session.add(FruitingFlush(fruiting_id=container.id, number=1))
            event(
                session,
                "fruiting",
                container.id,
                "spawned",
                f"Spawned on {data.spawning_date} from {source.id}; substrate recipe snapshot retained; operation {op.id}",
            )
            items.append(container)
        # Close any historical pool reservation once. No partial-spawn balance.
        prepared = session.scalar(
            select(PreparedMaterial).where(PreparedMaterial.spawn_id == source.id)
        )
        if prepared:
            finish(
                session,
                op,
                prepared,
                FinishInput(
                    request_key=data.request_key,
                    action="complete",
                    action_date=data.spawning_date,
                    reason=f"Spawn consumed by {op.id}",
                ),
            )
        else:
            set_lifecycle(session, "spawn", source.id, "completed")
        set_phase(session, "spawn", source.id, "used", data.spawning_date.isoformat())
        release_label(
            session,
            "spawn",
            source.id,
            data.spawning_date.isoformat(),
            "Spawn consumed by " + op.id,
        )
        source.stage = "used"
        event(
            session,
            "spawn",
            source.id,
            "used",
            f"Consumed in full for {len(items)} fruiting containers; operation {op.id}",
        )
        session.flush()
        return {
            "operation_id": op.id,
            "containers": [
                output(session, "fruiting", c).model_dump(mode="json") for c in items
            ],
        }

    return execute(request, data, "spawn_to_bulk", work)


@router.get("")
@router.get("/", include_in_schema=False)
def listing(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            output(session, "fruiting", row).model_dump(mode="json")
            for row in session.scalars(
                select(FruitingContainer).order_by(
                    FruitingContainer.created_at.desc(), FruitingContainer.id.desc()
                )
            )
        ]


@router.get("/records/{code}")
def detail(code: str, request: Request):
    with Session(request.app.state.engine) as session:
        return details(session, record(session, "fruiting", code))


@router.post("/records/{code}/stage")
def transition(code: str, data: StageAction, request: Request):
    def work(session, op):
        container, run = active_run(session, code)
        flush = session.get(FruitingFlush, (code, run.current_flush))
        action_date = data.action_date.isoformat()
        latest = session.scalar(
            select(HarvestEntry.harvest_date)
            .where(HarvestEntry.fruiting_id == code)
            .order_by(HarvestEntry.harvest_date.desc())
            .limit(1)
        )
        check_date(
            run,
            action_date,
            max(
                filter(None, [latest, flush.pinning_date, flush.fruiting_date]),
                default=None,
            ),
        )
        if data.action == "pinning" and run.stage in {"colonizing", "unrecorded"}:
            run.stage = "pinning"
            flush.pinning_date = action_date
            flush.pinning_notes = data.notes
        elif data.action == "fruiting" and run.stage == "pinning":
            run.stage = "fruiting"
            flush.fruiting_date = action_date
            container.stage = "fruiting"
        elif data.action == "next_flush" and run.stage == "harvest":
            run.current_flush += 1
            run.stage = "pinning"
            session.add(
                FruitingFlush(
                    fruiting_id=code,
                    number=run.current_flush,
                    pinning_date=action_date,
                    pinning_notes=data.notes,
                )
            )
        elif data.action in {"complete", "failed"}:
            run.stage = "completed" if data.action == "complete" else "failed"
            setattr(
                run,
                "completed_date" if data.action == "complete" else "failed_date",
                action_date,
            )
            run.closing_notes = data.notes
            set_phase(session, "fruiting", code, run.stage, action_date)
            release_label(
                session, "fruiting", code, action_date, data.notes or run.stage
            )
            container.stage = "finished"
        else:
            raise HTTPException(
                409, "This transition is not available at the current stage"
            )
        event(
            session,
            "fruiting",
            code,
            data.action,
            f"{data.action} on {action_date}; flush {run.current_flush}; {data.notes or ''}"[
                :500
            ],
        )
        session.flush()
        return details(session, container)

    return execute(request, data, "fruiting_stage:" + code, work)


def harvest_dict(row):
    return row_dict(row)


def validate_harvest_date(session, run, flush, day):
    check_date(
        run,
        day,
        max(filter(None, [flush.pinning_date, flush.fruiting_date]), default=None),
    )
    following = session.get(FruitingFlush, (run.fruiting_id, flush.number + 1))
    if following and following.pinning_date and day > following.pinning_date:
        raise HTTPException(422, "A harvest cannot fall after the next flush began")
    closing = run.completed_date or run.failed_date
    if closing and day > closing:
        raise HTTPException(422, "Harvest date cannot follow the end of this grow")


def save_harvest_revision(session, op, row):
    session.flush()
    session.refresh(row)
    session.add(
        HarvestRevision(
            harvest_id=row.id,
            revision=row.revision,
            operation_id=op.id,
            snapshot=json.dumps(harvest_dict(row)),
        )
    )
    event(
        session,
        "fruiting",
        row.fruiting_id,
        "harvest",
        f"Harvest {row.id}, flush {row.flush_number}, revision {row.revision}; wet {row.wet_grams if row.wet_grams is not None else 'unknown'} g; dry {row.dry_grams if row.dry_grams is not None else 'unknown'} g",
    )
    session.flush()
    return harvest_dict(row)


@router.post("/records/{code}/harvests", status_code=201)
def create_harvest(code: str, data: HarvestCreate, request: Request):
    def work(session, op):
        container, run = active_run(session, code)
        if run.stage not in {"fruiting", "harvest"}:
            raise HTTPException(
                409, "Mark the grow Fruiting before recording a harvest"
            )
        flush = session.get(FruitingFlush, (code, run.current_flush))
        validate_harvest_date(session, run, flush, data.harvest_date.isoformat())
        row = HarvestEntry(
            id=allocate(session, "HR"),
            fruiting_id=code,
            flush_number=run.current_flush,
            **data.model_dump(mode="json", exclude={"request_key"}),
        )
        session.add(row)
        run.stage = "harvest"
        return save_harvest_revision(session, op, row)

    return execute(request, data, "harvest_create:" + code, work)


@router.post("/harvests/{code}/edit")
def edit_harvest(code: str, data: HarvestEdit, request: Request):
    def work(session, op):
        row = get(session, HarvestEntry, code)
        if row.revision != data.expected_revision:
            raise HTTPException(409, "Harvest changed; reload before editing")
        run = session.get(FruitingRun, row.fruiting_id)
        flush = session.get(FruitingFlush, (row.fruiting_id, row.flush_number))
        validate_harvest_date(session, run, flush, data.harvest_date.isoformat())
        for key, value in data.model_dump(
            mode="json", exclude={"request_key", "expected_revision"}
        ).items():
            setattr(row, key, value)
        row.revision += 1
        row.updated_at = now()
        return save_harvest_revision(session, op, row)

    return execute(request, data, "harvest_edit:" + code, work)


@router.get("/harvests/{code}/history")
def harvest_history(code: str, request: Request):
    with Session(request.app.state.engine) as session:
        get(session, HarvestEntry, code)
        return [
            {**row_dict(row), "snapshot": decoded(row.snapshot)}
            for row in session.scalars(
                select(HarvestRevision)
                .where(HarvestRevision.harvest_id == code)
                .order_by(HarvestRevision.revision)
            )
        ]


@router.post("/records/{code}/environment")
def change_environment(code: str, data: EnvironmentChange, request: Request):
    def work(session, op):
        container, run = active_run(session, code)
        check_date(run, data.change_date.isoformat())
        latest = session.scalar(
            select(FruitingEnvironmentChange)
            .where(FruitingEnvironmentChange.fruiting_id == code)
            .order_by(
                FruitingEnvironmentChange.change_date.desc(),
                FruitingEnvironmentChange.id.desc(),
            )
            .limit(1)
        )
        if latest and data.change_date.isoformat() < latest.change_date:
            raise HTTPException(
                422, "A new environment change cannot precede the last recorded change"
            )
        settings = (
            data.environment.model_dump_json()
            if data.environment
            else latest.settings if latest else run.environment_snapshot
        )
        session.add(
            FruitingEnvironmentChange(
                fruiting_id=code,
                change_date=data.change_date.isoformat(),
                settings=settings,
                notes=data.notes,
            )
        )
        event(
            session,
            "fruiting",
            code,
            "environment_change",
            f"Environment change {data.change_date}: {data.notes}"[:500],
        )
        session.flush()
        return details(session, container)

    return execute(request, data, "grow_environment:" + code, work)


@router.get("/harvests/{code}/photos")
def harvest_photos(code: str, request: Request):
    with Session(request.app.state.engine) as session:
        get(session, HarvestEntry, code)
        return [
            photo_out(p)
            for p in session.scalars(
                select(PhotoAttachment)
                .join(HarvestPhoto, HarvestPhoto.photo_id == PhotoAttachment.id)
                .where(HarvestPhoto.harvest_id == code)
                .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
            )
        ]


@router.post("/harvests/{code}/photos", status_code=201)
def upload_harvest_photo(code: str, request: Request, file: UploadFile):
    from .photos import store_upload

    with Session(request.app.state.engine) as session:
        harvest = get(session, HarvestEntry, code)
        fruiting_id = harvest.fruiting_id
    return store_upload("fruiting", fruiting_id, request, file, harvest_id=code)


def pinning_event(session, code, number):
    record(session, "fruiting", code)
    flush = session.get(FruitingFlush, (code, number))
    if flush is None:
        raise HTTPException(404, "Flush not found")
    if flush.pinning_date is None:
        raise HTTPException(409, "Pinning has not been recorded for this flush")
    return flush


@router.get("/records/{code}/flushes/{number}/pinning/photos")
def pinning_photos(code: str, request: Request, number: int = Path(ge=1)):
    with Session(request.app.state.engine) as session:
        pinning_event(session, code, number)
        return [
            photo_out(p)
            for p in session.scalars(
                select(PhotoAttachment)
                .join(PinningPhoto, PinningPhoto.photo_id == PhotoAttachment.id)
                .where(
                    PinningPhoto.fruiting_id == code,
                    PinningPhoto.flush_number == number,
                )
                .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
            )
        ]


@router.post("/records/{code}/flushes/{number}/pinning/photos", status_code=201)
def upload_pinning_photo(
    code: str, request: Request, file: UploadFile, number: int = Path(ge=1)
):
    from .photos import store_upload

    with Session(request.app.state.engine) as session:
        pinning_event(session, code, number)
    return store_upload("fruiting", code, request, file, pinning_flush=number)
