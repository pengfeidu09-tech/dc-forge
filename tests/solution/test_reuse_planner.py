import pytest
from pydantic import ValidationError

from backend.app.contracts.solution_intelligence import (
    EvidenceRecord,
    ReuseDecision,
    ReuseSummary,
    SolutionAsset,
    SolutionAssetModule,
)
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.asset_retriever import AssetRetriever
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.gene_builder import GeneBuilder
from backend.app.solution.reuse_planner import ReusePlanner
from tests.solution.test_asset_retriever import _process, _procurement_process


def _process_spec(
    *,
    data: list[str] | None = None,
    systems: list[str] | None = None,
    constraints: list[dict] | None = None,
) -> object:
    process = _process(
        project_id="reuse-planner-test",
        industry="manufacturing",
        node_name="procurement review",
        node_description="review procurement document",
        business_goal="review procurement document",
        available_data=data or [],
        constraints=constraints or [],
        roles=["buyer"],
        actor="buyer",
    )
    return process.model_copy(update={"existing_systems": systems or ["OA"]})


def _module(
    module_id: str,
    *,
    required_data: list[str] | None = None,
    required_rules: list[str] | None = None,
    required_systems: list[str] | None = None,
    configurable_items: list[str] | None = None,
    capability_ids: list[str] | None = None,
) -> SolutionAssetModule:
    return SolutionAssetModule(
        module_id=module_id,
        name="procurement review",
        description="review procurement document",
        required_data=required_data or [],
        required_rules=required_rules or [],
        required_systems=required_systems or [],
        configurable_items=configurable_items or [],
        capability_ids=capability_ids if capability_ids is not None else ["document-extraction"],
        evidence_refs=["test-evidence"],
    )


def _asset(
    modules: list[SolutionAssetModule], *, deployments: list[str] | None = None
) -> SolutionAsset:
    return SolutionAsset(
        asset_id="reuse-test-asset",
        name="Reuse test asset",
        version="1.0",
        provider="Test provider",
        source_type="official_case",
        industries=["manufacturing"],
        processes=["procurement review"],
        scenarios=["procurement review"],
        modules=modules,
        supported_deployments=deployments or [],
        evidence=[
            EvidenceRecord(
                evidence_id="test-evidence",
                source_type="official_case",
                title="Test evidence",
                document_name="test-case.pdf",
                page_start=1,
                page_end=1,
                kind="capability",
                statement="Verified module capability.",
                verified=True,
            )
        ],
    )


def _plan(process, asset: SolutionAsset):
    genes = GeneBuilder().build_from_process(process)
    fit = FitEngine().assess(process, genes, asset)
    return ReusePlanner(AssetRepository()).plan(process, genes, asset, fit)


def test_planner_is_deterministic_and_decisions_are_closed_over_asset() -> None:
    process = _process_spec(data=["customer-data"])
    asset = _asset([_module("direct", required_data=["customer-data"])])

    first = _plan(process, asset)
    second = _plan(process, asset)
    evidence_ids = {item.evidence_id for item in asset.evidence}

    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
    assert [item.module_id for item in first] == ["direct"]
    assert all(item.rationale for item in first)
    assert all(set(item.evidence_refs) <= evidence_ids for item in first)


def test_direct_reuse_requires_confirmed_requirements_and_no_changes() -> None:
    decision = _plan(
        _process_spec(data=["customer-data"]),
        _asset([_module("direct", required_data=["customer-data"])]),
    )[0]

    assert decision.decision == "direct_reuse"
    assert decision.required_changes == []
    assert decision.estimated_effort == "none"


def test_configuration_requires_documented_configuration_basis() -> None:
    process = _process_spec(
        constraints=[{"id": "rule", "type": "approval", "statement": "customer review rule", "hard": True}]
    )
    decision = _plan(
        process,
        _asset(
            [
                _module(
                    "configured-review",
                    required_rules=["customer review rule"],
                    configurable_items=["customer review rule"],
                    capability_ids=["rule-engine"],
                )
            ]
        ),
    )[0]

    assert decision.decision == "configuration"
    assert decision.required_changes == ["configure:customer review rule"]
    assert decision.estimated_effort == "small"


