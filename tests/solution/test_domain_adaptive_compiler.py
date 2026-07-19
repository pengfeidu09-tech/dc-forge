"""B-M7 跨场景自适应方案编译测试。"""

import json
from pathlib import Path

import pytest

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionBundle, SolutionPlan
from backend.app.solution import compile_solution

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"

FORBIDDEN_PROCUREMENT_TERMS = ["采购订单", "发票", "收货记录", "供应商", "超过50万元"]


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _make_process(**overrides) -> ProcessSpec:
    """构造最小合法 ProcessSpec，默认为非采购场景。"""
    base = {
        "schema_version": "1.0",
        "project_id": "test-incident-001",
        "industry": "电信运营",
        "department": "网络运维",
        "business_goal": "缩短故障恢复时间",
        "roles": ["运维工程师"],
        "available_data": ["网络告警记录", "客服工单记录"],
        "existing_systems": ["监控系统"],
        "as_is_nodes": [],
        "pain_points": [{"id": "pp-1", "description": "客户核心通信功能不可用", "severity": "high"}],
        "constraints": [],
        "target_metrics": ["平均恢复时间", "客户重复联系率"],
        "missing_information": [],
        "clarification_questions": [],
        "readiness_score": 70,
    }
    base.update(overrides)
    return ProcessSpec.model_validate(base)


# ===== 测试一：人工审批节点语义 =====


def test_human_approval_node_always_has_human_gate() -> None:
    """human-approval 节点必须 executor=human, human_gate=true, gate_reason 非空。"""
    process = _make_process()
    bundle = compile_solution(process)
    for plan in bundle.plans:
        for node in plan.to_be_nodes:
            if node.component_id == "human-approval":
                assert node.executor == "human", f"{plan.plan_type}: executor={node.executor}"
                assert node.human_gate is True, f"{plan.plan_type}: human_gate={node.human_gate}"
                assert node.gate_reason and len(node.gate_reason) > 2, f"{plan.plan_type}: gate_reason empty"


# ===== 测试二：禁止无来源的采购硬编码 =====


def test_no_procurement_terms_for_non_procurement_scenario() -> None:
    """非采购场景的输出不得出现无来源的采购术语。"""
    process = _make_process(
        project_id="test-network-001",
        industry="互联网基础服务",
        department="网站运维",
        business_goal="缩短平台故障恢复时间",
        available_data=["网站可用性监控", "域名解析监控"],
        pain_points=[{"id": "pp-1", "description": "客户无法编辑网站", "severity": "high"}],
    )
    # 确认输入不含采购术语
    input_text = json.dumps(process.model_dump(), ensure_ascii=False)
    for term in FORBIDDEN_PROCUREMENT_TERMS:
        assert term not in input_text, f"输入不应含 {term}"

    bundle = compile_solution(process)
    # 只检查方案文案字段，不检查 required_data（来自 capabilities.json 共享数据）
    checked_fields = []
    for plan in bundle.plans:
        checked_fields.append(plan.summary)
        checked_fields.extend(plan.implementation_steps)
        checked_fields.extend(n.name for n in plan.to_be_nodes)
        checked_fields.extend(n.gate_reason or "" for n in plan.to_be_nodes)
        checked_fields.extend(plan.assumptions)
        checked_fields.extend(plan.warnings)
    output_text = " ".join(checked_fields)
    for term in FORBIDDEN_PROCUREMENT_TERMS:
        assert term not in output_text, f"输出文案不应含无来源采购术语: {term}"


# ===== 测试三：跨场景输出必须不同 =====


def test_cross_scenario_outputs_are_different() -> None:
    """至少 5 种场景，至少 3 种不同组件集合和 3 种不同节点序列。"""
    scenarios = [
        _make_process(
            project_id="s1", industry="电信运营", department="网络运维",
            business_goal="缩短故障恢复时间",
            available_data=["网络告警记录"], pain_points=[{"id": "p", "description": "通信不可用", "severity": "high"}],
        ),
        _make_process(
            project_id="s2", industry="银行与信用卡", department="反欺诈",
            business_goal="建立未授权交易调查闭环",
            available_data=["欺诈案件记录", "交易日志"], pain_points=[{"id": "p", "description": "存在未授权信用卡申请", "severity": "high"}],
        ),
        _make_process(
            project_id="s3", industry="银行业", department="账户服务",
            business_goal="提供线上账户姓名变更流程",
            available_data=["客户账户资料", "身份变更证明"], pain_points=[{"id": "p", "description": "客户无法到网点办理", "severity": "medium"}],
        ),
        _make_process(
            project_id="s4", industry="个人征信", department="争议处理",
            business_goal="缩短未经授权账户调查时间",
            available_data=["信用报告", "账户明细"], pain_points=[{"id": "p", "description": "信用报告含未经授权账户", "severity": "high"}],
        ),
        _make_process(
            project_id="s5", industry="企业采购", department="采购与财务",
            business_goal="降低采购异常处理时间",
            available_data=["采购订单", "收货记录"], pain_points=[{"id": "p", "description": "订单核对耗时", "severity": "medium"}],
        ),
    ]

    comp_sets = set()
    node_seqs = set()
    for process in scenarios:
        bundle = compile_solution(process)
        assert len(bundle.plans) == 3
        balanced = next(p for p in bundle.plans if p.plan_type == "balanced")
        comp_sets.add(frozenset(c.component_id for c in balanced.selected_components))
        node_seqs.add(tuple(n.name for n in balanced.to_be_nodes))

    assert len(comp_sets) >= 3, f"只有 {len(comp_sets)} 种组件集合"
    assert len(node_seqs) >= 3, f"只有 {len(node_seqs)} 种节点序列"


