"""B-M2 SolutionCompiler 三套方案编译器测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionBundle, SolutionPlan
from backend.app.solution import compile_solution
from backend.app.solution.capabilities import load_capabilities

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _compile() -> SolutionBundle:
    return compile_solution(_load_process_spec())


def test_compile_returns_solution_bundle() -> None:
    """compile_solution 返回 SolutionBundle 实例。"""
    result = _compile()
    assert isinstance(result, SolutionBundle)


def test_compile_returns_exactly_three_plan_types() -> None:
    """plans 长度恰好为 3，plan_type 集合正确。"""
    result = _compile()
    assert len(result.plans) == 3
    types = {p.plan_type for p in result.plans}
    assert types == {"conservative", "balanced", "innovative"}


def test_solution_ids_are_unique_and_stable() -> None:
    """solution_id 唯一且重复编译结果一致。"""
    first = _compile()
    second = _compile()
    ids_first = [p.solution_id for p in first.plans]
    ids_second = [p.solution_id for p in second.plans]
    assert len(ids_first) == len(set(ids_first)), "solution_id 不唯一"
    assert ids_first == ids_second, "solution_id 不稳定"


def test_source_project_id_matches_input() -> None:
    """source_project_id 全部等于输入 project_id。"""
    process = _load_process_spec()
    result = compile_solution(process)
    for plan in result.plans:
        assert plan.source_project_id == process.project_id


def test_selected_components_exist_in_catalog() -> None:
    """所有 selected_components 的 component_id 存在于能力胶囊库。"""
    result = _compile()
    capabilities = load_capabilities()
    known_ids = {cap.component_id for cap in capabilities}
    for plan in result.plans:
        for comp in plan.selected_components:
            assert comp.component_id in known_ids, f"未知 component_id: {comp.component_id}"


def test_all_plans_contain_workflow_nodes() -> None:
    """每套方案的 to_be_nodes 非空。"""
    result = _compile()
    for plan in result.plans:
        assert len(plan.to_be_nodes) > 0, f"{plan.plan_type} 的 to_be_nodes 为空"


def test_workflow_next_ids_are_not_dangling() -> None:
    """所有 next_ids 必须指向同一方案中真实存在的节点，不允许悬空。"""
    result = _compile()
    for plan in result.plans:
        node_ids = {n.id for n in plan.to_be_nodes}
        for node in plan.to_be_nodes:
            for next_id in node.next_ids:
                assert next_id in node_ids, (
                    f"{plan.plan_type} 节点 {node.id} 的 next_id {next_id} 悬空"
                )


def test_hard_approval_constraint_creates_human_gate_in_all_plans() -> None:
    """process_spec.json 存在 hard approval 约束，三套方案都必须有 human_gate=true。"""
    result = _compile()
    for plan in result.plans:
        gates = [n for n in plan.to_be_nodes if n.human_gate]
        assert len(gates) >= 1, f"{plan.plan_type} 缺少 human_gate=true 的节点"


def test_all_input_constraints_are_preserved() -> None:
    """每套方案的 applied_constraints 完整保留输入约束。"""
    process = _load_process_spec()
    result = compile_solution(process)
    input_constraint_ids = {c.id for c in process.constraints}
    for plan in result.plans:
        plan_constraint_ids = {c.id for c in plan.applied_constraints}
        assert input_constraint_ids <= plan_constraint_ids, (
            f"{plan.plan_type} 未保留全部输入约束"
        )


def test_three_plans_are_meaningfully_different() -> None:
    """三套方案不得完全相同（比较 selected_components 的 component_id 集合）。"""
    result = _compile()
    comp_sets = []
    for plan in result.plans:
        comp_sets.append(frozenset(c.component_id for c in plan.selected_components))
    assert len(set(comp_sets)) == 3, "三套方案的组件集合不应完全相同"


def test_innovative_has_at_least_as_many_automation_components_as_balanced() -> None:
    """innovative 的自动化组件数量不得低于 balanced。"""
    result = _compile()
    plans_by_type = {p.plan_type: p for p in result.plans}
    bal_auto = sum(1 for c in plans_by_type["balanced"].selected_components if c.component_id != "human-approval")
    inn_auto = sum(1 for c in plans_by_type["innovative"].selected_components if c.component_id != "human-approval")
    assert inn_auto >= bal_auto, (
        f"innovative 自动化组件({inn_auto})少于 balanced({bal_auto})"
    )


def test_conservative_has_at_least_as_many_human_gates_as_balanced() -> None:
    """conservative 的人工控制程度不得低于 balanced。"""
    result = _compile()
    plans_by_type = {p.plan_type: p for p in result.plans}
    con_gates = sum(1 for n in plans_by_type["conservative"].to_be_nodes if n.human_gate)
    bal_gates = sum(1 for n in plans_by_type["balanced"].to_be_nodes if n.human_gate)
    assert con_gates >= bal_gates, (
        f"conservative human_gate({con_gates})少于 balanced({bal_gates})"
    )


def test_compile_is_deterministic() -> None:
    """同一输入重复编译结果完全一致。"""
    process = _load_process_spec()
    first = compile_solution(process)
    second = compile_solution(process)
    assert first.model_dump() == second.model_dump(), "重复编译结果不一致"


def test_compile_does_not_mutate_process() -> None:
    """编译不修改传入的 ProcessSpec。"""
    process = _load_process_spec()
    original = process.model_dump()
    compile_solution(process)
    assert process.model_dump() == original, "ProcessSpec 被修改"


def test_review_is_explicitly_pending() -> None:
    """review_score 固定为 0.0，warnings 包含 Reviewer 未执行提示。"""
    result = _compile()
    for plan in result.plans:
        assert plan.review_score == 0.0, f"{plan.plan_type} review_score 不为 0.0"
        warning_text = " ".join(plan.warnings)
        assert "Reviewer" in warning_text or "review" in warning_text.lower(), (
            f"{plan.plan_type} warnings 未提及 Reviewer 未执行"
        )


def test_output_validates_against_public_contract() -> None:
    """输出能通过 SolutionBundle.model_validate。"""
    result = _compile()
    SolutionBundle.model_validate(result.model_dump())
