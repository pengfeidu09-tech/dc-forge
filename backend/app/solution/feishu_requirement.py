"""Feishu conversation orchestration over the frozen Requirement Intelligence engine."""

from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Literal

from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    CustomerSourceRecord,
    QuestionHistoryEntry,
    RequirementItem,
    RequirementSourceRef,
)
from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_analysis import RequirementAnalysisBuilder
from backend.app.process.requirement_extractor import RequirementExtractor
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.requirement_reducer import RequirementReducer
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.chat_agent import BusinessStateSnapshot
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.workspace_database import SqliteRequirementRepository


_DEFAULT_SKILL_ID = "procurement-core-v1"
_AUTOMOTIVE_SKILL_ID = "automotive-procurement-v1"
_INSTITUTION_TERMS = (
    "大学",
    "学院",
    "高校",
    "学校",
    "事业单位",
    "政府",
    "公共机构",
)
_AUTOMOTIVE_MANUFACTURING_TERMS = (
    "汽车制造",
    "整车制造",
    "汽车集团",
    "主机厂",
    "零部件供应商",
    "多基地采购",
    "多工厂采购",
)
_UNKNOWN_TERMS = re.compile(r"(?:暂时|目前|现在)?(?:不清楚|不知道|不确定|未确定|待确定)")
_NO_RULE_TERMS = re.compile(
    r"(?:没什么|没有|暂无|暂时没有)(?:明确的|固定的|具体的)?(?:审批)?(?:规则|阈值)|"
    r"(?:审批)?(?:规则|阈值)(?:还)?(?:没有|未定|未明确)"
)
_PRICE_EXPECTATION = re.compile(
    r"(?:采购)?价格(?:需要|要|需)?符合(?:我们|我们的|预算)?(?:的)?预期|"
    r"价格在(?:预算|预期)(?:范围)?内"
)
_SERVICE_EXPECTATION = re.compile(
    r"(?:保证)?(?:后续的?)?(?:交付、?)?(?:质保、?)?(?:售后)?服务(?:要|需|需要)?(?:完善|有保障|到位)|"
    r"售后(?:服务)?(?:完善|有保障|到位)"
)
_ACTIVE_STATUSES = {"confirmed", "pending", "conflicted"}
_CATEGORY_LABELS = {
    "customer_context": "客户背景",
    "industry": "行业",
    "department": "业务部门",
    "business_goal": "业务目标",
    "current_process": "当前流程",
    "pain_point": "核心痛点",
    "available_data": "可用数据",
    "existing_system": "现有系统",
    "business_rule": "业务规则",
    "security": "安全边界",
    "approval": "审批规则",
    "risk": "风险关注",
    "target_metric": "目标指标",
    "integration": "系统集成",
    "scope": "项目范围",
    "deliverable": "交付物",
    "budget": "预算",
    "time": "实施周期",
}

_EXTRACTION_CONTRACT_PROMPT = """

DCForge frozen Requirement Intelligence extraction contract:
- Allowed category values are exactly the following core values or a valid
  ext:<domain>:<key> value:
  customer_context, industry, department, business_goal, pain_point, role,
  current_process, available_data, existing_system, business_rule, security,
  approval, budget, time, data, risk, target_metric, integration, scope,
  deliverable, ext:procurement:supplier_entry_policy,
  ext:automotive:procurement_category, ext:automotive:multi_site_process,
  ext:automotive:group_approval_level, ext:automotive:system_boundary,
  ext:automotive:quality_compliance, ext:security:data_classification.
- Never output Chinese category names or invent a new category.
- confidence must be a JSON number from 0.0 through 1.0, never a string such as
  "high" or "medium".
- candidate_kind must be exactly "extracted" or "inferred".
- evidence_quote must be an exact substring copied from the untrusted business
  data. Do not paraphrase it.
- current_process requires process_detail with process_node_id, name, actor,
  node_type (human/system/ai), description, and next_node_ids.
- pain_point requires pain_point_detail with pain_point_id, description, severity
  (low/medium/high), and affected_process_node_ids.
- Do not add process_detail or pain_point_detail to any other category.
- A negative or unknown answer is still requirement information. Map "没有规则",
  "没有固定阈值", "不清楚", and "暂未确定" about approvals to category
  approval with rule_status not_defined or unknown and
  needs_internal_confirmation true.
- Keep approval status, price/budget expectation, and after-sales/service
  requirements as separate candidates. Never put these three concepts into
  ext:procurement:supplier_entry_policy unless the source explicitly discusses
  supplier qualification, entry, tiering, or exit.
- Output strict JSON only: {"candidates":[...]} with no markdown or commentary.
"""


