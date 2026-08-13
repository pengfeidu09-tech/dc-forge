"""R-CHANGE1 R1-R5: evidence-bound formal removal orchestration."""

from __future__ import annotations

import pytest

from backend.app.contracts.requirement_intelligence import CustomerSourceRecord
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_diff import RequirementDiffEngine
from backend.app.process.requirement_diff_router import RequirementDiffRouter
from backend.app.requirement_change.formal_removal import (
    FileRemovalAuditRepository,
    FormalRemovalService,
    RemovalEvidenceBinding,
    RequirementChangeDecision,
)
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _feedback(project_id: str, *, source_id: str = "feedback-1", content: str = "取消本期范围") -> CustomerSourceRecord:
    return CustomerSourceRecord(
        source_id=source_id,
        project_id=project_id,
        source_type="meeting_minutes",
        title="customer feedback",
        inline_content=content,
        author_role="customer",
    )


def _decision(target_requirement_id: str, *, action: str = "REMOVE", level: str = "customer") -> RequirementChangeDecision:
    return RequirementChangeDecision(
        target_requirement_id=target_requirement_id,
        action=action,
        evidence=RemovalEvidenceBinding(source_id="feedback-1", excerpt="取消本期范围"),
        confirmation_level=level,
        confirmed_by="customer-owner",
    )


def _active_state_with_feedback(state):
    return state.model_copy(update={"state_version": 2, "source_ids": [*state.source_ids, "feedback-1"]})


def _baseline_with_removable_scope(state, baseline):
    scope = item("req-scope-phase-1", "scope", "delivery scope", "phase one")
    return (
        state.model_copy(update={"items": [*state.items, scope]}),
        baseline.model_copy(update={"confirmed_items": [*baseline.confirmed_items, scope]}),
        scope,
    )


def test_r1_rejecting_a_new_candidate_is_not_formal_removal(tmp_path) -> None:
    state, baseline = state_and_baseline()
    candidate = next(item for item in state.items if item.category == "approval").model_copy(
        update={"requirement_id": "new-candidate", "status": "pending", "confirmation_level": "none"}
    )
    state = state.model_copy(update={"state_version": 2, "items": [*state.items, candidate]})

    result = FormalRemovalService(FileRemovalAuditRepository(tmp_path)).reject_candidate(
        state, "new-candidate", confirmed_by="reviewer"
    )

    assert result.disposition == "REJECTED_CANDIDATE"
    assert next(item for item in result.state.items if item.requirement_id == "new-candidate").status == "rejected"
    assert result.audit_record is None
    assert baseline.confirmed_items


def test_r2_evidence_bound_customer_removal_preserves_history_and_routes_full(tmp_path) -> None:
    state, previous = state_and_baseline()
    state, previous, target = _baseline_with_removable_scope(state, previous)
    state = _active_state_with_feedback(state)
    repository = FileRemovalAuditRepository(tmp_path)
    service = FormalRemovalService(repository)

    removal = service.apply(
        previous,
        state,
        [_feedback(state.project_id)],
        _decision(target.requirement_id),
    )
    resolved = removal.state
    resolved_conflicts = ConflictDetector().detect(resolved, skill())
    gaps = GapDetector().detect(resolved, skill(), resolved_conflicts)
    resolved = resolved.model_copy(update={"conflicts": resolved_conflicts, "gaps": gaps})
    readiness = ReadinessEvaluator().evaluate(resolved, skill(), gaps, resolved_conflicts, customer_confirmation_complete=True)
    current = RequirementBaselineBuilder(skill()).build(
        resolved,
        readiness,
        baseline_version=2,
        confirmed_by="customer-owner",
        confirmation_summary="customer removed approval requirement",
    )
    diff = RequirementDiffEngine().compare(previous, current)
    route = RequirementDiffRouter().route(diff, previous, current, skill())

    removed = next(item for item in removal.state.items if item.requirement_id == target.requirement_id)
    assert removal.disposition == "FORMAL_REMOVAL"
    assert removed.status == "rejected"
    assert target.requirement_id not in {item.requirement_id for item in current.confirmed_items}
    assert target.requirement_id in diff.removed_requirement_ids
    assert route.decision == "full_solution_recompile"
    assert removal.audit_record.target_requirement_id == target.requirement_id
    assert repository.list_records(state.project_id) == [removal.audit_record]


def test_r3_removal_without_new_feedback_evidence_is_blocked(tmp_path) -> None:
    state, baseline = state_and_baseline()
    state, baseline, target = _baseline_with_removable_scope(state, baseline)
    state = _active_state_with_feedback(state)

    with pytest.raises(ValueError, match="feedback source"):
        FormalRemovalService(FileRemovalAuditRepository(tmp_path)).apply(
            baseline, state, [], _decision(target.requirement_id)
        )


def test_r4_internal_only_removal_is_blocked(tmp_path) -> None:
    state, baseline = state_and_baseline()
    state, baseline, target = _baseline_with_removable_scope(state, baseline)
    state = _active_state_with_feedback(state)

    with pytest.raises(ValueError, match="customer confirmation"):
        FormalRemovalService(FileRemovalAuditRepository(tmp_path)).apply(
            baseline,
            state,
            [_feedback(state.project_id)],
            _decision(target.requirement_id, level="internal"),
        )


def test_r5_unmentioned_requirement_is_not_removed_without_explicit_action(tmp_path) -> None:
    state, baseline = state_and_baseline()
    state, baseline, target = _baseline_with_removable_scope(state, baseline)
    state = _active_state_with_feedback(state)
    service = FormalRemovalService(FileRemovalAuditRepository(tmp_path))

    assert service.list_formal_removals(baseline, state, [_feedback(state.project_id, content="仅补充新的数据材料")]) == []
    assert next(item for item in state.items if item.requirement_id == target.requirement_id).status == "confirmed"
