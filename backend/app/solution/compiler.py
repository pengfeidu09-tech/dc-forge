"""确定性 SolutionCompiler — 三套方案编译器（场景自适应版）。

输入 ProcessSpec，识别业务场景，按 conservative/balanced/innovative
三种策略生成恰好三套 SolutionPlan，封装为 SolutionBundle。

不调用 LLM，不使用随机数，同一输入结果完全确定。
"""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    ComponentRef,
    SolutionBundle,
    SolutionPlan,
    WorkflowNode,
)
from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities
from backend.app.solution.constraints import validate_constraints
from backend.app.solution.retriever import retrieve_components
from backend.app.solution.reviewer import review_solution
from backend.app.solution import scenario

# ---------------------------------------------------------------------------
# 策略名称（保持不变）
# ---------------------------------------------------------------------------

_STRATEGY_NAMES: dict[str, str] = {
    "conservative": "稳健合规方案",
    "balanced": "效率平衡方案",
    "innovative": "智能重构方案",
}


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _map_executor(executor_type: str) -> str:
    """将 CapabilityCapsule.executor_type 映射为 WorkflowNode.executor。"""
    if executor_type in ("ai", "human", "system"):
        return executor_type
    return "system"


def _build_component_refs(
    plan_type: str,
    component_ids: list[str],
    capabilities_map: dict[str, CapabilityCapsule],
    retrieved_map: dict[str, ComponentRef],
    scenario_name: str,
) -> list[ComponentRef]:
    """为策略构建 ComponentRef 列表，去重且顺序稳定。"""
    refs: list[ComponentRef] = []
    seen: set[str] = set()
    for comp_id in component_ids:
        if comp_id in seen:
            continue
        seen.add(comp_id)
        cap = capabilities_map[comp_id]
        if comp_id in retrieved_map:
            reason = retrieved_map[comp_id].reason
        else:
            reason = f"策略要求: {plan_type}方案必选组件"
        refs.append(
            ComponentRef(
                component_id=cap.component_id,
                name=cap.name,
                reason=reason,
                required_data=scenario.get_required_data(scenario_name, comp_id, cap.required_data),
                evidence_urls=list(cap.evidence_urls),
            )
        )
    return refs


def _build_workflow_nodes(
    plan_type: str,
    component_ids: list[str],
    capabilities_map: dict[str, CapabilityCapsule],
    scenario_name: str,
    gate_reason: str,
) -> list[WorkflowNode]:
    """为策略构建线性工作流节点链（场景自适应版）。"""
    nodes: list[WorkflowNode] = []
    total = len(component_ids)

    for i, comp_id in enumerate(component_ids):
        cap = capabilities_map[comp_id]
        node_id = f"{plan_type}-{i + 1:03d}"
        next_id = f"{plan_type}-{i + 2:03d}" if i < total - 1 else None
        next_ids: list[str] = [next_id] if next_id else []

        executor = _map_executor(cap.executor_type)
        human_gate = False
        node_gate_reason: str | None = None

        # human-approval 节点：统一设置 human_gate=true
        if comp_id == "human-approval":
            human_gate = True
            node_gate_reason = gate_reason

        # conservative 策略：rule-engine 节点额外设置人工复核 gate
        if plan_type == "conservative" and comp_id == "rule-engine":
            human_gate = True
            node_gate_reason = "保守方案要求人工复核规则结果"

        # 使用场景化节点名称
        node_name = scenario.get_node_name(scenario_name, comp_id, cap.name)

        nodes.append(
            WorkflowNode(
                id=node_id,
                name=node_name,
                component_id=comp_id,
                executor=executor,
                next_ids=next_ids,
                human_gate=human_gate,
                gate_reason=node_gate_reason,
            )
        )

    return nodes


