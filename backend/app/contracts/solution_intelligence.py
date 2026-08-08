from typing import Literal

from pydantic import Field, model_validator

from backend.app.contracts.common import StrictModel
from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import ComponentRef, WorkflowNode


SourceType = Literal[
    "official_solution",
    "official_case",
    "official_bluebook",
    "internal_material",
    "curated_fixture",
]
EvidenceKind = Literal[
    "asset_definition",
    "capability",
    "historical_outcome",
    "business_rule",
    "technical_requirement",
    "reuse_basis",
]
ExecutionMode = Literal["ai_autonomous", "ai_assisted", "human", "system"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ReuseMode = Literal[
    "direct_reuse",
    "configuration",
    "customization",
    "unavailable",
]
FitQuadrant = Literal["quick_win", "strategic", "experiment", "avoid"]
ValueClaimType = Literal["historical", "expected", "verified"]
_PLAN_STRATEGY = {
    "conservative": "quick_win",
    "balanced": "production_fit",
    "innovative": "transform",
}


class EvidenceRecord(StrictModel):
    evidence_id: str
    source_type: SourceType
    title: str
    document_name: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    kind: EvidenceKind
    statement: str
    verified: bool = False
    source_locator: str | None = None

    @model_validator(mode="after")
    def validate_page_range(self) -> "EvidenceRecord":
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_start is required when page_end is provided")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ValueClaim(StrictModel):
    claim_id: str
    claim_type: ValueClaimType
    metric_name: str
    value_text: str
    evidence_refs: list[str] = Field(default_factory=list)
    formula: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    run_report_id: str | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> "ValueClaim":
        if self.claim_type == "historical":
            if not self.evidence_refs:
                raise ValueError("historical ValueClaim requires evidence_refs")
            if self.run_report_id is not None:
                raise ValueError("historical ValueClaim must not have run_report_id")
        elif self.claim_type == "expected":
            if not self.formula or not self.formula.strip():
                raise ValueError("expected ValueClaim requires formula or calculation basis")
            if not self.assumptions:
                raise ValueError("expected ValueClaim requires assumptions")
            if self.run_report_id is not None:
                raise ValueError("expected ValueClaim must not have run_report_id")
        elif self.run_report_id is None or not self.run_report_id.strip():
            raise ValueError("verified ValueClaim requires run_report_id")
        return self


class SolutionAssetModule(StrictModel):
    module_id: str
    name: str
    description: str
    capability_ids: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    required_knowledge: list[str] = Field(default_factory=list)
    required_systems: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_rules: list[str] = Field(default_factory=list)
    configurable_items: list[str] = Field(default_factory=list)
    extension_points: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class AIGene(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    gene_id: str
    action_id: str | None = None
    action_name: str
    role: list[str] = Field(default_factory=list)
    object: list[str] = Field(default_factory=list)
    data_and_knowledge: list[str] = Field(default_factory=list)
    technology: list[str] = Field(default_factory=list)
    standards_and_rules: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    execution_mode: ExecutionMode
    risk_level: RiskLevel = "medium"
    evidence_refs: list[str] = Field(default_factory=list)


class AssetCandidate(StrictModel):
    """A retrieval-stage candidate, not a final solution recommendation."""

    asset_id: str
    retrieval_score: float = Field(ge=0, le=100)
    matched_terms: list[str] = Field(default_factory=list)
    matched_gene_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class HardGateResult(StrictModel):
    gate_id: str
    category: Literal[
        "security",
        "deployment",
        "data",
        "system",
        "rule",
        "budget",
        "time",
        "risk",
    ]
    passed: bool
    reason: str = Field(min_length=1)
    constraint_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FitDimensionScore(StrictModel):
    name: Literal[
        "role",
        "object",
        "data_knowledge",
        "rules",
        "tools_systems",
        "technology",
        "evidence",
    ]
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    explanation: str = Field(min_length=1)


class FitAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    asset_id: str
    eligible: bool
    hard_gates: list[HardGateResult]
    dimensions: list[FitDimensionScore]
    raw_fit_score: float = Field(ge=0, le=100)
    effective_fit_score: float | None = Field(default=None, ge=0, le=100)
    business_value_score: float = Field(ge=0, le=100)
    implementation_difficulty_score: float = Field(ge=0, le=100)
    quadrant: FitQuadrant
    matched_action_ids: list[str] = Field(default_factory=list)
    unmatched_action_ids: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    soft_gaps: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_eligibility_score(self) -> "FitAssessment":
        if self.eligible and self.effective_fit_score is None:
            raise ValueError("eligible FitAssessment requires effective_fit_score")
        if not self.eligible and self.effective_fit_score is not None:
            raise ValueError("blocked FitAssessment must not have effective_fit_score")
        return self


class ReuseDecision(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    asset_id: str
    module_id: str = Field(min_length=1)
    decision: ReuseMode
    rationale: str = Field(min_length=1)
    matched_requirements: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    estimated_effort: Literal["none", "small", "medium", "large", "unknown"]
    human_review_required: bool = False
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rationale(self) -> "ReuseDecision":
        if not self.rationale.strip():
            raise ValueError("reuse decision rationale must not be blank")
        return self


class ReuseSummary(StrictModel):
    direct_reuse_count: int = Field(ge=0)
    configuration_count: int = Field(ge=0)
    customization_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    direct_reuse_ratio: float = Field(ge=0, le=1)
    configuration_ratio: float = Field(ge=0, le=1)
    customization_ratio: float = Field(ge=0, le=1)
    unavailable_ratio: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_aggregate(self) -> "ReuseSummary":
        counts = (
            self.direct_reuse_count
            + self.configuration_count
            + self.customization_count
            + self.unavailable_count
        )
        if counts == 0:
            raise ValueError("reuse summary requires at least one decision")
        ratios = (
            self.direct_reuse_ratio,
            self.configuration_ratio,
            self.customization_ratio,
            self.unavailable_ratio,
        )
        if abs(sum(ratios) - 1.0) >= 1e-6:
            raise ValueError("reuse summary ratios must sum to 1")
        expected = (
            self.direct_reuse_count / counts,
            self.configuration_count / counts,
            self.customization_count / counts,
            self.unavailable_count / counts,
        )
        if any(abs(actual - target) >= 1e-6 for actual, target in zip(ratios, expected)):
            raise ValueError("reuse summary ratios must match counts")
        return self


class SolutionPlanV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    solution_id: str
    source_project_id: str
    plan_type: Literal["conservative", "balanced", "innovative"]
    display_strategy: Literal["quick_win", "production_fit", "transform"]
    name: str
    summary: str
    primary_asset_ids: list[str]
    supporting_asset_ids: list[str] = Field(default_factory=list)
    fit_assessments: list[FitAssessment]
    reuse_decisions: list[ReuseDecision]
    reuse_summary: ReuseSummary
    selected_components: list[ComponentRef]
    to_be_nodes: list[WorkflowNode]
    applied_constraints: list[BusinessConstraint]
    data_requirements: list[str] = Field(default_factory=list)
    knowledge_requirements: list[str] = Field(default_factory=list)
    system_integrations: list[str] = Field(default_factory=list)
    implementation_steps: list[str]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    value_claims: list[ValueClaim] = Field(default_factory=list)
    demo_blueprint_id: str | None = None
    review_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_executable_selection(self) -> "SolutionPlanV2":
        if not self.primary_asset_ids or not self.reuse_decisions or not self.implementation_steps:
            raise ValueError("v2 plan requires selected assets, reuse decisions, and implementation steps")
        if self.display_strategy != _PLAN_STRATEGY[self.plan_type]:
            raise ValueError("display_strategy must match the fixed plan_type mapping")
        if any(item.decision == "unavailable" for item in self.reuse_decisions):
            raise ValueError("unavailable reuse decision cannot be executable")
        if any(item.project_id != self.source_project_id for item in self.reuse_decisions):
            raise ValueError("reuse decisions must belong to source_project_id")
        if any(item.project_id != self.source_project_id for item in self.fit_assessments):
            raise ValueError("fit assessments must belong to source_project_id")
        if len({(item.asset_id, item.module_id) for item in self.reuse_decisions}) != len(self.reuse_decisions):
            raise ValueError("reuse decisions must have unique asset/module values per plan")
        plan_asset_ids = set(self.primary_asset_ids + self.supporting_asset_ids)
        if any(item.asset_id not in plan_asset_ids for item in self.reuse_decisions):
            raise ValueError("reuse decisions must reference plan assets")
        if any(item.asset_id not in plan_asset_ids for item in self.fit_assessments):
            raise ValueError("fit assessments must reference plan assets")
        component_ids = {item.component_id for item in self.selected_components}
        executable_component_ids = {
            f"{item.asset_id}:{item.module_id}" for item in self.reuse_decisions
        }
        if component_ids != executable_component_ids:
            raise ValueError("selected components must exactly match executable reuse decisions")
        if any(node.component_id not in component_ids for node in self.to_be_nodes):
            raise ValueError("workflow nodes must reference selected components")
        counts = {
            mode: sum(item.decision == mode for item in self.reuse_decisions)
            for mode in ("direct_reuse", "configuration", "customization", "unavailable")
        }
        if (
            self.reuse_summary.direct_reuse_count != counts["direct_reuse"]
            or self.reuse_summary.configuration_count != counts["configuration"]
            or self.reuse_summary.customization_count != counts["customization"]
            or self.reuse_summary.unavailable_count != counts["unavailable"]
        ):
            raise ValueError("reuse_summary counts must exactly aggregate reuse decisions")
        return self


class SolutionBundleV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: str
    recommended_solution_id: str
    plans: list[SolutionPlanV2]
    retrieval_asset_ids: list[str]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bundle(self) -> "SolutionBundleV2":
        if len(self.plans) != 3 or {plan.plan_type for plan in self.plans} != {"conservative", "balanced", "innovative"}:
            raise ValueError("v2 bundle requires exactly conservative, balanced, and innovative plans")
        if len({plan.solution_id for plan in self.plans}) != 3:
            raise ValueError("v2 solution_id values must be unique")
        if self.recommended_solution_id not in {plan.solution_id for plan in self.plans}:
            raise ValueError("recommended_solution_id must reference a plan")
        if any(plan.source_project_id != self.project_id for plan in self.plans):
            raise ValueError("all plans must belong to bundle project_id")
        retrieved_asset_ids = set(self.retrieval_asset_ids)
        if any(
            not set(plan.primary_asset_ids + plan.supporting_asset_ids) <= retrieved_asset_ids
            for plan in self.plans
        ):
            raise ValueError("plan assets must be present in retrieval_asset_ids")
        if any(
            not {fit.asset_id for fit in plan.fit_assessments} <= retrieved_asset_ids
            for plan in self.plans
        ):
            raise ValueError("fit assessments must be present in retrieval_asset_ids")
        return self


class DemoInput(StrictModel):
    name: str
    type: str
    required: bool = True
    description: str
    fixture_ref: str | None = None


class DemoAssertion(StrictModel):
    assertion_id: str
    description: str
    severity: Literal["info", "warning", "blocking"]
    metric_name: str | None = None
    expected_condition: str


class DemoNode(StrictModel):
    id: str
    name: str
    node_type: Literal[
        "retrieval", "transform", "llm", "rule", "tool", "human_gate", "report"
    ]
    executor: Literal["ai", "human", "system"]
    component_id: str | None = None
    asset_module_id: str | None = None
    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)
    next_ids: list[str] = Field(default_factory=list)
    human_gate: bool = False
    gate_reason: str | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    fallback_node_id: str | None = None


class DemoBlueprint(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    demo_id: str
    project_id: str
    solution_id: str
    title: str
    objective: str
    source_asset_ids: list[str]
    inputs: list[DemoInput]
    nodes: list[DemoNode]
    expected_outputs: list[str]
    metric_names: list[str]
    assertions: list[DemoAssertion]
    required_integrations: list[str] = Field(default_factory=list)
    security_requirements: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "DemoBlueprint":
        input_names = [item.name for item in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("DemoInput name values must be unique")
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("DemoNode id values must be unique")
        if not node_ids:
            raise ValueError("DemoBlueprint requires at least one node")

        node_id_set = set(node_ids)
        for node in self.nodes:
            if not set(node.next_ids) <= node_id_set:
                raise ValueError("DemoNode next_ids must reference existing nodes")
            if node.fallback_node_id is not None and node.fallback_node_id not in node_id_set:
                raise ValueError("DemoNode fallback_node_id must reference an existing node")
            if node.human_gate and node.executor != "human" and node.node_type != "human_gate":
                raise ValueError("human_gate requires a human executor or human_gate node_type")
            if node.human_gate and not node.gate_reason:
                raise ValueError("human_gate requires gate_reason")

        edges = {
            node.id: list(node.next_ids)
            + ([node.fallback_node_id] if node.fallback_node_id is not None else [])
            for node in self.nodes
        }
        reverse_edges = {node_id: [] for node_id in node_ids}
        for source, targets in edges.items():
            for target in targets:
                reverse_edges[target].append(source)
        starts = [node_id for node_id in node_ids if not reverse_edges[node_id]]
        if not starts:
            raise ValueError("DemoBlueprint graph requires at least one start node")
        terminals = [node_id for node_id in node_ids if not edges[node_id]]
        if not terminals:
            raise ValueError("DemoBlueprint graph requires at least one terminal node")

        reachable = _graph_reachable(starts, edges)
        if reachable != node_id_set:
            raise ValueError("DemoBlueprint graph contains unreachable node")
        terminal_reachable = _graph_reachable(terminals, reverse_edges)
        if terminal_reachable != node_id_set:
            raise ValueError("DemoBlueprint graph contains a closed infinite cycle")

        input_name_set = set(input_names)
        output_sources: dict[str, str] = {}
        for node in self.nodes:
            for output_key in node.output_keys:
                if output_key in output_sources:
                    raise ValueError("DemoNode output_keys must have unique producers")
                output_sources[output_key] = node.id
        for node in self.nodes:
            ancestor_ids = _graph_reachable(reverse_edges[node.id], reverse_edges)
            available_keys = input_name_set | {
                output_key
                for output_key, producer in output_sources.items()
                if producer in ancestor_ids
            }
            if not set(node.input_keys) <= available_keys:
                raise ValueError("DemoNode input_keys must reference DemoInput or upstream output_keys")
        return self


class SolutionIntelligenceDiff(StrictModel):
    changed_asset_ids: list[str] = Field(default_factory=list)
    changed_fit_asset_ids: list[str] = Field(default_factory=list)
    changed_module_ids: list[str] = Field(default_factory=list)
    reuse_mode_changes: dict[str, str] = Field(default_factory=dict)
    added_demo_node_ids: list[str] = Field(default_factory=list)
    removed_demo_node_ids: list[str] = Field(default_factory=list)
    changed_demo_node_ids: list[str] = Field(default_factory=list)
    value_claim_changes: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)


class RecompileSolutionV2Request(StrictModel):
    process: ProcessSpec
    selected_solution: SolutionPlanV2
    selected_blueprint: DemoBlueprint
    new_constraints: list[BusinessConstraint]

    @model_validator(mode="after")
    def validate_cross_object_closure(self) -> "RecompileSolutionV2Request":
        if self.process.project_id != self.selected_solution.source_project_id:
            raise ValueError("process.project_id must match selected_solution.source_project_id")
        if self.selected_blueprint.project_id != self.process.project_id:
            raise ValueError("selected_blueprint.project_id must match process.project_id")
        if self.selected_blueprint.solution_id != self.selected_solution.solution_id:
            raise ValueError("selected_blueprint.solution_id must match selected_solution.solution_id")
        expected_assets = list(dict.fromkeys(
            self.selected_solution.primary_asset_ids + self.selected_solution.supporting_asset_ids
        ))
        if self.selected_blueprint.source_asset_ids != expected_assets:
            raise ValueError("selected_blueprint.source_asset_ids must match selected solution assets")
        return self


class RecompileSolutionV2Result(StrictModel):
    previous_solution_id: str
    previous_demo_id: str
    new_solution: SolutionPlanV2
    new_blueprint: DemoBlueprint
    diff: SolutionIntelligenceDiff

    @model_validator(mode="after")
    def validate_cross_object_closure(self) -> "RecompileSolutionV2Result":
        if self.new_solution.source_project_id != self.new_blueprint.project_id:
            raise ValueError("new solution and Blueprint project_id must match")
        if self.new_blueprint.solution_id != self.new_solution.solution_id:
            raise ValueError("new Blueprint solution_id must match new solution")
        expected_assets = list(dict.fromkeys(
            self.new_solution.primary_asset_ids + self.new_solution.supporting_asset_ids
        ))
        if self.new_blueprint.source_asset_ids != expected_assets:
            raise ValueError("new Blueprint source_asset_ids must match new solution assets")
        return self


def _graph_reachable(start_ids: list[str], edges: dict[str, list[str]]) -> set[str]:
    visited: set[str] = set()
    pending = list(start_ids)
    while pending:
        node_id = pending.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        pending.extend(edges[node_id])
    return visited


class SolutionAsset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    asset_id: str
    name: str
    version: str
    provider: str
    source_type: SourceType
    industries: list[str]
    value_chains: list[str] = Field(default_factory=list)
    processes: list[str]
    scenarios: list[str]
    target_roles: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    action_genes: list[AIGene] = Field(default_factory=list)
    modules: list[SolutionAssetModule]
    supported_data: list[str] = Field(default_factory=list)
    supported_knowledge: list[str] = Field(default_factory=list)
    supported_systems: list[str] = Field(default_factory=list)
    supported_deployments: list[str] = Field(default_factory=list)
    standards_and_rules: list[str] = Field(default_factory=list)
    security_characteristics: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord]
    value_claims: list[ValueClaim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    derived_from_asset_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "SolutionAsset":
        module_ids = [module.module_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("module_id values must be unique within an asset")

        evidence_ids = [evidence.evidence_id for evidence in self.evidence]
        evidence_id_set = set(evidence_ids)
        if len(evidence_ids) != len(evidence_id_set):
            raise ValueError("evidence_id values must be unique within an asset")

        for module in self.modules:
            missing = set(module.evidence_refs) - evidence_id_set
            if missing:
                raise ValueError(
                    f"module {module.module_id} references unknown evidence: {sorted(missing)}"
                )
        for gene in self.action_genes:
            missing = set(gene.evidence_refs) - evidence_id_set
            if missing:
                raise ValueError(
                    f"gene {gene.gene_id} references unknown evidence: {sorted(missing)}"
                )
        for claim in self.value_claims:
            missing = set(claim.evidence_refs) - evidence_id_set
            if missing:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown evidence: {sorted(missing)}"
                )
        return self
