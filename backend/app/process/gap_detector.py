"""Three-layer deterministic requirement gap detection for R-M3."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    RequirementConflict,
    RequirementGap,
    RequirementItem,
    RequirementSkill,
    RequirementState,
)


_ACTIVE_STATUSES = {"confirmed", "pending", "conflicted"}


@dataclass(frozen=True)
class _GapRule:
    rule_id: str
    category: str
    description: str
    formal_blocking: bool
    requires_customer_confirmation: bool


_PROCESS_CLOSURE_RULES = (
    _GapRule("process-industry", "industry", "industry is required for minimum ProcessSpec closure", True, True),
    _GapRule("process-department", "department", "department is required for minimum ProcessSpec closure", True, True),
    _GapRule("process-business-goal", "business_goal", "business goal is required for problem definition", True, True),
    _GapRule("process-current-process", "current_process", "current process is required for problem definition", True, True),
    _GapRule("process-pain-point", "pain_point", "pain point is required for problem definition", True, True),
)

_GENERIC_PRESALES_RULES = (
    _GapRule("generic-data", "available_data", "available data should be understood", False, False),
    _GapRule("generic-systems", "existing_system", "existing systems should be understood", False, False),
    _GapRule("generic-business-rules", "business_rule", "business rules should be understood", False, False),
    _GapRule("generic-target-metric", "target_metric", "target metrics should be understood", False, False),
    _GapRule("generic-scope", "scope", "solution scope should be understood", False, False),
    _GapRule("generic-deliverable", "deliverable", "deliverables should be understood", False, False),
    _GapRule("generic-budget", "budget", "budget detail is recommended", False, False),
    _GapRule("generic-time", "time", "timeline detail is recommended", False, False),
)


class GapDetector:
    def detect(
        self,
        state: RequirementState,
        skill: RequirementSkill,
        conflicts: list[RequirementConflict],
    ) -> list[RequirementGap]:
        active_items = [item for item in state.items if item.status in _ACTIVE_STATUSES]
        open_conflicts = [conflict for conflict in conflicts if conflict.status == "open"]
        open_categories = {conflict.category for conflict in open_conflicts}
        not_applicable_categories = {
            rule.category for rule in skill.rules if rule.hard_constraint
        }
        gaps: dict[tuple[str, str], RequirementGap] = {}

        rules = [*_PROCESS_CLOSURE_RULES, *_GENERIC_PRESALES_RULES]
        rules.extend(
            _GapRule(
                rule_id=f"skill-{rule.rule_id}",
                category=rule.category,
                description=rule.description,
                formal_blocking=rule.unconfirmed_blocks_formal,
                requires_customer_confirmation=rule.requires_customer_confirmation,
            )
            for rule in skill.rules
        )
        for rule in rules:
            if rule.category in open_categories:
                continue
            category_items = [
                item
                for item in active_items
                if item.category == rule.category
                and (
                    item.parameters.get("not_applicable") is not True
                    or item.category in not_applicable_categories
                )
            ]
            related = sorted(item.requirement_id for item in category_items)
            if not related:
                gap = self._gap(state.project_id, rule, "missing", [])
                self._keep_stricter(gaps, gap)
                continue
            confirmed = any(
                item.category == rule.category
                and item.status == "confirmed"
                and item.confirmation_level == "customer"
                for item in category_items
            )
            if rule.requires_customer_confirmation and not confirmed:
                gap = self._gap(state.project_id, rule, "unconfirmed", related)
                self._keep_stricter(gaps, gap)

        for conflict in open_conflicts:
            rule = _GapRule(
                rule_id=f"conflict-{conflict.conflict_id}",
                category=conflict.category,
                description=f"open {conflict.severity}-severity {conflict.category} conflict",
                formal_blocking=True,
                requires_customer_confirmation=True,
            )
            gap = self._gap(state.project_id, rule, "conflicted", sorted(conflict.requirement_ids))
            self._keep_stricter(gaps, gap)

        return sorted(gaps.values(), key=lambda gap: gap.gap_id)

    @staticmethod
    def _gap(
        project_id: str,
        rule: _GapRule,
        gap_type: str,
        related_requirement_ids: list[str],
    ) -> RequirementGap:
        material = "|".join([project_id, rule.category, gap_type, rule.rule_id])
        gap_id = f"gap-{sha256(material.encode('utf-8')).hexdigest()[:12]}"
        return RequirementGap(
            gap_id=gap_id,
            category=rule.category,
            gap_type=gap_type,
            description=(
                f"{rule.category} is known but not customer-confirmed"
                if gap_type == "unconfirmed"
                else rule.description
            ),
            blocking=rule.formal_blocking,
            reason=f"{rule.rule_id}: {rule.description}",
            related_requirement_ids=related_requirement_ids,
        )

    @staticmethod
    def _keep_stricter(
        gaps: dict[tuple[str, str], RequirementGap],
        candidate: RequirementGap,
    ) -> None:
        key = candidate.category, candidate.gap_type
        existing = gaps.get(key)
        if existing is None or (candidate.blocking and not existing.blocking):
            gaps[key] = candidate
