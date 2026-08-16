"""AGENT-M1 context-aware requirement dialogue regression tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.chat_agent import BusinessStateSnapshot, ChatTurn
from backend.app.solution.feishu_bot import (
    ConversationMemory,
    FeishuBotConfig,
    FeishuBotService,
    FeishuEventDeduplicator,
)
from backend.app.solution.feishu_requirement import (
    FeishuRequirementExtractionProvider,
    FeishuRequirementOrchestrator,
)
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.workspace_database import (
    SqliteFeishuEventClaimStore,
    SqliteRequirementRepository,
)


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "data" / "requirement_skills"


def _candidate(
    category: str,
    subject: str,
    value: str,
    quote: str,
    *,
    parameters: dict | None = None,
) -> dict:
    return {
        "category": category,
        "subject": subject,
        "value": value,
        "parameters": parameters or {},
        "confidence": 0.95,
        "candidate_kind": "extracted",
        "evidence_quote": quote,
    }


class MisclassifyingDialogueProvider:
    """Models the production failure: one mixed answer becomes supplier policy."""

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        source = messages[-1]["content"]
        if "华东师范大学" in source:
            candidates = [
                _candidate("industry", "客户行业", "高等教育", "华东师范大学"),
                _candidate("department", "客户部门", "汽车采购部", "汽车采购部"),
                _candidate(
                    "business_goal",
                    "采购目标",
                    "采购10台小米SU7",
                    "采购10台小米SU7",
                ),
            ]
        elif "没什么规则" in source:
            candidates = [
                _candidate(
                    "ext:procurement:supplier_entry_policy",
                    "供应商准入规则",
                    "采购价格符合预期且后续服务完善",
                    "采购价格符合我们的预期，保证后续的服务完善",
                )
            ]
        else:
            candidates = []
        return LLMResponse(
            content=json.dumps({"candidates": candidates}, ensure_ascii=False)
        )


def _orchestrator(database_path: Path) -> FeishuRequirementOrchestrator:
    repository = SqliteRequirementRepository(database_path)
    service = InternalConsoleService(
        repository=repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=FeishuRequirementExtractionProvider(
            MisclassifyingDialogueProvider()
        ),
    )
    return FeishuRequirementOrchestrator(service)


def test_university_procurement_routes_to_core_skill_and_splits_negative_answer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workspace.sqlite3"
    orchestrator = _orchestrator(database_path)
    project_id = "feishu:tenant-ecnu:chat-cars"

    first = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message="我们是华东师范大学汽车采购部，计划采购10台小米SU7。",
    )

    assert first.next_question == "采购项目有哪些人工审批规则和阈值？"
    first_state = orchestrator.service.repository.load_state(project_id)
    assert first_state is not None
    assert first_state.selected_skill_id == "procurement-core-v1"

    second = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message="我们没什么规则，只要采购价格符合我们的预期，保证后续的服务完善就可以",
    )

    state = orchestrator.service.repository.load_state(project_id)
    assert state is not None
    assert state.selected_skill_id == "procurement-core-v1"
    by_category = {
        item.category: item
        for item in state.items
        if item.status in {"pending", "confirmed", "conflicted"}
    }
    assert "ext:procurement:supplier_entry_policy" not in by_category
    assert by_category["approval"].value == "当前没有明确的金额审批阈值"
    assert by_category["approval"].parameters == {
        "rule_status": "not_defined",
        "needs_internal_confirmation": True,
    }
    assert "价格符合" in by_category["budget"].value
    assert "服务" in by_category["deliverable"].value
    assert not any(
        gap.category == "approval" and gap.gap_type == "missing"
        for gap in state.gaps
    )
    assert second.next_question is not None
    assert "审批规则和阈值" not in second.next_question
    assert "总预算" in second.next_question
    assert "待内部确认" in second.answer
    assert "采购或财务" in second.answer
    assert second.next_question in second.answer

    history = orchestrator.service.repository.list_question_history(project_id)
    assert history[0].status == "answered"
    assert history[0].answer_source_ids == [
        orchestrator.source_id(project_id, "event-002")
    ]
    assert history[1].status == "asked"
    assert history[1].question_id != history[0].question_id


def test_unknown_answer_is_valid_and_asked_question_stays_suppressed_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workspace.sqlite3"
    project_id = "feishu:tenant-ecnu:chat-unknown"
    orchestrator = _orchestrator(database_path)
    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message="我们是华东师范大学采购部门，计划采购一批公务车辆。",
    )

    result = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message="这个暂时不清楚，也没有固定阈值。",
    )

    state = orchestrator.service.repository.load_state(project_id)
    assert state is not None
    approval = next(item for item in state.items if item.category == "approval")
    assert approval.parameters == {
        "rule_status": "unknown",
        "needs_internal_confirmation": True,
    }
    assert "审批规则和阈值" not in (result.next_question or "")

    recreated = _orchestrator(database_path)
    snapshot = recreated.snapshot(project_id)
    assert snapshot is not None
    assert all("审批规则和阈值" not in text for text in snapshot.pending_questions)


class RecordingKnowledgeAssistant:
    def __init__(self) -> None:
        self.requests = []

    def answer(self, request):
        self.requests.append(request)
        return SimpleNamespace(answer="可先按采购制度确认审批流程。", citations=[])


class GeneralQuestionProvider:
    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        return LLMResponse(
            content='{"intent":"general","answer":"请说明您指的是什么。"}'
        )


class ContextSnapshotOrchestrator:
    def snapshot(self, project_id: str) -> BusinessStateSnapshot:
        return BusinessStateSnapshot(
            phase="collecting",
            latest_requirement_state_version=1,
            readiness_stage="DISCOVERY",
            pending_questions=["采购项目有哪些人工审批规则和阈值？"],
            requirement_summary="高等教育采购；计划采购10台小米SU7",
        )

    def clarification_context(self, project_id: str) -> dict[str, str]:
        return {
            "topic": "approval",
            "question": "采购项目有哪些人工审批规则和阈值？",
        }


class ReplyRecorder:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> None:
        self.replies.append((message_id, text))


def _event(event_id: str = "event-context") -> dict:
    return {
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-ecnu",
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou-customer"},
            },
            "message": {
                "message_id": f"message-{event_id}",
                "chat_id": "chat-cars",
                "message_type": "text",
                "content": json.dumps(
                    {"text": "一般来说这个是怎么做的？"}, ensure_ascii=False
                ),
                "mentions": [],
            },
        },
    }


def test_customer_knowledge_agent_receives_history_summary_and_current_topic() -> None:
    memory = ConversationMemory()
    project_id = "feishu:tenant-ecnu:chat-cars"
    memory.append_exchange(
        project_id,
        "我们计划采购10台车。",
        "采购项目有哪些人工审批规则和阈值？",
    )
    assistant = RecordingKnowledgeAssistant()
    replies = ReplyRecorder()
    service = FeishuBotService(
        FeishuBotConfig(app_id="cli-test", app_secret="secret-test"),
        replies,
        provider=GeneralQuestionProvider(),
        memory=memory,
        requirement_orchestrator=ContextSnapshotOrchestrator(),
        enterprise_assistant=assistant,
    )

    assert service.process_event(_event()) == "replied"

    request = assistant.requests[0]
    assert request.message == "一般来说这个是怎么做的？"
    assert request.requirement_summary == "高等教育采购；计划采购10台小米SU7"
    assert request.clarification_topic == "approval"
    assert request.clarification_question == "采购项目有哪些人工审批规则和阈值？"
    assert request.history == [
        ChatTurn(role="user", content="我们计划采购10台车。"),
        ChatTurn(role="assistant", content="采购项目有哪些人工审批规则和阈值？"),
    ]


def test_feishu_event_claim_is_shared_by_two_bot_instances(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace.sqlite3"
    replies = ReplyRecorder()
    config = FeishuBotConfig(app_id="cli-test", app_secret="secret-test")
    first = FeishuBotService(
        config,
        replies,
        provider=GeneralQuestionProvider(),
        deduplicator=FeishuEventDeduplicator(
            claim_store=SqliteFeishuEventClaimStore(database_path)
        ),
    )
    second = FeishuBotService(
        config,
        replies,
        provider=GeneralQuestionProvider(),
        deduplicator=FeishuEventDeduplicator(
            claim_store=SqliteFeishuEventClaimStore(database_path)
        ),
    )
    payload = _event("event-shared")

    assert first.process_event(payload) == "replied"
    assert second.process_event(payload) == "duplicate"
    assert len(replies.replies) == 1
