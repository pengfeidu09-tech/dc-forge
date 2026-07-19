"""B-M4 增量重编译器测试。"""

import json
from pathlib import Path

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import RecompileRequest, RecompileResult, SolutionPlan
from backend.app.solution import compile_solution, recompile_solution

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _get_balanced_plan() -> SolutionPlan:
    process = _load_process_spec()
    bundle = compile_solution(process)
    return next(p for p in bundle.plans if p.plan_type == "balanced")


def _security_constraint() -> BusinessConstraint:
    return BusinessConstraint(
        id="constraint-security-local-001",
        type="security",
        statement="采购发票包含敏感信息，数据不得出域，必须在本地处理并完成脱敏和审计留痕",
        hard=True,
        parameters={
            "data_local_only": True,
            "mask_sensitive_fields": True,
            "audit_required": True,
        },
    )


def _make_request(new_constraints: list[BusinessConstraint] | None = None) -> RecompileRequest:
    return RecompileRequest(
        process=_load_process_spec(),
        selected_solution=_get_balanced_plan(),
        new_constraints=new_constraints or [_security_constraint()],
    )


def _recompile() -> RecompileResult:
    return recompile_solution(_make_request())


def test_recompile_returns_public_contract() -> None:
    result = _recompile()
    assert isinstance(result, RecompileResult)
    RecompileResult.model_validate(result.model_dump())


def test_recompile_preserves_plan_type() -> None:
    result = _recompile()
    assert result.new_solution.plan_type == "balanced"


def test_recompile_preserves_project_id() -> None:
    request = _make_request()
    result = recompile_solution(request)
    assert result.new_solution.source_project_id == request.process.project_id


def test_recompile_merges_constraints_without_duplicates() -> None:
    request = _make_request()
    result = recompile_solution(request)
    constraint_ids = [c.id for c in result.new_solution.applied_constraints]
    assert len(constraint_ids) == len(set(constraint_ids)), "约束 ID 重复"


def test_new_constraint_overrides_same_id() -> None:
    process = _load_process_spec()
    original = _get_balanced_plan()
    # 用同 id 但不同 statement 的约束覆盖
    overridden = BusinessConstraint(
        id="constraint-001",
        type="approval",
        statement="覆盖后的审批约束：超过30万元需人工审批",
        hard=True,
        parameters={"amount_threshold": 300000},
    )
    request = RecompileRequest(
        process=process,
        selected_solution=original,
        new_constraints=[overridden],
    )
    result = recompile_solution(request)
    matching = [c for c in result.new_solution.applied_constraints if c.id == "constraint-001"]
    assert len(matching) == 1
    assert "30万" in matching[0].statement or "300000" in str(matching[0].parameters.get("amount_threshold", ""))


def test_recompile_does_not_mutate_inputs() -> None:
    request = _make_request()
    process_before = request.process.model_dump()
    solution_before = request.selected_solution.model_dump()
    constraints_before = [c.model_dump() for c in request.new_constraints]
    recompile_solution(request)
    assert request.process.model_dump() == process_before
    assert request.selected_solution.model_dump() == solution_before
    assert [c.model_dump() for c in request.new_constraints] == constraints_before


def test_recompile_is_deterministic() -> None:
    first = _recompile()
    second = _recompile()
    assert first.model_dump() == second.model_dump()


def test_recompile_increments_solution_version_when_changed() -> None:
    request = _make_request()
    result = recompile_solution(request)
    old_id = request.selected_solution.solution_id
    new_id = result.new_solution.solution_id
    assert new_id != old_id, f"版本未递增: {old_id} -> {new_id}"
    assert "v2" in new_id or "v3" in new_id, f"版本号异常: {new_id}"


def test_no_effective_change_does_not_create_fake_diff() -> None:
    # 无新约束 → 无变化
    request = RecompileRequest(
        process=_load_process_spec(),
        selected_solution=_get_balanced_plan(),
        new_constraints=[],
    )
    result = recompile_solution(request)
    assert result.added_component_ids == []
    assert result.removed_component_ids == []
    assert result.changed_node_ids == []


