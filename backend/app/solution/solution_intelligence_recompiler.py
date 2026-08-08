"""Deterministic, scoped B-M8.7 recompile for an existing V2 plan and Blueprint."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import (
    DemoAssertion,
    DemoBlueprint,
    DemoNode,
    RecompileSolutionV2Result,
    SolutionIntelligenceDiff,
    SolutionPlanV2,
)
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.reuse_planner import ReusePlanner


@dataclass(frozen=True)
class AffectedScope:
    changed_constraint_ids: list[str]
    affected_constraint_types: list[str]
    affected_fit_dimensions: list[str]
    affected_hard_gate_categories: list[str]
    affected_asset_ids: list[str]
    affected_module_ids: list[str]
    affects_retrieval: bool
    affects_blueprint: bool
    affected_demo_node_ids: list[str]


_FIT_DIMENSIONS = {"approval": ["rules"], "data": ["data_knowledge"]}
_GATE_CATEGORIES = {
    "approval": ["rule"], "security": ["security", "deployment"],
    "data": ["data"], "budget": ["budget"], "time": ["time"], "risk": ["risk"],
}


def merge_constraints(
    old_constraints: list[BusinessConstraint], new_constraints: list[BusinessConstraint]
) -> tuple[list[BusinessConstraint], list[str], list[str]]:
    """Override existing ids in place; append new ids in sorted order without mutating input."""
    latest = {constraint.id: constraint for constraint in new_constraints}
    old_by_id = {constraint.id: constraint for constraint in old_constraints}
    merged = [latest.get(constraint.id, constraint) for constraint in old_constraints]
    additions = [latest[item_id] for item_id in sorted(latest) if item_id not in old_by_id]
    merged.extend(additions)
    changed_ids = sorted(
        item_id
        for item_id, constraint in latest.items()
        if item_id not in old_by_id or old_by_id[item_id].model_dump() != constraint.model_dump()
    )
    types = sorted({old_by_id[item_id].type for item_id in changed_ids if item_id in old_by_id} | {latest[item_id].type for item_id in changed_ids})
    return merged, changed_ids, types


class SolutionIntelligenceRecompiler:
    """Incrementally update only selected-plan entities affected by new constraints."""

    def __init__(self, repository: AssetRepository | None = None) -> None:
        self._repository = repository or AssetRepository()
        self._fit_engine = FitEngine()
        self._reuse_planner = ReusePlanner(self._repository)

    def detect_affected_scope(
        self, solution: SolutionPlanV2, blueprint: DemoBlueprint,
        changed_constraint_ids: list[str], affected_types: list[str],
    ) -> AffectedScope:
        affected_modules = []
        for decision in solution.reuse_decisions:
            asset = self._repository.get_asset(decision.asset_id)
            module = next(item for item in asset.modules if item.module_id == decision.module_id)
            capabilities = set(module.capability_ids)
            if "approval" in affected_types and (
                decision.human_review_required or "human-approval" in capabilities
                or "rule-engine" in capabilities or module.required_rules
            ):
                affected_modules.append(f"{decision.asset_id}:{decision.module_id}")
            elif "security" in affected_types:
                affected_modules.append(f"{decision.asset_id}:{decision.module_id}")
            elif "data" in affected_types and module.required_data:
                affected_modules.append(f"{decision.asset_id}:{decision.module_id}")
        affected_modules = sorted(set(affected_modules))
        component_to_node = {
            node.component_id: node.id for node in blueprint.nodes if node.component_id
        }
        demo_nodes = [component_to_node[item] for item in affected_modules if item in component_to_node]
        if "approval" in affected_types and any(node.id == "hard-approval-gate" for node in blueprint.nodes):
            demo_nodes.append("hard-approval-gate")
        return AffectedScope(
            changed_constraint_ids=changed_constraint_ids,
            affected_constraint_types=affected_types,
            affected_fit_dimensions=sorted({name for item in affected_types for name in _FIT_DIMENSIONS.get(item, [])}),
            affected_hard_gate_categories=sorted({name for item in affected_types for name in _GATE_CATEGORIES[item]}),
            affected_asset_ids=sorted({item.split(":", 1)[0] for item in affected_modules}),
            affected_module_ids=affected_modules,
            affects_retrieval=False,
            affects_blueprint=bool(affected_types),
            affected_demo_node_ids=sorted(set(demo_nodes)),
        )

    def recompile(
        self,
        process: ProcessSpec,
        selected_solution: SolutionPlanV2,
        selected_blueprint: DemoBlueprint,
        new_constraints: list[BusinessConstraint],
    ) -> RecompileSolutionV2Result:
        self._validate_baseline(process, selected_solution, selected_blueprint)
        merged, changed_ids, affected_types = merge_constraints(
            list(process.constraints), list(new_constraints)
        )
        if not changed_ids:
            return RecompileSolutionV2Result(
                previous_solution_id=selected_solution.solution_id,
                previous_demo_id=selected_blueprint.demo_id,
                new_solution=selected_solution,
                new_blueprint=selected_blueprint,
                diff=SolutionIntelligenceDiff(explanations=["no effective change: constraints are identical"]),
            )

        updated_process = process.model_copy(update={"constraints": merged})
        scope = self.detect_affected_scope(selected_solution, selected_blueprint, changed_ids, affected_types)
        new_fits = self._recompute_fits(updated_process, selected_solution, scope)
        new_decisions = self._recompute_decisions(updated_process, selected_solution, new_fits, scope)
        new_solution = self._update_solution(selected_solution, merged, new_fits, new_decisions)
        new_blueprint = self._update_blueprint(selected_blueprint, new_solution, affected_types)
        diff = self._diff(selected_solution, new_solution, selected_blueprint, new_blueprint, scope)
        return RecompileSolutionV2Result(
            previous_solution_id=selected_solution.solution_id,
            previous_demo_id=selected_blueprint.demo_id,
            new_solution=new_solution,
            new_blueprint=new_blueprint,
            diff=diff,
        )

    def _validate_baseline(self, process, solution, blueprint) -> None:
        if solution.source_project_id != process.project_id:
            raise ValueError("selected_solution must belong to process project_id")
        if blueprint.project_id != process.project_id or blueprint.solution_id != solution.solution_id:
            raise ValueError("selected_blueprint must belong to selected_solution and process")
        expected_assets = list(dict.fromkeys(solution.primary_asset_ids + solution.supporting_asset_ids))
        if blueprint.source_asset_ids != expected_assets:
            raise ValueError("selected_blueprint source assets must match selected_solution")

    def _recompute_fits(self, process, solution, scope):
        affected_assets = set(scope.affected_asset_ids)
        return [
            self._fit_engine.reassess_affected(
                process, self._repository.get_asset(fit.asset_id), fit,
                set(scope.affected_constraint_types),
            ) if fit.asset_id in affected_assets else fit
            for fit in solution.fit_assessments
        ]

    def _recompute_decisions(self, process, solution, fits, scope):
        fits_by_asset = {fit.asset_id: fit for fit in fits}
        affected_modules = set(scope.affected_module_ids)
        selected_asset_ids = {decision.asset_id for decision in solution.reuse_decisions}
        blocked_assets = [
            asset_id for asset_id, fit in fits_by_asset.items()
            if asset_id in selected_asset_ids and not fit.eligible
        ]
        if blocked_assets:
            raise ValueError(
                "incremental recompile blocked: selected executable asset failed a hard gate: "
                + ", ".join(sorted(blocked_assets))
            )
        updated = []
        for decision in solution.reuse_decisions:
            key = f"{decision.asset_id}:{decision.module_id}"
            if key not in affected_modules:
                updated.append(decision)
                continue
            recomputed = self._reuse_planner.reassess_decision(
                process, self._repository.get_asset(decision.asset_id),
                fits_by_asset[decision.asset_id], decision,
            )
            if recomputed is None:
                raise ValueError("affected module became unresolved and cannot remain executable")
            if recomputed.decision == "unavailable":
                raise ValueError("affected module became unavailable and blocks the selected executable plan")
            updated.append(recomputed)
        return updated

    def _update_solution(self, old, merged_constraints, fits, decisions):
        summary = self._reuse_planner.summarize(decisions)
        score = round(sum(item.raw_fit_score for item in fits) / len(fits), 2)
        revision = self._revision_id(old.solution_id, merged_constraints)
        candidate = old.model_copy(update={
            "solution_id": revision,
            "applied_constraints": merged_constraints,
            "fit_assessments": fits,
            "reuse_decisions": decisions,
            "reuse_summary": summary,
            "review_score": score,
        })
        return SolutionPlanV2.model_validate(candidate.model_dump())

    def _revision_id(self, solution_id: str, constraints: list[BusinessConstraint]) -> str:
        base = re.sub(r"-r-[0-9a-f]{8}$", "", solution_id)
        payload = json.dumps([item.model_dump() for item in constraints], ensure_ascii=False, sort_keys=True)
        return f"{base}-r-{sha256(payload.encode('utf-8')).hexdigest()[:8]}"

    def _update_blueprint(self, old, solution, affected_types):
        nodes = list(old.nodes)
        assertions = list(old.assertions)
        security_requirements = list(old.security_requirements)
        if "approval" in affected_types:
            approval_statements = [item.statement for item in solution.applied_constraints if item.hard and item.type == "approval"]
            condition = "; ".join(approval_statements)
            nodes = [
                node.model_copy(update={
                    "gate_reason": f"Customer hard approval requirement: {condition}. approval threshold compatibility requires confirmation."
                }) if node.id == "hard-approval-gate" else node
                for node in nodes
            ]
            assertions = [
                assertion.model_copy(update={
                    "expected_condition": f"When customer approval requirements apply ({condition}), execution must enter a human approval gate; approval threshold compatibility requires confirmation."
                }) if assertion.assertion_id == "hard-approval" else assertion
                for assertion in assertions
            ]
        if "security" in affected_types:
            security_requirements = [item.statement for item in solution.applied_constraints if item.hard and item.type == "security"]
            assertions = [
                assertion for assertion in assertions if not assertion.assertion_id.startswith("security-")
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
        candidate = old.model_copy(update={
            "demo_id": f"{solution.solution_id}-demo",
            "solution_id": solution.solution_id,
            "nodes": nodes,
            "assertions": assertions,
            "security_requirements": security_requirements,
        })
        return DemoBlueprint.model_validate(candidate.model_dump())

    def _diff(self, old_solution, new_solution, old_blueprint, new_blueprint, scope):
        old_fits = {item.asset_id: item for item in old_solution.fit_assessments}
        new_fits = {item.asset_id: item for item in new_solution.fit_assessments}
        changed_fits = sorted(item_id for item_id in new_fits if new_fits[item_id].model_dump() != old_fits[item_id].model_dump())
        old_decisions = {f"{item.asset_id}:{item.module_id}": item for item in old_solution.reuse_decisions}
        new_decisions = {f"{item.asset_id}:{item.module_id}": item for item in new_solution.reuse_decisions}
        changed_modules = sorted(item_id for item_id in new_decisions if new_decisions[item_id].model_dump() != old_decisions[item_id].model_dump())
        reuse_mode_changes = {
            item_id: f"{old_decisions[item_id].decision} -> {new_decisions[item_id].decision}"
            for item_id in changed_modules
            if old_decisions[item_id].decision != new_decisions[item_id].decision
        }
        old_nodes = {item.id: item for item in old_blueprint.nodes}
        new_nodes = {item.id: item for item in new_blueprint.nodes}
        added = sorted(set(new_nodes) - set(old_nodes))
        removed = sorted(set(old_nodes) - set(new_nodes))
        changed_nodes = sorted(
            item_id for item_id in set(old_nodes) & set(new_nodes)
            if old_nodes[item_id].model_dump() != new_nodes[item_id].model_dump()
        )
        changed_assets = sorted(set(changed_fits) | {item_id.split(":", 1)[0] for item_id in changed_modules})
        old_claims = {item.claim_id: item for item in old_solution.value_claims}
        new_claims = {item.claim_id: item for item in new_solution.value_claims}
        value_changes = sorted(
            item_id for item_id in set(old_claims) | set(new_claims)
            if item_id not in old_claims or item_id not in new_claims
            or old_claims[item_id].model_dump() != new_claims[item_id].model_dump()
        )
        return SolutionIntelligenceDiff(
            changed_asset_ids=changed_assets,
            changed_fit_asset_ids=changed_fits,
            changed_module_ids=changed_modules,
            reuse_mode_changes=reuse_mode_changes,
            added_demo_node_ids=added,
            removed_demo_node_ids=removed,
            changed_demo_node_ids=changed_nodes,
            value_claim_changes=value_changes,
            explanations=[
                f"incremental scope: constraints={', '.join(scope.changed_constraint_ids)}",
                "AssetRetriever was not invoked; selected plan and Blueprint were updated in place.",
            ],
        )
