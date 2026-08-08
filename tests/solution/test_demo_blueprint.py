import json

import pytest
from pydantic import ValidationError

from backend.app.contracts.solution_intelligence import (
    DemoAssertion,
    DemoBlueprint,
    DemoInput,
    DemoNode,
)
from backend.app.solution.demo_blueprint import DemoBlueprintCompiler
from backend.app.solution.solution_intelligence_compiler import SolutionIntelligenceCompiler
from backend.app.solution.service import compile_demo_blueprint
from tests.solution.test_reuse_planner import frozen_procurement_golden_process


def _input() -> DemoInput:
    return DemoInput(
        name="customer_data_01",
        type="customer_data",
        description="confirmed customer input",
    )


def _node(
    node_id: str,
    *,
    next_ids: list[str] | None = None,
    fallback_node_id: str | None = None,
    input_keys: list[str] | None = None,
    output_keys: list[str] | None = None,
    executor: str = "system",
    node_type: str = "transform",
    human_gate: bool = False,
    gate_reason: str | None = None,
) -> DemoNode:
    return DemoNode(
        id=node_id,
        name=node_id,
        node_type=node_type,
        executor=executor,
        next_ids=next_ids or [],
        fallback_node_id=fallback_node_id,
        input_keys=input_keys or [],
        output_keys=output_keys or [],
        human_gate=human_gate,
        gate_reason=gate_reason,
    )


def _blueprint(nodes: list[DemoNode]) -> DemoBlueprint:
    return DemoBlueprint(
        demo_id="demo",
        project_id="project",
        solution_id="solution",
        title="Demo",
        objective="Validate the selected solution.",
        source_asset_ids=["asset"],
        inputs=[_input()],
        nodes=nodes,
        expected_outputs=["report"],
        metric_names=["processing_time"],
        assertions=[
            DemoAssertion(
                assertion_id="metric",
                description="metric collection",
                severity="warning",
                metric_name="processing_time",
                expected_condition="processing_time must be measurable",
            )
        ],
    )


def _simple_graph() -> list[DemoNode]:
    return [
        _node("prepare", next_ids=["report"], input_keys=["customer_data_01"], output_keys=["prepared"]),
        _node("report", node_type="report", input_keys=["prepared"], output_keys=["report"]),
    ]


def _plans():
    process = frozen_procurement_golden_process()
    bundle = SolutionIntelligenceCompiler().compile(process)
    return process, {plan.plan_type: plan for plan in bundle.plans}


