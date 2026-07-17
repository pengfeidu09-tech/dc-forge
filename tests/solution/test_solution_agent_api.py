"""B-M6 Solution Agent API 测试。"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.solution import compile_solution
from backend.app.solution.api import set_agent_provider
from backend.app.solution.llm_provider import FakeLLMProvider

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"
client = TestClient(app)


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _get_balanced() -> dict:
    bundle = compile_solution(__import__("backend.app.contracts.process", fromlist=["ProcessSpec"]).ProcessSpec.model_validate(_load_json("process_spec.json")))
    return next(p for p in bundle.plans if p.plan_type == "balanced").model_dump(mode="json")


_COMPILE_RESP = '{"intent": "compile", "constraint": null, "missing_info": null, "answer": "编译"}'
_RECOMPILE_RESP = json.dumps({
    "intent": "recompile",
    "constraint": {
        "id": "constraint-security-local-001",
        "type": "security",
        "statement": "采购发票包含敏感信息，数据不得出域，必须在本地处理并完成脱敏和审计留痕",
        "hard": True,
        "parameters": {"data_local_only": True, "mask_sensitive_fields": True, "audit_required": True},
    },
    "missing_info": None,
    "answer": "添加安全约束",
})


def test_agent_compile_endpoint() -> None:
    """POST /agent/solution compile 意图。"""
    set_agent_provider(FakeLLMProvider(responses=[_COMPILE_RESP]))
    try:
        payload = {
            "process": _load_json("process_spec.json"),
            "message": "生成三套方案",
        }
        resp = client.post("/agent/solution", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "compile"
        assert body["solution_bundle"] is not None
        assert len(body["solution_bundle"]["plans"]) == 3
    finally:
        set_agent_provider(None)


def test_agent_recompile_endpoint() -> None:
    """POST /agent/solution recompile 意图。"""
    balanced = _get_balanced()
    set_agent_provider(FakeLLMProvider(responses=[_RECOMPILE_RESP]))
    try:
        payload = {
            "process": _load_json("process_spec.json"),
            "message": "客户要求数据不出域",
            "selected_solution": balanced,
        }
        resp = client.post("/agent/solution", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "recompile"
        assert body["recompile_result"] is not None
        assert "data-masking" in body["recompile_result"]["added_component_ids"]
    finally:
        set_agent_provider(None)


def test_agent_review_endpoint() -> None:
    """POST /agent/solution review 意图。"""
    balanced = _get_balanced()
    review_resp = '{"intent": "review", "constraint": null, "missing_info": null, "answer": "评审"}'
    set_agent_provider(FakeLLMProvider(responses=[review_resp, "解释"]))
    try:
        payload = {
            "process": _load_json("process_spec.json"),
            "message": "评审这个方案",
            "selected_solution": balanced,
        }
        resp = client.post("/agent/solution", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "review"
        assert body["review"] is not None
        assert 0 <= body["review"]["score"] <= 100
    finally:
        set_agent_provider(None)


def test_agent_rejects_extra_fields() -> None:
    """AgentRequest extra 字段返回 422。"""
    set_agent_provider(FakeLLMProvider(responses=[_COMPILE_RESP]))
    try:
        payload = {
            "process": _load_json("process_spec.json"),
            "message": "编译",
            "extra_field": "bad",
        }
        resp = client.post("/agent/solution", json=payload)
        assert resp.status_code == 422
    finally:
        set_agent_provider(None)
