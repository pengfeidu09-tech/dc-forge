"""Deterministic B-M8.3 asset-fit assessment; it makes no reuse decisions."""

from __future__ import annotations

from collections.abc import Iterable

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import (
    AIGene,
    FitAssessment,
    FitDimensionScore,
    HardGateResult,
    SolutionAsset,
)
from backend.app.solution.asset_retriever import _matched_terms


FIT_WEIGHTS: dict[str, float] = {
    "role": 0.10,
    "object": 0.10,
    "data_knowledge": 0.20,
    "rules": 0.20,
    "tools_systems": 0.15,
    "technology": 0.15,
    "evidence": 0.10,
}
# Unknown is deliberately conservative: it is neither a confirmed match nor a conflict.
UNKNOWN_DIMENSION_SCORE = 20.0
UNKNOWN_DIFFICULTY_SCORE = 50.0
HIGH_VALUE_THRESHOLD = 60.0
HIGH_DIFFICULTY_THRESHOLD = 60.0

_OFFICIAL_SOURCE_TYPES = {"official_solution", "official_case", "official_bluebook"}
_PRIVATE_MARKERS = ("私有", "本地", "不出域", "不得出域", "禁止公网", "禁止外传")
_PUBLIC_MARKERS = ("public", "saas", "公网", "公有")
_UNAVAILABLE_MARKERS = ("不可获得", "无法获得", "无法提供", "不可用", "禁止使用", "不存在")


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _module_values(asset: SolutionAsset, field_name: str) -> list[str]:
    return [value for module in asset.modules for value in getattr(module, field_name)]


def _asset_action_terms(asset: SolutionAsset) -> list[str]:
    return list(asset.processes) + [module.name for module in asset.modules] + [
        gene.action_name for gene in asset.action_genes
    ]


def _asset_evidence_refs(asset: SolutionAsset) -> list[str]:
    return [evidence.evidence_id for evidence in asset.evidence]


def _contains_marker(values: Iterable[str], markers: tuple[str, ...]) -> bool:
    text = " ".join(values).lower()
    return any(marker in text for marker in markers)


def _result(status: str, score: float, explanation: str) -> tuple[float, str, str]:
    return score, f"{status}: {explanation}", status


def _coverage_score(
    customer_values: list[str], asset_values: list[str], label: str
) -> tuple[float, str, str]:
    if not customer_values or not asset_values:
        return _result("UNKNOWN", UNKNOWN_DIMENSION_SCORE, f"{label}: insufficient information for a confirmed match")
    matched = _matched_terms(asset_values, customer_values)
    if not matched:
        return _result("MISMATCH", 0.0, f"{label}: no normalized overlap")
    score = min(100.0, 60.0 + 10.0 * len(matched))
    return _result("MATCH", score, f"{label}: matched {', '.join(matched)}")


def _requirement_gap(
    required: list[str], available: list[str], *, unknown_score: float = UNKNOWN_DIFFICULTY_SCORE
) -> tuple[float, list[str]]:
    if not required:
        return unknown_score, []
    missing = [item for item in required if not _matched_terms([item], available)]
    return round(100.0 * len(missing) / len(required), 2), missing


