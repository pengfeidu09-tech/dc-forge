"""PORTAL-M3 unified Feishu, Requirement Intelligence, and customer portal tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.internal_console.service import InternalConsoleService
from backend.app.main import create_app
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.api import (
    CustomerConfirmationRequest,
    CustomerFeedbackRequest,
    CustomerPublicationRequest,
    reset_customer_engagement_rate_limiter,
    set_customer_engagement_service,
)
from backend.app.solution.customer_engagement import (
    CustomerEngagementService,
    FileCustomerEngagementRepository,
)
from backend.app.solution.feishu_bot import FeishuBotConfig, FeishuBotService
from backend.app.solution.llm_provider import LLMResponse
from tests.process.rm5_helpers import PROJECT_ID, SKILL_ROOT, state_and_baseline


class NoopProvider:
    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        return LLMResponse(
            content='{"intent":"general","answer":"请继续介绍您的需求。"}'
        )


class RecordingReplyClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


class RecordingFeedbackAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def analyze_turn(self, **kwargs):
        self.calls.append(kwargs)
        return type("FeedbackResult", (), {"state_version": 2})()


def _service(tmp_path: Path, *, analyzer=None) -> CustomerEngagementService:
    requirement_repository = FileRequirementRepository(tmp_path / "requirements")
    internal_console = InternalConsoleService(
        repository=requirement_repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=NoopProvider(),
    )
    return CustomerEngagementService(
        repository=FileCustomerEngagementRepository(tmp_path / "engagement"),
        requirement_repository=requirement_repository,
        internal_console=internal_console,
        feedback_analyzer=analyzer,
        public_base_url="https://dcforge.example.com",
    )


def _record_project(service: CustomerEngagementService, project_id: str = PROJECT_ID) -> None:
    service.record_customer_message(
        project_id=project_id,
        channel="feishu",
        message_id="message-001",
        event_id="event-001",
        content="我们希望缩短采购审查周期",
        tenant_key="tenant-001",
        chat_id="chat-001",
        sender_open_id="ou-customer",
    )
    service.record_agent_message(
        project_id=project_id,
        channel="feishu",
        message_id="message-001",
        event_id="event-001",
        content="请补充现有审批规则。",
        delivery_status="replied",
    )


def _pending_state():
    state, _ = state_and_baseline()
    pending_items = [
        item.model_copy(update={"status": "pending", "confirmation_level": "none"})
        for item in state.items
    ]
    return state.model_copy(update={"items": pending_items, "gaps": []})


def test_feishu_messages_are_durable_and_joined_with_requirement_state(tmp_path) -> None:
    service = _service(tmp_path)
    _record_project(service)
    state, _ = state_and_baseline()
    service.requirement_repository.save_state(state)

    restarted = _service(tmp_path)
    workbench = restarted.get_internal_project(PROJECT_ID)

    assert [message["role"] for message in workbench["conversation"]] == [
        "customer",
        "assistant",
    ]
    assert workbench["requirement_state"]["state_version"] == 1
    assert workbench["requirement_state"]["items"]
    assert restarted.chat_history(PROJECT_ID)[0].content == "我们希望缩短采购审查周期"
    assert restarted.list_internal_projects()[0]["message_count"] == 2


def test_existing_requirement_state_is_discovered_before_the_next_feishu_message(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    state, _ = state_and_baseline()
    service.requirement_repository.save_state(state)

    projects = service.list_internal_projects()

    assert projects[0]["project_id"] == PROJECT_ID
    assert projects[0]["message_count"] == 0
    assert service.get_internal_project(PROJECT_ID)["requirement_state"]["items"]
    assert "/customer/engagement/" in projects[0]["customer_url"]


def test_customer_view_hides_internal_fields_and_customer_confirmation_builds_baseline(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    _record_project(service)
    service.requirement_repository.save_state(_pending_state())
    access = service.ensure_customer_access(PROJECT_ID)
    token = access["token"]

    assert token not in urlsplit(access["url"]).path
    assert urlsplit(access["url"]).fragment == f"access_token={token}"

    before = service.get_customer_view(token)
    serialized = json.dumps(before, ensure_ascii=False)

    assert before["requirements"]
    assert "item_key" in before["requirements"][0]
    for internal_name in (
        "requirement_id",
        "source_refs",
        "confidence",
        "selected_skill_id",
        "readiness_stage",
    ):
        assert internal_name not in serialized

    confirmed = service.confirm_customer_requirements(
        token=token,
        confirmation_revision=before["confirmation_revision"],
        accepted_item_keys=[item["item_key"] for item in before["requirements"]],
        rejected_item_keys=[],
        note="页面确认当前需求理解",
    )

    assert confirmed["baseline_created"] is True
    assert service.requirement_repository.list_baseline_versions(PROJECT_ID) == [1]
    assert service.get_customer_view(token)["requirements_confirmed"] is True


def test_only_confirmed_baseline_can_be_published_and_customer_gets_safe_solution(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    _record_project(service)

    try:
        service.publish_project(PROJECT_ID, baseline_version=1, published_by="presales")
    except ValueError as error:
        assert "Baseline" in str(error)
    else:
        raise AssertionError("publishing without a baseline must fail")

    state, baseline = state_and_baseline()
    service.requirement_repository.save_state(state)
    service.requirement_repository.save_baseline(baseline)
    publication = service.publish_project(
        PROJECT_ID,
        baseline_version=1,
        published_by="presales-owner",
    )
    token = service.ensure_customer_access(PROJECT_ID)["token"]
    customer = service.get_customer_view(token)
    serialized = json.dumps(customer, ensure_ascii=False)

    assert publication["publication_version"] == 1
    assert customer["solution"]["baseline_version"] == 1
    assert customer["solution"]["plan"]["name"]
    assert "plans" not in customer["solution"]
    assert customer["progress"]["stages"][-1]["status"] == "completed"
    for internal_name in (
        "review_score",
        "asset_id",
        "reuse_summary",
        "evidence_refs",
        "solution_id",
    ):
        assert internal_name not in serialized


def test_customer_feedback_returns_to_requirement_analyzer(tmp_path) -> None:
    analyzer = RecordingFeedbackAnalyzer()
    service = _service(tmp_path, analyzer=analyzer)
    _record_project(service)
    token = service.ensure_customer_access(PROJECT_ID)["token"]

    result = service.submit_customer_feedback(
        token=token,
        message="审批阈值应调整为80万元",
    )

    assert result["accepted"] is True
    assert analyzer.calls[0]["project_id"] == PROJECT_ID
    assert analyzer.calls[0]["message"] == "审批阈值应调整为80万元"
    assert service.get_internal_project(PROJECT_ID)["conversation"][-1]["channel"] == "customer_portal"


def test_http_pages_and_api_share_the_same_engagement_service(tmp_path) -> None:
    service = _service(tmp_path)
    _record_project(service)
    access = service.ensure_customer_access(PROJECT_ID)
    token = access["token"]
    access_id = access["access_id"]
    set_customer_engagement_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        workbench_page = client.get("/customer-engagement/workbench")
        projects = client.get("/customer-engagement/projects")
        internal = client.get(f"/customer-engagement/projects/{PROJECT_ID}")
        customer_page = client.get(f"/customer/engagement/{access_id}")
        customer_data = client.get(
            f"/customer/engagement/{access_id}/data",
            headers={"X-DCForge-Customer-Token": token},
        )
    finally:
        set_customer_engagement_service(None)

    assert workbench_page.status_code == 200
    assert "统一售前工作台" in workbench_page.text
    assert projects.json()["projects"][0]["project_id"] == PROJECT_ID
    assert internal.json()["conversation"][0]["content"] == "我们希望缩短采购审查周期"
    assert customer_page.status_code == 200
    assert "需求与方案中心" in customer_page.text
    assert customer_data.json()["project"]["channel"] == "feishu"
    for response in (workbench_page, customer_page, customer_data):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_customer_request_models_reject_unbounded_or_duplicate_input() -> None:
    with pytest.raises(ValidationError):
        CustomerPublicationRequest(baseline_version=1, published_by="x" * 121)
    with pytest.raises(ValidationError):
        CustomerFeedbackRequest(message="x" * 4001)
    with pytest.raises(ValidationError):
        CustomerConfirmationRequest(
            confirmation_revision="revision",
            accepted_item_keys=["same", "same"],
            rejected_item_keys=[],
        )
    with pytest.raises(ValidationError):
        CustomerConfirmationRequest(
            confirmation_revision="revision",
            accepted_item_keys=[str(index) for index in range(201)],
            rejected_item_keys=[],
        )


def test_customer_feedback_endpoint_has_single_process_rate_limit(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path, analyzer=RecordingFeedbackAnalyzer())
    _record_project(service)
    access = service.ensure_customer_access(PROJECT_ID)
    monkeypatch.setenv("CUSTOMER_ENGAGEMENT_RATE_LIMIT_MAX", "1")
    monkeypatch.setenv("CUSTOMER_ENGAGEMENT_RATE_LIMIT_WINDOW_SECONDS", "60")
    reset_customer_engagement_rate_limiter()
    set_customer_engagement_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        path = f"/customer/engagement/{access['access_id']}/feedback"
        headers = {"X-DCForge-Customer-Token": access["token"]}
        first = client.post(path, headers=headers, json={"message": "补充审批规则"})
        second = client.post(path, headers=headers, json={"message": "补充数据范围"})
    finally:
        set_customer_engagement_service(None)
        reset_customer_engagement_rate_limiter()

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "提交过于频繁，请稍后再试。"


def test_customer_access_migrates_expiry_rejects_expired_token_and_rotation_renews(
    tmp_path,
) -> None:
    repository = FileCustomerEngagementRepository(
        tmp_path / "engagement",
        access_ttl_days=30,
    )
    repository.register_project(PROJECT_ID)
    access = repository.ensure_access(PROJECT_ID)
    access_path = repository._project_dir(PROJECT_ID) / "access.json"
    legacy = json.loads(access_path.read_text(encoding="utf-8"))
    legacy.pop("expires_at")
    access_path.write_text(json.dumps(legacy), encoding="utf-8")

    migrated = repository.ensure_access(PROJECT_ID)
    stored = json.loads(access_path.read_text(encoding="utf-8"))

    assert migrated.expires_at
    assert stored["expires_at"] == migrated.expires_at

    stored["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    access_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        repository.project_for_token(access.token)

    rotated = repository.rotate_access(PROJECT_ID)
    assert rotated.token != access.token
    assert datetime.fromisoformat(rotated.expires_at) > datetime.now(UTC)


def test_customer_page_uses_radio_buttons_for_conflicting_choices() -> None:
    component = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/customer/CustomerEngagementCenter.vue"
    ).read_text(encoding="utf-8")

    assert "<a-radio" in component
    assert "<a-checkbox" in component
    assert "item.choice_group" in component
    assert "部分需求存在冲突，请在同组中选择一项" in component


def _feishu_event(text: str, *, sender_open_id: str = "ou-customer") -> dict:
    return {
        "header": {
            "event_id": "event-link",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-001",
            "token": "verification-test",
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": sender_open_id},
            },
            "message": {
                "message_id": "message-link",
                "chat_id": "chat-001",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def test_feishu_bot_is_an_entry_for_customer_center_and_internal_workbench(tmp_path) -> None:
    engagement = _service(tmp_path)
    customer_reply = RecordingReplyClient()
    customer_bot = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=customer_reply,
        provider=NoopProvider(),
        engagement_service=engagement,
    )

    assert customer_bot.process_event(_feishu_event("/项目")) == "replied"
    assert "/customer/engagement/" in customer_reply.replies[0][1]

    internal_reply = RecordingReplyClient()
    internal_bot = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=internal_reply,
        provider=NoopProvider(),
        internal_open_ids={"ou-internal"},
        engagement_service=engagement,
    )
    assert internal_bot.process_event(
        _feishu_event("/客户工作台", sender_open_id="ou-internal")
    ) == "replied"
    assert internal_reply.replies == [
        (
            "message-link",
            "客户需求工作台：https://dcforge.example.com/presales/workbench",
        )
    ]


def test_same_feishu_chat_can_start_a_clean_logical_project_without_deleting_history(
    tmp_path,
) -> None:
    engagement = _service(tmp_path)
    reply = RecordingReplyClient()
    bot = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
            allowed_open_id="ou-owner",
        ),
        reply_client=reply,
        provider=NoopProvider(),
        engagement_service=engagement,
    )
    first = _feishu_event("旧项目客户背景", sender_open_id="ou-owner")
    first["header"]["event_id"] = "event-old"
    first["event"]["message"]["message_id"] = "message-old"
    reset = _feishu_event("/清空记忆 确认", sender_open_id="ou-owner")
    reset["header"]["event_id"] = "event-reset"
    reset["event"]["message"]["message_id"] = "message-reset"
    fresh = _feishu_event("新的汽车采购项目背景", sender_open_id="ou-owner")
    fresh["header"]["event_id"] = "event-fresh"
    fresh["event"]["message"]["message_id"] = "message-fresh"

    assert bot.process_event(first) == "replied"
    original_project_id = engagement.active_feishu_project_id(
        "tenant-001", "chat-001"
    )
    assert bot.process_event(reset) == "replied"
    fresh_project_id = engagement.active_feishu_project_id(
        "tenant-001", "chat-001"
    )
    assert fresh_project_id != original_project_id
    assert bot.process_event(fresh) == "replied"

    assert [item.content for item in engagement.repository.list_messages(original_project_id)] == [
        "旧项目客户背景",
        "请继续介绍您的需求。",
    ]
    assert [item.content for item in engagement.repository.list_messages(fresh_project_id)] == [
        "新的汽车采购项目背景",
        "请继续介绍您的需求。",
    ]
    assert engagement.requirement_repository.list_versions(fresh_project_id) == []
    assert engagement.requirement_repository.list_baseline_versions(fresh_project_id) == []
    assert reply.replies[1] == (
        "message-reset",
        "已在当前群开启全新项目。旧项目已归档保留，不会参与新的需求分析。"
        "请重新发送客户背景和本次项目范围。",
    )

    restarted = _service(tmp_path)
    assert restarted.active_feishu_project_id(
        "tenant-001", "chat-001"
    ) == fresh_project_id


def test_customer_cannot_reset_the_feishu_project(tmp_path) -> None:
    engagement = _service(tmp_path)
    reply = RecordingReplyClient()
    bot = FeishuBotService(
        config=FeishuBotConfig(
            app_id="cli_test",
            app_secret="secret-test-value",
            verification_token="verification-test",
        ),
        reply_client=reply,
        provider=NoopProvider(),
        internal_open_ids=set(),
        engagement_service=engagement,
    )
    reset = _feishu_event("/清空记忆 确认", sender_open_id="ou-customer")
    original_project_id = engagement.active_feishu_project_id(
        "tenant-001", "chat-001"
    )

    assert bot.process_event(reset) == "replied"

    assert engagement.active_feishu_project_id(
        "tenant-001", "chat-001"
    ) == original_project_id
    assert reply.replies == [
        ("message-link", "该指令仅供已授权的企业内部人员使用。")
    ]
