import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .library import router as library_router
from .photos import router as photo_router
from .provenance import router as provenance_router
from .preparation import router as preparation_router
from .containers import router as container_router
from .fruiting import router as fruiting_router
from .reports import router as reports_router
from .config import VERSION, Settings
from .database import initialize, make_engine

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            initialize(settings, engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Cultivatinator", version=VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.include_router(router)
    app.include_router(provenance_router)
    app.include_router(preparation_router)
    app.include_router(container_router)
    app.include_router(fruiting_router)
    app.include_router(reports_router)
    app.include_router(library_router)
    app.include_router(photo_router)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.error("Unhandled request error", exc_info=exc)
        return JSONResponse(
            status_code=500, content={"detail": "An unexpected server error occurred."}
        )

    frontend = settings.frontend_dir.resolve()
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_page(path: str):
        # Never return HTML for misspelled API or missing static asset requests.
        if path == "api" or path.startswith(("api/", "assets/")):
            raise HTTPException(404, "Not found")
        if not (frontend / "index.html").is_file():
            raise HTTPException(
                404, "Frontend not built. Run npm run build in frontend/."
            )
        return FileResponse(frontend / "index.html")

    return app


app = create_app()
