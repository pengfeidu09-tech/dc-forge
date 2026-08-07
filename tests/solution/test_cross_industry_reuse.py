from backend.app.solution.asset_repository import AssetRepository
from backend.app.solution.fit_engine import FitEngine
from backend.app.solution.gene_builder import GeneBuilder
from backend.app.solution.reuse_planner import ReusePlanner
from tests.solution.test_asset_retriever import _process, _procurement_process


def test_energy_modules_have_evidence_backed_tobacco_lineage_without_inheriting_industry_rules() -> None:
    process = _process(
        project_id="energy-reuse-demo",
        industry="能源",
        node_name="严肃长文本报告审查",
        node_description="进行文档结构解析和文档审查",
        business_goal="生成并审查严肃长文本报告",
        available_data=["专业文档", "能源行业专属规则"],
        roles=["报告编制人员"],
        actor="报告编制人员",
    )
    repository = AssetRepository()
    asset = repository.get_asset("dc-energy-serious-longtext")
    genes = GeneBuilder().build_from_process(process)
    fit = FitEngine().assess(process, genes, asset)
    planner = ReusePlanner(repository)
    decisions = planner.plan(process, genes, asset, fit)
    by_module = {item.module_id: item for item in decisions}

    structure = by_module["energy-document-structure-parsing"]
    review = by_module["energy-document-review"]

    assert "asset:dc-tobacco-smart-procurement/module:tobacco-document-structure-parsing" in structure.dependencies
    assert "asset:dc-tobacco-smart-procurement/module:tobacco-document-review" in review.dependencies
    assert "energy-longtext-generation" not in by_module
    assert "module:energy-longtext-generation: reuse decision requires confirmation" in planner.unresolved_modules
    assert all("火电" not in dependency and "碳排放" not in dependency for item in decisions for dependency in item.dependencies)
    assert all("火电" not in change and "碳排放" not in change for item in decisions for change in item.required_changes)
    assert review.decision == "configuration"


def test_lineage_does_not_turn_unknown_deployment_into_unavailable() -> None:
    process = _process(
        project_id="energy-private-deployment",
        industry="能源",
        node_name="文档审查",
        node_description="进行文档审查",
        business_goal="审查严肃长文本",
        available_data=["专业文档"],
        constraints=[{"id": "security", "type": "security", "statement": "必须私有部署", "hard": True}],
        roles=["报告编制人员"],
        actor="报告编制人员",
    )
    repository = AssetRepository()
    asset = repository.get_asset("dc-energy-serious-longtext")
    genes = GeneBuilder().build_from_process(process)
    fit = FitEngine().assess(process, genes, asset)
    decisions = ReusePlanner(repository).plan(process, genes, asset, fit)
    by_module = {item.module_id: item for item in decisions}

    assert decisions
    assert all(item.decision != "unavailable" for item in decisions)
    assert "asset:dc-tobacco-smart-procurement/module:tobacco-document-review" in by_module[
        "energy-document-review"
    ].dependencies


def test_energy_longtext_generation_is_not_a_procurement_reuse_decision() -> None:
    process = _procurement_process()
    repository = AssetRepository()
    asset = repository.get_asset("dc-energy-serious-longtext")
    genes = GeneBuilder().build_from_process(process)
    planner = ReusePlanner(repository)

    decisions = planner.plan(process, genes, asset, FitEngine().assess(process, genes, asset))

    assert decisions == []
    assert "energy-longtext-generation" not in {item.module_id for item in decisions}
    assert all("tobacco" not in dependency for item in decisions for dependency in item.dependencies)
