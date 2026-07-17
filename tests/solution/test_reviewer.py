"""B-M3 方案 Reviewer 测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionPlan
from backend.app.solution import compile_solution, validate_constraints
from backend.app.solution.reviewer import (
    ReviewDimension,
    SolutionReviewResult,
    review_solution,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _compile_balanced() -> tuple[SolutionPlan, ProcessSpec]:
    process = _load_process_spec()
    bundle = compile_solution(process)
    plan = next(p for p in bundle.plans if p.plan_type == "balanced")
    return plan, process


def test_review_score_is_between_zero_and_one_hundred() -> None:
    """Reviewer 分数范围 0—100。"""
    plan, process = _compile_balanced()
    result = review_solution(plan, process)
    assert 0 <= result.score <= 100


def test_review_contains_all_dimensions() -> None:
    """Reviewer 输出包含全部 5 个维度。"""
    plan, process = _compile_balanced()
    result = review_solution(plan, process)
    dim_names = {d.name for d in result.dimensions}
    assert len(result.dimensions) == 5
    assert "约束合规" in dim_names
    assert "需求与痛点覆盖" in dim_names
    assert "工作流完整性" in dim_names
    assert "可解释性与证据" in dim_names
    assert "实施可行性" in dim_names


def test_compliant_plan_scores_higher_than_constraint_violating_plan() -> None:
    """合规方案得分高于相同结构的违规方案。"""
    from backend.app.contracts.common import BusinessConstraint
    from backend.app.contracts.solution import ComponentRef, WorkflowNode
    from backend.app.solution.constraints import validate_constraints

    plan, process = _compile_balanced()
    validation_good = validate_constraints(plan, process.constraints)
    score_good = review_solution(plan, process, validation_good).score

    # 构造一个没有 human_gate 的违规方案
    violating_plan = SolutionPlan(
        schema_version="1.0",
        solution_id="violating-v1",
        source_project_id=plan.source_project_id,
        plan_type="balanced",
        name="违规方案",
        summary="无人工审批",
        selected_components=plan.selected_components,
        to_be_nodes=[
            WorkflowNode(
                id=n.id, name=n.name, component_id=n.component_id,
                executor=n.executor, next_ids=n.next_ids,
                human_gate=False, gate_reason=None,
            )
            for n in plan.to_be_nodes
        ],
        applied_constraints=plan.applied_constraints,
        implementation_steps=plan.implementation_steps,
        expected_metrics=plan.expected_metrics,
        assumptions=[],
        warnings=[],
        review_score=0.0,
    )
    validation_bad = validate_constraints(violating_plan, process.constraints)
    score_bad = review_solution(violating_plan, process, validation_bad).score
    assert score_good > score_bad, f"合规({score_good})应高于违规({score_bad})"


def test_hard_failure_cannot_be_recommended() -> None:
    """hard failed 时不得 recommended。"""
    from backend.app.contracts.common import BusinessConstraint
    from backend.app.contracts.solution import ComponentRef, WorkflowNode
    from backend.app.solution.constraints import validate_constraints

    plan, process = _compile_balanced()
    # 构造无 human_gate 的方案 → hard approval failed
    violating_plan = plan.model_copy(update={
        "to_be_nodes": [
            WorkflowNode(
                id=n.id, name=n.name, component_id=n.component_id,
                executor=n.executor, next_ids=n.next_ids,
                human_gate=False, gate_reason=None,
            )
            for n in plan.to_be_nodes
        ],
    })
    validation = validate_constraints(violating_plan, process.constraints)
    result = review_solution(violating_plan, process, validation)
    assert result.recommendation != "recommended"


def test_hard_unverifiable_cannot_be_recommended() -> None:
    """hard unverifiable 时不得 recommended。"""
    from backend.app.contracts.common import BusinessConstraint
    from backend.app.solution.constraints import validate_constraints

    plan, process = _compile_balanced()
    # 添加 hard budget 约束 → unverifiable
    budget_constraint = BusinessConstraint(
        id="c-budget-hard", type="budget", statement="预算不超100万", hard=True,
    )
    all_constraints = list(process.constraints) + [budget_constraint]
    validation = validate_constraints(plan, all_constraints)
    result = review_solution(plan, process, validation)
    assert result.recommendation != "recommended"


def test_review_is_deterministic() -> None:
    """相同输入结果稳定。"""
    plan, process = _compile_balanced()
    first = review_solution(plan, process)
    second = review_solution(plan, process)
    assert first.model_dump() == second.model_dump()


def test_review_does_not_mutate_plan() -> None:
    """Reviewer 不修改传入的 SolutionPlan。"""
    plan, process = _compile_balanced()
    before = plan.model_dump()
    review_solution(plan, process)
    assert plan.model_dump() == before


def test_review_warnings_disclose_missing_evidence() -> None:
    """warnings 说明证据引用尚未补齐。"""
    plan, process = _compile_balanced()
    result = review_solution(plan, process)
    warning_text = " ".join(result.warnings)
    assert "证据" in warning_text or "evidence" in warning_text.lower()


def test_balanced_compiled_plan_is_top_ranked() -> None:
    """balanced 综合评分不低于 conservative 和 innovative。"""
    process = _load_process_spec()
    bundle = compile_solution(process)
    scores = {}
    for plan in bundle.plans:
        validation = validate_constraints(plan, process.constraints)
        result = review_solution(plan, process, validation)
        scores[plan.plan_type] = result.score
    assert scores["balanced"] >= scores["conservative"], (
        f"balanced({scores['balanced']}) < conservative({scores['conservative']})"
    )
    assert scores["balanced"] >= scores["innovative"], (
        f"balanced({scores['balanced']}) < innovative({scores['innovative']})"
    )


def test_all_compiled_plans_receive_nonzero_scores() -> None:
    """三套方案 review_score 不再为 0。"""
    process = _load_process_spec()
    bundle = compile_solution(process)
    for plan in bundle.plans:
        assert plan.review_score > 0, f"{plan.plan_type} review_score 仍为 0"


def test_recommendation_matches_score_and_validation() -> None:
    """recommendation 与 score 和 validation 一致。"""
    plan, process = _compile_balanced()
    validation = validate_constraints(plan, process.constraints)
    result = review_solution(plan, process, validation)
    if result.score >= 85 and validation.is_valid:
        assert result.recommendation == "recommended"
    elif result.score >= 70 and validation.is_valid:
        assert result.recommendation == "acceptable"
    elif result.score >= 50:
        assert result.recommendation == "needs_revision"
    else:
        assert result.recommendation == "rejected"


def test_review_summary_is_not_empty() -> None:
    """summary 非空。"""
    plan, process = _compile_balanced()
    result = review_solution(plan, process)
    assert len(result.summary) > 0
