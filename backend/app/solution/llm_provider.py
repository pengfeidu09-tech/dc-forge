"""LLM Provider 抽象与 OpenAI 兼容实现。

使用 httpx 调用兼容 Chat Completions 的 HTTP 接口，不新增模型 SDK 依赖。
支持依赖注入，测试时可传 FakeLLMProvider。
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict


class LLMResponse(BaseModel):
    """LLM 响应。"""

    model_config = ConfigDict(extra="forbid")

    content: str
    role: str = "assistant"
    warnings: list[str] = []


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
    ) -> None:
        self._api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self._base_url = base_url or os.environ.get("LLM_BASE_URL", "")
        self._model = model or os.environ.get("LLM_MODEL", "")
        self._timeout = timeout

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

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException:
            return LLMResponse(content="", warnings=["LLM 请求超时"])
        except httpx.RequestError:
            return LLMResponse(content="", warnings=["LLM 网络请求失败"])

        if resp.status_code in (401, 403):
            return LLMResponse(content="", warnings=["LLM 认证失败，请检查 API Key"])
        if resp.status_code == 429:
            return LLMResponse(content="", warnings=["LLM 请求被限流"])
        if resp.status_code >= 500:
            return LLMResponse(content="", warnings=[f"LLM 服务端错误: {resp.status_code}"])

        try:
            data = resp.json()
        except Exception:
            return LLMResponse(content="", warnings=["LLM 返回非法 JSON"])

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
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
