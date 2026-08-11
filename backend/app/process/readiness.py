"""Deterministic completeness and readiness gates for R-M3."""

from __future__ import annotations

from backend.app.contracts.requirement_intelligence import (
    ReadinessAssessment,
    RequirementConflict,
    RequirementGap,
    RequirementSkill,
    RequirementState,
)


_ACTIVE_STATUSES = {"confirmed", "pending", "conflicted"}
_PROCESS_MINIMUM = {"industry", "department", "business_goal", "current_process", "pain_point"}


class ReadinessEvaluator:
    def evaluate(
        self,
        state: RequirementState,
        skill: RequirementSkill,
        gaps: list[RequirementGap],
        conflicts: list[RequirementConflict],
        *,
        customer_confirmation_complete: bool = False,
    ) -> ReadinessAssessment:
        completeness = self._completeness(state, skill)
        open_conflicts = sorted(
            (conflict for conflict in conflicts if conflict.status == "open"),
            key=lambda conflict: conflict.conflict_id,
        )
        blocking_gap_ids = sorted(gap.gap_id for gap in gaps if gap.blocking)
        non_blocking_gap_ids = sorted(gap.gap_id for gap in gaps if not gap.blocking)
        open_conflict_ids = [conflict.conflict_id for conflict in open_conflicts]

        preliminary_categories = set(_PROCESS_MINIMUM)
        preliminary_categories.update(
            rule.category for rule in skill.rules if rule.missing_blocks_preliminary
        )
        preliminary_missing = sorted(
            (gap for gap in gaps if gap.gap_type == "missing" and gap.category in preliminary_categories),
            key=lambda gap: (gap.category, gap.gap_id),
        )
        high_conflicts = [conflict for conflict in open_conflicts if conflict.severity == "high"]

        reasons: set[str] = set()
        for gap in preliminary_missing:
            reasons.add(f"{gap.category} missing")
        for conflict in high_conflicts:
            reasons.add(f"open high-severity {conflict.category} conflict")

        if preliminary_missing or high_conflicts:
            stage = "DISCOVERY"
            preliminary = False
            formal = False
        else:
            formal_gaps = sorted((gap for gap in gaps if gap.blocking), key=lambda gap: (gap.category, gap.gap_id))
            for gap in formal_gaps:
                if gap.gap_type == "unconfirmed":
                    reasons.add(f"{gap.category} requirement is known but not customer-confirmed")
                elif gap.gap_type == "missing":
                    reasons.add(f"{gap.category} missing")
                elif gap.gap_type == "conflicted":
                    reasons.add(f"open {gap.category} conflict")
            for conflict in open_conflicts:
                reasons.add(f"open {conflict.severity}-severity {conflict.category} conflict")
            if not customer_confirmation_complete:
                reasons.add("customer confirmation is incomplete")

            formal = not formal_gaps and not open_conflicts and customer_confirmation_complete
            preliminary = True
            stage = "CONFIRMED_READY" if formal else "PRELIMINARY_READY"

        if stage == "CONFIRMED_READY":
            reasons.add("all formal readiness gates satisfied")

        return ReadinessAssessment(
            stage=stage,
            completeness_score=completeness,
            blocking_gap_ids=blocking_gap_ids,
            non_blocking_gap_ids=non_blocking_gap_ids,
            open_conflict_ids=open_conflict_ids,
            can_generate_preliminary_solution=preliminary,
            can_generate_formal_solution=formal,
            reasons=sorted(reasons),
        )

    @staticmethod
    def _completeness(state: RequirementState, skill: RequirementSkill) -> float:
        active_categories = {
            item.category for item in state.items if item.status in _ACTIVE_STATUSES
        }
        score = sum(
            dimension.weight
            for dimension in skill.completeness_dimensions
            if active_categories.intersection(dimension.categories)
        )
        return round(min(100.0, max(0.0, score)), 2)
