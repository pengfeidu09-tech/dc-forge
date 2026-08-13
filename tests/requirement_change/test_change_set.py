"""R-CHANGE1 G1-G7 generic ChangeSet and multi-change orchestration."""

from __future__ import annotations

from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    CustomerSourceRecord,
    RequirementItem,
    RequirementSourceRef,
)
from backend.app.requirement_change.change_set import (
    ChangeSetReviewAction,
    MultiChangeConfirmationOrchestrator,
    RequirementChangeSetBuilder,
)
from backend.app.requirement_change.formal_removal import (
    FileRemovalAuditRepository,
    FormalRemovalService,
    RemovalEvidenceBinding,
)
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _feedback(project_id: str) -> CustomerSourceRecord:
    return CustomerSourceRecord(
        source_id="feedback-1",
        project_id=project_id,
        source_type="meeting_minutes",
        title="customer feedback",
        inline_content="本轮客户确认以下需求变化。",
        author_role="customer",
    )


def _candidate(
    requirement_id: str,
    category: str,
    subject: str,
    value: str,
    *,
    parameters: dict | None = None,
) -> RequirementItem:
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=subject,
        value=value,
        parameters=parameters or {},
        provenance="ai_extracted",
        status="pending",
        confirmation_level="none",
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="feedback-1", excerpt=value)],
    )


def _state_with_feedback(state, *candidates: RequirementItem):
    return state.model_copy(
        update={
            "state_version": state.state_version + 1,
            "source_ids": [*state.source_ids, "feedback-1"],
            "items": [*state.items, *candidates],
        }
    )


def _orchestrator(tmp_path: Path) -> MultiChangeConfirmationOrchestrator:
    return MultiChangeConfirmationOrchestrator(
        FormalRemovalService(FileRemovalAuditRepository(tmp_path))
    )


def test_g1_one_feedback_projects_three_independent_candidates() -> None:
    state, baseline = state_and_baseline()
    candidates = [
        _candidate("candidate-security", "security", "audit encryption", "encrypt audit records"),
        _candidate("candidate-time", "time", "rollout window", "complete rollout in one quarter"),
        _candidate("candidate-integration", "integration", "SRM", "connect SRM"),
    ]

    change_set = RequirementChangeSetBuilder().build(baseline, _state_with_feedback(state, *candidates))

    assert len(change_set.items) == 3
    assert {entry.category for entry in change_set.items} == {"security", "time", "integration"}
    assert {entry.suggested_change_type for entry in change_set.items} == {"ADDED"}


def test_golden_a_same_identity_changed_payload_projects_updated_not_pending() -> None:
    state, baseline = state_and_baseline()
    previous = next(item for item in baseline.confirmed_items if item.category == "approval")
    candidate = _candidate(
        "candidate-updated", previous.category, previous.subject, "updated approval rule",
        parameters={"threshold_amount": 800000},
    )
    state = _state_with_feedback(state, candidate)

    projected = RequirementChangeSetBuilder().build(baseline, state)

    assert len(projected.items) == 1
    assert projected.items[0].suggested_change_type == "UPDATED"
    assert projected.items[0].review_disposition == "ACCEPT"


def test_g2_compatible_constraint_batch_confirmation_routes_incremental(tmp_path: Path) -> None:
    state, previous = state_and_baseline()
    candidates = [
        _candidate("candidate-approval", "approval", "delegated approval", "delegate approval"),
        _candidate("candidate-security", "security", "audit encryption", "encrypt audit records"),
        _candidate("candidate-time", "time", "rollout window", "complete rollout in one quarter"),
    ]
    state = _state_with_feedback(state, *candidates)
    change_set = RequirementChangeSetBuilder().build(previous, state)
    assert len(change_set.items) == 3

    result = _orchestrator(tmp_path).apply(
        previous,
        state,
        [_feedback(state.project_id)],
        [ChangeSetReviewAction(target_requirement_id=item.candidate_requirement_id, disposition="ACCEPT") for item in change_set.items],
        confirmation_level="customer",
        confirmed_by="customer-owner",
    )
    finalized = MultiChangeConfirmationOrchestrator.finalize_baseline_diff_route(
        previous, result.state, skill(), confirmed_by="customer-owner", confirmation_summary="batch accepted"
    )

    assert len(finalized.diff.added_requirement_ids) == 3
    assert finalized.route.decision == "incremental_constraint_recompile"
    assert finalized.route.changed_categories == ["approval", "security", "time"]


