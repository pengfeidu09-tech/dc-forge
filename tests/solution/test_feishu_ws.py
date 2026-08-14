"""CHAT-M3 Feishu WebSocket transport tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.solution.feishu_bot import FeishuBotConfig, FeishuBotService
from backend.app.solution.feishu_ws import (
    FeishuWebSocketAdapter,
    build_feishu_websocket_client,
    normalize_feishu_ws_event,
)
from backend.app.solution.llm_provider import FakeLLMProvider


class RecordingReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


class InlineExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return function(*args)


def _sdk_event(*, sender_open_id: str = "ou_owner") -> SimpleNamespace:
    return SimpleNamespace(
        schema="2.0",
        header=SimpleNamespace(
            event_id="event-ws-001",
            event_type="im.message.receive_v1",
            tenant_key="tenant-001",
            token=None,
        ),
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_type="user",
                tenant_key="tenant-001",
                sender_id=SimpleNamespace(open_id=sender_open_id),
            ),
            message=SimpleNamespace(
                message_id="message-ws-001",
                chat_id="chat-001",
                chat_type="p2p",
                message_type="text",
                content=json.dumps({"text": "帮我分析采购审查需求"}, ensure_ascii=False),
                mentions=[SimpleNamespace(key="@_user_1", name="DCForge")],
            ),
        ),
    )


def _service(
    *, allowed_open_id: str | None = "ou_owner"
) -> tuple[FeishuBotService, RecordingReplyClient]:
    reply_client = RecordingReplyClient()
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_created",
            app_secret="created-secret-value",
            allowed_open_id=allowed_open_id,
        ),
        reply_client=reply_client,
        provider=FakeLLMProvider(
            responses=[
                '{"intent":"requirement_input","answer":"请补充当前采购审查流程。"}'
            ]
        ),
    )
    return service, reply_client


def test_normalize_sdk_event_matches_existing_service_payload() -> None:
    payload = normalize_feishu_ws_event(_sdk_event())

    assert payload["header"] == {
        "event_id": "event-ws-001",
        "event_type": "im.message.receive_v1",
        "tenant_key": "tenant-001",
    }
    assert payload["event"]["sender"]["sender_id"]["open_id"] == "ou_owner"
    assert payload["event"]["message"]["message_id"] == "message-ws-001"
    assert payload["event"]["message"]["mentions"] == [
        {"key": "@_user_1", "name": "DCForge"}
    ]


def test_websocket_callback_schedules_existing_chat_service() -> None:
    service, reply_client = _service()
    executor = InlineExecutor()
    adapter = FeishuWebSocketAdapter(service, executor=executor)

    result = adapter.handle(_sdk_event())

    assert result is None
    assert len(executor.submissions) == 1
    assert reply_client.replies == [
        ("message-ws-001", "请补充当前采购审查流程。")
    ]


def test_qr_owner_allowlist_ignores_other_feishu_users() -> None:
    service, reply_client = _service()
    executor = InlineExecutor()

    FeishuWebSocketAdapter(service, executor=executor).handle(
        _sdk_event(sender_open_id="ou_someone_else")
    )

    assert reply_client.replies == []


def test_build_client_registers_message_handler_and_feishu_domain() -> None:
    captured: dict[str, object] = {}

    class FakeBuilder:
        def register_p2_im_message_receive_v1(self, handler):
            captured["handler"] = handler
            return self

        def build(self):
            return "dispatcher"

    class FakeEventDispatcherHandler:
        @staticmethod
        def builder(encrypt_key: str, verification_token: str):
            captured["builder_args"] = (encrypt_key, verification_token)
            return FakeBuilder()

    class FakeWSClient:
        def __init__(self, app_id: str, app_secret: str, **kwargs):
            captured["client_args"] = (app_id, app_secret)
            captured["client_kwargs"] = kwargs

    fake_sdk = SimpleNamespace(
        EventDispatcherHandler=FakeEventDispatcherHandler,
        LogLevel=SimpleNamespace(WARNING="warning"),
        ws=SimpleNamespace(Client=FakeWSClient),
    )
    service, _ = _service()
    config = FeishuBotConfig(
        app_id="cli_created",
        app_secret="created-secret-value",
        api_base_url="https://open.feishu.cn",
    )

    client = build_feishu_websocket_client(
        config,
        service=service,
        sdk=fake_sdk,
        executor=InlineExecutor(),
    )

    assert isinstance(client, FakeWSClient)
    assert captured["builder_args"] == ("", "")
    assert captured["client_args"] == ("cli_created", "created-secret-value")
    assert captured["client_kwargs"] == {
        "log_level": "warning",
        "event_handler": "dispatcher",
        "domain": "https://open.feishu.cn",
    }
    assert callable(captured["handler"])