def test_local_sensitive_constraint_adds_local_model_and_data_masking() -> None:
    result = _recompile()
    new_comp_ids = {c.component_id for c in result.new_solution.selected_components}
    assert "local-model" in new_comp_ids, "缺少 local-model"
    assert "data-masking" in new_comp_ids, "缺少 data-masking"


def test_added_components_have_real_catalog_data() -> None:
    from backend.app.solution import load_capabilities
    result = _recompile()
    caps = {c.component_id: c for c in load_capabilities()}
    for comp in result.new_solution.selected_components:
        assert comp.component_id in caps, f"未知组件: {comp.component_id}"


def test_added_components_have_explanatory_reason() -> None:
    result = _recompile()
    for comp in result.new_solution.selected_components:
        if comp.component_id in ("local-model", "data-masking"):
            assert len(comp.reason) > 5, f"{comp.component_id} reason 过短: {comp.reason}"
            assert "约束" in comp.reason or "安全" in comp.reason or "策略" in comp.reason


def test_recompiled_workflow_has_no_dangling_edges() -> None:
    result = _recompile()
    node_ids = {n.id for n in result.new_solution.to_be_nodes}
    for node in result.new_solution.to_be_nodes:
        for nid in node.next_ids:
            assert nid in node_ids, f"悬空 next_id: {nid}"


def test_changed_node_ids_match_actual_node_changes() -> None:
    request = _make_request()
    result = recompile_solution(request)
    old_nodes = {n.id: n for n in request.selected_solution.to_be_nodes}
    new_nodes = {n.id: n for n in result.new_solution.to_be_nodes}
    # 验证 changed_node_ids 是合理的子集
    all_changed = set(result.changed_node_ids)
    new_only = set(new_nodes) - set(old_nodes)
    removed = set(old_nodes) - set(new_nodes)
    modified = set()
    for nid in set(new_nodes) & set(old_nodes):
        if new_nodes[nid].model_dump() != old_nodes[nid].model_dump():
            modified.add(nid)
    expected = new_only | removed | modified
    assert all_changed == expected or all_changed >= expected, (
        f"changed_node_ids({all_changed}) 与实际变化({expected})不一致"
    )


def test_added_component_ids_match_actual_component_diff() -> None:
    request = _make_request()
    result = recompile_solution(request)
    old_ids = {c.component_id for c in request.selected_solution.selected_components}
    new_ids = {c.component_id for c in result.new_solution.selected_components}
    expected_added = sorted(new_ids - old_ids)
    assert result.added_component_ids == expected_added, (
        f"added: {result.added_component_ids} vs expected: {expected_added}"
    )


def test_removed_component_ids_match_actual_component_diff() -> None:
    request = _make_request()
    result = recompile_solution(request)
    old_ids = {c.component_id for c in request.selected_solution.selected_components}
    new_ids = {c.component_id for c in result.new_solution.selected_components}
    expected_removed = sorted(old_ids - new_ids)
    assert result.removed_component_ids == expected_removed, (
        f"removed: {result.removed_component_ids} vs expected: {expected_removed}"
    )


def test_recompiled_plan_is_revalidated() -> None:
    from backend.app.solution import validate_constraints
    request = _make_request()
    result = recompile_solution(request)
    validation = validate_constraints(result.new_solution, result.new_solution.applied_constraints)
    security_check = next((c for c in validation.checks if c.constraint_type == "security"), None)
    if security_check:
        assert security_check.status == "passed", security_check.message


def test_recompiled_plan_receives_review_score() -> None:
    result = _recompile()
    assert result.new_solution.review_score > 0


def test_hard_unverifiable_constraint_is_disclosed() -> None:
    budget = BusinessConstraint(
        id="c-budget-hard", type="budget", statement="预算不超100万", hard=True,
    )
    request = RecompileRequest(
        process=_load_process_spec(),
        selected_solution=_get_balanced_plan(),
        new_constraints=[budget],
    )
    result = recompile_solution(request)
    explanation_text = " ".join(result.change_explanations)
    assert "unverifiable" in explanation_text.lower() or "无法验证" in explanation_text or "不可验证" in explanation_text


def test_change_explanations_are_not_empty_when_changed() -> None:
    result = _recompile()
    assert len(result.change_explanations) > 0
    for exp in result.change_explanations:
        assert len(exp) > 5, f"解释过短: {exp}"
