"""Explicit, deterministic Requirement confirmation state transitions for R-M4."""

from __future__ import annotations

import json
from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    RequirementChange,
    RequirementConfirmation,
    RequirementConfirmationRecord,
    RequirementItem,
    RequirementModification,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector


_INACTIVE_STATUSES = {"rejected", "superseded"}


def _digest(prefix: str, payload: object) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{sha256(material.encode('utf-8')).hexdigest()[:12]}"


class RequirementConfirmationApplier:
    """Applies one real confirmation event to create exactly one new state version."""

    def apply(
        self,
        state: RequirementState,
        confirmation: RequirementConfirmation,
        *,
        recorded_at: str | None = None,
    ) -> tuple[RequirementState, list[RequirementChange], RequirementConfirmationRecord]:
        if confirmation.project_id != state.project_id:
            raise ValueError("confirmation project_id must match RequirementState")
        if confirmation.state_version != state.state_version:
            raise ValueError("stale confirmation state_version")

        supplied_open_conflicts = {
            (conflict.category, tuple(sorted(conflict.requirement_ids)))
            for conflict in state.conflicts
            if conflict.status == "open"
        }
        detected_open_conflicts = {
            (conflict.category, tuple(sorted(conflict.requirement_ids)))
            for conflict in ConflictDetector().detect(state)
            if conflict.status == "open"
        }
        if supplied_open_conflicts != detected_open_conflicts:
            raise ValueError(
                "stale conflict snapshot; run RequirementAnalysis before confirmation"
            )

        items = {item.requirement_id: item for item in state.items}
        action_ids = {
            *confirmation.confirmed_requirement_ids,
            *confirmation.rejected_requirement_ids,
            *(modification.target_requirement_id for modification in confirmation.modifications),
        }
        unknown = sorted(action_ids - set(items))
        if unknown:
            raise ValueError(f"unknown requirement_id: {unknown[0]}")
        inactive = sorted(
            requirement_id
            for requirement_id in action_ids
            if items[requirement_id].status in _INACTIVE_STATUSES
        )
        if inactive:
            raise ValueError(f"inactive requirement cannot be confirmed: {inactive[0]}")

        open_conflicts = [conflict for conflict in state.conflicts if conflict.status == "open"]
        open_conflict_ids = {
            requirement_id
            for conflict in open_conflicts
            for requirement_id in conflict.requirement_ids
        }
        modified_ids = {
            modification.target_requirement_id for modification in confirmation.modifications
        }
        blocked_modifications = sorted(modified_ids & open_conflict_ids)
        if blocked_modifications:
            raise ValueError(
                f"human modification cannot target an open conflict: {blocked_modifications[0]}"
            )

        confirmed_ids = set(confirmation.confirmed_requirement_ids)
        rejected_ids = set(confirmation.rejected_requirement_ids)
        if confirmation.confirmation_level == "internal":
            internal_conflict_rejections = sorted(rejected_ids & open_conflict_ids)
            if internal_conflict_rejections:
                raise ValueError("internal confirmation cannot reject an open customer conflict")
            customer_truth_rejections = sorted(
                requirement_id
                for requirement_id in rejected_ids
                if items[requirement_id].confirmation_level == "customer"
            )
            if customer_truth_rejections:
                raise ValueError("internal confirmation cannot reject customer-confirmed truth")
        else:
            for conflict in open_conflicts:
                winners = confirmed_ids & set(conflict.requirement_ids)
                if len(winners) > 1:
                    raise ValueError(
                        f"customer confirmation cannot select multiple winners for {conflict.conflict_id}"
                    )

        changes: list[RequirementChange] = []
        for requirement_id in sorted(confirmed_ids):
            item = items[requirement_id]
            level = confirmation.confirmation_level
            if item.status == "confirmed" and item.confirmation_level == level:
                continue
            items[requirement_id] = item.model_copy(
                update={"status": "confirmed", "confirmation_level": level}
            )
            changes.append(
                RequirementChange(
                    requirement_id=requirement_id,
                    change_type="confirmed",
                    before_value=item.value,
                    after_value=item.value,
                    explanation=f"explicit {level} confirmation by {confirmation.confirmed_by}",
                )
            )

        for requirement_id in sorted(rejected_ids):
            item = items[requirement_id]
            if item.status == "rejected":
                continue
            items[requirement_id] = item.model_copy(
                update={"status": "rejected", "confirmation_level": "none"}
            )
            changes.append(
                RequirementChange(
                    requirement_id=requirement_id,
                    change_type="rejected",
                    before_value=item.value,
                    after_value=None,
                    explanation=f"explicit {confirmation.confirmation_level} rejection",
                )
            )

        for modification in sorted(
            confirmation.modifications,
            key=lambda item: item.target_requirement_id,
        ):
            self._apply_modification(items, state, modification, changes)

        conflicts = list(state.conflicts)
        if confirmation.confirmation_level == "customer":
            for index, conflict in enumerate(conflicts):
                if conflict.status != "open":
                    continue
                member_ids = set(conflict.requirement_ids)
                winners = sorted(confirmed_ids & member_ids)
                if winners:
                    winner_id = winners[0]
                    for loser_id in sorted(member_ids - {winner_id}):
                        loser = items[loser_id]
                        if loser.status != "superseded":
                            items[loser_id] = loser.model_copy(
                                update={"status": "superseded", "confirmation_level": "none"}
                            )
                            changes.append(
                                RequirementChange(
                                    requirement_id=loser_id,
                                    change_type="superseded",
                                    before_value=loser.value,
                                    after_value=None,
                                    explanation=f"superseded by customer-confirmed {winner_id}",
                                )
                            )
                    conflicts[index] = conflict.model_copy(
                        update={"status": "resolved", "resolution_requirement_id": winner_id}
                    )
                    changes.append(
                        RequirementChange(
                            requirement_id=winner_id,
                            change_type="resolved",
                            before_value=None,
                            after_value=items[winner_id].value,
                            explanation=f"resolved conflict {conflict.conflict_id}",
                        )
                    )
                elif member_ids and member_ids <= rejected_ids:
                    conflicts[index] = conflict.model_copy(
                        update={"status": "resolved", "resolution_requirement_id": None}
                    )
                    anchor_id = min(member_ids)
                    changes.append(
                        RequirementChange(
                            requirement_id=anchor_id,
                            change_type="resolved",
                            before_value=None,
                            after_value=None,
                            explanation=f"all candidates rejected for {conflict.conflict_id}",
                        )
                    )

        if not changes:
            raise ValueError("confirmation does not change RequirementState")

        result_version = state.state_version + 1
        result = RequirementState(
            project_id=state.project_id,
            state_version=result_version,
            source_ids=list(state.source_ids),
            items=[items[requirement_id] for requirement_id in sorted(items)],
            gaps=[],
            conflicts=sorted(conflicts, key=lambda conflict: conflict.conflict_id),
            selected_skill_id=state.selected_skill_id,
            organization=state.organization,
            contacts=list(state.contacts),
            created_at=state.created_at,
            updated_at=None,
        )
        canonical_confirmation = {
            "project_id": confirmation.project_id,
            "state_version": confirmation.state_version,
            "confirmation_level": confirmation.confirmation_level,
            "confirmed_requirement_ids": sorted(confirmation.confirmed_requirement_ids),
            "rejected_requirement_ids": sorted(confirmation.rejected_requirement_ids),
            "modifications": [
                modification.model_dump(mode="json")
                for modification in sorted(
                    confirmation.modifications,
                    key=lambda item: item.target_requirement_id,
                )
            ],
            "confirmed_by": confirmation.confirmed_by,
            "note": confirmation.note,
        }
        record_payload = {
            "project_id": state.project_id,
            "source_state_version": state.state_version,
            "result_state_version": result_version,
            "confirmation": canonical_confirmation,
        }
        record = RequirementConfirmationRecord(
            confirmation_id=_digest("confirmation", record_payload),
            project_id=state.project_id,
            source_state_version=state.state_version,
            result_state_version=result_version,
            confirmation_level=confirmation.confirmation_level,
            confirmed_requirement_ids=sorted(confirmation.confirmed_requirement_ids),
            rejected_requirement_ids=sorted(confirmation.rejected_requirement_ids),
            modifications=sorted(
                confirmation.modifications,
                key=lambda item: item.target_requirement_id,
            ),
            confirmed_by=confirmation.confirmed_by,
            note=confirmation.note,
            recorded_at=recorded_at,
        )
        return result, sorted(changes, key=lambda item: (item.requirement_id, item.change_type)), record

    @staticmethod
    def _apply_modification(
        items: dict[str, RequirementItem],
        state: RequirementState,
        modification: RequirementModification,
        changes: list[RequirementChange],
    ) -> None:
        old = items[modification.target_requirement_id]
        subject = modification.new_subject if modification.new_subject is not None else old.subject
        value = modification.new_value if modification.new_value is not None else old.value
        parameters = (
            modification.new_parameters
            if modification.new_parameters is not None
            else old.parameters
        )
        process_detail = (
            modification.process_detail
            if modification.process_detail is not None
            else old.process_detail
        )
        pain_point_detail = (
            modification.pain_point_detail
            if modification.pain_point_detail is not None
            else old.pain_point_detail
        )
        comparison = (
            subject,
            value,
            parameters,
            process_detail,
            pain_point_detail,
        )
        original = (
            old.subject,
            old.value,
            old.parameters,
            old.process_detail,
            old.pain_point_detail,
        )
        if comparison == original:
            raise ValueError(
                f"RequirementModification does not change {old.requirement_id}"
            )
        identity_payload = {
            "project_id": state.project_id,
            "source_state_version": state.state_version,
            "target_requirement_id": old.requirement_id,
            "subject": subject,
            "value": value,
            "parameters": parameters,
            "process_detail": (
                process_detail.model_dump(mode="json") if process_detail is not None else None
            ),
            "pain_point_detail": (
                pain_point_detail.model_dump(mode="json") if pain_point_detail is not None else None
            ),
            "reason": modification.reason,
        }
        new_id = _digest("req", identity_payload)
        if new_id in items:
            raise ValueError(f"human modification already exists: {new_id}")
        new_item = RequirementItem(
            requirement_id=new_id,
            category=old.category,
            subject=subject,
            value=value,
            parameters=parameters,
            provenance="human_modified",
            status="confirmed",
            confirmation_level="internal",
            confidence=old.confidence,
            source_refs=list(old.source_refs),
            process_detail=process_detail,
            pain_point_detail=pain_point_detail,
            supersedes_requirement_ids=sorted(
                {old.requirement_id, *old.supersedes_requirement_ids}
            ),
        )
        items[old.requirement_id] = old.model_copy(
            update={"status": "superseded", "confirmation_level": "none"}
        )
        items[new_id] = new_item
        changes.extend(
            [
                RequirementChange(
                    requirement_id=old.requirement_id,
                    change_type="superseded",
                    before_value=old.value,
                    after_value=None,
                    explanation=f"superseded by human modification {new_id}",
                ),
                RequirementChange(
                    requirement_id=new_id,
                    change_type="added",
                    before_value=None,
                    after_value=new_item.value,
                    explanation="human modification added as internal-confirmed truth",
                ),
            ]
        )
