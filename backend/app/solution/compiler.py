"""确定性 SolutionCompiler — 三套方案编译器。

输入 ProcessSpec，调用 B-M1 检索器，按 conservative/balanced/innovative
三种策略生成恰好三套 SolutionPlan，封装为 SolutionBundle。

不调用 LLM，不使用随机数，同一输入结果完全确定。
"""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    BusinessConstraint,
    ComponentRef,
    SolutionBundle,
    SolutionPlan,
    WorkflowNode,
)
from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities
from backend.app.solution.retriever import retrieve_components

# ---------------------------------------------------------------------------
# 策略定义
# ---------------------------------------------------------------------------

_STRATEGY_COMPONENTS: dict[str, list[str]] = {
    "conservative": [
        "document-extraction",
        "field-completeness-check",
        "rule-engine",
        "human-approval",
        "feishu-notification",
        "audit-log",
    ],
    "balanced": [
        "document-extraction",
        "field-completeness-check",
        "rule-engine",
        "anomaly-classification",
        "risk-scoring",
        "ticket-routing",
        "human-approval",
        "feishu-notification",
        "audit-log",
    ],
    "innovative": [
        "data-masking",
        "document-extraction",
        "enterprise-rag",
        "field-completeness-check",
        "rule-engine",
        "anomaly-classification",
        "risk-scoring",
        "local-model",
        "human-approval",
        "feishu-notification",
        "process-monitoring",
        "quality-dashboard",
        "audit-log",
    ],
}

_STRATEGY_NAMES: dict[str, str] = {
    "conservative": "稳健合规方案",
    "balanced": "效率平衡方案",
    "innovative": "智能重构方案",
}

_STRATEGY_SUMMARIES: dict[str, str] = {
    "conservative": (
        "优先低风险和人工可控，自动化范围最小，"
        "保留人工审批、人工复核和审计环节。"
    ),
    "balanced": (
        "风险、成本和自动化程度平衡，引入异常分类、风险评分和工单路由，"
        "保留高风险人工审批，作为 Demo 默认推荐方案。"
    ),
    "innovative": (
        "自动化和流程重构程度最高，引入知识检索、本地模型、流程监控和质量看板，"
        "仍保留人工审批环节，不违反硬约束。"
    ),
}

_STRATEGY_STEPS: dict[str, list[str]] = {
    "conservative": [
        "接入采购订单、收货记录和发票数据",
        "配置文档抽取和字段完整性检查规则",
        "配置业务规则引擎校验条件",
        "配置超过50万元人工审批流程",
        "接入飞书审批通知",
        "部署审计日志记录",
    ],
    "balanced": [
        "接入采购订单、收货记录和发票数据",
        "配置文档抽取和字段完整性检查规则",
        "配置业务规则引擎校验条件",
        "部署异常分类和风险评分模型",
        "配置低风险工单自动路由",
        "配置高风险人工审批流程",
        "接入飞书通知和审计日志",
    ],
    "innovative": [
        "接入采购订单、收货记录和发票数据",
        "部署数据脱敏组件保护敏感字段",
        "配置文档抽取和字段完整性检查规则",
        "接入企业知识库增强异常处理依据",
        "配置业务规则引擎和风险评分联合判断",
        "部署本地模型满足数据安全要求",
        "配置低风险自动处理和高风险人工审批",
        "接入流程监控和质量看板",
        "部署审计日志和反馈回流",
    ],
}


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _map_executor(executor_type: str) -> str:
    """将 CapabilityCapsule.executor_type 映射为 WorkflowNode.executor。"""
    if executor_type in ("ai", "human", "system"):
        return executor_type
    # hybrid → system（需人工 gate 时单独建立 human 节点）
    return "system"


def _build_component_refs(
    plan_type: str,
    component_ids: list[str],
    capabilities_map: dict[str, CapabilityCapsule],
    retrieved_map: dict[str, ComponentRef],
) -> list[ComponentRef]:
    """为策略构建 ComponentRef 列表，去重且顺序稳定。"""
    refs: list[ComponentRef] = []
    seen: set[str] = set()
    for comp_id in component_ids:
        if comp_id in seen:
            continue
        seen.add(comp_id)
        cap = capabilities_map[comp_id]
        # 优先使用检索器的 reason（更具体），否则使用策略理由
        if comp_id in retrieved_map:
            reason = retrieved_map[comp_id].reason
        else:
            reason = f"策略要求: {plan_type}方案必选组件"
        refs.append(
            ComponentRef(
                component_id=cap.component_id,
                name=cap.name,
                reason=reason,
                required_data=list(cap.required_data),
                evidence_urls=list(cap.evidence_urls),
            )
        )
    return refs


