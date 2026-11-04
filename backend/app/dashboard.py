"""Dashboard projections of recorded facts. No cultivation writes or predictions."""

from collections import Counter
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Float, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session, load_only
from .models import (
    PhysicalCulture,
    Spawn,
    FruitingContainer,
    CultureLine,
    Strain,
    ActivityEvent,
    SporeSource,
    GrowBatch,
)
from .container_models import CultivationState, LabelAssignment, ContainerLabel
from .preparation_models import MaterialLifecycle
from .fruiting_models import FruitingRun, FruitingFlush, HarvestEntry
from .reports import source_identities, milligrams, day
from . import dashboard_store as store

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
MODELS = {"physical": PhysicalCulture, "spawn": Spawn, "fruiting": FruitingContainer}
OWNERS = {
    "physical": "physical_id",
    "spawn": "spawn_id",
    "fruiting": "fruiting_id",
    "strains": "strain_id",
    "lines": "line_id",
    "spores": "spore_id",
    "batches": "batch_id",
}
TERMINAL = {"used", "completed", "failed", "depleted", "finished"}
STAGE_EVENTS = {
    "ready",
    "used",
    "failed",
    "fail",
    "complete",
    "completed",
    "pinning",
    "fruiting",
    "next_flush",
    "harvest",
}


def now():
    return datetime.now(timezone.utc)


def local_day(zone):
    try:
        return now().astimezone(ZoneInfo(zone)).date()
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(422, "Use a valid IANA timezone") from exc


def identity(rows):
    known = sorted({r["strain_name"] for r in rows if r["strain_id"]})
    if not known:
        lines = sorted({r["line_name"] or r["line_id"] for r in rows if r["line_id"]})
        return "Unknown strain" + (" · " + ", ".join(lines) if lines else "")
    partial = any(not r["strain_id"] for r in rows)
    return (
        (
            "Partial identification: "
            if partial
            else "Mixed Strains: " if len(known) > 1 else ""
        )
        + ", ".join(known)
        + (" + unknown sources" if partial else "")
    )


