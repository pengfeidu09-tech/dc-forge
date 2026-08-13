"""Deterministic R-CHANGE1 Golden A-F and continuous-round E2E coverage."""

from __future__ import annotations

from backend.app.contracts.requirement_intelligence import RequirementConfirmation
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier
from backend.app.process.requirement_diff import RequirementDiffEngine
from backend.app.process.requirement_diff_router import RequirementDiffRouter
from backend.app.requirement_change.change_set import MultiChangeConfirmationOrchestrator
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _finalize(state, previous, version: int):
    resolved_skill = skill()
    conflicts = ConflictDetector().detect(state, resolved_skill)
    gaps = GapDetector().detect(state, resolved_skill, conflicts)
    state = state.model_copy(update={"conflicts": conflicts, "gaps": gaps})
    readiness = ReadinessEvaluator().evaluate(
        state, resolved_skill, gaps, conflicts, customer_confirmation_complete=True
    )
    baseline = RequirementBaselineBuilder(resolved_skill).build(
        state, readiness, baseline_version=version,
        confirmed_by="customer-owner", confirmation_summary=f"round {version}",
    )
    diff = RequirementDiffEngine().compare(previous, baseline)
    return state, baseline, diff, RequirementDiffRouter().route(diff, previous, baseline, resolved_skill)


def _confirm_added(state, added_ids: list[str]):
    return RequirementConfirmationApplier().apply(
        state,
        RequirementConfirmation(
            project_id=state.project_id, state_version=state.state_version,
            confirmation_level="customer", confirmed_requirement_ids=added_ids,
            confirmed_by="customer-owner",
        ),
    )[0]


def test_golden_b_c_d_e_routes_are_one_diff_per_feedback_cycle() -> None:
    state, previous = state_and_baseline()
    compatible = [
        item("round2-security", "security", "audit encryption", "encrypt audit records", status="pending", confirmation_level="none"),
        item("round2-time", "time", "rollout", "complete in one quarter", status="pending", confirmation_level="none"),
        item("round2-budget", "budget", "pilot", "within pilot budget", status="pending", confirmation_level="none"),
    ]
    state = state.model_copy(update={"state_version": 2, "items": [*state.items, *compatible]})
    state, baseline2, diff_b, route_b = _finalize(_confirm_added(state, [item.requirement_id for item in compatible]), previous, 2)
    assert len(diff_b.changes) == 3 and route_b.decision == "incremental_constraint_recompile"  # B

    integration = item("round3-integration", "integration", "SRM", "connect SRM", status="pending", confirmation_level="none")
    state = state.model_copy(update={"state_version": 4, "items": [*state.items, integration]})
    state, baseline3, _, route_c = _finalize(_confirm_added(state, [integration.requirement_id]), baseline2, 3)
    assert route_c.decision == "full_solution_recompile"  # C

    mixed = [
        item("round4-risk", "risk", "supplier risk", "monitor supplier risk", status="pending", confirmation_level="none"),
        item("round4-scope", "scope", "delivery", "include legal review", status="pending", confirmation_level="none"),
    ]
    state = state.model_copy(update={"state_version": 6, "items": [*state.items, *mixed]})
    state, baseline4, _, route_d = _finalize(_confirm_added(state, [item.requirement_id for item in mixed]), baseline3, 4)
    assert route_d.decision == "full_solution_recompile"  # D

    copy = baseline4.model_copy(update={"baseline_id": "golden-no-op-v5", "baseline_version": 5})
    diff_e = RequirementDiffEngine().compare(baseline4, copy)
    route_e = RequirementDiffRouter().route(diff_e, baseline4, copy, skill())
    assert diff_e.changes == [] and route_e.decision == "no_op"  # E


def test_continuous_rounds_v1_v2_v3_keep_each_previous_baseline_separate() -> None:
    state, baseline1 = state_and_baseline()
    round2 = item("round2-security", "security", "audit encryption", "encrypt audit records", status="pending", confirmation_level="none")
    state = state.model_copy(update={"state_version": 2, "items": [*state.items, round2]})
    state, baseline2, _, _ = _finalize(_confirm_added(state, [round2.requirement_id]), baseline1, 2)
    round3 = item("round3-time", "time", "rollout", "complete in one quarter", status="pending", confirmation_level="none")
    state = state.model_copy(update={"state_version": 4, "items": [*state.items, round3]})
    _, baseline3, diff3, route3 = _finalize(_confirm_added(state, [round3.requirement_id]), baseline2, 3)

    assert (baseline1.baseline_version, baseline2.baseline_version, baseline3.baseline_version) == (1, 2, 3)
    assert baseline1.baseline_id != baseline2.baseline_id != baseline3.baseline_id
    assert diff3.previous_baseline_id == baseline2.baseline_id
    assert route3.decision == "incremental_constraint_recompile"
