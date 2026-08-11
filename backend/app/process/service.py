"""Requirement Intelligence service and its frozen B-M8 handoff boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementDiff,
    RequirementDiffRoute,
)
from backend.app.contracts.solution_intelligence import (
    DemoBlueprint,
    RecompileSolutionV2Result,
    SolutionBundleV2,
    SolutionPlanV2,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.process_spec_adapter import ProcessSpecAdapter
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_diff import RequirementDiffEngine
from backend.app.process.requirement_diff_router import RequirementDiffRouter
from backend.app.process.requirement_repository import RequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.service import (
    compile_demo_blueprint,
    compile_solution_v2,
    recompile_solution_v2,
)


@dataclass(frozen=True)
class InitialSolutionHandoff:
    process: ProcessSpec
    bundle: SolutionBundleV2
    selected_solution: SolutionPlanV2
    blueprint: DemoBlueprint


@dataclass(frozen=True)
class BaselineChangeHandoff:
    decision: str
    requirement_diff: RequirementDiff
    route: RequirementDiffRoute
    process: ProcessSpec
    solution: SolutionPlanV2
    blueprint: DemoBlueprint
    bundle: SolutionBundleV2 | None = None
    recompile_result: RecompileSolutionV2Result | None = None


class RequirementIntelligenceService:
    def __init__(
        self,
        repository: RequirementRepository,
        skill_loader: RequirementSkillLoader,
        adapter: ProcessSpecAdapter | None = None,
        diff_engine: RequirementDiffEngine | None = None,
        router: RequirementDiffRouter | None = None,
        *,
        compile_solution_fn: Callable[[ProcessSpec], SolutionBundleV2] = compile_solution_v2,
        compile_blueprint_fn: Callable[[ProcessSpec, SolutionPlanV2], DemoBlueprint] = compile_demo_blueprint,
        recompile_solution_fn: Callable[
            [ProcessSpec, SolutionPlanV2, DemoBlueprint, list], RecompileSolutionV2Result
        ] = recompile_solution_v2,
    ) -> None:
        self._repository = repository
        self._skill_loader = skill_loader
        self._adapter = adapter or ProcessSpecAdapter()
        self._diff_engine = diff_engine or RequirementDiffEngine()
        self._router = router or RequirementDiffRouter(self._adapter)
        self._compile_solution = compile_solution_fn
        self._compile_blueprint = compile_blueprint_fn
        self._recompile_solution = recompile_solution_fn

    def _context(self, baseline: RequirementBaseline):
        state = self._repository.load_state(
            baseline.project_id, version=baseline.source_state_version
        )
        if state is None:
            raise FileNotFoundError("RequirementBaseline source RequirementState does not exist")
        if state.project_id != baseline.project_id or state.state_version != baseline.source_state_version:
            raise ValueError("RequirementBaseline source state closure failed")
        if not state.selected_skill_id:
            raise ValueError("RequirementState selected_skill_id is required")
        try:
            skill = self._skill_loader.resolve(state.selected_skill_id)
        except KeyError as exc:
            raise ValueError(f"RequirementState selected_skill_id is invalid: {state.selected_skill_id}") from exc
        conflicts = ConflictDetector().detect(state, skill)
        gaps = GapDetector().detect(state, skill, conflicts)
        readiness = ReadinessEvaluator().evaluate(
            state, skill, gaps, conflicts, customer_confirmation_complete=True
        )
        if readiness.stage != "CONFIRMED_READY" or not readiness.can_generate_formal_solution:
            raise ValueError("RequirementBaseline source state is not CONFIRMED_READY")
        questions = QuestionPlanner().plan(
            state, skill, list(baseline.non_blocking_gaps), conflicts
        )
        return state, skill, readiness, questions

    def compile_process_spec(self, baseline: RequirementBaseline) -> ProcessSpec:
        state, skill, readiness, questions = self._context(baseline)
        return self._adapter.adapt(baseline, state, skill, readiness, questions)

    def diff(self, previous: RequirementBaseline, current: RequirementBaseline) -> RequirementDiff:
        return self._diff_engine.compare(previous, current)

    def route_diff(
        self, previous: RequirementBaseline, current: RequirementBaseline
    ) -> RequirementDiffRoute:
        diff = self.diff(previous, current)
        _, skill, _, _ = self._context(current)
        if not diff.changes:
            return self._router.route(diff, previous, current, skill)
        categories = {
            (next((item for item in current.confirmed_items if item.requirement_id == change.requirement_id), None)
             or next(item for item in previous.confirmed_items if item.requirement_id == change.requirement_id)).category
            for change in diff.changes
        }
        if categories <= {"security", "approval", "budget", "time", "data", "risk"}:
            return self._router.route(diff, previous, current, skill)
        previous_process = self.compile_process_spec(previous)
        current_process = self.compile_process_spec(current)
        return self._router.route(
            diff, previous, current, skill,
            previous_process=previous_process, current_process=current_process,
        )

    def compile_solution_from_baseline(
        self, baseline: RequirementBaseline
    ) -> InitialSolutionHandoff:
        process = self.compile_process_spec(baseline)
        bundle = self._compile_solution(process)
        selected = next(
            plan for plan in bundle.plans if plan.solution_id == bundle.recommended_solution_id
        )
        blueprint = self._compile_blueprint(process, selected)
        return InitialSolutionHandoff(process, bundle, selected, blueprint)

    def _validate_previous_artifacts(
        self,
        baseline: RequirementBaseline,
        previous_process: ProcessSpec,
        selected_solution: SolutionPlanV2,
        selected_blueprint: DemoBlueprint,
    ) -> None:
        expected_process = self.compile_process_spec(baseline)
        if previous_process.model_dump() != expected_process.model_dump():
            raise ValueError("previous_process does not represent previous_baseline")
        if selected_solution.source_project_id != previous_process.project_id:
            raise ValueError("selected_solution must belong to previous_process project_id")
        if (
            selected_blueprint.project_id != previous_process.project_id
            or selected_blueprint.solution_id != selected_solution.solution_id
        ):
            raise ValueError("selected_blueprint must belong to selected_solution and previous_process")
        expected_assets = list(dict.fromkeys(
            selected_solution.primary_asset_ids + selected_solution.supporting_asset_ids
        ))
        if selected_blueprint.source_asset_ids != expected_assets:
            raise ValueError("selected_blueprint source assets must match selected_solution")
        if [item.model_dump() for item in selected_solution.applied_constraints] != [
            item.model_dump() for item in previous_process.constraints
        ]:
            raise ValueError("selected_solution applied_constraints are stale for previous_process")

    def apply_baseline_change(
        self,
        previous_baseline: RequirementBaseline,
        current_baseline: RequirementBaseline,
        previous_process: ProcessSpec,
        selected_solution: SolutionPlanV2,
        selected_blueprint: DemoBlueprint,
    ) -> BaselineChangeHandoff:
        self._validate_previous_artifacts(
            previous_baseline, previous_process, selected_solution, selected_blueprint
        )
        diff = self.diff(previous_baseline, current_baseline)
        _, current_skill, _, _ = self._context(current_baseline)
        route = self._router.route(
            diff, previous_baseline, current_baseline, current_skill
        )
        if route.decision == "no_op":
            return BaselineChangeHandoff(
                route.decision, diff, route, previous_process, selected_solution, selected_blueprint
            )
        if route.decision == "incremental_constraint_recompile":
            recompiled = self._recompile_solution(
                previous_process, selected_solution, selected_blueprint, route.new_constraints
            )
            return BaselineChangeHandoff(
                route.decision, diff, route, previous_process,
                recompiled.new_solution, recompiled.new_blueprint,
                recompile_result=recompiled,
            )
        current_process = self.compile_process_spec(current_baseline)
        route = self._router.route(
            diff, previous_baseline, current_baseline, current_skill,
            previous_process=previous_process, current_process=current_process,
        )
        bundle = self._compile_solution(current_process)
        selected = next(
            plan for plan in bundle.plans if plan.solution_id == bundle.recommended_solution_id
        )
        blueprint = self._compile_blueprint(current_process, selected)
        return BaselineChangeHandoff(
            route.decision, diff, route, current_process, selected, blueprint, bundle=bundle
        )
