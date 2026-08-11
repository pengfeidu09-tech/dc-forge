"""DCForge Solution Compiler FastAPI 应用。"""

import os

from fastapi import FastAPI

from backend.app.process.api import router as requirement_router
from backend.app.solution.api import router as solution_router


def _internal_console_enabled() -> bool:
    return os.getenv("DCFORGE_ENABLE_INTERNAL_CONSOLE", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


def create_app(enable_internal_console: bool | None = None) -> FastAPI:
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
    return application


app = create_app()
