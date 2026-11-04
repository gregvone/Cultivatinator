"""Read-only genetic graph; physical provenance never manufactures genetic edges."""

from collections import defaultdict
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import (
    Strain,
    CultureLine,
    LineOrigin,
    LineParent,
    PhotoAttachment,
    PhysicalCulture,
    Spawn,
    GrowBatch,
    BatchSource,
    FruitingSource,
    FruitingContainer,
)
from .library import photo_out, record
from .backup_store import atomic_json

router = APIRouter(prefix="/api/genetics", tags=["Genetics"])


class PhotoChoices(BaseModel):
    version: int = 1
    photos: dict[str, str] = Field(default_factory=dict)


class PhotoChoice(BaseModel):
    photo_id: str | None = Field(default=None, max_length=36)


def choices(settings):
    path = Path(settings.data_dir) / "settings" / "genetics.json"
    try:
        if not path.exists():
            return PhotoChoices()
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError()
        result = PhotoChoices.model_validate_json(path.read_bytes())
        if result.version != 1:
            raise ValueError()
        return result
    except (OSError, ValueError, ValidationError) as exc:
        raise HTTPException(
            503,
            "Genetics photo settings could not be read; repair or restore settings/genetics.json.",
        ) from exc


def snapshot(session, settings):
    # Fixed number of bulk queries, independent of line count.
    strains = session.scalars(select(Strain).order_by(Strain.name, Strain.id)).all()
    lines = session.scalars(select(CultureLine).order_by(CultureLine.id)).all()
    origins = {o.line_id: o for o in session.scalars(select(LineOrigin))}
    edges = session.scalars(
        select(LineParent).order_by(LineParent.line_id, LineParent.parent_id)
    ).all()
    physical = {p.id: p.line_id for p in session.scalars(select(PhysicalCulture))}
    spawn = {p.id: p.line_id for p in session.scalars(select(Spawn))}
    batches = {b.id: b for b in session.scalars(select(GrowBatch))}
    batch_lines, specific_lines = defaultdict(set), defaultdict(set)
    for b in batches.values():
        if b.line_id:
            batch_lines[b.id].add(b.line_id)
    for s in session.scalars(select(BatchSource)):
        batch_lines[s.batch_id].add(spawn[s.spawn_id])
    for s in session.scalars(select(FruitingSource)):
        specific_lines[s.fruiting_id].add(spawn[s.spawn_id])
    fruits = defaultdict(list)
    fruit_lines = {}
    for f in session.scalars(select(FruitingContainer).order_by(FruitingContainer.id)):
        b = batches[f.batch_id]
        ids = (
            set(specific_lines[f.id])
            if b.allocation_mode == "specific"
            else set(batch_lines[b.id])
        )
        if b.line_id:
            ids.add(b.line_id)
        fruit_lines[f.id] = ids
        if f.status == "active":
            for line_id in ids:
                fruits[line_id].append(
                    {"id": f.id, "name": f.name or f.id, "kind": "fruiting"}
                )
    photos, strain_covers = defaultdict(list), {}
    root = Path(settings.data_dir) / "photos"
    for p in session.scalars(
        select(PhotoAttachment).order_by(PhotoAttachment.created_at, PhotoAttachment.id)
    ):
        # Broken disk references are omitted too, allowing the next fallback.
        if not (root / p.thumbnail).is_file() or not (root / p.filename).is_file():
            continue
        out = photo_out(p).model_dump()
        if p.strain_id and p.is_cover:
            strain_covers[p.strain_id] = out
        ids = (
            {p.line_id}
            if p.line_id
            else (
                {physical[p.physical_id]}
                if p.physical_id
                else (
                    {spawn[p.spawn_id]}
                    if p.spawn_id
                    else fruit_lines.get(p.fruiting_id, set())
                )
            )
        )
        for line_id in ids:
            photos[line_id].append(
                {
                    **out,
                    "owner_id": p.line_id
                    or p.physical_id
                    or p.spawn_id
                    or p.fruiting_id,
                    "line_cover": bool(p.line_id and p.is_cover),
                }
            )
    selected = choices(settings).photos
    nodes = []
    for line in lines:
        associated = photos[line.id]
        cover = next((p for p in associated if p["line_cover"]), None)
        representative = next(
            (p for p in associated if p["id"] == selected.get(line.id)), None
        )
        photo = cover or representative or strain_covers.get(line.strain_id)
        origin = origins.get(line.id)
        nodes.append(
            {
                "id": line.id,
                "name": line.name or line.id,
                "strain_id": line.strain_id,
                "status": line.status,
                "origin_type": origin.origin_type if origin else "unknown",
                "source": (
                    {"kind": "spores", "id": origin.spore_id}
                    if origin and origin.spore_id
                    else (
                        {"kind": "fruiting", "id": origin.fruiting_id}
                        if origin and origin.fruiting_id
                        else None
                    )
                ),
                "photo": photo,
                "photo_source": (
                    "line cover"
                    if cover
                    else (
                        "representative"
                        if representative
                        else "strain cover" if photo else "none"
                    )
                ),
                "photos": associated,
                "fruiting_sources": fruits[line.id],
                "can_isolate": line.status == "active",
            }
        )
    return {
        "strains": [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "cover": strain_covers.get(s.id),
            }
            for s in strains
        ],
        "nodes": nodes,
        "edges": [
            {"parent_id": e.parent_id, "line_id": e.line_id, "confidence": e.confidence}
            for e in edges
        ],
    }


@router.get("")
def graph(request: Request):
    with Session(request.app.state.engine) as session:
        return snapshot(session, request.app.state.settings)


@router.put("/lines/{code}/photo")
def choose_photo(code: str, data: PhotoChoice, request: Request):
    with Session(request.app.state.engine) as session:
        record(session, "lines", code)
        node = next(
            n
            for n in snapshot(session, request.app.state.settings)["nodes"]
            if n["id"] == code
        )
        if data.photo_id and data.photo_id not in {p["id"] for p in node["photos"]}:
            raise HTTPException(
                422, "Select an existing photograph associated with this culture line"
            )
        document = choices(request.app.state.settings)
        if data.photo_id:
            document.photos[code] = data.photo_id
        else:
            document.photos.pop(code, None)
        try:
            atomic_json(
                Path(request.app.state.settings.data_dir)
                / "settings"
                / "genetics.json",
                document.model_dump(),
            )
        except OSError as exc:
            raise HTTPException(
                503, "Genetics photo settings could not be saved"
            ) from exc
    return {"saved": True}
