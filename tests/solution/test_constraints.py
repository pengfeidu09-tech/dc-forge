"""B-M3 硬约束校验器测试。"""

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.solution import ComponentRef, SolutionPlan, WorkflowNode
from backend.app.solution.constraints import (
    ConstraintCheck,
    ConstraintValidationResult,
    validate_constraints,
)


def _make_component(comp_id: str) -> ComponentRef:
    return ComponentRef(
        component_id=comp_id,
        name=comp_id,
        reason="test",
        required_data=[],
        evidence_urls=[],
    )


def _make_node(
    node_id: str,
    comp_id: str = "human-approval",
    executor: str = "human",
    human_gate: bool = True,
    gate_reason: str | None = "超过50万元的订单必须人工审批",
    next_ids: list[str] | None = None,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        name="test node",
        component_id=comp_id,
        executor=executor,
        next_ids=next_ids or [],
        human_gate=human_gate,
        gate_reason=gate_reason,
    )


def _make_plan(
    component_ids: list[str] | None = None,
    nodes: list[WorkflowNode] | None = None,
    constraints: list[BusinessConstraint] | None = None,
) -> SolutionPlan:
    if component_ids is None:
        component_ids = ["human-approval", "audit-log"]
    if nodes is None:
        nodes = [_make_node("node-001")]
    if constraints is None:
        constraints = []
    return SolutionPlan(
        schema_version="1.0",
        solution_id="test-plan-v1",
        source_project_id="test-001",
        plan_type="balanced",
        name="测试方案",
        summary="测试",
        selected_components=[_make_component(c) for c in component_ids],
        to_be_nodes=nodes,
        applied_constraints=constraints,
        implementation_steps=["step1", "step2", "step3"],
        expected_metrics=["指标"],
        assumptions=[],
        warnings=[],
        review_score=0.0,
    )


def _approval_constraint(hard: bool = True, threshold: float | None = 500000) -> BusinessConstraint:
    params = {}
    if threshold is not None:
        params["amount_threshold"] = threshold
    return BusinessConstraint(
        id="c-approval",
        type="approval",
        statement="超过50万元的订单必须人工审批",
        hard=hard,
        parameters=params,
    )


def test_validation_returns_check_for_every_constraint() -> None:
    """每条输入约束都产生一条 ConstraintCheck。"""
    plan = _make_plan()
    constraints = [
        _approval_constraint(),
        BusinessConstraint(id="c-budget", type="budget", statement="预算不超过100万", hard=True),
    ]
    result = validate_constraints(plan, constraints)
    assert len(result.checks) == 2
    assert {c.constraint_id for c in result.checks} == {"c-approval", "c-budget"}


def test_valid_approval_constraint_passes() -> None:
    """有 human_gate=true 且 gate_reason 体现约束的 approval 约束应 passed。"""
    plan = _make_plan()
    result = validate_constraints(plan, [_approval_constraint()])
    approval_check = next(c for c in result.checks if c.constraint_type == "approval")
    assert approval_check.status == "passed", approval_check.message


def test_missing_human_gate_fails_hard_approval() -> None:
    """没有 human_gate=true 时 hard approval 约束应 failed。"""
    plan = _make_plan(
        nodes=[_make_node("node-001", human_gate=False, gate_reason=None)],
    )
    result = validate_constraints(plan, [_approval_constraint()])
    approval_check = next(c for c in result.checks if c.constraint_type == "approval")
    assert approval_check.status == "failed"


def test_empty_gate_reason_fails_approval() -> None:
    """有 human_gate=true 但 gate_reason 为空时 approval 应 failed。"""
    plan = _make_plan(
        nodes=[_make_node("node-001", human_gate=True, gate_reason=None)],
    )
    result = validate_constraints(plan, [_approval_constraint()])
    approval_check = next(c for c in result.checks if c.constraint_type == "approval")
    assert approval_check.status == "failed"


def test_approval_threshold_is_reflected_in_gate_reason() -> None:
    """gate_reason 包含阈值数字或完整 statement 时 passed。"""
    plan = _make_plan(
        nodes=[_make_node("node-001", gate_reason="超过50万元的订单必须人工审批")],
    )
    result = validate_constraints(plan, [_approval_constraint(threshold=500000)])
    approval_check = next(c for c in result.checks if c.constraint_type == "approval")
    assert approval_check.status == "passed"


def test_security_audit_requirement_needs_audit_log() -> None:
    """security 约束涉及审计时需要 audit-log 组件。"""
    constraint = BusinessConstraint(
        id="c-sec", type="security", statement="所有操作需审计留痕", hard=True,
    )
    # 有 audit-log
    plan_with = _make_plan(component_ids=["human-approval", "audit-log"])
    result_with = validate_constraints(plan_with, [constraint])
    assert next(c for c in result_with.checks if c.constraint_type == "security").status == "passed"
    # 无 audit-log
    plan_without = _make_plan(component_ids=["human-approval"])
    result_without = validate_constraints(plan_without, [constraint])
    assert next(c for c in result_without.checks if c.constraint_type == "security").status == "failed"