def records(session, kinds=None, archived=False, today=None):
    """Fixed query count; scalar projections, no lazy relationships/per-record queries.

    kinds maps kinds to bounded owner-ID sets for activity, or None for all active
    dashboard records. Payloads are paginated even when all candidates are counted.
    """
    result = {}
    for kind, model in MODELS.items():
        if kinds is not None and not kinds.get(kind):
            continue
        owner = OWNERS[kind]
        latest = (
            select(
                getattr(LabelAssignment, owner).label("code"),
                func.max(LabelAssignment.id).label("last_id"),
            )
            .group_by(getattr(LabelAssignment, owner))
            .subquery()
        )
        query = (
            select(model, CultivationState, ContainerLabel.code)
            .outerjoin(CultivationState, getattr(CultivationState, owner) == model.id)
            .outerjoin(latest, latest.c.code == model.id)
            .outerjoin(LabelAssignment, LabelAssignment.id == latest.c.last_id)
            .outerjoin(ContainerLabel, ContainerLabel.id == LabelAssignment.label_id)
        )
        if not archived:
            query = query.where(model.status == "active")
        if kinds is not None:
            query = query.where(model.id.in_(kinds[kind]))
        if kind == "fruiting":
            query = (
                query.add_columns(FruitingRun, FruitingFlush)
                .outerjoin(FruitingRun, FruitingRun.fruiting_id == model.id)
                .outerjoin(
                    FruitingFlush,
                    and_(
                        FruitingFlush.fruiting_id == model.id,
                        FruitingFlush.number == FruitingRun.current_flush,
                    ),
                )
            )
        else:
            query = (
                query.add_columns(
                    MaterialLifecycle.state,
                    Strain.name,
                    func.coalesce(CultureLine.name, CultureLine.id),
                )
                .outerjoin(
                    MaterialLifecycle, getattr(MaterialLifecycle, owner) == model.id
                )
                .outerjoin(CultureLine, CultureLine.id == model.line_id)
                .outerjoin(
                    Strain,
                    Strain.id
                    == (
                        CultureLine.strain_id
                        if kind == "physical"
                        else func.coalesce(CultureLine.strain_id, Spawn.strain_id)
                    ),
                )
            )
        if today is not None and not archived:
            alive = or_(
                CultivationState.phase.is_(None), ~CultivationState.phase.in_(TERMINAL)
            )
            failed = CultivationState.phase == "failed"
            failed_date = CultivationState.failed_date
            if kind == "fruiting":
                alive = and_(
                    alive,
                    model.stage != "finished",
                    or_(FruitingRun.stage.is_(None), ~FruitingRun.stage.in_(TERMINAL)),
                )
                failed = or_(failed, FruitingRun.stage == "failed")
                failed_date = func.coalesce(FruitingRun.failed_date, failed_date)
            else:
                alive = and_(
                    alive,
                    or_(
                        MaterialLifecycle.state.is_(None),
                        MaterialLifecycle.state == "active",
                    ),
                )
                failed = or_(failed, MaterialLifecycle.state == "failed")
                if kind == "spawn":
                    alive = and_(alive, model.stage != "used")
            query = query.where(
                or_(
                    alive,
                    and_(
                        failed,
                        failed_date >= (today - timedelta(days=6)).isoformat(),
                        failed_date <= today.isoformat(),
                    ),
                )
            )
        columns = [model.id, model.status, model.material_type, model.created_at]
        if kind != "physical":
            columns.append(model.stage)
        query = query.options(load_only(*columns))
        if kind == "fruiting":
            query = query.options(
                load_only(
                    FruitingRun.fruiting_id,
                    FruitingRun.stage,
                    FruitingRun.current_flush,
                    FruitingRun.spawning_date,
                    FruitingRun.completed_date,
                    FruitingRun.failed_date,
                ),
                load_only(
                    FruitingFlush.fruiting_id,
                    FruitingFlush.number,
                    FruitingFlush.pinning_date,
                    FruitingFlush.fruiting_date,
                ),
            )
        for row, state, label, *extra in session.execute(query):
            phase = state.phase if state else None
            stage = phase or getattr(row, "stage", None)
            lifecycle = phase if phase in TERMINAL else "active"
            recorded_date = getattr(
                state,
                "inoculation_date" if stage == "colonizing" else str(stage) + "_date",
                None,
            )
            flush = None
            if kind == "fruiting":
                run, current = extra
                # Legacy FR "ready" predates recorded fruiting stages; the
                # existing detail/list already displays it as Stage not recorded.
                stage = (
                    run.stage
                    if run
                    else (
                        phase
                        if phase in TERMINAL
                        else (
                            "unrecorded"
                            if row.stage == "ready"
                            else "completed" if row.stage == "finished" else row.stage
                        )
                    )
                )
                flush = run.current_flush if run else None
                lifecycle = (
                    stage
                    if stage in TERMINAL
                    else "completed" if row.stage == "finished" else lifecycle
                )
                if stage == "colonizing":
                    recorded_date = run.spawning_date if run else recorded_date
                elif stage in {"pinning", "fruiting"}:
                    recorded_date = getattr(current, stage + "_date", None)
                elif stage in {"completed", "failed"}:
                    recorded_date = getattr(run, stage + "_date", None) or recorded_date
                ident = "Unknown strain"
            else:
                material_lifecycle, strain, line = extra
                if lifecycle == "active" and material_lifecycle:
                    lifecycle = material_lifecycle
                if getattr(row, "stage", None) == "used":
                    lifecycle = "used"
                if lifecycle == "failed":
                    recorded_date = state.failed_date if state else None
                ident = strain or (
                    "Unknown strain · " + line if line else "Unknown strain"
                )
            result[(kind, row.id)] = dict(
                kind=kind,
                record_id=row.id,
                title=f"{label or row.id} · {ident}",
                identity=ident,
                target=f"/culture-library/{kind}/{row.id}",
                stage=stage,
                lifecycle=lifecycle,
                recorded_date=recorded_date,
                flush=flush,
                material_type=row.material_type,
                archived=row.status == "archived",
                created_at=row.created_at,
            )
    fr_codes = [code for kind, code in result if kind == "fruiting"]
    if fr_codes:
        # Filter source query at the database, rather than loading every old grow.
        identities = source_identities(session, fr_codes)
        for code in fr_codes:
            item = result[("fruiting", code)]
            item["identity"] = identity(identities[code])
            item["title"] = item["title"].replace("Unknown strain", item["identity"], 1)
    return result


def reference(record):
    return {k: record[k] for k in ("record_id", "title", "target", "stage", "archived")}


