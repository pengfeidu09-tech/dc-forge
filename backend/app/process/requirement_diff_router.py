"""Deterministic routing from Requirement business changes to frozen B-M8 services."""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementDiff,
    RequirementDiffRoute,
    RequirementSkill,
)
from backend.app.process.process_spec_adapter import ProcessSpecAdapter


CONSTRAINT_CATEGORIES = {"security", "approval", "budget", "time", "data", "risk"}


class RequirementDiffRouter:
    def __init__(self, adapter: ProcessSpecAdapter | None = None) -> None:
        self._adapter = adapter or ProcessSpecAdapter()

    def route(
        self,
        diff: RequirementDiff,
        previous: RequirementBaseline,
        current: RequirementBaseline,
        skill: RequirementSkill,
        *,
        previous_process: ProcessSpec | None = None,
        current_process: ProcessSpec | None = None,
    ) -> RequirementDiffRoute:
        if diff.project_id != previous.project_id or diff.project_id != current.project_id:
            raise ValueError("RequirementDiff project closure failed")
        if not diff.changes:
            return RequirementDiffRoute(
                decision="no_op",
                explanation="No solution-facing business semantic change was detected.",
            )

        previous_by_id = {item.requirement_id: item for item in previous.confirmed_items}
        current_by_id = {item.requirement_id: item for item in current.confirmed_items}
        categories: set[str] = set()
        has_removal = False
        incremental_constraints = []
        removed_ids = set(diff.removed_requirement_ids)
        for change in diff.changes:
            item = current_by_id.get(change.requirement_id) or previous_by_id.get(change.requirement_id)
            if item is None:
                raise ValueError(f"RequirementDiff change is not closed over baselines: {change.requirement_id}")
            categories.add(item.category)
            if change.requirement_id in removed_ids:
                has_removal = True
                continue
            if item.category in CONSTRAINT_CATEGORIES:
                constraint = self._adapter.constraint_from_item(current.project_id, item, skill)
                if constraint is None:
                    has_removal = True
                else:
                    incremental_constraints.append(constraint)

        changed_categories = sorted(categories)
        all_constraints = categories <= CONSTRAINT_CATEGORIES
        if all_constraints and not has_removal:
            by_id = {constraint.id: constraint for constraint in incremental_constraints}
            return RequirementDiffRoute(
                decision="incremental_constraint_recompile",
                changed_categories=changed_categories,
                explanation=(
                    "All changes are applicable constraint additions/updates representable by "
                    "B-M8.7 new_constraints append/override semantics."
                ),
                new_constraints=[by_id[item_id] for item_id in sorted(by_id)],
            )

        if all_constraints and has_removal:
            explanation = (
                "Constraint removal or applicable-to-not-applicable change requires full compile; "
                "constraint removal is not representable by B-M8.7 new_constraints append/override semantics."
            )
        else:
            explanation = "Structural or mixed requirement change requires full solution compile."

        structural = sorted(categories - CONSTRAINT_CATEGORIES)
        if (
            structural
            and previous_process is not None
            and current_process is not None
            and previous_process.model_dump() == current_process.model_dump()
        ):
            raise ValueError(
                "structural requirement change is not representable in ProcessSpec v1.0: "
                + ", ".join(structural)
            )
        return RequirementDiffRoute(
            decision="full_solution_recompile",
            changed_categories=changed_categories,
            explanation=explanation,
        )
