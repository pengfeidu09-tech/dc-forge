"""B 模块 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    CompileRequest,
    RecompileRequest,
    RecompileResult,
    SolutionBundle,
    SolutionPlan,
)
from backend.app.solution.agent import AgentRequest, AgentResponse, run_solution_agent
from backend.app.solution.llm_provider import LLMProvider
from backend.app.solution.reviewer import SolutionReviewResult
from backend.app.solution.service import compile_solution, recompile_solution

router = APIRouter(tags=["solution"])

# Agent provider 覆盖（测试用）
_agent_provider_override: LLMProvider | None = None


def set_agent_provider(provider: LLMProvider | None) -> None:
    """设置 Agent LLM Provider（测试依赖注入用）。"""
    global _agent_provider_override
    _agent_provider_override = provider


class ReviewRequest(BaseModel):
    """私有评审请求模型，不放入公共 contracts。"""

    model_config = ConfigDict(extra="forbid")

    process: ProcessSpec
    solution: SolutionPlan


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dcforge-solution"}


@router.post("/compile-solution", response_model=SolutionBundle)
def compile_endpoint(request: CompileRequest) -> SolutionBundle:
    return compile_solution(request.process)


@router.post("/recompile-solution", response_model=RecompileResult)
def recompile_endpoint(request: RecompileRequest) -> RecompileResult:
    return recompile_solution(request)


@router.post("/review-solution", response_model=SolutionReviewResult)
def review_endpoint(request: ReviewRequest) -> SolutionReviewResult:
    from backend.app.solution.constraints import validate_constraints
    from backend.app.solution.reviewer import review_solution

    validation = validate_constraints(request.solution, list(request.process.constraints))
    return review_solution(request.solution, request.process, validation)


@router.post("/agent/solution", response_model=AgentResponse)
def agent_endpoint(request: AgentRequest) -> AgentResponse:
    return run_solution_agent(request, provider=_agent_provider_override)