def test_explicit_system_difference_requires_customization_not_configuration() -> None:
    decision = _plan(
        _process_spec(systems=["OA"]),
        _asset([_module("erp-review", required_systems=["ERP"], configurable_items=["review point"])]),
    )[0]

    assert decision.decision == "customization"
    assert decision.required_changes == ["develop:connector adapter for system:ERP"]
    assert decision.estimated_effort == "medium"


def test_unknown_required_data_creates_no_false_direct_or_unavailable_decision() -> None:
    decisions = _plan(
        _process_spec(),
        _asset([_module("unknown-data", required_data=["unconfirmed-data"])]),
    )

    assert decisions == []


def test_module_specific_data_blocker_does_not_pollute_unrelated_module() -> None:
    process = _process_spec(
        constraints=[
            {"id": "data", "type": "data", "statement": "customer master data 明确不可获得", "hard": True}
        ]
    )
    decisions = _plan(
        process,
        _asset(
            [
                _module("blocked-data", required_data=["customer master data"]),
                _module("independent-module"),
            ]
        ),
    )
    by_module = {item.module_id: item for item in decisions}

    assert by_module["blocked-data"].decision == "unavailable"
    assert by_module["independent-module"].decision == "direct_reuse"


def test_global_security_blocker_marks_all_participating_modules_unavailable() -> None:
    process = _process_spec(
        constraints=[{"id": "security", "type": "security", "statement": "必须私有部署", "hard": True}]
    )
    decisions = _plan(
        process,
        _asset([_module("first"), _module("second")], deployments=["public_saas"]),
    )

    assert [item.decision for item in decisions] == ["unavailable", "unavailable"]
    assert all(item.estimated_effort == "unknown" for item in decisions)


def test_human_review_is_limited_to_human_approval_modules() -> None:
    process = _process_spec(
        constraints=[{"id": "approval", "type": "approval", "statement": "must have human approval", "hard": True}]
    )
    decisions = _plan(
        process,
        _asset(
            [
                _module("human-review", capability_ids=["human-approval"]),
                _module("document-parse"),
            ]
        ),
    )
    by_module = {item.module_id: item for item in decisions}

    assert by_module["human-review"].human_review_required is True
    assert by_module["document-parse"].human_review_required is False


def test_fit_score_is_not_a_reuse_mode_threshold() -> None:
    process = _process_spec(data=["customer-data"], systems=["OA"])
    asset = _asset(
        [
            _module("direct", required_data=["customer-data"]),
            _module("custom", required_systems=["ERP"]),
        ]
    )
    decisions = _plan(process, asset)
    genes = GeneBuilder().build_from_process(process)
    fit = FitEngine().assess(process, genes, asset)
    changed_fit = fit.model_copy(update={"raw_fit_score": 99.0, "effective_fit_score": 99.0})
    repeated = ReusePlanner(AssetRepository()).plan(process, genes, asset, changed_fit)

    assert [item.decision for item in decisions] == ["direct_reuse", "customization"]
    assert [item.model_dump() for item in decisions] == [item.model_dump() for item in repeated]


def test_summary_aggregates_existing_decisions_and_rejects_empty_input() -> None:
    planner = ReusePlanner(AssetRepository())
    decisions = _plan(
        _process_spec(data=["customer-data"]),
        _asset(
            [
                _module("direct", required_data=["customer-data"]),
                _module("custom", required_systems=["ERP"]),
            ]
        ),
    )

    summary = planner.summarize(decisions)

    assert summary.direct_reuse_count == 1
    assert summary.customization_count == 1
    assert summary.direct_reuse_ratio == pytest.approx(0.5)
    assert summary.customization_ratio == pytest.approx(0.5)
    assert sum(summary.model_dump()[key] for key in summary.model_dump() if key.endswith("_ratio")) == pytest.approx(1.0)
    assert summary == planner.summarize(decisions)
    with pytest.raises(ValueError, match="at least one"):
        planner.summarize([])
    with pytest.raises(ValidationError):
        ReuseSummary(
            direct_reuse_count=0,
            configuration_count=0,
            customization_count=0,
            unavailable_count=0,
            direct_reuse_ratio=0,
            configuration_ratio=0,
            customization_ratio=0,
            unavailable_ratio=0,
        )


