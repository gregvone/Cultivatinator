"""Atomic label allocation and lifecycle projection. No lineage uses label codes.

The flush listener covers all existing biological registration paths, including
acquisitions, clones, establishments and manual FR provenance. Existing rows
are never backfilled merely by reading or editing them.
"""

from datetime import date
from fastapi import HTTPException
from sqlalchemy import event, func, insert, select, update, inspect
from sqlalchemy.orm import Session
from .models import PhysicalCulture, Spawn, FruitingContainer, now
from .preparation_models import PreparedMaterial, PreparationBatch
from .container_models import ContainerLabel, LabelAssignment, CultivationState

LABELS = {
    "agar_plate": ("P", True),
    "spawn_jar": ("J", True),
    "spawn_bag": ("B", False),
    "lc_jar": ("L", True),
    "lc_syringe": ("LS", False),
    "fruiting_reusable": ("F", True),
    "fruiting_disposable": ("FD", False),
}
OWNERS = {
    "physical": "physical_id",
    "spawn": "spawn_id",
    "fruiting": "fruiting_id",
    "prepared": "prepared_id",
}
L = ContainerLabel.__table__
A = LabelAssignment.__table__
S = CultivationState.__table__


def owner_column(table, kind):
    return table.c[OWNERS[kind]]


def tracking_state(session, kind, code):
    if kind not in OWNERS:
        return {}
    conn = session.connection()
    assignment = (
        conn.execute(
            select(L.c.code, L.c.reusable, A.c.released_at)
            .join(A, A.c.label_id == L.c.id)
            .where(owner_column(A, kind) == code)
            .order_by(A.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    phase = (
        conn.execute(select(S).where(owner_column(S, kind) == code)).mappings().first()
    )
    return {
        "physical_label": assignment["code"] if assignment else None,
        "label_reusable": bool(assignment["reusable"]) if assignment else None,
        "label_occupied": assignment is not None and assignment["released_at"] is None,
        "growth_stage": phase["phase"] if phase else None,
        **{
            field: phase[field] if phase else None
            for field in (
                "inoculation_date",
                "ready_date",
                "used_date",
                "completed_date",
                "failed_date",
            )
        },
    }


def set_phase(session, kind, code, phase, action_date=None):
    conn = session.connection()
    existing = (
        conn.execute(select(S).where(owner_column(S, kind) == code)).mappings().first()
    )
    field = {
        "colonizing": "inoculation_date",
        "ready": "ready_date",
        "used": "used_date",
        "completed": "completed_date",
        "failed": "failed_date",
    }[phase]
    values = {"phase": phase, field: action_date}
    if existing:
        conn.execute(update(S).where(S.c.id == existing["id"]).values(**values))
    else:
        conn.execute(insert(S).values(**{OWNERS[kind]: code}, **values))


def release_label(session, kind, code, action_date, reason):
    session.connection().execute(
        update(A)
        .where(owner_column(A, kind) == code, A.c.released_at.is_(None))
        .values(
            released_at=now(), release_date=action_date, release_reason=reason[:500]
        )
    )


def label_type(material_type, reusable=None):
    if material_type in {"tray", "bag", "block", "other"}:
        return (
            "fruiting_reusable"
            if (material_type == "tray" if reusable is None else reusable)
            and material_type not in {"bag", "block"}
            else "fruiting_disposable"
        )
    return material_type if material_type in LABELS else None


def available(session, container_type):
    conn = session.connection()
    prefix, reusable = LABELS[container_type]
    maximum = (
        conn.execute(
            select(func.max(L.c.number)).where(L.c.container_type == container_type)
        ).scalar()
        or 0
    )
    rows = (
        conn.execute(
            select(L.c.code)
            .where(
                L.c.container_type == container_type,
                ~select(A.c.id)
                .where(A.c.label_id == L.c.id, A.c.released_at.is_(None))
                .exists(),
            )
            .order_by(L.c.number)
        )
        .scalars()
        .all()
        if reusable
        else []
    )
    return {
        "available": rows,
        "next_label": f"{prefix}-{maximum+1:02d}",
        "reusable": reusable,
    }


def assign_label(session, kind, code, container_type, choice=None):
    conn = session.connection()
    existing = conn.execute(
        select(A.c.id).where(owner_column(A, kind) == code, A.c.released_at.is_(None))
    ).first()
    if existing:
        return
    options = available(session, container_type)
    choice = choice or {}
    requested = choice.get("label")
    reserved = session.info.get("reserved_label_codes", set())
    automatic_free = [code for code in options["available"] if code not in reserved]
    selected = requested or (
        options["next_label"]
        if choice.get("new_label") or not automatic_free
        else automatic_free[0]
    )
    label = conn.execute(select(L).where(L.c.code == selected)).mappings().first()
    if label:
        if label["container_type"] != container_type:
            raise HTTPException(422, "Choose a label for this container type")
        if (
            not label["reusable"]
            or conn.execute(
                select(A.c.id).where(
                    A.c.label_id == label["id"], A.c.released_at.is_(None)
                )
            ).first()
        ):
            raise HTTPException(
                409,
                f"Physical label {selected} is occupied or disposable and cannot be reused",
            )
        label_id = label["id"]
    else:
        if selected != options["next_label"]:
            raise HTTPException(
                422,
                f"The next new label is {options['next_label']}; select an available label or create that new label",
            )
        prefix, _ = LABELS[container_type]
        label_id = conn.execute(
            insert(L).values(
                container_type=container_type,
                number=int(selected[len(prefix) + 1 :]),
                code=selected,
                reusable=int(options["reusable"]),
            )
        ).inserted_primary_key[0]
    conn.execute(
        insert(A).values(label_id=label_id, **{OWNERS[kind]: code}, assigned_at=now())
    )


def move_pending(session, kind, code):
    conn = session.connection()
    for table in (A, S):
        conn.execute(
            update(table)
            .where(table.c.prepared_id == code)
            .values(prepared_id=None, **{OWNERS[kind]: code})
        )


@event.listens_for(Session, "after_flush")
def allocate_new_biological_labels(session, context):
    for row in list(session.new):
        if isinstance(row, (PhysicalCulture, Spawn, FruitingContainer)):
            kind = (
                "physical"
                if isinstance(row, PhysicalCulture)
                else "spawn" if isinstance(row, Spawn) else "fruiting"
            )
            container_type = label_type(row.material_type)
            if not container_type:
                continue
            move_pending(session, kind, row.id)
            choice = session.info.get("container_choices", {}).get(row.id)
            assign_label(
                session,
                kind,
                row.id,
                label_type(row.material_type, (choice or {}).get("reusable")),
                choice,
            )
            if kind == "fruiting" and row.stage == "finished":
                # An explicitly registered finished cycle cannot reserve a tray.
                # Keep the assignment as history; no spawning event is invented.
                set_phase(session, kind, row.id, "completed", None)
                release_label(
                    session, kind, row.id, None, "Registered finished growing cycle"
                )
            prepared = (
                session.connection()
                .execute(
                    select(PreparedMaterial.__table__).where(
                        PreparedMaterial.id == row.id
                    )
                )
                .mappings()
                .first()
            )
            if (
                prepared
                and row.material_type in {"agar_plate", "spawn_jar", "spawn_bag"}
                and not tracking_state(session, kind, row.id).get("growth_stage")
            ):
                import json

                batch = (
                    session.connection()
                    .execute(
                        select(PreparationBatch.__table__.c.snapshot).where(
                            PreparationBatch.id == prepared["batch_id"]
                        )
                    )
                    .scalar()
                )
                snapshot = json.loads(batch)
                from .preparation_models import MaterialTransfer

                inoculated = (
                    session.connection()
                    .execute(
                        select(MaterialTransfer.__table__.c.transfer_date).where(
                            MaterialTransfer.prepared_id == row.id
                        )
                    )
                    .scalar()
                )
                set_phase(
                    session,
                    kind,
                    row.id,
                    "colonizing",
                    inoculated or snapshot.get("inoculation_date"),
                )
    for row in list(session.dirty):
        if isinstance(row, Spawn) and inspect(row).attrs.stage.history.has_changes():
            prior = tracking_state(session, "spawn", row.id)
            if prior.get("growth_stage") != row.stage:
                set_phase(
                    session,
                    "spawn",
                    row.id,
                    row.stage,
                    (
                        date.today().isoformat()
                        if row.stage == "ready"
                        else prior.get("inoculation_date")
                    ),
                )
        if (
            isinstance(row, FruitingContainer)
            and row.stage == "finished"
            and inspect(row).attrs.stage.history.has_changes()
        ):
            if tracking_state(session, "fruiting", row.id).get("growth_stage") not in {
                "completed",
                "failed",
            }:
                set_phase(session, "fruiting", row.id, "completed", None)
                release_label(
                    session, "fruiting", row.id, None, "Explicit end of growing cycle"
                )
        if (
            isinstance(row, PreparedMaterial)
            and row.stage == "inoculated"
            and not row.physical_id
            and not row.spawn_id
        ):
            assign_label(
                session,
                "prepared",
                row.id,
                label_type(row.material_type),
                session.info.get("container_choices", {}).get(row.id),
            )
            if not tracking_state(session, "prepared", row.id).get("growth_stage"):
                from .preparation_models import MaterialTransfer

                transfer_date = (
                    session.connection()
                    .execute(
                        select(MaterialTransfer.__table__.c.transfer_date).where(
                            MaterialTransfer.prepared_id == row.id
                        )
                    )
                    .scalar()
                )
                set_phase(session, "prepared", row.id, "colonizing", transfer_date)
