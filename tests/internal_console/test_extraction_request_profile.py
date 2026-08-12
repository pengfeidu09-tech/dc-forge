import pytest

from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.solution.llm_provider import FakeLLMProvider, OpenAICompatibleProvider


def test_default_internal_console_provider_uses_extraction_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EXTRACTION_LLM_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("EXTRACTION_LLM_ENABLE_THINKING", "false")
    monkeypatch.setenv("EXTRACTION_LLM_RESPONSE_FORMAT", "json_object")
    service = InternalConsoleService(repository=FileRequirementRepository(tmp_path))

    assert isinstance(service.provider, OpenAICompatibleProvider)
    assert service.provider._timeout == 90
    assert service.provider._request_options == {
        "enable_thinking": False,
        "response_format": {"type": "json_object"},
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EXTRACTION_LLM_TIMEOUT_SECONDS", "0"),
        ("EXTRACTION_LLM_ENABLE_THINKING", "not-a-boolean"),
        ("EXTRACTION_LLM_RESPONSE_FORMAT", "text"),
    ],
)
def test_invalid_extraction_profile_environment_is_rejected(monkeypatch, tmp_path, name, value) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        InternalConsoleService(repository=FileRequirementRepository(tmp_path))


def test_injected_provider_does_not_require_or_change_extraction_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EXTRACTION_LLM_TIMEOUT_SECONDS", "not-a-number")
    provider = FakeLLMProvider()
    service = InternalConsoleService(
        repository=FileRequirementRepository(tmp_path), provider=provider
    )

    assert service.provider is provider
