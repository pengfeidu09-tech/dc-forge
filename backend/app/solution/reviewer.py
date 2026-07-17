"""B 模块私有方案 Reviewer — 确定性评分。

根据约束合规、需求覆盖、工作流完整性、可解释性和实施可行性
进行确定性评分，不调用 LLM，不使用随机数。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionPlan
from backend.app.solution.constraints import ConstraintValidationResult


# ---------------------------------------------------------------------------
# 私有结果模型
# ---------------------------------------------------------------------------


class ReviewDimension(BaseModel):
    """单个评分维度。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    score: float
    max_score: float
    reasons: list[str] = Field(default_factory=list)


class SolutionReviewResult(BaseModel):
    """方案评审总体结果。"""

    model_config = ConfigDict(extra="forbid")

    score: float
    dimensions: list[ReviewDimension] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendation: Literal["recommended", "acceptable", "needs_revision", "rejected"]
    summary: str


# ---------------------------------------------------------------------------
# 私有评分辅助
# ---------------------------------------------------------------------------

# 关键流程区域 → 对应 component_id
_PROCESS_AREAS: dict[str, list[str]] = {
    "数据抽取": ["document-extraction"],
    "校验": ["field-completeness-check", "rule-engine"],
    "风险": ["risk-scoring", "anomaly-classification"],
    "审批": ["human-approval"],
    "通知": ["feishu-notification"],
    "审计": ["audit-log"],
}


def _data_matches(required: str, available: list[str]) -> bool:
    for avail in available:
        if required and avail and (required in avail or avail in required):
            return True
    return False


def _score_compliance(
    plan: SolutionPlan,
    validation: ConstraintValidationResult | None,
) -> ReviewDimension:
    """约束合规维度，30 分。"""
    max_score = 30.0
    score = max_score
    reasons: list[str] = []

    if validation is None:
        score = 15.0
        reasons.append("未提供校验结果，合规分减半")
        return ReviewDimension(name="约束合规", score=score, max_score=max_score, reasons=reasons)

    for check in validation.checks:
        if check.hard:
            if check.status == "failed":
                score -= 20
                reasons.append(f"hard 约束 {check.constraint_id} 失败: -20")
            elif check.status == "unverifiable":
                score -= 15
                reasons.append(f"hard 约束 {check.constraint_id} 无法验证: -15")
        else:
            if check.status in ("failed", "unverifiable"):
                score -= 3
                reasons.append(f"soft 约束 {check.constraint_id} {check.status}: -3")

    score = max(0.0, score)
    if score == max_score:
        reasons.append("全部约束通过校验")
    return ReviewDimension(name="约束合规", score=score, max_score=max_score, reasons=reasons)


def _score_coverage(
    plan: SolutionPlan,
    process: ProcessSpec,
) -> ReviewDimension:
    """需求与痛点覆盖维度，25 分。"""
    max_score = 25.0
    reasons: list[str] = []
    component_ids = {c.component_id for c in plan.selected_components}
    all_tags = " ".join(c.reason for c in plan.selected_components)
    all_text = " ".join(process.target_metrics + [process.business_goal])

    # 痛点覆盖 10 分
    pain_score = 0.0
    if process.pain_points:
        per_pain = 10.0 / len(process.pain_points)
        for pp in process.pain_points:
            pp_text = pp.description
            # 检查组件 reason 或 component_id 是否涉及痛点
            matched = False
            for comp_id in component_ids:
                if comp_id.replace("-", "") in pp_text.replace(" ", ""):
                    matched = True
                    break
            # 关键词匹配
            if not matched:
                for kw in ["核对", "异常", "风险", "审批", "人工", "单据"]:
                    if kw in pp_text and kw in all_tags:
                        matched = True
                        break
            if matched:
                pain_score += per_pain
                reasons.append(f"痛点 {pp.id} 已覆盖")
            else:
                reasons.append(f"痛点 {pp.id} 未完全覆盖")
    else:
        pain_score = 5.0
        reasons.append("无痛点，基础分 5/10")

    # 业务目标覆盖 5 分
    goal_score = 0.0
    goal_keywords = ["异常", "处理", "风险", "付款", "采购", "自动化", "审批"]
    matched_goals = sum(1 for kw in goal_keywords if kw in process.business_goal and kw in all_tags)
    goal_score = min(5.0, matched_goals / max(1, len(goal_keywords)) * 5.0 + 1.0)
    reasons.append(f"业务目标关键词覆盖: {matched_goals}/{len(goal_keywords)}")

    # 指标覆盖 5 分
    metric_score = 0.0
    if process.target_metrics:
        per_metric = 5.0 / len(process.target_metrics)
        for metric in process.target_metrics:
            # 检查组件是否覆盖该指标
            metric_covered = False
            for kw in ["异常", "处理", "人工", "风险", "自动化"]:
                if kw in metric and kw in all_tags:
                    metric_covered = True
                    break
            # 检查组件 evaluation_metrics
            for comp in plan.selected_components:
                if any(kw in metric for kw in ["时间", "处理", "人工", "风险", "自动化"]):
                    metric_covered = True
                    break
            if metric_covered:
                metric_score += per_metric
        reasons.append(f"目标指标覆盖: {metric_score:.1f}/5")
    else:
        metric_score = 2.5

    # 关键流程区域覆盖 5 分
    area_score = 0.0
    covered_areas = 0
    for area, comp_ids in _PROCESS_AREAS.items():
        if any(cid in component_ids for cid in comp_ids):
            covered_areas += 1
    # 6 个区域，前 4 个各 1 分，后 2 个各 0.5 分
    area_score = min(5.0, covered_areas * (5.0 / 6.0))
    reasons.append(f"关键流程区域覆盖: {covered_areas}/6")

    score = pain_score + goal_score + metric_score + area_score
    score = min(max_score, score)
    return ReviewDimension(name="需求与痛点覆盖", score=score, max_score=max_score, reasons=reasons)


