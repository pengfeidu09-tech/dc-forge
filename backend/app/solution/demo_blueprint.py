"""Deterministic B-M8.6 DemoBlueprint compiler; it does not execute a demo."""

from __future__ import annotations

import re

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import (
    DemoAssertion,
    DemoBlueprint,
    DemoInput,
    DemoNode,
    SolutionPlanV2,
)
from backend.app.solution.asset_repository import AssetRepository


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _stable_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "node"


class DemoBlueprintCompiler:
    """Compile an already decided SolutionPlanV2 into a C-consumable handoff."""

    def __init__(self, repository: AssetRepository | None = None) -> None:
        self._repository = repository or AssetRepository()

    def compile(self, process: ProcessSpec, solution: SolutionPlanV2) -> DemoBlueprint:
        if solution.source_project_id != process.project_id:
            raise ValueError("SolutionPlanV2 must belong to ProcessSpec.project_id")
        source_asset_ids = _unique(solution.primary_asset_ids + solution.supporting_asset_ids)
        module_by_component, decision_by_component = self._validate_solution_references(
            process, solution, source_asset_ids
        )
        inputs = self._inputs(process, solution)
        nodes = self._nodes(solution, inputs, module_by_component, decision_by_component)
        evidence_refs = self._evidence_refs(solution, source_asset_ids)
        security_requirements = [
            constraint.statement
            for constraint in solution.applied_constraints
            if constraint.hard and constraint.type == "security"
        ]
        assertions = self._assertions(process, solution, nodes, security_requirements)
        expected_outputs = self._expected_outputs(solution, decision_by_component)
        return DemoBlueprint(
            demo_id=f"{solution.solution_id}-demo",
            project_id=process.project_id,
            solution_id=solution.solution_id,
            title=f"Demo: {solution.name}",
            objective=process.business_goal,
            source_asset_ids=source_asset_ids,
            inputs=inputs,
            nodes=nodes,
            expected_outputs=expected_outputs,
            metric_names=_unique(list(process.target_metrics)),
            assertions=assertions,
            required_integrations=_unique(list(solution.system_integrations)),
            security_requirements=security_requirements,
            evidence_refs=evidence_refs,
        )

    def _validate_solution_references(self, process, solution, source_asset_ids):
        source_asset_set = set(source_asset_ids)
        components = {component.component_id: component for component in solution.selected_components}
        decisions = {
            f"{decision.asset_id}:{decision.module_id}": decision
            for decision in solution.reuse_decisions
        }
        if set(components) != set(decisions):
            raise ValueError("selected component bindings must exactly match reuse decisions")

        module_by_component = {}
        for component_id, decision in decisions.items():
            if decision.project_id != process.project_id:
                raise ValueError("reuse decision must belong to ProcessSpec.project_id")
            if decision.asset_id not in source_asset_set:
                raise ValueError("reuse decision asset must belong to solution source assets")
            if decision.decision == "unavailable":
                raise ValueError("unavailable reuse decision cannot bind a DemoNode")
            asset = self._repository.get_asset(decision.asset_id)
            module = next(
                (item for item in asset.modules if item.module_id == decision.module_id), None
            )
            if module is None:
                raise ValueError("reuse decision must reference an existing asset module")
            if not set(decision.evidence_refs) <= {item.evidence_id for item in asset.evidence}:
                raise ValueError("reuse decision evidence_refs must resolve to its asset")
            module_by_component[component_id] = module

        for workflow_node in solution.to_be_nodes:
            if workflow_node.component_id not in components:
                raise ValueError("workflow component must be a selected component")
        return module_by_component, decisions

    def _inputs(self, process: ProcessSpec, solution: SolutionPlanV2) -> list[DemoInput]:
        sources: list[tuple[str, str]] = [("customer_data", value) for value in process.available_data]
        sources.extend(("data_requirement", value.removeprefix("data:")) for value in solution.data_requirements)
        sources.extend(
            ("knowledge_requirement", value.removeprefix("knowledge:"))
            for value in solution.knowledge_requirements
        )
        source_type_by_value: dict[str, str] = {}
        for kind, value in sources:
            if value and value not in source_type_by_value:
                source_type_by_value[value] = kind
        unique_sources = sorted(
            ((kind, value) for value, kind in source_type_by_value.items()),
            key=lambda item: (item[0], item[1]),
        )
        return [
            DemoInput(
                name=f"customer_input_{index:02d}",
                type=kind,
                description=f"Confirmed input requirement: {value}",
            )
            for index, (kind, value) in enumerate(unique_sources, start=1)
        ]

    def _nodes(self, solution, inputs, module_by_component, decision_by_component):
        plan_nodes = list(solution.to_be_nodes)
        plan_ids = {node.id for node in plan_nodes}
        reserved = {"demo-input-preparation", "hard-approval-gate", "demo-report"}
        if plan_ids & reserved:
            raise ValueError("SolutionPlanV2 workflow uses a reserved DemoBlueprint node id")
        incoming = {node.id: [] for node in plan_nodes}
        for node in plan_nodes:
            for target in node.next_ids:
                if target in incoming:
                    incoming[target].append(node.id)
        starts = [node.id for node in plan_nodes if not incoming[node.id]]
        if not starts:
            raise ValueError("SolutionPlanV2 workflow requires a start node")

        output_key = {node.id: f"{_stable_key(node.id)}_result" for node in plan_nodes}
        nodes = [
            DemoNode(
                id="demo-input-preparation",
                name="Prepare confirmed demo inputs",
                node_type="transform",
                executor="system",
                input_keys=[item.name for item in inputs],
                output_keys=["prepared_inputs"],
                next_ids=starts,
            )
        ]
        for plan_node in plan_nodes:
            module = module_by_component[plan_node.component_id]
            decision = decision_by_component[plan_node.component_id]
            input_keys = ["prepared_inputs"] + [output_key[node_id] for node_id in incoming[plan_node.id]]
            nodes.append(
                DemoNode(
                    id=plan_node.id,
                    name=plan_node.name,
                    node_type=self._node_type(plan_node, module.capability_ids),
                    executor=plan_node.executor,
                    component_id=plan_node.component_id,
                    asset_module_id=decision.module_id,
                    input_keys=_unique(input_keys),
                    output_keys=[output_key[plan_node.id]],
                    next_ids=list(plan_node.next_ids),
                    human_gate=plan_node.human_gate,
                    gate_reason=(
                        "Human review is required by the selected reuse decision and customer approval constraint."
                        if plan_node.human_gate
                        else None
                    ),
                )
            )

        terminals = [node.id for node in plan_nodes if not node.next_ids]
        approval_constraints = [
            constraint
            for constraint in solution.applied_constraints
            if constraint.hard and constraint.type == "approval"
        ]
        next_after_plan = "hard-approval-gate" if approval_constraints else "demo-report"
        nodes = [
            node.model_copy(update={"next_ids": [next_after_plan]}) if node.id in terminals else node
            for node in nodes
        ]
        report_inputs = [output_key[node_id] for node_id in terminals]
        if approval_constraints:
            nodes.append(
                DemoNode(
                    id="hard-approval-gate",
                    name="Customer hard approval gate",
                    node_type="human_gate",
                    executor="human",
                    input_keys=report_inputs,
                    output_keys=["approval_decision"],
                    next_ids=["demo-report"],
                    human_gate=True,
                    gate_reason=(
                        "A hard customer approval constraint requires human approval when the customer threshold applies; "
                        "approval threshold compatibility requires confirmation."
                    ),
                )
            )
            report_inputs = ["approval_decision"]
        nodes.append(
            DemoNode(
                id="demo-report",
                name="Demo validation report",
                node_type="report",
                executor="system",
                input_keys=report_inputs,
                output_keys=["demo_validation_report"],
            )
        )
        return nodes

    def _node_type(self, plan_node, capability_ids: list[str]) -> str:
        if plan_node.human_gate:
            return "human_gate"
        if plan_node.executor == "system":
            return "tool"
        capabilities = set(capability_ids)
        if "enterprise-rag" in capabilities:
            return "retrieval"
        if "rule-engine" in capabilities:
            return "rule"
        return "transform"

    def _expected_outputs(self, solution, decisions) -> list[str]:
        outputs = []
        for component_id in (item.component_id for item in solution.selected_components):
            decision = decisions[component_id]
            asset = self._repository.get_asset(decision.asset_id)
            module = next(item for item in asset.modules if item.module_id == decision.module_id)
            outputs.append(f"{module.name} result")
        if any(constraint.hard and constraint.type == "approval" for constraint in solution.applied_constraints):
            outputs.append("human approval decision")
        outputs.append("demo validation report")
        return _unique(outputs)

    def _assertions(self, process, solution, nodes, security_requirements):
        assertions = [
            DemoAssertion(
                assertion_id=f"metric-{metric_name}",
                description=f"Runtime should collect {metric_name}.",
                severity="warning",
                metric_name=metric_name,
                expected_condition=f"{metric_name} must be emitted or measurable by Runtime.",
            )
            for metric_name in _unique(list(process.target_metrics))
        ]
        assertions.extend(
            DemoAssertion(
                assertion_id=f"security-{index:02d}",
                description="Preserve a hard customer security requirement.",
                severity="blocking",
                expected_condition=f"Demo execution must preserve: {requirement}",
            )
            for index, requirement in enumerate(security_requirements, start=1)
        )
        for decision in solution.reuse_decisions:
            if decision.human_review_required:
                assertions.append(
                    DemoAssertion(
                        assertion_id=f"human-review-{decision.module_id}",
                        description="Selected module requires human review.",
                        severity="blocking",
                        expected_condition=f"A human gate must remain for {decision.module_id}.",
                    )
                )
        if any(constraint.hard and constraint.type == "approval" for constraint in solution.applied_constraints):
            assertions.append(
                DemoAssertion(
                    assertion_id="hard-approval",
                    description="Preserve the customer hard approval requirement.",
                    severity="blocking",
                    expected_condition=(
                        "When amount exceeds the customer approval threshold, execution must enter a human approval gate; "
                        "approval threshold compatibility requires confirmation."
                    ),
                )
            )
        assertions.extend(
            DemoAssertion(
                assertion_id=f"output-{node.id}",
                description=f"Required output from {node.name}.",
                severity="blocking",
                expected_condition=f"{output_key} must be produced for the demo handoff.",
            )
            for node in nodes
            for output_key in node.output_keys
            if node.node_type in {"human_gate", "report"}
        )
        return assertions

    def _evidence_refs(self, solution, source_asset_ids):
        evidence_by_asset = {
            asset_id: {item.evidence_id for item in self._repository.get_asset(asset_id).evidence}
            for asset_id in source_asset_ids
        }
        refs = _unique([ref for decision in solution.reuse_decisions for ref in decision.evidence_refs])
        if not set(refs) <= set().union(*evidence_by_asset.values()):
            raise ValueError("DemoBlueprint evidence_refs must resolve to source asset evidence")
        if not set(refs) <= set(solution.evidence_refs):
            raise ValueError("DemoBlueprint evidence_refs must be present in SolutionPlanV2")
        return refs
