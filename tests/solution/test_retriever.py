"""B-M1 确定性检索器测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import ComponentRef
from backend.app.solution.capabilities import load_capabilities
from backend.app.solution.retriever import retrieve_components

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def test_retriever_returns_components_for_procurement_process() -> None:
    """输入采购场景 ProcessSpec 时，检索结果非空。"""
    process = _load_process_spec()
    result = retrieve_components(process)
    assert len(result) > 0, "采购场景应返回非空结果"


def test_retriever_returns_only_known_component_ids() -> None:
    """返回的每个 component_id 都必须存在于能力胶囊库。"""
    process = _load_process_spec()
    capabilities = load_capabilities()
    known_ids = {cap.component_id for cap in capabilities}
    result = retrieve_components(process)
    for ref in result:
        assert ref.component_id in known_ids, f"未知 component_id: {ref.component_id}"


def test_retriever_respects_limit() -> None:
    """返回数量不超过 limit。"""
    process = _load_process_spec()
    result = retrieve_components(process, limit=3)
    assert len(result) <= 3


def test_retriever_returns_component_refs() -> None:
    """返回结果满足 ComponentRef 公共合同。"""
    process = _load_process_spec()
    result = retrieve_components(process)
    for ref in result:
        ComponentRef.model_validate(ref.model_dump())


def test_retriever_is_deterministic() -> None:
    """同一输入多次运行结果一致。"""
    process = _load_process_spec()
    first = retrieve_components(process)
    second = retrieve_components(process)
    assert [r.component_id for r in first] == [r.component_id for r in second]


def test_approval_constraint_prioritizes_human_approval() -> None:
    """有审批约束时，human-approval 应获得优先匹配。"""
    process = _load_process_spec()
    result = retrieve_components(process, limit=10)
    ids = [r.component_id for r in result]
    assert "human-approval" in ids, "审批约束应使 human-approval 进入结果"
    # human-approval 应排在前列（前 3 名）
    assert ids.index("human-approval") < 3, (
        f"human-approval 应排在前 3 名，实际位置: {ids.index('human-approval')}"
    )


def test_retriever_returns_empty_when_nothing_matches() -> None:
    """没有匹配结果时返回空列表，不虚构组件。"""
    process = ProcessSpec(
        schema_version="1.0",
        project_id="no-match-001",
        industry="航空航天",
        department="深空探测",
        business_goal="实现星际通信",
        roles=["宇航员"],
        available_data=["星际信号"],
        existing_systems=["深空天线"],
        as_is_nodes=[],
        pain_points=[],
        constraints=[],
        target_metrics=["信号延迟"],
        missing_information=[],
        clarification_questions=[],
        readiness_score=10,
    )
    result = retrieve_components(process)
    assert result == [], "无匹配时应返回空列表"
