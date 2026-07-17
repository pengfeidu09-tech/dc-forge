"""B-M5 端到端冒烟测试。"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.runtime import RuntimeRequest
from backend.app.contracts.solution import (
    CompileRequest,
    RecompileRequest,
    RecompileResult,
    SolutionBundle,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"

client = TestClient(app)


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _compile_bundle() -> dict:
    process_data = _load_json("process_spec.json")
    resp = client.post("/compile-solution", json={"process": process_data})
    assert resp.status_code == 200
    return resp.json()


def _get_balanced(bundle: dict) -> dict:
    return next(p for p in bundle["plans"] if p["plan_type"] == "balanced")


def test_health_to_compile_to_recompile_flow() -> None:
    """完整流程：health → compile → 选择 balanced → recompile。"""
    # 1. Health
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Compile
    bundle = _compile_bundle()
    assert len(bundle["plans"]) == 3

    # 3. 选择 balanced
    balanced = _get_balanced(bundle)
    assert balanced["plan_type"] == "balanced"

    # 4. Recompile
    recompile_req = _load_json("recompile_request.json")
    resp = client.post("/recompile-solution", json=recompile_req)
    assert resp.status_code == 200
    result = resp.json()

    # 5. 验证
    assert result["previous_solution_id"] == balanced["solution_id"]
    assert result["new_solution"]["plan_type"] == "balanced"
    assert "v2" in result["new_solution"]["solution_id"]
    assert "data-masking" in result["added_component_ids"]
    assert "local-model" in result["added_component_ids"]
    assert len(result["changed_node_ids"]) > 0
    assert len(result["change_explanations"]) > 0
    assert result["new_solution"]["review_score"] > 0


def test_compile_output_can_build_runtime_request() -> None:
    """成员 B 输出能被 RuntimeRequest 公共合同消费。"""
    from backend.app.contracts.solution import SolutionPlan

    bundle = _compile_bundle()
    balanced = _get_balanced(bundle)
    process = ProcessSpec.model_validate(_load_json("process_spec.json"))

    # 用 SolutionPlan 构造 RuntimeRequest
    plan = SolutionPlan.model_validate(balanced)
    runtime_req = RuntimeRequest(
        process=process,
        solution=plan,
        case_id="procurement-case-001",
    )
    assert runtime_req.case_id == "procurement-case-001"
    assert runtime_req.solution.solution_id == balanced["solution_id"]


def test_invalid_process_is_rejected_before_compilation() -> None:
    """删除必填字段的 ProcessSpec 应返回 422。"""
    bad_process = {"project_id": "test"}  # 缺少大量必填字段
    resp = client.post("/compile-solution", json={"process": bad_process})
    assert resp.status_code == 422


def test_recompile_output_is_public_contract_compatible() -> None:
    """RecompileResult API 响应通过公共合同校验。"""
    recompile_req = _load_json("recompile_request.json")
    resp = client.post("/recompile-solution", json=recompile_req)
    RecompileResult.model_validate(resp.json())


def test_end_to_end_flow_is_deterministic() -> None:
    """同一输入两次调用结果完全相同。"""
    process_data = _load_json("process_spec.json")
    r1 = client.post("/compile-solution", json={"process": process_data})
    r2 = client.post("/compile-solution", json={"process": process_data})
    assert r1.json() == r2.json()

    recompile_req = _load_json("recompile_request.json")
    rr1 = client.post("/recompile-solution", json=recompile_req)
    rr2 = client.post("/recompile-solution", json=recompile_req)
    assert rr1.json() == rr2.json()


def test_demo_flow_has_no_dangling_workflow_edges() -> None:
    """balanced v1 和 v2 都无悬空 next_id。"""
    # v1
    bundle = _compile_bundle()
    balanced_v1 = _get_balanced(bundle)
    node_ids = {n["id"] for n in balanced_v1["to_be_nodes"]}
    for node in balanced_v1["to_be_nodes"]:
        for nid in node["next_ids"]:
            assert nid in node_ids, f"v1 悬空: {nid}"

    # v2
    recompile_req = _load_json("recompile_request.json")
    resp = client.post("/recompile-solution", json=recompile_req)
    balanced_v2 = resp.json()["new_solution"]
    node_ids = {n["id"] for n in balanced_v2["to_be_nodes"]}
    for node in balanced_v2["to_be_nodes"]:
        for nid in node["next_ids"]:
            assert nid in node_ids, f"v2 悬空: {nid}"


def test_demo_language_does_not_claim_actual_business_results() -> None:
    """fixture 和 API 返回不含虚假收益表述。"""
    forbidden_phrases = [
        "降低50%", "提升50%", "节省100万",
        "已经降低", "已经提升", "已降低", "已提升",
    ]

    # 检查 solution_bundle fixture
    bundle_data = _load_json("solution_bundle.json")
    for plan in bundle_data["plans"]:
        texts = plan.get("expected_metrics", []) + [plan.get("summary", "")] + plan.get("warnings", [])
        for text in texts:
            for phrase in forbidden_phrases:
                assert phrase not in text, f"fixture 含虚假收益: {phrase} in {text}"

    # 检查 API 返回
    api_bundle = _compile_bundle()
    for plan in api_bundle["plans"]:
        texts = plan.get("expected_metrics", []) + [plan.get("summary", "")] + plan.get("warnings", [])
        for text in texts:
            for phrase in forbidden_phrases:
                assert phrase not in text, f"API 含虚假收益: {phrase} in {text}"