def test_g3_integration_addition_routes_full(tmp_path: Path) -> None:
    state, previous = state_and_baseline()
    candidate = _candidate("candidate-integration", "integration", "SRM", "connect SRM")
    state = _state_with_feedback(state, candidate)
    projected = RequirementChangeSetBuilder().build(previous, state)
    result = _orchestrator(tmp_path).apply(
        previous, state, [_feedback(state.project_id)],
        [ChangeSetReviewAction(target_requirement_id=projected.items[0].candidate_requirement_id, disposition="ACCEPT")],
        confirmation_level="customer", confirmed_by="customer-owner",
    )

    finalized = MultiChangeConfirmationOrchestrator.finalize_baseline_diff_route(
        previous, result.state, skill(), confirmed_by="customer-owner", confirmation_summary="integration accepted"
    )

    assert finalized.route.decision == "full_solution_recompile"
    assert finalized.route.changed_categories == ["integration"]


def test_g4_constraint_and_integration_batch_routes_full(tmp_path: Path) -> None:
    state, previous = state_and_baseline()
    candidates = [
        _candidate("candidate-security", "security", "audit encryption", "encrypt audit records"),
        _candidate("candidate-integration", "integration", "SRM", "connect SRM"),
    ]
    state = _state_with_feedback(state, *candidates)
    projected = RequirementChangeSetBuilder().build(previous, state)
    result = _orchestrator(tmp_path).apply(
        previous, state, [_feedback(state.project_id)],
        [ChangeSetReviewAction(target_requirement_id=entry.candidate_requirement_id, disposition="ACCEPT") for entry in projected.items],
        confirmation_level="customer", confirmed_by="customer-owner",
    )

    finalized = MultiChangeConfirmationOrchestrator.finalize_baseline_diff_route(
        previous, result.state, skill(), confirmed_by="customer-owner", confirmation_summary="mixed accepted"
    )

    assert finalized.route.decision == "full_solution_recompile"
    assert finalized.route.changed_categories == ["integration", "security"]


def test_g5_semantic_duplicate_produces_no_changes_and_no_op_route() -> None:
    state, previous = state_and_baseline()
    original = next(item for item in previous.confirmed_items if item.category == "security")
    duplicate = _candidate(
        "candidate-duplicate-security", original.category, original.subject, original.value,
        parameters=dict(original.parameters),
    )
    state = _state_with_feedback(state, duplicate)

    projected = RequirementChangeSetBuilder().build(previous, state)
    finalized = MultiChangeConfirmationOrchestrator.finalize_baseline_diff_route(
        previous, state, skill(), confirmed_by="customer-owner", confirmation_summary="no material change"
    )

    assert projected.items == []
    assert finalized.diff.changes == []
    assert finalized.route.decision == "no_op"


def test_g6_ambiguous_identity_is_pending_clarification_and_cannot_enter_baseline(tmp_path: Path) -> None:
    state, previous = state_and_baseline()
    candidates = [
        _candidate("candidate-data-a", "data", "retention", "retain 30 days"),
        _candidate("candidate-data-b", "data", "retention", "retain 90 days"),
    ]
    state = _state_with_feedback(state, *candidates)
    projected = RequirementChangeSetBuilder().build(previous, state)
    assert {entry.review_disposition for entry in projected.items} == {"PENDING_CLARIFICATION"}

    result = _orchestrator(tmp_path).apply(
        previous, state, [_feedback(state.project_id)],
        [ChangeSetReviewAction(target_requirement_id=entry.candidate_requirement_id, disposition="PENDING_CLARIFICATION") for entry in projected.items],
        confirmation_level="customer", confirmed_by="customer-owner",
    )

    assert result.state == state
    assert all(item.status == "pending" for item in result.state.items if item.requirement_id.startswith("candidate-data"))


def test_g7_candidate_reject_and_formal_removal_are_distinct(tmp_path: Path) -> None:
    state, previous = state_and_baseline()
    scope = item("req-scope-phase-1", "scope", "delivery scope", "phase one")
    previous = previous.model_copy(update={"confirmed_items": [*previous.confirmed_items, scope]})
    candidate = _candidate("candidate-budget", "budget", "pilot budget", "pilot budget cap")
    state = _state_with_feedback(state.model_copy(update={"items": [*state.items, scope]}), candidate)
    orchestrator = _orchestrator(tmp_path)

    rejected = orchestrator.apply(
        previous, state, [_feedback(state.project_id)],
        [ChangeSetReviewAction(target_requirement_id=candidate.requirement_id, disposition="REJECT")],
        confirmation_level="internal", confirmed_by="reviewer",
    )
    removed = orchestrator.apply(
        previous, rejected.state, [_feedback(state.project_id)],
        [ChangeSetReviewAction(
            target_requirement_id=scope.requirement_id,
            disposition="REMOVE",
            evidence=RemovalEvidenceBinding(source_id="feedback-1", excerpt="本轮客户确认以下需求变化。"),
        )],
        confirmation_level="customer", confirmed_by="customer-owner",
    )

    assert next(item for item in rejected.state.items if item.requirement_id == candidate.requirement_id).status == "rejected"
    assert removed.formal_removal_audits[0].target_requirement_id == scope.requirement_id
    assert next(item for item in removed.state.items if item.requirement_id == scope.requirement_id).status == "rejected"
