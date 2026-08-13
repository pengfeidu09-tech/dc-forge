"""B-M6 LLM Provider 测试。"""

import pytest

from backend.app.solution.llm_provider import (
    FakeLLMProvider,
    LLMResponse,
    OpenAICompatibleProvider,
)


class _CapturedResponse:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": "OK"}}]}


class _CapturedClient:
    instances: list["_CapturedClient"] = []

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.calls: list[dict] = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, *, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _CapturedResponse()


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


def test_openai_provider_no_config_returns_warning(monkeypatch) -> None:
    """未配置环境变量时返回 warning 而非崩溃。"""
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
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


def test_openai_provider_default_payload_omits_optional_request_options(monkeypatch) -> None:
    from backend.app.solution import llm_provider

    _CapturedClient.instances.clear()
    monkeypatch.setattr(llm_provider.httpx, "Client", _CapturedClient)
    provider = OpenAICompatibleProvider(
        api_key="test-key", base_url="https://example.test/v1", model="test-model"
    )

    assert provider.complete([{"role": "user", "content": "test"}]).content == "OK"
    client = _CapturedClient.instances[-1]
    assert client.timeout == 30.0
    assert client.calls[-1]["json"] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "test"}],
        "temperature": 0,
    }


def test_openai_provider_merges_extraction_request_options_without_core_overrides(monkeypatch) -> None:
    from backend.app.solution import llm_provider

    _CapturedClient.instances.clear()
    monkeypatch.setattr(llm_provider.httpx, "Client", _CapturedClient)
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        timeout=90,
        request_options={
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        },
    )

    provider.complete([{"role": "user", "content": "test"}])
    client = _CapturedClient.instances[-1]
    assert client.timeout == 90
    payload = client.calls[-1]["json"]
    assert payload["enable_thinking"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "test-model"
    assert payload["messages"] == [{"role": "user", "content": "test"}]
    assert payload["temperature"] == 0


@pytest.mark.parametrize("reserved", ["model", "messages", "temperature"])
def test_openai_provider_rejects_core_payload_overrides(reserved: str) -> None:
    with pytest.raises(ValueError, match=reserved):
        OpenAICompatibleProvider(request_options={reserved: "forbidden"})
