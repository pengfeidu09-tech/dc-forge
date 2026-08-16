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
    """Simulates a context-aware extraction and dialogue Agent."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        self.calls.append(messages)
        system = messages[0]["content"]
        if "You route a customer requirement conversation" in system:
            return LLMResponse(
                content='{"selected_skill_id":"procurement-core-v1"}'
            )
        if "consultative presales requirement Agent" in system:
            context = json.loads(messages[-1]["content"])
            latest = context["latest_customer_message"]
            if "华东师范大学" in latest:
                payload = {
                    "acknowledgement": "了解，已记录贵校计划采购10台小米SU7。",
                    "next_question": "采购项目有哪些人工审批规则和阈值？",
                    "target_category": "approval",
                }
            else:
                payload = {
                    "acknowledgement": (
                        "明白，已记录目前没有明确审批阈值，价格需符合预算预期，"
                        "并要求后续服务完善。审批规则已标记为待内部确认，"
                        "后续由贵校采购或财务负责人确认。"
                    ),
                    "next_question": "这次采购预计的总预算大概是多少？",
                    "target_category": "budget",
                }
            return LLMResponse(content=json.dumps(payload, ensure_ascii=False))
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
                    "approval",
                    "人工审批规则",
                    "当前没有明确的金额审批阈值",
                    "没什么规则",
                    parameters={
                        "rule_status": "not_defined",
                        "needs_internal_confirmation": True,
                    },
                ),
                _candidate(
                    "budget",
                    "采购价格预期",
                    "采购价格符合客户预算预期",
                    "采购价格符合我们的预期",
                    parameters={"expectation_status": "qualitative"},
                ),
                _candidate(
                    "deliverable",
                    "售后服务",
                    "后续售后服务需要完善",
                    "后续的服务完善",
                    parameters={"service_expectation": "complete_after_sales"},
                ),
            ]
        elif "暂时不清楚" in source:
            candidates = [
                _candidate(
                    "approval",
                    "人工审批规则",
                    "当前审批规则和金额阈值暂不清楚",
                    "暂时不清楚",
                    parameters={
                        "rule_status": "unknown",
                        "needs_internal_confirmation": True,
                    },
                )
            ]
        else:
            candidates = []
        return LLMResponse(
            content=json.dumps({"candidates": candidates}, ensure_ascii=False)
        )


def _orchestrator(database_path: Path) -> FeishuRequirementOrchestrator:
    provider = MisclassifyingDialogueProvider()
    repository = SqliteRequirementRepository(database_path)
    service = InternalConsoleService(
        repository=repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=FeishuRequirementExtractionProvider(provider),
    )
    return FeishuRequirementOrchestrator(service, dialogue_provider=provider)


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


class ProactiveDialogueProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        self.calls.append(messages)
        system = messages[0]["content"]
        if "You route a customer requirement conversation" in system:
            context = json.loads(messages[-1]["content"])
            selected_skill_id = (
                "automotive-procurement-v1"
                if "汽车制造企业" in context["latest_customer_message"]
                else "procurement-core-v1"
            )
            return LLMResponse(
                content=json.dumps({"selected_skill_id": selected_skill_id})
            )
        if "consultative presales requirement Agent" in system:
            context = json.loads(messages[-1]["content"])
            latest = context["latest_customer_message"]
            if "暂时没有" in latest:
                payload = {
                    "acknowledgement": (
                        "明白，已记录目前没有明确审批规则，采购价格需低于市场价 10%，"
                        "采购数量不少于 100 台；审批规则待内部确认。"
                    ),
                    "next_question": "这批车辆主要用于什么场景，对车型或能源类型有什么偏好？",
                    "target_category": "scope",
                }
            elif "预算大概500万元" in latest:
                payload = {
                    "acknowledgement": "了解，已记录总预算约500万元。",
                    "next_question": "预计采购多少台，主要用于什么场景？",
                    "target_category": "scope",
                }
            else:
                payload = {
                    "acknowledgement": "了解，您计划采购一批汽车。",
                    "next_question": "预计采购多少台，主要用于什么场景？",
                    "target_category": "scope",
                }
            return LLMResponse(content=json.dumps(payload, ensure_ascii=False))
        source = messages[-1]["content"]
        if "采购一批汽车" in source:
            candidates = [
                _candidate(
                    "business_goal",
                    "车辆采购目标",
                    "采购一批汽车",
                    "采购一批汽车",
                )
            ]
        elif "暂时没有" in source:
            candidates = [
                _candidate(
                    "approval",
                    "人工审批规则",
                    "当前没有明确的金额审批阈值",
                    "暂时没有",
                    parameters={
                        "rule_status": "not_defined",
                        "needs_internal_confirmation": True,
                    },
                ),
                _candidate(
                    "budget",
                    "采购价格目标",
                    "采购价格低于市场价 10%",
                    "采购价低于市场价的 10%",
                    parameters={"benchmark_discount_percent": 10.0},
                ),
                _candidate(
                    "scope",
                    "采购数量",
                    "采购数量不少于 100 台",
                    "数量 100台以上",
                    parameters={
                        "quantity": 100,
                        "unit": "台",
                        "lower_bound_inclusive": True,
                    },
                ),
            ]
        elif "预算大概500万元" in source:
            candidates = [
                _candidate(
                    "budget",
                    "采购总预算",
                    "总预算约500万元",
                    "预算大概500万元",
                    parameters={"amount_cny": 5_000_000},
                )
            ]
        elif "汽车制造企业" in source:
            candidates = [
                _candidate(
                    "industry",
                    "客户行业",
                    "汽车制造企业",
                    "汽车制造企业",
                )
            ]
        else:
            candidates = []
        return LLMResponse(
            content=json.dumps({"candidates": candidates}, ensure_ascii=False)
        )


class InvalidDialogueCategoryProvider(ProactiveDialogueProvider):
    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        if "consultative presales requirement Agent" in messages[0]["content"]:
            return LLMResponse(
                content=json.dumps(
                    {
                        "acknowledgement": "了解，您计划采购一批汽车。",
                        "next_question": "还需要了解哪些信息？",
                        "target_category": "invalid-category",
                    },
                    ensure_ascii=False,
                )
            )
        return super().complete(messages, tools=tools)


def _proactive_orchestrator(
    database_path: Path,
    *,
    provider: ProactiveDialogueProvider | None = None,
) -> FeishuRequirementOrchestrator:
    provider = provider or ProactiveDialogueProvider()
    repository = SqliteRequirementRepository(database_path)
    service = InternalConsoleService(
        repository=repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=FeishuRequirementExtractionProvider(provider),
    )
    return FeishuRequirementOrchestrator(service, dialogue_provider=provider)


def test_vehicle_procurement_starts_with_business_facts_not_approval(
    tmp_path: Path,
) -> None:
    orchestrator = _proactive_orchestrator(tmp_path / "workspace.sqlite3")

    result = orchestrator.analyze_turn(
        project_id="feishu:tenant:proactive-first",
        message_id="event-001",
        message="我想要采购一批汽车",
    )

    assert result.next_question is not None
    assert "多少台" in result.next_question
    assert "主要用于" in result.next_question
    assert "审批" not in result.next_question
    assert "继续补充" not in result.answer


def test_skill_router_reconsiders_later_customer_context(tmp_path: Path) -> None:
    orchestrator = _proactive_orchestrator(tmp_path / "workspace.sqlite3")
    project_id = "feishu:tenant:dynamic-skill"

    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message="我想要采购一批汽车",
    )
    first_state = orchestrator.service.repository.load_state(project_id)
    assert first_state is not None
    assert first_state.selected_skill_id == "procurement-core-v1"

    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message="补充一下，我们是汽车制造企业。",
    )
    second_state = orchestrator.service.repository.load_state(project_id)
    assert second_state is not None
    assert second_state.selected_skill_id == "automotive-procurement-v1"


def test_contextual_bare_negative_is_atomized_and_followed_by_a_new_question(
    tmp_path: Path,
) -> None:
    orchestrator = _proactive_orchestrator(tmp_path / "workspace.sqlite3")
    project_id = "feishu:tenant:proactive-mixed"
    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message="我想要采购一批汽车",
    )
    repository = orchestrator.service.repository
    assert repository.dismiss_latest_question(project_id)
    repository.record_question(
        project_id=project_id,
        question_id="question-approval-existing-chat",
        question_text="采购项目有哪些人工审批规则和阈值？",
        target_category="approval",
        asked_state_version=1,
    )

    result = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message="暂时没有，需要采购价低于市场价的 10%，数量 100台以上",
    )

    state = repository.load_state(project_id)
    assert state is not None
    items = {
        item.category: item
        for item in state.items
        if item.status in {"pending", "confirmed", "conflicted"}
    }
    assert "ext:procurement:supplier_entry_policy" not in items
    assert items["approval"].parameters["rule_status"] == "not_defined"
    assert items["budget"].value == "采购价格低于市场价 10%"
    assert items["budget"].parameters["benchmark_discount_percent"] == 10.0
    assert items["scope"].value == "采购数量不少于 100 台"
    assert items["scope"].parameters == {
        "quantity": 100,
        "unit": "台",
        "lower_bound_inclusive": True,
    }
    assert result.next_question is not None
    assert "审批规则" not in result.next_question
    assert "主要用于" in result.next_question
    assert "低于市场价 10%" in result.answer
    assert "100 台" in result.answer
    assert result.next_question in result.answer
    assert "继续补充" not in result.answer

    history = repository.list_question_history(project_id)
    assert [entry.status for entry in history] == [
        "dismissed",
        "answered",
        "asked",
    ]
    assert history[1].answer_source_ids == [
        orchestrator.source_id(project_id, "event-002")
    ]
    provider_calls = orchestrator._dialogue_provider.calls
    extraction_prompts = [
        json.dumps(messages, ensure_ascii=False)
        for messages in provider_calls
        if "Conversation interpretation context" in messages[0]["content"]
    ]
    assert any("采购项目有哪些人工审批规则和阈值" in prompt for prompt in extraction_prompts)
    assert any(
        '"topic": "approval"' in messages[0]["content"]
        for messages in provider_calls
        if "Conversation interpretation context" in messages[0]["content"]
    )


def test_valid_jump_answer_dismisses_instead_of_falsely_answering_current_question(
    tmp_path: Path,
) -> None:
    orchestrator = _proactive_orchestrator(tmp_path / "workspace.sqlite3")
    project_id = "feishu:tenant:proactive-jump"
    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message="我想要采购一批汽车",
    )

    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message="预算大概500万元",
    )

    history = orchestrator.service.repository.list_question_history(project_id)
    assert history[0].status == "dismissed"
    assert history[0].answer_source_ids == []
    assert history[-1].status == "asked"


def test_invalid_agent_question_category_falls_back_without_persisting_it(
    tmp_path: Path,
) -> None:
    repository_path = tmp_path / "workspace.sqlite3"
    orchestrator = _proactive_orchestrator(
        repository_path,
        provider=InvalidDialogueCategoryProvider(),
    )

    result = orchestrator.analyze_turn(
        project_id="feishu:tenant:invalid-agent-category",
        message_id="event-001",
        message="我想要采购一批汽车",
    )

    assert result.next_question != "还需要了解哪些信息？"
    contexts = orchestrator.service.repository.list_question_contexts(
        "feishu:tenant:invalid-agent-category"
    )
    assert contexts
    assert all(item["topic"] != "invalid-category" for item in contexts)