def _build_expected_metrics(process: ProcessSpec) -> list[str]:
    """构建预期指标列表，使用 process.target_metrics + 可测指标名称。"""
    metrics: list[str] = list(process.target_metrics)
    extra = ["自动化率", "审批等待时间", "风险遗漏率"]
    for m in extra:
        if m not in metrics:
            metrics.append(m)
    return metrics


def _build_assumptions(process: ProcessSpec) -> list[str]:
    """构建假设列表，来源于 missing_information 和数据/系统缺失。"""
    assumptions: list[str] = []
    for info in process.missing_information:
        assumptions.append(f"待确认: {info}")
    if not process.available_data:
        assumptions.append("客户尚未提供可用数据源")
    if not process.existing_systems:
        assumptions.append("客户尚未明确现有系统")
    return assumptions


def _build_warnings() -> list[str]:
    """构建设计阶段警告列表。"""
    return [
        "预期指标需由成员 C 的 Runtime/ValueProof 实际验证，当前仅为指标名称而非结果。",
    ]


def _build_plan(
    process: ProcessSpec,
    plan_type: str,
    scenario_name: str,
    capabilities_map: dict[str, CapabilityCapsule],
    retrieved_map: dict[str, ComponentRef],
    gate_reason: str,
) -> SolutionPlan:
    """构建单套 SolutionPlan（场景自适应版）。"""
    component_ids = scenario.get_scenario_components(scenario_name, plan_type)

    selected_components = _build_component_refs(
        plan_type, component_ids, capabilities_map, retrieved_map, scenario_name
    )
    to_be_nodes = _build_workflow_nodes(
        plan_type, component_ids, capabilities_map, scenario_name, gate_reason
    )

    return SolutionPlan(
        schema_version="1.0",
        solution_id=f"{process.project_id}-{plan_type}-v1",
        source_project_id=process.project_id,
        plan_type=plan_type,
        name=_STRATEGY_NAMES[plan_type],
        summary=scenario.get_summary(scenario_name, plan_type),
        selected_components=selected_components,
        to_be_nodes=to_be_nodes,
        applied_constraints=list(process.constraints),
        implementation_steps=scenario.get_implementation_steps(scenario_name, process, plan_type),
        expected_metrics=_build_expected_metrics(process),
        assumptions=_build_assumptions(process),
        warnings=_build_warnings(),
        review_score=0.0,
    )


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


def compile_solution(process: ProcessSpec) -> SolutionBundle:
    """接收 ProcessSpec，生成包含三套方案的 SolutionBundle。

    Args:
        process: 成员 A 输出的流程规格。

    Returns:
        包含 conservative、balanced、innovative 三套 SolutionPlan 的 SolutionBundle。
    """
    # 识别业务场景
    scenario_name = scenario.identify_scenario(process)

    # 加载能力胶囊库
    capabilities = load_capabilities()
    capabilities_map = {cap.component_id: cap for cap in capabilities}

    # 调用 B-M1 检索器获取候选组件及匹配原因
    retrieved = retrieve_components(process, limit=15)
    retrieved_map = {ref.component_id: ref for ref in retrieved}

    # 获取场景化审批理由
    gate_reason = scenario.get_gate_reason(scenario_name, process)

    # 按策略顺序构建三套方案
    plan_types = ["conservative", "balanced", "innovative"]
    raw_plans = [
        _build_plan(
            process,
            pt,
            scenario_name,
            capabilities_map,
            retrieved_map,
            gate_reason,
        )
        for pt in plan_types
    ]

    # 对每套方案执行约束校验和 Reviewer 评分
    final_plans = []
    for plan in raw_plans:
        validation = validate_constraints(plan, list(process.constraints))
        review = review_solution(plan, process, validation)

        # 合并 warnings
        merged_warnings = list(plan.warnings)
        for w in validation.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)
        for w in review.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)

        updated_plan = plan.model_copy(update={
            "review_score": review.score,
            "warnings": merged_warnings,
        })
        final_plans.append(updated_plan)

    return SolutionBundle(project_id=process.project_id, plans=final_plans)
