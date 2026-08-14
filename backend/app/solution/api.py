"""B 模块 FastAPI 路由。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.app.contracts.process import ProcessSpec
from backend.app.solution.chat_agent import (
    ChatAgentRequest,
    ChatAgentResponse,
    run_chat_agent,
)
from backend.app.solution.feishu_bot import (
    FeishuBotService,
    FeishuVerificationError,
)
from backend.app.solution.enterprise_assistant import (
    EnterpriseAssistantRequest,
    EnterpriseAssistantResponse,
    EnterpriseAssistantService,
)
from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
from backend.app.solution.mcp_server import MCPDispatcher
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
from backend.app.solution.service import compile_solution_v2
from backend.app.solution.service import recompile_solution_v2
from backend.app.contracts.solution_intelligence import (
    RecompileSolutionV2Request,
    RecompileSolutionV2Result,
    SolutionBundleV2,
)

router = APIRouter(tags=["solution"])

# Agent provider 覆盖（测试用）
_agent_provider_override: LLMProvider | None = None
_chat_agent_provider_override: LLMProvider | None = None
_feishu_bot_service_override: FeishuBotService | None = None


def set_agent_provider(provider: LLMProvider | None) -> None:
    """设置 Agent LLM Provider（测试依赖注入用）。"""
    global _agent_provider_override
    _agent_provider_override = provider


def set_chat_agent_provider(provider: LLMProvider | None) -> None:
    """Set the requirement chat provider for tests and local integration."""
    global _chat_agent_provider_override
    _chat_agent_provider_override = provider


@lru_cache(maxsize=1)
def get_feishu_bot_service() -> FeishuBotService:
    return FeishuBotService.from_env()


def set_feishu_bot_service(service: FeishuBotService | None) -> None:
    """Set a Feishu bot service for tests and local integration."""
    global _feishu_bot_service_override
    _feishu_bot_service_override = service


def _active_feishu_bot_service() -> FeishuBotService:
    if _feishu_bot_service_override is not None:
        return _feishu_bot_service_override
    try:
        return get_feishu_bot_service()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@lru_cache(maxsize=1)
def get_enterprise_knowledge_service() -> EnterpriseKnowledgeService:
    repository_root = Path(__file__).resolve().parents[3]
    return EnterpriseKnowledgeService(repository_root)


@lru_cache(maxsize=1)
def get_enterprise_mcp_dispatcher() -> MCPDispatcher:
    return MCPDispatcher(get_enterprise_knowledge_service())


@lru_cache(maxsize=1)
def get_enterprise_assistant_service() -> EnterpriseAssistantService:
    return EnterpriseAssistantService(get_enterprise_mcp_dispatcher())


def _portal_error(error: Exception) -> HTTPException:
    if isinstance(error, PermissionError):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=503, detail="enterprise knowledge service unavailable")


class ReviewRequest(BaseModel):
    """私有评审请求模型，不放入公共 contracts。"""

    model_config = ConfigDict(extra="forbid")

    process: ProcessSpec
    solution: SolutionPlan


class EnterpriseCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    as_of: str


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dcforge-solution"}


@router.post("/compile-solution", response_model=SolutionBundle)
def compile_endpoint(request: CompileRequest) -> SolutionBundle:
    return compile_solution(request.process)


@router.post("/compile-solution-v2", response_model=SolutionBundleV2)
def compile_v2_endpoint(process: ProcessSpec) -> SolutionBundleV2:
    return compile_solution_v2(process)


@router.post("/recompile-solution-v2", response_model=RecompileSolutionV2Result)
def recompile_v2_endpoint(request: RecompileSolutionV2Request) -> RecompileSolutionV2Result:
    try:
        return recompile_solution_v2(
            request.process,
            request.selected_solution,
            request.selected_blueprint,
            request.new_constraints,
        )
    except ValueError as error:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(error)) from error


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


@router.post("/agent/chat", response_model=ChatAgentResponse)
def chat_agent_endpoint(request: ChatAgentRequest) -> ChatAgentResponse:
    return run_chat_agent(request, provider=_chat_agent_provider_override)


@router.get("/enterprise/projects")
def enterprise_projects_endpoint() -> dict[str, Any]:
    return {
        "projects": get_enterprise_knowledge_service().list_projects(),
        "data_classification": "synthetic_demo",
    }


@router.get("/enterprise/projects/{project_id}/dashboard")
def enterprise_dashboard_endpoint(
    project_id: str, user_id: str, as_of: str
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().get_project_dashboard(
            project_id, user_id=user_id, as_of=as_of
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get("/enterprise/projects/{project_id}/search")
def enterprise_search_endpoint(
    project_id: str,
    query: str,
    user_id: str,
    as_of: str,
    limit: int = 8,
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().search_knowledge(
            project_id,
            query=query,
            user_id=user_id,
            as_of=as_of,
            limit=limit,
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get("/enterprise/projects/{project_id}/requirements/{requirement_id}/history")
def enterprise_requirement_history_endpoint(
    project_id: str,
    requirement_id: str,
    user_id: str,
    as_of: str,
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().get_requirement_history(
            project_id,
            requirement_id,
            user_id=user_id,
            as_of=as_of,
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get("/enterprise/projects/{project_id}/suppliers")
def enterprise_suppliers_endpoint(
    project_id: str, user_id: str, as_of: str
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().analyze_suppliers(
            project_id, user_id=user_id, as_of=as_of
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get("/enterprise/projects/{project_id}/document-reviews")
def enterprise_document_reviews_endpoint(
    project_id: str, user_id: str, as_of: str
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().get_document_reviews(
            project_id, user_id=user_id, as_of=as_of
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.post("/enterprise/projects/{project_id}/compile")
def enterprise_compile_endpoint(
    project_id: str, request: EnterpriseCompileRequest
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().generate_solution_bundle(
            project_id, user_id=request.user_id, as_of=request.as_of
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.post("/enterprise/assistant", response_model=EnterpriseAssistantResponse)
def enterprise_assistant_endpoint(
    request: EnterpriseAssistantRequest,
) -> EnterpriseAssistantResponse:
    try:
        return get_enterprise_assistant_service().answer(request)
    except Exception as error:
        raise _portal_error(error) from error


@router.post("/mcp")
def enterprise_mcp_endpoint(request: dict[str, Any]) -> dict[str, Any]:
    response = get_enterprise_mcp_dispatcher().handle(request)
    return response or {"jsonrpc": "2.0", "result": {}}


@router.post("/integrations/feishu/events")
async def feishu_event_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    service = _active_feishu_bot_service()
    try:
        payload = await request.json()
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid JSON payload") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Feishu payload must be an object")
    try:
        validation = service.validate_callback(payload)
    except FeishuVerificationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if validation.kind == "challenge":
        return {"challenge": validation.challenge or ""}
    background_tasks.add_task(service.process_event, payload)
    return {"status": "accepted", "event_id": validation.event_id or ""}
