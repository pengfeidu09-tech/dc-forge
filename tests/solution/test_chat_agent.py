"""CHAT-M1 basic requirement conversation agent tests."""

from __future__ import annotations

import json

import pytest

from backend.app.solution.chat_agent import (
    BusinessStateSnapshot,
    ChatAgentRequest,
    ChatAgentResponse,
    ChatTurn,
    run_chat_agent,
)
from backend.app.solution.llm_provider import LLMResponse


class CapturingProvider:
    def __init__(self, content: str, warnings: list[str] | None = None) -> None:
        self.content = content
        self.warnings = warnings or []
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self.content, warnings=self.warnings)


def _request(
    message: str = "我们希望缩短采购文件审查时间",
    *,
    state: BusinessStateSnapshot | None = None,
    history: list[ChatTurn] | None = None,
) -> ChatAgentRequest:
    return ChatAgentRequest(
        project_id="customer-project-001",
        message_id="feishu-event-001",
        message=message,
        history=history or [],
        state=state,
    )


def _model_response(intent: str, answer: str = "我已记录这项需求。") -> str:
    return json.dumps({"intent": intent, "answer": answer}, ensure_ascii=False)


@pytest.mark.parametrize("intent", ["requirement_input", "clarification_answer", "feedback"])
def test_requirement_messages_route_to_analysis(intent: str) -> None:
    result = run_chat_agent(
        _request(),
        provider=CapturingProvider(_model_response(intent)),
    )

    assert result.status == "ok"
    assert result.intent == intent
    assert result.next_action == "analyze_requirements"


def test_confirmation_only_prepares_explicit_confirmation() -> None:
    result = run_chat_agent(
        _request("以上需求我确认"),
        provider=CapturingProvider(_model_response("confirmation", "我会展示待确认项。")),
    )

    assert result.status == "ok"
    assert result.next_action == "prepare_confirmation"
    assert "确认" in result.answer


def test_solution_request_requires_formal_readiness() -> None:
    not_ready = run_chat_agent(
        _request(
            "请生成方案",
            state=BusinessStateSnapshot(
                phase="collecting",
                readiness_stage="DISCOVERY",
                can_generate_formal_solution=False,
            ),
        ),
        provider=CapturingProvider(_model_response("solution_request")),
    )
    ready = run_chat_agent(
        _request(
            "请生成方案",
            state=BusinessStateSnapshot(
                phase="confirmed_ready",
                readiness_stage="CONFIRMED_READY",
                can_generate_formal_solution=True,
                latest_requirement_state_version=4,
                latest_baseline_version=1,
            ),
        ),
        provider=CapturingProvider(_model_response("solution_request")),
    )

    assert not_ready.next_action == "none"
    assert ready.next_action == "compile_solution"


def test_history_and_customer_safe_business_context_are_sent_to_model() -> None:
    provider = CapturingProvider(_model_response("clarification_answer"))
    request = _request(
        "必须部署在客户私域",
        history=[
            ChatTurn(role="assistant", content="数据部署在哪里？"),
            ChatTurn(role="user", content="我们需要内部确认。"),
        ],
        state=BusinessStateSnapshot(
            phase="collecting",
            latest_requirement_state_version=3,
            readiness_stage="DISCOVERY",
            pending_questions=["数据部署在哪里？"],
            requirement_summary="客户正在补充安全约束。",
        ),
    )

    run_chat_agent(request, provider=provider)

    assert len(provider.calls) == 1
    messages = provider.calls[0]
    serialized = json.dumps(messages, ensure_ascii=False)
    assert "数据部署在哪里" in serialized
    assert "客户正在补充安全约束" in serialized
    assert "latest_requirement_state_version" not in serialized
    assert "readiness_stage" not in serialized
    assert "DISCOVERY" not in serialized
    assert "customer-project-001" not in serialized
    assert messages[-1]["role"] == "user"
    assert "必须部署在客户私域" in messages[-1]["content"]
    assert "untrusted" in messages[0]["content"].lower()


def test_model_answer_with_internal_requirement_metadata_is_not_delivered() -> None:
    result = run_chat_agent(
        _request("现在进展怎么样？"),
        provider=CapturingProvider(
            _model_response(
                "general",
                "当前 state_version=3，readiness_stage=DISCOVERY，技能是 "
                "automotive-procurement-v1。",
            )
        ),
    )

    assert result.status == "ok"
    assert result.intent == "general"
    assert result.answer == "我还缺少足够信息来回答。请告诉我您想了解的业务环节或当前做法。"
    assert "state_version" not in result.answer
    assert "DISCOVERY" not in result.answer
    assert "automotive-procurement-v1" not in result.answer


def test_model_cannot_choose_an_arbitrary_action() -> None:
    content = json.dumps(
        {
            "intent": "greeting",
            "answer": "你好，请介绍一下业务需求。",
            "next_action": "compile_solution",
            "tool": "delete_project",
        },
        ensure_ascii=False,
    )

    result = run_chat_agent(_request("你好"), provider=CapturingProvider(content))

    assert result.status == "ok"
    assert result.intent == "greeting"
    assert result.next_action == "none"


@pytest.mark.parametrize("content", ["", "not-json", '{"intent":"unknown","answer":"x"}'])
def test_invalid_or_empty_model_output_is_unavailable(content: str) -> None:
    result = run_chat_agent(
        _request(),
        provider=CapturingProvider(content, warnings=["LLM 暂不可用"]),
    )

    assert result.status == "unavailable"
    assert result.intent is None
    assert result.next_action == "none"
    assert result.answer
    assert "LLM 暂不可用" in result.warnings


def test_response_does_not_leak_provider_secret() -> None:
    result = run_chat_agent(
        _request(),
        provider=CapturingProvider("", warnings=["request failed for sk-secret-123456789"]),
    )

    assert "sk-secret-123456789" not in result.model_dump_json()
    assert "[REDACTED]" in result.warnings[0]


def test_models_are_strict_and_history_is_bounded() -> None:
    with pytest.raises(Exception):
        ChatAgentRequest.model_validate(
            {
                "project_id": "project",
                "message_id": "message",
                "message": "hello",
                "extra": "forbidden",
            }
        )

    with pytest.raises(Exception):
        ChatAgentRequest(
            project_id="project",
            message_id="message",
            message="hello",
            history=[ChatTurn(role="user", content=str(index)) for index in range(21)],
        )

    response = run_chat_agent(
        _request("你好"),
        provider=CapturingProvider(_model_response("greeting", "你好，请介绍业务场景。")),
    )
    ChatAgentResponse.model_validate(response.model_dump())
