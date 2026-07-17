"""B 模块私有硬约束校验器。

设计阶段对 SolutionPlan 进行约束校验，不执行运行时订单级判断。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.solution import SolutionPlan


# ---------------------------------------------------------------------------
# 私有结果模型
# ---------------------------------------------------------------------------


class ConstraintCheck(BaseModel):
    """单条约束的校验结果。"""

    model_config = ConfigDict(extra="forbid")

    constraint_id: str
    constraint_type: str
    hard: bool
    status: Literal["passed", "failed", "unverifiable"]
    message: str
    required_component_ids: list[str] = Field(default_factory=list)
    missing_component_ids: list[str] = Field(default_factory=list)
    affected_node_ids: list[str] = Field(default_factory=list)


class ConstraintValidationResult(BaseModel):
    """约束校验总体结果。"""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    checks: list[ConstraintCheck] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    unverifiable_count: int = 0
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 私有校验辅助
# ---------------------------------------------------------------------------


def _has_component(plan: SolutionPlan, comp_id: str) -> bool:
    return any(c.component_id == comp_id for c in plan.selected_components)


def _human_gate_nodes(plan: SolutionPlan) -> list[tuple[str, str | None]]:
    """返回 (node_id, gate_reason) 列表。"""
    return [(n.id, n.gate_reason) for n in plan.to_be_nodes if n.human_gate]


def _check_approval(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """校验 approval 约束。"""
    required: list[str] = []
    missing: list[str] = []
    affected: list[str] = []

    gates = _human_gate_nodes(plan)

    if not gates:
        missing.append("human-approval")
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="approval",
            hard=constraint.hard,
            status="failed",
            message="方案中没有任何 human_gate=true 的节点，无法满足审批要求",
            required_component_ids=["human-approval"],
            missing_component_ids=missing,
            affected_node_ids=affected,
        )

    # 有 human_gate，检查 gate_reason
    for node_id, reason in gates:
        affected.append(node_id)
        if not reason:
            return ConstraintCheck(
                constraint_id=constraint.id,
                constraint_type="approval",
                hard=constraint.hard,
                status="failed",
                message=f"节点 {node_id} 的 human_gate=true 但 gate_reason 为空",
                required_component_ids=["human-approval"],
                missing_component_ids=[],
                affected_node_ids=affected,
            )

    # 检查 gate_reason 是否体现约束 statement 或阈值
    threshold = constraint.parameters.get("amount_threshold")
    all_reasons = " ".join(r for _, r in gates if r)

    if threshold is not None:
        threshold_str = str(threshold)
        if threshold_str in all_reasons or constraint.statement in all_reasons:
            return ConstraintCheck(
                constraint_id=constraint.id,
                constraint_type="approval",
                hard=constraint.hard,
                status="passed",
                message="方案包含 human_gate 且 gate_reason 体现了审批阈值或约束声明",
                required_component_ids=["human-approval"],
                missing_component_ids=[],
                affected_node_ids=affected,
            )
        else:
            return ConstraintCheck(
                constraint_id=constraint.id,
                constraint_type="approval",
                hard=constraint.hard,
                status="failed",
                message=f"gate_reason 未体现审批阈值({threshold})或约束声明",
                required_component_ids=["human-approval"],
                missing_component_ids=[],
                affected_node_ids=affected,
            )

    # 无 threshold，只要有 human_gate + 非空 reason 即通过
    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="approval",
        hard=constraint.hard,
        status="passed",
        message="方案包含 human_gate 且 gate_reason 非空",
        required_component_ids=["human-approval"],
        missing_component_ids=[],
        affected_node_ids=affected,
    )


def _check_security(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """校验 security 约束。"""
    stmt = constraint.statement
    required: list[str] = []
    missing: list[str] = []

    needs_audit = any(kw in stmt for kw in ["审计", "留痕", "访问记录", "安全追踪", "风险记录", "审计留痕"])
    needs_local = any(kw in stmt for kw in ["本地部署", "私有化", "不出域", "禁止外传", "本地处理", "私有部署"])
    needs_masking = any(kw in stmt for kw in ["敏感信息", "隐私", "脱敏", "敏感数据", "个人信息"])

    if needs_audit:
        required.append("audit-log")
        if not _has_component(plan, "audit-log"):
            missing.append("audit-log")
    if needs_local:
        required.append("local-model")
        if not _has_component(plan, "local-model"):
            missing.append("local-model")
    if needs_masking:
        required.append("data-masking")
        if not _has_component(plan, "data-masking"):
            missing.append("data-masking")

    if not required:
        # statement 过于抽象，无法映射到具体规则
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="security",
            hard=constraint.hard,
            status="unverifiable",
            message="安全约束声明过于抽象，无法映射到具体组件要求",
            required_component_ids=[],
            missing_component_ids=[],
            affected_node_ids=[],
        )

    if missing:
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="security",
            hard=constraint.hard,
            status="failed",
            message=f"缺少安全所需组件: {', '.join(missing)}",
            required_component_ids=required,
            missing_component_ids=missing,
            affected_node_ids=[],
        )

    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="security",
        hard=constraint.hard,
        status="passed",
        message="方案包含安全约束所需的全部组件",
        required_component_ids=required,
        missing_component_ids=[],
        affected_node_ids=[],
    )


def _check_data(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """校验 data 约束。"""
    stmt = constraint.statement
    required: list[str] = []
    missing: list[str] = []

    needs_masking = any(kw in stmt for kw in ["脱敏", "敏感数据", "隐私", "个人信息", "敏感信息"])
    needs_local = any(kw in stmt for kw in ["数据不出域", "本地处理", "私有部署", "本地部署", "不出域"])

    if needs_masking:
        required.append("data-masking")
        if not _has_component(plan, "data-masking"):
            missing.append("data-masking")
    if needs_local:
        required.append("local-model")
        if not _has_component(plan, "local-model"):
            missing.append("local-model")

    if not required:
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="data",
            hard=constraint.hard,
            status="unverifiable",
            message="数据约束要求不明确，无法映射到具体组件",
            required_component_ids=[],
            missing_component_ids=[],
            affected_node_ids=[],
        )

    if missing:
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="data",
            hard=constraint.hard,
            status="failed",
            message=f"缺少数据约束所需组件: {', '.join(missing)}",
            required_component_ids=required,
            missing_component_ids=missing,
            affected_node_ids=[],
        )

    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="data",
        hard=constraint.hard,
        status="passed",
        message="方案包含数据约束所需的全部组件",
        required_component_ids=required,
        missing_component_ids=[],
        affected_node_ids=[],
    )


def _check_risk(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """校验 risk 约束。"""
    stmt = constraint.statement
    required: list[str] = []
    missing: list[str] = []

    needs_scoring = any(kw in stmt for kw in ["风险评分", "高风险识别", "异常风险", "风险"])
    needs_human = any(kw in stmt for kw in ["高风险人工", "人工复核", "人工审批", "人工确认"])
    needs_audit = any(kw in stmt for kw in ["审计", "留痕", "记录"])

    if needs_scoring:
        required.append("risk-scoring")
        if not _has_component(plan, "risk-scoring"):
            missing.append("risk-scoring")
    if needs_human:
        required.append("human-approval")
        if not _has_component(plan, "human-approval"):
            missing.append("human-approval")
        # 还需要 human_gate
        if not _human_gate_nodes(plan):
            missing.append("human_gate")
    if needs_audit:
        required.append("audit-log")
        if not _has_component(plan, "audit-log"):
            missing.append("audit-log")

    if not required:
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="risk",
            hard=constraint.hard,
            status="unverifiable",
            message="风险约束要求不明确，无法映射到具体组件",
            required_component_ids=[],
            missing_component_ids=[],
            affected_node_ids=[],
        )

    if missing:
        return ConstraintCheck(
            constraint_id=constraint.id,
            constraint_type="risk",
            hard=constraint.hard,
            status="failed",
            message=f"缺少风险约束所需组件或条件: {', '.join(missing)}",
            required_component_ids=required,
            missing_component_ids=missing,
            affected_node_ids=[],
        )

    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="risk",
        hard=constraint.hard,
        status="passed",
        message="方案包含风险约束所需的全部组件",
        required_component_ids=required,
        missing_component_ids=[],
        affected_node_ids=[],
    )


def _check_budget(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """budget 约束：当前合同无成本字段，始终 unverifiable。"""
    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="budget",
        hard=constraint.hard,
        status="unverifiable",
        message="公共合同 SolutionPlan 缺少可验证的预算/成本字段，设计阶段无法验证",
        required_component_ids=[],
        missing_component_ids=[],
        affected_node_ids=[],
    )


def _check_time(
    constraint: BusinessConstraint, plan: SolutionPlan
) -> ConstraintCheck:
    """time 约束：当前合同无时间字段，始终 unverifiable。"""
    return ConstraintCheck(
        constraint_id=constraint.id,
        constraint_type="time",
        hard=constraint.hard,
        status="unverifiable",
        message="公共合同 SolutionPlan 缺少可验证的时间/周期字段，设计阶段无法验证",
        required_component_ids=[],
        missing_component_ids=[],
        affected_node_ids=[],
    )


_CHECKERS = {
    "approval": _check_approval,
    "security": _check_security,
    "data": _check_data,
    "risk": _check_risk,
    "budget": _check_budget,
    "time": _check_time,
}


# ---------------------------------------------------------------------------
# 公开函数
# ---------------------------------------------------------------------------


def validate_constraints(
    plan: SolutionPlan,
    constraints: list[BusinessConstraint],
) -> ConstraintValidationResult:
    """对 SolutionPlan 进行设计阶段硬约束校验。

    Args:
        plan: 待校验的方案。
        constraints: 客户约束列表。

    Returns:
        ConstraintValidationResult，包含每条约束的检查结果和总体有效性。
    """
    checks: list[ConstraintCheck] = []
    warnings: list[str] = []

    for constraint in constraints:
        checker = _CHECKERS.get(constraint.type)
        if checker is None:
            checks.append(ConstraintCheck(
                constraint_id=constraint.id,
                constraint_type=constraint.type,
                hard=constraint.hard,
                status="unverifiable",
                message=f"未知的约束类型: {constraint.type}",
                required_component_ids=[],
                missing_component_ids=[],
                affected_node_ids=[],
            ))
            continue
        checks.append(checker(constraint, plan))

    passed_count = sum(1 for c in checks if c.status == "passed")
    failed_count = sum(1 for c in checks if c.status == "failed")
    unverifiable_count = sum(1 for c in checks if c.status == "unverifiable")

    # 总体有效性
    has_hard_failed = any(c.hard and c.status == "failed" for c in checks)
    has_hard_unverifiable = any(c.hard and c.status == "unverifiable" for c in checks)
    is_valid = not has_hard_failed and not has_hard_unverifiable

    # warnings
    for c in checks:
        if not c.hard and c.status in ("failed", "unverifiable"):
            warnings.append(f"soft 约束 {c.constraint_id} ({c.constraint_type}): {c.message}")
    if has_hard_failed:
        warnings.append("存在 hard 约束校验失败，方案需修改后重新评审")
    if has_hard_unverifiable:
        warnings.append("存在 hard 约束无法在设计阶段验证，需 Runtime 阶段确认")

    return ConstraintValidationResult(
        is_valid=is_valid,
        checks=checks,
        passed_count=passed_count,
        failed_count=failed_count,
        unverifiable_count=unverifiable_count,
        warnings=warnings,
    )
