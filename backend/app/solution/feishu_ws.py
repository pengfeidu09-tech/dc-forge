"""Feishu long-connection adapter for DCForge's conversation service."""

from __future__ import annotations

import logging
import os
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.app.solution.feishu_bot import (
    FeishuAPIClient,
    FeishuBotConfig,
    FeishuBotService,
)
from backend.app.solution.llm_provider import OpenAICompatibleProvider


logger = logging.getLogger(__name__)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _nonempty(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def normalize_feishu_ws_event(event: Any) -> dict:
    """Convert the official SDK event model to CHAT-M2's normalized envelope."""
    header = _get(event, "header")
    event_data = _get(event, "event")
    sender = _get(event_data, "sender")
    sender_id = _get(sender, "sender_id")
    message = _get(event_data, "message")

    normalized_header = {
        key: value
        for key in ("event_id", "event_type", "tenant_key", "token")
        if (value := _nonempty(_get(header, key))) is not None
    }
    normalized_sender_id = {
        key: value
        for key in ("user_id", "open_id", "union_id")
        if (value := _nonempty(_get(sender_id, key))) is not None
    }
    normalized_sender: dict[str, Any] = {
        key: value
        for key in ("sender_type", "tenant_key")
        if (value := _nonempty(_get(sender, key))) is not None
    }
    if normalized_sender_id:
        normalized_sender["sender_id"] = normalized_sender_id

    mentions: list[dict[str, str]] = []
    raw_mentions = _get(message, "mentions", [])
    if isinstance(raw_mentions, list):
        for mention in raw_mentions:
            normalized_mention = {
                key: value
                for key in ("key", "name", "mentioned_type", "tenant_key")
                if (value := _nonempty(_get(mention, key))) is not None
            }
            if normalized_mention:
                mentions.append(normalized_mention)

    normalized_message: dict[str, Any] = {
        key: value
        for key in (
            "message_id",
            "root_id",
            "parent_id",
            "chat_id",
            "thread_id",
            "chat_type",
            "message_type",
            "content",
        )
        if (value := _nonempty(_get(message, key))) is not None
    }
    normalized_message["mentions"] = mentions

    return {
        "schema": _nonempty(_get(event, "schema")) or "2.0",
        "header": normalized_header,
        "event": {
            "sender": normalized_sender,
            "message": normalized_message,
        },
    }


class FeishuWebSocketAdapter:
    """Acknowledge SDK callbacks quickly and process chat turns in a worker."""

    def __init__(
        self,
        service: FeishuBotService,
        *,
        executor: Executor | None = None,
    ) -> None:
        self._service = service
        self._executor = executor or ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="dcforge-feishu"
        )

    def handle(self, event: Any) -> None:
        try:
            payload = normalize_feishu_ws_event(event)
            self._executor.submit(self._service.process_event, payload)
        except Exception:
            logger.warning("Feishu WebSocket event scheduling failed")
        return None


def _load_lark_sdk() -> Any:
    try:
        import lark_oapi as lark
    except ImportError as error:
        raise RuntimeError(
            "Feishu WebSocket support requires the lark-oapi package"
        ) from error
    return lark


def build_feishu_websocket_client(
    config: FeishuBotConfig,
    *,
    service: FeishuBotService | None = None,
    sdk: Any | None = None,
    executor: Executor | None = None,
) -> Any:
    """Build the official SDK client while keeping the business service injectable."""
    lark = sdk or _load_lark_sdk()
    if service is None:
        from backend.app.solution.enterprise_assistant import EnterpriseAssistantService
        from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
        from backend.app.solution.feishu_requirement import (
            FeishuRequirementOrchestrator,
        )
        from backend.app.solution.mcp_server import MCPDispatcher

        provider = OpenAICompatibleProvider()
        repository_root = Path(__file__).resolve().parents[3]
        dispatcher = MCPDispatcher(EnterpriseKnowledgeService(repository_root))
        from backend.app.solution.agent_configuration import configured_agent_service

        assistant = EnterpriseAssistantService(
            dispatcher,
            provider=provider,
            capability_policy=configured_agent_service(dispatcher),
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
        active_service = FeishuBotService(
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
    else:
        active_service = service
    adapter = FeishuWebSocketAdapter(active_service, executor=executor)
    dispatcher = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(adapter.handle)
        .build()
    )
    return lark.ws.Client(
        config.app_id,
        config.app_secret,
        log_level=lark.LogLevel.WARNING,
        event_handler=dispatcher,
        domain=config.api_base_url,
    )


def run_feishu_websocket(config: FeishuBotConfig | None = None) -> None:
    """Start the blocking Feishu long connection."""
    active_config = config or FeishuBotConfig.from_env(
        require_verification_token=False
    )
    build_feishu_websocket_client(active_config).start()
