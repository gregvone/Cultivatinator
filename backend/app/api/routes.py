import logging

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text, select, func, or_
from sqlalchemy.orm import Session
from ..models import PhysicalCulture, Spawn, FruitingContainer
from ..preparation_models import MaterialLifecycle

from ..config import VERSION
from ..database import migration_config
from ..schemas import AppInfo, DashboardSummary, Health

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
def health(request: Request):
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = MigrationContext.configure(connection).get_current_revision()
        expected = ScriptDirectory.from_config(
            migration_config(request.app.state.settings)
        ).get_current_head()
        if current != expected:
            return JSONResponse(
                status_code=503,
                content=Health(
                    status="error", database="ok", migrations="outdated"
                ).model_dump(),
            )
        return Health(status="ok", database="ok", migrations="current")
    except Exception:
        logger.exception("Database health check failed")
        return JSONResponse(
            status_code=503,
            content=Health(
                status="error", database="unavailable", migrations="unavailable"
            ).model_dump(),
        )


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(request: Request):
    summary = DashboardSummary()
    with request.app.state.engine.connect() as connection:
        for field, model, owner in [
            ("active_cultures", PhysicalCulture, MaterialLifecycle.physical_id),
            ("spawn_containers", Spawn, MaterialLifecycle.spawn_id),
        ]:
            count = connection.scalar(
                select(func.count())
                .select_from(model)
                .outerjoin(MaterialLifecycle, owner == model.id)
                .where(
                    model.status == "active",
                    or_(
                        MaterialLifecycle.state.is_(None),
                        MaterialLifecycle.state == "active",
                    ),
                )
            )
            setattr(summary.counts, field, count)
        summary.counts.fruiting_units = connection.scalar(
            select(func.count())
            .select_from(FruitingContainer)
            .where(
                FruitingContainer.status == "active",
                FruitingContainer.stage != "finished",
            )
        )
    from ..library import output
    from ..schemas import RecordReference

    with Session(request.app.state.engine) as session:
        for kind, model in (
            ("physical", PhysicalCulture),
            ("spawn", Spawn),
            ("fruiting", FruitingContainer),
        ):
            for row in session.scalars(
                select(model)
                .where(model.status == "active")
                .order_by(model.created_at.desc())
                .limit(12)
            ):
                record = output(session, kind, row)
                if record.lifecycle in {
                    "used",
                    "completed",
                    "failed",
                    "depleted",
                } or getattr(row, "stage", None) in {"used", "finished"}:
                    continue
                summary.active_cultivation.append(
                    RecordReference(
                        record_id=row.id,
                        title=f"{record.physical_label or row.id} · {record.strain_name or record.material_type or 'Unknown strain'}",
                        target=f"/culture-library/{kind}/{row.id}",
                    )
                )
    return summary


@router.get("/app/info", response_model=AppInfo)
def app_info(request: Request):
    return AppInfo(version=VERSION, environment=request.app.state.settings.environment)
