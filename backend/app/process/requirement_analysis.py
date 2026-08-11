"""Deterministic R-M4 RequirementAnalysis composition."""

from __future__ import annotations

from backend.app.contracts.requirement_intelligence import (
    QuestionHistoryEntry,
    RequirementAnalysis,
    RequirementChange,
    RequirementSkill,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.readiness import ReadinessEvaluator


_ACTIVE_STATUSES = {"confirmed", "pending", "conflicted"}


class RequirementAnalysisBuilder:
    def build(
        self,
        state: RequirementState,
        skill: RequirementSkill,
        *,
        changes: list[RequirementChange],
        previous_state_version: int | None = None,
        history: list[QuestionHistoryEntry] | None = None,
        customer_confirmation_complete: bool = False,
    ) -> RequirementAnalysis:
        conflicts = ConflictDetector().detect(state, skill)
        gaps = GapDetector().detect(state, skill, conflicts)
        analyzed_state = RequirementState.model_validate(
            {
                **state.model_dump(mode="json"),
                "gaps": [gap.model_dump(mode="json") for gap in gaps],
                "conflicts": [conflict.model_dump(mode="json") for conflict in conflicts],
            }
        )
        readiness = ReadinessEvaluator().evaluate(
            analyzed_state,
            skill,
            gaps,
            conflicts,
            customer_confirmation_complete=customer_confirmation_complete,
        )
        next_questions = QuestionPlanner().plan(
            analyzed_state,
            skill,
            gaps,
            conflicts,
            history=history,
        )
        summary = self._summary(analyzed_state)
        return RequirementAnalysis(
            project_id=state.project_id,
            previous_state_version=previous_state_version,
            current_state=analyzed_state,
            changes=sorted(changes, key=lambda item: (item.requirement_id, item.change_type)),
            readiness=readiness,
            next_questions=next_questions,
            customer_confirmation_summary=summary,
        )

    @staticmethod
    def _summary(state: RequirementState) -> str:
        active_items = sorted(
            (item for item in state.items if item.status in _ACTIVE_STATUSES),
            key=lambda item: item.requirement_id,
        )
        open_conflicts = sorted(
            (conflict for conflict in state.conflicts if conflict.status == "open"),
            key=lambda conflict: conflict.conflict_id,
        )
        blocking_gaps = sorted(
            (gap for gap in state.gaps if gap.blocking),
            key=lambda gap: gap.gap_id,
        )
        pending_confirmation = [
            item.requirement_id
            for item in active_items
            if not (
                item.status == "confirmed" and item.confirmation_level == "customer"
            )
        ]
        lines = [
            "以下为待客户确认的当前需求理解。",
            "当前核心 Requirement：",
        ]
        lines.extend(
            (
                f"- {item.requirement_id} | {item.category} | {item.value} | "
                f"status={item.status} | confirmation={item.confirmation_level} | "
                f"provenance={item.provenance}"
            )
            for item in active_items
        )
        lines.append(f"open conflict：{len(open_conflicts)}")
        lines.extend(
            f"- {conflict.conflict_id} | {conflict.category} | {','.join(sorted(conflict.requirement_ids))}"
            for conflict in open_conflicts
        )
        lines.append(f"blocking gap：{len(blocking_gaps)}")
        lines.extend(
            f"- {gap.gap_id} | {gap.category} | {gap.gap_type}"
            for gap in blocking_gaps
        )
        lines.append(
            "准备让客户确认的 Requirement："
            + (", ".join(pending_confirmation) if pending_confirmation else "无")
        )
        return "\n".join(lines)
