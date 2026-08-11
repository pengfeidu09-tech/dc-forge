from __future__ import annotations

import pytest

from backend.app.contracts.requirement_intelligence import NextQuestion, ReadinessAssessment
from backend.app.process.process_spec_adapter import ProcessSpecAdapter, stable_constraint_id
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _adapt(state, baseline, questions=None, readiness_override=None):
    from backend.app.process.conflict_detector import ConflictDetector
    from backend.app.process.gap_detector import GapDetector
    from backend.app.process.readiness import ReadinessEvaluator

    resolved = skill()
    conflicts = ConflictDetector().detect(state, resolved)
    gaps = GapDetector().detect(state, resolved, conflicts)
    readiness = ReadinessEvaluator().evaluate(
        state, resolved, gaps, conflicts, customer_confirmation_complete=True
    )
    return ProcessSpecAdapter().adapt(
        baseline, state, resolved, readiness_override or readiness, questions or []
    )


def test_adapter_maps_confirmed_truth_graph_lists_gaps_questions_and_readiness() -> None:
    state, baseline = state_and_baseline()
    question = NextQuestion(
        question_id="question-1", text="Confirm optional integration details.",
        target_category="integration", priority="medium", blocking=False,
        reason="non-blocking gap", related_gap_ids=[baseline.non_blocking_gaps[0].gap_id],
    )
    process = _adapt(state, baseline, [question])

    assert process.project_id == baseline.project_id
    assert process.industry == "制造"
    assert process.department == "采购中心"
    assert process.roles == ["采购专员"]
    assert process.available_data == ["企业采购制度", "历史招标文件", "审查规则"]
    assert process.existing_systems == ["OA"]
    assert [node.id for node in process.as_is_nodes] == ["intake", "review"]
    assert process.as_is_nodes[0].next_ids == ["review"]
    assert process.pain_points[0].affected_node_ids == ["review"]
    assert process.readiness_score == 75
    assert process.readiness_score != 100
    assert process.missing_information
    assert process.clarification_questions == [question.text]


def test_scalar_cardinality_is_strict_but_semantic_duplicates_are_deterministic() -> None:
    state, baseline = state_and_baseline()
    missing_items = [item for item in baseline.confirmed_items if item.category != "industry"]
    missing = baseline.model_copy(update={"confirmed_items": missing_items})
    missing_state = state.model_copy(update={"items": missing_items})
    forged = ReadinessAssessment(
        stage="CONFIRMED_READY", completeness_score=75, blocking_gap_ids=[],
        non_blocking_gap_ids=[], open_conflict_ids=[],
        can_generate_preliminary_solution=True, can_generate_formal_solution=True,
    )
    with pytest.raises(ValueError, match="industry.*exactly one"):
        _adapt(missing_state, missing, readiness_override=forged)

    duplicate = item("req-industry-duplicate", "industry", "industry copy", "  制造 ")
    duplicate_baseline = baseline.model_copy(
        update={"confirmed_items": [*baseline.confirmed_items, duplicate]}
    )
    duplicate_state = state.model_copy(update={"items": [*state.items, duplicate]})
    assert _adapt(duplicate_state, duplicate_baseline).industry == "制造"

    conflict = duplicate.model_copy(update={"requirement_id": "req-industry-conflict", "value": "energy"})
    conflict_baseline = baseline.model_copy(update={"confirmed_items": [*baseline.confirmed_items, conflict]})
    conflict_state = state.model_copy(update={"items": [*state.items, conflict]})
    with pytest.raises(ValueError, match="industry.*multiple"):
        _adapt(conflict_state, conflict_baseline, readiness_override=forged)


