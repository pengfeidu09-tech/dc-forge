import pytest

from backend.app.contracts.solution_intelligence import EvidenceRecord
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.asset_retriever import AssetRetriever
from backend.app.solution.fit_engine import FIT_WEIGHTS, UNKNOWN_DIMENSION_SCORE, FitEngine
from backend.app.solution.gene_builder import GeneBuilder
from tests.solution.test_asset_retriever import _procurement_process, _process
from tests.solution.test_hard_gates import _asset


def _assess_procurement():
    process = _procurement_process()
    genes = GeneBuilder().build_from_process(process)
    asset = AssetRepository().get_asset("dc-smart-procurement")
    return process, genes, FitEngine().assess(process, genes, asset)


def test_fit_weights_sum_to_one_and_assessment_is_deterministic() -> None:
    process, genes, first = _assess_procurement()
    second = FitEngine().assess(
        process,
        genes,
        AssetRepository().get_asset("dc-smart-procurement"),
    )

    assert sum(FIT_WEIGHTS.values()) == pytest.approx(1.0)
    assert first.model_dump() == second.model_dump()


def test_dimensions_are_explained_and_raw_fit_is_weighted_sum() -> None:
    _, _, assessment = _assess_procurement()

    assert {dimension.name for dimension in assessment.dimensions} == set(FIT_WEIGHTS)
    assert all(0 <= dimension.score <= 100 and dimension.explanation for dimension in assessment.dimensions)
    assert assessment.raw_fit_score == round(
        sum(dimension.score * dimension.weight for dimension in assessment.dimensions), 2
    )
    assert assessment.effective_fit_score == assessment.raw_fit_score


def test_unknown_object_and_technology_use_shared_neutral_score() -> None:
    _, _, assessment = _assess_procurement()
    dimensions = {dimension.name: dimension for dimension in assessment.dimensions}

    assert dimensions["object"].score == UNKNOWN_DIMENSION_SCORE
    assert "insufficient information" in dimensions["object"].explanation
    assert dimensions["technology"].score == UNKNOWN_DIMENSION_SCORE
    assert "insufficient information" in dimensions["technology"].explanation


def test_unrelated_asset_evidence_cannot_create_high_fit_and_action_ids_are_valid() -> None:
    process = _process(
        project_id="unrelated-fit",
        industry="航空航天",
        node_name="星际通信校验",
        node_description="校验深空信号延迟",
        business_goal="实现星际通信",
        available_data=["星际信号"],
        roles=["宇航员"],
        actor="宇航员",
    )
    genes = GeneBuilder().build_from_process(process)
    assessment = FitEngine().assess(
        process,
        genes,
        AssetRepository().get_asset("dc-auto-store-mate"),
    )
    node_ids = {node.id for node in process.as_is_nodes}

    assert assessment.raw_fit_score < 60
    assert set(assessment.matched_action_ids) <= node_ids
    assert set(assessment.unmatched_action_ids) <= node_ids
    assert set(assessment.matched_action_ids).isdisjoint(assessment.unmatched_action_ids)


def test_value_difficulty_and_quadrant_are_bounded_and_deterministic() -> None:
    _, _, assessment = _assess_procurement()

    assert 0 <= assessment.business_value_score <= 100
    assert 0 <= assessment.implementation_difficulty_score <= 100
    assert assessment.quadrant in {"quick_win", "strategic", "experiment", "avoid"}


def test_medical_internal_evidence_scores_below_equivalent_verified_official_evidence() -> None:
    process = _process(
        project_id="medical-fit",
        industry="医药",
        node_name="循证助手场景",
        node_description="医药智能循证助手",
        business_goal="支持医药智能循证助手",
        available_data=[],
        roles=["医药人员"],
        actor="医药人员",
    )
    genes = GeneBuilder().build_from_process(process)
    medical = AssetRepository().get_asset("dc-medical-evidence-assistant")
    official_evidence = EvidenceRecord(
        evidence_id="mea-corpus-definition",
        source_type="official_case",
        title="Equivalent official evidence",
        document_name="Equivalent case.pdf",
        page_start=1,
        page_end=1,
        kind="asset_definition",
        statement="Equivalent evidence.",
        verified=True,
    )
    official_equivalent = medical.model_copy(update={"evidence": [official_evidence]})

    internal = FitEngine().assess(process, genes, medical)
    official = FitEngine().assess(process, genes, official_equivalent)
    internal_evidence = next(item for item in internal.dimensions if item.name == "evidence")
    official_evidence_dimension = next(item for item in official.dimensions if item.name == "evidence")

    assert internal_evidence.score < official_evidence_dimension.score


