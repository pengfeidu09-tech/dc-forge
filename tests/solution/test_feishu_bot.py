"""CHAT-M2 Feishu application bot service tests."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.app.solution.feishu_bot import (
    FeishuAPIClient,
    FeishuAPIError,
    FeishuBotConfig,
    FeishuBotService,
    FeishuVerificationError,
)
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.enterprise_assistant import EnterpriseAssistantResponse


class RecordingReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


class RecordingProvider:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or [
            '{"intent":"requirement_input","answer":"请继续介绍当前流程。"}'
        ]
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append(messages)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return LLMResponse(content=self.responses[index])


class RecordingEnterpriseAssistant:
    def __init__(self) -> None:
        self.requests = []

    def answer(self, request):
        self.requests.append(request)
        return EnterpriseAssistantResponse(
            answer="供应商三因模拟环境证书过期未进入推荐。",
            tool_name="analyze_suppliers",
            tool_call={"method": "tools/call"},
            citations=["SRC-TENDER-019", "SRC-TENDER-021"],
        )


def _service(
    *,
    provider: RecordingProvider | None = None,
    client: RecordingReplyClient | None = None,
) -> tuple[FeishuBotService, RecordingProvider, RecordingReplyClient]:
    actual_provider = provider or RecordingProvider()
    actual_client = client or RecordingReplyClient()
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=actual_client,
        provider=actual_provider,
    )
    return service, actual_provider, actual_client


def _event(
    *,
    event_id: str = "event-001",
    message_id: str = "message-001",
    text: str = "我们希望缩短采购文件审查时间",
    message_type: str = "text",
    sender_type: str = "user",
    mentions: list[dict] | None = None,
    sender_open_id: str = "ou-owner",
) -> dict:
    content = {"text": text} if message_type == "text" else {"image_key": "img-1"}
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-001",
            "token": "verification-test",
        },
        "event": {
            "sender": {
                "sender_type": sender_type,
                "sender_id": {"open_id": sender_open_id},
            },
            "message": {
                "message_id": message_id,
                "chat_id": "chat-001",
                "message_type": message_type,
                "content": json.dumps(content, ensure_ascii=False),
                "mentions": mentions or [],
            },
        },
    }


def test_url_verification_returns_challenge() -> None:
    service, _, _ = _service()

    result = service.validate_callback(
        {
            "type": "url_verification",
            "token": "verification-test",
            "challenge": "challenge-value",
        }
    )

    assert result.kind == "challenge"
    assert result.challenge == "challenge-value"


def test_invalid_verification_token_is_rejected() -> None:
    service, _, _ = _service()
    payload = _event()
    payload["header"]["token"] = "wrong-token"

    with pytest.raises(FeishuVerificationError):
        service.validate_callback(payload)


def test_text_event_calls_chat_agent_and_replies_once() -> None:
    service, provider, client = _service()
    payload = _event()

    callback = service.validate_callback(payload)
    result = service.process_event(payload)

    assert callback.kind == "event"
    assert callback.event_id == "event-001"
    assert result == "replied"
    assert len(provider.calls) == 1
    assert client.replies == [("message-001", "请继续介绍当前流程。")]


def test_duplicate_event_does_not_reply_twice() -> None:
    service, provider, client = _service()
    payload = _event()

    assert service.process_event(payload) == "replied"
    assert service.process_event(payload) == "duplicate"
    assert len(provider.calls) == 1
    assert len(client.replies) == 1


@pytest.mark.parametrize(
    ("message_type", "sender_type"),
    [("image", "user"), ("text", "bot")],
)
def test_unsupported_messages_are_ignored(message_type: str, sender_type: str) -> None:
    service, provider, client = _service()

    result = service.process_event(
        _event(message_type=message_type, sender_type=sender_type)
    )

    assert result == "ignored"
    assert provider.calls == []
    assert client.replies == []


def test_feishu_mention_placeholder_is_removed() -> None:
    service, provider, _ = _service()

    service.process_event(
        _event(
            text="@_user_1 帮我分析采购需求",
            mentions=[{"key": "@_user_1", "name": "DCForge"}],
        )
    )

    latest_message = provider.calls[0][-1]["content"]
    assert "帮我分析采购需求" in latest_message
    assert "@_user_1" not in latest_message


def test_configured_owner_allowlist_ignores_other_senders() -> None:
    provider = RecordingProvider()
    client = RecordingReplyClient()
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
            allowed_open_id="ou-owner",
        ),
        reply_client=client,
        provider=provider,
    )

    result = service.process_event(_event(sender_open_id="ou-other"))

    assert result == "ignored"
    assert provider.calls == []
    assert client.replies == []


def test_second_turn_receives_bounded_conversation_history() -> None:
    provider = RecordingProvider(
        responses=[
            '{"intent":"requirement_input","answer":"目前是人工审查吗？"}',
            '{"intent":"clarification_answer","answer":"已记录人工审查现状。"}',
        ]
    )
    service, _, client = _service(provider=provider)

    service.process_event(_event(event_id="event-001", message_id="message-001"))
    service.process_event(
        _event(
            event_id="event-002",
            message_id="message-002",
            text="是的，目前由采购专员人工审查",
        )
    )

    second_call = json.dumps(provider.calls[1], ensure_ascii=False)
    assert "我们希望缩短采购文件审查时间" in second_call
    assert "目前是人工审查吗" in second_call
    assert client.replies[-1] == ("message-002", "已记录人工审查现状。")


def test_feishu_api_client_gets_token_and_replies_to_source_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token-test",
                    "expire": 7200,
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    config = FeishuBotConfig(
        app_id="cli_test",
        app_secret="secret-test-value",
        verification_token="verification-test",
    )
    client = FeishuAPIClient(config, http_client=http_client)

    client.reply_text("message/with/slash", "请继续补充现有系统。")
    client.reply_text("message-002", "已记录。")

    assert len(requests) == 3
    assert requests[0].url.path.endswith("/tenant_access_token/internal")
    assert requests[1].url.raw_path.endswith(
        b"/messages/message%2Fwith%2Fslash/reply"
    )
    assert requests[1].headers["authorization"] == "Bearer tenant-token-test"
    assert json.loads(requests[1].content)["msg_type"] == "text"
    reply_content = json.loads(json.loads(requests[1].content)["content"])
    assert reply_content == {"text": "请继续补充现有系统。"}


def test_feishu_api_errors_do_not_expose_app_secret_or_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"code": 999, "msg": "secret-test-value must never escape"},
        )

    config = FeishuBotConfig(
        app_id="cli_test",
        app_secret="secret-test-value",
        verification_token="verification-test",
    )
    client = FeishuAPIClient(
        config,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(FeishuAPIError) as captured:
        client.reply_text("message-001", "hello")

    assert "secret-test-value" not in str(captured.value)


def test_explicit_mcp_command_routes_feishu_bot_to_enterprise_assistant() -> None:
    provider = RecordingProvider()
    client = RecordingReplyClient()
    assistant = RecordingEnterpriseAssistant()
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=client,
        provider=provider,
        enterprise_assistant=assistant,
        enterprise_project_id="PRJ-TENDER-001",
        enterprise_user_id="user-procurement-owner",
        enterprise_as_of="2026-10-30T23:59:59+08:00",
    )

    result = service.process_event(
        _event(text="/mcp 供应商三为什么未进入推荐？")
    )

    assert result == "replied"
    assert provider.calls == []
    assert assistant.requests[0].message == "供应商三为什么未进入推荐？"
    assert client.replies == [
        (
            "message-001",
            "供应商三因模拟环境证书过期未进入推荐。\n\n来源：SRC-TENDER-019、SRC-TENDER-021",
        )
    ]
