"""Internal-only FastAPI boundary for the Intelligence Console."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from backend.app.internal_console.models import (
    ConsoleAnalyzeRequest,
    ConsoleAnalyzeResponse,
    ConsoleCompileRequest,
    ConsoleCompileResponse,
    ConsoleConfirmRequest,
    ConsoleConfirmResponse,
    ConsoleDiffRequest,
    ConsoleDiffResponse,
    ConsoleRecompileRequest,
    ConsoleRecompileResponse,
    ConsoleChangeSetRequest,
    ConsoleChangeSetResponse,
    ConsoleChangeSetReviewRequest,
    ConsoleChangeSetReviewResponse,
)
from backend.app.internal_console.service import InternalConsoleService
from backend.app.solution.agent_configuration import configured_database_path
from backend.app.solution.internal_console_projects import (
    InternalConsoleProjectCreateRequest,
    InternalConsoleProjectListResponse,
    InternalConsoleProjectRecord,
    InternalConsoleProjectRepository,
    InternalConsoleProjectSnapshotRequest,
)


router = APIRouter(prefix="/internal-console", tags=["internal-console"])


@lru_cache(maxsize=1)
def get_internal_console_service() -> InternalConsoleService:
    try:
        return InternalConsoleService()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@lru_cache(maxsize=1)
def get_internal_console_project_repository() -> InternalConsoleProjectRepository:
    try:
        return InternalConsoleProjectRepository(configured_database_path())
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/projects", response_model=InternalConsoleProjectListResponse)
def list_projects_endpoint(
    repository: InternalConsoleProjectRepository = Depends(
        get_internal_console_project_repository
    ),
) -> InternalConsoleProjectListResponse:
    return InternalConsoleProjectListResponse(projects=repository.list_projects())


@router.post(
    "/projects", status_code=201, response_model=InternalConsoleProjectRecord
)
def create_project_endpoint(
    request: InternalConsoleProjectCreateRequest,
    repository: InternalConsoleProjectRepository = Depends(
        get_internal_console_project_repository
    ),
) -> InternalConsoleProjectRecord:
    return repository.create_project(
        sources=request.sources,
        uploaded_files=request.uploaded_files,
    )


@router.put("/projects/{project_id}", response_model=InternalConsoleProjectRecord)
def save_project_endpoint(
    project_id: str,
    request: InternalConsoleProjectSnapshotRequest,
    repository: InternalConsoleProjectRepository = Depends(
        get_internal_console_project_repository
    ),
) -> InternalConsoleProjectRecord:
    try:
        return repository.save_snapshot(project_id, request.snapshot)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (FileExistsError, KeyError)):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.post("/analyze", response_model=ConsoleAnalyzeResponse)
def analyze_endpoint(
    request: ConsoleAnalyzeRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleAnalyzeResponse:
    try:
        analysis, warnings = service.analyze(
            request.project_id,
            request.sources,
            previous_state_version=request.previous_state_version,
            skill_id=request.skill_id,
        )
        return ConsoleAnalyzeResponse(
            analysis=analysis, extraction_warnings=warnings
        )
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        raise _http_error(error) from error


@router.post("/confirm", response_model=ConsoleConfirmResponse)
def confirm_endpoint(
    request: ConsoleConfirmRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleConfirmResponse:
    try:
        analysis, baseline = service.confirm(request.confirmation)
        return ConsoleConfirmResponse(analysis=analysis, baseline=baseline)
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        raise _http_error(error) from error


@router.post("/compile", response_model=ConsoleCompileResponse)
def compile_endpoint(
    request: ConsoleCompileRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleCompileResponse:
    try:
        handoff = service.compile(request.project_id, request.baseline_version)
        return ConsoleCompileResponse(
            process_spec=handoff.process,
            solution_bundle=handoff.bundle,
            recommended_solution=handoff.selected_solution,
            demo_blueprint=handoff.blueprint,
        )
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _http_error(error) from error


@router.post("/diff", response_model=ConsoleDiffResponse)
def diff_endpoint(
    request: ConsoleDiffRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleDiffResponse:
    try:
        diff, route = service.diff(
            request.project_id,
            request.previous_baseline_version,
            request.current_baseline_version,
        )
        return ConsoleDiffResponse(requirement_diff=diff, route=route)
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _http_error(error) from error


@router.post("/change-set", response_model=ConsoleChangeSetResponse)
def change_set_endpoint(
    request: ConsoleChangeSetRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleChangeSetResponse:
    try:
        return ConsoleChangeSetResponse(
            change_set=service.change_set(
                request.project_id, request.previous_baseline_version, request.state_version
            )
        )
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _http_error(error) from error


@router.post("/change-set/review", response_model=ConsoleChangeSetReviewResponse)
def review_change_set_endpoint(
    request: ConsoleChangeSetReviewRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleChangeSetReviewResponse:
    try:
        analysis, baseline, diff, route, audits = service.review_change_set(
            request.project_id, request.previous_baseline_version, request.state_version,
            request.feedback_sources, request.actions,
            confirmation_level=request.confirmation_level,
            confirmed_by=request.confirmed_by,
            note=request.note,
        )
        return ConsoleChangeSetReviewResponse(
            analysis=analysis, baseline=baseline, requirement_diff=diff, route=route,
            formal_removal_audit_ids=[audit.audit_id for audit in audits],
        )
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        raise _http_error(error) from error


@router.post("/recompile", response_model=ConsoleRecompileResponse)
def recompile_endpoint(
    request: ConsoleRecompileRequest,
    service: InternalConsoleService = Depends(get_internal_console_service),
) -> ConsoleRecompileResponse:
    try:
        handoff = service.recompile(
            request.project_id,
            request.previous_baseline_version,
            request.current_baseline_version,
            request.previous_process,
            request.selected_solution,
            request.selected_blueprint,
        )
        return ConsoleRecompileResponse(
            decision=handoff.decision,
            requirement_diff=handoff.requirement_diff,
            route=handoff.route,
            process_spec=handoff.process,
            solution=handoff.solution,
            demo_blueprint=handoff.blueprint,
            solution_bundle=handoff.bundle,
            recompile_result=handoff.recompile_result,
        )
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _http_error(error) from error
