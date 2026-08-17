"""Thin orchestration over the frozen Requirement and B-M8 engines."""

from __future__ import annotations

import os
from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    CustomerSourceRecord,
    RequirementAnalysis,
    RequirementBaseline,
    RequirementConfirmation,
    RequirementExtractionWarning,
)
from backend.app.process.requirement_analysis import RequirementAnalysisBuilder
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier
from backend.app.process.requirement_extractor import RequirementExtractor
from backend.app.process.requirement_reducer import RequirementReducer
from backend.app.process.requirement_repository import RequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService
from backend.app.requirement_change.change_set import (
    ChangeSetReviewAction,
    MultiChangeConfirmationOrchestrator,
    RequirementChangeSet,
    RequirementChangeSetBuilder,
)
from backend.app.requirement_change.formal_removal import (
    FileRemovalAuditRepository,
    FormalRemovalService,
)
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.agent_configuration import configured_database_path
from backend.app.solution.workspace_database import (
    SqliteRemovalAuditRepository,
    SqliteRequirementRepository,
)


class InternalConsoleService:
    def __init__(
        self,
        repository: RequirementRepository | None = None,
        skill_loader: RequirementSkillLoader | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        repository_root = Path(__file__).parents[3]
        self.repository = repository or SqliteRequirementRepository(
            configured_database_path()
        )
        self.audit_repository = (
            SqliteRemovalAuditRepository(self.repository.database_path)
            if isinstance(self.repository, SqliteRequirementRepository)
            else FileRemovalAuditRepository(
                self.repository._root / "requirement-change-audits"
            )
        )
        self.skill_loader = skill_loader or RequirementSkillLoader(
            repository_root / "data" / "requirement_skills"
        )
        self.provider = provider or self._extraction_provider()

    @staticmethod
    def _extraction_provider() -> LLMProvider:
        timeout_raw = os.getenv("EXTRACTION_LLM_TIMEOUT_SECONDS", "90").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError as error:
            raise RuntimeError("EXTRACTION_LLM_TIMEOUT_SECONDS must be a positive number") from error
        if timeout <= 0:
            raise RuntimeError("EXTRACTION_LLM_TIMEOUT_SECONDS must be a positive number")

        thinking_raw = os.getenv("EXTRACTION_LLM_ENABLE_THINKING", "false").strip().casefold()
        if thinking_raw not in {"true", "false"}:
            raise RuntimeError("EXTRACTION_LLM_ENABLE_THINKING must be true or false")

        response_format = os.getenv("EXTRACTION_LLM_RESPONSE_FORMAT", "json_object").strip()
        if response_format != "json_object":
            raise RuntimeError("EXTRACTION_LLM_RESPONSE_FORMAT must be json_object")

        delegate = OpenAICompatibleProvider(
            timeout=timeout,
            request_options={
                "enable_thinking": thinking_raw == "true",
                "response_format": {"type": response_format},
            },
        )
        from backend.app.solution.feishu_requirement import (
            FeishuRequirementExtractionProvider,
        )

        return FeishuRequirementExtractionProvider(delegate)

    def analyze(
        self,
        project_id: str,
        sources: list[CustomerSourceRecord],
        *,
        previous_state_version: int | None,
        skill_id: str,
    ) -> tuple[RequirementAnalysis, list[RequirementExtractionWarning]]:
        previous = None
        if previous_state_version is not None:
            previous = self.repository.load_state(project_id, previous_state_version)
            if previous is None:
                raise FileNotFoundError("previous RequirementState does not exist")
        elif self.repository.list_versions(project_id):
            raise ValueError("previous_state_version is required for an existing project")

        skill = self.skill_loader.resolve(skill_id)
        context = CustomerContextPackage(
            project_id=project_id,
            sources=sources,
            previous_state_version=previous_state_version,
            requirement_skill_ids=[skill_id],
        )
        extraction = RequirementExtractor(self.provider).extract(context)
        state, changes = RequirementReducer().reduce(
            previous, extraction.candidates, context
        )
        state = state.model_copy(update={"selected_skill_id": skill.skill_id})
        analysis = RequirementAnalysisBuilder().build(
            state,
            skill,
            changes=changes,
            previous_state_version=previous_state_version,
            customer_confirmation_complete=False,
        )
        self.repository.save_state(analysis.current_state)
        return analysis, extraction.warnings

    def confirm(
        self, confirmation: RequirementConfirmation
    ) -> tuple[RequirementAnalysis, RequirementBaseline | None]:
        state = self.repository.load_state(
            confirmation.project_id, confirmation.state_version
        )
        if state is None:
            raise FileNotFoundError("RequirementState does not exist")
        if not state.selected_skill_id:
            raise ValueError("RequirementState selected_skill_id is required")
        skill = self.skill_loader.resolve(state.selected_skill_id)
        new_state, changes, record = RequirementConfirmationApplier().apply(
            state, confirmation
        )
        analysis = RequirementAnalysisBuilder().build(
            new_state,
            skill,
            changes=changes,
            previous_state_version=state.state_version,
            customer_confirmation_complete=confirmation.confirmation_level == "customer",
        )
        self.repository.save_state(analysis.current_state)
        self.repository.save_confirmation_record(record)

        baseline = None
        if analysis.readiness.stage == "CONFIRMED_READY":
            versions = self.repository.list_baseline_versions(confirmation.project_id)
            baseline = RequirementBaselineBuilder(skill).build(
                analysis.current_state,
                analysis.readiness,
                baseline_version=(versions[-1] + 1 if versions else 1),
                confirmed_by=confirmation.confirmed_by,
                confirmation_summary=analysis.customer_confirmation_summary,
            )
            self.repository.save_baseline(baseline)
        return analysis, baseline

    def requirement_service(self) -> RequirementIntelligenceService:
        return RequirementIntelligenceService(self.repository, self.skill_loader)

    def _baseline(self, project_id: str, version: int) -> RequirementBaseline:
        baseline = self.repository.load_baseline(project_id, version)
        if baseline is None:
            raise FileNotFoundError(
                f"RequirementBaseline version does not exist: {project_id}/{version}"
            )
        return baseline

    def compile(self, project_id: str, baseline_version: int):
        baseline = self._baseline(project_id, baseline_version)
        return self.requirement_service().compile_solution_from_baseline(baseline)

    def diff(
        self,
        project_id: str,
        previous_baseline_version: int,
        current_baseline_version: int,
    ):
        previous = self._baseline(project_id, previous_baseline_version)
        current = self._baseline(project_id, current_baseline_version)
        service = self.requirement_service()
        return service.diff(previous, current), service.route_diff(previous, current)

    def change_set(
        self, project_id: str, previous_baseline_version: int, state_version: int
    ) -> RequirementChangeSet:
        previous = self._baseline(project_id, previous_baseline_version)
        state = self.repository.load_state(project_id, state_version)
        if state is None:
            raise FileNotFoundError("RequirementState does not exist")
        return RequirementChangeSetBuilder().build(previous, state)

    def review_change_set(
        self,
        project_id: str,
        previous_baseline_version: int,
        state_version: int,
        feedback_sources: list[CustomerSourceRecord],
        actions: list[ChangeSetReviewAction],
        *,
        confirmation_level: str,
        confirmed_by: str,
        note: str | None,
    ):
        previous = self._baseline(project_id, previous_baseline_version)
        state = self.repository.load_state(project_id, state_version)
        if state is None:
            raise FileNotFoundError("RequirementState does not exist")
        orchestrator = MultiChangeConfirmationOrchestrator(
            FormalRemovalService(self.audit_repository)
        )
        reviewed = orchestrator.apply(
            previous, state, feedback_sources, actions,
            confirmation_level=confirmation_level, confirmed_by=confirmed_by, note=note,
        )
        if reviewed.state.state_version == state.state_version:
            analysis = RequirementAnalysisBuilder().build(
                state, self.skill_loader.resolve(state.selected_skill_id), changes=[],
                previous_state_version=state.state_version - 1,
                customer_confirmation_complete=False,
            )
            return analysis, None, None, None, reviewed.formal_removal_audits
        skill = self.skill_loader.resolve(reviewed.state.selected_skill_id)
        analysis = RequirementAnalysisBuilder().build(
            reviewed.state, skill, previous_state_version=state.state_version,
            customer_confirmation_complete=confirmation_level == "customer",
        )
        self.repository.save_state(analysis.current_state)
        for record in reviewed.confirmation_records:
            self.repository.save_confirmation_record(record)
        baseline = diff = route = None
        if analysis.readiness.stage == "CONFIRMED_READY":
            finalized = MultiChangeConfirmationOrchestrator.finalize_baseline_diff_route(
                previous, analysis.current_state, skill,
                confirmed_by=confirmed_by,
                confirmation_summary=analysis.customer_confirmation_summary,
            )
            baseline, diff, route = finalized.baseline, finalized.diff, finalized.route
            self.repository.save_baseline(baseline)
            self.repository.save_diff(diff)
        return analysis, baseline, diff, route, reviewed.formal_removal_audits

    def recompile(
        self,
        project_id: str,
        previous_baseline_version: int,
        current_baseline_version: int,
        previous_process,
        selected_solution,
        selected_blueprint,
    ):
        previous = self._baseline(project_id, previous_baseline_version)
        current = self._baseline(project_id, current_baseline_version)
        return self.requirement_service().apply_baseline_change(
            previous,
            current,
            previous_process,
            selected_solution,
            selected_blueprint,
        )
