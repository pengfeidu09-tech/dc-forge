"""确定性能力胶囊检索器。

基于关键词和字段匹配的确定性评分检索，不调用 LLM 或外部 API。
后续可替换为 Embedding、Hybrid Search 和 Rerank。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import ComponentRef
from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities


@dataclass
class _ScoredCapsule:
    """内部评分结果，不对外导出。"""

    capsule: CapabilityCapsule
    score: int
    reasons: list[str] = field(default_factory=list)


def _industry_matches(process_industry: str, cap_industries: list[str]) -> bool:
    """检查行业是否匹配（支持子串匹配以兼容 '企业采购' vs '采购'）。"""
    for ind in cap_industries:
        if ind and (ind in process_industry or process_industry in ind):
            return True
    return False


def _department_matches(process_dept: str, cap_depts: list[str]) -> bool:
    """检查部门是否匹配。"""
    for dept in cap_depts:
        if dept and (dept in process_dept or process_dept in dept):
            return True
    return False


def _tag_matches(
    tags: list[str], pain_texts: list[str], business_goal: str, target_metrics: list[str]
) -> list[str]:
    """返回与痛点/目标/指标匹配的 tag 列表。"""
    matched: list[str] = []
    all_text = " ".join(pain_texts + [business_goal] + target_metrics)
    for tag in tags:
        if tag and tag in all_text:
            matched.append(tag)
    return matched


def _data_matches(cap_data: list[str], available_data: list[str]) -> list[str]:
    """返回与可用数据匹配的 required_data 列表。"""
    matched: list[str] = []
    for req in cap_data:
        for avail in available_data:
            if req and avail and (req in avail or avail in req):
                matched.append(req)
                break
    return matched


def _constraint_type_matches(
    cap_types: list[str], process_constraint_types: set[str]
) -> list[str]:
    """返回与约束类型匹配的 supported_constraint_types 列表。"""
    return [t for t in cap_types if t in process_constraint_types]


def _score_capsule(
    process: ProcessSpec, cap: CapabilityCapsule
) -> _ScoredCapsule:
    """对单个胶囊评分，返回评分结果和匹配原因。"""
    score = 0
    reasons: list[str] = []

    # 行业匹配 +3
    if _industry_matches(process.industry, cap.applicable_industries):
        score += 3
        reasons.append(f"行业匹配: {process.industry}")

    # 部门匹配 +2
    if _department_matches(process.department, cap.applicable_departments):
        score += 2
        reasons.append(f"部门匹配: {process.department}")

    # problem_tags 与痛点/目标/指标匹配 每项 +2
    pain_texts = [p.description for p in process.pain_points]
    matched_tags = _tag_matches(
        cap.problem_tags, pain_texts, process.business_goal, process.target_metrics
    )
    for tag in matched_tags:
        score += 2
    if matched_tags:
        reasons.append(f"痛点/目标匹配: {', '.join(matched_tags)}")

    # required_data 与 available_data 匹配 每项 +1
    matched_data = _data_matches(cap.required_data, process.available_data)
    for _ in matched_data:
        score += 1
    if matched_data:
        reasons.append(f"数据匹配: {', '.join(matched_data)}")

    # 约束类型集合
    process_constraint_types = {c.type for c in process.constraints}

    # supported_constraint_types 与约束类型匹配 每项 +2
    matched_types = _constraint_type_matches(
        cap.supported_constraint_types, process_constraint_types
    )
    for _ in matched_types:
        score += 2
    if matched_types:
        reasons.append(f"约束匹配: {', '.join(matched_types)}")

    # 特殊加权：approval 约束 + human-approval → 额外 +5
    if "approval" in process_constraint_types and cap.component_id == "human-approval":
        score += 5
        reasons.append("审批约束优先匹配: human-approval")

    # 特殊加权：risk 约束 + risk-scoring/audit-log → 额外 +3
    if "risk" in process_constraint_types and cap.component_id in (
        "risk-scoring",
        "audit-log",
    ):
        score += 3
        reasons.append(f"风险约束优先匹配: {cap.component_id}")

    return _ScoredCapsule(capsule=cap, score=score, reasons=reasons)


def _to_component_ref(scored: _ScoredCapsule) -> ComponentRef:
    """将评分结果转换为公共合同 ComponentRef。"""
    cap = scored.capsule
    reason = "; ".join(scored.reasons) if scored.reasons else "综合匹配"
    return ComponentRef(
        component_id=cap.component_id,
        name=cap.name,
        reason=reason,
        required_data=list(cap.required_data),
        evidence_urls=list(cap.evidence_urls),
    )


def retrieve_components(
    process: ProcessSpec,
    capabilities: list[CapabilityCapsule] | None = None,
    limit: int = 5,
) -> list[ComponentRef]:
    """从能力胶囊库中检索匹配的候选组件。

    Args:
        process: 成员 A 输出的流程规格。
        capabilities: 能力胶囊列表，默认从 data/capabilities.json 加载。
        limit: 返回最大数量，小于等于 0 时返回空列表。

    Returns:
        按 score 降序排列的 ComponentRef 列表，同分按 component_id 升序。
    """
    if limit <= 0:
        return []

    if capabilities is None:
        capabilities = load_capabilities()

    # 评分
    scored_list: list[_ScoredCapsule] = [
        _score_capsule(process, cap) for cap in capabilities
    ]

    # 只保留 score > 0
    positive = [s for s in scored_list if s.score > 0]

    # 按 score 降序，同分按 component_id 升序（保证稳定）
    positive.sort(key=lambda s: (-s.score, s.capsule.component_id))

    # 截取 limit
    top = positive[:limit]

    return [_to_component_ref(s) for s in top]
