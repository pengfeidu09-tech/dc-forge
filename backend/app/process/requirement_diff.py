"""Deterministic business-semantic diff for customer-confirmed baselines."""

from __future__ import annotations

import json
from typing import Any

from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementChange,
    RequirementDiff,
    RequirementItem,
)
from backend.app.process.process_spec_adapter import normalize_text


_SCALAR_CATEGORIES = {"industry", "department", "business_goal"}
_CONSTRAINT_CATEGORIES = {"security", "approval", "budget", "time", "data", "risk"}


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def semantic_identity(item: RequirementItem) -> tuple[str, str]:
    if item.category in _SCALAR_CATEGORIES:
        return item.category, ""
    if item.category == "current_process":
        return item.category, item.process_detail.process_node_id
    if item.category == "pain_point":
        return item.category, item.pain_point_detail.pain_point_id
    if item.category in _CONSTRAINT_CATEGORIES:
        return item.category, normalize_text(item.subject)
    return item.category, _payload_text(semantic_payload(item))


def semantic_payload(item: RequirementItem) -> dict[str, Any]:
    return {
        "category": item.category,
        "subject": normalize_text(item.subject),
        "value": normalize_text(item.value),
        "parameters": _canonical(item.parameters),
        "process_detail": _canonical(item.process_detail.model_dump()) if item.process_detail else None,
        "pain_point_detail": _canonical(item.pain_point_detail.model_dump()) if item.pain_point_detail else None,
    }


def _payload_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class RequirementDiffEngine:
    def index(self, baseline: RequirementBaseline) -> dict[tuple[str, str], tuple[RequirementItem, dict[str, Any]]]:
        result: dict[tuple[str, str], tuple[RequirementItem, dict[str, Any]]] = {}
        for item in sorted(baseline.confirmed_items, key=lambda value: value.requirement_id):
            identity = semantic_identity(item)
            payload = semantic_payload(item)
            if identity in result and result[identity][1] != payload:
                raise ValueError(f"baseline has conflicting semantic identity: {identity[0]} / {identity[1]}")
            if identity not in result or item.requirement_id < result[identity][0].requirement_id:
                result[identity] = item, payload
        return result

    def compare(self, previous: RequirementBaseline, current: RequirementBaseline) -> RequirementDiff:
        if previous.project_id != current.project_id:
            raise ValueError("RequirementBaseline project_id values must match for diff")
        if previous.baseline_id == current.baseline_id:
            raise ValueError("cannot diff the same RequirementBaseline")
        if previous.baseline_version >= current.baseline_version:
            raise ValueError("previous baseline_version must be strictly earlier than current")
        old, new = self.index(previous), self.index(current)
        added_ids: list[str] = []
        removed_ids: list[str] = []
        changed_ids: list[str] = []
        changes: list[RequirementChange] = []
        for identity in sorted(set(old) | set(new)):
            before = old.get(identity)
            after = new.get(identity)
            if before is None:
                added_ids.append(after[0].requirement_id)
                changes.append(RequirementChange(
                    requirement_id=after[0].requirement_id,
                    change_type="added",
                    after_value=_payload_text(after[1]),
                    explanation=f"added {identity[0]} semantic requirement",
                ))
            elif after is None:
                removed_ids.append(before[0].requirement_id)
                changes.append(RequirementChange(
                    requirement_id=before[0].requirement_id,
                    change_type="updated",
                    before_value=_payload_text(before[1]),
                    after_value=None,
                    explanation="requirement removed from current baseline",
                ))
            elif before[1] != after[1]:
                changed_ids.append(after[0].requirement_id)
                changes.append(RequirementChange(
                    requirement_id=after[0].requirement_id,
                    change_type="updated",
                    before_value=_payload_text(before[1]),
                    after_value=_payload_text(after[1]),
                    explanation=f"updated {identity[0]} semantic requirement",
                ))
        return RequirementDiff(
            project_id=previous.project_id,
            previous_baseline_id=previous.baseline_id,
            current_baseline_id=current.baseline_id,
            added_requirement_ids=sorted(added_ids),
            removed_requirement_ids=sorted(removed_ids),
            changed_requirement_ids=sorted(changed_ids),
            changes=changes,
        )
