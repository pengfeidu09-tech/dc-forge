"""Deterministic R-M3 conflict detection over active Requirement Truth."""

from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    RequirementConflict,
    RequirementItem,
    RequirementSkill,
    RequirementState,
)


_WHITESPACE = re.compile(r"\s+")
_ACTIVE_STATUSES = {"confirmed", "pending", "conflicted"}
_DEFAULT_HIGH_CATEGORIES = {"security", "approval", "data"}


def _normalized(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _slot(item: RequirementItem) -> tuple[str, str]:
    return item.category, _normalized(item.subject)


class ConflictDetector:
    def detect(
        self,
        state: RequirementState,
        skill: RequirementSkill | None = None,
    ) -> list[RequirementConflict]:
        existing = list(state.conflicts)
        generated: list[RequirementConflict] = []
        replaced_conflict_ids: set[str] = set()
        hard_categories = set(_DEFAULT_HIGH_CATEGORIES)
        if skill is not None:
            hard_categories.update(rule.category for rule in skill.rules if rule.hard_constraint)

        groups: dict[tuple[str, str], list[RequirementItem]] = defaultdict(list)
        for item in state.items:
            if item.status in _ACTIVE_STATUSES:
                groups[_slot(item)].append(item)

        for slot in sorted(groups):
            items = sorted(groups[slot], key=lambda item: item.requirement_id)
            if len({_normalized(item.value) for item in items}) < 2:
                continue
            item_ids = [item.requirement_id for item in items]
            item_id_set = set(item_ids)
            overlapping = [
                conflict
                for conflict in existing
                if conflict.status == "open"
                and conflict.category == slot[0]
                and len(set(conflict.requirement_ids) & item_id_set) >= 2
            ]
            exact = [
                conflict
                for conflict in overlapping
                if set(conflict.requirement_ids) == item_id_set
            ]
            if exact:
                preserved = min(exact, key=lambda conflict: conflict.conflict_id)
                replaced_conflict_ids.update(
                    conflict.conflict_id
                    for conflict in overlapping
                    if conflict.conflict_id != preserved.conflict_id
                )
                continue
            replaced_conflict_ids.update(conflict.conflict_id for conflict in overlapping)
            material = "|".join([state.project_id, *item_ids])
            conflict_id = f"conflict-{sha256(material.encode('utf-8')).hexdigest()[:12]}"
            generated.append(
                RequirementConflict(
                    conflict_id=conflict_id,
                    category=slot[0],
                    requirement_ids=item_ids,
                    description=f"active requirements disagree for {slot[0]} / {slot[1]}",
                    severity="high" if slot[0] in hard_categories else "medium",
                    status="open",
                )
            )

        preserved_existing = [
            conflict
            for conflict in existing
            if conflict.conflict_id not in replaced_conflict_ids
        ]
        return sorted([*preserved_existing, *generated], key=lambda conflict: conflict.conflict_id)
