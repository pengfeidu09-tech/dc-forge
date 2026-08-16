"""LLM Provider 抽象与 OpenAI 兼容实现。

使用 httpx 调用兼容 Chat Completions 的 HTTP 接口，不新增模型 SDK 依赖。
支持依赖注入，测试时可传 FakeLLMProvider。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field


class LLMResponse(BaseModel):
    """LLM 响应。"""

    model_config = ConfigDict(extra="forbid")

    content: str
    role: str = "assistant"
    warnings: list[str] = Field(default_factory=list)


class LLMProvider(Protocol):
    """LLM Provider 协议，支持依赖注入。"""

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        ...


class OpenAICompatibleProvider:
    """OpenAI 兼容 Chat Completions Provider。

    从环境变量读取配置：
    - LLM_API_KEY: API 密钥
    - LLM_BASE_URL: API 基地址
    - LLM_MODEL: 模型名称
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        request_options: dict[str, Any] | None = None,
        max_retries: int = 2,
        max_retry_delay: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        reserved_options = {"model", "messages", "temperature"}
        supplied_options = request_options or {}
        forbidden_options = reserved_options & set(supplied_options)
        if forbidden_options:
            raise ValueError(
                "request_options cannot override core payload fields: "
                + ", ".join(sorted(forbidden_options))
            )
        if not 0 <= max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")
        if not 0 <= max_retry_delay <= 10:
            raise ValueError("max_retry_delay must be between 0 and 10")
        self._api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self._base_url = base_url or os.environ.get("LLM_BASE_URL", "")
        self._model = model or os.environ.get("LLM_MODEL", "")
        self._timeout = timeout
        self._request_options = dict(supplied_options)
        self._max_retries = max_retries
        self._max_retry_delay = max_retry_delay
        self._sleep = sleep

    def _retry_delay(self, response: Any | None, attempt: int) -> float:
        retry_after = None
        headers = getattr(response, "headers", None)
        if headers is not None:
            retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), self._max_retry_delay)
            except ValueError:
                pass
        return min(0.25 * (2**attempt), self._max_retry_delay)

    @staticmethod
    def _response_warning(status_code: int) -> str:
        if status_code in (401, 403):
            return "LLM 认证失败，请检查 API Key"
        if status_code == 429:
            return "LLM 请求被限流"
        if status_code >= 500:
            return f"LLM 服务端错误: {status_code}"
        return f"LLM 请求失败: {status_code}"

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """调用 Chat Completions API。"""
        if not self._api_key or not self._base_url or not self._model:
            return LLMResponse(
                content="",
                warnings=["LLM 未配置：缺少 LLM_API_KEY、LLM_BASE_URL 或 LLM_MODEL"],
            )

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
        payload.update(self._request_options)

        transient_statuses = {429, 502, 503, 504}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                for attempt in range(self._max_retries + 1):
                    try:
                        resp = client.post(
                            url,
                            json=payload,
                            headers={
                                "Authorization": f"Bearer {self._api_key}",
                                "Content-Type": "application/json",
                            },
                        )
                    except (httpx.TimeoutException, httpx.RequestError) as error:
                        if attempt < self._max_retries:
                            self._sleep(self._retry_delay(None, attempt))
                            continue
                        warning = (
                            "LLM 请求超时"
                            if isinstance(error, httpx.TimeoutException)
                            else "LLM 网络请求失败"
                        )
                        return LLMResponse(content="", warnings=[warning])
                    if (
                        resp.status_code in transient_statuses
                        and attempt < self._max_retries
                    ):
                        self._sleep(self._retry_delay(resp, attempt))
                        continue
                    break
        except (httpx.TimeoutException, httpx.RequestError) as error:
            warning = (
                "LLM 请求超时"
                if isinstance(error, httpx.TimeoutException)
                else "LLM 网络请求失败"
            )
            return LLMResponse(content="", warnings=[warning])

        if not 200 <= resp.status_code < 300:
            return LLMResponse(
                content="",
                warnings=[self._response_warning(resp.status_code)],
            )

        headers = getattr(resp, "headers", None)
        if headers is not None:
            raw_length = headers.get("Content-Length")
            try:
                if raw_length and int(raw_length) > 2_000_000:
                    return LLMResponse(content="", warnings=["LLM 响应过大"])
            except ValueError:
                pass
            content_type = headers.get("Content-Type", "")
            if content_type and "json" not in content_type.casefold():
                return LLMResponse(content="", warnings=["LLM 返回非 JSON 响应"])

        try:
            data = resp.json()
        except (json.JSONDecodeError, TypeError, ValueError):
            return LLMResponse(content="", warnings=["LLM 返回非法 JSON"])

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return LLMResponse(content="", warnings=["LLM 响应格式异常"])

        if content is not None and not isinstance(content, str):
            return LLMResponse(content="", warnings=["LLM 响应格式异常"])

        return LLMResponse(content=content or "")


class FakeLLMProvider:
    """测试用 Fake Provider，按预设规则返回响应。

    根据 messages 内容匹配预设响应，不调用真实 API。
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        if self._call_count < len(self._responses):
            content = self._responses[self._call_count]
        else:
            content = '{"intent": "compile", "answer": "默认编译响应"}'
        self._call_count += 1
        return LLMResponse(content=content)
