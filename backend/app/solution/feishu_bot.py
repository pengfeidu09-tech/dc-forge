"""Feishu application-bot transport for the requirement conversation agent."""

from __future__ import annotations

import hmac
import json
import logging
import os
from pathlib import Path
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Literal, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.solution.chat_agent import (
    BusinessStateSnapshot,
    ChatAgentRequest,
    ChatTurn,
    run_chat_agent,
)
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.enterprise_assistant import (
    EnterpriseAssistantRequest,
    EnterpriseAssistantService,
)


logger = logging.getLogger(__name__)


class FeishuVerificationError(ValueError):
    """Raised when a callback does not contain the configured verification token."""


class FeishuAPIError(RuntimeError):
    """Raised for sanitized Feishu Open API failures."""


class FeishuBotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    app_id: str = Field(min_length=1)
    app_secret: str = Field(min_length=1)
    verification_token: str = ""
    allowed_open_id: str | None = None
    api_base_url: str = "https://open.feishu.cn"

    @classmethod
    def from_env(
        cls, *, require_verification_token: bool = True
    ) -> "FeishuBotConfig":
        values = {
            "app_id": os.getenv("FEISHU_APP_ID", ""),
            "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
            "verification_token": os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
            "allowed_open_id": os.getenv("FEISHU_ALLOWED_OPEN_ID") or None,
            "api_base_url": os.getenv(
                "FEISHU_API_BASE_URL", "https://open.feishu.cn"
            ),
        }
        required_fields = ["app_id", "app_secret"]
        if require_verification_token:
            required_fields.append("verification_token")
        missing = [name for name in required_fields if not values[name].strip()]
        if missing:
            env_names = {
                "app_id": "FEISHU_APP_ID",
                "app_secret": "FEISHU_APP_SECRET",
                "verification_token": "FEISHU_VERIFICATION_TOKEN",
            }
            required = ", ".join(env_names[name] for name in missing)
            raise RuntimeError(f"Feishu bot is not configured; missing {required}")
        return cls(**values)


class FeishuReplyClient(Protocol):
    def reply_text(self, message_id: str, text: str) -> None:
        ...


class FeishuRequirementOrchestratorProtocol(Protocol):
    def snapshot(self, project_id: str) -> BusinessStateSnapshot | None:
        ...

    def analyze_turn(
        self,
        *,
        project_id: str,
        message_id: str,
        message: str,
        sender_open_id: str | None = None,
    ):
        ...


class CustomerEngagementProtocol(Protocol):
    def active_feishu_project_id(self, tenant_key: str, chat_id: str) -> str: ...

    def start_new_feishu_project(
        self,
        tenant_key: str,
        chat_id: str,
        *,
        sender_open_id: str | None = None,
    ) -> str: ...

    def record_customer_message(
        self,
        *,
        project_id: str,
        channel: str,
        message_id: str,
        event_id: str,
        content: str,
        tenant_key: str | None = None,
        chat_id: str | None = None,
        sender_open_id: str | None = None,
    ) -> None: ...

    def record_agent_message(
        self,
        *,
        project_id: str,
        channel: str,
        message_id: str,
        event_id: str,
        content: str,
        delivery_status: str,
    ) -> None: ...

    def chat_history(self, project_id: str, limit: int = 20) -> list[ChatTurn]: ...

    def customer_portal_url(self, project_id: str) -> str: ...

    def internal_workbench_url(self) -> str: ...


