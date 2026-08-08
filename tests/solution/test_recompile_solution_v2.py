from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.solution_intelligence import (
    RecompileSolutionV2Request,
    SolutionIntelligenceDiff,
)
from backend.app.main import app
from backend.app.solution.asset_retriever import AssetRetriever
from backend.app.solution.demo_blueprint import DemoBlueprintCompiler
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.gene_builder import GeneBuilder
from backend.app.solution.reuse_planner import ReusePlanner
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.solution_intelligence_compiler import SolutionIntelligenceCompiler
from backend.app.solution.solution_intelligence_recompiler import SolutionIntelligenceRecompiler
from backend.app.solution.solution_intelligence_recompiler import merge_constraints
from tests.solution.test_reuse_planner import frozen_procurement_golden_process


def _baseline():
    process = frozen_procurement_golden_process()
    bundle = SolutionIntelligenceCompiler().compile(process)
    solution = next(plan for plan in bundle.plans if plan.plan_type == "balanced")
    blueprint = DemoBlueprintCompiler().compile(process, solution)
    return process, solution, blueprint


def _approval(threshold: int, *, constraint_id: str = "approval-threshold") -> BusinessConstraint:
    return BusinessConstraint(
        id=constraint_id,
        type="approval",
        statement=f"超过{threshold}必须人工审批",
        hard=True,
        parameters={"threshold": threshold},
    )


def _recompile(constraints: list[BusinessConstraint]):
    process, solution, blueprint = _baseline()
    return process, solution, blueprint, SolutionIntelligenceRecompiler().recompile(
        process, solution, blueprint, constraints
    )


def test_v2_contracts_are_strict() -> None:
    with pytest.raises(ValidationError):
        SolutionIntelligenceDiff(extra="forbidden")
    process, solution, blueprint = _baseline()
    with pytest.raises(ValidationError):
        RecompileSolutionV2Request(
            process=process,
            selected_solution=solution,
            selected_blueprint=blueprint,
            new_constraints=[],
            extra="forbidden",
        )


def test_same_constraint_is_a_noop_without_retrieval_or_false_diff() -> None:
    process, solution, blueprint = _baseline()
    same = next(item for item in process.constraints if item.id == "approval-threshold")
    with patch.object(AssetRetriever, "retrieve", side_effect=AssertionError("must not retrieve")):
        result = SolutionIntelligenceRecompiler().recompile(process, solution, blueprint, [same])

    assert result.new_solution.model_dump() == solution.model_dump()
    assert result.new_blueprint.model_dump() == blueprint.model_dump()
    assert result.diff.model_dump(exclude={"explanations"}) == SolutionIntelligenceDiff().model_dump(exclude={"explanations"})
    assert "no effective change" in result.diff.explanations[0]


@pytest.mark.parametrize("threshold", [800000, 300000])
def test_approval_threshold_change_is_incremental_and_precise(threshold: int) -> None:
    process, old_solution, old_blueprint = _baseline()
    recompiler = SolutionIntelligenceRecompiler()
    merged, changed_ids, types = merge_constraints(list(process.constraints), [_approval(threshold)])
    scope = recompiler.detect_affected_scope(old_solution, old_blueprint, changed_ids, types)
    with patch.object(AssetRetriever, "retrieve", side_effect=AssertionError("approval must not retrieve")):
        result = recompiler.recompile(
            process, old_solution, old_blueprint, [_approval(threshold)]
        )

    new_solution = result.new_solution
    new_blueprint = result.new_blueprint
    assert scope.changed_constraint_ids == ["approval-threshold"]
    assert scope.affected_fit_dimensions == ["rules"]
    assert scope.affects_retrieval is False
    assert {item.asset_id for item in new_solution.fit_assessments} == {item.asset_id for item in old_solution.fit_assessments}
    assert next(item for item in new_solution.reuse_decisions if item.module_id == "procurement-document-workbench").model_dump() == next(item for item in old_solution.reuse_decisions if item.module_id == "procurement-document-workbench").model_dump()
    assert next(item for item in new_solution.reuse_decisions if item.module_id == "procurement-review-and-risk-location").decision == "configuration"
    assert next(item for item in new_solution.reuse_decisions if item.module_id == "procurement-review-and-risk-location").human_review_required is True
    assert new_solution.primary_asset_ids == old_solution.primary_asset_ids
    assert new_solution.evidence_refs == old_solution.evidence_refs
    assert new_solution.value_claims == old_solution.value_claims
    assert any(item.id == "approval-threshold" and item.parameters["threshold"] == threshold for item in new_solution.applied_constraints)
    assert "approval threshold compatibility requires confirmation" in next(item for item in new_solution.reuse_decisions if item.module_id == "procurement-review-and-risk-location").gaps
    assert all(str(threshold) not in change for item in new_solution.reuse_decisions for change in item.required_changes)
    assert result.diff.changed_module_ids == []
    assert result.diff.reuse_mode_changes == {}
    assert result.diff.value_claim_changes == []
    assert result.diff.added_demo_node_ids == []
    assert result.diff.removed_demo_node_ids == []
    assert result.diff.changed_demo_node_ids == ["hard-approval-gate"]
    assert "超过" in next(node for node in new_blueprint.nodes if node.id == "hard-approval-gate").gate_reason
    assert str(threshold) in new_blueprint.model_dump_json()
    assert "configure:审批金额" not in new_blueprint.model_dump_json()
    assert new_blueprint.demo_id == f"{new_solution.solution_id}-demo"
    old_nodes = {node.id: node.model_dump() for node in old_blueprint.nodes}
    new_nodes = {node.id: node.model_dump() for node in new_blueprint.nodes}
    assert {node_id: payload for node_id, payload in new_nodes.items() if node_id != "hard-approval-gate"} == {
        node_id: payload for node_id, payload in old_nodes.items() if node_id != "hard-approval-gate"
    }


