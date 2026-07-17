"""B-M6 LLM Provider 测试。"""

from backend.app.solution.llm_provider import (
    FakeLLMProvider,
    LLMResponse,
    OpenAICompatibleProvider,
)


def test_fake_provider_returns_preset_response() -> None:
    """FakeProvider 按预设顺序返回响应。"""
    provider = FakeLLMProvider(responses=['{"intent": "compile"}', '{"intent": "review"}'])
    r1 = provider.complete([{"role": "user", "content": "test"}])
    r2 = provider.complete([{"role": "user", "content": "test"}])
    assert r1.content == '{"intent": "compile"}'
    assert r2.content == '{"intent": "review"}'


def test_fake_provider_defaults_when_empty() -> None:
    """FakeProvider 超出预设数量时返回默认响应。"""
    provider = FakeLLMProvider(responses=[])
    r = provider.complete([{"role": "user", "content": "test"}])
    assert "compile" in r.content


def test_openai_provider_no_config_returns_warning() -> None:
    """未配置环境变量时返回 warning 而非崩溃。"""
    provider = OpenAICompatibleProvider(api_key="", base_url="", model="")
    r = provider.complete([{"role": "user", "content": "test"}])
    assert r.content == ""
    assert len(r.warnings) > 0
    assert "未配置" in r.warnings[0]


def test_openai_provider_error_no_api_key_in_message() -> None:
    """错误信息不得包含 API Key。"""
    provider = OpenAICompatibleProvider(
        api_key="sk-secret-key-12345",
        base_url="http://localhost:99999",
        model="test-model",
        timeout=0.001,
    )
    r = provider.complete([{"role": "user", "content": "test"}])
    for w in r.warnings:
        assert "sk-secret-key-12345" not in w, f"API Key 泄露到 warning: {w}"
    assert r.content == ""


def test_llm_response_validates_against_model() -> None:
    """LLMResponse 通过 Pydantic 校验。"""
    resp = LLMResponse(content="hello", role="assistant", warnings=[])
    LLMResponse.model_validate(resp.model_dump())
    assert resp.content == "hello"
