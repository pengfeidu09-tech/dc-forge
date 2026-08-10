"""Deterministic truth-state reduction for Requirement Intelligence R-M1."""

from __future__ import annotations

from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    RequirementChange,
    RequirementConflict,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)

_AUTO_CONFIRM_BLOCKED = {"ai_inferred", "sales_judgment", "presales_judgment"}


def _key(item: RequirementItem) -> tuple[str, str, str]:
    return (item.category, item.subject.strip().casefold(), item.value.strip().casefold())


def _identity(project_id: str, item: RequirementItem) -> str:
    material = "|".join(
        [project_id, item.category, item.subject.strip(), item.value.strip()]
        + [ref.source_id for ref in sorted(item.source_refs, key=lambda ref: (ref.source_id, ref.locator or "", ref.excerpt))]
    )
    return f"req-{sha256(material.encode('utf-8')).hexdigest()[:12]}"


def _merge_refs(*groups: list[RequirementSourceRef]) -> list[RequirementSourceRef]:
    refs = {
        (ref.source_id, ref.locator, ref.excerpt): ref
        for group in groups
        for ref in group
    }
    return [refs[key] for key in sorted(refs)]


class RequirementReducer:
    """Merges normalized candidates without treating rank or confidence as truth."""

    def reduce(
        self,
        previous: RequirementState | None,
        candidates: list[RequirementItem],
        context: CustomerContextPackage,
    ) -> tuple[RequirementState, list[RequirementChange]]:
        if previous is not None and previous.project_id != context.project_id:
            raise ValueError("previous RequirementState project_id must match context project_id")
        if previous is not None and context.previous_state_version not in (None, previous.state_version):
            raise ValueError("context previous_state_version must match previous RequirementState")

        items = {item.requirement_id: item for item in (previous.items if previous else [])}
        source_ids = sorted(set((previous.source_ids if previous else []) + context.source_ids))
        conflicts = list(previous.conflicts if previous else [])
        changes: list[RequirementChange] = []

        for raw_candidate in sorted(candidates, key=lambda item: (_key(item), item.requirement_id)):
            candidate = raw_candidate.model_copy(
                update={"requirement_id": raw_candidate.requirement_id or _identity(context.project_id, raw_candidate)}
            )
            if candidate.provenance in _AUTO_CONFIRM_BLOCKED and candidate.status == "confirmed":
                candidate = candidate.model_copy(update={"status": "pending", "confirmation_level": "none"})

            exact = next((item for item in items.values() if _key(item) == _key(candidate)), None)
            if exact is not None:
                merged_refs = _merge_refs(exact.source_refs, candidate.source_refs)
                supersedes = sorted(set(exact.supersedes_requirement_ids + candidate.supersedes_requirement_ids))
                update: dict[str, object] = {
                    "source_refs": merged_refs,
                    "supersedes_requirement_ids": supersedes,
                }
                change_type: str | None = "updated" if merged_refs != exact.source_refs else None
                if candidate.status in {"confirmed", "rejected"} and candidate.status != exact.status:
                    update["status"] = candidate.status
                    update["confirmation_level"] = candidate.confirmation_level
                    change_type = candidate.status
                for requirement_id in candidate.supersedes_requirement_ids:
                    old = items.get(requirement_id)
                    if old is not None and old.requirement_id != exact.requirement_id and old.status != "superseded":
                        items[old.requirement_id] = old.model_copy(
                            update={"status": "superseded", "confirmation_level": "none"}
                        )
                        changes.append(
                            RequirementChange(
                                requirement_id=old.requirement_id,
                                change_type="superseded",
                                before_value=old.value,
                                after_value=None,
                                explanation=f"superseded by {exact.requirement_id}",
                            )
                        )
                if change_type:
                    items[exact.requirement_id] = exact.model_copy(update=update)
                    changes.append(
                        RequirementChange(
                            requirement_id=exact.requirement_id,
                            change_type=change_type,
                            before_value=exact.value,
                            after_value=exact.value,
                            explanation="duplicate requirement merged with source/status update",
                        )
                    )
                elif supersedes != exact.supersedes_requirement_ids:
                    items[exact.requirement_id] = exact.model_copy(update=update)
                if candidate.status == "confirmed" and candidate.confirmation_level == "customer":
                    for index, conflict in enumerate(conflicts):
                        if (
                            conflict.status == "open"
                            and exact.requirement_id in conflict.requirement_ids
                            and set(candidate.supersedes_requirement_ids) & set(conflict.requirement_ids)
                        ):
                            conflicts[index] = conflict.model_copy(
                                update={"status": "resolved", "resolution_requirement_id": exact.requirement_id}
                            )
                continue

            superseded = [
                items[requirement_id]
                for requirement_id in candidate.supersedes_requirement_ids
                if requirement_id in items
            ]
            for old in superseded:
                if old.status != "superseded":
                    items[old.requirement_id] = old.model_copy(update={"status": "superseded", "confirmation_level": "none"})
                    changes.append(
                        RequirementChange(
                            requirement_id=old.requirement_id,
                            change_type="superseded",
                            before_value=old.value,
                            after_value=None,
                            explanation=f"superseded by {candidate.requirement_id}",
                        )
                    )

            confirmed_conflict = next(
                (
                    item
                    for item in items.values()
                    if item.category == candidate.category
                    and item.subject.strip().casefold() == candidate.subject.strip().casefold()
                    and item.value != candidate.value
                    and item.status == "confirmed"
                    and item.requirement_id not in candidate.supersedes_requirement_ids
                ),
                None,
            )
            if confirmed_conflict is not None:
                candidate = candidate.model_copy(update={"status": "conflicted", "confirmation_level": "none"})
                conflict_ids = sorted([confirmed_conflict.requirement_id, candidate.requirement_id])
                conflict_id = f"conflict-{sha256('|'.join(conflict_ids).encode('utf-8')).hexdigest()[:12]}"
                if not any(conflict.conflict_id == conflict_id for conflict in conflicts):
                    conflicts.append(
                        RequirementConflict(
                            conflict_id=conflict_id,
                            category=candidate.category,
                            requirement_ids=conflict_ids,
                            description="new source conflicts with an existing confirmed requirement",
                            severity="high" if candidate.category in {"security", "approval", "data"} else "medium",
                            status="open",
                        )
                    )
                changes.append(
                    RequirementChange(
                        requirement_id=candidate.requirement_id,
                        change_type="conflicted",
                        before_value=confirmed_conflict.value,
                        after_value=candidate.value,
                        explanation=f"conflicts with confirmed requirement {confirmed_conflict.requirement_id}",
                    )
                )
            else:
                changes.append(
                    RequirementChange(
                        requirement_id=candidate.requirement_id,
                        change_type="added",
                        before_value=None,
                        after_value=candidate.value,
                        explanation="new requirement candidate added deterministically",
                    )
                )
            items[candidate.requirement_id] = candidate

        state = RequirementState(
            project_id=context.project_id,
            state_version=(previous.state_version + 1) if previous else 1,
            source_ids=source_ids,
            items=[items[requirement_id] for requirement_id in sorted(items)],
            gaps=list(previous.gaps if previous else []),
            conflicts=sorted(conflicts, key=lambda conflict: conflict.conflict_id),
            selected_skill_id=(previous.selected_skill_id if previous else None),
            organization=context.organization or (previous.organization if previous else None),
            contacts=list(context.contacts) if context.contacts else list(previous.contacts if previous else []),
            created_at=(previous.created_at if previous else None),
            updated_at=None,
        )
        return state, sorted(changes, key=lambda change: (change.requirement_id, change.change_type))
