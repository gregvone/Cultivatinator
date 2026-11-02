"""Ancestry is genetic; grow links document physical provenance, never consumption."""

from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .models import (
    CultureLine,
    PhysicalCulture,
    Spawn,
    GrowBatch,
    BatchSource,
    FruitingContainer,
    FruitingSource,
    SporeSource,
    SporeCollection,
    LineOrigin,
    LineParent,
)
from .provenance_sources import spawn_sources, source_lines
from .library import (
    transaction,
    allocate,
    record,
    event,
    output,
    resolve_strain,
    PREFIX,
    receive_culture,
)
from .library_schemas import Kind, ReceiveCulture, ReceiveResult, RecordOut
from .provenance_schemas import (
    AcquisitionInput,
    AcquisitionResult,
    GrowInput,
    GrowResult,
    EstablishInput,
    CollectInput,
    AncestryCorrection,
    ProvenanceOut,
    ParentInput,
    Relationship,
)

router = APIRouter(prefix="/api/provenance", tags=["Lineage and provenance"])


def iso(value):
    return value.isoformat() if value else None


def new_line(session, data, strain_id):
    line = CultureLine(
        id=allocate(session, "CL"), strain_id=strain_id, **data.model_dump(mode="json")
    )
    session.add(line)
    session.flush()
    event(
        session,
        "lines",
        line.id,
        "created",
        "Independent acquired culture line registered; external ancestry unknown",
    )
    session.add(LineOrigin(line_id=line.id, origin_type="external"))
    return line


def physical_material(session, line, material):
    items = []
    if material:
        batch = str(uuid4())
        for _ in range(material.count):
            item = PhysicalCulture(
                id=allocate(session, PREFIX[material.material_type]),
                line_id=line.id,
                registration_batch=batch,
                **material.model_dump(exclude={"count"}),
            )
            session.add(item)
            session.flush()
            event(
                session,
                "physical",
                item.id,
                "created",
                f"Established physical culture under {line.id}; starting quantity only",
            )
            items.append(output(session, "physical", item))
    return items


@router.post("/acquisitions", response_model=AcquisitionResult, status_code=201)
def acquire(data: AcquisitionInput, request: Request):
    if data.entry_type == "culture":
        result = receive_culture(
            ReceiveCulture.model_validate(
                data.model_dump(include=set(ReceiveCulture.model_fields))
            ),
            request,
        )
        return AcquisitionResult(line=result.line, records=result.physical)
    with transaction(request) as session:
        strain = resolve_strain(session, data.strain_id, data.inline_strain)
        if data.existing_line_id:
            line = record(session, "lines", data.existing_line_id, active=True)
            if line.strain_id != strain:
                raise HTTPException(
                    422, "Culture line must match the selected or unknown strain"
                )
        else:
            line = new_line(session, data.line, strain)
        acquired = iso(data.acquisition_date)
        fields = dict(
            name=data.name,
            notes=data.notes,
            quantity=data.quantity,
            unit=data.unit,
            storage_location=data.storage_location,
            acquisition_date=acquired,
            stage=data.stage,
        )
        items, batch_out = [], None
        if data.entry_type.startswith("spawn_"):
            for _ in range(data.count):
                item = Spawn(
                    id=allocate(
                        session, "SJ" if data.entry_type == "spawn_jar" else "SB"
                    ),
                    line_id=line.id,
                    strain_id=line.strain_id,
                    supplier=data.supplier or line.supplier,
                    supplier_reference=data.supplier_reference
                    or line.supplier_reference,
                    supplier_batch=data.supplier_batch or line.supplier_batch,
                    material_type=data.entry_type,
                    **fields,
                )
                session.add(item)
                session.flush()
                event(
                    session,
                    "spawn",
                    item.id,
                    "acquired",
                    "Acquired colonized spawn; no preparation or inoculation history asserted",
                )
                items.append(output(session, "spawn", item))
        else:
            batch = GrowBatch(
                id=allocate(session, "GB"),
                name=data.name,
                notes=data.notes,
                supplier=data.supplier or line.supplier,
                supplier_reference=data.supplier_reference or line.supplier_reference,
                supplier_batch=data.supplier_batch or line.supplier_batch,
                batch_origin="acquired",
                allocation_mode="shared",
                line_id=line.id,
                acquisition_date=acquired,
            )
            session.add(batch)
            session.flush()
            event(
                session,
                "batches",
                batch.id,
                "acquired",
                "Acquired fruiting material; substrate and external spawn sources unknown",
            )
            for _ in range(data.count):
                item = FruitingContainer(
                    id=allocate(session, "FR"),
                    batch_id=batch.id,
                    material_type=(
                        "bag" if data.entry_type == "fruiting_bag" else "block"
                    ),
                    **fields,
                )
                session.add(item)
                session.flush()
                event(
                    session,
                    "fruiting",
                    item.id,
                    "acquired",
                    f"Acquired fruiting container in {batch.id}",
                )
                items.append(output(session, "fruiting", item))
            batch_out = output(session, "batches", batch)
        event(
            session,
            "lines",
            line.id,
            "material_registered",
            f"{len(items)} acquired container(s) registered",
        )
        return AcquisitionResult(
            line=output(session, "lines", line), records=items, batch=batch_out
        )


