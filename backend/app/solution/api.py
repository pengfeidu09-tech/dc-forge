"""B 模块 FastAPI 路由。"""

from __future__ import annotations

from functools import lru_cache
import hmac
import os
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import HTMLResponse, JSONResponse

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
from backend.app.solution.customer_engagement import CustomerEngagementService
from backend.app.solution.customer_engagement_pages import (
    customer_center_html,
    internal_workbench_html,
    presales_workbench_html,
)
from backend.app.solution.mcp_server import MCPDispatcher
from backend.app.contracts.solution import (
    CompileRequest,
    RecompileRequest,
    RecompileResult,
    SolutionBundle,
    SolutionPlan,
)
from backend.app.solution.agent import AgentRequest, AgentResponse, run_solution_agent
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.production_readiness import evaluate_production_readiness
from backend.app.solution.presales_orchestration import (
    DeliverableContent,
    PresalesOrchestrationService,
)
from backend.app.solution.rate_limiter import InMemoryRateLimiter
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
_customer_engagement_service_override: CustomerEngagementService | None = None
_presales_orchestration_service_override: PresalesOrchestrationService | None = None
_customer_rate_limiter: InMemoryRateLimiter | None = None
_customer_rate_limiter_settings: tuple[int, float] | None = None
_customer_rate_limiter_lock = Lock()

_CUSTOMER_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


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
def get_customer_engagement_service() -> CustomerEngagementService:
    from backend.app.solution.feishu_requirement import FeishuRequirementOrchestrator

    analyzer = FeishuRequirementOrchestrator.from_env()
    return CustomerEngagementService.from_env(feedback_analyzer=analyzer)


def set_customer_engagement_service(
    service: CustomerEngagementService | None,
) -> None:
    """Set the PORTAL-M3 service for tests and local integration."""
    global _customer_engagement_service_override
    _customer_engagement_service_override = service


def _active_customer_engagement_service() -> CustomerEngagementService:
    if _customer_engagement_service_override is not None:
        return _customer_engagement_service_override
    try:
        return get_customer_engagement_service()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@lru_cache(maxsize=1)
def get_presales_orchestration_service() -> PresalesOrchestrationService:
    return PresalesOrchestrationService.from_env(
        engagement_service=get_customer_engagement_service(),
        knowledge_service=get_enterprise_knowledge_service(),
    )


def set_presales_orchestration_service(
    service: PresalesOrchestrationService | None,
) -> None:
    """Set the PRESALES-M1 orchestration service for tests and integration."""
    global _presales_orchestration_service_override
    _presales_orchestration_service_override = service


def _active_presales_orchestration_service() -> PresalesOrchestrationService:
    if _presales_orchestration_service_override is not None:
        return _presales_orchestration_service_override
    try:
        if _customer_engagement_service_override is not None:
            return PresalesOrchestrationService.from_env(
                engagement_service=_customer_engagement_service_override,
                knowledge_service=get_enterprise_knowledge_service(),
            )
        return get_presales_orchestration_service()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _require_internal_access(request: Request) -> None:
    configured = os.getenv("CUSTOMER_ENGAGEMENT_INTERNAL_TOKEN", "").strip()
    if not configured:
        client_host = request.client.host if request.client is not None else ""
        if client_host in {"127.0.0.1", "::1", "testclient"}:
            return
        raise HTTPException(
            status_code=403,
            detail="internal access token must be configured for remote access",
        )
    supplied = request.headers.get("X-DCForge-Internal-Token", "")
    if not supplied or not hmac.compare_digest(configured, supplied):
        raise HTTPException(status_code=401, detail="invalid internal access token")


def _customer_engagement_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail="customer project not found")
    if isinstance(error, RuntimeError) and "stale" in str(error):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=503, detail="customer engagement service unavailable")


def _presales_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, PermissionError):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, (RuntimeError, ValueError)):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=503, detail="presales orchestration unavailable")


