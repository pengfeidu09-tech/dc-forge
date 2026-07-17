"""B-M3 编译器与校验/Reviewer 集成测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionBundle
from backend.app.solution import compile_solution, validate_constraints

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _compile() -> SolutionBundle:
    return compile_solution(_load_process_spec())


def test_compiler_assigns_nonzero_review_scores() -> None:
    """编译器输出的三套方案 review_score 均 > 0。"""
    bundle = _compile()
    for plan in bundle.plans:
        assert plan.review_score > 0, f"{plan.plan_type} review_score 为 0"


def test_compiler_removes_pending_reviewer_warning() -> None:
    """warnings 不再包含"Reviewer 尚未执行"。"""
    bundle = _compile()
    for plan in bundle.plans:
        for w in plan.warnings:
            assert "尚未执行" not in w, f"{plan.plan_type} 仍有 Reviewer 未执行 warning: {w}"


def test_compiler_preserves_constraint_validation_warnings() -> None:
    """warnings 包含真实校验信息或待 Runtime 验证事项。"""
    bundle = _compile()
    process = _load_process_spec()
    for plan in bundle.plans:
        validation = validate_constraints(plan, process.constraints)
        # 如果有 unverifiable 或 failed，warnings 应体现
        if validation.unverifiable_count > 0 or validation.failed_count > 0:
            warning_text = " ".join(plan.warnings)
            assert len(warning_text) > 0, f"{plan.plan_type} 有校验问题但无 warning"


def test_compiled_plans_pass_current_hard_approval_constraint() -> None:
    """三套方案都通过当前 hard approval 约束。"""
    bundle = _compile()
    process = _load_process_spec()
    for plan in bundle.plans:
        result = validate_constraints(plan, process.constraints)
        approval = next(c for c in result.checks if c.constraint_type == "approval")
        assert approval.status == "passed", f"{plan.plan_type}: {approval.message}"


def test_balanced_plan_has_highest_or_tied_highest_score() -> None:
    """balanced 的 review_score 不低于 conservative 和 innovative。"""
    bundle = _compile()
    scores = {p.plan_type: p.review_score for p in bundle.plans}
    assert scores["balanced"] >= scores["conservative"]
    assert scores["balanced"] >= scores["innovative"]


def test_compiler_output_is_still_deterministic() -> None:
    """同一输入重复编译结果一致。"""
    process = _load_process_spec()
    first = compile_solution(process)
    second = compile_solution(process)
    assert first.model_dump() == second.model_dump()


def test_compiler_output_still_validates_public_contract() -> None:
    """输出通过 SolutionBundle.model_validate。"""
    bundle = _compile()
    SolutionBundle.model_validate(bundle.model_dump())


def test_compiler_does_not_add_private_review_fields_to_contract() -> None:
    """输出不包含私有 Review 字段（如 dimensions）。"""
    bundle = _compile()
    raw = bundle.model_dump()
    plan_keys = set()
    for plan in raw["plans"]:
        plan_keys.update(plan.keys())
    forbidden = {"dimensions", "checks", "constraint_validation", "review"}
    assert not (plan_keys & forbidden), f"输出包含私有字段: {plan_keys & forbidden}"