def mixing(lines):
    warnings = []
    if len(lines) > 1:
        warnings.append("Mixed culture lines: provenance does not imply hybridization")
    if len({line.strain_id for line in lines if line.strain_id}) > 1:
        warnings.append("Mixed named strains: no synthetic strain is created")
    if any(line.strain_id is None for line in lines):
        warnings.append("Some strain identities are unknown")
    return warnings


@router.post("/grows", response_model=GrowResult, status_code=201)
def grow(data: GrowInput, request: Request):
    with transaction(request) as session:
        for code in data.source_ids:
            record(session, "spawn", code, active=True)
        batch = GrowBatch(
            id=allocate(session, "GB"),
            name=data.name,
            notes=data.notes,
            batch_origin="prepared",
            allocation_mode=data.allocation_mode,
            acquisition_date=iso(data.acquisition_date),
        )
        session.add(batch)
        session.flush()
        for code in data.source_ids:
            session.add(BatchSource(batch_id=batch.id, spawn_id=code))
            event(
                session,
                "spawn",
                code,
                "provenance_registered",
                f"Manually documented source for {batch.id}; no consumption or status change",
            )
        session.flush()
        items = []
        for container in data.containers:
            item = FruitingContainer(
                id=allocate(session, "FR"),
                batch_id=batch.id,
                **container.model_dump(mode="json", exclude={"source_ids"}),
            )
            session.add(item)
            session.flush()
            for code in container.source_ids:
                session.add(
                    FruitingSource(
                        batch_id=batch.id, fruiting_id=item.id, spawn_id=code
                    )
                )
            event(
                session,
                "fruiting",
                item.id,
                "registered",
                f"Manually documented membership in {batch.id}; no consumption event",
            )
            items.append(output(session, "fruiting", item))
        event(
            session,
            "batches",
            batch.id,
            "registered",
            "User-prepared grow registered as manual provenance; no spawn consumed",
        )
        session.flush()
        return GrowResult(
            batch=output(session, "batches", batch),
            containers=items,
            warnings=mixing(source_lines(session, batch)),
        )


def parents_for_fruiting(session, code):
    fruiting = record(session, "fruiting", code)
    batch = record(session, "batches", fruiting.batch_id)
    return source_lines(session, batch, fruiting)


def set_parents(session, code, parents):
    # Check both possible and confirmed edges, so uncertainty cannot hide a cycle.
    graph = {}
    for edge in session.scalars(select(LineParent).where(LineParent.line_id != code)):
        graph.setdefault(edge.line_id, set()).add(edge.parent_id)
    graph[code] = {p.parent_id for p in parents}
    for parent in parents:
        record(session, "lines", parent.parent_id)
        pending, seen = [parent.parent_id], set()
        while pending:
            current = pending.pop()
            if current == code:
                raise HTTPException(422, "Circular ancestry is not allowed")
            if current not in seen:
                seen.add(current)
                pending.extend(graph.get(current, []))
    session.execute(delete(LineParent).where(LineParent.line_id == code))
    for parent in parents:
        session.add(LineParent(line_id=code, **parent.model_dump()))
    session.flush()