def _customer_access_token(request: Request) -> str:
    token = request.headers.get("X-DCForge-Customer-Token", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="customer project not found")
    return token


def _apply_customer_security_headers(response: Response) -> None:
    for name, value in _CUSTOMER_SECURITY_HEADERS.items():
        response.headers[name] = value


def _bounded_env_number(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _active_customer_rate_limiter() -> InMemoryRateLimiter:
    global _customer_rate_limiter, _customer_rate_limiter_settings
    limit = _bounded_env_number(
        "CUSTOMER_ENGAGEMENT_RATE_LIMIT_MAX",
        10,
        minimum=1,
        maximum=1000,
    )
    window_seconds = float(
        _bounded_env_number(
            "CUSTOMER_ENGAGEMENT_RATE_LIMIT_WINDOW_SECONDS",
            60,
            minimum=1,
            maximum=3600,
        )
    )
    settings = (limit, window_seconds)
    with _customer_rate_limiter_lock:
        if _customer_rate_limiter is None or _customer_rate_limiter_settings != settings:
            _customer_rate_limiter = InMemoryRateLimiter(
                limit=limit,
                window_seconds=window_seconds,
            )
            _customer_rate_limiter_settings = settings
        return _customer_rate_limiter


def reset_customer_engagement_rate_limiter() -> None:
    """Clear the process-local customer limiter for tests and restarts."""
    global _customer_rate_limiter, _customer_rate_limiter_settings
    with _customer_rate_limiter_lock:
        _customer_rate_limiter = None
        _customer_rate_limiter_settings = None


def _enforce_customer_rate_limit(
    request: Request,
    *,
    access_id: str,
    action: str,
) -> None:
    client_host = request.client.host if request.client is not None else "unknown"
    key = f"{action}|{access_id}|{client_host}"
    if not _active_customer_rate_limiter().allow(key):
        raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试。")


@lru_cache(maxsize=1)
def get_enterprise_knowledge_service() -> EnterpriseKnowledgeService:
    repository_root = Path(__file__).resolve().parents[3]
    return EnterpriseKnowledgeService(repository_root)


@lru_cache(maxsize=1)
def get_enterprise_mcp_dispatcher() -> MCPDispatcher:
    return MCPDispatcher(get_enterprise_knowledge_service())


@lru_cache(maxsize=1)
def get_enterprise_assistant_service() -> EnterpriseAssistantService:
    return EnterpriseAssistantService(
        get_enterprise_mcp_dispatcher(),
        provider=OpenAICompatibleProvider(),
    )


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


class CustomerPublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    baseline_version: int = Field(ge=1)
    published_by: str = Field(min_length=1, max_length=120)


class CustomerConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirmation_revision: str = Field(min_length=1, max_length=128)
    accepted_item_keys: list[
        Annotated[str, Field(min_length=1, max_length=128)]
    ] = Field(max_length=200)
    rejected_item_keys: list[
        Annotated[str, Field(min_length=1, max_length=128)]
    ] = Field(max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_item_keys(self) -> "CustomerConfirmationRequest":
        accepted = set(self.accepted_item_keys)
        rejected = set(self.rejected_item_keys)
        if len(accepted) != len(self.accepted_item_keys):
            raise ValueError("accepted_item_keys must not contain duplicates")
        if len(rejected) != len(self.rejected_item_keys):
            raise ValueError("rejected_item_keys must not contain duplicates")
        if accepted & rejected:
            raise ValueError("accepted and rejected requirement items must not overlap")
        return self


class CustomerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)


class PresalesProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=240)
    owner: str = Field(min_length=1, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    reference_project_id: str = Field(
        default="PRJ-TENDER-001", min_length=1, max_length=160
    )


class PresalesSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal[
        "customer_document",
        "meeting_minutes",
        "customer_email",
        "internal_material",
        "external_intelligence",
    ]
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=12000)
    added_by: str = Field(min_length=1, max_length=120)
    source_url: str | None = Field(default=None, max_length=2000)
    occurred_at: str | None = Field(default=None, max_length=80)


class PresalesResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2000)
    user_id: str = Field(min_length=1, max_length=160)
    as_of: str = Field(min_length=1, max_length=80)
    generated_by: str = Field(min_length=1, max_length=120)


class PresalesDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    baseline_version: int | None = Field(default=None, ge=1)
    generated_by: str = Field(min_length=1, max_length=120)


class PresalesDeliverableUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: DeliverableContent
    updated_by: str = Field(min_length=1, max_length=120)


class PresalesReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reviewed_by: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class PresalesPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_version: int = Field(ge=1)
    published_by: str = Field(min_length=1, max_length=120)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dcforge-solution"}


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "dcforge-solution"}


@router.get("/health/ready")
def health_ready() -> JSONResponse:
    report = evaluate_production_readiness()
    return JSONResponse(
        content=report,
        status_code=200 if report["status"] == "ready" else 503,
    )


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


@router.get("/enterprise/projects/{project_id}/sources")
def enterprise_sources_endpoint(
    project_id: str,
    user_id: str,
    as_of: str,
    source_type: str | None = None,
    requirement_id: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().list_project_sources(
            project_id,
            user_id=user_id,
            as_of=as_of,
            source_type=source_type,
            requirement_id=requirement_id,
            query=query,
            limit=limit,
            offset=offset,
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get("/enterprise/projects/{project_id}/sources/{source_id}")
def enterprise_source_endpoint(
    project_id: str,
    source_id: str,
    user_id: str,
    as_of: str,
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().get_project_source(
            project_id,
            source_id,
            user_id=user_id,
            as_of=as_of,
        )
    except Exception as error:
        raise _portal_error(error) from error


@router.get(
    "/enterprise/projects/{project_id}/requirements/{requirement_id}/sources"
)
def enterprise_requirement_sources_endpoint(
    project_id: str,
    requirement_id: str,
    user_id: str,
    as_of: str,
) -> dict[str, Any]:
    try:
        return get_enterprise_knowledge_service().get_requirement_sources(
            project_id,
            requirement_id,
            user_id=user_id,
            as_of=as_of,
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


@router.get("/presales/workbench", response_class=HTMLResponse)
def presales_workbench_page() -> HTMLResponse:
    response = HTMLResponse(presales_workbench_html())
    _apply_customer_security_headers(response)
    return response


@router.get("/customer-engagement/workbench", response_class=HTMLResponse)
def customer_engagement_workbench_page() -> HTMLResponse:
    response = HTMLResponse(internal_workbench_html())
    _apply_customer_security_headers(response)
    return response


@router.get("/presales/projects")
def presales_projects_endpoint(
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return {"projects": _active_presales_orchestration_service().list_projects()}
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects", status_code=201)
def presales_create_project_endpoint(
    project: PresalesProjectCreateRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().create_project(
            title=project.title,
            owner=project.owner,
            industry=project.industry,
            reference_project_id=project.reference_project_id,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.get("/presales/projects/{project_id}")
def presales_project_endpoint(
    project_id: str,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().get_workspace(project_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects/{project_id}/sources", status_code=201)
def presales_source_endpoint(
    project_id: str,
    source: PresalesSourceRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().add_source(
            project_id,
            **source.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects/{project_id}/research", status_code=201)
def presales_research_endpoint(
    project_id: str,
    research: PresalesResearchRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().run_research(
            project_id,
            **research.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects/{project_id}/drafts", status_code=201)
def presales_draft_endpoint(
    project_id: str,
    draft: PresalesDraftRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().generate_draft(
            project_id,
            **draft.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post(
    "/presales/projects/{project_id}/drafts/{draft_version}/deliverable"
)
def presales_deliverable_update_endpoint(
    project_id: str,
    draft_version: int,
    update: PresalesDeliverableUpdateRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().update_deliverable(
            project_id,
            draft_version=draft_version,
            content=update.content,
            updated_by=update.updated_by,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects/{project_id}/reviews", status_code=201)
def presales_review_endpoint(
    project_id: str,
    review: PresalesReviewRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().review_draft(
            project_id,
            **review.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/presales/projects/{project_id}/publish", status_code=201)
def presales_publish_endpoint(
    project_id: str,
    publication: PresalesPublishRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_presales_orchestration_service().publish_project(
            project_id,
            **publication.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.get("/customer-engagement/projects")
def customer_engagement_projects_endpoint(
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return {
            "projects": _active_customer_engagement_service().list_internal_projects()
        }
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.get("/customer-engagement/projects/{project_id}")
def customer_engagement_project_endpoint(
    project_id: str,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_customer_engagement_service().get_internal_project(project_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.post("/customer-engagement/projects/{project_id}/publish")
def customer_engagement_publish_endpoint(
    project_id: str,
    publication: CustomerPublicationRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _require_internal_access(request)
    _apply_customer_security_headers(response)
    try:
        return _active_customer_engagement_service().publish_project(
            project_id,
            baseline_version=publication.baseline_version,
            published_by=publication.published_by,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.get("/customer/engagement/{access_id}/data")
def customer_engagement_data_endpoint(
    access_id: str,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _apply_customer_security_headers(response)
    try:
        token = _customer_access_token(request)
        data = _active_customer_engagement_service().get_customer_view_for_access(
            access_id, token
        )
        data["deliverable"] = (
            _active_presales_orchestration_service().get_customer_deliverable_for_access(
                access_id, token
            )
        )
        return data
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.get(
    "/customer/engagement/{access_id}/deliverable",
    response_class=HTMLResponse,
)
def customer_engagement_deliverable_endpoint(
    access_id: str,
    request: Request,
) -> HTMLResponse:
    try:
        service = _active_presales_orchestration_service()
        deliverable = service.get_customer_deliverable_for_access(
            access_id,
            _customer_access_token(request),
        )
        response = HTMLResponse(service.render_customer_deliverable_html(deliverable))
        _apply_customer_security_headers(response)
        return response
    except HTTPException:
        raise
    except Exception as error:
        raise _presales_error(error) from error


@router.post("/customer/engagement/{access_id}/confirm")
def customer_engagement_confirm_endpoint(
    access_id: str,
    confirmation: CustomerConfirmationRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _apply_customer_security_headers(response)
    try:
        service = _active_customer_engagement_service()
        token = _customer_access_token(request)
        service.get_customer_view_for_access(access_id, token)
        _enforce_customer_rate_limit(
            request,
            access_id=access_id,
            action="confirm",
        )
        return service.confirm_customer_requirements(
            token=token,
            confirmation_revision=confirmation.confirmation_revision,
            accepted_item_keys=confirmation.accepted_item_keys,
            rejected_item_keys=confirmation.rejected_item_keys,
            note=confirmation.note,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.post("/customer/engagement/{access_id}/feedback")
def customer_engagement_feedback_endpoint(
    access_id: str,
    feedback: CustomerFeedbackRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _apply_customer_security_headers(response)
    try:
        service = _active_customer_engagement_service()
        token = _customer_access_token(request)
        service.get_customer_view_for_access(access_id, token)
        _enforce_customer_rate_limit(
            request,
            access_id=access_id,
            action="feedback",
        )
        return service.submit_customer_feedback(
            token=token,
            message=feedback.message,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error


@router.get("/customer/engagement/{access_id}", response_class=HTMLResponse)
def customer_engagement_page(access_id: str) -> HTMLResponse:
    try:
        _active_customer_engagement_service().validate_customer_access_id(access_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _customer_engagement_error(error) from error
    response = HTMLResponse(customer_center_html(access_id))
    _apply_customer_security_headers(response)
    return response


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
