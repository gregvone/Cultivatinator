"""Physical label choices and explicit operational lifecycle actions."""

from datetime import date
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .preparation_schemas import Command, LabelChoice, FinishInput
from .library_schemas import Notes
from .container_tracking import (
    A,
    L,
    assign_label,
    available,
    label_type,
    tracking_state,
    set_phase,
    release_label,
)

from .preparation_models import PreparedMaterial
from .library import record, event
from .preparation import execute, finish

router = APIRouter(prefix="/api/containers", tags=["Container labels and lifecycle"])
Kind = Literal["physical", "spawn", "fruiting", "prepared"]


class AssignLabel(Command, LabelChoice):
    reason: Notes | None = None


class StateAction(Command):
    action: Literal["ready", "failed", "complete"]
    action_date: date = Field(default_factory=date.today)
    reason: Notes | None = None
    notes: Notes | None = None


def get_owner(session, kind, code):
    if kind == "prepared":
        row = session.get(PreparedMaterial, code)
        if row is None:
            raise HTTPException(404, "Material record not found")
        return row
    return record(session, kind, code)


def result(session, kind, row):
    return {"id": row.id, **tracking_state(session, kind, row.id)}


@router.get("/available")
def available_labels(
    request: Request, material_type: str, reusable: bool | None = None
):
    kind = label_type(material_type, reusable)
    if not kind:
        raise HTTPException(422, "This material has no physical label type")
    with Session(request.app.state.engine) as session:
        return available(session, kind)


@router.get("/records/{kind}/{code}")
def label_history(kind: Kind, code: str, request: Request):
    with Session(request.app.state.engine) as session:
        row = get_owner(session, kind, code)
        from .container_tracking import owner_column

        rows = (
            session.connection()
            .execute(
                select(A, L.c.code, L.c.reusable)
                .join(L, L.c.id == A.c.label_id)
                .where(owner_column(A, kind) == code)
                .order_by(A.c.id)
            )
            .mappings()
            .all()
        )
        return {**result(session, kind, row), "assignments": [dict(r) for r in rows]}


@router.post("/records/{kind}/{code}/label")
def assign_record_label(kind: Kind, code: str, data: AssignLabel, request: Request):
    def work(session, op):
        row = get_owner(session, kind, code)
        state = tracking_state(session, kind, code)
        from .material_state import material_state

        lifecycle = material_state(session, kind, code)["lifecycle"]
        if (
            lifecycle in {"used", "completed", "failed"}
            or (kind == "spawn" and row.stage == "used")
            or (kind == "fruiting" and row.stage == "finished")
            or (kind == "prepared" and row.stage in {"failed", "completed"})
        ):
            raise HTTPException(
                409, "Terminal historical records cannot occupy a new physical label"
            )
        if state["label_occupied"]:
            if not data.label and not data.new_label:
                return result(session, kind, row)
            if not state["label_reusable"]:
                raise HTTPException(
                    409, "Disposable physical labels cannot be reassigned"
                )
            if data.label == state["physical_label"] and not data.new_label:
                return result(session, kind, row)
            release_label(
                session,
                kind,
                code,
                date.today().isoformat(),
                data.reason or "Explicit physical label change",
            )
        container_type = label_type(
            row.material_type,
            data.reusable if data.reusable is not None else state.get("label_reusable"),
        )
        if not container_type:
            raise HTTPException(422, "This record type has no physical container label")
        assign_label(session, kind, code, container_type, data.model_dump())
        if kind != "prepared":
            event(
                session,
                kind,
                code,
                "physical_label",
                f"Physical label assigned; permanent record {code} retained",
            )
        return result(session, kind, row)

    return execute(request, data, "assign_label:" + kind + ":" + code, work)


@router.post("/records/{kind}/{code}/state")
def change_state(kind: Kind, code: str, data: StateAction, request: Request):
    if data.action in {"failed", "complete"} and kind in {
        "physical",
        "spawn",
        "prepared",
    }:
        # Reuse legacy completion, source closure and old pool-release accounting.
        from .preparation import set_lifecycle, close_source_balance

        def terminal(session, op):
            row = get_owner(session, kind, code)
            from .material_state import material_state

            if (
                material_state(session, kind, code)["lifecycle"]
                in {
                    "used",
                    "completed",
                    "failed",
                }
                or (kind == "prepared" and row.stage in {"failed", "completed"})
                or (kind == "spawn" and row.stage == "used")
            ):
                raise HTTPException(
                    409,
                    "Record is already terminal; its label cannot be released twice",
                )
            prepared = (
                row
                if kind == "prepared"
                else session.scalar(
                    select(PreparedMaterial).where(
                        (
                            PreparedMaterial.physical_id
                            if kind == "physical"
                            else PreparedMaterial.spawn_id
                        )
                        == code
                    )
                )
            )
            end = "failed" if data.action == "failed" else "completed"
            if prepared:
                finish(
                    session,
                    op,
                    prepared,
                    FinishInput(
                        request_key=data.request_key,
                        action=data.action,
                        action_date=data.action_date,
                        reason=data.reason
                        or (
                            "Marked failed"
                            if end == "failed"
                            else "Explicitly completed/retired"
                        ),
                        notes=data.notes,
                    ),
                )
            else:
                set_lifecycle(session, kind, code, end)
                close_source_balance(
                    session, op, kind, code, data.reason or "Explicit lifecycle action"
                )
                set_phase(session, kind, code, end, data.action_date.isoformat())
                release_label(
                    session,
                    kind,
                    code,
                    data.action_date.isoformat(),
                    data.reason or end,
                )
            if kind != "prepared":
                event(
                    session,
                    kind,
                    code,
                    end,
                    f"{end} on {data.action_date}; {data.reason or ''}; {data.notes or ''}"[
                        :500
                    ],
                )
            return result(session, kind, row)

        return execute(request, data, "container_state:" + kind + ":" + code, terminal)

    def work(session, op):
        row = get_owner(session, kind, code)
        state = tracking_state(session, kind, code)
        from .material_state import material_state

        if material_state(session, kind, code)["lifecycle"] in {
            "used",
            "completed",
            "failed",
        } or (kind == "spawn" and row.stage == "used"):
            raise HTTPException(409, "A terminal record cannot change readiness")
        if data.action == "ready":
            if getattr(row, "status", "active") != "active":
                raise HTTPException(409, "Restore the record before marking it Ready")
            if not (
                kind == "spawn"
                or (kind == "physical" and row.material_type == "agar_plate")
            ):
                raise HTTPException(
                    422,
                    "Only established agar cultures and spawn have this readiness action",
                )
            if state["growth_stage"] == "ready":
                raise HTTPException(409, "This record is already Ready")
            if kind == "spawn":
                row.stage = "ready"
            set_phase(session, kind, code, "ready", data.action_date.isoformat())
        elif kind == "fruiting":
            if row.stage == "finished":
                raise HTTPException(409, "This growing cycle is already finished")
            phase = "completed" if data.action == "complete" else "failed"
            row.stage = "finished"
            set_phase(session, kind, code, phase, data.action_date.isoformat())
            release_label(
                session, kind, code, data.action_date.isoformat(), data.reason or phase
            )
        else:
            raise HTTPException(422, "Unsupported lifecycle action")
        event(
            session,
            kind,
            code,
            "ready" if data.action == "ready" else data.action,
            f"{data.action} on {data.action_date}; {data.reason or ''}; {data.notes or ''}"[
                :500
            ],
        )
        session.flush()
        return result(session, kind, row)

    return execute(request, data, "container_state:" + kind + ":" + code, work)
