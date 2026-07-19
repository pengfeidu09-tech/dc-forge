"""B 模块增量重编译器。

接收 RecompileRequest，合并约束，重新编译同一策略方案，
补充新硬约束所需组件，计算 Diff，返回 RecompileResult。
"""

from __future__ import annotations

import re

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    ComponentRef,
    RecompileRequest,
    RecompileResult,
    SolutionPlan,
    WorkflowNode,
)
from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities
from backend.app.solution.compiler import (
    _build_component_refs,
    _build_workflow_nodes,
    compile_solution,
)
from backend.app.solution.constraints import validate_constraints
from backend.app.solution.reviewer import review_solution
from backend.app.solution import scenario


# ---------------------------------------------------------------------------
# 约束合并
# ---------------------------------------------------------------------------


def _merge_constraints(
    old: list[BusinessConstraint],
    new: list[BusinessConstraint],
) -> list[BusinessConstraint]:
    """按 id 合并约束，同 id 新覆盖旧，保持确定性顺序。"""
    by_id: dict[str, BusinessConstraint] = {}
    for c in old:
        by_id[c.id] = c
    for c in new:
        by_id[c.id] = c
    return list(by_id.values())


# ---------------------------------------------------------------------------
# 新约束所需组件
# ---------------------------------------------------------------------------


def _required_components_for_constraints(
    constraints: list[BusinessConstraint],
) -> list[str]:
    """根据约束类型和 statement 确定所需组件 ID 列表。"""
    required: list[str] = []
    seen: set[str] = set()

    def _add(cid: str) -> None:
        if cid not in seen:
            seen.add(cid)
            required.append(cid)

    for c in constraints:
        stmt = c.statement
        if c.type == "approval":
            _add("human-approval")
            _add("audit-log")
        elif c.type == "security":
            if any(kw in stmt for kw in ["审计", "留痕", "访问记录", "安全追踪", "风险记录"]):
                _add("audit-log")
            if any(kw in stmt for kw in ["本地", "不出域", "禁止外传", "私有"]):
                _add("local-model")
            if any(kw in stmt for kw in ["敏感", "隐私", "脱敏"]):
                _add("data-masking")
        elif c.type == "data":
            if any(kw in stmt for kw in ["脱敏", "敏感", "隐私", "个人信息"]):
                _add("data-masking")
            if any(kw in stmt for kw in ["不出域", "本地", "私有"]):
                _add("local-model")
        elif c.type == "risk":
            if any(kw in stmt for kw in ["风险", "异常"]):
                _add("risk-scoring")
            if any(kw in stmt for kw in ["人工", "复核", "审批"]):
                _add("human-approval")
            if any(kw in stmt for kw in ["审计", "留痕", "记录"]):
                _add("audit-log")
        # budget/time: 不添加组件

    return required


# ---------------------------------------------------------------------------
# 版本递增
# ---------------------------------------------------------------------------


def _increment_version(solution_id: str) -> str:
    """递增 solution_id 的版本号。"""
    match = re.match(r"^(.+)-v(\d+)$", solution_id)
    if match:
        base, ver = match.group(1), int(match.group(2))
        return f"{base}-v{ver + 1}"
    return f"{solution_id}-v2"


# ---------------------------------------------------------------------------
# Diff 计算
# ---------------------------------------------------------------------------


def _diff_components(
    old_plan: SolutionPlan,
    new_plan: SolutionPlan,
) -> tuple[list[str], list[str]]:
    old_ids = {c.component_id for c in old_plan.selected_components}
    new_ids = {c.component_id for c in new_plan.selected_components}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    return added, removed