def candidates(session, rows, preferences, today):
    # Only explicit lifecycle events participate: photos, notes, weights and label
    # edits cannot invalidate a dismissal. Flush/date also distinguish legacy data.
    transition_ids = {}
    for kind in MODELS:
        owner = getattr(ActivityEvent, OWNERS[kind])
        transition_ids[kind] = dict(
            session.execute(
                select(owner, func.max(ActivityEvent.id))
                .where(
                    owner.in_([code for k, code in rows if k == kind]),
                    ActivityEvent.event_type.in_(STAGE_EVENTS),
                )
                .group_by(owner)
            ).all()
        )
    output = []
    for (kind, code), r in rows.items():
        stage, lifecycle = r["stage"], r["lifecycle"]
        if r["archived"]:
            continue
        date = day(r["recorded_date"])
        elapsed = (today - date).days if date and date <= today else None
        fingerprint = sha256(
            json.dumps(
                [
                    stage,
                    lifecycle,
                    r["recorded_date"],
                    r["flush"],
                    transition_ids[kind].get(code),
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        r["fingerprint"] = fingerprint

        def add(rule, category, description, severity="info"):
            output.append(
                {
                    **reference(r),
                    "alert_id": f"{rule}:{kind}:{code}",
                    "fingerprint": fingerprint,
                    "rule": rule,
                    "category": category,
                    "severity": severity,
                    "description": description,
                    "recorded_date": r["recorded_date"],
                    "elapsed_days": elapsed,
                }
            )

        if lifecycle in TERMINAL or stage in TERMINAL:
            if (
                (lifecycle == "failed" or stage == "failed")
                and elapsed is not None
                and elapsed <= 6
            ):
                add(
                    "recent_failure",
                    "Review / history",
                    "Explicitly marked Failed within the last seven calendar days. Review the recorded history; no cause is inferred.",
                    "warning",
                )
            continue
        if stage == "ready" and (
            kind == "spawn" or kind == "physical" and r["material_type"] == "agar_plate"
        ):
            add(
                "ready",
                "Ready for action",
                "Marked Ready. Open the record to choose a transfer or spawning action.",
            )
        if kind == "fruiting" and stage in {
            "colonizing",
            "ready",
            "pinning",
            "fruiting",
            "harvest",
        }:
            suggestion = {
                "colonizing": "Review the grow; mark Pinning when observed.",
                "ready": "Review this recorded Ready grow before recording its next stage.",
                "pinning": "Mark Fruiting when observed.",
                "fruiting": "Record a harvest when one occurs.",
                "harvest": "Record another harvest, start Next Flush, or Finish Grow when appropriate.",
            }[stage]
            add(
                "fruiting_action",
                "Ready for action",
                f"Recorded stage: {stage.title()}. {suggestion}",
            )
        rule = (
            "agar_growing"
            if kind == "physical"
            and r["material_type"] == "agar_plate"
            and stage == "colonizing"
            else (
                "spawn_colonizing"
                if kind == "spawn" and stage == "colonizing"
                else (
                    "fruiting_colonizing"
                    if kind == "fruiting" and stage == "colonizing"
                    else (
                        stage
                        if kind == "fruiting" and stage in {"pinning", "fruiting"}
                        else None
                    )
                )
            )
        )
        if rule:
            pref = getattr(preferences, rule)
            if pref.enabled and elapsed is not None and elapsed > pref.days:
                add(
                    rule,
                    "Elapsed-time reminder",
                    f"{elapsed} days since recorded {'Germinating' if rule == 'agar_growing' else stage.title()} date; reminder threshold {pref.days} days. Review only; this is not a growth prediction.",
                    "warning",
                )
    return sorted(
        output,
        key=lambda a: (
            a["severity"] != "warning",
            a["recorded_date"] or "9999",
            a["alert_id"],
        ),
    )


def attention(session, settings, today):
    document = store.read(settings)
    rows = records(session, today=today)
    all_items = candidates(session, rows, document.preferences, today)
    visible, hidden = [], []
    for item in all_items:
        state = document.alerts.get(item["alert_id"])
        suppressed = (
            state
            and state.fingerprint == item["fingerprint"]
            and (state.action == "dismiss" or state.until and state.until > now())
        )
        (hidden if suppressed else visible).append(
            {
                **item,
                "suppression": state.model_dump(mode="json") if suppressed else None,
            }
        )
    return visible, hidden, all_items, document, rows


def activity(session, record_type="all", page=1, page_size=25):
    query = select(ActivityEvent)
    if record_type != "all":
        query = query.where(getattr(ActivityEvent, OWNERS[record_type]).is_not(None))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    timestamp = ActivityEvent.occurred_at
    # julianday/strftime("%f") round sub-millisecond timestamps in SQLite.
    # Normalize whole seconds to UTC, then preserve the actual fractional value;
    # event ID breaks ties only for events recorded at the same instant.
    fraction = case(
        (
            func.instr(timestamp, ".") > 0,
            cast(
                literal("0.").concat(
                    func.substr(timestamp, func.instr(timestamp, ".") + 1)
                ),
                Float,
            ),
        ),
        else_=0,
    )
    events = session.scalars(
        query.order_by(
            func.strftime("%Y-%m-%dT%H:%M:%S", timestamp).desc(),
            fraction.desc(),
            ActivityEvent.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    keys = {
        kind: {getattr(e, owner) for e in events if getattr(e, owner)}
        for kind, owner in OWNERS.items()
    }
    refs = records(session, keys, archived=True)
    for kind, model in {
        "strains": Strain,
        "lines": CultureLine,
        "spores": SporeSource,
        "batches": GrowBatch,
    }.items():
        if not keys[kind]:
            continue
        # These owners have no reusable physical labels; resolve known identity in
        # one query per owner type, including archived catalog/provenance records.
        query = select(model).where(model.id.in_(keys[kind]))
        if kind == "strains":
            details = [(row, row.name) for row in session.scalars(query)]
        else:
            if kind == "batches":
                query = query.outerjoin(
                    CultureLine, CultureLine.id == GrowBatch.line_id
                )
                strain_column = CultureLine.strain_id
            else:
                strain_column = model.strain_id
            details = session.execute(
                query.add_columns(Strain.name).outerjoin(
                    Strain, Strain.id == strain_column
                )
            )
        for row, strain in details:
            title = row.name or row.id
            if strain and strain != title:
                title += " · " + strain
            refs[(kind, row.id)] = dict(
                record_id=row.id,
                title=title,
                target=f"/culture-library/{kind}/{row.id}",
                archived=row.status == "archived",
                stage=None,
            )

    items = []
    for event in events:
        kind = next(k for k, owner in OWNERS.items() if getattr(event, owner))
        code = getattr(event, OWNERS[kind])
        ref = refs.get(
            (kind, code),
            dict(
                record_id=code,
                title=code,
                target=f"/culture-library/{kind}/{code}",
                archived=False,
            ),
        )
        items.append(
            {
                **reference({"stage": None, **ref}),
                "event_id": event.id,
                "event_type": event.event_type,
                "record_type": kind,
                "occurred_at": event.occurred_at,
                "description": event.description,
            }
        )
    return dict(items=items, total=total, page=page, page_size=page_size)


def summary(session, settings, zone):
    today = local_day(zone)
    rows = records(session, today=today)
    doc = store.read(settings)
    all_items = candidates(session, rows, doc.preferences, today)
    visible = [
        a
        for a in all_items
        if not (
            (s := doc.alerts.get(a["alert_id"]))
            and s.fingerprint == a["fingerprint"]
            and (s.action == "dismiss" or s.until and s.until > now())
        )
    ]
    active = [
        r
        for r in rows.values()
        if r["lifecycle"] not in TERMINAL and r["stage"] not in TERMINAL
    ]
    counts = Counter(r["kind"] for r in active)
    stages = []
    for group, kind, label, path in [
        ("laboratory", "physical", "Laboratory", "/laboratory?filter="),
        ("spawn", "spawn", "Spawn", "/cultivation?view=spawn&filter="),
        (
            "fruiting",
            "fruiting",
            "Fruiting containers",
            "/cultivation?view=fruiting&fruiting=",
        ),
    ]:
        for stage in ("colonizing", "ready", "pinning", "fruiting"):
            if kind != "fruiting" and stage in {"pinning", "fruiting"}:
                continue
            stages.append(
                dict(
                    group=group,
                    label=label,
                    stage=stage,
                    count=sum(
                        r["kind"] == kind and r["stage"] == stage for r in active
                    ),
                    target=path + stage,
                )
            )
    start = today - timedelta(days=29)
    harvest = session.execute(
        select(
            func.count(HarvestEntry.id),
            func.count(HarvestEntry.wet_grams),
            func.sum(milligrams(HarvestEntry.wet_grams)),
            func.count(func.distinct(HarvestEntry.fruiting_id)),
        ).where(
            HarvestEntry.harvest_date >= start.isoformat(),
            HarvestEntry.harvest_date <= today.isoformat(),
        )
    ).one()
    return dict(
        counts=dict(
            active_cultures=counts["physical"],
            spawn_containers=counts["spawn"],
            fruiting_units=counts["fruiting"],
            open_alerts=len(visible),
        ),
        attention_items=visible[:25],
        attention_total=len(visible),
        active_cultivation=[
            reference(r)
            for r in sorted(
                active,
                key=lambda r: (r["stage"] == "ready", r["created_at"], r["record_id"]),
                reverse=True,
            )[:24]
        ],
        active_total=len(active),
        recent_activity=activity(session, page_size=15)["items"],
        stage_overview=stages,
        harvest_summary=dict(
            start_date=start,
            end_date=today,
            timezone=zone,
            harvest_count=harvest[0],
            wet_weight_count=harvest[1],
            wet_grams=(
                str(Decimal(harvest[2]) / 1000) if harvest[2] is not None else None
            ),
            fruiting_count=harvest[3],
        ),
        environmental_observations=[],
    )


@router.get("/preferences", response_model=store.Preferences)
def preferences(request: Request):
    return store.read(request.app.state.settings).preferences


@router.put("/preferences", response_model=store.Preferences)
def save_preferences(data: store.Preferences, request: Request):
    doc = store.read(request.app.state.settings)
    doc.preferences = data
    store.write(request.app.state.settings, doc)
    return data


@router.get("/activity")
def activity_page(
    request: Request,
    record_type: Literal[
        "all", "physical", "spawn", "fruiting", "strains", "lines", "spores", "batches"
    ] = "all",
    page: int = Query(1, ge=1, le=1000000),
    page_size: int = Query(25, ge=1, le=50),
):
    with Session(request.app.state.engine) as session:
        return activity(session, record_type, page, page_size)


@router.get("/attention")
def attention_page(
    request: Request,
    timezone: str = Query("UTC", max_length=100),
    hidden: bool = False,
    page: int = Query(1, ge=1, le=1000000),
):
    with Session(request.app.state.engine) as session:
        visible, suppressed, _, _, _ = attention(
            session, request.app.state.settings, local_day(timezone)
        )
        items = suppressed if hidden else visible
        return dict(
            items=items[(page - 1) * 25 : page * 25],
            total=len(items),
            page=page,
            page_size=25,
        )


class AttentionAction(BaseModel):
    alert_id: str = Field(max_length=120)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["dismiss", "snooze", "restore"]
    days: Literal[1, 3, 7] = 1
    timezone: str = Field(default="UTC", max_length=100)


@router.post("/attention")
def change_attention(data: AttentionAction, request: Request):
    with Session(request.app.state.engine) as session:
        _, _, current, doc, rows = attention(
            session, request.app.state.settings, local_day(data.timezone)
        )
        item = next((a for a in current if a["alert_id"] == data.alert_id), None)
        if item is None or item["fingerprint"] != data.fingerprint:
            raise HTTPException(
                409,
                "This alert changed or resolved. Refresh the dashboard before acting.",
            )

        # Preserve disabled/below-threshold dismissals while the same issue state
        # remains. Drop expired snoozes and records whose lifecycle really changed.
        def same_issue(key, state):
            parts = key.split(":", 2)
            record = rows.get(tuple(parts[1:])) if len(parts) == 3 else None
            return record and record.get("fingerprint") == state.fingerprint

        doc.alerts = {
            k: s
            for k, s in doc.alerts.items()
            if same_issue(k, s)
            and (s.action == "dismiss" or s.until and s.until > now())
        }
        doc.alerts.pop(data.alert_id, None)
        if data.action != "restore":
            if len(doc.alerts) >= 5000:
                raise HTTPException(
                    409, "Restore a hidden alert before hiding more alerts."
                )
            doc.alerts[data.alert_id] = store.Suppression(
                fingerprint=data.fingerprint,
                action=data.action,
                until=(
                    now() + timedelta(days=data.days)
                    if data.action == "snooze"
                    else None
                ),
            )
        store.write(request.app.state.settings, doc)
    return {"saved": True}
