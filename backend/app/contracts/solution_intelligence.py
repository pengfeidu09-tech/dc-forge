from typing import Literal

from pydantic import Field, model_validator

from backend.app.contracts.common import StrictModel


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
