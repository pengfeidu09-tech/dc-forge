from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contracts.requirement_intelligence import (
    RequirementChange,
    RequirementDiff,
    RequirementDiffRoute,
)
from backend.app.process.requirement_diff import RequirementDiffEngine
from tests.process.rm5_helpers import item, state_and_baseline


def test_semantically_equal_baselines_are_noop_despite_ids_lineage_and_order() -> None:
    _, first = state_and_baseline()
    changed_ids = [x.model_copy(update={"requirement_id": f"new-{x.requirement_id}"}) for x in first.confirmed_items]
    second = first.model_copy(
        update={
            "baseline_id": "baseline-lineage-only",
            "baseline_version": 2,
            "source_state_version": 2,
            "confirmed_items": list(reversed(changed_ids)),
        }
    )
    diff = RequirementDiffEngine().compare(first, second)
    assert diff.added_requirement_ids == []
    assert diff.removed_requirement_ids == []
    assert diff.changed_requirement_ids == []
    assert diff.changes == []


def test_approval_500k_to_800k_is_one_typed_change_not_add_remove() -> None:
    _, first = state_and_baseline(approval=500000)
    _, second = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    diff = RequirementDiffEngine().compare(first, second)

    assert diff.added_requirement_ids == []
    assert diff.removed_requirement_ids == []
    assert diff.changed_requirement_ids == ["req-approval-800000"]
    assert len(diff.changes) == 1
    assert diff.changes[0].change_type == "updated"
    assert "500000" in diff.changes[0].before_value
    assert "800000" in diff.changes[0].after_value


def test_added_removed_and_typed_process_changes_are_deterministic() -> None:
    _, first = state_and_baseline()
    added = item("req-budget", "budget", "phase one budget", "1000000")
    current_process = next(x for x in first.confirmed_items if x.requirement_id == "req-process-2")
    changed_process = current_process.model_copy(
        update={
            "requirement_id": "req-process-2-new",
            "process_detail": current_process.process_detail.model_copy(update={"description": "AI-assisted review"}),
        }
    )
    second_items = [
        changed_process if x.requirement_id == current_process.requirement_id else x
        for x in first.confirmed_items
        if x.requirement_id != "req-role"
    ] + [added]
    second = first.model_copy(
        update={
            "baseline_id": "baseline-changed", "baseline_version": 2,
            "source_state_version": 2, "confirmed_items": second_items,
        }
    )
    engine = RequirementDiffEngine()
    first_diff = engine.compare(first, second)
    reordered = second.model_copy(update={"confirmed_items": list(reversed(second.confirmed_items))})
    second_diff = engine.compare(first, reordered)

    assert first_diff.model_dump() == second_diff.model_dump()
    assert first_diff.added_requirement_ids == ["req-budget"]
    assert first_diff.removed_requirement_ids == ["req-role"]
    assert first_diff.changed_requirement_ids == ["req-process-2-new"]
    assert {change.change_type for change in first_diff.changes} == {"added", "updated"}
    removed_change = next(change for change in first_diff.changes if change.requirement_id == "req-role")
    assert removed_change.change_type == "updated"
    assert removed_change.after_value is None