def test_data_masking_requirement_needs_data_masking() -> None:
    """data 约束涉及脱敏时需要 data-masking 组件。"""
    constraint = BusinessConstraint(
        id="c-data", type="data", statement="敏感数据需脱敏处理", hard=True,
    )
    plan_with = _make_plan(component_ids=["human-approval", "data-masking"])
    result_with = validate_constraints(plan_with, [constraint])
    assert next(c for c in result_with.checks if c.constraint_type == "data").status == "passed"
    plan_without = _make_plan(component_ids=["human-approval"])
    result_without = validate_constraints(plan_without, [constraint])
    assert next(c for c in result_without.checks if c.constraint_type == "data").status == "failed"


def test_local_only_requirement_needs_local_model() -> None:
    """security/data 约束涉及本地部署时需要 local-model 组件。"""
    constraint = BusinessConstraint(
        id="c-local", type="security", statement="数据不出域，需本地部署", hard=True,
    )
    plan_with = _make_plan(component_ids=["human-approval", "local-model"])
    result_with = validate_constraints(plan_with, [constraint])
    assert next(c for c in result_with.checks if c.constraint_type == "security").status == "passed"
    plan_without = _make_plan(component_ids=["human-approval"])
    result_without = validate_constraints(plan_without, [constraint])
    assert next(c for c in result_without.checks if c.constraint_type == "security").status == "failed"


def test_risk_constraint_needs_risk_components() -> None:
    """risk 约束涉及风险评分时需要 risk-scoring 组件。"""
    constraint = BusinessConstraint(
        id="c-risk", type="risk", statement="需对高风险订单进行风险评分", hard=True,
    )
    plan_with = _make_plan(component_ids=["human-approval", "risk-scoring", "audit-log"])
    result_with = validate_constraints(plan_with, [constraint])
    assert next(c for c in result_with.checks if c.constraint_type == "risk").status == "passed"
    plan_without = _make_plan(component_ids=["human-approval"])
    result_without = validate_constraints(plan_without, [constraint])
    assert next(c for c in result_without.checks if c.constraint_type == "risk").status == "failed"


def test_hard_budget_constraint_is_unverifiable_and_invalid() -> None:
    """hard budget 约束应 unverifiable 且使总体 is_valid=false。"""
    constraint = BusinessConstraint(
        id="c-budget", type="budget", statement="总预算不超过100万", hard=True,
    )
    plan = _make_plan()
    result = validate_constraints(plan, [constraint])
    budget_check = next(c for c in result.checks if c.constraint_type == "budget")
    assert budget_check.status == "unverifiable"
    assert result.is_valid is False


def test_soft_unverifiable_constraint_does_not_invalidate_plan() -> None:
    """soft unverifiable 约束不使总体 invalid。"""
    constraint = BusinessConstraint(
        id="c-budget-soft", type="budget", statement="建议控制成本", hard=False,
    )
    plan = _make_plan()
    result = validate_constraints(plan, [constraint])
    assert result.is_valid is True
    assert result.unverifiable_count >= 1


def test_validation_does_not_mutate_inputs() -> None:
    """校验不修改输入方案和约束。"""
    plan = _make_plan()
    constraints = [_approval_constraint()]
    plan_before = plan.model_dump()
    constraints_before = [c.model_dump() for c in constraints]
    validate_constraints(plan, constraints)
    assert plan.model_dump() == plan_before
    assert [c.model_dump() for c in constraints] == constraints_before


def test_validation_is_deterministic() -> None:
    """相同输入结果稳定。"""
    plan = _make_plan()
    constraints = [_approval_constraint()]
    first = validate_constraints(plan, constraints)
    second = validate_constraints(plan, constraints)
    assert first.model_dump() == second.model_dump()


def test_compiled_three_plans_pass_current_approval_constraint() -> None:
    """编译器生成的三套方案都应通过当前 approval 约束。"""
    import json
    from pathlib import Path
    from backend.app.contracts.process import ProcessSpec
    from backend.app.solution import compile_solution

    root = Path(__file__).resolve().parents[2]
    spec_data = json.loads((root / "data/fixtures/process_spec.json").read_text(encoding="utf-8"))
    process = ProcessSpec.model_validate(spec_data)
    bundle = compile_solution(process)
    for plan in bundle.plans:
        result = validate_constraints(plan, process.constraints)
        approval_check = next(
            c for c in result.checks if c.constraint_type == "approval"
        )
        assert approval_check.status == "passed", (
            f"{plan.plan_type} approval check: {approval_check.message}"
        )
