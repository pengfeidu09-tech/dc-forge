"""B-M6 Solution Agent 测试。"""

import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import SolutionBundle, SolutionPlan
from backend.app.solution.agent import (
    AgentRequest,
    AgentResponse,
    AgentToolCall,
    run_solution_agent,
)
from backend.app.solution.llm_provider import FakeLLMProvider, LLMResponse

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_process_spec() -> ProcessSpec:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return ProcessSpec.model_validate(data)


def _get_balanced_plan() -> SolutionPlan:
    from backend.app.solution import compile_solution

    bundle = compile_solution(_load_process_spec())
    return next(p for p in bundle.plans if p.plan_type == "balanced")


def _make_request(message: str, selected: SolutionPlan | None = None) -> AgentRequest:
    return AgentRequest(
        process=_load_process_spec(),
        message=message,
        selected_solution=selected,
    )


_COMPILE_RESP = '{"intent": "compile", "constraint": null, "missing_info": null, "answer": "编译三套方案"}'
_REVIEW_RESP = '{"intent": "review", "constraint": null, "missing_info": null, "answer": "评审方案"}'
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
_EXPLAIN_RESP = '{"intent": "explain", "constraint": null, "missing_info": null, "answer": "解释评分"}'
_EXPLAIN_FOLLOWUP = "balanced 评分较高因为约束合规和可行性维度表现好"


def test_compile_intent_calls_compile_solution() -> None:
    """compile 意图调用 compile_solution。"""
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("生成三套方案"), provider=provider)
    assert result.intent == "compile"
    assert result.solution_bundle is not None
    assert len(result.solution_bundle.plans) == 3
    tool_names = [tc.tool_name for tc in result.tool_calls]
    assert "compile_solution" in tool_names


def test_recompile_intent_calls_recompile_solution() -> None:
    """recompile 意图调用 recompile_solution。"""
    balanced = _get_balanced_plan()
    provider = FakeLLMProvider(responses=[_RECOMPILE_RESP])
    result = run_solution_agent(
        _make_request("客户要求数据不出域", selected=balanced),
        provider=provider,
    )
    assert result.intent == "recompile"
    assert result.recompile_result is not None
    assert "data-masking" in result.recompile_result.added_component_ids
    assert "local-model" in result.recompile_result.added_component_ids


def test_review_intent_calls_validate_and_review() -> None:
    """review 意图调用 validate_constraints 和 review_solution。"""
    balanced = _get_balanced_plan()
    provider = FakeLLMProvider(responses=[_REVIEW_RESP])
    result = run_solution_agent(
        _make_request("评审这个方案", selected=balanced),
        provider=provider,
    )
    assert result.intent == "review"
    assert result.review is not None
    assert 0 <= result.review.score <= 100
    tool_names = [tc.tool_name for tc in result.tool_calls]
    assert "validate_constraints" in tool_names
    assert "review_solution" in tool_names


def test_agent_does_not_fake_solution_bundle() -> None:
    """Agent 不直接伪造 SolutionBundle（来自确定性工具）。"""
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("编译"), provider=provider)
    assert result.solution_bundle is not None
    # 验证 solution_bundle 来自真实的 compile_solution（有真实 review_score > 0）
    for plan in result.solution_bundle.plans:
        assert plan.review_score > 0, "review_score 应来自真实 Reviewer，非伪造"


def test_tool_calls_are_recorded() -> None:
    """工具调用轨迹完整。"""
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("编译"), provider=provider)
    assert len(result.tool_calls) > 0
    for tc in result.tool_calls:
        assert tc.step > 0
        assert tc.tool_name
        assert tc.status in ("success", "failed")
        assert len(tc.summary) > 0


def test_max_steps_limit() -> None:
    """最大步骤限制有效。"""
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("编译"), provider=provider, max_steps=1)
    # max_steps=1 时只能执行意图识别，无法执行工具
    assert len(result.tool_calls) <= 1


def test_invalid_constraint_rejected() -> None:
    """非法约束被拒绝。"""
    bad_resp = json.dumps({
        "intent": "recompile",
        "constraint": {"id": "", "type": "unknown_type", "statement": ""},
        "missing_info": None,
        "answer": "...",
    })
    balanced = _get_balanced_plan()
    provider = FakeLLMProvider(responses=[bad_resp])
    result = run_solution_agent(
        _make_request("加个约束", selected=balanced),
        provider=provider,
    )
    assert result.intent == "recompile"
    assert result.recompile_result is None
    assert any("约束" in w for w in result.warnings)


def test_missing_selected_solution_for_review() -> None:
    """缺少 selected_solution 时无法 review。"""
    provider = FakeLLMProvider(responses=[_REVIEW_RESP])
    result = run_solution_agent(_make_request("评审方案"), provider=provider)
    assert "selected_solution" in " ".join(result.warnings) or "已选方案" in result.answer


def test_provider_timeout_returns_warning() -> None:
    """Provider 超时返回明确 warning。"""
    class TimeoutProvider:
        def complete(self, messages, tools=None):
            return LLMResponse(content="", warnings=["LLM 请求超时"])

    result = run_solution_agent(_make_request("编译"), provider=TimeoutProvider())
    assert any("超时" in w or "回退" in w for w in result.warnings)


def test_provider_failure_falls_back_to_compile() -> None:
    """Provider 失败时 compile 可以确定性回退。"""
    class FailProvider:
        def complete(self, messages, tools=None):
            return LLMResponse(content="", warnings=["LLM 不可用"])

    result = run_solution_agent(_make_request("编译"), provider=FailProvider())
    assert result.intent == "compile"
    assert result.solution_bundle is not None
    assert len(result.solution_bundle.plans) == 3
    assert any("回退" in w for w in result.warnings)


def test_no_api_key_in_warnings() -> None:
    """API Key 不出现在错误信息中。"""
    class LeakProvider:
        def complete(self, messages, tools=None):
            return LLMResponse(content="", warnings=["LLM 认证失败，请检查 API Key"])

    result = run_solution_agent(_make_request("编译"), provider=LeakProvider())
    for w in result.warnings:
        assert "sk-" not in w, f"可能的 API Key 泄露: {w}"


def test_deterministic_with_fake_provider() -> None:
    """相同输入和 FakeProvider 响应结果稳定。"""
    provider1 = FakeLLMProvider(responses=[_COMPILE_RESP])
    provider2 = FakeLLMProvider(responses=[_COMPILE_RESP])
    r1 = run_solution_agent(_make_request("编译"), provider=provider1)
    r2 = run_solution_agent(_make_request("编译"), provider=provider2)
    assert r1.model_dump() == r2.model_dump()


def test_agent_response_validates() -> None:
    """AgentResponse 通过模型校验。"""
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("编译"), provider=provider)
    AgentResponse.model_validate(result.model_dump())


def test_only_allowed_tools_in_tool_calls() -> None:
    """tool_calls 中只包含允许的工具。"""
    allowed = {"compile_solution", "review_solution", "recompile_solution",
               "validate_constraints", "retrieve_components"}
    provider = FakeLLMProvider(responses=[_COMPILE_RESP])
    result = run_solution_agent(_make_request("编译"), provider=provider)
    for tc in result.tool_calls:
        assert tc.tool_name in allowed, f"不允许的工具: {tc.tool_name}"


def test_agent_request_rejects_extra_fields() -> None:
    """AgentRequest 拒绝 extra 字段。"""
    import pytest

    with pytest.raises(Exception):
        AgentRequest.model_validate({
            "process": json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8")),
            "message": "test",
            "extra_field": "bad",
        })
