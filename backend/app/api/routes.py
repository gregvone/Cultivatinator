import logging

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text, select, func
from ..models import PhysicalCulture, Spawn, FruitingContainer

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
        summary.counts.active_cultures = connection.scalar(
            select(func.count())
            .select_from(PhysicalCulture)
            .where(PhysicalCulture.status == "active")
        )
        for field, model in [
            ("spawn_containers", Spawn),
            ("fruiting_units", FruitingContainer),
        ]:
            setattr(
                summary.counts,
                field,
                connection.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.status == "active")
                ),
            )
    return summary


@router.get("/app/info", response_model=AppInfo)
def app_info(request: Request):
    return AppInfo(version=VERSION, environment=request.app.state.settings.environment)
