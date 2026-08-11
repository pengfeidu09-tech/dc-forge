"""Thin HTTP boundary for Requirement Intelligence R-M5."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.contracts.common import StrictModel
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementDiff,
    RequirementDiffRoute,
)
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService


router = APIRouter(prefix="/requirement", tags=["requirement"])


class CompileProcessSpecRequest(StrictModel):
    baseline: RequirementBaseline


class RequirementDiffRequest(StrictModel):
    previous: RequirementBaseline
    current: RequirementBaseline


def get_requirement_service() -> RequirementIntelligenceService:
    root = os.getenv("REQUIREMENT_REPOSITORY_ROOT")
    if not root:
        raise HTTPException(
            status_code=503,
            detail="REQUIREMENT_REPOSITORY_ROOT is not configured",
        )
    skill_root = Path(__file__).parents[3] / "data" / "requirement_skills"
    return RequirementIntelligenceService(
        FileRequirementRepository(root), RequirementSkillLoader(skill_root)
    )


def _map_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.post("/compile-process-spec", response_model=ProcessSpec)
def compile_process_spec_endpoint(
    request: CompileProcessSpecRequest,
    service: RequirementIntelligenceService = Depends(get_requirement_service),
) -> ProcessSpec:
    try:
        return service.compile_process_spec(request.baseline)
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _map_error(error) from error


@router.post("/diff", response_model=RequirementDiff)
def diff_endpoint(
    request: RequirementDiffRequest,
    service: RequirementIntelligenceService = Depends(get_requirement_service),
) -> RequirementDiff:
    try:
        return service.diff(request.previous, request.current)
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _map_error(error) from error


@router.post("/route-diff", response_model=RequirementDiffRoute)
def route_diff_endpoint(
    request: RequirementDiffRequest,
    service: RequirementIntelligenceService = Depends(get_requirement_service),
) -> RequirementDiffRoute:
    try:
        return service.route_diff(request.previous, request.current)
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise _map_error(error) from error