def test_golden_procurement_top_three_produce_explainable_fit_assessments() -> None:
    process = _procurement_process()
    genes = GeneBuilder().build_from_process(process)
    repository = AssetRepository()
    candidates = AssetRetriever(repository).retrieve(process, genes, top_k=3)
    assessments = [FitEngine().assess(process, genes, repository.get_asset(item.asset_id)) for item in candidates]

    by_asset = {assessment.asset_id: assessment for assessment in assessments}
    assert set(by_asset) == {
        "dc-smart-procurement",
        "dc-energy-serious-longtext",
        "dc-tobacco-smart-procurement",
    }
    assert by_asset["dc-smart-procurement"].eligible is True
    assert next(
        item for item in by_asset["dc-smart-procurement"].dimensions if item.name == "data_knowledge"
    ).score > UNKNOWN_DIMENSION_SCORE
    assert all(assessment.evidence_refs for assessment in assessments)


def test_known_match_outscores_sparse_unknown_which_outscores_known_mismatch() -> None:
    """Unknown fields remain conservative and cannot reward a sparse asset."""
    process = _process(
        project_id="uncertainty-ordering",
        industry="manufacturing",
        node_name="procurement review",
        node_description="review procurement document",
        business_goal="review procurement document",
        available_data=["customer-data"],
        roles=["buyer"],
        actor="buyer",
    )
    genes = GeneBuilder().build_from_process(process)
    matched = _asset(required_data=["customer-data"])
    sparse = matched.model_copy(
        update={
            "target_roles": [],
            "modules": [matched.modules[0].model_copy(update={"required_data": []})],
        }
    )
    mismatched = matched.model_copy(
        update={
            "target_roles": ["other-role"],
            "modules": [matched.modules[0].model_copy(update={"required_data": ["other-data"]})],
        }
    )

    assessments = [FitEngine().assess(process, genes, asset) for asset in (matched, sparse, mismatched)]

    assert assessments[0].raw_fit_score > assessments[1].raw_fit_score > assessments[2].raw_fit_score
    assert "MATCH:" in next(item for item in assessments[0].dimensions if item.name == "data_knowledge").explanation
    assert "UNKNOWN:" in next(item for item in assessments[1].dimensions if item.name == "data_knowledge").explanation
    assert "MISMATCH:" in next(item for item in assessments[2].dimensions if item.name == "data_knowledge").explanation


def test_rule_accommodation_is_partial_and_not_an_exact_rule_match() -> None:
    process = _procurement_process()
    genes = GeneBuilder().build_from_process(process)
    repository = AssetRepository()

    rule_scores = {
        asset_id: next(
            item
            for item in FitEngine().assess(process, genes, repository.get_asset(asset_id)).dimensions
            if item.name == "rules"
        )
        for asset_id in (
            "dc-smart-procurement",
            "dc-tobacco-smart-procurement",
            "dc-energy-serious-longtext",
        )
    }

    assert rule_scores["dc-smart-procurement"].score > 0
    assert rule_scores["dc-tobacco-smart-procurement"].score > 0
    assert rule_scores["dc-tobacco-smart-procurement"].score < rule_scores["dc-smart-procurement"].score
    assert rule_scores["dc-energy-serious-longtext"].score < rule_scores["dc-smart-procurement"].score
    assert "PARTIAL:" in rule_scores["dc-tobacco-smart-procurement"].explanation


def test_human_approval_support_is_partial_without_evidence_for_the_customer_threshold() -> None:
    process = _process(
        project_id="approval-threshold",
        industry="manufacturing",
        node_name="procurement review",
        node_description="review procurement document",
        business_goal="review procurement document",
        available_data=[],
        constraints=[
            {
                "id": "approval-threshold",
                "type": "approval",
                "statement": "approval is required over 500000",
                "hard": True,
            }
        ],
        roles=["buyer"],
        actor="buyer",
    )
    asset = AssetRepository().get_asset("dc-smart-procurement")
    rules = next(
        item
        for item in FitEngine().assess(process, GeneBuilder().build_from_process(process), asset).dimensions
        if item.name == "rules"
    )

    assert rules.score == 70
    assert rules.explanation.startswith("PARTIAL:")
    assert "exact customer threshold is not evidenced" in rules.explanation


def test_official_evidence_without_matched_capability_reference_is_not_full_score() -> None:
    process = _process(
        project_id="unlinked-evidence",
        industry="manufacturing",
        node_name="procurement review",
        node_description="review procurement document",
        business_goal="review procurement document",
        available_data=[],
        roles=["buyer"],
        actor="buyer",
    )
    asset = _asset().model_copy(
        update={"modules": [_asset().modules[0].model_copy(update={"evidence_refs": []})]}
    )

    assessment = FitEngine().assess(process, GeneBuilder().build_from_process(process), asset)
    evidence = next(item for item in assessment.dimensions if item.name == "evidence")

    assert evidence.score < 100
    assert "does not support the current matched action" in evidence.explanation