def test_rm5_contracts_are_strict() -> None:
    with pytest.raises(ValidationError):
        RequirementDiff(
            project_id="project", previous_baseline_id="old", current_baseline_id="new",
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        RequirementDiffRoute(
            decision="no_op", explanation="no change",
            new_constraints=[{
                "id": "constraint", "type": "budget", "statement": "budget", "hard": False
            }],
        )

    with pytest.raises(ValidationError):
        RequirementChange(
            requirement_id="req-removed",
            change_type="removed",
            before_value="old",
            explanation="not part of the frozen enum",
        )


def test_requirement_diff_contract_rejects_same_baseline_and_overlapping_sets() -> None:
    with pytest.raises(ValidationError, match="baseline"):
        RequirementDiff(
            project_id="project", previous_baseline_id="same", current_baseline_id="same"
        )
    for overlap in (
        {"added_requirement_ids": ["req"], "changed_requirement_ids": ["req"]},
        {"removed_requirement_ids": ["req"], "changed_requirement_ids": ["req"]},
        {"added_requirement_ids": ["req"], "removed_requirement_ids": ["req"]},
    ):
        with pytest.raises(ValidationError, match="overlap"):
            RequirementDiff(
                project_id="project", previous_baseline_id="old", current_baseline_id="new",
                **overlap,
            )
    with pytest.raises(ValidationError, match="close over"):
        RequirementDiff(
            project_id="project", previous_baseline_id="old", current_baseline_id="new",
            added_requirement_ids=["req-added"], changes=[],
        )


def test_diff_rejects_reverse_same_version_and_cross_project_baselines() -> None:
    _, first = state_and_baseline()
    _, second = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    engine = RequirementDiffEngine()
    with pytest.raises(ValueError, match="strictly earlier"):
        engine.compare(second, first)
    with pytest.raises(ValueError, match="strictly earlier"):
        engine.compare(first, first.model_copy(update={"baseline_id": "other-same-version"}))
    with pytest.raises(ValueError, match="project_id"):
        engine.compare(first, second.model_copy(update={"project_id": "other-project"}))


def test_multi_value_identity_preserves_oa_srm_and_expresses_srm_to_erp_as_remove_add() -> None:
    _, first = state_and_baseline()
    existing = [x for x in first.confirmed_items if x.category != "existing_system"]
    oa = item("req-oa", "existing_system", "existing system", "OA")
    srm = item("req-srm", "existing_system", "existing system", "SRM")
    first = first.model_copy(update={"confirmed_items": [*existing, oa, srm]})
    lineage = first.model_copy(
        update={
            "baseline_id": "baseline-multi-lineage", "baseline_version": 2,
            "source_state_version": 2,
            "confirmed_items": [
                value.model_copy(update={"requirement_id": f"new-{value.requirement_id}"})
                for value in reversed(first.confirmed_items)
            ],
        }
    )
    assert RequirementDiffEngine().compare(first, lineage).changes == []

    erp = item("req-erp", "existing_system", "existing system", "ERP")
    changed = first.model_copy(
        update={
            "baseline_id": "baseline-multi-changed", "baseline_version": 2,
            "source_state_version": 2, "confirmed_items": [*existing, oa, erp],
        }
    )
    diff = RequirementDiffEngine().compare(first, changed)
    assert diff.added_requirement_ids == ["req-erp"]
    assert diff.removed_requirement_ids == ["req-srm"]
    assert diff.changed_requirement_ids == []
    assert [(change.requirement_id, change.change_type) for change in diff.changes] == [
        ("req-erp", "added"), ("req-srm", "updated")
    ]
    assert diff.changes[1].after_value is None


def test_parameter_key_order_does_not_change_diff() -> None:
    _, first = state_and_baseline()
    approval = next(x for x in first.confirmed_items if x.category == "approval")
    before = approval.model_copy(update={"parameters": {"currency": "CNY", "threshold": 500000}})
    after = approval.model_copy(
        update={"requirement_id": "req-approval-lineage", "parameters": {"threshold": 500000, "currency": "CNY"}}
    )
    previous = first.model_copy(update={"confirmed_items": [before if x.category == "approval" else x for x in first.confirmed_items]})
    current = first.model_copy(
        update={
            "baseline_id": "baseline-param-order", "baseline_version": 2,
            "source_state_version": 2,
            "confirmed_items": [after if x.category == "approval" else x for x in first.confirmed_items],
        }
    )
    assert RequirementDiffEngine().compare(previous, current).changes == []


def test_noop_ignores_source_provenance_and_confidence_lineage_metadata() -> None:
    from backend.app.contracts.requirement_intelligence import RequirementSourceRef

    _, previous = state_and_baseline()
    current_items = [
        value.model_copy(
            update={
                "requirement_id": f"lineage-{value.requirement_id}",
                "provenance": "human_modified",
                "confidence": 0.7,
                "source_refs": [RequirementSourceRef(source_id="new-source", excerpt="same truth")],
            }
        )
        for value in previous.confirmed_items
    ]
    current = previous.model_copy(
        update={
            "baseline_id": "baseline-metadata-lineage", "baseline_version": 2,
            "source_state_version": 2, "confirmed_items": current_items,
        }
    )
    assert RequirementDiffEngine().compare(previous, current).changes == []