def _build_workflow_nodes(
    plan_type: str,
    component_ids: list[str],
    capabilities_map: dict[str, CapabilityCapsule],
    has_hard_approval: bool,
    approval_statement: str | None,
) -> list[WorkflowNode]:
    """为策略构建线性工作流节点链。"""
    nodes: list[WorkflowNode] = []
    total = len(component_ids)

    for i, comp_id in enumerate(component_ids):
        cap = capabilities_map[comp_id]
        node_id = f"{plan_type}-{i + 1:03d}"
        next_id = f"{plan_type}-{i + 2:03d}" if i < total - 1 else None
        next_ids: list[str] = [next_id] if next_id else []

        executor = _map_executor(cap.executor_type)
        human_gate = False
        gate_reason: str | None = None

        # human-approval 节点：有 hard approval 约束时设置 human_gate
        if comp_id == "human-approval" and has_hard_approval:
            human_gate = True
            gate_reason = approval_statement or "硬约束要求人工审批"

        # conservative 策略：rule-engine 节点额外设置人工复核 gate
        if plan_type == "conservative" and comp_id == "rule-engine":
            human_gate = True
            gate_reason = "保守方案要求人工复核规则结果"

        nodes.append(
            WorkflowNode(
                id=node_id,
                name=cap.name,
                component_id=comp_id,
                executor=executor,
                next_ids=next_ids,
                human_gate=human_gate,
                gate_reason=gate_reason,
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
    """构建警告列表，明确 Reviewer 尚未执行。"""
    return [
        "当前方案尚未经过 Reviewer 正式评分，review_score=0.0 为占位值。",
        "预期指标需由成员 C 的 Runtime/ValueProof 实际验证，当前仅为指标名称而非结果。",
    ]


def _build_plan(
    process: ProcessSpec,
    plan_type: str,
    capabilities_map: dict[str, CapabilityCapsule],
    retrieved_map: dict[str, ComponentRef],
    has_hard_approval: bool,
    approval_statement: str | None,
) -> SolutionPlan:
    """构建单套 SolutionPlan。"""
    component_ids = _STRATEGY_COMPONENTS[plan_type]

    selected_components = _build_component_refs(
        plan_type, component_ids, capabilities_map, retrieved_map
    )
    to_be_nodes = _build_workflow_nodes(
        plan_type, component_ids, capabilities_map, has_hard_approval, approval_statement
    )

    return SolutionPlan(
        schema_version="1.0",
        solution_id=f"{process.project_id}-{plan_type}-v1",
        source_project_id=process.project_id,
        plan_type=plan_type,
        name=_STRATEGY_NAMES[plan_type],
        summary=_STRATEGY_SUMMARIES[plan_type],
        selected_components=selected_components,
        to_be_nodes=to_be_nodes,
        applied_constraints=list(process.constraints),
        implementation_steps=list(_STRATEGY_STEPS[plan_type]),
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
    # 加载能力胶囊库
    capabilities = load_capabilities()
    capabilities_map = {cap.component_id: cap for cap in capabilities}

    # 调用 B-M1 检索器获取候选组件及匹配原因
    retrieved = retrieve_components(process, limit=15)
    retrieved_map = {ref.component_id: ref for ref in retrieved}

    # 检查硬审批约束
    has_hard_approval = any(
        c.type == "approval" and c.hard for c in process.constraints
    )
    approval_statement: str | None = None
    for c in process.constraints:
        if c.type == "approval" and c.hard:
            approval_statement = c.statement
            break

    # 按策略顺序构建三套方案
    plan_types = ["conservative", "balanced", "innovative"]
    plans = [
        _build_plan(
            process,
            pt,
            capabilities_map,
            retrieved_map,
            has_hard_approval,
            approval_statement,
        )
        for pt in plan_types
    ]

    return SolutionBundle(project_id=process.project_id, plans=plans)