class FeishuAPIClient:
    """Minimal internal-app token and text-reply client."""

    def __init__(
        self,
        config: FeishuBotConfig,
        *,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._config = config
        self._http_client = http_client
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = Lock()

    def _post(self, url: str, **kwargs) -> httpx.Response:
        try:
            if self._http_client is not None:
                return self._http_client.post(url, **kwargs)
            with httpx.Client(timeout=self._timeout) as client:
                return client.post(url, **kwargs)
        except httpx.TimeoutException as error:
            raise FeishuAPIError("Feishu API request timed out") from error
        except httpx.RequestError as error:
            raise FeishuAPIError("Feishu API network request failed") from error

    @staticmethod
    def _payload(response: httpx.Response, operation: str) -> dict:
        if response.status_code >= 400:
            raise FeishuAPIError(
                f"Feishu {operation} failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise FeishuAPIError(f"Feishu {operation} returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise FeishuAPIError(f"Feishu {operation} returned an invalid payload")
        code = payload.get("code", 0)
        if code != 0:
            raise FeishuAPIError(f"Feishu {operation} failed with code {code}")
        return payload

    def _tenant_access_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token
        with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at:
                return self._token
            response = self._post(
                f"{self._config.api_base_url.rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self._config.app_id,
                    "app_secret": self._config.app_secret,
                },
            )
            payload = self._payload(response, "tenant token request")
            token = payload.get("tenant_access_token")
            if not isinstance(token, str) or not token.strip():
                raise FeishuAPIError("Feishu tenant token response omitted the token")
            expire = payload.get("expire", 7200)
            lifetime = expire if isinstance(expire, int) and expire > 120 else 7200
            self._token = token
            self._token_expires_at = now + lifetime - 60
            return token

    def reply_text(self, message_id: str, text: str) -> None:
        token = self._tenant_access_token()
        response = self._post(
            (
                f"{self._config.api_base_url.rstrip('/')}/open-apis/im/v1/messages/"
                f"{quote(message_id, safe='')}/reply"
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        self._payload(response, "message reply")


@dataclass(frozen=True)
class FeishuCallbackValidation:
    kind: Literal["challenge", "event"]
    challenge: str | None = None
    event_id: str | None = None


class FeishuEventDeduplicator:
    def __init__(self, max_entries: int = 2048) -> None:
        self._max_entries = max_entries
        self._order: deque[str] = deque()
        self._seen: set[str] = set()
        self._lock = Lock()

    def claim(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._seen:
                return False
            if len(self._order) >= self._max_entries:
                expired = self._order.popleft()
                self._seen.remove(expired)
            self._order.append(event_id)
            self._seen.add(event_id)
            return True


class ConversationMemory:
    def __init__(self, max_turns: int = 20) -> None:
        self._max_turns = max_turns
        self._turns: dict[str, deque[ChatTurn]] = {}
        self._lock = Lock()

    def history(self, project_id: str) -> list[ChatTurn]:
        with self._lock:
            return list(self._turns.get(project_id, ()))

    def append_exchange(self, project_id: str, user: str, assistant: str) -> None:
        with self._lock:
            turns = self._turns.setdefault(
                project_id, deque(maxlen=self._max_turns)
            )
            turns.append(ChatTurn(role="user", content=user))
            turns.append(ChatTurn(role="assistant", content=assistant))

    def clear(self, project_id: str) -> None:
        with self._lock:
            self._turns.pop(project_id, None)


class FeishuBotService:
    def __init__(
        self,
        config: FeishuBotConfig,
        reply_client: FeishuReplyClient,
        provider: LLMProvider | None = None,
        *,
        deduplicator: FeishuEventDeduplicator | None = None,
        memory: ConversationMemory | None = None,
        requirement_orchestrator: FeishuRequirementOrchestratorProtocol | None = None,
        enterprise_assistant: EnterpriseAssistantService | None = None,
        enterprise_project_id: str = "PRJ-TENDER-001",
        enterprise_user_id: str = "user-procurement-owner",
        enterprise_as_of: str = "2026-10-30T23:59:59+08:00",
        internal_open_ids: set[str] | None = None,
        engagement_service: CustomerEngagementProtocol | None = None,
    ) -> None:
        self._config = config
        self._reply_client = reply_client
        self._provider = provider or OpenAICompatibleProvider()
        self._deduplicator = deduplicator or FeishuEventDeduplicator()
        self._memory = memory or ConversationMemory()
        self._requirement_orchestrator = requirement_orchestrator
        self._enterprise_assistant = enterprise_assistant
        self._enterprise_project_id = enterprise_project_id
        self._enterprise_user_id = enterprise_user_id
        self._enterprise_as_of = enterprise_as_of
        self._internal_open_ids = set(internal_open_ids or ())
        self._engagement_service = engagement_service

    @classmethod
    def from_env(cls) -> "FeishuBotService":
        from backend.app.solution.feishu_requirement import (
            FeishuRequirementOrchestrator,
        )

        config = FeishuBotConfig.from_env()
        provider = OpenAICompatibleProvider()
        from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
        from backend.app.solution.mcp_server import MCPDispatcher

        repository_root = Path(__file__).resolve().parents[3]
        assistant = EnterpriseAssistantService(
            MCPDispatcher(EnterpriseKnowledgeService(repository_root)),
            provider=provider,
        )
        internal_open_ids = {
            value.strip()
            for value in os.getenv("FEISHU_INTERNAL_OPEN_IDS", "").split(",")
            if value.strip()
        }
        requirement_orchestrator = FeishuRequirementOrchestrator.from_env()
        from backend.app.solution.customer_engagement import CustomerEngagementService

        try:
            engagement_service = CustomerEngagementService.from_env(
                feedback_analyzer=requirement_orchestrator
            )
        except RuntimeError:
            logger.warning("Customer engagement persistence is not configured")
            engagement_service = None
        return cls(
            config,
            FeishuAPIClient(config),
            provider=provider,
            requirement_orchestrator=requirement_orchestrator,
            enterprise_assistant=assistant,
            enterprise_project_id=os.getenv(
                "FEISHU_ENTERPRISE_PROJECT_ID", "PRJ-TENDER-001"
            ),
            enterprise_user_id=os.getenv(
                "FEISHU_ENTERPRISE_USER_ID", "user-procurement-owner"
            ),
            enterprise_as_of=os.getenv(
                "FEISHU_ENTERPRISE_AS_OF", "2026-10-30T23:59:59+08:00"
            ),
            internal_open_ids=internal_open_ids,
            engagement_service=engagement_service,
        )

    def _verify_token(self, token: object) -> None:
        if not isinstance(token, str) or not hmac.compare_digest(
            token, self._config.verification_token
        ):
            raise FeishuVerificationError("invalid Feishu verification token")

    def validate_callback(self, payload: dict) -> FeishuCallbackValidation:
        if "encrypt" in payload:
            raise ValueError("encrypted Feishu callbacks are not supported")
        if payload.get("type") == "url_verification":
            self._verify_token(payload.get("token"))
            challenge = payload.get("challenge")
            if not isinstance(challenge, str) or not challenge.strip():
                raise ValueError("Feishu URL verification challenge is required")
            return FeishuCallbackValidation(kind="challenge", challenge=challenge)

        header = payload.get("header")
        if not isinstance(header, dict):
            raise ValueError("Feishu event header is required")
        self._verify_token(header.get("token"))
        event_id = header.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Feishu event_id is required")
        return FeishuCallbackValidation(kind="event", event_id=event_id)

    @staticmethod
    def _message_text(message: dict) -> str | None:
        if message.get("message_type") != "text":
            return None
        content = message.get("content")
        if not isinstance(content, str):
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        text = parsed.get("text") if isinstance(parsed, dict) else None
        if not isinstance(text, str):
            return None
        mentions = message.get("mentions", [])
        if isinstance(mentions, list):
            for mention in mentions:
                if isinstance(mention, dict) and isinstance(mention.get("key"), str):
                    text = text.replace(mention["key"], "")
        text = text.strip()
        return text or None

    @staticmethod
    def _is_customer_capability_question(text: str) -> bool:
        capability_markers = (
            "能力",
            "能做什么",
            "可以做什么",
            "提供哪些帮助",
            "怎么帮助",
            "产品介绍",
        )
        provider_markers = ("你们", "贵司", "你司", "DCForge", "公司")
        return any(marker in text for marker in capability_markers) and any(
            marker in text for marker in provider_markers
        )

    @staticmethod
    def _is_customer_portal_request(text: str) -> bool:
        normalized = text.strip().replace(" ", "")
        return normalized in {
            "/项目",
            "查看需求",
            "查看方案",
            "项目进展",
            "需求与方案",
            "需求方案",
        }

    @staticmethod
    def _is_internal_workbench_request(text: str) -> bool:
        normalized = text.strip().replace(" ", "")
        return normalized in {"/客户工作台", "客户工作台", "客户需求工作台"}

    @staticmethod
    def _project_reset_request(text: str) -> Literal["confirm", "prompt"] | None:
        normalized = text.strip().replace(" ", "")
        if normalized in {"/清空记忆确认", "/新项目确认"}:
            return "confirm"
        if normalized in {"/清空记忆", "/新项目"}:
            return "prompt"
        return None

    def _record_customer_message(
        self,
        *,
        project_id: str,
        message_id: str,
        event_id: str,
        content: str,
        tenant_key: str,
        chat_id: str,
        sender_open_id: str | None,
    ) -> None:
        if self._engagement_service is None:
            return
        try:
            self._engagement_service.record_customer_message(
                project_id=project_id,
                channel="feishu",
                message_id=message_id,
                event_id=event_id,
                content=content,
                tenant_key=tenant_key,
                chat_id=chat_id,
                sender_open_id=sender_open_id,
            )
        except Exception:
            logger.warning("Customer conversation persistence failed")

    def _record_agent_message(
        self,
        *,
        project_id: str,
        message_id: str,
        event_id: str,
        content: str,
        delivery_status: Literal["replied", "failed"],
    ) -> None:
        if self._engagement_service is None:
            return
        try:
            self._engagement_service.record_agent_message(
                project_id=project_id,
                channel="feishu",
                message_id=message_id,
                event_id=event_id,
                content=content,
                delivery_status=delivery_status,
            )
        except Exception:
            logger.warning("Agent conversation persistence failed")

    def process_event(self, payload: dict) -> str:
        header = payload.get("header")
        event = payload.get("event")
        if not isinstance(header, dict) or not isinstance(event, dict):
            return "ignored"
        if header.get("event_type") != "im.message.receive_v1":
            return "ignored"

        sender = event.get("sender")
        message = event.get("message")
        if not isinstance(sender, dict) or not isinstance(message, dict):
            return "ignored"
        if sender.get("sender_type") != "user":
            return "ignored"
        sender_id = sender.get("sender_id")
        sender_open_id = (
            sender_id.get("open_id") if isinstance(sender_id, dict) else None
        )
        if self._config.allowed_open_id:
            if sender_open_id != self._config.allowed_open_id:
                return "ignored"

        text = self._message_text(message)
        if text is None:
            return "ignored"
        event_id = header.get("event_id")
        message_id = message.get("message_id")
        tenant_key = header.get("tenant_key")
        chat_id = message.get("chat_id")
        if not all(isinstance(value, str) and value.strip() for value in (
            event_id, message_id, tenant_key, chat_id
        )):
            return "ignored"
        if not self._deduplicator.claim(event_id):
            return "duplicate"

        project_id = f"feishu:{tenant_key}:{chat_id}"
        if self._engagement_service is not None:
            try:
                project_id = self._engagement_service.active_feishu_project_id(
                    tenant_key, chat_id
                )
            except Exception:
                logger.warning("Active Feishu project mapping is unavailable")
        is_internal = (
            isinstance(sender_open_id, str)
            and sender_open_id in self._internal_open_ids
        )
        is_allowlisted_creator = bool(
            self._config.allowed_open_id
            and sender_open_id == self._config.allowed_open_id
        )
        reset_request = self._project_reset_request(text)
        if reset_request is not None:
            if not (is_internal or is_allowlisted_creator):
                answer = "该指令仅供已授权的企业内部人员使用。"
            elif self._engagement_service is None:
                answer = "项目存储暂时不可用，当前会话未做任何修改。"
            elif reset_request == "prompt":
                answer = (
                    "该操作会在当前群开启全新项目，旧项目将归档保留。"
                    "如需继续，请发送：/清空记忆 确认"
                )
            else:
                try:
                    self._engagement_service.start_new_feishu_project(
                        tenant_key,
                        chat_id,
                        sender_open_id=(
                            sender_open_id
                            if isinstance(sender_open_id, str)
                            else None
                        ),
                    )
                    self._memory.clear(project_id)
                    answer = (
                        "已在当前群开启全新项目。旧项目已归档保留，"
                        "不会参与新的需求分析。请重新发送客户背景和本次项目范围。"
                    )
                except Exception:
                    logger.warning("Starting a clean Feishu project failed")
                    answer = "新项目创建失败，旧项目未被删除，请稍后重试。"
            try:
                self._reply_client.reply_text(message_id, answer)
            except Exception:
                logger.warning("Feishu reply failed for message_id=%s", message_id)
                return "failed"
            return "replied"
        if (
            (is_internal or is_allowlisted_creator)
            and self._engagement_service is not None
            and self._is_internal_workbench_request(text)
        ):
            answer = (
                "客户需求工作台："
                + self._engagement_service.internal_workbench_url()
            )
            try:
                self._reply_client.reply_text(message_id, answer)
            except Exception:
                logger.warning("Feishu reply failed for message_id=%s", message_id)
                return "failed"
            return "replied"

        persistent_history: list[ChatTurn] = []
        if not is_internal:
            if self._engagement_service is not None:
                try:
                    persistent_history = self._engagement_service.chat_history(
                        project_id, limit=20
                    )
                except Exception:
                    logger.warning("Persistent customer conversation history unavailable")
            self._record_customer_message(
                project_id=project_id,
                message_id=message_id,
                event_id=event_id,
                content=text,
                tenant_key=tenant_key,
                chat_id=chat_id,
                sender_open_id=(
                    sender_open_id if isinstance(sender_open_id, str) else None
                ),
            )

        if (
            not (is_internal or is_allowlisted_creator)
            and self._engagement_service is not None
            and self._is_customer_portal_request(text)
        ):
            answer = (
                "您可以在这里查看当前需求理解和已发布方案："
                + self._engagement_service.customer_portal_url(project_id)
            )
            self._memory.append_exchange(project_id, text, answer)
            try:
                self._reply_client.reply_text(message_id, answer)
            except Exception:
                self._record_agent_message(
                    project_id=project_id,
                    message_id=message_id,
                    event_id=event_id,
                    content=answer,
                    delivery_status="failed",
                )
                logger.warning("Feishu reply failed for message_id=%s", message_id)
                return "failed"
            self._record_agent_message(
                project_id=project_id,
                message_id=message_id,
                event_id=event_id,
                content=answer,
                delivery_status="replied",
            )
            return "replied"

        if text.startswith("/mcp"):
            if not (is_internal or is_allowlisted_creator):
                answer = "该指令仅供已授权的企业内部人员使用。"
                self._memory.append_exchange(project_id, text, answer)
                try:
                    self._reply_client.reply_text(message_id, answer)
                except Exception:
                    self._record_agent_message(
                        project_id=project_id,
                        message_id=message_id,
                        event_id=event_id,
                        content=answer,
                        delivery_status="failed",
                    )
                    logger.warning("Feishu reply failed for message_id=%s", message_id)
                    return "failed"
                self._record_agent_message(
                    project_id=project_id,
                    message_id=message_id,
                    event_id=event_id,
                    content=answer,
                    delivery_status="replied",
                )
                return "replied"
            if self._enterprise_assistant is None:
                answer = "抱歉，企业知识服务暂时不可用，请稍后重试。"
                try:
                    self._reply_client.reply_text(message_id, answer)
                except Exception:
                    logger.warning("Feishu reply failed for message_id=%s", message_id)
                    return "failed"
                return "replied"
            query = text.removeprefix("/mcp").strip()
            if not query:
                answer = "请在 /mcp 后输入需求版本、供应商、文档审查或方案问题。"
            else:
                try:
                    result = self._enterprise_assistant.answer(
                        EnterpriseAssistantRequest(
                            project_id=self._enterprise_project_id,
                            user_id=self._enterprise_user_id,
                            as_of=self._enterprise_as_of,
                            message=query,
                            audience="internal",
                        )
                    )
                    answer = result.answer
                    if result.citations:
                        answer += "\n\n来源：" + "、".join(result.citations)
                except Exception:
                    logger.warning("Enterprise MCP assistant failed for Feishu event")
                    answer = "抱歉，企业知识服务暂时不可用，请稍后重试。"
            self._memory.append_exchange(self._enterprise_project_id, text, answer)
            try:
                self._reply_client.reply_text(message_id, answer)
            except Exception:
                logger.warning("Feishu reply failed for message_id=%s", message_id)
                return "failed"
            return "replied"

        if is_internal and self._enterprise_assistant is not None:
            try:
                result = self._enterprise_assistant.answer(
                    EnterpriseAssistantRequest(
                        project_id=self._enterprise_project_id,
                        user_id=self._enterprise_user_id,
                        as_of=self._enterprise_as_of,
                        message=text,
                        audience="internal",
                    )
                )
                answer = result.answer
                if result.citations:
                    answer += "\n\n来源：" + "、".join(result.citations)
            except Exception:
                logger.warning("Enterprise Agent failed for Feishu internal event")
                answer = "抱歉，企业知识服务暂时不可用，请稍后重试。"
            self._memory.append_exchange(self._enterprise_project_id, text, answer)
            try:
                self._reply_client.reply_text(message_id, answer)
            except Exception:
                logger.warning("Feishu reply failed for message_id=%s", message_id)
                return "failed"
            return "replied"

        state = None
        if self._requirement_orchestrator is not None:
            try:
                state = self._requirement_orchestrator.snapshot(project_id)
            except Exception:
                logger.warning("Requirement state snapshot unavailable")
        request = ChatAgentRequest(
            project_id=project_id,
            message_id=event_id,
            message=text,
            history=self._memory.history(project_id) or persistent_history,
            state=state,
        )
        response = run_chat_agent(request, provider=self._provider)
        answer = response.answer
        analysis_failed = False
        if (
            response.next_action == "analyze_requirements"
            and self._requirement_orchestrator is not None
        ):
            sender_id = sender.get("sender_id")
            sender_open_id = (
                sender_id.get("open_id") if isinstance(sender_id, dict) else None
            )
            try:
                requirement_result = self._requirement_orchestrator.analyze_turn(
                    project_id=project_id,
                    message_id=event_id,
                    message=text,
                    sender_open_id=(
                        sender_open_id if isinstance(sender_open_id, str) else None
                    ),
                )
                answer = requirement_result.answer
            except Exception:
                logger.warning("Requirement analysis failed for Feishu event")
                answer = "抱歉，当前服务暂时繁忙，请稍后重新发送刚才的信息。"
                analysis_failed = True
        elif (
            response.intent == "general"
            or (
                response.intent == "solution_request"
                and response.next_action == "none"
                and self._is_customer_capability_question(text)
            )
        ) and self._enterprise_assistant is not None:
            try:
                knowledge_result = self._enterprise_assistant.answer(
                    EnterpriseAssistantRequest(
                        project_id="PUBLIC-CAPABILITIES",
                        user_id="external-customer",
                        as_of=self._enterprise_as_of,
                        message=text,
                        audience="customer",
                    )
                )
                answer = knowledge_result.answer
                if knowledge_result.citations:
                    answer += "\n\n来源：" + "、".join(
                        knowledge_result.citations
                    )
            except Exception:
                logger.warning("Public capability Agent failed for Feishu customer")
        self._memory.append_exchange(project_id, text, answer)
        try:
            self._reply_client.reply_text(message_id, answer)
        except Exception:
            self._record_agent_message(
                project_id=project_id,
                message_id=message_id,
                event_id=event_id,
                content=answer,
                delivery_status="failed",
            )
            logger.warning("Feishu reply failed for message_id=%s", message_id)
            return "failed"
        self._record_agent_message(
            project_id=project_id,
            message_id=message_id,
            event_id=event_id,
            content=answer,
            delivery_status="replied",
        )
        return "failed" if analysis_failed else "replied"