def test_process_and_pain_graph_reject_dangling_and_conflicting_duplicate_ids() -> None:
    state, baseline = state_and_baseline()
    process_item = next(item for item in baseline.confirmed_items if item.requirement_id == "req-process-1")
    dangling = process_item.model_copy(
        update={"process_detail": process_item.process_detail.model_copy(update={"next_node_ids": ["missing"]})}
    )
    bad_baseline = baseline.model_copy(
        update={"confirmed_items": [dangling if x.requirement_id == dangling.requirement_id else x for x in baseline.confirmed_items]}
    )
    bad_state = state.model_copy(
        update={"items": [dangling if x.requirement_id == dangling.requirement_id else x for x in state.items]}
    )
    with pytest.raises(ValueError, match="dangling"):
        _adapt(bad_state, bad_baseline)

    duplicate = process_item.model_copy(
        update={
            "requirement_id": "req-process-duplicate",
            "process_detail": process_item.process_detail.model_copy(update={"description": "conflict"}),
        }
    )
    with pytest.raises(ValueError, match="duplicate process_node_id"):
        _adapt(
            state.model_copy(update={"items": [*state.items, duplicate]}),
            baseline.model_copy(update={"confirmed_items": [*baseline.confirmed_items, duplicate]}),
        )

    pain = next(x for x in baseline.confirmed_items if x.category == "pain_point")
    bad_pain = pain.model_copy(
        update={"pain_point_detail": pain.pain_point_detail.model_copy(update={"affected_process_node_ids": ["missing"]})}
    )
    with pytest.raises(ValueError, match="affected.*missing"):
        _adapt(
            state.model_copy(update={"items": [bad_pain if x.requirement_id == pain.requirement_id else x for x in state.items]}),
            baseline.model_copy(update={"confirmed_items": [bad_pain if x.requirement_id == pain.requirement_id else x for x in baseline.confirmed_items]}),
        )

    duplicate_pain = pain.model_copy(
        update={
            "requirement_id": "req-pain-duplicate",
            "pain_point_detail": pain.pain_point_detail.model_copy(update={"description": "conflict"}),
        }
    )
    with pytest.raises(ValueError, match="duplicate pain_point_id"):
        _adapt(
            state.model_copy(update={"items": [*state.items, duplicate_pain]}),
            baseline.model_copy(update={"confirmed_items": [*baseline.confirmed_items, duplicate_pain]}),
        )


def test_constraint_ids_are_semantic_hard_and_not_applicable_is_skipped() -> None:
    state1, baseline1 = state_and_baseline(approval=500000)
    state2, baseline2 = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    first = _adapt(state1, baseline1)
    second = _adapt(state2, baseline2)
    first_approval = next(c for c in first.constraints if c.type == "approval")
    second_approval = next(c for c in second.constraints if c.type == "approval")

    assert first_approval.id == second_approval.id
    assert first_approval.parameters == {"threshold": 500000}
    assert second_approval.parameters == {"threshold": 800000}
    assert first_approval.hard is True
    assert "hard" not in first_approval.parameters and "not_applicable" not in first_approval.parameters

    approval_item = next(x for x in baseline1.confirmed_items if x.category == "approval")
    na = approval_item.model_copy(update={"parameters": {"not_applicable": True}})
    assert not any(
        c.type == "approval"
        for c in _adapt(
            state1.model_copy(update={"items": [na if x.requirement_id == na.requirement_id else x for x in state1.items]}),
            baseline1.model_copy(update={"confirmed_items": [na if x.requirement_id == na.requirement_id else x for x in baseline1.confirmed_items]}),
        ).constraints
    )

    invalid = approval_item.model_copy(update={"parameters": {"hard": "yes"}})
    with pytest.raises(ValueError, match="hard.*bool"):
        _adapt(
            state1.model_copy(update={"items": [invalid if x.requirement_id == invalid.requirement_id else x for x in state1.items]}),
            baseline1.model_copy(update={"confirmed_items": [invalid if x.requirement_id == invalid.requirement_id else x for x in baseline1.confirmed_items]}),
        )

    explicit_false = approval_item.model_copy(update={"parameters": {"hard": False}})
    false_process = _adapt(
        state1.model_copy(update={"items": [explicit_false if x.requirement_id == explicit_false.requirement_id else x for x in state1.items]}),
        baseline1.model_copy(update={"confirmed_items": [explicit_false if x.requirement_id == explicit_false.requirement_id else x for x in baseline1.confirmed_items]}),
    )
    assert next(c for c in false_process.constraints if c.type == "approval").hard is True

    different_subject = approval_item.model_copy(
        update={"requirement_id": "req-approval-other", "subject": "contract approval threshold"}
    )
    other_process = _adapt(
        state1.model_copy(update={"items": [x for x in state1.items if x.category != "approval"] + [different_subject]}),
        baseline1.model_copy(update={"confirmed_items": [x for x in baseline1.confirmed_items if x.category != "approval"] + [different_subject]}),
    )
    assert next(c for c in other_process.constraints if c.type == "approval").id != first_approval.id