def test_demo_contracts_are_strict_and_graph_validators_accept_a_simple_dag() -> None:
    blueprint = _blueprint(_simple_graph())

    assert blueprint.nodes[-1].node_type == "report"
    with pytest.raises(ValidationError):
        DemoInput(name="input", type="data", description="x", extra="forbidden")
    with pytest.raises(ValidationError, match="DemoInput name"):
        _blueprint(_simple_graph()).model_validate(
            _blueprint(_simple_graph()).model_dump()
            | {"inputs": [_input(), _input()]}
        )
    with pytest.raises(ValidationError):
        DemoNode(id="bad", name="bad", node_type="unknown", executor="system")
    with pytest.raises(ValidationError):
        DemoAssertion(
            assertion_id="bad",
            description="bad",
            severity="bad",
            expected_condition="bad",
        )


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        (_simple_graph() + [_simple_graph()[1].model_copy(update={"id": "report"})], "unique"),
        ([_node("prepare", next_ids=["missing"], input_keys=["customer_data_01"], output_keys=["prepared"])], "next_ids"),
        ([_node("prepare", fallback_node_id="missing", input_keys=["customer_data_01"], output_keys=["prepared"])], "fallback"),
        (_simple_graph() + [_node("island", next_ids=["island"], output_keys=["island"])], "unreachable"),
        ([_node("a", next_ids=["b"], output_keys=["a"]), _node("b", next_ids=["a"], input_keys=["a"], output_keys=["b"])], "start"),
        ([_node("prepare", next_ids=["retry"], input_keys=["customer_data_01"], output_keys=["prepared"]), _node("retry", next_ids=["retry"], input_keys=["prepared"], output_keys=["retry_result"])], "terminal"),
        ([_node("gate", executor="ai", human_gate=True, output_keys=["gate"])], "human_gate"),
        ([_node("a", input_keys=["unknown"], output_keys=["a"])], "input_keys"),
        ([_node("a", input_keys=["customer_data_01"], output_keys=["same"]), _node("b", output_keys=["same"])], "unique producers"),
    ],
)
def test_demo_blueprint_rejects_invalid_graphs_and_key_references(nodes, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _blueprint(nodes)


def test_graph_allows_a_cycle_when_an_escape_path_reaches_a_terminal() -> None:
    blueprint = _blueprint(
        [
            _node("prepare", next_ids=["retry"], input_keys=["customer_data_01"], output_keys=["prepared"]),
            _node("retry", next_ids=["retry", "report"], input_keys=["prepared"], output_keys=["retry_result"]),
            _node("report", node_type="report", input_keys=["retry_result"], output_keys=["report"]),
        ]
    )

    assert blueprint.nodes[1].next_ids == ["retry", "report"]


def test_compiler_generates_deterministic_blueprints_from_plan_only() -> None:
    process, plans = _plans()
    compiler = DemoBlueprintCompiler()

    first = compiler.compile(process, plans["balanced"])
    second = compiler.compile(process, plans["balanced"])

    assert first.model_dump() == second.model_dump()
    assert first.project_id == process.project_id
    assert first.solution_id == plans["balanced"].solution_id
    assert plans["balanced"].demo_blueprint_id is None
    assert compile_demo_blueprint(process, plans["balanced"]).model_dump() == first.model_dump()


def test_blueprint_keeps_reference_closure_security_and_approval_without_fabrication() -> None:
    process, plans = _plans()
    blueprint = DemoBlueprintCompiler().compile(process, plans["balanced"])
    solution = plans["balanced"]

    selected = {item.component_id for item in solution.selected_components}
    decisions = {(item.asset_id, item.module_id) for item in solution.reuse_decisions}
    for node in blueprint.nodes:
        if node.component_id:
            assert node.component_id in selected
            assert (node.component_id.split(":", 1)[0], node.asset_module_id) in decisions
    assert blueprint.source_asset_ids == solution.primary_asset_ids + solution.supporting_asset_ids
    assert "数据不得出企业私域" in blueprint.security_requirements
    assert any(item.severity == "blocking" and "私域" in item.expected_condition for item in blueprint.assertions)
    assert any("approval threshold compatibility requires confirmation" in item.expected_condition for item in blueprint.assertions)
    assert {item.metric_name for item in blueprint.assertions if item.metric_name} == {
        "processing_time", "manual_steps", "risk_findings"
    }
    assert set(blueprint.evidence_refs) <= set(solution.evidence_refs)
    assert not any("connected" in item.lower() for item in blueprint.required_integrations)
    assert not any("30min" in item.expected_condition or "30分钟" in item.expected_condition for item in blueprint.assertions)


def test_quick_win_production_and_transform_preserve_their_real_structures() -> None:
    process, plans = _plans()
    compiler = DemoBlueprintCompiler()
    quick, production, transform = (
        compiler.compile(process, plans[plan_type])
        for plan_type in ("conservative", "balanced", "innovative")
    )

    assert "procurement-review-and-risk-location" not in {
        node.asset_module_id for node in quick.nodes
    }
    assert any(node.id == "hard-approval-gate" and node.component_id is None for node in quick.nodes)
    review = next(node for node in production.nodes if node.asset_module_id == "procurement-review-and-risk-location")
    assert review.node_type == "human_gate"
    assert review.executor == "human"
    assert review.human_gate is True
    assert any(node.id == "innovative-redesign-handoff" and node.executor == "system" for node in transform.nodes)
    assert ["processing_time", "manual_steps", "risk_findings"] == production.metric_names
    assert all(claim.claim_type != "verified" for claim in plans["balanced"].value_claims)


def test_compiler_rejects_phantom_unavailable_or_unresolved_component_bindings() -> None:
    process, plans = _plans()
    solution = plans["conservative"]
    phantom_component = solution.selected_components[0].model_copy(
        update={"component_id": "dc-smart-procurement:procurement-knowledge-reuse"}
    )
    phantom = solution.model_copy(update={"selected_components": [phantom_component]})

    with pytest.raises(ValueError, match="selected component"):
        DemoBlueprintCompiler().compile(process, phantom)

    unavailable = solution.reuse_decisions[0].model_copy(update={"decision": "unavailable"})
    blocked = solution.model_copy(update={"reuse_decisions": [unavailable]})
    with pytest.raises(ValueError, match="unavailable"):
        DemoBlueprintCompiler().compile(process, blocked)


def test_c_handoff_json_is_self_contained_without_b_engine_imports() -> None:
    process, plans = _plans()
    payload = json.loads(DemoBlueprintCompiler().compile(process, plans["balanced"]).model_dump_json())

    assert payload["inputs"]
    assert payload["nodes"]
    assert payload["expected_outputs"]
    assert payload["metric_names"] == ["processing_time", "manual_steps", "risk_findings"]
    assert any(item["severity"] == "blocking" for item in payload["assertions"])
    assert payload["security_requirements"]