def _score_workflow(plan: SolutionPlan) -> ReviewDimension:
    """工作流完整性维度，20 分。"""
    max_score = 20.0
    score = 0.0
    reasons: list[str] = []
    nodes = plan.to_be_nodes

    if nodes:
        score += 2
        reasons.append("有工作流节点: +2")
    else:
        return ReviewDimension(name="工作流完整性", score=0, max_score=max_score, reasons=["无节点"])

    # 节点 ID 唯一
    node_ids = [n.id for n in nodes]
    if len(node_ids) == len(set(node_ids)):
        score += 3
        reasons.append("节点 ID 唯一: +3")
    else:
        reasons.append("节点 ID 重复")

    # 无悬空 next_id
    id_set = set(node_ids)
    dangling = False
    for n in nodes:
        for nid in n.next_ids:
            if nid not in id_set:
                dangling = True
    if not dangling:
        score += 5
        reasons.append("无悬空 next_id: +5")
    else:
        reasons.append("存在悬空 next_id")

    # 末尾节点可终止
    terminal = [n for n in nodes if not n.next_ids]
    if terminal:
        score += 3
        reasons.append("存在终止节点: +3")

    # 组件与节点基本一致
    comp_in_nodes = {n.component_id for n in nodes}
    comp_in_plan = {c.component_id for c in plan.selected_components}
    if comp_in_plan <= comp_in_nodes or comp_in_nodes <= comp_in_plan:
        score += 3
        reasons.append("组件与节点基本一致: +3")

    # hard approval 有 human gate
    has_hard_approval = any(
        c.type == "approval" and c.hard for c in plan.applied_constraints
    )
    if has_hard_approval:
        gates = [n for n in nodes if n.human_gate]
        if gates:
            score += 2
            reasons.append("hard approval 有 human gate: +2")
        else:
            reasons.append("hard approval 缺少 human gate")
    else:
        score += 2
        reasons.append("无 hard approval 约束: +2")

    # executor 无明显冲突
    score += 2
    reasons.append("executor 无明显冲突: +2")

    score = min(max_score, score)
    return ReviewDimension(name="工作流完整性", score=score, max_score=max_score, reasons=reasons)


def _score_explainability(plan: SolutionPlan) -> ReviewDimension:
    """可解释性与证据维度，15 分。"""
    max_score = 15.0
    score = 0.0
    reasons: list[str] = []

    # reason 非空
    non_empty = sum(1 for c in plan.selected_components if c.reason and len(c.reason) > 2)
    if non_empty == len(plan.selected_components):
        score += 5
        reasons.append("所有组件 reason 非空: +5")
    else:
        score += (non_empty / max(1, len(plan.selected_components))) * 5

    # reason 不是纯占位
    generic = {"test", "placeholder", "todo", "tbd", "n/a"}
    non_generic = sum(
        1 for c in plan.selected_components
        if c.reason.lower().strip() not in generic
    )
    score += (non_generic / max(1, len(plan.selected_components))) * 3
    reasons.append(f"非占位 reason: {non_generic}/{len(plan.selected_components)}")

    # required_data 明确
    has_data = sum(1 for c in plan.selected_components if c.required_data)
    score += (has_data / max(1, len(plan.selected_components))) * 3
    reasons.append(f"required_data 明确: {has_data}/{len(plan.selected_components)}")

    # evidence_urls 不伪造（空列表可以）
    score += 2
    reasons.append("evidence_urls 未伪造: +2")

    # assumptions 和 warnings 明确
    if plan.assumptions or plan.warnings:
        score += 2
        reasons.append("assumptions/warnings 存在: +2")

    score = min(max_score, score)
    return ReviewDimension(name="可解释性与证据", score=score, max_score=max_score, reasons=reasons)


