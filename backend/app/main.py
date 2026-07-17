"""DCForge Solution Compiler FastAPI 应用。"""

from fastapi import FastAPI

from backend.app.solution.api import router as solution_router

app = FastAPI(
    title="DCForge Solution Compiler",
    version="1.0.0",
)

app.include_router(solution_router)