def test_constraint_merge_overrides_by_id_and_stably_appends_new_ids() -> None:
    process, old_solution, old_blueprint = _baseline()
    added = _approval(900000, constraint_id="approval-extra")
    recompiler = SolutionIntelligenceRecompiler()
    _, changed_ids, types = merge_constraints(list(process.constraints), [_approval(800000), added])
    scope = recompiler.detect_affected_scope(old_solution, old_blueprint, changed_ids, types)
    result = recompiler.recompile(
        process, old_solution, old_blueprint, [_approval(800000), added]
    )

    assert [item.id for item in result.new_solution.applied_constraints] == [
        "security-private", "approval-threshold", "approval-extra"
    ]
    assert scope.changed_constraint_ids == ["approval-extra", "approval-threshold"]


def test_security_data_and_budget_scopes_do_not_invent_value_or_retrieval_changes() -> None:
    process, solution, blueprint = _baseline()
    security = BusinessConstraint(id="security-extra", type="security", statement="数据必须私有部署", hard=True)
    data = BusinessConstraint(id="data-extra", type="data", statement="历史招标文件可供确认", hard=True)
    budget = BusinessConstraint(id="budget-extra", type="budget", statement="预算待确认", hard=True)
    recompiler = SolutionIntelligenceRecompiler()
    _, changed_ids, types = merge_constraints(list(process.constraints), [security, data, budget])
    scope = recompiler.detect_affected_scope(solution, blueprint, changed_ids, types)
    result = recompiler.recompile(process, solution, blueprint, [security, data, budget])

    assert scope.affects_retrieval is False
    assert "security" in scope.affected_constraint_types
    assert "data" in scope.affected_constraint_types
    assert result.new_solution.value_claims == solution.value_claims
    assert all(claim.claim_type != "verified" for claim in result.new_solution.value_claims)
    assert result.new_solution.fit_assessments[0].eligible is True


def test_result_is_deterministic_and_preserves_v2_closure() -> None:
    process, solution, blueprint, first = _recompile([_approval(800000)])
    second = SolutionIntelligenceRecompiler().recompile(process, solution, blueprint, [_approval(800000)])

    assert first.model_dump() == second.model_dump()
    assert first.new_solution.source_project_id == process.project_id
    assert first.new_blueprint.project_id == process.project_id
    assert first.new_blueprint.solution_id == first.new_solution.solution_id
    assert first.new_solution.demo_blueprint_id is None


def test_v2_recompile_api_is_parallel_to_v1_and_rejects_invalid_payload() -> None:
    process, solution, blueprint = _baseline()
    client = TestClient(app)
    payload = {
        "process": process.model_dump(mode="json"),
        "selected_solution": solution.model_dump(mode="json"),
        "selected_blueprint": blueprint.model_dump(mode="json"),
        "new_constraints": [_approval(800000).model_dump(mode="json")],
    }
    response = client.post("/recompile-solution-v2", json=payload)

    assert response.status_code == 200
    assert response.json()["diff"]["changed_demo_node_ids"] == ["hard-approval-gate"]
    assert client.post("/recompile-solution-v2", json=payload | {"extra": "bad"}).status_code == 422
    mismatched = dict(payload)
    mismatched["selected_blueprint"] = dict(payload["selected_blueprint"])
    mismatched["selected_blueprint"]["solution_id"] = "other-solution"
    assert client.post("/recompile-solution-v2", json=mismatched).status_code == 422
    schema = client.get("/openapi.json").json()["paths"]
    assert "/recompile-solution" in schema
    assert "/compile-solution-v2" in schema
    assert "/recompile-solution-v2" in schema


