"""CHAT-M2 Feishu callback HTTP tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.solution.api import (
    get_feishu_bot_service,
    set_feishu_bot_service,
)
from backend.app.solution.feishu_bot import FeishuBotConfig, FeishuBotService
from backend.app.solution.llm_provider import FakeLLMProvider


client = TestClient(app)


class RecordingReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


def _service() -> tuple[FeishuBotService, RecordingReplyClient]:
    reply_client = RecordingReplyClient()
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=reply_client,
        provider=FakeLLMProvider(
            responses=[
                '{"intent":"requirement_input","answer":"请继续补充现有系统。"}'
            ]
        ),
    )
    return service, reply_client


def _event() -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": "event-api-001",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-001",
            "token": "verification-test",
        },
        "event": {
            "sender": {"sender_type": "user"},
            "message": {
                "message_id": "message-api-001",
                "chat_id": "chat-001",
                "message_type": "text",
                "content": json.dumps(
                    {"text": "我们想优化采购审查"}, ensure_ascii=False
                ),
                "mentions": [],
            },
        },
    }


def test_feishu_url_verification_endpoint() -> None:
    service, _ = _service()
    set_feishu_bot_service(service)
    try:
        response = client.post(
            "/integrations/feishu/events",
            json={
                "type": "url_verification",
                "token": "verification-test",
                "challenge": "challenge-api",
            },
        )
    finally:
        set_feishu_bot_service(None)

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-api"}


def test_feishu_text_event_is_acknowledged_and_replied() -> None:
    service, reply_client = _service()
    set_feishu_bot_service(service)
    try:
        response = client.post("/integrations/feishu/events", json=_event())
    finally:
        set_feishu_bot_service(None)

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "event_id": "event-api-001"}
    assert reply_client.replies == [("message-api-001", "请继续补充现有系统。")]


def test_feishu_invalid_token_returns_401() -> None:
    service, _ = _service()
    payload = _event()
    payload["header"]["token"] = "wrong-token"
    set_feishu_bot_service(service)
    try:
        response = client.post("/integrations/feishu/events", json=payload)
    finally:
        set_feishu_bot_service(None)

    assert response.status_code == 401


def test_feishu_missing_configuration_returns_503(monkeypatch) -> None:
    for name in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_VERIFICATION_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    get_feishu_bot_service.cache_clear()
    set_feishu_bot_service(None)

    response = client.post("/integrations/feishu/events", json=_event())

    assert response.status_code == 503


def test_openapi_contains_feishu_event_route() -> None:
    assert "/integrations/feishu/events" in app.openapi()["paths"]

