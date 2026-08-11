"""Private HTTP contracts for the Internal Intelligence Console."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.app.contracts.common import StrictModel
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    CustomerSourceRecord,
    RequirementAnalysis,
    RequirementBaseline,
    RequirementConfirmation,
    RequirementDiff,
    RequirementDiffRoute,
    RequirementExtractionWarning,
)
from backend.app.contracts.solution_intelligence import (
    DemoBlueprint,
    RecompileSolutionV2Result,
    SolutionBundleV2,
    SolutionPlanV2,
)


class ConsoleAnalyzeRequest(StrictModel):
    project_id: str
    sources: list[CustomerSourceRecord] = Field(min_length=1)
    previous_state_version: int | None = Field(default=None, ge=1)
    skill_id: str = "automotive-procurement-v1"


class ConsoleAnalyzeResponse(StrictModel):
    analysis: RequirementAnalysis
    extraction_warnings: list[RequirementExtractionWarning] = Field(default_factory=list)


class ConsoleConfirmRequest(StrictModel):
    confirmation: RequirementConfirmation


class ConsoleConfirmResponse(StrictModel):
    analysis: RequirementAnalysis
    baseline: RequirementBaseline | None = None


class ConsoleCompileRequest(StrictModel):
    project_id: str
    baseline_version: int = Field(ge=1)


class ConsoleCompileResponse(StrictModel):
    process_spec: ProcessSpec
    solution_bundle: SolutionBundleV2
    recommended_solution: SolutionPlanV2
    demo_blueprint: DemoBlueprint


class ConsoleDiffRequest(StrictModel):
    project_id: str
    previous_baseline_version: int = Field(ge=1)
    current_baseline_version: int = Field(ge=1)


class ConsoleDiffResponse(StrictModel):
    requirement_diff: RequirementDiff
    route: RequirementDiffRoute


class ConsoleRecompileRequest(StrictModel):
    project_id: str
    previous_baseline_version: int = Field(ge=1)
    current_baseline_version: int = Field(ge=1)
    previous_process: ProcessSpec
    selected_solution: SolutionPlanV2
    selected_blueprint: DemoBlueprint


class ConsoleRecompileResponse(StrictModel):
    decision: Literal[
        "no_op",
        "incremental_constraint_recompile",
        "full_solution_recompile",
    ]
    requirement_diff: RequirementDiff
    route: RequirementDiffRoute
    process_spec: ProcessSpec
    solution: SolutionPlanV2
    demo_blueprint: DemoBlueprint
    solution_bundle: SolutionBundleV2 | None = None
    recompile_result: RecompileSolutionV2Result | None = None