@router.post("/{kind}/{code}/establish", response_model=ReceiveResult, status_code=201)
def establish(kind: Kind, code: str, data: EstablishInput, request: Request):
    if kind not in {"lines", "spores", "fruiting"}:
        raise HTTPException(
            422,
            "Establish from a spore source, fruiting container, or selected culture line",
        )
    with transaction(request) as session:
        source = record(session, kind, code, active=True)
        if data.prepared_id and (kind != "spores" or data.material is not None):
            raise HTTPException(
                422,
                "Bind a pending agar establishment from spores without new material",
            )
        parents, strain_id = [], None
        if kind == "lines":
            if data.unknown_strain:
                raise HTTPException(422, "An isolate preserves its parent strain")
            origin_type, strain_id = "isolate", source.strain_id
            parents = [ParentInput(parent_id=code, confidence="confirmed")]
        elif kind == "fruiting":
            origin_type = "clone"
            lines = parents_for_fruiting(session, code)
            parents = [
                ParentInput(
                    parent_id=l.id,
                    confidence="confirmed" if len(lines) == 1 else "possible",
                )
                for l in lines
            ]
            strain_ids = {l.strain_id for l in lines}
            strain_id = next(iter(strain_ids)) if len(strain_ids) == 1 else None
        else:
            origin_type, strain_id = "spores", source.strain_id
            collection = session.get(SporeCollection, code)
            if collection:
                parents = [
                    ParentInput(parent_id=l.id, confidence="possible")
                    for l in parents_for_fruiting(session, collection.fruiting_id)
                ]
        if data.unknown_strain:
            strain_id = None
        line = CultureLine(
            id=allocate(session, "CL"),
            name=data.name,
            notes=data.notes,
            strain_id=strain_id,
            origin="other",
        )
        session.add(line)
        session.flush()
        session.add(
            LineOrigin(
                line_id=line.id,
                origin_type=origin_type,
                spore_id=code if kind == "spores" else None,
                fruiting_id=code if kind == "fruiting" else None,
                origin_date=iso(data.origin_date),
                notes=data.notes,
            )
        )
        set_parents(session, line.id, parents)
        event(
            session,
            "lines",
            line.id,
            "established",
            f"Successfully established {origin_type} from {code}; no purity or hybrid claim",
        )
        event(
            session,
            kind,
            code,
            "descendant_established",
            f"Independent {origin_type} culture line {line.id} established",
        )
        if data.prepared_id:
            from .preparation import bind_established

            established = bind_established(session, line, data.prepared_id, code)
            items = [output(session, "physical", established)]
        else:
            items = physical_material(session, line, data.material)
        return ReceiveResult(line=output(session, "lines", line), physical=items)


@router.post("/fruiting/{code}/collect", response_model=RecordOut, status_code=201)
def collect(code: str, data: CollectInput, request: Request):
    with transaction(request) as session:
        record(session, "fruiting", code, active=True)
        lines = parents_for_fruiting(session, code)
        strains = {l.strain_id for l in lines}
        strain = next(iter(strains)) if len(strains) == 1 else None
        values = data.model_dump(exclude={"collection_date"})
        spore = SporeSource(id=allocate(session, "SP"), strain_id=strain, **values)
        session.add(spore)
        session.flush()
        session.add(
            SporeCollection(
                spore_id=spore.id,
                fruiting_id=code,
                collection_date=iso(data.collection_date),
            )
        )
        event(
            session,
            "spores",
            spore.id,
            "collected",
            f"Spores collected from {code}; physical provenance is not confirmed genetic parentage",
        )
        event(
            session,
            "fruiting",
            code,
            "spores_collected",
            f"Spore source {spore.id} collected",
        )
        return output(session, "spores", spore)


@router.put("/lines/{code}/ancestry", response_model=ProvenanceOut)
def correct(code: str, data: AncestryCorrection, request: Request):
    with transaction(request) as session:
        record(session, "lines", code)
        origin = session.get(LineOrigin, code)
        revision = origin.revision if origin else 0
        if revision != data.expected_revision:
            raise HTTPException(409, "Ancestry changed; reload before correcting")
        old = [
            dict(parent_id=p.parent_id, confidence=p.confidence)
            for p in session.scalars(
                select(LineParent).where(LineParent.line_id == code)
            )
        ]
        if origin and origin.origin_type == "clone":
            possible = {l.id for l in parents_for_fruiting(session, origin.fruiting_id)}
            if any(p.parent_id not in possible for p in data.parents):
                raise HTTPException(
                    422,
                    "Clone parent must be a documented source of its fruiting container",
                )
        if origin and origin.origin_type == "isolate":
            if [p.model_dump() for p in data.parents] != old:
                raise HTTPException(
                    422,
                    "Selected isolate parent is immutable; register a separate corrected line",
                )
        set_parents(session, code, data.parents)
        if not origin:
            origin = LineOrigin(line_id=code, origin_type="other", revision=0)
            session.add(origin)
        origin.revision = revision + 1

        # Store full previous relationships and reason without truncating long notes.
        def parent_description(parents):
            return (
                ", ".join(f"{p['parent_id']} ({p['confidence']})" for p in parents)
                or "Unknown"
            )

        before = parent_description(old)
        after = parent_description([p.model_dump() for p in data.parents])
        for label, content in [
            ("Previous ancestry", before),
            ("Corrected ancestry", after),
            ("Correction reason", data.reason),
        ]:
            for offset in range(0, len(content), 400):
                event(
                    session,
                    "lines",
                    code,
                    "ancestry_corrected",
                    f"Revision {origin.revision} {label}: {content[offset:offset+400]}",
                )
        session.flush()
        return describe(session, "lines", code)


