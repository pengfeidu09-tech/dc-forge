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
