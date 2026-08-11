from __future__ import annotations

from unittest.mock import Mock

import pytest

from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService
from backend.app.solution.asset_retriever import AssetRetriever
from tests.process.rm5_helpers import SKILL_ROOT, state_and_baseline


def _service(repository, **overrides):
    return RequirementIntelligenceService(
        repository=repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        **overrides,
    )


def _save(repository, *states):
    for state in states:
        repository.save_state(state)


def test_initial_handoff_runs_existing_compile_and_blueprint(tmp_path) -> None:
    state, baseline = state_and_baseline()
    repository = FileRequirementRepository(tmp_path)
    _save(repository, state)
    handoff = _service(repository).compile_solution_from_baseline(baseline)
    assert handoff.process.project_id == baseline.project_id
    assert handoff.bundle.recommended_solution_id == handoff.selected_solution.solution_id
    assert handoff.blueprint.solution_id == handoff.selected_solution.solution_id


def test_noop_change_performs_zero_b_calls_and_retains_prior_artifacts(tmp_path) -> None:
    state, baseline = state_and_baseline()
    state2, lineage_only = state_and_baseline(state_version=2, baseline_version=2)
    repository = FileRequirementRepository(tmp_path)
    _save(repository, state, state2)
    actual = _service(repository).compile_solution_from_baseline(baseline)
    compile_spy, blueprint_spy, recompile_spy = Mock(), Mock(), Mock()
    service = _service(
        repository,
        compile_solution_fn=compile_spy,
        compile_blueprint_fn=blueprint_spy,
        recompile_solution_fn=recompile_spy,
    )
    result = service.apply_baseline_change(
        baseline, lineage_only, actual.process, actual.selected_solution, actual.blueprint
    )
    assert result.decision == "no_op"
    assert result.solution is actual.selected_solution
    compile_spy.assert_not_called(); blueprint_spy.assert_not_called(); recompile_spy.assert_not_called()


def test_approval_change_uses_previous_process_and_existing_b_recompiler(tmp_path, monkeypatch) -> None:
    state1, baseline1 = state_and_baseline(approval=500000)
    state2, baseline2 = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    repository = FileRequirementRepository(tmp_path)
    _save(repository, state1, state2)
    service = _service(repository)
    initial = service.compile_solution_from_baseline(baseline1)
    monkeypatch.setattr(AssetRetriever, "retrieve", Mock(side_effect=AssertionError("incremental must not retrieve")))
    result = service.apply_baseline_change(
        baseline1, baseline2, initial.process, initial.selected_solution, initial.blueprint
    )
    approvals = [c for c in result.solution.applied_constraints if c.type == "approval"]
    assert result.decision == "incremental_constraint_recompile"
    assert len(approvals) == 1 and approvals[0].parameters["threshold"] == 800000
    assert "500000" not in result.solution.model_dump_json()
    assert result.recompile_result.diff.changed_demo_node_ids == ["hard-approval-gate"]


def test_structural_change_runs_full_compile_not_recompile(tmp_path) -> None:
    state1, baseline1 = state_and_baseline()
    state2, baseline2 = state_and_baseline(
        state_version=2, baseline_version=2,
        goal="automate procurement document review and risk location",
    )
    repository = FileRequirementRepository(tmp_path)
    _save(repository, state1, state2)
    actual = _service(repository).compile_solution_from_baseline(baseline1)
    recompile_spy = Mock(side_effect=AssertionError("structural must not recompile"))
    service = _service(repository, recompile_solution_fn=recompile_spy)
    result = service.apply_baseline_change(
        baseline1, baseline2, actual.process, actual.selected_solution, actual.blueprint
    )
    assert result.decision == "full_solution_recompile"
    assert result.process.business_goal == "automate procurement document review and risk location"
    recompile_spy.assert_not_called()


def test_stale_selected_solution_and_process_are_rejected(tmp_path) -> None:
    state, baseline = state_and_baseline()
    repository = FileRequirementRepository(tmp_path)
    _save(repository, state)
    initial = _service(repository).compile_solution_from_baseline(baseline)
    stale = initial.selected_solution.model_copy(update={"source_project_id": "other"})
    with pytest.raises(ValueError, match="selected_solution"):
        _service(repository).apply_baseline_change(
            baseline, baseline, initial.process, stale, initial.blueprint
        )
    wrong_process = initial.process.model_copy(update={"business_goal": "stale"})
    with pytest.raises(ValueError, match="previous_process"):
        _service(repository).apply_baseline_change(
            baseline, baseline, wrong_process, initial.selected_solution, initial.blueprint
        )

    stale_constraint = initial.selected_solution.applied_constraints[0].model_copy(
        update={"statement": "stale selected solution constraint"}
    )
    stale_solution = initial.selected_solution.model_copy(
        update={"applied_constraints": [stale_constraint, *initial.selected_solution.applied_constraints[1:]]}
    )
    with pytest.raises(ValueError, match="applied_constraints"):
        _service(repository).apply_baseline_change(
            baseline, baseline, initial.process, stale_solution, initial.blueprint
        )


def test_all_service_dependencies_are_explicitly_injectable(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    loader = RequirementSkillLoader(SKILL_ROOT)
    adapter, diff_engine, router = Mock(), Mock(), Mock()
    compile_spy, blueprint_spy, recompile_spy = Mock(), Mock(), Mock()
    service = RequirementIntelligenceService(
        repository, loader, adapter, diff_engine, router,
        compile_solution_fn=compile_spy,
        compile_blueprint_fn=blueprint_spy,
        recompile_solution_fn=recompile_spy,
    )
    assert service._repository is repository
    assert service._skill_loader is loader
    assert service._adapter is adapter
    assert service._diff_engine is diff_engine
    assert service._router is router
    assert service._compile_solution is compile_spy
    assert service._compile_blueprint is blueprint_spy
    assert service._recompile_solution is recompile_spy