def _diff_nodes(
    old_plan: SolutionPlan,
    new_plan: SolutionPlan,
) -> list[str]:
    old_nodes = {n.id: n for n in old_plan.to_be_nodes}
    new_nodes = {n.id: n for n in new_plan.to_be_nodes}

    changed: set[str] = set()
    # 新增节点
    changed |= set(new_nodes) - set(old_nodes)
    # 删除节点
    changed |= set(old_nodes) - set(new_nodes)
    # 修改节点
    for nid in set(new_nodes) & set(old_nodes):
        if new_nodes[nid].model_dump() != old_nodes[nid].model_dump():
            changed.add(nid)

    return sorted(changed)


# ---------------------------------------------------------------------------
# 工作流重建
# ---------------------------------------------------------------------------

# 前置处理组件（应放在人工审批之前）
_PREPROCESS_COMPONENTS = {"data-masking", "local-model", "enterprise-rag"}


def _rebuild_workflow(
    plan_type: str,
    component_ids: list[str],
    capabilities_map: dict[str, CapabilityCapsule],
    scenario_name: str,
    gate_reason: str,
) -> list[WorkflowNode]:
    """用扩展后的组件列表重建工作流。"""
    return _build_workflow_nodes(
        plan_type, component_ids, capabilities_map, scenario_name, gate_reason
    )


def _reorder_components(component_ids: list[str]) -> list[str]:
    """将前置处理组件排在前面，保持其余顺序稳定。"""
    preprocess = [c for c in component_ids if c in _PREPROCESS_COMPONENTS]
    rest = [c for c in component_ids if c not in _PREPROCESS_COMPONENTS]
    return preprocess + rest


# ---------------------------------------------------------------------------
# 公开函数
# ---------------------------------------------------------------------------


