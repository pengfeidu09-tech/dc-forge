"""CHAT-M4 integration between FeishuBotService and Requirement Intelligence."""

from __future__ import annotations

import json

from backend.app.solution.chat_agent import BusinessStateSnapshot
from backend.app.solution.feishu_bot import FeishuBotConfig, FeishuBotService
from backend.app.solution.feishu_requirement import FeishuRequirementTurnResult
from backend.app.solution.llm_provider import LLMResponse


class RecordingReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


class RecordingChatProvider:
    def __init__(self, intent: str = "requirement_input") -> None:
        self.intent = intent
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            content=json.dumps(
                {"intent": self.intent, "answer": "这段自由回答不应发送给客户。"},
                ensure_ascii=False,
            )
        )


class RecordingRequirementOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.snapshot_calls: list[str] = []
        self.analyze_calls: list[dict] = []

    def snapshot(self, project_id: str) -> BusinessStateSnapshot:
        self.snapshot_calls.append(project_id)
        return BusinessStateSnapshot(
            phase="collecting",
            latest_requirement_state_version=3,
            readiness_stage="DISCOVERY",
            can_generate_formal_solution=False,
            pending_questions=["采购资料的数据安全边界是什么？"],
            requirement_summary="汽车制造企业；供应商准入依赖人工",
        )

    def analyze_turn(self, **kwargs) -> FeishuRequirementTurnResult:
        self.analyze_calls.append(kwargs)
        if self.fail:
            raise RuntimeError("secret provider response and repository path")
        return FeishuRequirementTurnResult(
            answer="感谢您的说明。为了进一步梳理适合贵司的方案，请确认采购审批规则。",
            state_version=4,
            readiness_stage="DISCOVERY",
            completeness_score=35.0,
            next_question="请确认采购审批规则。",
        )


def _event(text: str = "我们是汽车制造企业，希望优化采购合规。") -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": "event-001",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-001",
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou-owner"},
            },
            "message": {
                "message_id": "message-001",
                "chat_id": "chat-001",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
                "mentions": [],
            },
        },
    }


def _service(intent: str = "requirement_input", *, fail: bool = False):
    provider = RecordingChatProvider(intent)
    reply_client = RecordingReplyClient()
    orchestrator = RecordingRequirementOrchestrator(fail=fail)
    service = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli-test",
            app_secret="secret-test",
            allowed_open_id="ou-owner",
        ),
        reply_client=reply_client,
        provider=provider,
        requirement_orchestrator=orchestrator,
    )
    return service, provider, reply_client, orchestrator


def test_requirement_intent_uses_state_snapshot_and_engine_answer() -> None:
    service, provider, reply_client, orchestrator = _service()

    assert service.process_event(_event()) == "replied"

    prompt = json.dumps(provider.calls[0], ensure_ascii=False)
    assert "汽车制造企业；供应商准入依赖人工" in prompt
    assert "采购资料的数据安全边界是什么" in prompt
    assert "latest_requirement_state_version" not in prompt
    assert "readiness_stage" not in prompt
    assert "DISCOVERY" not in prompt
    assert orchestrator.snapshot_calls == ["feishu:tenant-001:chat-001"]
    assert orchestrator.analyze_calls == [
        {
            "project_id": "feishu:tenant-001:chat-001",
            "message_id": "event-001",
            "message": "我们是汽车制造企业，希望优化采购合规。",
            "sender_open_id": "ou-owner",
            "history": [],
        }
    ]
    assert reply_client.replies == [
        (
            "message-001",
            "感谢您的说明。为了进一步梳理适合贵司的方案，请确认采购审批规则。",
        )
    ]
    customer_answer = reply_client.replies[0][1]
    for internal_term in (
        "状态版本",
        "DISCOVERY",
        "覆盖度",
        "客户确认基线",
        "候选",
    ):
        assert internal_term not in customer_answer


def test_greeting_does_not_create_requirement_state() -> None:
    service, _, reply_client, orchestrator = _service(intent="greeting")

    assert service.process_event(_event("你好")) == "replied"

    assert orchestrator.analyze_calls == []
    assert reply_client.replies == [
        ("message-001", "这段自由回答不应发送给客户。")
    ]


def test_requirement_failure_returns_sanitized_customer_message() -> None:
    service, _, reply_client, orchestrator = _service(fail=True)

    assert service.process_event(_event()) == "failed"

    assert len(orchestrator.analyze_calls) == 1
    answer = reply_client.replies[0][1]
    assert answer == "抱歉，当前服务暂时繁忙，请稍后重新发送刚才的信息。"
    assert "secret" not in answer
    assert "repository" not in answer
    assert "状态池" not in answer