# ===== 测试四：输入内容必须进入方案 =====


def test_input_content_reflected_in_output() -> None:
    """implementation_steps/summary/节点中需体现输入信息。"""
    process = _make_process(
        industry="铁路客运",
        department="票务服务",
        business_goal="降低购票失败率",
        available_data=["购票订单记录", "网站点击日志"],
        target_metrics=["购票成功率"],
    )
    bundle = compile_solution(process)
    balanced = next(p for p in bundle.plans if p.plan_type == "balanced")

    all_text = balanced.summary + " ".join(balanced.implementation_steps)
    all_text += " ".join(n.name for n in balanced.to_be_nodes)

    # 至少体现部分输入信息
    input_terms = ["铁路", "票务", "购票", "订单", "点击"]
    matched = sum(1 for t in input_terms if t in all_text)
    assert matched >= 1, f"输出未体现输入内容，匹配 {matched}/{len(input_terms)}"


# ===== 测试五：结构兼容性 =====


def test_structure_compatibility() -> None:
    """结构兼容：3 套方案、正确类型、无悬空、组件一致。"""
    process = _make_process()
    bundle = compile_solution(process)

    assert isinstance(bundle, SolutionBundle)
    assert len(bundle.plans) == 3
    types = [p.plan_type for p in bundle.plans]
    assert types == ["conservative", "balanced", "innovative"]

    for plan in bundle.plans:
        assert plan.solution_id
        assert plan.selected_components
        assert plan.to_be_nodes
        node_ids = {n.id for n in plan.to_be_nodes}
        for n in plan.to_be_nodes:
            for nid in n.next_ids:
                assert nid in node_ids, f"{plan.plan_type}: dangling {nid}"
        # 节点 component_id 应在 selected_components 中
        comp_ids = {c.component_id for c in plan.selected_components}
        for n in plan.to_be_nodes:
            assert n.component_id in comp_ids, f"{plan.plan_type}: node {n.id} comp {n.component_id} not in selected"

    SolutionBundle.model_validate(bundle.model_dump())


# ===== 测试六：约束映射 =====


def test_constraint_mapping() -> None:
    """约束能影响 human_gate 和组件选择。"""
    approval_constraint = BusinessConstraint(
        id="c-approval", type="approval", statement="高风险操作需人工审批", hard=True,
    )
    security_constraint = BusinessConstraint(
        id="c-security", type="security", statement="敏感数据需脱敏和审计留痕", hard=True,
    )
    process = _make_process(constraints=[approval_constraint, security_constraint])
    bundle = compile_solution(process)
    balanced = next(p for p in bundle.plans if p.plan_type == "balanced")

    # approval 约束应影响 human_gate
    has_gate = any(n.human_gate for n in balanced.to_be_nodes)
    assert has_gate, "approval 约束应产生 human_gate"

    # security 约束应影响组件（data-masking 或 audit-log）
    comp_ids = {c.component_id for c in balanced.selected_components}
    assert "audit-log" in comp_ids or "data-masking" in comp_ids, "security 约束应引入审计或脱敏组件"

    # applied_constraints 保留输入约束
    constraint_ids = {c.id for c in balanced.applied_constraints}
    assert "c-approval" in constraint_ids
    assert "c-security" in constraint_ids

    # 无约束也能正常编译
    no_constraint_process = _make_process(constraints=[])
    no_constraint_bundle = compile_solution(no_constraint_process)
    assert len(no_constraint_bundle.plans) == 3


# ===== 测试七：推荐文案不与评分冲突 =====


def test_recommendation_text_does_not_conflict_with_score() -> None:
    """如果 balanced 不是最高分，summary 不应声称最高或默认推荐。"""
    process = _make_process()
    bundle = compile_solution(process)
    scores = {p.plan_type: p.review_score for p in bundle.plans}
    balanced = next(p for p in bundle.plans if p.plan_type == "balanced")

    if scores["balanced"] < max(scores.values()):
        # balanced 不是最高分
        forbidden = ["评分最高", "绝对最优", "默认推荐"]
        for term in forbidden:
            assert term not in balanced.summary, f"balanced 非最高分但 summary 含 '{term}'"