def recompile_solution(request: RecompileRequest) -> RecompileResult:
    """增量重编译：合并约束 → 重新编译 → 补充组件 → 校验评分 → 计算 Diff。

    Args:
        request: 包含原 ProcessSpec、已选 SolutionPlan 和新约束。

    Returns:
        RecompileResult，包含新方案和变化 Diff。
    """
    old_plan = request.selected_solution
    old_process = request.process

    # 1. 合并约束
    merged_constraints = _merge_constraints(
        list(old_process.constraints), list(request.new_constraints)
    )

    # 2. 创建更新后的 ProcessSpec（不修改原对象）
    updated_process = old_process.model_copy(update={"constraints": merged_constraints})

    # 3. 重新编译
    new_bundle = compile_solution(updated_process)

    # 4. 选择相同策略的方案
    new_plan = next(
        p for p in new_bundle.plans if p.plan_type == old_plan.plan_type
    )

    # 5. 检查新硬约束所需组件
    required = _required_components_for_constraints(list(request.new_constraints))
    existing_ids = {c.component_id for c in new_plan.selected_components}
    missing = [cid for cid in required if cid not in existing_ids]

    has_real_changes = len(request.new_constraints) > 0 or bool(missing)

    if missing:
        # 需要补充组件
        capabilities = load_capabilities()
        capabilities_map = {cap.component_id: cap for cap in capabilities}

        # 扩展组件列表
        extended_ids = [c.component_id for c in new_plan.selected_components]
        for cid in missing:
            if cid not in extended_ids:
                extended_ids.append(cid)

        # 重排序：前置处理组件在前
        extended_ids = _reorder_components(extended_ids)

        # 识别场景和审批理由
        recompile_scenario = scenario.identify_scenario(updated_process)
        recompile_gate_reason = scenario.get_gate_reason(recompile_scenario, updated_process)

        # 重建组件引用
        # 对新增组件使用约束触发原因
        from backend.app.solution.retriever import retrieve_components
        retrieved = retrieve_components(updated_process, limit=15)
        retrieved_map = {ref.component_id: ref for ref in retrieved}

        selected_components: list[ComponentRef] = []
        seen: set[str] = set()
        for cid in extended_ids:
            if cid in seen:
                continue
            seen.add(cid)
            cap = capabilities_map[cid]
            if cid in retrieved_map:
                reason = retrieved_map[cid].reason
            elif cid in missing:
                # 新约束触发的组件
                trigger_constraints = [
                    c.id for c in request.new_constraints
                    if cid in _required_components_for_constraints([c])
                ]
                reason = f"由新约束 {', '.join(trigger_constraints)} 触发添加"
            else:
                reason = f"策略要求: {old_plan.plan_type}方案必选组件"
            selected_components.append(ComponentRef(
                component_id=cap.component_id,
                name=cap.name,
                reason=reason,
                required_data=scenario.get_required_data(recompile_scenario, cid, cap.required_data),
                evidence_urls=list(cap.evidence_urls),
            ))

        # 重建工作流
        to_be_nodes = _rebuild_workflow(
            old_plan.plan_type, extended_ids, capabilities_map,
            recompile_scenario, recompile_gate_reason,
        )

        # 重新校验和评分
        temp_plan = new_plan.model_copy(update={
            "selected_components": selected_components,
            "to_be_nodes": to_be_nodes,
            "applied_constraints": list(merged_constraints),
        })
        validation = validate_constraints(temp_plan, list(merged_constraints))
        review = review_solution(temp_plan, updated_process, validation)

        # 合并 warnings
        merged_warnings = list(temp_plan.warnings)
        for w in validation.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)
        for w in review.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)

        new_plan = temp_plan.model_copy(update={
            "review_score": review.score,
            "warnings": merged_warnings,
        })
    else:
        # 无需补充组件，检查是否有约束变化
        if not request.new_constraints:
            has_real_changes = False
        # new_plan 已由 compiler 完成校验和评分

    # 6. 计算 Diff
    added, removed = _diff_components(old_plan, new_plan)
    changed_nodes = _diff_nodes(old_plan, new_plan)

    # 7. 版本递增
    if has_real_changes and (added or removed or changed_nodes):
        new_solution_id = _increment_version(old_plan.solution_id)
    else:
        new_solution_id = old_plan.solution_id
        added = []
        removed = []
        changed_nodes = []

    # 8. 构建变更说明
    explanations: list[str] = []

    # 约束变化
    new_constraint_ids = {c.id for c in request.new_constraints}
    if new_constraint_ids:
        explanations.append(
            f"新增或覆盖约束: {', '.join(sorted(new_constraint_ids))}"
        )

    # 组件变化
    if added:
        explanations.append(f"新增组件: {', '.join(added)}")
    if removed:
        explanations.append(f"移除组件: {', '.join(removed)}")

    # 节点变化
    if changed_nodes:
        explanations.append(f"流程节点变化: {', '.join(changed_nodes[:5])}{'...' if len(changed_nodes) > 5 else ''}")

    # 评分变化
    old_score = old_plan.review_score
    new_score = new_plan.review_score
    if old_score != new_score:
        explanations.append(f"review_score 由 {old_score:.1f} 变为 {new_score:.1f}")

    # 约束校验状态
    validation = validate_constraints(new_plan, list(merged_constraints))
    hard_failed = [c for c in validation.checks if c.hard and c.status == "failed"]
    hard_unverifiable = [c for c in validation.checks if c.hard and c.status == "unverifiable"]
    if hard_failed:
        explanations.append(f"存在 hard 约束校验失败: {', '.join(c.constraint_id for c in hard_failed)}")
    if hard_unverifiable:
        explanations.append(
            f"存在 hard 约束无法在设计阶段验证(unverifiable): {', '.join(c.constraint_id for c in hard_unverifiable)}"
        )

    if not explanations:
        explanations.append("无有效变化，方案保持原样")

    # 更新 solution_id
    final_plan = new_plan.model_copy(update={"solution_id": new_solution_id})

    return RecompileResult(
        previous_solution_id=old_plan.solution_id,
        new_solution=final_plan,
        changed_node_ids=changed_nodes,
        added_component_ids=added,
        removed_component_ids=removed,
        change_explanations=explanations,
    )
