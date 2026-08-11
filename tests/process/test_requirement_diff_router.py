from __future__ import annotations

import pytest

from backend.app.process.process_spec_adapter import ProcessSpecAdapter
from backend.app.process.requirement_diff import RequirementDiffEngine
from backend.app.process.requirement_diff_router import RequirementDiffRouter
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _process(state, baseline):
    resolved = skill()
    conflicts = ConflictDetector().detect(state, resolved)
    gaps = GapDetector().detect(state, resolved, conflicts)
    readiness = ReadinessEvaluator().evaluate(state, resolved, gaps, conflicts, customer_confirmation_complete=True)
    return ProcessSpecAdapter().adapt(baseline, state, resolved, readiness, [])


def _route(previous, current, previous_process=None, current_process=None):
    diff = RequirementDiffEngine().compare(previous, current)
    return RequirementDiffRouter().route(
        diff, previous, current, skill(), previous_process=previous_process, current_process=current_process
    )


def test_router_noop_and_constraint_update_are_deterministic() -> None:
    _, previous = state_and_baseline(approval=500000)
    _, current = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    no_op = _route(previous, previous.model_copy(
        update={"baseline_id": "lineage-only", "baseline_version": 2, "source_state_version": 2}
    ))
    route = _route(previous, current)
    assert no_op.decision == "no_op" and no_op.new_constraints == []
    assert route.decision == "incremental_constraint_recompile"
    assert route.changed_categories == ["approval"]
    assert len(route.new_constraints) == 1
    assert route.new_constraints[0].parameters["threshold"] == 800000

    added = item("req-budget", "budget", "phase one budget", "1000000")
    added_baseline = previous.model_copy(
        update={
            "baseline_id": "baseline-budget", "baseline_version": 2,
            "source_state_version": 2, "confirmed_items": [*previous.confirmed_items, added],
        }
    )
    add_route = _route(previous, added_baseline)
    assert add_route.decision == "incremental_constraint_recompile"
    assert [constraint.type for constraint in add_route.new_constraints] == ["budget"]


def test_constraint_removal_and_not_applicable_route_full() -> None:
    _, previous = state_and_baseline()
    without_approval = previous.model_copy(
        update={
            "baseline_id": "without-approval", "baseline_version": 2, "source_state_version": 2,
            "confirmed_items": [x for x in previous.confirmed_items if x.category != "approval"],
        }
    )
    removed = _route(previous, without_approval)
    assert removed.decision == "full_solution_recompile"
    assert "removal" in removed.explanation

    approval = next(x for x in previous.confirmed_items if x.category == "approval")
    na = approval.model_copy(update={"requirement_id": "req-approval-na", "parameters": {"not_applicable": True}})
    current = previous.model_copy(
        update={
            "baseline_id": "approval-na", "baseline_version": 2, "source_state_version": 2,
            "confirmed_items": [na if x.category == "approval" else x for x in previous.confirmed_items],
        }
    )
    assert _route(previous, current).decision == "full_solution_recompile"


def test_structural_mixed_and_unmapped_changes_route_full_with_guard() -> None:
    state1, previous = state_and_baseline()
    state2, structural = state_and_baseline(
        state_version=2, baseline_version=2, goal="automate procurement review and risk location"
    )
    assert _route(previous, structural).decision == "full_solution_recompile"

    _, changed_constraint = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    goal = next(x for x in structural.confirmed_items if x.category == "business_goal")
    mixed = changed_constraint.model_copy(
        update={
            "baseline_id": "mixed",
            "confirmed_items": [goal if x.category == "business_goal" else x for x in changed_constraint.confirmed_items],
        }
    )
    assert _route(previous, mixed).decision == "full_solution_recompile"

    scope1 = item("req-scope-1", "scope", "phase", "phase one")
    scope2 = scope1.model_copy(update={"requirement_id": "req-scope-2", "value": "phase two"})
    old = previous.model_copy(update={"baseline_id": "scope-1", "confirmed_items": [*previous.confirmed_items, scope1]})
    new = previous.model_copy(
        update={"baseline_id": "scope-2", "baseline_version": 2, "source_state_version": 2,
                "confirmed_items": [*previous.confirmed_items, scope2]}
    )
    process = _process(state1, previous)
    with pytest.raises(ValueError, match="scope.*not representable|not representable.*scope"):
        _route(old, new, process, process)


