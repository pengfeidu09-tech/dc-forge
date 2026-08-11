from __future__ import annotations

import pytest

from backend.app.contracts.requirement_intelligence import RequirementState
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService
from tests.process.rm5_helpers import SKILL_ROOT, item, state_and_baseline


def _service(repository):
    return RequirementIntelligenceService(repository, RequirementSkillLoader(SKILL_ROOT))


def test_automotive_500k_to_800k_traceability_golden(tmp_path) -> None:
    state1, baseline1 = state_and_baseline(approval=500000)
    state2, baseline2 = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state1); repository.save_state(state2)
    service = _service(repository)
    initial = service.compile_solution_from_baseline(baseline1)
    approval_requirement = next(x for x in baseline1.confirmed_items if x.category == "approval")
    approval_constraint = next(x for x in initial.process.constraints if x.type == "approval")
    assert approval_requirement.requirement_id == "req-approval-500000"
    assert approval_constraint.parameters["threshold"] == 500000
    assert any(x.id == approval_constraint.id for x in initial.selected_solution.applied_constraints)
    assert any(node.id == "hard-approval-gate" for node in initial.blueprint.nodes)

    changed = service.apply_baseline_change(
        baseline1, baseline2, initial.process, initial.selected_solution, initial.blueprint
    )
    new_approval = next(x for x in changed.solution.applied_constraints if x.type == "approval")
    assert changed.decision == "incremental_constraint_recompile"
    assert new_approval.id == approval_constraint.id
    assert new_approval.parameters["threshold"] == 800000
    assert "500000" not in changed.solution.model_dump_json()
    assert changed.recompile_result.diff.changed_demo_node_ids == ["hard-approval-gate"]


def test_current_process_change_routes_full_and_uses_current_process(tmp_path) -> None:
    state1, baseline1 = state_and_baseline()
    old = next(x for x in state1.items if x.requirement_id == "req-process-2")
    changed = old.model_copy(
        update={
            "requirement_id": "req-process-2-v2",
            "process_detail": old.process_detail.model_copy(update={"description": "AI辅助审查招标文件并定位风险"}),
        }
    )
    state2 = RequirementState.model_validate({
        **state1.model_dump(mode="json"),
        "state_version": 2,
        "items": [
            changed.model_dump(mode="json") if x.requirement_id == old.requirement_id else x.model_dump(mode="json")
            for x in state1.items
        ],
        "process_observations": [],
    })
    baseline2 = baseline1.model_copy(
        update={
            "baseline_id": "baseline-process-v2", "baseline_version": 2, "source_state_version": 2,
            "confirmed_items": [changed if x.requirement_id == old.requirement_id else x for x in baseline1.confirmed_items],
        }
    )
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state1); repository.save_state(state2)
    service = _service(repository)
    initial = service.compile_solution_from_baseline(baseline1)
    result = service.apply_baseline_change(
        baseline1, baseline2, initial.process, initial.selected_solution, initial.blueprint
    )
    assert result.decision == "full_solution_recompile"
    assert next(x for x in result.process.as_is_nodes if x.id == "review").description.startswith("AI辅助")


def test_applicable_to_not_applicable_uses_full_compile_and_removes_gate(tmp_path) -> None:
    state1, baseline1 = state_and_baseline()
    approval = next(x for x in state1.items if x.category == "approval")
    not_applicable = approval.model_copy(
        update={"requirement_id": "req-approval-na", "parameters": {"not_applicable": True}}
    )
    state2 = state1.model_copy(
        update={
            "state_version": 2,
            "items": [not_applicable if x.requirement_id == approval.requirement_id else x for x in state1.items],
        }
    )
    baseline2 = baseline1.model_copy(
        update={
            "baseline_id": "baseline-na", "baseline_version": 2, "source_state_version": 2,
            "confirmed_items": [not_applicable if x.requirement_id == approval.requirement_id else x for x in baseline1.confirmed_items],
        }
    )
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state1); repository.save_state(state2)
    service = _service(repository)
    initial = service.compile_solution_from_baseline(baseline1)
    result = service.apply_baseline_change(
        baseline1, baseline2, initial.process, initial.selected_solution, initial.blueprint
    )
    assert result.decision == "full_solution_recompile"
    assert not any(x.type == "approval" for x in result.process.constraints)
    assert not any(node.id == "hard-approval-gate" for node in result.blueprint.nodes)


def test_unmapped_scope_change_fails_instead_of_fake_full_compile(tmp_path) -> None:
    scope1 = item("req-scope-1", "scope", "phase", "phase one")
    scope2 = item("req-scope-2", "scope", "phase", "phase two")
    state1, baseline1 = state_and_baseline(extra_items=[scope1])
    state2, baseline2 = state_and_baseline(
        state_version=2, baseline_version=2, extra_items=[scope2]
    )
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state1); repository.save_state(state2)
    service = _service(repository)
    initial = service.compile_solution_from_baseline(baseline1)
    assert "phase one" not in initial.process.model_dump_json()
    assert "phase one" not in initial.selected_solution.model_dump_json()
    with pytest.raises(ValueError, match="scope.*not representable|not representable.*scope"):
        service.apply_baseline_change(
            baseline1, baseline2, initial.process, initial.selected_solution, initial.blueprint
        )
