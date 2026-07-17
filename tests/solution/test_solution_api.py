"""B-M4 FastAPI Solution API 测试。"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    CompileRequest,
    RecompileRequest,
    RecompileResult,
    SolutionBundle,
)
from backend.app.solution import compile_solution

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"

client = TestClient(app)


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _get_balanced_plan():
    bundle = compile_solution(_load_process_spec())
    return next(p for p in bundle.plans if p.plan_type == "balanced")


def test_health_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "dcforge-solution"


def test_compile_endpoint_returns_three_plans() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    resp = client.post("/compile-solution", json={"process": process_data})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["plans"]) == 3
    types = {p["plan_type"] for p in body["plans"]}
    assert types == {"conservative", "balanced", "innovative"}


def test_compile_endpoint_returns_public_contract() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    resp = client.post("/compile-solution", json={"process": process_data})
    SolutionBundle.model_validate(resp.json())


def test_compile_endpoint_rejects_extra_fields() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    resp = client.post("/compile-solution", json={"process": process_data, "extra": "bad"})
    assert resp.status_code == 422


def test_recompile_endpoint_returns_diff() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    balanced = _get_balanced_plan()
    new_constraint = {
        "id": "constraint-security-local-001",
        "type": "security",
        "statement": "采购发票包含敏感信息，数据不得出域，必须在本地处理并完成脱敏和审计留痕",
        "hard": True,
        "parameters": {"data_local_only": True, "mask_sensitive_fields": True, "audit_required": True},
    }
    payload = {
        "process": process_data,
        "selected_solution": balanced.model_dump(mode="json"),
        "new_constraints": [new_constraint],
    }
    resp = client.post("/recompile-solution", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    RecompileResult.model_validate(body)
    assert len(body["added_component_ids"]) > 0


def test_recompile_endpoint_preserves_plan_type() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    balanced = _get_balanced_plan()
    payload = {
        "process": process_data,
        "selected_solution": balanced.model_dump(mode="json"),
        "new_constraints": [],
    }
    resp = client.post("/recompile-solution", json=payload)
    assert resp.status_code == 200
    assert resp.json()["new_solution"]["plan_type"] == "balanced"


def test_review_endpoint_returns_score_and_dimensions() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    balanced = _get_balanced_plan()
    payload = {
        "process": process_data,
        "solution": balanced.model_dump(mode="json"),
    }
    resp = client.post("/review-solution", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["score"] <= 100
    assert len(body["dimensions"]) == 5


def test_review_endpoint_rejects_invalid_solution() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    # 缺少必填字段的 solution
    bad_solution = {"solution_id": "bad", "plan_type": "balanced"}
    payload = {"process": process_data, "solution": bad_solution}
    resp = client.post("/review-solution", json=payload)
    assert resp.status_code == 422


def test_api_results_are_deterministic() -> None:
    process_data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    r1 = client.post("/compile-solution", json={"process": process_data})
    r2 = client.post("/compile-solution", json={"process": process_data})
    assert r1.json() == r2.json()


def test_openapi_contains_solution_routes() -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/health" in paths
    assert "/compile-solution" in paths
    assert "/recompile-solution" in paths
    assert "/review-solution" in paths
