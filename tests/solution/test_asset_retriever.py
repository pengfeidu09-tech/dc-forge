import pytest

from backend.app.contracts.process import ProcessSpec
from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.asset_retriever import AssetRetriever
from backend.app.solution.gene_builder import GeneBuilder


def _process(
    *,
    project_id: str,
    industry: str,
    node_name: str,
    node_description: str,
    business_goal: str,
    available_data: list[str],
    constraints: list[dict] | None = None,
    roles: list[str] | None = None,
    actor: str = "采购专员",
) -> ProcessSpec:
    return ProcessSpec.model_validate(
        {
            "project_id": project_id,
            "industry": industry,
            "department": "采购" if "采购" in business_goal else "业务部门",
            "business_goal": business_goal,
            "roles": roles or ["采购专员"],
            "available_data": available_data,
            "existing_systems": ["OA", "采购系统"],
            "as_is_nodes": [
                {
                    "id": "main-node",
                    "name": node_name,
                    "actor": actor,
                    "node_type": "human",
                    "description": node_description,
                }
            ],
            "pain_points": [
                {
                    "id": "main-pain",
                    "description": node_description,
                    "severity": "high",
                    "affected_node_ids": ["main-node"],
                }
            ],
            "constraints": constraints or [],
            "target_metrics": ["处理周期"],
            "missing_information": [],
            "clarification_questions": [],
            "readiness_score": 80,
        }
    )


def _retrieve(process: ProcessSpec, top_k: int = 5):
    genes = GeneBuilder().build_from_process(process)
    candidates = AssetRetriever(AssetRepository()).retrieve(process, genes, top_k=top_k)
    return genes, candidates


def test_retrieval_is_deterministic_and_scores_are_ordered() -> None:
    process = _procurement_process()

    _, first = _retrieve(process)
    _, second = _retrieve(process)

    assert [candidate.model_dump() for candidate in first] == [candidate.model_dump() for candidate in second]
    assert all(0 <= candidate.retrieval_score <= 100 for candidate in first)
    assert [candidate.retrieval_score for candidate in first] == sorted(
        (candidate.retrieval_score for candidate in first), reverse=True
    )
    for left, right in zip(first, first[1:]):
        if left.retrieval_score == right.retrieval_score:
            assert left.asset_id < right.asset_id


def test_top_k_and_invalid_top_k_behavior() -> None:
    process = _procurement_process()

    assert len(_retrieve(process, top_k=1)[1]) == 1
    assert len(_retrieve(process, top_k=3)[1]) == 3
    assert len(_retrieve(process, top_k=5)[1]) <= 5
    with pytest.raises(ValueError, match="top_k"):
        _retrieve(process, top_k=0)


def test_top_k_is_a_maximum_and_unrelated_official_assets_do_not_fill_results() -> None:
    _, candidates = _retrieve(_procurement_process(), top_k=5)

    assert len(candidates) == 3
    assert all(candidate.matched_terms or candidate.matched_gene_ids for candidate in candidates)
    assert "dc-auto-store-mate" not in {candidate.asset_id for candidate in candidates}
    assert "dc-super-employee" not in {candidate.asset_id for candidate in candidates}


def test_candidates_only_reference_known_assets_evidence_and_genes() -> None:
    process = _procurement_process()
    genes, candidates = _retrieve(process)
    repository = AssetRepository()
    gene_ids = {gene.gene_id for gene in genes}

    for candidate in candidates:
        asset = repository.get_asset(candidate.asset_id)
        evidence_ids = {evidence.evidence_id for evidence in asset.evidence}
        assert set(candidate.evidence_refs) <= evidence_ids
        assert set(candidate.matched_gene_ids) <= gene_ids


def test_manufacturing_procurement_retrieves_procurement_assets_without_industry_filter() -> None:
    _, candidates = _retrieve(_procurement_process(), top_k=3)
    asset_ids = [candidate.asset_id for candidate in candidates]

    assert "dc-smart-procurement" in asset_ids
    assert "dc-tobacco-smart-procurement" in asset_ids


def test_energy_longtext_retrieves_energy_and_cross_industry_tobacco_assets() -> None:
    process = _process(
        project_id="energy-longtext-demo",
        industry="能源",
        node_name="严肃长文本报告审查",
        node_description="对严肃长文本报告进行文档结构解析和专业审查",
        business_goal="生成并审查严肃长文本报告",
        available_data=["专业文档", "审查规则"],
        roles=["报告编制人员"],
        actor="报告编制人员",
    )

    _, candidates = _retrieve(process, top_k=5)
    asset_ids = [candidate.asset_id for candidate in candidates]

    assert asset_ids[0] == "dc-energy-serious-longtext"
    assert "dc-tobacco-smart-procurement" in asset_ids


def test_medical_placeholder_has_no_verified_official_evidence_bonus() -> None:
    process = _process(
        project_id="medical-placeholder-demo",
        industry="医药",
        node_name="循证助手场景",
        node_description="医药智能循证助手",
        business_goal="支持医药智能循证助手",
        available_data=[],
    )

    _, candidates = _retrieve(process, top_k=5)
    medical = next(candidate for candidate in candidates if candidate.asset_id == "dc-medical-evidence-assistant")

    assert medical.evidence_refs == ["mea-corpus-definition"]
    assert medical.retrieval_score == 65.0


def test_official_evidence_does_not_create_relevance_without_business_match() -> None:
    process = _process(
        project_id="unrelated-demo",
        industry="航空航天",
        node_name="星际通信校验",
        node_description="校验深空信号延迟",
        business_goal="实现星际通信",
        available_data=["星际信号"],
        roles=["宇航员"],
        actor="宇航员",
    )

    _, candidates = _retrieve(process, top_k=5)

    assert candidates == []


def test_business_match_receives_official_evidence_bonus() -> None:
    _, candidates = _retrieve(_procurement_process(), top_k=3)
    smart_procurement = next(
        candidate for candidate in candidates if candidate.asset_id == "dc-smart-procurement"
    )

    assert smart_procurement.retrieval_score == 80.0
    assert smart_procurement.evidence_refs


def _procurement_process() -> ProcessSpec:
    return _process(
        project_id="procurement-demo-40",
        industry="制造",
        node_name="招标文件审查",
        node_description="采购专员依据审查规则审查招标文件并定位风险",
        business_goal="缩短招标文件编制与审查周期，降低合规风险",
        available_data=["历史招标文件", "企业采购制度", "审查规则"],
        constraints=[
            {
                "id": "security-private",
                "type": "security",
                "statement": "数据不得出企业私域",
                    "hard": True,
            }
        ],
    )