class FitEngine:
    """Assess one retrieved asset with deterministic hard gates and fit dimensions."""

    def assess(self, process: ProcessSpec, genes: list[AIGene], asset: SolutionAsset) -> FitAssessment:
        soft_gaps: list[str] = []
        hard_gates = self._evaluate_hard_gates(process, asset, soft_gaps)
        matched_action_ids, unmatched_action_ids = self._action_coverage(process, asset)
        dimensions = self._dimensions(process, genes, asset, matched_action_ids, soft_gaps)
        raw_fit_score = round(sum(item.score * item.weight for item in dimensions), 2)
        hard_blockers = [gate.reason for gate in hard_gates if not gate.passed]
        eligible = not hard_blockers
        business_value_score = self._business_value(process, asset, matched_action_ids)
        difficulty_score = self._difficulty(process, asset, matched_action_ids, hard_gates, soft_gaps)

        return FitAssessment(
            project_id=process.project_id,
            asset_id=asset.asset_id,
            eligible=eligible,
            hard_gates=hard_gates,
            dimensions=dimensions,
            raw_fit_score=raw_fit_score,
            effective_fit_score=raw_fit_score if eligible else None,
            business_value_score=business_value_score,
            implementation_difficulty_score=difficulty_score,
            quadrant=self._quadrant(business_value_score, difficulty_score),
            matched_action_ids=matched_action_ids,
            unmatched_action_ids=unmatched_action_ids,
            hard_blockers=hard_blockers,
            soft_gaps=_unique(soft_gaps),
            explanation=(
                f"{asset.asset_id}: {len(matched_action_ids)}/{len(process.as_is_nodes)} customer "
                f"actions have deterministic lexical overlap; hard gates {'passed' if eligible else 'blocked'}"
            ),
            evidence_refs=_asset_evidence_refs(asset),
        )

    def _evaluate_hard_gates(
        self, process: ProcessSpec, asset: SolutionAsset, soft_gaps: list[str]
    ) -> list[HardGateResult]:
        gates: list[HardGateResult] = []
        for constraint in process.constraints:
            if not constraint.hard:
                continue
            if constraint.type == "security":
                gates.append(self._deployment_gate(constraint.id, constraint.statement, asset, soft_gaps))
            elif constraint.type == "data":
                gates.append(self._data_gate(constraint.id, constraint.statement, asset, soft_gaps))
            elif constraint.type == "approval":
                gates.append(self._approval_gate(constraint.id, asset, soft_gaps))
            elif constraint.type in {"budget", "time", "risk"}:
                gates.append(self._unknown_gate(constraint.id, constraint.type, soft_gaps))
        return gates

    def _deployment_gate(
        self, constraint_id: str, statement: str, asset: SolutionAsset, soft_gaps: list[str]
    ) -> HardGateResult:
        requires_private = _contains_marker([statement], _PRIVATE_MARKERS)
        deployments = list(asset.supported_deployments) + list(asset.security_characteristics)
        if not requires_private:
            return HardGateResult(gate_id=f"security:{constraint_id}", category="security", passed=True,
                reason="security constraint has no explicit deployment requirement", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))
        if deployments and _contains_marker(deployments, _PRIVATE_MARKERS):
            return HardGateResult(gate_id=f"deployment:{constraint_id}", category="deployment", passed=True,
                reason="asset explicitly declares compatible private or local deployment support", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))
        if deployments and _contains_marker(deployments, _PUBLIC_MARKERS):
            return HardGateResult(gate_id=f"deployment:{constraint_id}", category="deployment", passed=False,
                reason="asset explicitly declares public-only deployment incompatible with private requirement", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))
        soft_gaps.append("deployment/security compatibility not confirmed")
        return HardGateResult(gate_id=f"deployment:{constraint_id}", category="deployment", passed=True,
            reason="deployment support is insufficiently specified; no explicit contradiction established", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))

    def _data_gate(
        self, constraint_id: str, statement: str, asset: SolutionAsset, soft_gaps: list[str]
    ) -> HardGateResult:
        required_data = _module_values(asset, "required_data")
        unavailable_required = [item for item in required_data if _matched_terms([item], [statement])]
        if _contains_marker([statement], _UNAVAILABLE_MARKERS) and unavailable_required:
            return HardGateResult(gate_id=f"data:{constraint_id}", category="data", passed=False,
                reason=f"required data explicitly unavailable: {', '.join(unavailable_required)}", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))
        if required_data:
            soft_gaps.append("required data availability not confirmed")
        return HardGateResult(gate_id=f"data:{constraint_id}", category="data", passed=True,
            reason="no explicit required-data contradiction established", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))

    def _approval_gate(self, constraint_id: str, asset: SolutionAsset, soft_gaps: list[str]) -> HardGateResult:
        has_human_support = any("human-approval" in module.capability_ids for module in asset.modules) or any(
            gene.execution_mode == "human" for gene in asset.action_genes
        )
        if has_human_support:
            return HardGateResult(gate_id=f"rule:{constraint_id}", category="rule", passed=True,
                reason="asset explicitly includes human review or approval capability", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))
        soft_gaps.append("approval and human-review compatibility not confirmed")
        return HardGateResult(gate_id=f"rule:{constraint_id}", category="rule", passed=True,
            reason="asset does not explicitly establish approval incompatibility", constraint_ids=[constraint_id], evidence_refs=_asset_evidence_refs(asset))

    def _unknown_gate(self, constraint_id: str, category: str, soft_gaps: list[str]) -> HardGateResult:
        soft_gaps.append(f"{category} compatibility requires structured estimate or explicit asset fact")
        return HardGateResult(gate_id=f"{category}:{constraint_id}", category=category, passed=True,
            reason=f"{category} has no structured contradiction evidence in the current asset contract", constraint_ids=[constraint_id], evidence_refs=[])

    def _action_coverage(self, process: ProcessSpec, asset: SolutionAsset) -> tuple[list[str], list[str]]:
        asset_terms = _asset_action_terms(asset)
        matched = [node.id for node in process.as_is_nodes if _matched_terms(asset_terms, [node.name, node.description])]
        return matched, [node.id for node in process.as_is_nodes if node.id not in matched]

    def _rules_dimension(
        self, process: ProcessSpec, customer_rules: list[str], asset: SolutionAsset
    ) -> tuple[float, str, str]:
        asset_rules = list(asset.standards_and_rules) + _module_values(asset, "required_rules") + [
            value for gene in asset.action_genes for value in gene.standards_and_rules
        ]
        rule_intent = customer_rules + [node.name for node in process.as_is_nodes] + [
            node.description for node in process.as_is_nodes
        ]
        confirmed_rule_values = list(asset.standards_and_rules) + _module_values(
            asset, "configurable_items"
        ) + [value for gene in asset.action_genes for value in gene.standards_and_rules]
        direct = [
            term
            for term in _matched_terms(confirmed_rule_values, rule_intent)
            if term not in {"规则", "审查"}
        ]
        capabilities = {capability for module in asset.modules for capability in module.capability_ids}
        configurable = _module_values(asset, "configurable_items")
        has_rule_accommodation = "rule-engine" in capabilities and bool(configurable or asset_rules)
        has_human_approval = "human-approval" in capabilities or any(
            gene.execution_mode == "human" for gene in asset.action_genes
        )
        approval_required = any(constraint.type == "approval" for constraint in process.constraints)
        if approval_required and has_human_approval:
            return _result("PARTIAL", 70.0, "rules: human approval is supported, but the exact customer threshold is not evidenced")
        if direct:
            return _result("MATCH", min(100.0, 70.0 + 10.0 * len(direct)), f"rules: matched {', '.join(direct)}")
        if not customer_rules:
            return _result("UNKNOWN", UNKNOWN_DIMENSION_SCORE, "rules: insufficient information for a confirmed match")
        if has_rule_accommodation:
            return _result("PARTIAL", 55.0, "rules: rule engine or configurable rules can accommodate a rule, but no exact customer rule is evidenced")
        if asset_rules or capabilities:
            return _result("MISMATCH", 0.0, "rules: asset declares no compatible rule accommodation")
        return _result("UNKNOWN", UNKNOWN_DIMENSION_SCORE, "rules: insufficient information for a confirmed match")

    def _supporting_evidence_refs(
        self, process: ProcessSpec, asset: SolutionAsset, matched_action_ids: list[str]
    ) -> list[str]:
        matched_nodes = [node for node in process.as_is_nodes if node.id in matched_action_ids]
        refs: list[str] = []
        for node in matched_nodes:
            action_terms = [node.name, node.description]
            for module in asset.modules:
                if _matched_terms([module.name, module.description], action_terms):
                    refs.extend(module.evidence_refs)
            for gene in asset.action_genes:
                if gene.action_id == node.id or _matched_terms([gene.action_name], action_terms):
                    refs.extend(gene.evidence_refs)
        return _unique(refs)

    def _evidence_dimension(
        self, process: ProcessSpec, asset: SolutionAsset, matched_action_ids: list[str]
    ) -> tuple[float, str, str]:
        evidence_by_id = {evidence.evidence_id: evidence for evidence in asset.evidence}
        supporting_refs = self._supporting_evidence_refs(process, asset, matched_action_ids)
        supported = [evidence_by_id[ref] for ref in supporting_refs if ref in evidence_by_id]
        if any(e.verified and e.source_type in _OFFICIAL_SOURCE_TYPES for e in supported):
            return _result("MATCH", 100.0, "evidence: verified official evidence supports a matched action")
        if any(e.verified for e in supported):
            return _result("PARTIAL", 25.0, "evidence: only verified non-official evidence supports a matched action")
        if supported:
            return _result("PARTIAL", 10.0, "evidence: only unverified evidence supports a matched action")
        if asset.evidence:
            return _result("UNKNOWN", UNKNOWN_DIMENSION_SCORE, "evidence: asset evidence exists but does not support the current matched action")
        return _result("MISMATCH", 0.0, "evidence: no asset evidence available")

    def _dimensions(
        self, process: ProcessSpec, genes: list[AIGene], asset: SolutionAsset,
        matched_action_ids: list[str], soft_gaps: list[str]
    ) -> list[FitDimensionScore]:
        customer_roles = list(process.roles) + [role for gene in genes for role in gene.role]
        asset_roles = list(asset.target_roles) + [role for gene in asset.action_genes for role in gene.role]
        customer_objects = [value for gene in genes for value in gene.object]
        asset_objects = [value for gene in asset.action_genes for value in gene.object]
        customer_data = list(process.available_data) + [value for gene in genes for value in gene.data_and_knowledge]
        asset_data = list(asset.supported_data) + list(asset.supported_knowledge) + _module_values(asset, "required_data") + _module_values(asset, "required_knowledge") + [value for gene in asset.action_genes for value in gene.data_and_knowledge]
        customer_rules = [constraint.statement for constraint in process.constraints] + [value for gene in genes for value in gene.standards_and_rules]
        customer_tools = list(process.existing_systems) + [tool for gene in genes for tool in gene.tools]
        asset_tools = list(asset.supported_systems) + _module_values(asset, "required_systems") + _module_values(asset, "required_tools") + [tool for gene in asset.action_genes for tool in gene.tools]
        customer_technology = [value for gene in genes for value in gene.technology]
        asset_technology = [value for gene in asset.action_genes for value in gene.technology]

        values = {
            "role": _coverage_score(customer_roles, asset_roles, "role"),
            "object": _coverage_score(customer_objects, asset_objects, "object"),
            "data_knowledge": _coverage_score(customer_data, asset_data, "data and knowledge"),
            "rules": self._rules_dimension(process, customer_rules, asset),
            "tools_systems": _coverage_score(customer_tools, asset_tools, "tools and systems"),
            "technology": _coverage_score(customer_technology, asset_technology, "technology"),
            "evidence": self._evidence_dimension(process, asset, matched_action_ids),
        }
        if not asset_tools:
            soft_gaps.append("connector availability not confirmed")
        _, missing_data = _requirement_gap(_module_values(asset, "required_data"), process.available_data)
        if missing_data:
            soft_gaps.append("required data not confirmed: " + ", ".join(missing_data))
        required_systems = _module_values(asset, "required_systems") + _module_values(asset, "required_tools")
        _, missing_systems = _requirement_gap(required_systems, process.existing_systems)
        if missing_systems:
            soft_gaps.append("required systems not confirmed: " + ", ".join(missing_systems))
        if not customer_technology:
            soft_gaps.append("customer technology requirement unknown")
        return [FitDimensionScore(name=name, score=values[name][0], weight=FIT_WEIGHTS[name], explanation=values[name][1]) for name in FIT_WEIGHTS]

    def _business_value(self, process: ProcessSpec, asset: SolutionAsset, matched_action_ids: list[str]) -> float:
        action_coverage = 100.0 * len(matched_action_ids) / len(process.as_is_nodes) if process.as_is_nodes else UNKNOWN_DIMENSION_SCORE
        asset_terms = _asset_action_terms(asset) + list(asset.scenarios) + list(asset.pain_points)
        goal_alignment = 100.0 if _matched_terms(asset_terms, [process.business_goal]) else 0.0
        if not process.pain_points:
            pain_score = UNKNOWN_DIMENSION_SCORE
        else:
            severity = {"low": 33.0, "medium": 66.0, "high": 100.0}
            pain_score = sum(severity[pain.severity] if any(node_id in matched_action_ids for node_id in pain.affected_node_ids) else 0.0 for pain in process.pain_points) / len(process.pain_points)
        metric_score = 100.0 if _matched_terms(asset_terms, process.target_metrics) else 0.0 if process.target_metrics else UNKNOWN_DIMENSION_SCORE
        evidence_by_id = {evidence.evidence_id: evidence for evidence in asset.evidence}
        historical_strength = 100.0 if any(claim.claim_type == "historical" and all(evidence_by_id[ref].verified and evidence_by_id[ref].source_type in _OFFICIAL_SOURCE_TYPES for ref in claim.evidence_refs) for claim in asset.value_claims) else 0.0
        return round(0.30 * goal_alignment + 0.25 * pain_score + 0.20 * metric_score + 0.15 * historical_strength + 0.10 * action_coverage, 2)

    def _difficulty(self, process: ProcessSpec, asset: SolutionAsset, matched_action_ids: list[str], hard_gates: list[HardGateResult], soft_gaps: list[str]) -> float:
        data_gap, _ = _requirement_gap(_module_values(asset, "required_data"), process.available_data)
        system_gap, _ = _requirement_gap(_module_values(asset, "required_systems") + _module_values(asset, "required_tools"), process.existing_systems)
        rule_gap, _ = _requirement_gap(_module_values(asset, "required_rules"), [constraint.statement for constraint in process.constraints])
        if any(not gate.passed and gate.category == "deployment" for gate in hard_gates):
            deployment_gap = 100.0
        elif any("deployment/security compatibility not confirmed" in gap for gap in soft_gaps):
            deployment_gap = UNKNOWN_DIFFICULTY_SCORE
        else:
            deployment_gap = 0.0
        customization_proxy = 100.0 * (1.0 - len(matched_action_ids) / len(process.as_is_nodes)) if process.as_is_nodes else UNKNOWN_DIFFICULTY_SCORE
        return round(0.25 * data_gap + 0.20 * system_gap + 0.20 * rule_gap + 0.20 * deployment_gap + 0.15 * customization_proxy, 2)

    def _quadrant(self, value: float, difficulty: float) -> str:
        if value >= HIGH_VALUE_THRESHOLD and difficulty < HIGH_DIFFICULTY_THRESHOLD:
            return "quick_win"
        if value >= HIGH_VALUE_THRESHOLD and difficulty >= HIGH_DIFFICULTY_THRESHOLD:
            return "strategic"
        if value < HIGH_VALUE_THRESHOLD and difficulty < HIGH_DIFFICULTY_THRESHOLD:
            return "experiment"
        return "avoid"
