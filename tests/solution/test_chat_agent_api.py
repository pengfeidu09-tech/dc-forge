"""CHAT-M1 HTTP boundary tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.solution.api import set_chat_agent_provider
from backend.app.solution.llm_provider import FakeLLMProvider


client = TestClient(app)


def test_chat_agent_endpoint_returns_structured_routing() -> None:
    set_chat_agent_provider(
        FakeLLMProvider(
            responses=[
                '{"intent":"requirement_input","answer":"请继续补充当前流程。"}'
            ]
        )
    )
    try:
        response = client.post(
            "/agent/chat",
            json={
                "project_id": "customer-project-001",
                "message_id": "feishu-event-001",
                "message": "我们希望缩短采购文件审查时间",
                "state": {
                    "phase": "collecting",
                    "readiness_stage": "DISCOVERY",
                    "can_generate_formal_solution": False,
                },
            },
        )
    finally:
        set_chat_agent_provider(None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "intent": "requirement_input",
        "answer": "请继续补充当前流程。",
        "next_action": "analyze_requirements",
        "warnings": [],
    }


def test_chat_agent_endpoint_rejects_extra_fields() -> None:
    response = client.post(
        "/agent/chat",
        json={
            "project_id": "customer-project-001",
            "message_id": "feishu-event-001",
            "message": "你好",
            "unexpected": True,
        },
    )

    assert response.status_code == 422


def test_openapi_contains_chat_agent_route() -> None:
    assert "/agent/chat" in app.openapi()["paths"]

