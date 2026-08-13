"""Private generic R-CHANGE1 ChangeSet projection and review orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, field_validator

from backend.app.contracts.common import StrictModel
from backend.app.contracts.requirement_intelligence import (
    CustomerSourceRecord,
    RequirementBaseline,
    RequirementConfirmation,
    RequirementConfirmationRecord,
    RequirementDiff,
    RequirementDiffRoute,
    RequirementItem,
    RequirementModification,
    RequirementSkill,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier
from backend.app.process.requirement_diff import RequirementDiffEngine, semantic_identity, semantic_payload
from backend.app.process.requirement_diff_router import RequirementDiffRouter
from backend.app.requirement_change.formal_removal import (
    FormalRemovalService,
    RemovalEvidenceBinding,
    RequirementChangeAuditRecord,
    RequirementChangeDecision,
)


ReviewDisposition = Literal[
    "ACCEPT", "REJECT", "MODIFY", "PENDING_CLARIFICATION", "REMOVE", "NOT_APPLICABLE"
]
SuggestedChangeType = Literal["ADDED", "UPDATED", "CONFLICT", "PENDING_CLARIFICATION"]


class RequirementChangeSetItem(StrictModel):
    """Private UI/API review projection; it does not change Requirement contracts."""

    candidate_requirement_id: str
    matched_baseline_requirement_id: str | None = None
    suggested_change_type: SuggestedChangeType
    category: str
    subject: str
    previous_value: str | None = None
    previous_parameters: dict = Field(default_factory=dict)
    proposed_value: str
    proposed_parameters: dict = Field(default_factory=dict)
    source_refs: list[RequirementSourceRef]
    confidence: float = Field(ge=0, le=1)
    conflict_status: Literal["none", "open", "resolved"] = "none"
    review_disposition: ReviewDisposition

    _candidate_id = field_validator("candidate_requirement_id")(
        lambda value: value.strip() or (_ for _ in ()).throw(ValueError("candidate_requirement_id must not be blank"))
    )


class RequirementChangeSet(StrictModel):
    project_id: str
    previous_baseline_id: str
    previous_baseline_version: int = Field(ge=1)
    source_state_version: int = Field(ge=1)
    items: list[RequirementChangeSetItem] = Field(default_factory=list)


class ChangeSetReviewAction(StrictModel):
    target_requirement_id: str
    disposition: ReviewDisposition
    modification: RequirementModification | None = None
    evidence: RemovalEvidenceBinding | None = None

    @field_validator("target_requirement_id")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target_requirement_id must not be blank")
        return value


@dataclass(frozen=True)
class ChangeSetReviewResult:
    state: RequirementState
    formal_removal_audits: list[RequirementChangeAuditRecord]
    confirmation_records: list[RequirementConfirmationRecord]


@dataclass(frozen=True)
class BaselineRouteResult:
    baseline: RequirementBaseline
    diff: RequirementDiff
    route: RequirementDiffRoute


class RequirementChangeSetBuilder:
    """Projects only non-baseline proposals using frozen deterministic semantic rules."""

    def build(self, previous: RequirementBaseline, current: RequirementState) -> RequirementChangeSet:
        if previous.project_id != current.project_id:
            raise ValueError("RequirementChangeSet project closure failed")
        baseline_by_identity = {
            semantic_identity(item): item for item in previous.confirmed_items
        }
        baseline_ids = {item.requirement_id for item in previous.confirmed_items}
        candidates = [
            item for item in current.items
            if item.requirement_id not in baseline_ids
            and item.status not in {"rejected", "superseded"}
        ]
        candidate_identity_counts: dict[tuple[str, str], int] = {}
        for candidate in candidates:
            identity = semantic_identity(candidate)
            candidate_identity_counts[identity] = candidate_identity_counts.get(identity, 0) + 1
        open_conflict_ids = {
            requirement_id
            for conflict in current.conflicts
            if conflict.status == "open"
            for requirement_id in conflict.requirement_ids
        }
        projected: list[RequirementChangeSetItem] = []
        for candidate in sorted(candidates, key=lambda item: item.requirement_id):
            identity = semantic_identity(candidate)
            matched = baseline_by_identity.get(identity)
            ambiguous = candidate_identity_counts[identity] > 1
            in_conflict = candidate.requirement_id in open_conflict_ids or candidate.status == "conflicted"
            if ambiguous:
                suggested: SuggestedChangeType = "PENDING_CLARIFICATION"
                disposition: ReviewDisposition = "PENDING_CLARIFICATION"
            elif matched is None:
                if in_conflict:
                    suggested = "CONFLICT"
                    disposition = "PENDING_CLARIFICATION"
                else:
                    suggested = "ADDED"
                    disposition = "ACCEPT"
            elif semantic_payload(matched) != semantic_payload(candidate):
                suggested = "UPDATED"
                disposition = "ACCEPT"
            else:
                # A semantic duplicate cannot create a solution-facing change.
                continue
            projected.append(
                RequirementChangeSetItem(
                    candidate_requirement_id=candidate.requirement_id,
                    matched_baseline_requirement_id=matched.requirement_id if matched else None,
                    suggested_change_type=suggested,
                    category=candidate.category,
                    subject=candidate.subject,
                    previous_value=matched.value if matched else None,
                    previous_parameters=dict(matched.parameters) if matched else {},
                    proposed_value=candidate.value,
                    proposed_parameters=dict(candidate.parameters),
                    source_refs=list(candidate.source_refs),
                    confidence=candidate.confidence,
                    conflict_status="open" if in_conflict else "none",
                    review_disposition=disposition,
                )
            )
        return RequirementChangeSet(
            project_id=previous.project_id,
            previous_baseline_id=previous.baseline_id,
            previous_baseline_version=previous.baseline_version,
            source_state_version=current.state_version,
            items=projected,
        )


class MultiChangeConfirmationOrchestrator:
    """Converts reviewed private actions into existing confirmation and removal primitives."""

    def __init__(self, formal_removal_service: FormalRemovalService) -> None:
        self._formal_removal_service = formal_removal_service

    def apply(
        self,
        previous: RequirementBaseline,
        state: RequirementState,
        feedback_sources: list[CustomerSourceRecord],
        actions: list[ChangeSetReviewAction],
        *,
        confirmation_level: Literal["internal", "customer"],
        confirmed_by: str,
        note: str | None = None,
    ) -> ChangeSetReviewResult:
        if previous.project_id != state.project_id:
            raise ValueError("previous formal Baseline project_id must match RequirementState")
        if not actions:
            return ChangeSetReviewResult(state, [], [])
        action_ids = [action.target_requirement_id for action in actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("ChangeSet review actions must target unique requirement IDs")

        accepted: list[str] = []
        rejected: list[str] = []
        modifications: list[RequirementModification] = []
        removals: list[ChangeSetReviewAction] = []
        for action in actions:
            if action.disposition == "ACCEPT":
                accepted.append(action.target_requirement_id)
            elif action.disposition == "REJECT":
                rejected.append(action.target_requirement_id)
            elif action.disposition == "MODIFY":
                if action.modification is None or action.modification.target_requirement_id != action.target_requirement_id:
                    raise ValueError("MODIFY requires a matching RequirementModification")
                modifications.append(action.modification)
            elif action.disposition == "PENDING_CLARIFICATION":
                continue
            else:
                if action.evidence is None:
                    raise ValueError("REMOVE/NOT_APPLICABLE requires RemovalEvidenceBinding")
                removals.append(action)

        current = state
        confirmation_records: list[RequirementConfirmationRecord] = []
        if accepted or rejected or modifications:
            confirmation = RequirementConfirmation(
                project_id=current.project_id,
                state_version=current.state_version,
                confirmation_level=confirmation_level,
                confirmed_requirement_ids=sorted(accepted),
                rejected_requirement_ids=sorted(rejected),
                modifications=sorted(modifications, key=lambda item: item.target_requirement_id),
                confirmed_by=confirmed_by,
                note=note,
            )
            current, _, confirmation_record = RequirementConfirmationApplier().apply(current, confirmation)
            confirmation_records.append(confirmation_record)

        audits: list[RequirementChangeAuditRecord] = []
        for action in removals:
            result = self._formal_removal_service.apply(
                previous,
                current,
                feedback_sources,
                RequirementChangeDecision(
                    target_requirement_id=action.target_requirement_id,
                    action=action.disposition,
                    evidence=action.evidence,
                    confirmation_level=confirmation_level,
                    confirmed_by=confirmed_by,
                    note=note,
                ),
            )
            current = result.state
            audits.append(result.audit_record)
            confirmation_records.append(result.confirmation_record)
        return ChangeSetReviewResult(current, audits, confirmation_records)

    @staticmethod
    def finalize_baseline_diff_route(
        previous: RequirementBaseline,
        state: RequirementState,
        skill: RequirementSkill,
        *,
        confirmed_by: str,
        confirmation_summary: str,
    ) -> BaselineRouteResult:
        conflicts = ConflictDetector().detect(state, skill)
        gaps = GapDetector().detect(state, skill, conflicts)
        analyzed = state.model_copy(update={"conflicts": conflicts, "gaps": gaps})
        readiness = ReadinessEvaluator().evaluate(
            analyzed, skill, gaps, conflicts, customer_confirmation_complete=True
        )
        baseline = RequirementBaselineBuilder(skill).build(
            analyzed,
            readiness,
            baseline_version=previous.baseline_version + 1,
            confirmed_by=confirmed_by,
            confirmation_summary=confirmation_summary,
        )
        diff = RequirementDiffEngine().compare(previous, baseline)
        route = RequirementDiffRouter().route(diff, previous, baseline, skill)
        return BaselineRouteResult(baseline, diff, route)
