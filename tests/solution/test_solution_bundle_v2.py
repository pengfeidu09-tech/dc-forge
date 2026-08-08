from collections import Counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.contracts.solution_intelligence import SolutionBundleV2
from backend.app.main import app
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.gene_builder import GeneBuilder
from backend.app.solution.solution_intelligence_compiler import SolutionIntelligenceCompiler
from tests.solution.test_reuse_planner import frozen_procurement_golden_process


def _compile():
    return SolutionIntelligenceCompiler().compile(frozen_procurement_golden_process())


def _structural_fingerprint(plan):
    """Only executable scope, dependencies, and topology count as structure."""
    return (
        tuple(plan.primary_asset_ids),
        tuple(plan.supporting_asset_ids),
        tuple(item.component_id for item in plan.selected_components),
        tuple(
            (item.asset_id, item.module_id, item.decision) for item in plan.reuse_decisions
        ),
        tuple(plan.reuse_summary.model_dump().items()),
        tuple(
            (node.component_id, node.executor, node.human_gate, tuple(node.next_ids))
            for node in plan.to_be_nodes
        ),
        tuple(plan.data_requirements),
        tuple(plan.knowledge_requirements),
        tuple(plan.system_integrations),
    )


def _plan(bundle, plan_type):
    return next(plan for plan in bundle.plans if plan.plan_type == plan_type)


def test_v2_bundle_has_exactly_three_plans_fixed_strategies_and_balanced_default() -> None:
    bundle = _compile()
    plans = {plan.plan_type: plan for plan in bundle.plans}

    assert set(plans) == {"conservative", "balanced", "innovative"}
    assert bundle.recommended_solution_id == plans["balanced"].solution_id
    assert {
        plan_type: plan.display_strategy for plan_type, plan in plans.items()
    } == {
        "conservative": "quick_win",
        "balanced": "production_fit",
        "innovative": "transform",
    }
    assert len({_structural_fingerprint(plan) for plan in plans.values()}) == 3


def test_quick_win_is_a_real_minimum_executable_scope_and_production_covers_more() -> None:
    bundle = _compile()
    quick_win = _plan(bundle, "conservative")
    production = _plan(bundle, "balanced")

    assert [item.decision for item in quick_win.reuse_decisions] == ["direct_reuse"]
    assert [item.module_id for item in quick_win.reuse_decisions] == [
        "procurement-document-workbench"
    ]
    assert {item.module_id for item in production.reuse_decisions} == {
        "procurement-document-workbench",
        "procurement-review-and-risk-location",
    }
    assert production.reuse_summary.configuration_count == 1
    assert quick_win.reuse_summary.configuration_count == 0
    assert any("not selected for Quick Win" in warning for warning in quick_win.warnings)


def test_transform_has_real_topology_difference_without_fabricated_assets_or_customization() -> None:
    bundle = _compile()
    production = _plan(bundle, "balanced")
    transform = _plan(bundle, "innovative")

    production_topology = [
        (node.component_id, node.executor, node.human_gate, tuple(node.next_ids))
        for node in production.to_be_nodes
    ]
    transform_topology = [
        (node.component_id, node.executor, node.human_gate, tuple(node.next_ids))
        for node in transform.to_be_nodes
    ]
    assert production_topology != transform_topology
    assert any(node.executor == "system" for node in transform.to_be_nodes)
    assert transform.supporting_asset_ids == []
    assert transform.reuse_summary.customization_count == 0


