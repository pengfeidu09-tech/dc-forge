"""Deterministic Next Best Question planning for Requirement Intelligence R-M4."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    NextQuestion,
    QuestionHistoryEntry,
    RequirementConflict,
    RequirementGap,
    RequirementSkill,
    RequirementState,
)


_CATEGORY_ORDER = {
    "security": 1,
    "approval": 1,
    "data": 1,
    "available_data": 2,
    "existing_system": 2,
    "integration": 2,
    "industry": 3,
    "department": 3,
    "business_goal": 3,
    "current_process": 4,
    "pain_point": 4,
    "target_metric": 6,
    "scope": 7,
    "deliverable": 7,
    "budget": 8,
    "time": 8,
}
_DEFAULT_TEXT = {
    "industry": "请确认本项目所属行业。",
    "department": "请确认本项目的主要业务部门。",
    "business_goal": "请确认本项目最重要的业务目标。",
    "current_process": "请说明当前业务流程及主要参与角色。",
    "pain_point": "请确认当前流程中最需要解决的核心痛点。",
    "available_data": "请确认当前可用于项目的数据和材料。",
    "existing_system": "请确认当前涉及的既有系统及其边界。",
    "integration": "请确认方案需要对接的系统与集成边界。",
    "target_metric": "请确认用于验证项目价值的目标指标。",
    "scope": "请确认本期项目范围。",
    "deliverable": "请确认本期预期交付物。",
    "budget": "请确认当前预算范围。",
    "time": "请确认期望实施时间或关键里程碑。",
}


def _question_id(material: list[str]) -> str:
    digest = sha256("|".join(material).encode("utf-8")).hexdigest()[:12]
    return f"question-{digest}"


class QuestionPlanner:
    """Ranks unresolved deterministic issues and returns at most three questions."""

    def plan(
        self,
        state: RequirementState,
        skill: RequirementSkill,
        gaps: list[RequirementGap],
        conflicts: list[RequirementConflict],
        *,
        history: list[QuestionHistoryEntry] | None = None,
    ) -> list[NextQuestion]:
        suppressed_ids = {entry.question_id for entry in (history or [])}
        item_by_id = {item.requirement_id: item for item in state.items}
        candidates: list[tuple[tuple[object, ...], NextQuestion]] = []
        conflict_categories: set[str] = set()

        for conflict in sorted(conflicts, key=lambda item: item.conflict_id):
            if conflict.status != "open":
                continue
            conflict_categories.add(conflict.category)
            requirement_ids = sorted(conflict.requirement_ids)
            values = sorted(
                {
                    item_by_id[requirement_id].value.strip()
                    for requirement_id in requirement_ids
                    if requirement_id in item_by_id
                },
                key=lambda value: value.casefold(),
            )
            identifier = _question_id(
                [
                    state.project_id,
                    "conflict",
                    conflict.category,
                    conflict.conflict_id,
                    *requirement_ids,
                    *values,
                ]
            )
            if identifier in suppressed_ids:
                continue
            related_gap_ids = sorted(
                gap.gap_id
                for gap in gaps
                if gap.category == conflict.category and gap.gap_type == "conflicted"
            )
            displayed_values = " / ".join(values) if values else "多个不同口径"
            question = NextQuestion(
                question_id=identifier,
                text=(
                    f"{conflict.category} 当前存在多个口径（{displayed_values}），"
                    "请确认当前有效规则。"
                ),
                target_category=conflict.category,
                priority="critical",
                blocking=True,
                reason=f"open {conflict.severity}-severity conflict requires explicit confirmation",
                related_gap_ids=related_gap_ids,
                related_conflict_ids=[conflict.conflict_id],
            )
            candidates.append(((0, conflict.category, conflict.conflict_id), question))

        gaps_by_category: dict[str, list[RequirementGap]] = defaultdict(list)
        for gap in gaps:
            if gap.category not in conflict_categories:
                gaps_by_category[gap.category].append(gap)

        rule_by_category = {
            rule.category: rule
            for rule in sorted(skill.rules, key=lambda item: item.rule_id)
        }
        hard_categories = {
            rule.category for rule in skill.rules if rule.hard_constraint
        } | {"security", "approval", "data"}
        customer_confirmed_categories = {
            item.category
            for item in state.items
            if item.status == "confirmed" and item.confirmation_level == "customer"
        }

        for category in sorted(gaps_by_category):
            if category in customer_confirmed_categories:
                continue
            category_gaps = sorted(gaps_by_category[category], key=lambda gap: gap.gap_id)
            gap_ids = [gap.gap_id for gap in category_gaps]
            gap_types = sorted({gap.gap_type for gap in category_gaps})
            related_requirement_ids = sorted(
                {
                    requirement_id
                    for gap in category_gaps
                    for requirement_id in gap.related_requirement_ids
                }
            )
            identifier = _question_id(
                [
                    state.project_id,
                    "gap",
                    category,
                    *gap_types,
                    *gap_ids,
                    *related_requirement_ids,
                ]
            )
            if identifier in suppressed_ids:
                continue
            tier = 1 if category in hard_categories else _CATEGORY_ORDER.get(category, 7)
            priority = self._priority(tier)
            rule = rule_by_category.get(category)
            text = (
                rule.question_template
                if rule is not None
                else _DEFAULT_TEXT.get(category, f"请确认 {category} 的当前要求。")
            )
            reason = "; ".join(sorted({gap.reason for gap in category_gaps}))
            question = NextQuestion(
                question_id=identifier,
                text=text,
                target_category=category,
                priority=priority,
                blocking=any(gap.blocking for gap in category_gaps),
                reason=reason,
                related_gap_ids=gap_ids,
                related_conflict_ids=[],
            )
            candidates.append(((tier, category, tuple(gap_ids)), question))

        return [question for _, question in sorted(candidates, key=lambda pair: pair[0])[:3]]

    @staticmethod
    def _priority(tier: int) -> str:
        if tier <= 2:
            return "high"
        if tier <= 7:
            return "medium" if tier >= 4 else "high"
        return "low"