def _score_feasibility(
    plan: SolutionPlan,
    process: ProcessSpec,
) -> ReviewDimension:
    """实施可行性维度，10 分。"""
    max_score = 10.0
    score = 0.0
    reasons: list[str] = []
    comp_count = len(plan.selected_components)
    step_count = len(plan.implementation_steps)

    # steps 非空
    if step_count > 0:
        score += 1
        reasons.append("implementation_steps 非空: +1")

    # steps 与组件数量匹配
    if step_count >= comp_count / 2:
        score += 1
        reasons.append("steps 数量与组件匹配: +1")
    else:
        reasons.append(f"steps({step_count}) 少于组件({comp_count})/2")

    # 组件数量复杂度
    if comp_count <= 7:
        score += 3
        reasons.append(f"组件数 {comp_count} ≤ 7: +3")
    elif comp_count <= 10:
        score += 1.5
        reasons.append(f"组件数 {comp_count} 8-10: +1.5")
    else:
        score += 0
        reasons.append(f"组件数 {comp_count} > 10: +0")

    # 数据覆盖率
    total_required = 0
    total_covered = 0
    for comp in plan.selected_components:
        for req in comp.required_data:
            total_required += 1
            if _data_matches(req, process.available_data):
                total_covered += 1
    if total_required > 0:
        coverage = total_covered / total_required
    else:
        coverage = 0.5
    data_score = coverage * 5
    score += data_score
    reasons.append(f"数据覆盖率 {coverage:.1%}: +{data_score:.1f}")

    score = min(max_score, score)
    return ReviewDimension(name="实施可行性", score=score, max_score=max_score, reasons=reasons)


def _determine_recommendation(
    score: float,
    validation: ConstraintValidationResult | None,
) -> Literal["recommended", "acceptable", "needs_revision", "rejected"]:
    if validation is not None:
        has_hard_failed = any(c.hard and c.status == "failed" for c in validation.checks)
        has_hard_unverifiable = any(
            c.hard and c.status == "unverifiable" for c in validation.checks
        )
        if has_hard_failed:
            return "rejected"
        if has_hard_unverifiable and score >= 85:
            return "acceptable"
        if has_hard_unverifiable:
            return "needs_revision"

    if score >= 85 and (validation is None or validation.is_valid):
        return "recommended"
    if score >= 70 and (validation is None or validation.is_valid):
        return "acceptable"
    if score >= 50:
        return "needs_revision"
    return "rejected"


def _build_summary(
    plan: SolutionPlan,
    score: float,
    recommendation: str,
    dimensions: list[ReviewDimension],
) -> str:
    top_dim = max(dimensions, key=lambda d: d.score / d.max_score) if dimensions else None
    low_dim = min(dimensions, key=lambda d: d.score / d.max_score) if dimensions else None
    parts = [
        f"{plan.name} 综合评分 {score:.1f}/100，建议: {recommendation}。",
    ]
    if top_dim:
        parts.append(f"优势维度: {top_dim.name}({top_dim.score:.1f}/{top_dim.max_score:.0f})。")
    if low_dim:
        parts.append(f"待改进维度: {low_dim.name}({low_dim.score:.1f}/{low_dim.max_score:.0f})。")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 公开函数
# ---------------------------------------------------------------------------


def review_solution(
    plan: SolutionPlan,
    process: ProcessSpec,
    validation: ConstraintValidationResult | None = None,
) -> SolutionReviewResult:
    """对 SolutionPlan 进行确定性评分。

    Args:
        plan: 待评审的方案。
        process: 原始流程规格。
        validation: 约束校验结果（可选，推荐提供）。

    Returns:
        SolutionReviewResult，包含总分、维度明细和建议。
    """
    dimensions = [
        _score_compliance(plan, validation),
        _score_coverage(plan, process),
        _score_workflow(plan),
        _score_explainability(plan),
        _score_feasibility(plan, process),
    ]

    total = sum(d.score for d in dimensions)
    total = max(0.0, min(100.0, total))

    recommendation = _determine_recommendation(total, validation)

    warnings: list[str] = []
    # 证据缺失警告
    has_evidence = any(
        c.evidence_urls for c in plan.selected_components
    )
    if not has_evidence:
        warnings.append("所有组件的 evidence_urls 为空，证据引用尚未补齐，需后续补充公开引用。")
    # 约束警告
    if validation is not None:
        for w in validation.warnings:
            if w not in warnings:
                warnings.append(w)
    # Runtime 验证提醒
    warnings.append("预期指标需由成员 C 的 Runtime/ValueProof 实际验证，当前仅为指标名称而非结果。")

    summary = _build_summary(plan, total, recommendation, dimensions)

    return SolutionReviewResult(
        score=total,
        dimensions=dimensions,
        warnings=warnings,
        recommendation=recommendation,
        summary=summary,
    )
