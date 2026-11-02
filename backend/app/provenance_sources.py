"""Read-only physical source resolution shared by provenance and record display."""

from sqlalchemy import select
from .models import BatchSource, CultureLine, FruitingSource, GrowBatch, Spawn, Strain


def spawn_sources(session, batch, fruiting=None):
    if fruiting is not None and batch.allocation_mode == "specific":
        statement = (
            select(Spawn)
            .join(FruitingSource, FruitingSource.spawn_id == Spawn.id)
            .where(
                FruitingSource.batch_id == batch.id,
                FruitingSource.fruiting_id == fruiting.id,
            )
        )
    else:
        statement = (
            select(Spawn)
            .join(BatchSource, BatchSource.spawn_id == Spawn.id)
            .where(BatchSource.batch_id == batch.id)
        )
    return session.scalars(statement.order_by(Spawn.id)).all()


def source_lines(session, batch, fruiting=None):
    ids = {source.line_id for source in spawn_sources(session, batch, fruiting)}
    if batch.line_id:
        ids.add(batch.line_id)
    return session.scalars(
        select(CultureLine).where(CultureLine.id.in_(ids)).order_by(CultureLine.id)
    ).all()


def fruiting_strain_identity(session, fruiting):
    """Derive present-day display from existing links, including archived sources.

    A partial identity never fills the legacy single-strain fields: doing so
    would present the known portion as the complete identity.
    """
    batch = session.get(GrowBatch, fruiting.batch_id)
    lines = source_lines(session, batch, fruiting)
    strain_ids = {line.strain_id for line in lines if line.strain_id}
    strains = session.scalars(
        select(Strain).where(Strain.id.in_(strain_ids)).order_by(Strain.name, Strain.id)
    ).all()
    unknown = not lines or any(line.strain_id is None for line in lines)
    identification = (
        "unknown"
        if not strains
        else "partial" if unknown else "mixed" if len(strains) > 1 else "known"
    )
    single = strains[0] if identification == "known" else None
    return {
        "strain_id": single.id if single else None,
        "strain_name": single.name if single else None,
        "strain_identification": identification,
        "contributing_strains": [
            {"id": strain.id, "name": strain.name} for strain in strains
        ],
    }