def test_plan_and_bundle_reference_closure_and_exact_reuse_summaries() -> None:
    bundle = _compile()
    repository = AssetRepository()
    retrieved = set(bundle.retrieval_asset_ids)

    assert bundle.project_id == frozen_procurement_golden_process().project_id
    compiler = SolutionIntelligenceCompiler()
    process = frozen_procurement_golden_process()
    candidates = compiler._retriever.retrieve(
        process, GeneBuilder().build_from_process(process), top_k=3
    )
    assert bundle.retrieval_asset_ids == [candidate.asset_id for candidate in candidates]

    for plan in bundle.plans:
        assert plan.source_project_id == bundle.project_id
        plan_assets = set(plan.primary_asset_ids + plan.supporting_asset_ids)
        assert plan_assets <= retrieved
        assert {fit.asset_id for fit in plan.fit_assessments} <= retrieved
        assert {decision.asset_id for decision in plan.reuse_decisions} <= plan_assets
        selected_ids = {component.component_id for component in plan.selected_components}
        executable = {
            f"{decision.asset_id}:{decision.module_id}"
            for decision in plan.reuse_decisions
            if decision.decision != "unavailable"
        }
        assert selected_ids == executable
        assert all(node.component_id in selected_ids for node in plan.to_be_nodes)
        assert all(decision.decision != "unavailable" for decision in plan.reuse_decisions)
        assert all(
            decision.module_id
            in {module.module_id for module in repository.get_asset(decision.asset_id).modules}
            for decision in plan.reuse_decisions
        )
        counts = Counter(decision.decision for decision in plan.reuse_decisions)
        assert plan.reuse_summary.direct_reuse_count == counts["direct_reuse"]
        assert plan.reuse_summary.configuration_count == counts["configuration"]
        assert plan.reuse_summary.customization_count == counts["customization"]
        assert plan.reuse_summary.unavailable_count == counts["unavailable"]


def test_golden_constraints_human_review_and_value_provenance_are_preserved() -> None:
    bundle = _compile()
    expected_constraints = {"security-private", "approval-threshold"}
    repository = AssetRepository()

    for plan in bundle.plans:
        assert {constraint.id for constraint in plan.applied_constraints} == expected_constraints
        assert plan.demo_blueprint_id is None
        assert all(claim.claim_type == "historical" for claim in plan.value_claims)
        assert all(claim.claim_type != "verified" for claim in plan.value_claims)
        assert not any(claim.claim_type == "expected" for claim in plan.value_claims)
        assert any("Expected value is insufficient" in warning for warning in plan.warnings)
        evidence_by_asset = {
            asset_id: {item.evidence_id for item in repository.get_asset(asset_id).evidence}
            for asset_id in plan.primary_asset_ids
        }
        assert set(plan.evidence_refs) <= set().union(*evidence_by_asset.values())
        for decision in plan.reuse_decisions:
            assert set(decision.evidence_refs) <= evidence_by_asset[decision.asset_id]
        for claim in plan.value_claims:
            assert set(claim.evidence_refs) <= set().union(*evidence_by_asset.values())

    production = _plan(bundle, "balanced")
    review = next(
        item
        for item in production.reuse_decisions
        if item.module_id == "procurement-review-and-risk-location"
    )
    review_node = next(
        node for node in production.to_be_nodes if node.component_id.endswith(review.module_id)
    )
    assert review.human_review_required is True
    assert review_node.human_gate is True
    assert review_node.executor == "human"
    assert "approval threshold compatibility requires confirmation" in review.gaps
    assert all("500000" not in change for change in review.required_changes)


def test_contract_rejects_illegal_strategy_mapping_and_cross_project_bundle() -> None:
    bundle = _compile()
    invalid_strategy = bundle.plans[0].model_copy(update={"display_strategy": "transform"})
    with pytest.raises(ValidationError, match="display_strategy"):
        invalid_strategy.__class__.model_validate(invalid_strategy.model_dump())

    cross_project = bundle.plans[0].model_copy(update={"source_project_id": "other-project"})
    payload = bundle.model_dump()
    payload["plans"][0] = cross_project.model_dump()
    with pytest.raises(ValidationError, match="project_id"):
        SolutionBundleV2.model_validate(payload)


def test_v2_compilation_is_deterministic_and_does_not_reclassify_reuse_modes() -> None:
    first = _compile()
    second = _compile()

    assert first.model_dump() == second.model_dump()
    assert {item.decision for item in _plan(first, "conservative").reuse_decisions} == {
        "direct_reuse"
    }


def test_compile_solution_v2_api_is_parallel_to_v1_api_and_rejects_extra_process_field() -> None:
    process = frozen_procurement_golden_process()
    client = TestClient(app)

    response = client.post("/compile-solution-v2", json=process.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json()["recommended_solution_id"].endswith("balanced-v2")

    invalid = process.model_dump(mode="json") | {"unexpected": "not allowed"}
    assert client.post("/compile-solution-v2", json=invalid).status_code == 422

    schema = client.get("/openapi.json").json()
    assert "/compile-solution" in schema["paths"]
    assert "/recompile-solution" in schema["paths"]
    assert "/review-solution" in schema["paths"]
    assert "/agent/solution" in schema["paths"]