def test_route_contract_requires_sorted_categories_and_nonempty_incremental_constraints() -> None:
    from backend.app.contracts.requirement_intelligence import RequirementDiffRoute
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="sorted"):
        RequirementDiffRoute(
            decision="full_solution_recompile",
            changed_categories=["role", "business_goal"],
            explanation="structural",
        )
    with pytest.raises(ValidationError, match="new_constraints"):
        RequirementDiffRoute(
            decision="incremental_constraint_recompile",
            changed_categories=["approval"],
            explanation="incremental",
        )


@pytest.mark.parametrize(
    ("category", "old_value", "new_value"),
    [
        ("role", "采购专员", "法务"),
        ("available_data", "历史招标文件", "历史合同"),
        ("existing_system", "OA", "ERP"),
        ("target_metric", "processing_time", "manual_steps"),
        ("pain_point", "manual review is slow", "manual review misses risks"),
    ],
)
def test_multi_value_and_typed_structural_changes_route_full(category, old_value, new_value) -> None:
    _, previous = state_and_baseline()
    target = next(x for x in previous.confirmed_items if x.category == category)
    updates = {"requirement_id": f"new-{target.requirement_id}", "value": new_value}
    if category == "pain_point":
        updates["pain_point_detail"] = target.pain_point_detail.model_copy(
            update={"description": new_value}
        )
    changed = target.model_copy(update=updates)
    current = previous.model_copy(
        update={
            "baseline_id": f"baseline-{category}-changed", "baseline_version": 2,
            "source_state_version": 2,
            "confirmed_items": [changed if x.requirement_id == target.requirement_id else x for x in previous.confirmed_items],
        }
    )
    assert _route(previous, current).decision == "full_solution_recompile"


def test_multi_value_oa_srm_to_oa_erp_routes_full_without_collision() -> None:
    _, previous = state_and_baseline()
    others = [x for x in previous.confirmed_items if x.category != "existing_system"]
    oa = item("req-oa", "existing_system", "existing system", "OA")
    srm = item("req-srm", "existing_system", "existing system", "SRM")
    erp = item("req-erp", "existing_system", "existing system", "ERP")
    previous = previous.model_copy(update={"confirmed_items": [*others, oa, srm]})
    current = previous.model_copy(
        update={
            "baseline_id": "baseline-oa-erp", "baseline_version": 2,
            "source_state_version": 2, "confirmed_items": [*others, oa, erp],
        }
    )
    route = _route(previous, current)
    assert route.decision == "full_solution_recompile"
    assert route.changed_categories == ["existing_system"]


def test_route_is_identical_when_parameter_key_order_changes() -> None:
    _, previous = state_and_baseline()
    approval = next(x for x in previous.confirmed_items if x.category == "approval")
    old = approval.model_copy(update={"parameters": {"currency": "CNY", "threshold": 500000}})
    new = approval.model_copy(
        update={"requirement_id": "req-approval-new-lineage", "parameters": {"threshold": 500000, "currency": "CNY"}}
    )
    previous = previous.model_copy(
        update={"confirmed_items": [old if x.category == "approval" else x for x in previous.confirmed_items]}
    )
    current = previous.model_copy(
        update={
            "baseline_id": "baseline-route-param-order", "baseline_version": 2,
            "source_state_version": 2,
            "confirmed_items": [new if x.category == "approval" else x for x in previous.confirmed_items],
        }
    )
    first = _route(previous, current)
    second = _route(previous, current.model_copy(update={"confirmed_items": list(reversed(current.confirmed_items))}))
    assert first.model_dump() == second.model_dump()
    assert first.decision == "no_op"
