"""B-M3 质量报告 fixture 测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionBundle
from backend.app.solution import compile_solution, validate_constraints, review_solution

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_quality_report() -> dict:
    return json.loads((FIXTURES / "solution_quality_report.json").read_text(encoding="utf-8"))


def _load_bundle() -> dict:
    return json.loads((FIXTURES / "solution_bundle.json").read_text(encoding="utf-8"))


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def test_quality_fixture_contains_three_plans() -> None:
    """质量报告包含 3 套方案。"""
    report = _load_quality_report()
    assert len(report["plans"]) == 3


def test_quality_fixture_matches_solution_bundle_ids() -> None:
    """质量报告的 solution_id 与 solution_bundle.json 一致。"""
    report = _load_quality_report()
    bundle = _load_bundle()
    report_ids = {p["solution_id"] for p in report["plans"]}
    bundle_ids = {p["solution_id"] for p in bundle["plans"]}
    assert report_ids == bundle_ids


def test_quality_fixture_scores_match_solution_bundle() -> None:
    """质量报告的 review score 与 solution_bundle.json 一致。"""
    report = _load_quality_report()
    bundle = _load_bundle()
    report_scores = {p["solution_id"]: p["review"]["score"] for p in report["plans"]}
    bundle_scores = {p["solution_id"]: p["review_score"] for p in bundle["plans"]}
    for sid in report_scores:
        assert report_scores[sid] == bundle_scores[sid], (
            f"{sid}: report={report_scores[sid]} vs bundle={bundle_scores[sid]}"
        )


def test_quality_fixture_contains_constraint_checks() -> None:
    """质量报告包含 constraint_validation.checks。"""
    report = _load_quality_report()
    for plan in report["plans"]:
        checks = plan["constraint_validation"]["checks"]
        assert len(checks) > 0, f"{plan['plan_type']} 无 constraint checks"


def test_quality_fixture_contains_review_dimensions() -> None:
    """质量报告包含 review.dimensions（5 个维度）。"""
    report = _load_quality_report()
    for plan in report["plans"]:
        dims = plan["review"]["dimensions"]
        assert len(dims) == 5, f"{plan['plan_type']} 维度数不为 5: {len(dims)}"


def test_quality_fixture_has_no_pending_reviewer_warning() -> None:
    """质量报告不包含"Reviewer 尚未执行"。"""
    report = _load_quality_report()
    for plan in report["plans"]:
        for w in plan["review"]["warnings"]:
            assert "尚未执行" not in w
        for w in plan.get("constraint_validation", {}).get("warnings", []):
            assert "尚未执行" not in w


def test_quality_fixture_is_deterministically_regenerable() -> None:
    """重新生成质量报告结果稳定。"""
    process = _load_process_spec()
    bundle = compile_solution(process)
    regenerated = []
    for plan in bundle.plans:
        validation = validate_constraints(plan, process.constraints)
        review = review_solution(plan, process, validation)
        regenerated.append(review.model_dump())
    # 与 fixture 对比
    report = _load_quality_report()
    for i, plan_report in enumerate(report["plans"]):
        fixture_score = plan_report["review"]["score"]
        regen_score = regenerated[i]["score"]
        assert fixture_score == regen_score, (
            f"plan {i}: fixture={fixture_score} vs regen={regen_score}"
        )


def test_current_three_plans_have_no_hard_constraint_failure() -> None:
    """三套方案无 hard constraint failure。"""
    process = _load_process_spec()
    bundle = compile_solution(process)
    for plan in bundle.plans:
        result = validate_constraints(plan, process.constraints)
        hard_failed = [c for c in result.checks if c.hard and c.status == "failed"]
        assert len(hard_failed) == 0, f"{plan.plan_type} 有 hard failed: {hard_failed}"