class FeishuRequirementExtractionProvider:
    """Adds the frozen extraction vocabulary without weakening strict validation."""

    def __init__(self, delegate: LLMProvider) -> None:
        self._delegate = delegate

    def complete(self, messages: list[dict], tools=None):
        constrained = [dict(message) for message in messages]
        if constrained and constrained[0].get("role") == "system":
            constrained[0]["content"] = (
                str(constrained[0].get("content", ""))
                + _EXTRACTION_CONTRACT_PROMPT
            )
        else:
            constrained.insert(
                0, {"role": "system", "content": _EXTRACTION_CONTRACT_PROMPT}
            )
        response = self._delegate.complete(constrained, tools=tools)
        try:
            payload = json.loads(response.content)
        except (TypeError, json.JSONDecodeError):
            return response
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            return response
        changed = False
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            parameters = candidate.get("parameters")
            if not isinstance(parameters, dict):
                continue
            parameters = dict(parameters)
            category = candidate.get("category")
            detail_key = {
                "current_process": "process_detail",
                "pain_point": "pain_point_detail",
            }.get(category)
            if detail_key and detail_key not in candidate and detail_key in parameters:
                candidate[detail_key] = parameters.pop(detail_key)
                candidate["parameters"] = parameters
                changed = True
        if not changed:
            return response
        return LLMResponse(
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            role=response.role,
            warnings=list(response.warnings),
        )


@dataclass(frozen=True)
class FeishuRequirementTurnResult:
    answer: str
    state_version: int
    readiness_stage: Literal["DISCOVERY", "PRELIMINARY_READY", "CONFIRMED_READY"]
    completeness_score: float
    next_question: str | None


@dataclass(frozen=True)
class _DialogueQuestion:
    question_id: str
    text: str
    target_category: str


