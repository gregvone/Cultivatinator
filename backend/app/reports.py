"""Read-only per-container analytics; no inferred measurements or stored results."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query
from sqlalchemy import BigInteger, and_, cast, func, select, union
from sqlalchemy.orm import Session, load_only
from .models import (
    FruitingContainer,
    GrowBatch,
    BatchSource,
    FruitingSource,
    Spawn,
    CultureLine,
    Strain,
)
from .fruiting_models import FruitingRun, FruitingFlush, HarvestEntry
from .container_models import CultivationState, LabelAssignment, ContainerLabel
from .report_schemas import PerformanceReport

router = APIRouter(prefix="/api/reports", tags=["Read-only performance"])
SCALE = Decimal(1000)


def grams(value):
    return Decimal(value) / SCALE if value is not None else None


def measured_sum(values):
    known = [v for v in values if v is not None]
    return sum(known, Decimal(0)) if known else None


def mean(values):
    known = [Decimal(v) for v in values if v is not None]
    return (
        (sum(known) / len(known)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if known
        else None
    )


def average(values):
    return {
        "value": mean(values),
        "sample_count": sum(v is not None for v in values),
        "missing_count": sum(v is None for v in values),
    }


def day(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def elapsed(start, end):
    start, end = day(start), day(end)
    return (end - start).days if start and end and end >= start else None


def milligrams(column):
    # SQLite stores NUMERIC using numeric affinity. Sum integer milligrams,
    # not binary floating-point grams; division/averages use Decimal in Python.
    return cast(func.round(column * 1000), BigInteger)


def harvest_aggregate(*keys):
    return select(
        *keys,
        func.count(HarvestEntry.id).label("harvest_count"),
        func.count(HarvestEntry.wet_grams).label("wet_count"),
        func.count(HarvestEntry.dry_grams).label("dry_count"),
        func.sum(milligrams(HarvestEntry.wet_grams)).label("wet_mg"),
        func.sum(milligrams(HarvestEntry.dry_grams)).label("dry_mg"),
        func.min(HarvestEntry.harvest_date).label("first_harvest"),
    ).group_by(*keys)


def source_identities(session, codes=None):
    # Resolve all physical sources in one set query. Operational sources are
    # authoritative; otherwise preserve the existing shared/specific model.
    operational = select(
        FruitingRun.fruiting_id.label("fruiting_id"),
        Spawn.id.label("spawn_id"),
        Spawn.line_id.label("line_id"),
    ).join(Spawn, Spawn.id == FruitingRun.source_spawn_id)
    common = (
        select(
            FruitingContainer.id.label("fruiting_id"),
            Spawn.id.label("spawn_id"),
            Spawn.line_id.label("line_id"),
        )
        .join(GrowBatch, GrowBatch.id == FruitingContainer.batch_id)
        .outerjoin(FruitingRun, FruitingRun.fruiting_id == FruitingContainer.id)
        .where(FruitingRun.source_spawn_id.is_(None))
    )
    shared = (
        common.join(BatchSource, BatchSource.batch_id == GrowBatch.id)
        .join(Spawn, Spawn.id == BatchSource.spawn_id)
        .where(GrowBatch.allocation_mode == "shared")
    )
    specific = (
        common.join(
            FruitingSource,
            and_(
                FruitingSource.fruiting_id == FruitingContainer.id,
                FruitingSource.batch_id == GrowBatch.id,
            ),
        )
        .join(Spawn, Spawn.id == FruitingSource.spawn_id)
        .where(GrowBatch.allocation_mode == "specific")
    )
    # Acquired fruiting material retains its real culture line, without inventing spawn.
    acquired = (
        select(
            FruitingContainer.id.label("fruiting_id"),
            cast(None, Spawn.id.type).label("spawn_id"),
            GrowBatch.line_id.label("line_id"),
        )
        .join(GrowBatch, GrowBatch.id == FruitingContainer.batch_id)
        .where(GrowBatch.line_id.is_not(None))
    )
    sources = union(operational, shared, specific, acquired).subquery()
    query = select(sources)
    if codes is not None:
        query = query.where(sources.c.fruiting_id.in_(codes))
    sources = query.subquery()
    identities = defaultdict(list)
    for row in session.execute(
        select(
            sources.c.fruiting_id,
            sources.c.spawn_id,
            sources.c.line_id,
            CultureLine.name.label("line_name"),
            Strain.id.label("strain_id"),
            Strain.name.label("strain_name"),
            Strain.scientific_name,
        )
        .select_from(sources)
        .outerjoin(CultureLine, CultureLine.id == sources.c.line_id)
        .outerjoin(Strain, Strain.id == CultureLine.strain_id)
    ).mappings():
        identities[row["fruiting_id"]].append(row)

    return identities


def load_observations(session):
    harvests = harvest_aggregate(HarvestEntry.fruiting_id).subquery()
    pins = (
        select(
            FruitingFlush.fruiting_id,
            func.min(FruitingFlush.pinning_date).label("first_pin"),
        )
        .group_by(FruitingFlush.fruiting_id)
        .subquery()
    )
    latest_label = (
        select(
            LabelAssignment.fruiting_id,
            func.max(LabelAssignment.id).label("assignment_id"),
        )
        .where(LabelAssignment.fruiting_id.is_not(None))
        .group_by(LabelAssignment.fruiting_id)
        .subquery()
    )
    # This is one aggregate row per permanent FR, including historical/archived records.
    rows = session.execute(
        select(
            FruitingContainer,
            FruitingRun,
            CultivationState,
            ContainerLabel.code,
            harvests.c.harvest_count,
            harvests.c.wet_count,
            harvests.c.dry_count,
            harvests.c.wet_mg,
            harvests.c.dry_mg,
            harvests.c.first_harvest,
            pins.c.first_pin,
        )
        .outerjoin(FruitingRun, FruitingRun.fruiting_id == FruitingContainer.id)
        .outerjoin(
            CultivationState, CultivationState.fruiting_id == FruitingContainer.id
        )
        .outerjoin(harvests, harvests.c.fruiting_id == FruitingContainer.id)
        .outerjoin(pins, pins.c.fruiting_id == FruitingContainer.id)
        .outerjoin(latest_label, latest_label.c.fruiting_id == FruitingContainer.id)
        .outerjoin(LabelAssignment, LabelAssignment.id == latest_label.c.assignment_id)
        .outerjoin(ContainerLabel, ContainerLabel.id == LabelAssignment.label_id)
        .options(
            load_only(
                FruitingContainer.id,
                FruitingContainer.name,
                FruitingContainer.status,
                FruitingContainer.stage,
            ),
            load_only(
                FruitingRun.fruiting_id,
                FruitingRun.operation_id,
                FruitingRun.stage,
                FruitingRun.recipe_id,
                FruitingRun.recipe_snapshot,
                FruitingRun.spawning_date,
                FruitingRun.completed_date,
                FruitingRun.failed_date,
            ),
            load_only(
                CultivationState.id,
                CultivationState.phase,
                CultivationState.completed_date,
                CultivationState.failed_date,
            ),
        )
        .order_by(FruitingContainer.id)
    ).all()

    identities = source_identities(session)

    observations = []
    for (
        fr,
        run,
        state,
        label,
        count,
        wet_count,
        dry_count,
        wet_mg,
        dry_mg,
        first_harvest,
        first_pin,
    ) in rows:
        count, wet_count, dry_count = count or 0, wet_count or 0, dry_count or 0
        outcome = (
            run.stage
            if run and run.stage in {"completed", "failed"}
            else (
                state.phase
                if state and state.phase in {"completed", "failed"}
                else "completed" if fr.stage == "finished" else "active"
            )
        )
        outcome_date = (getattr(run, outcome + "_date", None) if run else None) or (
            getattr(state, outcome + "_date", None) if state else None
        )
        source_rows = identities[fr.id]
        lines = {
            s["line_id"]: s["line_name"] or s["line_id"]
            for s in source_rows
            if s["line_id"]
        }
        strains = {
            s["strain_id"]: s["strain_name"] for s in source_rows if s["strain_id"]
        }

        def identity(known, unknown):
            return (
                "unknown"
                if not known
                else "partial" if unknown else "mixed" if len(known) > 1 else "known"
            )

        line_identity = identity(
            lines, not source_rows or any(not s["line_id"] for s in source_rows)
        )
        strain_identity = identity(
            strains, not source_rows or any(not s["strain_id"] for s in source_rows)
        )
        scientific = {
            s["scientific_name"].strip()
            for s in source_rows
            if s["scientific_name"] and s["scientific_name"].strip()
        }
        species = (
            next(iter(scientific))
            if len(scientific) == 1
            and source_rows
            and all(
                s["scientific_name"] and s["scientific_name"].strip()
                for s in source_rows
            )
            else None
        )
        try:
            snapshot = (
                json.loads(run.recipe_snapshot) if run and run.recipe_snapshot else None
            )
        except (TypeError, ValueError):
            snapshot = None
        snapshot = snapshot if isinstance(snapshot, dict) else None
        recipe_id = (run.recipe_id or snapshot.get("id")) if run and snapshot else None
        observations.append(
            {
                "id": fr.id,
                "label": label,
                "name": fr.name,
                "outcome": outcome,
                "outcome_date": (
                    day(outcome_date).isoformat() if day(outcome_date) else None
                ),
                "archived": fr.status == "archived",
                "legacy": not run or not run.operation_id,
                "strain_identity": strain_identity,
                "line_identity": line_identity,
                "strain_ids": sorted(strains),
                "line_ids": sorted(lines),
                "spawn_ids": sorted(
                    {s["spawn_id"] for s in source_rows if s["spawn_id"]}
                ),
                "strain_names": [strains[k] for k in sorted(strains)],
                "line_names": [lines[k] for k in sorted(lines)],
                "species": species,
                "recipe_id": recipe_id,
                "recipe_name": snapshot.get("name") if recipe_id else None,
                "recipe_revision": (
                    snapshot.get("revision")
                    if recipe_id and isinstance(snapshot.get("revision"), int)
                    else None
                ),
                "harvest_count": count,
                "wet_measurement_count": wet_count,
                "known_wet_grams": grams(wet_mg),
                "complete_wet": count > 0 and count == wet_count,
                "known_dry_grams": grams(dry_mg),
                "complete_dry": count > 0 and count == dry_count,
                "days_to_first_pinning": elapsed(
                    run.spawning_date if run else None, first_pin
                ),
                "days_to_first_harvest": elapsed(
                    run.spawning_date if run else None, first_harvest
                ),
                "cycle_days": (
                    elapsed(run.spawning_date if run else None, outcome_date)
                    if outcome == "completed"
                    else None
                ),
                "_snapshot": snapshot,
            }
        )
    return observations


def statistics(rows):
    completed = [r for r in rows if r["outcome"] == "completed"]
    failed = [r for r in rows if r["outcome"] == "failed"]
    qualifying = [r for r in completed if r["complete_wet"]]
    return {
        "completed": len(completed),
        "failed": len(failed),
        "terminal_count": len(rows),
        "failure_rate_percent": (
            (Decimal(len(failed)) * 100 / len(rows)).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            if rows
            else None
        ),
        "qualifying_containers": len(qualifying),
        "excluded_incomplete_wet": len(completed) - len(qualifying),
        "average_wet_grams": mean([r["known_wet_grams"] for r in qualifying]),
        "qualifying_wet_total_grams": measured_sum(
            [r["known_wet_grams"] for r in qualifying]
        ),
        "total_known_wet_grams": measured_sum([r["known_wet_grams"] for r in rows]),
        "completed_known_wet_grams": measured_sum(
            [r["known_wet_grams"] for r in completed]
        ),
        "failed_known_wet_grams": measured_sum([r["known_wet_grams"] for r in failed]),
        "wet_measured_containers": sum(r["known_wet_grams"] is not None for r in rows),
        "wet_measurement_count": sum(r["wet_measurement_count"] for r in rows),
        "harvest_count": sum(r["harvest_count"] for r in rows),
        "distinct_spawn_sources": len({s for r in qualifying for s in r["spawn_ids"]}),
        "containers_without_known_spawn": sum(not r["spawn_ids"] for r in qualifying),
        "average_dry_grams": average(
            [r["known_dry_grams"] if r["complete_dry"] else None for r in completed]
        ),
        **{
            key: average([r[key] for r in completed])
            for key in ["days_to_first_pinning", "days_to_first_harvest", "cycle_days"]
        },
    }


def comparisons(rows, group_by):
    buckets = defaultdict(list)
    for r in rows:
        if group_by == "recipe":
            key = r["recipe_id"] or "unknown"
        else:
            identity = r[group_by + "_identity"]
            key = r[group_by + "_ids"][0] if identity == "known" else identity
        buckets[key].append(r)
    result = []
    for key, group in buckets.items():
        known = key not in {"unknown", "mixed", "partial"}
        ordered = sorted(
            group,
            key=lambda r: (
                r["recipe_revision"] is None,
                r["recipe_revision"] or 0,
                r["id"],
            ),
        )
        name = (
            (ordered[0]["recipe_name"] or key)
            if group_by == "recipe" and known
            else (
                group[0][group_by + "_names"][0]
                if known
                else {
                    "unknown": "Unknown provenance",
                    "mixed": "Mixed "
                    + ("strains" if group_by == "strain" else "culture lines"),
                    "partial": "Partial identification",
                }[key]
            )
        )
        stats = statistics(group)
        revisions = []
        if group_by == "recipe" and known:
            revs = defaultdict(list)
            for r in ordered:
                revs[r["recipe_revision"]].append(r)
            revisions = [
                {
                    "revision": rev,
                    "name": items[0]["recipe_name"] or key,
                    "snapshot": items[0]["_snapshot"],
                    "stats": statistics(items),
                    "record_ids": [r["id"] for r in items],
                }
                for rev, items in revs.items()
            ]
        result.append(
            {
                "key": key,
                "name": name,
                "identity": "known" if known else key,
                "ranked": known and stats["qualifying_containers"] > 0,
                "preliminary": stats["qualifying_containers"] < 3,
                "stats": stats,
                "record_ids": [r["id"] for r in group],
                "revisions": revisions,
            }
        )
    return sorted(
        result,
        key=lambda g: (
            not g["ranked"],
            -(g["stats"]["average_wet_grams"] or Decimal(0)),
            g["name"].casefold(),
            g["key"],
        ),
    )


def flush_performance(session, rows):
    completed_ids = {r["id"] for r in rows if r["outcome"] == "completed"}
    grouped = harvest_aggregate(
        HarvestEntry.fruiting_id, HarvestEntry.flush_number
    ).subquery()
    buckets = defaultdict(list)
    # Read every flush in one query, avoiding an unbounded SQL IN parameter list.
    for r in session.execute(
        select(
            FruitingFlush.fruiting_id,
            FruitingFlush.number,
            grouped.c.harvest_count,
            grouped.c.wet_count,
            grouped.c.wet_mg,
        ).outerjoin(
            grouped,
            and_(
                grouped.c.fruiting_id == FruitingFlush.fruiting_id,
                grouped.c.flush_number == FruitingFlush.number,
            ),
        )
    ).mappings():
        if r["fruiting_id"] in completed_ids:
            buckets[r["number"]].append(r)
    results = []
    for number, flushes in sorted(buckets.items()):
        qualified = [
            f
            for f in flushes
            if f["harvest_count"] and f["harvest_count"] == f["wet_count"]
        ]
        results.append(
            {
                "number": number,
                "containers_reached": len(flushes),
                "qualifying_containers": len(qualified),
                "excluded_incomplete_wet": len(flushes) - len(qualified),
                "average_wet_grams": mean([grams(f["wet_mg"]) for f in qualified]),
                "total_known_wet_grams": measured_sum(
                    [grams(f["wet_mg"]) for f in flushes]
                ),
                "record_ids": sorted(f["fruiting_id"] for f in flushes),
                "qualifying_record_ids": sorted(f["fruiting_id"] for f in qualified),
            }
        )
    return results


@router.get("/performance", response_model=PerformanceReport)
def performance(
    request: Request,
    group_by: Literal["strain", "line", "recipe"] = "strain",
    strain_id: str | None = Query(default=None, max_length=32),
    species: str | None = Query(default=None, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Start date must be on or before end date")
    with Session(request.app.state.engine) as session:
        # One consistent read snapshot across the fixed number of aggregate queries.
        session.connection().exec_driver_sql("BEGIN")
        options = [
            {"id": s.id, "name": s.name, "scientific_name": s.scientific_name}
            for s in session.scalars(select(Strain).order_by(Strain.name, Strain.id))
        ]
        species_options = sorted(
            {
                s["scientific_name"].strip()
                for s in options
                if s["scientific_name"] and s["scientific_name"].strip()
            }
        )
        if strain_id is not None and strain_id not in {s["id"] for s in options}:
            raise HTTPException(422, "Unknown strain filter")
        if species is not None and species not in species_options:
            raise HTTPException(422, "Unknown recorded species filter")
        matching = [
            r
            for r in load_observations(session)
            if (
                strain_id is None
                or r["strain_identity"] == "known"
                and r["strain_ids"] == [strain_id]
            )
            and (species is None or r["species"] == species)
        ]
        active = [r for r in matching if r["outcome"] == "active"]
        terminals = [r for r in matching if r["outcome"] != "active"]
        bounded = start_date is not None or end_date is not None
        undated = sum(not r["outcome_date"] for r in terminals) if bounded else 0
        rows = [
            r
            for r in terminals
            if not bounded
            or r["outcome_date"]
            and (start_date is None or day(r["outcome_date"]) >= start_date)
            and (end_date is None or day(r["outcome_date"]) <= end_date)
        ]
        return {
            "group_by": group_by,
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "label": (
                    f"{start_date or 'Beginning'} through {end_date or 'present'} (inclusive)"
                    if bounded
                    else "All time"
                ),
            },
            "options": {"strains": options, "species": species_options},
            "summary": statistics(rows),
            "groups": comparisons(rows, group_by),
            "flushes": flush_performance(session, rows),
            "records": rows,
            "active_records": active,
            "matching_containers": len(matching),
            "terminal_containers_outside_period": len(terminals) - len(rows) - undated,
            "undated_terminal_excluded": undated,
            "legacy_containers": sum(r["legacy"] for r in rows),
        }
