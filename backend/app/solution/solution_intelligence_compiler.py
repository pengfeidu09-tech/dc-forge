"""Deterministic B-M8.5 compiler consuming retrieval, fit, and reuse outputs."""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import ComponentRef, WorkflowNode
from backend.app.contracts.solution_intelligence import (
    AssetCandidate, FitAssessment, ReuseDecision, SolutionAsset, SolutionBundleV2, SolutionPlanV2,
)
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.asset_retriever import AssetRetriever
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.gene_builder import GeneBuilder
from backend.app.solution.reuse_planner import ReusePlanner


_STRATEGIES = {
    "conservative": ("quick_win", "Quick Win"),
    "balanced": ("production_fit", "Production Fit"),
    "innovative": ("transform", "Transform"),
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class SolutionIntelligenceCompiler:
    def __init__(self, repository: AssetRepository | None = None) -> None:
        self._repository = repository or AssetRepository()
        self._retriever = AssetRetriever(self._repository)
        self._fit_engine = FitEngine()
        self._reuse_planner = ReusePlanner(self._repository)

    def compile(self, process: ProcessSpec) -> SolutionBundleV2:
        genes = GeneBuilder().build_from_process(process)
        candidates = self._retriever.retrieve(process, genes, top_k=3)
        evaluated = [self._evaluate(process, genes, candidate) for candidate in candidates]
        executable = [item for item in evaluated if item[2]]
        if not executable:
            raise ValueError("no executable reuse decisions are available for SolutionBundleV2")

        plans = [self._build_plan(process, plan_type, evaluated) for plan_type in _STRATEGIES]
        balanced = next(plan for plan in plans if plan.plan_type == "balanced")
        return SolutionBundleV2(
            project_id=process.project_id,
            recommended_solution_id=balanced.solution_id,
            plans=plans,
            retrieval_asset_ids=[item.asset_id for item in candidates],
            warnings=["Balanced / Production Fit is the deterministic default recommendation."],
        )

    def _evaluate(self, process: ProcessSpec, genes, candidate: AssetCandidate):
        asset = self._repository.get_asset(candidate.asset_id)
        fit = self._fit_engine.assess(process, genes, asset)
        decisions = self._reuse_planner.plan(process, genes, asset, fit)
        return asset, fit, decisions, list(self._reuse_planner.unresolved_modules)

    def _build_plan(self, process: ProcessSpec, plan_type: str, evaluated) -> SolutionPlanV2:
        display_strategy, display_name = _STRATEGIES[plan_type]
        executable = [
            (asset, fit, decision)
            for asset, fit, decisions, _ in evaluated
            for decision in decisions
            if decision.decision != "unavailable"
        ]
        selected = self._select_for_strategy(plan_type, executable)
        unresolved: list[str] = []
        for asset, fit, decisions, unresolved_items in evaluated:
            unresolved.extend(unresolved_items)
        if not selected:
            raise ValueError("strategy has no executable reuse decision")

        assets = _unique([asset.asset_id for asset, _, _ in selected])
        decisions = [decision for _, _, decision in selected]
        summary = self._reuse_planner.summarize(decisions)
        components = self._components(selected)
        nodes = self._nodes(plan_type, selected, components)
        evidence_refs = _unique([ref for decision in decisions for ref in decision.evidence_refs])
        claims = [claim for asset_id in assets for claim in self._repository.get_asset(asset_id).value_claims if claim.claim_type == "historical"]
        evidence_refs = _unique(evidence_refs + [ref for claim in claims for ref in claim.evidence_refs])
        dependencies = [dep for decision in decisions for dep in decision.dependencies]
        gaps = [gap for decision in decisions for gap in decision.gaps]
        risks = _unique([risk for decision in decisions for risk in decision.risks] + (unresolved if plan_type != "conservative" else []))
        fit_assessments = _unique_fits([fit for _, fit, _ in selected])
        omitted = [item for item in executable if item not in selected]
        plan_warnings = _unique(gaps + (unresolved if plan_type == "conservative" else []))
        plan_warnings.append(
            "Expected value is insufficiently specified: no reliable customer parameters or RunReport exist."
        )
        if plan_type == "conservative":
            plan_warnings.extend(
                f"not selected for Quick Win: {decision.decision} {decision.module_id}"
                for _, _, decision in omitted
            )
        if plan_type == "innovative":
            plan_warnings.append("No additional cross-asset executable module was introduced without a ReuseDecision.")
        steps = self._steps(plan_type, decisions, dependencies)
        review_score = round(sum(item.raw_fit_score for item in fit_assessments) / len(fit_assessments), 2)
        return SolutionPlanV2(
            solution_id=f"{process.project_id}-{plan_type}-v2", source_project_id=process.project_id,
            plan_type=plan_type, display_strategy=display_strategy, name=display_name,
            summary=f"{display_name}: deterministic compilation from selected reuse decisions.",
            primary_asset_ids=assets, fit_assessments=fit_assessments, reuse_decisions=decisions,
            reuse_summary=summary, selected_components=components, to_be_nodes=nodes,
            applied_constraints=list(process.constraints),
            data_requirements=[dep for dep in dependencies if dep.startswith("data:")],
            knowledge_requirements=[dep for dep in dependencies if dep.startswith("knowledge:")],
            system_integrations=[dep for dep in dependencies if dep.startswith(("system:", "tool:"))],
            implementation_steps=steps, assumptions=list(process.missing_information),
            warnings=plan_warnings, risks=risks, evidence_refs=evidence_refs, value_claims=claims,
            review_score=review_score,
        )

    def _select_for_strategy(self, plan_type: str, executable):
        """Choose only from existing ReusePlanner decisions, in stable retrieval order."""
        if plan_type != "conservative":
            return list(executable)
        direct = [item for item in executable if item[2].decision == "direct_reuse"]
        if direct:
            return direct
        configuration = [item for item in executable if item[2].decision == "configuration"]
        if configuration:
            return configuration[:1]
        customization = [item for item in executable if item[2].decision == "customization"]
        return customization[:1]

    def _components(self, selected):
        components = []
        for asset, _, decision in selected:
            module = next(item for item in asset.modules if item.module_id == decision.module_id)
            component_id = f"{asset.asset_id}:{module.module_id}"
            components.append(ComponentRef(component_id=component_id, name=module.name, reason=decision.rationale, required_data=list(module.required_data)))
        return components

    def _nodes(self, plan_type: str, selected, components):
        nodes = []
        for index, ((asset, _, decision), component) in enumerate(zip(selected, components), start=1):
            node_id = f"{plan_type}-{index:03d}"
            next_ids = [f"{plan_type}-{index + 1:03d}"] if index < len(selected) else []
            nodes.append(WorkflowNode(id=node_id, name=component.name, component_id=component.component_id,
                executor="human" if decision.human_review_required else "ai", next_ids=next_ids,
                human_gate=decision.human_review_required,
                gate_reason="customer approval remains required" if decision.human_review_required else None))
        if plan_type == "innovative" and len(nodes) >= 2:
            first = components[0]
            handoff = WorkflowNode(
                id="innovative-redesign-handoff",
                name="System handoff to governed review",
                component_id=first.component_id,
                executor="system",
                next_ids=[nodes[1].id],
                human_gate=False,
            )
            nodes[0] = nodes[0].model_copy(update={"next_ids": [handoff.id]})
            nodes.insert(1, handoff)
        return nodes

    def _steps(self, plan_type: str, decisions, dependencies):
        steps = [f"{decision.decision}: {decision.module_id}" for decision in decisions]
        steps += [f"validate dependency: {item}" for item in _unique(dependencies)]
        if plan_type == "balanced":
            steps.append("confirm production security, system, and approval gaps")
        if plan_type == "innovative":
            steps.append("redesign handoff around selected executable modules")
        return steps


def _unique_fits(items: list[FitAssessment]) -> list[FitAssessment]:
    result = []
    seen = set()
    for item in items:
        if item.asset_id not in seen:
            result.append(item); seen.add(item.asset_id)
    return result