def test_reuse_decision_rejects_blank_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        ReuseDecision(
            project_id="project",
            asset_id="asset",
            module_id="module",
            decision="direct_reuse",
            rationale="   ",
            estimated_effort="none",
        )


def test_golden_smart_procurement_scopes_human_review_to_the_review_module() -> None:
    process = _process(
        project_id="procurement-approval-demo",
        industry="制造",
        node_name="招标文件审查",
        node_description="采购专员依据审查规则审查招标文件并定位风险",
        business_goal="缩短招标文件编制与审查周期，降低合规风险",
        available_data=["历史招标文件", "企业采购制度", "审查规则"],
        constraints=[
            {"id": "security", "type": "security", "statement": "数据不得出企业私域", "hard": True},
            {"id": "approval", "type": "approval", "statement": "超过500000必须人工审批", "hard": True},
        ],
    )
    repository = AssetRepository()
    asset = repository.get_asset("dc-smart-procurement")
    decisions = _plan(process, asset)
    by_module = {item.module_id: item for item in decisions}

    assert by_module["procurement-review-and-risk-location"].decision == "configuration"
    assert by_module["procurement-review-and-risk-location"].human_review_required is True


def frozen_procurement_golden_process():
    """B-M8 fixture; intentionally separate from the existing v1 procurement fixture."""
    return _process(
        project_id="frozen-procurement-golden",
        industry="制造",
        node_name="招标文件审查",
        node_description="采购专员依据审查规则审查招标文件并定位风险",
        business_goal="缩短招标文件编制与审查周期，降低合规风险",
        available_data=["历史采购方案", "历史招标文件", "企业采购制度", "审查规则"],
        constraints=[
            {"id": "security-private", "type": "security", "statement": "数据不得出企业私域", "hard": True},
            {"id": "approval-threshold", "type": "approval", "statement": "超过500000必须人工审批", "hard": True},
        ],
        roles=["采购专员", "法务", "采购经理"],
        actor="采购专员",
    ).model_copy(update={"target_metrics": ["processing_time", "manual_steps", "risk_findings"]})


def test_sparse_metadata_and_generic_overlap_cannot_create_direct_reuse() -> None:
    process = _process_spec()
    sparse = SolutionAssetModule(
        module_id="sparse-longtext",
        name="energy longtext generation",
        description="document generation",
        evidence_refs=["test-evidence"],
    )

    decisions = _plan(process, _asset([sparse]))

    assert decisions == []


def test_frozen_procurement_golden_has_approval_without_inventing_threshold_configuration() -> None:
    process = frozen_procurement_golden_process()
    repository = AssetRepository()
    genes = GeneBuilder().build_from_process(process)
    candidates = AssetRetriever(repository).retrieve(process, genes, top_k=3)
    smart = repository.get_asset("dc-smart-procurement")
    decisions = ReusePlanner(repository).plan(process, genes, smart, FitEngine().assess(process, genes, smart))
    by_module = {item.module_id: item for item in decisions}
    review = by_module["procurement-review-and-risk-location"]

    assert "dc-smart-procurement" in {item.asset_id for item in candidates}
    assert process.target_metrics == ["processing_time", "manual_steps", "risk_findings"]
    assert review.human_review_required is True
    assert "approval threshold compatibility requires confirmation" in review.gaps
    assert all("审批金额" not in change and "500000" not in change for change in review.required_changes)
    assert review.decision in {"configuration", "customization", "direct_reuse"}


def test_frozen_fixture_does_not_mutate_the_existing_v1_procurement_fixture() -> None:
    existing = _procurement_process()

    assert [constraint.type for constraint in existing.constraints] == ["security"]
    assert {constraint.type for constraint in frozen_procurement_golden_process().constraints} == {
        "security",
        "approval",
    }


def test_tobacco_rule_input_without_action_evidence_remains_unresolved() -> None:
    process = frozen_procurement_golden_process()
    repository = AssetRepository()
    asset = repository.get_asset("dc-tobacco-smart-procurement")
    planner = ReusePlanner(repository)
    genes = GeneBuilder().build_from_process(process)

    decisions = planner.plan(process, genes, asset, FitEngine().assess(process, genes, asset))

    assert decisions == []
    assert "module:tobacco-document-review: reuse decision requires confirmation" in planner.unresolved_modules