def test_request_and_result_cross_object_closure_are_strict() -> None:
    process, solution, blueprint = _baseline()
    with pytest.raises(ValidationError, match="source_project_id"):
        RecompileSolutionV2Request(
            process=process.model_copy(update={"project_id": "other-project"}),
            selected_solution=solution,
            selected_blueprint=blueprint,
            new_constraints=[],
        )
    result = SolutionIntelligenceRecompiler().recompile(process, solution, blueprint, [_approval(800000)])
    payload = result.model_dump()
    payload["new_blueprint"]["solution_id"] = "other-solution"
    with pytest.raises(ValidationError, match="solution_id"):
        result.__class__.model_validate(payload)


def test_approval_path_does_not_call_full_engines() -> None:
    process, solution, blueprint = _baseline()
    with (
        patch.object(AssetRetriever, "retrieve", side_effect=AssertionError("retriever")),
        patch.object(SolutionIntelligenceCompiler, "compile", side_effect=AssertionError("compiler")),
        patch.object(FitEngine, "assess", side_effect=AssertionError("fit")),
        patch.object(ReusePlanner, "plan", side_effect=AssertionError("reuse")),
        patch.object(DemoBlueprintCompiler, "compile", side_effect=AssertionError("blueprint")),
        patch.object(GeneBuilder, "build_from_process", side_effect=AssertionError("genes")),
    ):
        result = SolutionIntelligenceRecompiler().recompile(process, solution, blueprint, [_approval(800000)])
    assert result.diff.changed_demo_node_ids == ["hard-approval-gate"]


def test_explicit_security_and_data_hard_fail_block_selected_asset_without_retrieval() -> None:
    process, solution, blueprint = _baseline()
    repository = AssetRepository()
    asset = repository.get_asset("dc-smart-procurement")
    repository._assets[asset.asset_id] = asset.model_copy(update={"supported_deployments": ["public_saas"]})
    recompiler = SolutionIntelligenceRecompiler(repository)
    security = BusinessConstraint(id="security-private", type="security", statement="必须私有部署", hard=True)
    security_process = process.model_copy(update={"constraints": [security, *process.constraints[1:]]})
    security_fit = FitEngine().reassess_affected(
        security_process, repository.get_asset(asset.asset_id), solution.fit_assessments[0], {"security"}
    )
    assert security_fit.eligible is False
    assert security_fit.effective_fit_score is None
    with patch.object(AssetRetriever, "retrieve", side_effect=AssertionError("must not retrieve")):
        with pytest.raises(ValueError, match="(failed a hard gate|became unavailable)"):
            recompiler.recompile(process, solution, blueprint, [security])

    data = BusinessConstraint(
        id="data-no-document", type="data", statement="招采、招标或合同文档不可获得", hard=True
    )
    updated_process = process.model_copy(update={"constraints": list(process.constraints) + [data]})
    updated_fit = FitEngine().reassess_affected(updated_process, asset, solution.fit_assessments[0], {"data"})
    old_dimensions = {item.name: item.model_dump() for item in solution.fit_assessments[0].dimensions}
    new_dimensions = {item.name: item.model_dump() for item in updated_fit.dimensions}
    assert updated_fit.eligible is False
    assert updated_fit.effective_fit_score is None
    assert new_dimensions["data_knowledge"] != old_dimensions["data_knowledge"] or updated_fit.hard_gates != solution.fit_assessments[0].hard_gates
    assert all(new_dimensions[name] == old_dimensions[name] for name in old_dimensions if name != "data_knowledge")
    with pytest.raises(ValueError, match="(failed a hard gate|became unavailable)"):
        recompiler.recompile(process, solution, blueprint, [data])


def test_diff_records_a_removed_historical_value_claim() -> None:
    _, solution, blueprint = _baseline()
    removed_claim = solution.value_claims[0]
    changed_solution = solution.model_copy(update={"value_claims": []})
    diff = SolutionIntelligenceRecompiler()._diff(
        solution,
        changed_solution,
        blueprint,
        blueprint,
        SolutionIntelligenceRecompiler().detect_affected_scope(solution, blueprint, [], []),
    )

    assert diff.value_claim_changes == [removed_claim.claim_id]
