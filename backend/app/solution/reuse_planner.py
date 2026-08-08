"""Deterministic module-level reuse decisions for B-M8.4."""

from __future__ import annotations

from collections.abc import Iterable

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import (
    AIGene,
    FitAssessment,
    ReuseDecision,
    ReuseSummary,
    SolutionAsset,
    SolutionAssetModule,
)
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.asset_retriever import _matched_terms


_UNAVAILABLE_MARKERS = ("不可获得", "无法获得", "无法提供", "不可用", "禁止使用", "不存在", "unavailable")
_HUMAN_REVIEW_CAPABILITIES = {"human-approval", "human-review"}
_GENERIC_ACTION_TERMS = {"文档", "生成", "审查", "数据", "规则", "处理", "报告", "文本", "业务", "场景", "能力"}
_LINEAGE_DESCRIPTION_MARKERS = ("来源于", "复用依据")


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _missing(required: list[str], available: list[str]) -> list[str]:
    return [item for item in required if not _matched_terms([item], available)]


class ReusePlanner:
    """Classify relevant modules from facts, never from a FitScore threshold."""

    def __init__(self, repository: AssetRepository) -> None:
        self._repository = repository
        self._last_unresolved: list[str] = []

    @property
    def unresolved_modules(self) -> list[str]:
        """Stable planner-level confirmation gaps; not a fifth ReuseMode."""
        return list(self._last_unresolved)

    def plan(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        asset: SolutionAsset,
        fit: FitAssessment,
    ) -> list[ReuseDecision]:
        if fit.project_id != process.project_id or fit.asset_id != asset.asset_id:
            raise ValueError("fit assessment must belong to the supplied process and asset")

        self._last_unresolved = []
        evidence_ids = {evidence.evidence_id for evidence in asset.evidence}
        global_blockers = [
            gate.reason
            for gate in fit.hard_gates
            if not gate.passed and gate.category in {"security", "deployment"}
        ]
        decisions: list[ReuseDecision] = []
        for module in asset.modules:
            if not self._participates(process, genes, module):
                continue
            if not set(module.evidence_refs) <= evidence_ids:
                raise ValueError(f"module {module.module_id} has dangling evidence reference")
            decision = self._decide_module(process, asset, module, fit, global_blockers)
            if decision is not None:
                decisions.append(decision)
            else:
                self._last_unresolved.append(
                    f"module:{module.module_id}: reuse decision requires confirmation"
                )
        return decisions

    def summarize(self, decisions: list[ReuseDecision]) -> ReuseSummary:
        if not decisions:
            raise ValueError("reuse summary requires at least one decision")
        total = len(decisions)
        counts = {mode: sum(item.decision == mode for item in decisions) for mode in (
            "direct_reuse", "configuration", "customization", "unavailable"
        )}
        return ReuseSummary(
            direct_reuse_count=counts["direct_reuse"],
            configuration_count=counts["configuration"],
            customization_count=counts["customization"],
            unavailable_count=counts["unavailable"],
            direct_reuse_ratio=counts["direct_reuse"] / total,
            configuration_ratio=counts["configuration"] / total,
            customization_ratio=counts["customization"] / total,
            unavailable_ratio=counts["unavailable"] / total,
        )

    def reassess_decision(
        self,
        process: ProcessSpec,
        asset: SolutionAsset,
        fit: FitAssessment,
        previous: ReuseDecision,
    ) -> ReuseDecision | None:
        """Reapply the existing module decision rule to one affected module only."""
        module = next((item for item in asset.modules if item.module_id == previous.module_id), None)
        if module is None:
            raise ValueError("reuse decision module must exist in the supplied asset")
        global_blockers = [
            gate.reason
            for gate in fit.hard_gates
            if not gate.passed and gate.category in {"security", "deployment"}
        ]
        return self._decide_module(process, asset, module, fit, global_blockers)

    def _participates(
        self, process: ProcessSpec, genes: list[AIGene], module: SolutionAssetModule
    ) -> bool:
        if self._strong_action_matches(process, genes, module):
            return True
        context = list(process.available_data) + list(process.existing_systems) + [
            constraint.statement for constraint in process.constraints
        ]
        requirements = (
            list(module.required_data)
            + list(module.required_knowledge)
            + list(module.required_rules)
            + list(module.required_systems)
            + list(module.required_tools)
        )
        return bool(_matched_terms(requirements, context))

    def _strong_action_matches(
        self, process: ProcessSpec, genes: list[AIGene], module: SolutionAssetModule
    ) -> list[str]:
        action_terms = [node.name for node in process.as_is_nodes] + [
            node.description for node in process.as_is_nodes
        ] + [gene.action_name for gene in genes] + [process.business_goal]
        module_terms = [module.name]
        if not any(marker in module.description for marker in _LINEAGE_DESCRIPTION_MARKERS):
            module_terms.append(module.description)
        matches = _matched_terms(module_terms, action_terms)
        return [
            match
            for match in matches
            if match not in _GENERIC_ACTION_TERMS and len(match) >= 2
        ]

    def _decide_module(
        self,
        process: ProcessSpec,
        asset: SolutionAsset,
        module: SolutionAssetModule,
        fit: FitAssessment,
        global_blockers: list[str],
    ) -> ReuseDecision | None:
        matched, missing_data, missing_knowledge, missing_rules, missing_systems = self._requirements(
            process, module
        )
        dependencies = self._dependencies(asset, module)
        human_review_required = self._human_review_required(process, module)
        approval_gaps = self._approval_gaps(process, module)

        if global_blockers:
            return self._decision(
                process, asset, module, "unavailable",
                rationale="module is blocked by an explicit asset-level security or deployment conflict",
                matched=matched, gaps=[f"hard blocker: {reason}" for reason in global_blockers] + approval_gaps,
                dependencies=dependencies, risks=["hard security or deployment constraint conflict"],
                effort="unknown", human_review_required=human_review_required,
            )

        explicitly_unavailable = self._explicitly_unavailable(process, module.required_data)
        if explicitly_unavailable:
            return self._decision(
                process, asset, module, "unavailable",
                rationale="required module data is explicitly unavailable under a hard customer constraint",
                matched=matched,
                gaps=[f"hard data conflict: {item}" for item in explicitly_unavailable] + approval_gaps,
                dependencies=dependencies, risks=["required data cannot be supplied"], effort="unknown",
                human_review_required=human_review_required,
            )

        configuration_changes = self._configuration_changes(process, module)
        if missing_systems:
            changes = [f"develop:connector adapter for system:{item}" for item in missing_systems]
            changes += [f"develop:connector adapter for tool:{item}" for item in _missing(module.required_tools, process.existing_systems)]
            return self._decision(
                process, asset, module, "customization",
                rationale="a required system or tool is not present in the confirmed customer systems and has no documented configuration path",
                matched=matched,
                gaps=[f"required system unavailable: {item}" for item in missing_systems] + approval_gaps,
                changes=changes, dependencies=dependencies,
                risks=["new integration implementation requires validation"], effort="medium",
                human_review_required=human_review_required,
            )

        if configuration_changes and self._strong_action_matches(process, [], module) and not missing_data and not missing_knowledge:
            return self._decision(
                process, asset, module, "configuration",
                rationale="the module's documented configurable items cover the confirmed customer-specific settings",
                matched=matched,
                gaps=[f"customer-specific setting: {item.removeprefix('configure:')}" for item in configuration_changes] + approval_gaps,
                changes=configuration_changes, dependencies=dependencies, effort="small",
                human_review_required=human_review_required,
            )

        # Missing data, knowledge, or rules without an explicit contradiction remains unknown.
        # It is intentionally not turned into direct reuse, customization, or unavailable.
        if missing_data or missing_knowledge or missing_rules:
            return None

        if not self._confirmed_direct_reuse(process, [], asset, module):
            return None

        return self._decision(
            process, asset, module, "direct_reuse",
            rationale="core action is relevant and all declared module requirements are confirmed without customer-specific changes",
            matched=matched, gaps=approval_gaps, dependencies=dependencies, effort="none",
            human_review_required=human_review_required,
        )

    def _requirements(
        self, process: ProcessSpec, module: SolutionAssetModule
    ) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
        rule_facts = [constraint.statement for constraint in process.constraints] + list(process.available_data)
        missing_data = _missing(module.required_data, process.available_data)
        missing_knowledge = _missing(module.required_knowledge, process.available_data)
        missing_rules = _missing(module.required_rules, rule_facts)
        missing_systems = _missing(module.required_systems, process.existing_systems)
        missing_tools = _missing(module.required_tools, process.existing_systems)
        matched = (
            [f"data:{item}" for item in module.required_data if item not in missing_data]
            + [f"knowledge:{item}" for item in module.required_knowledge if item not in missing_knowledge]
            + [f"rule:{item}" for item in module.required_rules if item not in missing_rules]
            + [f"system:{item}" for item in module.required_systems if item not in missing_systems]
            + [f"tool:{item}" for item in module.required_tools if item not in missing_tools]
        )
        return matched, missing_data, missing_knowledge, missing_rules, _unique(missing_systems + missing_tools)

    def _configuration_changes(self, process: ProcessSpec, module: SolutionAssetModule) -> list[str]:
        customer_settings = list(process.available_data) + [
            constraint.statement for constraint in process.constraints
        ] + [node.name for node in process.as_is_nodes] + [node.description for node in process.as_is_nodes]
        return [
            f"configure:{item}"
            for item in module.configurable_items
            # Configuration is a customer fact only when the documented item is explicit.
            # A short lexical overlap such as "审查" is not enough to invent a setting.
            if item in customer_settings
        ]

    def _confirmed_direct_reuse(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        asset: SolutionAsset,
        module: SolutionAssetModule,
    ) -> bool:
        evidence_by_id = {item.evidence_id: item for item in asset.evidence}
        has_verified_module_evidence = any(
            evidence_by_id.get(ref) is not None and evidence_by_id[ref].verified
            for ref in module.evidence_refs
        )
        has_documented_capability = bool(module.capability_ids)
        return bool(
            self._strong_action_matches(process, genes, module)
            and has_verified_module_evidence
            and has_documented_capability
        )

    def _explicitly_unavailable(self, process: ProcessSpec, required_data: list[str]) -> list[str]:
        blocked: list[str] = []
        for constraint in process.constraints:
            if (
                constraint.hard
                and constraint.type == "data"
                and any(marker in constraint.statement.lower() for marker in _UNAVAILABLE_MARKERS)
            ):
                blocked.extend(item for item in required_data if _matched_terms([item], [constraint.statement]))
        return _unique(blocked)

    def _dependencies(self, asset: SolutionAsset, module: SolutionAssetModule) -> list[str]:
        dependencies = (
            [f"data:{item}" for item in module.required_data]
            + [f"knowledge:{item}" for item in module.required_knowledge]
            + [f"system:{item}" for item in module.required_systems]
            + [f"tool:{item}" for item in module.required_tools]
            + [f"rule:{item}" for item in module.required_rules]
        )
        dependencies.extend(self._lineage_dependencies(asset, module))
        return _unique(dependencies)

    def _lineage_dependencies(self, asset: SolutionAsset, module: SolutionAssetModule) -> list[str]:
        evidence_by_id = {item.evidence_id: item for item in asset.evidence}
        has_reuse_evidence = any(
            evidence_by_id.get(ref) is not None
            and evidence_by_id[ref].verified
            and evidence_by_id[ref].kind == "reuse_basis"
            for ref in module.evidence_refs
        )
        if not has_reuse_evidence:
            return []
        dependencies: list[str] = []
        for source_asset_id in asset.derived_from_asset_ids:
            source_asset = self._repository.get_asset(source_asset_id)
            for source_module in source_asset.modules:
                if set(module.capability_ids) & set(source_module.capability_ids):
                    dependencies.append(f"asset:{source_asset_id}/module:{source_module.module_id}")
        return dependencies

    def _human_review_required(self, process: ProcessSpec, module: SolutionAssetModule) -> bool:
        approval_required = any(
            constraint.hard and constraint.type == "approval" for constraint in process.constraints
        )
        return approval_required and bool(_HUMAN_REVIEW_CAPABILITIES & set(module.capability_ids))

    def _approval_gaps(self, process: ProcessSpec, module: SolutionAssetModule) -> list[str]:
        if self._human_review_required(process, module):
            return ["approval threshold compatibility requires confirmation"]
        return []

    def _decision(
        self,
        process: ProcessSpec,
        asset: SolutionAsset,
        module: SolutionAssetModule,
        mode: str,
        *,
        rationale: str,
        matched: list[str],
        gaps: list[str] | None = None,
        changes: list[str] | None = None,
        dependencies: list[str],
        risks: list[str] | None = None,
        effort: str,
        human_review_required: bool,
    ) -> ReuseDecision:
        return ReuseDecision(
            project_id=process.project_id,
            asset_id=asset.asset_id,
            module_id=module.module_id,
            decision=mode,
            rationale=rationale,
            matched_requirements=matched,
            gaps=gaps or [],
            required_changes=changes or [],
            dependencies=dependencies,
            risks=risks or [],
            estimated_effort=effort,
            human_review_required=human_review_required,
            evidence_refs=list(module.evidence_refs),
        )
