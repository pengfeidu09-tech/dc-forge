"""CHAT-M4 durable Feishu Requirement Intelligence orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.feishu_requirement import (
    FeishuRequirementExtractionProvider,
    FeishuRequirementOrchestrator,
)
from backend.app.solution.llm_provider import LLMResponse


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _candidate(
    category: str,
    subject: str,
    value: str,
    quote: str,
    **extra,
) -> dict:
    return {
        "category": category,
        "subject": subject,
        "value": value,
        "parameters": extra.pop("parameters", {}),
        "confidence": 0.95,
        "candidate_kind": "extracted",
        "evidence_quote": quote,
        **extra,
    }


class AutomotiveConversationProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        source = messages[-1]["content"]
        self.calls.append(source)
        if "大型汽车制造企业" in source:
            candidates = [
                _candidate("industry", "客户行业", "汽车制造", "汽车制造企业"),
                _candidate(
                    "business_goal",
                    "采购智能化目标",
                    "通过AI辅助智能招采与采购合规",
                    "希望通过AI辅助智能招采与采购合规",
                ),
                _candidate(
                    "current_process",
                    "供应商准入与合规审查",
                    "供应商准入和采购合规审查主要依赖人工",
                    "供应商准入和采购合规审查主要依赖人工",
                    process_detail={
                        "process_node_id": "manual-supplier-compliance-review",
                        "name": "供应商准入与合规审查",
                        "actor": "采购人员",
                        "node_type": "human",
                        "description": "供应商准入和采购合规审查主要依赖人工",
                        "next_node_ids": [],
                    },
                ),
                _candidate(
                    "pain_point",
                    "采购周期",
                    "人工流程导致采购周期较长",
                    "采购周期较长",
                    pain_point_detail={
                        "pain_point_id": "long-procurement-cycle",
                        "description": "人工流程导致采购周期较长",
                        "severity": "high",
                        "affected_process_node_ids": [
                            "manual-supplier-compliance-review"
                        ],
                    },
                ),
            ]
        elif "历史供应商资料" in source:
            candidates = [
                _candidate(
                    "approval",
                    "采购金额分级审批",
                    "采购金额超过50万元由部门负责人审批，超过300万元由采购委员会审批",
                    "采购金额超过50万元由部门负责人审批，超过300万元由采购委员会审批",
                    parameters={
                        "threshold_1": 500000,
                        "approver_1": "部门负责人",
                        "threshold_2": 3000000,
                        "approver_2": "采购委员会",
                    },
                ),
                _candidate(
                    "available_data",
                    "供应商资料",
                    "已有历史供应商资料和采购制度",
                    "历史供应商资料和采购制度",
                ),
                _candidate(
                    "existing_system",
                    "采购系统",
                    "使用SRM和ERP",
                    "SRM和ERP",
                ),
                _candidate(
                    "security",
                    "数据安全边界",
                    "采购数据不能离开企业数据域",
                    "采购数据不能离开企业数据域",
                ),
            ]
        else:
            candidates = []
        return LLMResponse(
            content=json.dumps({"candidates": candidates}, ensure_ascii=False)
        )


class CapturingProvider:
    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        self.messages.append(messages)
        return LLMResponse(content='{"candidates":[]}')


def _orchestrator(tmp_path: Path, provider=None) -> FeishuRequirementOrchestrator:
    service = InternalConsoleService(
        repository=FileRequirementRepository(tmp_path),
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=provider or AutomotiveConversationProvider(),
    )
    return FeishuRequirementOrchestrator(
        service, skill_id="automotive-procurement-v1"
    )


def test_extraction_adapter_constrains_deepseek_to_frozen_contract() -> None:
    delegate = CapturingProvider()
    provider = FeishuRequirementExtractionProvider(delegate)

    provider.complete(
        [
            {"role": "system", "content": "extract requirements"},
            {"role": "user", "content": "汽车采购需求"},
        ]
    )

    system = delegate.messages[0][0]["content"]
    assert "Allowed category values" in system
    assert "business_goal" in system
    assert "ext:procurement:supplier_entry_policy" in system
    assert "confidence must be a JSON number" in system
    assert "current_process requires process_detail" in system
    assert "pain_point requires pain_point_detail" in system


def test_extraction_adapter_hoists_only_known_typed_details() -> None:
    class NestedDetailProvider:
        def complete(self, messages: list[dict], tools=None) -> LLMResponse:
            return LLMResponse(
                content=json.dumps(
                    {
                        "candidates": [
                            {
                                "category": "current_process",
                                "subject": "供应商准入",
                                "value": "供应商准入依赖人工",
                                "parameters": {
                                    "source_system": "SRM",
                                    "process_detail": {
                                        "process_node_id": "supplier-entry",
                                        "name": "供应商准入",
                                        "actor": "采购人员",
                                        "node_type": "human",
                                        "description": "供应商准入依赖人工",
                                        "next_node_ids": [],
                                    },
                                },
                                "confidence": 1.0,
                                "candidate_kind": "extracted",
                                "evidence_quote": "供应商准入依赖人工",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            )

    response = FeishuRequirementExtractionProvider(
        NestedDetailProvider()
    ).complete([{"role": "user", "content": "供应商准入依赖人工"}])
    candidate = json.loads(response.content)["candidates"][0]

    assert candidate["process_detail"]["process_node_id"] == "supplier-entry"
    assert candidate["parameters"] == {"source_system": "SRM"}


def test_first_feishu_turn_creates_automotive_requirement_state_v1(
    tmp_path: Path,
) -> None:
    orchestrator = _orchestrator(tmp_path)
    project_id = "feishu:tenant-001:chat-001"

    result = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message=(
            "我们是一家大型汽车制造企业，供应商准入和采购合规审查主要依赖人工，"
            "采购周期较长，希望通过AI辅助智能招采与采购合规。"
        ),
        sender_open_id="ou-owner",
    )

    state = orchestrator.service.repository.load_state(project_id)
    assert state is not None
    assert state.state_version == 1
    assert state.selected_skill_id == "automotive-procurement-v1"
    assert {item.category for item in state.items} == {
        "industry",
        "business_goal",
        "current_process",
        "pain_point",
        "ext:automotive:quality_compliance",
        "ext:procurement:supplier_entry_policy",
    }
    assert state.source_ids == [orchestrator.source_id(project_id, "event-001")]
    assert all(ref.source_id == state.source_ids[0] for item in state.items for ref in item.source_refs)
    assert all(item.status == "pending" and item.confirmation_level == "none" for item in state.items)
    assert result.state_version == 1
    assert result.readiness_stage == "DISCOVERY"
    assert result.completeness_score > 0
    assert result.next_question is not None
    assert result.next_question in result.answer
    assert result.answer == (
        f"了解。为了继续帮您梳理需求，想先确认：{result.next_question}"
    )
    for internal_term in (
        "需求状态池",
        "版本",
        "automotive-procurement-v1",
        "DISCOVERY",
        "覆盖度",
        "客户确认基线",
        "gap",
        "候选",
    ):
        assert internal_term not in result.answer


def test_customer_answer_is_direct_when_no_more_question_is_needed() -> None:
    answer = FeishuRequirementOrchestrator._format_customer_answer(None)

    assert answer == "目前已形成初步需求理解，我会基于已记录的信息继续整理。"
    assert "感谢您的说明" not in answer
    assert "继续补充" not in answer


def test_second_turn_loads_v1_and_persists_v2(tmp_path: Path) -> None:
    provider = AutomotiveConversationProvider()
    orchestrator = _orchestrator(tmp_path, provider)
    project_id = "feishu:tenant-001:chat-001"
    orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message=(
            "我们是一家大型汽车制造企业，供应商准入和采购合规审查主要依赖人工，"
            "采购周期较长，希望通过AI辅助智能招采与采购合规。"
        ),
    )

    result = orchestrator.analyze_turn(
        project_id=project_id,
        message_id="event-002",
        message=(
            "采购金额超过50万元由部门负责人审批，超过300万元由采购委员会审批。"
            "目前有历史供应商资料和采购制度，使用SRM和ERP，"
            "采购数据不能离开企业数据域。"
        ),
    )

    assert result.state_version == 2
    assert orchestrator.service.repository.list_versions(project_id) == [1, 2]
    state = orchestrator.service.repository.load_state(project_id, 2)
    assert state is not None
    assert len(state.source_ids) == 2
    assert {"available_data", "existing_system", "security"} <= {
        item.category for item in state.items
    }
    assert "approval" in {item.category for item in state.items}
    assert any(
        gap.category == "approval" and gap.gap_type == "unconfirmed"
        for gap in state.gaps
    )
    assert result.next_question != "采购项目有哪些人工审批规则和阈值？"
    assert "审批规则和阈值" not in result.answer


def test_recreated_orchestrator_exposes_durable_business_snapshot(
    tmp_path: Path,
) -> None:
    project_id = "feishu:tenant-001:chat-001"
    first = _orchestrator(tmp_path)
    first.analyze_turn(
        project_id=project_id,
        message_id="event-001",
        message=(
            "我们是一家大型汽车制造企业，供应商准入和采购合规审查主要依赖人工，"
            "采购周期较长，希望通过AI辅助智能招采与采购合规。"
        ),
    )

    recreated = _orchestrator(tmp_path)
    snapshot = recreated.snapshot(project_id)

    assert snapshot is not None
    assert snapshot.phase == "collecting"
    assert snapshot.latest_requirement_state_version == 1
    assert snapshot.readiness_stage == "DISCOVERY"
    assert "汽车制造" in (snapshot.requirement_summary or "")
    assert snapshot.pending_questions


def test_empty_extraction_does_not_create_an_empty_state_version(
    tmp_path: Path,
) -> None:
    class EmptyProvider:
        def complete(self, messages: list[dict], tools=None) -> LLMResponse:
            return LLMResponse(content='{"candidates":[]}')

    orchestrator = _orchestrator(tmp_path, EmptyProvider())

    with pytest.raises(RuntimeError, match="no valid requirement candidates"):
        orchestrator.analyze_turn(
            project_id="feishu:tenant-001:chat-empty",
            message_id="event-empty",
            message="我们希望优化采购。",
        )

    assert orchestrator.service.repository.list_versions(
        "feishu:tenant-001:chat-empty"
    ) == []