def test_unmapped_categories_are_not_guessed_and_order_is_deterministic() -> None:
    extra = item("req-scope", "scope", "phase", "phase one only")
    state, baseline = state_and_baseline(extra_items=[extra])
    first = _adapt(state, baseline)
    reversed_state = state.model_copy(update={"items": list(reversed(state.items))})
    reversed_baseline = baseline.model_copy(update={"confirmed_items": list(reversed(baseline.confirmed_items))})
    second = _adapt(reversed_state, reversed_baseline)

    assert first.model_dump() == second.model_dump()
    assert "phase one only" not in first.model_dump_json()


def test_baseline_cannot_silently_omit_confirmed_source_truth() -> None:
    state, baseline = state_and_baseline()
    incomplete = baseline.model_copy(update={"confirmed_items": baseline.confirmed_items[:-1]})
    with pytest.raises(ValueError, match="exactly contain"):
        _adapt(state, incomplete)


def test_constraint_slot_collision_with_different_payload_fails() -> None:
    state, baseline = state_and_baseline()
    approval = next(x for x in baseline.confirmed_items if x.category == "approval")
    collision = approval.model_copy(
        update={
            "requirement_id": "req-approval-collision",
            "value": "超过900000必须人工审批",
            "parameters": {"threshold": 900000},
        }
    )
    collision_state = state.model_copy(update={"items": [*state.items, collision]})
    collision_baseline = baseline.model_copy(
        update={"confirmed_items": [*baseline.confirmed_items, collision]}
    )
    forged = ReadinessAssessment(
        stage="CONFIRMED_READY", completeness_score=75,
        blocking_gap_ids=[], non_blocking_gap_ids=[], open_conflict_ids=[],
        can_generate_preliminary_solution=True, can_generate_formal_solution=True,
    )
    with pytest.raises(ValueError, match="constraint.*collision"):
        _adapt(collision_state, collision_baseline, readiness_override=forged)


def test_multi_value_adapter_preserves_all_values_in_stable_order() -> None:
    extras = [
        item("req-system-srm", "existing_system", "existing system", "SRM"),
        item("req-system-erp", "existing_system", "existing system", "ERP"),
        item("req-role-legal", "role", "legal", "法务"),
        item("req-data-plan", "available_data", "plans", "历史采购方案"),
        item("req-metric-manual", "target_metric", "manual", "manual_steps"),
    ]
    state, baseline = state_and_baseline()
    state = state.model_copy(update={"items": [*state.items, *extras]})
    baseline = baseline.model_copy(update={"confirmed_items": [*baseline.confirmed_items, *extras]})
    forged = ReadinessAssessment(
        stage="CONFIRMED_READY", completeness_score=75,
        blocking_gap_ids=[], non_blocking_gap_ids=[], open_conflict_ids=[],
        can_generate_preliminary_solution=True, can_generate_formal_solution=True,
    )
    process = _adapt(state, baseline, readiness_override=forged)
    assert process.existing_systems == ["ERP", "OA", "SRM"]
    assert process.roles == ["法务", "采购专员"]
    assert process.available_data == ["企业采购制度", "历史招标文件", "历史采购方案", "审查规则"]
    assert process.target_metrics == ["manual_steps", "processing_time", "risk_findings"]


def test_constraint_id_changes_across_projects_and_parameters_are_canonical() -> None:
    assert stable_constraint_id("project-a", "approval", "threshold") != stable_constraint_id(
        "project-b", "approval", "threshold"
    )
    approval = item(
        "req-approval-canonical", "approval", "threshold", "approval rule",
        parameters={"z": {"b": 2, "a": 1}, "a": 0, "hard": True},
    )
    constraint = ProcessSpecAdapter().constraint_from_item("project-a", approval, skill())
    assert list(constraint.parameters) == ["a", "z"]
    assert list(constraint.parameters["z"]) == ["a", "b"]
    assert "hard" not in constraint.parameters