class FeishuRequirementOrchestrator:
    """Persist one immutable RequirementState version per analyzed Feishu turn."""

    def __init__(
        self,
        service: InternalConsoleService,
        *,
        skill_id: str = _DEFAULT_SKILL_ID,
    ) -> None:
        self.service = service
        self._skill_id = skill_id
        self._lock = Lock()
        self._fallback_question_records: dict[str, list[dict]] = {}

    @classmethod
    def from_env(
        cls,
        *,
        provider: LLMProvider | None = None,
    ) -> "FeishuRequirementOrchestrator":
        project_root = Path(__file__).parents[3].resolve()
        from backend.app.solution.agent_configuration import configured_database_path

        skill_root = project_root / "data" / "requirement_skills"
        skill_id = (
            os.getenv("FEISHU_REQUIREMENT_SKILL_ID", _DEFAULT_SKILL_ID).strip()
            or _DEFAULT_SKILL_ID
        )
        delegate = provider or OpenAICompatibleProvider(timeout=90.0)
        service = InternalConsoleService(
            repository=SqliteRequirementRepository(configured_database_path()),
            skill_loader=RequirementSkillLoader(skill_root),
            provider=FeishuRequirementExtractionProvider(delegate),
        )
        service.skill_loader.resolve(skill_id)
        return cls(service, skill_id=skill_id)

    @staticmethod
    def source_id(project_id: str, message_id: str) -> str:
        material = f"{project_id}|{message_id}"
        return f"feishu-conversation-{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    def analyze_turn(
        self,
        *,
        project_id: str,
        message_id: str,
        message: str,
        sender_open_id: str | None = None,
    ) -> FeishuRequirementTurnResult:
        with self._lock:
            versions = self.service.repository.list_versions(project_id)
            previous_version = versions[-1] if versions else None
            previous = (
                self.service.repository.load_state(project_id, previous_version)
                if previous_version is not None
                else None
            )
            pending_question = self._latest_question_context(project_id)
            skill_id = self._select_skill_id(message, previous)
            skill = self.service.skill_loader.resolve(skill_id)
            source_id = self.source_id(project_id, message_id)
            source = CustomerSourceRecord(
                source_id=source_id,
                project_id=project_id,
                source_type="conversation",
                title="飞书客户需求对话",
                inline_content=message,
                author_role="customer",
                locator=f"feishu:event:{message_id}",
                metadata={
                    "channel": "feishu",
                    "scenario": skill_id,
                    **(
                        {"sender_open_id": sender_open_id}
                        if sender_open_id
                        else {}
                    ),
                },
            )
            context = CustomerContextPackage(
                project_id=project_id,
                sources=[source],
                previous_state_version=previous_version,
                requirement_skill_ids=[skill_id],
            )
            extraction = RequirementExtractor(self.service.provider).extract(context)
            candidates, approval_status = self._normalize_dialogue_candidates(
                extraction.candidates,
                message=message,
                source=source,
                clarification_topic=(
                    pending_question.get("topic") if pending_question else None
                ),
            )
            if not candidates:
                raise RuntimeError("no valid requirement candidates were extracted")
            pending_answered = bool(
                pending_question
                and (
                    approval_status is not None
                    or any(
                        item.category == pending_question.get("topic")
                        for item in candidates
                    )
                )
            )
            state, changes = RequirementReducer().reduce(
                previous, candidates, context
            )
            state = state.model_copy(update={"selected_skill_id": skill.skill_id})
            history = self._list_question_history(project_id)
            analysis = RequirementAnalysisBuilder().build(
                state,
                skill,
                changes=changes,
                previous_state_version=previous_version,
                history=history,
                customer_confirmation_complete=False,
            )
            self.service.repository.save_state(analysis.current_state)
            if pending_answered:
                self._answer_latest_question(project_id, source_id)
            discovery_questions = self._discovery_questions(
                analysis, skill, history=history
            )
            selected_question = None
            if pending_question is None or pending_answered:
                selected_question = (
                    self._continuation_question(analysis.current_state, history)
                    if approval_status is not None
                    else None
                )
            if (
                selected_question is None
                and (pending_question is None or pending_answered)
                and discovery_questions
            ):
                selected_question = discovery_questions[0]
            next_question = (
                selected_question.text if selected_question is not None else None
            )
            if selected_question is not None:
                self._record_question(
                    project_id,
                    selected_question,
                    analysis.current_state.state_version,
                )
            return FeishuRequirementTurnResult(
                answer=self._format_customer_answer(
                    next_question, approval_status=approval_status
                ),
                state_version=analysis.current_state.state_version,
                readiness_stage=analysis.readiness.stage,
                completeness_score=analysis.readiness.completeness_score,
                next_question=next_question,
            )

    def snapshot(self, project_id: str) -> BusinessStateSnapshot | None:
        with self._lock:
            state = self.service.repository.load_state(project_id)
            if state is None:
                return None
            skill_id = state.selected_skill_id or self._skill_id
            skill = self.service.skill_loader.resolve(skill_id)
            baseline_versions = self.service.repository.list_baseline_versions(project_id)
            latest_baseline = (
                self.service.repository.load_baseline(project_id, baseline_versions[-1])
                if baseline_versions
                else None
            )
            confirmation_complete = bool(
                latest_baseline
                and latest_baseline.source_state_version == state.state_version
            )
            analysis = RequirementAnalysisBuilder().build(
                state,
                skill,
                changes=[],
                previous_state_version=(state.state_version - 1 or None),
                customer_confirmation_complete=confirmation_complete,
            )
            history = self._list_question_history(project_id)
            discovery_questions = self._discovery_questions(
                analysis, skill, history=history
            )
            current_question = self._latest_question_context(project_id)
            active_items = sorted(
                (
                    item
                    for item in analysis.current_state.items
                    if item.status in _ACTIVE_STATUSES
                ),
                key=lambda item: (item.category, item.requirement_id),
            )
            summary = "；".join(
                f"{self._label(item.category)}：{item.value}"
                for item in active_items[:12]
            )
            phase = {
                "DISCOVERY": "collecting",
                "PRELIMINARY_READY": "awaiting_confirmation",
                "CONFIRMED_READY": "confirmed_ready",
            }[analysis.readiness.stage]
            pending_questions = []
            if current_question is not None:
                pending_questions.append(current_question["question"])
            pending_questions.extend(
                question.text
                for question in discovery_questions
                if question.text not in pending_questions
            )
            return BusinessStateSnapshot(
                phase=phase,
                latest_requirement_state_version=state.state_version,
                latest_baseline_version=(
                    latest_baseline.baseline_version if latest_baseline else None
                ),
                readiness_stage=analysis.readiness.stage,
                can_generate_formal_solution=(
                    analysis.readiness.can_generate_formal_solution
                ),
                pending_questions=pending_questions[:3],
                requirement_summary=summary or "尚未提取出明确需求项",
            )

    def clarification_context(self, project_id: str) -> dict[str, str]:
        with self._lock:
            return self._latest_question_context(project_id) or {}

    @staticmethod
    def _discovery_questions(analysis, skill, *, history=None):
        discovery_gaps = [
            gap for gap in analysis.current_state.gaps if gap.gap_type != "unconfirmed"
        ]
        return QuestionPlanner().plan(
            analysis.current_state,
            skill,
            discovery_gaps,
            analysis.current_state.conflicts,
            history=history,
        )

    @staticmethod
    def _format_customer_answer(
        next_question: str | None, *, approval_status: str | None = None
    ) -> str:
        if approval_status is not None:
            recorded = (
                "目前没有明确的金额审批阈值"
                if approval_status == "not_defined"
                else "目前审批规则和金额阈值暂不清楚"
            )
            answer = (
                f"明白，我先按以下口径记录：{recorded}。"
                "该项已标记为待内部确认；正式执行前，建议由贵单位采购或财务负责人"
                "确认内部制度、适用采购限额和固定资产管理要求。"
            )
            if next_question:
                answer += f"\n\n接下来想确认一下：{next_question}"
            return answer
        if next_question:
            return f"我先确认一个信息：{next_question}"
        return (
            "目前的信息足够形成初步理解。"
            "您可以继续补充审批规则、数据范围或部署要求。"
        )

    @staticmethod
    def _label(category: str) -> str:
        if category.startswith("ext:"):
            return category.split(":")[-1].replace("_", " ")
        return _CATEGORY_LABELS.get(category, category)

    def _select_skill_id(self, message: str, previous) -> str:
        state_text = " ".join(
            f"{item.subject} {item.value}"
            for item in (previous.items if previous is not None else [])
            if item.status in _ACTIVE_STATUSES
        )
        evidence = f"{state_text} {message}"
        if any(term in evidence for term in _INSTITUTION_TERMS):
            return _DEFAULT_SKILL_ID
        if any(term in evidence for term in _AUTOMOTIVE_MANUFACTURING_TERMS):
            return _AUTOMOTIVE_SKILL_ID
        if self._skill_id not in {_DEFAULT_SKILL_ID, _AUTOMOTIVE_SKILL_ID}:
            return self._skill_id
        return _DEFAULT_SKILL_ID

    @staticmethod
    def _approval_answer_status(message: str, topic: str | None) -> str | None:
        approval_context = topic == "approval" or any(
            term in message for term in ("审批", "规则", "阈值")
        )
        if not approval_context:
            return None
        if _UNKNOWN_TERMS.search(message):
            return "unknown"
        if _NO_RULE_TERMS.search(message):
            return "not_defined"
        return None

    def _normalize_dialogue_candidates(
        self,
        candidates: list[RequirementItem],
        *,
        message: str,
        source: CustomerSourceRecord,
        clarification_topic: str | None,
    ) -> tuple[list[RequirementItem], str | None]:
        approval_status = self._approval_answer_status(
            message, clarification_topic
        )
        if approval_status is None:
            return candidates, None

        replacements: list[RequirementItem] = []
        approval_match = (
            _UNKNOWN_TERMS.search(message)
            if approval_status == "unknown"
            else _NO_RULE_TERMS.search(message)
        )
        approval_quote = approval_match.group(0) if approval_match else message
        replacements.append(
            self._direct_item(
                category="approval",
                subject="人工审批规则",
                value=(
                    "当前没有明确的金额审批阈值"
                    if approval_status == "not_defined"
                    else "当前审批规则和金额阈值暂不清楚"
                ),
                parameters={
                    "rule_status": approval_status,
                    "needs_internal_confirmation": True,
                },
                quote=approval_quote,
                source=source,
            )
        )
        price_match = _PRICE_EXPECTATION.search(message)
        if price_match:
            replacements.append(
                self._direct_item(
                    category="budget",
                    subject="采购价格预期",
                    value="采购价格符合客户预算预期",
                    parameters={"expectation_status": "qualitative"},
                    quote=price_match.group(0),
                    source=source,
                )
            )
        service_match = _SERVICE_EXPECTATION.search(message)
        if service_match:
            replacements.append(
                self._direct_item(
                    category="deliverable",
                    subject="交付与售后服务",
                    value="后续交付、质保与售后服务需要完善",
                    parameters={"service_expectation": "complete_after_sales"},
                    quote=service_match.group(0),
                    source=source,
                )
            )

        replacement_categories = {item.category for item in replacements}
        normalized = [
            item
            for item in candidates
            if item.category not in replacement_categories
            and item.category != "ext:procurement:supplier_entry_policy"
        ]
        normalized.extend(replacements)
        return normalized, approval_status

    @staticmethod
    def _direct_item(
        *,
        category: str,
        subject: str,
        value: str,
        parameters: dict,
        quote: str,
        source: CustomerSourceRecord,
    ) -> RequirementItem:
        return RequirementItem(
            category=category,
            subject=subject,
            value=value,
            parameters=parameters,
            provenance="ai_extracted",
            status="pending",
            confirmation_level="none",
            confidence=1.0,
            source_refs=[
                RequirementSourceRef(
                    source_id=source.source_id,
                    locator=source.locator,
                    excerpt=quote,
                )
            ],
        )

    @staticmethod
    def _continuation_question(state, history) -> _DialogueQuestion | None:
        used_ids = {entry.question_id for entry in history}
        budget_id = (
            "question-"
            + sha256(f"{state.project_id}|dialogue|total-budget".encode()).hexdigest()[:12]
        )
        has_quantified_budget = any(
            item.category == "budget"
            and item.status in _ACTIVE_STATUSES
            and re.search(r"\d", item.value)
            for item in state.items
        )
        if not has_quantified_budget and budget_id not in used_ids:
            return _DialogueQuestion(
                question_id=budget_id,
                text="这次采购预计的总预算大概是多少？",
                target_category="budget",
            )
        time_id = (
            "question-"
            + sha256(f"{state.project_id}|dialogue|delivery-time".encode()).hexdigest()[:12]
        )
        if time_id not in used_ids:
            return _DialogueQuestion(
                question_id=time_id,
                text="这批采购期望在什么时间完成交付？",
                target_category="time",
            )
        return None

    def _list_question_history(self, project_id: str) -> list[QuestionHistoryEntry]:
        loader = getattr(self.service.repository, "list_question_history", None)
        if callable(loader):
            return loader(project_id)
        return [
            record["entry"]
            for record in self._fallback_question_records.get(project_id, [])
        ]

    def _latest_question_context(self, project_id: str) -> dict[str, str] | None:
        loader = getattr(self.service.repository, "latest_question_context", None)
        if callable(loader):
            return loader(project_id)
        for record in reversed(self._fallback_question_records.get(project_id, [])):
            if record["entry"].status == "asked":
                return {
                    "question_id": record["entry"].question_id,
                    "question": record["question"],
                    "topic": record["topic"],
                    "status": "asked",
                }
        return None

    def _answer_latest_question(self, project_id: str, source_id: str) -> None:
        updater = getattr(self.service.repository, "answer_latest_question", None)
        if callable(updater):
            updater(project_id, source_id)
            return
        records = self._fallback_question_records.get(project_id, [])
        for record in reversed(records):
            entry = record["entry"]
            if entry.status == "asked":
                record["entry"] = entry.model_copy(
                    update={"status": "answered", "answer_source_ids": [source_id]}
                )
                return

    def _record_question(
        self, project_id: str, question, asked_state_version: int
    ) -> None:
        recorder = getattr(self.service.repository, "record_question", None)
        if callable(recorder):
            recorder(
                project_id=project_id,
                question_id=question.question_id,
                question_text=question.text,
                target_category=question.target_category,
                asked_state_version=asked_state_version,
            )
            return
        records = self._fallback_question_records.setdefault(project_id, [])
        if any(
            record["entry"].question_id == question.question_id
            for record in records
        ):
            return
        records.append(
            {
                "entry": QuestionHistoryEntry(
                    question_id=question.question_id,
                    asked_state_version=asked_state_version,
                    status="asked",
                ),
                "question": question.text,
                "topic": question.target_category,
            }
        )