def describe(session, kind, code):
    row = record(session, kind, code)
    result = ProvenanceOut()
    linked = set()

    def link(label, target_kind, target):
        if target and (label, target_kind, target.id) not in linked:
            linked.add((label, target_kind, target.id))
            result.relationships.append(
                Relationship(label=label, record=output(session, target_kind, target))
            )

    def lines_for(batch, fruiting=None):
        lines = source_lines(session, batch, fruiting)
        result.warnings = mixing(lines)
        if not lines:
            result.warnings.append("Source allocation unknown; no parent inferred")
        for line in lines:
            link("Physical provenance · culture line", "lines", line)
            if line.strain_id:
                link(
                    "Contributing strain · physical provenance",
                    "strains",
                    record(session, "strains", line.strain_id),
                )
        for source in spawn_sources(session, batch, fruiting):
            link("Physical source · spawn", "spawn", source)

    if kind == "lines":
        origin = session.get(LineOrigin, code)
        if origin:
            result.origin_type, result.origin_date, result.notes, result.revision = (
                origin.origin_type,
                origin.origin_date,
                origin.notes,
                origin.revision,
            )
            if origin.spore_id:
                link(
                    "Original spore source",
                    "spores",
                    record(session, "spores", origin.spore_id),
                )
            if origin.fruiting_id:
                for candidate in parents_for_fruiting(session, origin.fruiting_id):
                    link(
                        "Documented fruiting source line · not a parent assertion",
                        "lines",
                        candidate,
                    )
                link(
                    "Tissue source · fruiting container",
                    "fruiting",
                    record(session, "fruiting", origin.fruiting_id),
                )
        for edge in session.scalars(
            select(LineParent).where(LineParent.line_id == code)
        ):
            result.parents.append(
                ParentInput(parent_id=edge.parent_id, confidence=edge.confidence)
            )
            link(
                (
                    "Confirmed genetic parent"
                    if edge.confidence == "confirmed"
                    else "Possible genetic parent"
                ),
                "lines",
                record(session, "lines", edge.parent_id),
            )
        result.ancestry_status = (
            "confirmed"
            if any(p.confidence == "confirmed" for p in result.parents)
            else "uncertain" if result.parents else "unknown"
        )
        for edge in session.scalars(
            select(LineParent).where(LineParent.parent_id == code)
        ):
            link(
                (
                    "Confirmed descendant"
                    if edge.confidence == "confirmed"
                    else "Possible descendant"
                ),
                "lines",
                record(session, "lines", edge.line_id),
            )
        for model, target_kind in [
            (PhysicalCulture, "physical"),
            (Spawn, "spawn"),
            (GrowBatch, "batches"),
        ]:
            for item in session.scalars(select(model).where(model.line_id == code)):
                link("Associated material", target_kind, item)
    elif kind == "spores":
        collection = session.get(SporeCollection, code)
        if collection:
            result.origin_date = collection.collection_date
            link(
                "Physical collection source",
                "fruiting",
                record(session, "fruiting", collection.fruiting_id),
            )
        for origin in session.scalars(
            select(LineOrigin).where(LineOrigin.spore_id == code)
        ):
            link(
                "Independently established from spores",
                "lines",
                record(session, "lines", origin.line_id),
            )
    elif kind in {"batches", "fruiting"}:
        batch = row if kind == "batches" else record(session, "batches", row.batch_id)
        result.origin_type, result.allocation_mode = (
            batch.batch_origin,
            batch.allocation_mode,
        )
        lines_for(batch, row if kind == "fruiting" else None)
        if kind == "batches":
            for item in session.scalars(
                select(FruitingContainer).where(FruitingContainer.batch_id == code)
            ):
                link("Grow-batch member", "fruiting", item)
        else:
            link("Grow-batch membership", "batches", batch)
            for origin in session.scalars(
                select(LineOrigin).where(LineOrigin.fruiting_id == code)
            ):
                link(
                    "Established tissue clone",
                    "lines",
                    record(session, "lines", origin.line_id),
                )
            for collection in session.scalars(
                select(SporeCollection).where(SporeCollection.fruiting_id == code)
            ):
                link(
                    "Collected spore source",
                    "spores",
                    record(session, "spores", collection.spore_id),
                )
    elif kind in {"physical", "spawn"}:
        link("Culture line", "lines", record(session, "lines", row.line_id))
        if kind == "spawn":
            for source in session.scalars(
                select(BatchSource).where(BatchSource.spawn_id == code)
            ):
                link(
                    "Manual grow provenance · not consumption",
                    "batches",
                    record(session, "batches", source.batch_id),
                )
    return result


@router.get("/{kind}/{code}", response_model=ProvenanceOut)
def provenance(kind: Kind, code: str, request: Request):
    with Session(request.app.state.engine) as session:
        return describe(session, kind, code)
