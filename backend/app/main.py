"""DCForge Solution Compiler FastAPI 应用。"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.process.api import router as requirement_router
from backend.app.solution.api import router as solution_router


def _internal_console_enabled() -> bool:
    return os.getenv("DCFORGE_ENABLE_INTERNAL_CONSOLE", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


def create_app(
    enable_internal_console: bool | None = None,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    application = FastAPI(
        title="DCForge Solution Compiler",
        version="1.0.0",
    )
    application.include_router(solution_router)
    application.include_router(requirement_router)
    enabled = (
        enable_internal_console
        if enable_internal_console is not None
        else _internal_console_enabled()
    )
    if enabled:
        from backend.app.internal_console.api import router as internal_console_router

        application.include_router(internal_console_router)
    dist = (
        Path(frontend_dist).resolve()
        if frontend_dist is not None
        else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    index = dist / "index.html"
    if index.is_file():
        assets = dist / "assets"
        if assets.is_dir():
            application.mount("/assets", StaticFiles(directory=assets), name="portal-assets")

        @application.get("/", include_in_schema=False)
        def enterprise_portal_index() -> FileResponse:
            return FileResponse(index)

    return application


app = create_app()
