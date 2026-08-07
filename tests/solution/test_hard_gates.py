from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import EvidenceRecord, SolutionAsset, SolutionAssetModule
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.gene_builder import GeneBuilder


def _process(constraints: list[dict], available_data: list[str] | None = None) -> ProcessSpec:
    return ProcessSpec.model_validate(
        {
            "project_id": "hard-gate-test",
            "industry": "制造",
            "department": "采购",
            "business_goal": "审查采购文档",
            "roles": ["采购专员"],
            "available_data": available_data or [],
            "existing_systems": ["OA"],
            "as_is_nodes": [
                {
                    "id": "review-node",
                    "name": "采购文档审查",
                    "actor": "采购专员",
                    "node_type": "human",
                    "description": "审查采购文档",
                }
            ],
            "pain_points": [],
            "constraints": constraints,
            "target_metrics": ["审查周期"],
            "missing_information": [],
            "clarification_questions": [],
            "readiness_score": 80,
        }
    )


def _asset(
    *,
    deployments: list[str] | None = None,
    required_data: list[str] | None = None,
    required_systems: list[str] | None = None,
    capability_ids: list[str] | None = None,
) -> SolutionAsset:
    return SolutionAsset(
        asset_id="test-asset",
        name="Test asset",
        version="1.0",
        provider="Test provider",
        source_type="official_case",
        industries=["制造"],
        processes=["采购文档审查"],
        scenarios=["采购审查"],
        target_roles=["采购专员"],
        modules=[
            SolutionAssetModule(
                module_id="review-module",
                name="采购文档审查",
                description="Test review module.",
                capability_ids=capability_ids or [],
                required_data=required_data or [],
                required_systems=required_systems or [],
                evidence_refs=["test-evidence"],
            )
        ],
        supported_deployments=deployments or [],
        evidence=[
            EvidenceRecord(
                evidence_id="test-evidence",
                source_type="official_case",
                title="Test evidence",
                document_name="Test case.pdf",
                page_start=1,
                page_end=1,
                kind="asset_definition",
                statement="A short test statement.",
                verified=True,
            )
        ],
    )


def _assess(process: ProcessSpec, asset: SolutionAsset):
    return FitEngine().assess(process, GeneBuilder().build_from_process(process), asset)


def test_private_deployment_conflicts_with_explicit_public_only_asset() -> None:
    process = _process(
        [{"id": "private", "type": "security", "statement": "必须私有部署", "hard": True}]
    )

    assessment = _assess(process, _asset(deployments=["public_saas"]))

    failed = [gate for gate in assessment.hard_gates if not gate.passed]
    assert failed and failed[0].category == "deployment"
    assert assessment.eligible is False
    assert assessment.effective_fit_score is None


def test_unknown_deployment_is_soft_gap_not_hard_failure() -> None:
    process = _process(
        [{"id": "private", "type": "security", "statement": "必须私有部署", "hard": True}]
    )

    assessment = _assess(process, _asset())

    assert assessment.eligible is True
    assert any("compatibility not confirmed" in gap for gap in assessment.soft_gaps)


def test_explicitly_unavailable_required_data_blocks_but_absence_does_not() -> None:
    asset = _asset(required_data=["客户主数据"])
    unavailable = _process(
        [{"id": "data-unavailable", "type": "data", "statement": "客户主数据明确不可获得", "hard": True}]
    )
    not_listed = _process([], available_data=[])

    blocked = _assess(unavailable, asset)
    soft_gap = _assess(not_listed, asset)

    assert any(not gate.passed and gate.category == "data" for gate in blocked.hard_gates)
    assert blocked.eligible is False
    assert soft_gap.eligible is True
    assert any("required data not confirmed" in gap for gap in soft_gap.soft_gaps)


def test_missing_system_is_soft_gap_and_approval_capability_passes() -> None:
    process = _process(
        [
            {
                "id": "approval",
                "type": "approval",
                "statement": "超过 500000 必须人工审批",
                "hard": True,
            }
        ]
    )
    assessment = _assess(
        process,
        _asset(required_systems=["ERP"], capability_ids=["human-approval"]),
    )

    approval_gate = next(gate for gate in assessment.hard_gates if gate.category == "rule")
    assert approval_gate.passed is True
    assert assessment.eligible is True
    assert any("required systems not confirmed" in gap for gap in assessment.soft_gaps)


def test_budget_and_time_without_structured_estimates_do_not_block() -> None:
    process = _process(
        [
            {"id": "budget", "type": "budget", "statement": "预算不超过 10 万", "hard": True},
            {"id": "time", "type": "time", "statement": "两周内交付", "hard": True},
        ]
    )

    assessment = _assess(process, _asset())

    assert assessment.eligible is True
    assert {gate.category for gate in assessment.hard_gates} == {"budget", "time"}


def test_gate_references_are_closed_over_process_and_asset() -> None:
    process = _process(
        [{"id": "private", "type": "security", "statement": "必须私有部署", "hard": True}]
    )
    asset = _asset(deployments=["public_saas"])
    assessment = _assess(process, asset)
    constraint_ids = {constraint.id for constraint in process.constraints}
    evidence_ids = {evidence.evidence_id for evidence in asset.evidence}

    for gate in assessment.hard_gates:
        assert set(gate.constraint_ids) <= constraint_ids
        assert set(gate.evidence_refs) <= evidence_ids
