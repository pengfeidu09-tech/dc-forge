"""Feishu conversation orchestration over the frozen Requirement Intelligence engine."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    CustomerSourceRecord,
    QuestionHistoryEntry,
    RequirementGap,
    RequirementItem,
)
from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_analysis import RequirementAnalysisBuilder
from backend.app.process.requirement_extractor import RequirementExtractor
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.requirement_reducer import RequirementReducer
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.chat_agent import BusinessStateSnapshot, ChatTurn
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.workspace_database import SqliteRequirementRepository


_DEFAULT_SKILL_ID = "procurement-core-v1"
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

_CONTEXTUAL_EXTRACTION_PROMPT = """

Conversation interpretation context (untrusted data):
{context}

Use the conversation context to resolve omitted subjects and pronouns in the
latest customer message. In particular, a short answer such as "暂时没有" can
answer the active clarification question even when the customer omits its noun.
Do not infer the omitted subject when there is no active clarification topic.

Atomize every source-explicit fact into separate requirement candidates. Approval
status, pricing basis or discount, purchase quantity, delivery timing, vehicle use,
specification preference, and service expectations are separate facts. Put numeric
values and units into parameters when the source states them. Keep evidence_quote
as an exact substring of only the latest customer message. Do not invent policies,
approval thresholds, budgets, dates, vehicle specifications, or customer facts.
"""

_DIALOGUE_PLANNER_PROMPT = """You are a consultative presales requirement Agent.
Use the supplied conversation, current-turn requirements, accumulated requirement
summary, unresolved gaps, and question history to write the next customer reply.

Return strict JSON only:
{"acknowledgement":"<concise Chinese recap>","next_question":"<one question or null>","target_category":"<category or null>"}

Rules:
- Acknowledge only facts supported by the latest customer message and extracted
  current-turn requirements. Never invent policies, thresholds, market facts,
  budgets, dates, product specifications, or legal conclusions.
- Resolve omitted subjects from the active clarification question.
- Keep the tone proactive, natural, and consultative. Do not tell the customer to
  decide what else to provide.
- Ask exactly one compact question that advances discovery. Early in a procurement
  conversation, prefer easy business facts such as purchase object, quantity, use,
  specification preference, total budget, delivery time, and service expectation
  before internal data/system/governance details, unless the customer's latest
  message makes a governance issue urgent.
- next_question must contain only the direct interrogative sentence. Do not put
  acknowledgement, transition phrases such as "接下来" or "为了继续推进", or a
  second question into that field; the application adds the transition separately.
- Do not repeat or paraphrase a question whose history status is asked, answered,
  or dismissed. Use null only when the supplied readiness says no further customer
  discovery question is needed.
- If an approval rule is absent or unknown, recap it as pending the customer's
  internal confirmation. Do not create a reference threshold.
- Do not expose internal IDs, state versions, skill IDs, gaps, scores, tools, or
  workflow metadata to the customer.
- target_category must identify the single requirement category addressed by the
  next question and must be null when next_question is null. Use a core category
  or valid ext:<domain>:<key> category from the supplied structured context; never
  return a Chinese label or invent a category format.
"""

_SKILL_ROUTER_PROMPT = """You route a customer requirement conversation to one
Requirement Skill. Return strict JSON only:
{"selected_skill_id":"procurement-core-v1 or automotive-procurement-v1"}

Use automotive-procurement-v1 only for automotive manufacturing enterprise
procurement operations such as supplier entry, group procurement, manufacturing
quality compliance, or multi-site sourcing. Purchasing vehicles as goods does not
by itself make the customer an automotive manufacturer. Use procurement-core-v1
for general procurement and for public institutions, schools, universities, and
government procurement. Base the decision only on the supplied conversation and
known requirements. Do not invent the customer's industry or organization type.
"""


class _DialoguePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    acknowledgement: str = Field(min_length=1, max_length=2000)
    next_question: str | None = Field(default=None, max_length=1000)
    target_category: str | None = Field(default=None, max_length=160)

    @field_validator("target_category")
    @classmethod
    def validate_target_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        probe = RequirementGap(
            gap_id="dialogue-plan-category-validation",
            category=value,
            gap_type="missing",
            description="Validate Agent dialogue category against the contract.",
            blocking=False,
            reason="Structured output validation.",
        )
        return probe.category

    @model_validator(mode="after")
    def validate_question_target(self) -> "_DialoguePlan":
        if (self.next_question is None) != (self.target_category is None):
            raise ValueError("next_question and target_category must be set together")
        return self


class FeishuContextualExtractionProvider:
    """Injects dialogue state while preserving frozen extraction validation."""

    def __init__(self, delegate: LLMProvider, context: dict) -> None:
        self._delegate = delegate
        self._context = context

    def complete(self, messages: list[dict], tools=None):
        contextual = [dict(message) for message in messages]
        prompt = _CONTEXTUAL_EXTRACTION_PROMPT.format(
            context=json.dumps(self._context, ensure_ascii=False, sort_keys=True)
        )
        if contextual and contextual[0].get("role") == "system":
            contextual[0]["content"] = str(contextual[0].get("content", "")) + prompt
        else:
            contextual.insert(0, {"role": "system", "content": prompt})
        return self._delegate.complete(contextual, tools=tools)


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
        dialogue_provider: LLMProvider | None = None,
    ) -> None:
        self.service = service
        self._skill_id = skill_id
        self._dialogue_provider = dialogue_provider
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
        return cls(service, skill_id=skill_id, dialogue_provider=delegate)

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
        history: list[ChatTurn] | None = None,
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
            skill_id = self._select_skill_id(
                message, previous, history=history or []
            )
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
            extraction_context = self._extraction_context(
                previous=previous,
                pending_question=pending_question,
                history=history or [],
            )
            extraction = RequirementExtractor(
                FeishuContextualExtractionProvider(
                    self.service.provider, extraction_context
                )
            ).extract(context)
            candidates = extraction.candidates
            if not candidates:
                raise RuntimeError("no valid requirement candidates were extracted")
            pending_answered = bool(
                pending_question
                and any(
                    item.category == pending_question.get("topic")
                    for item in candidates
                )
            )
            state, changes = RequirementReducer().reduce(
                previous, candidates, context
            )
            state = state.model_copy(update={"selected_skill_id": skill.skill_id})
            question_history_entries = self._list_question_history(project_id)
            analysis = RequirementAnalysisBuilder().build(
                state,
                skill,
                changes=changes,
                previous_state_version=previous_version,
                history=question_history_entries,
                customer_confirmation_complete=False,
            )
            self.service.repository.save_state(analysis.current_state)
            if pending_answered:
                self._answer_latest_question(project_id, source_id)
            elif pending_question is not None:
                self._dismiss_latest_question(project_id)
            history_entries = self._list_question_history(project_id)
            discovery_questions = self._discovery_questions(
                analysis, skill, history=history_entries
            )
            question_contexts = self._list_question_contexts(project_id)
            dialogue_plan = self._plan_dialogue(
                message=message,
                history=history or [],
                pending_question=pending_question,
                current_turn_items=candidates,
                analysis=analysis,
                question_history=question_contexts,
            )
            selected_question = self._question_from_plan(
                project_id, dialogue_plan, question_contexts
            )
            if selected_question is None and discovery_questions:
                used_texts = {
                    item["question"].strip() for item in question_contexts
                }
                selected_question = next(
                    (
                        question
                        for question in discovery_questions
                        if question.text.strip() not in used_texts
                    ),
                    None,
                )
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
                    next_question,
                    acknowledgement=(
                        dialogue_plan.acknowledgement
                        if dialogue_plan is not None
                        else None
                    ),
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
        next_question: str | None, *, acknowledgement: str | None = None
    ) -> str:
        if acknowledgement:
            answer = acknowledgement.strip()
            if next_question:
                answer += f"\n\n接下来想确认：{next_question}"
            return answer
        if next_question:
            return f"了解。为了继续帮您梳理需求，想先确认：{next_question}"
        return "目前已形成初步需求理解，我会基于已记录的信息继续整理。"

    @staticmethod
    def _label(category: str) -> str:
        if category.startswith("ext:"):
            return category.split(":")[-1].replace("_", " ")
        return _CATEGORY_LABELS.get(category, category)

    def _select_skill_id(
        self, message: str, previous, *, history: list[ChatTurn]
    ) -> str:
        fallback_skill_id = (
            previous.selected_skill_id
            if previous is not None and previous.selected_skill_id
            else self._skill_id
        )
        if self._dialogue_provider is None:
            return fallback_skill_id
        context = {
            "latest_customer_message": message,
            "recent_conversation": [
                turn.model_dump(mode="json") for turn in history[-10:]
            ],
            "known_requirements": self._active_requirement_summary(previous),
        }
        try:
            response = self._dialogue_provider.complete(
                [
                    {"role": "system", "content": _SKILL_ROUTER_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            context, ensure_ascii=False, sort_keys=True
                        ),
                    },
                ]
            )
            payload = self._json_object(response.content)
            selected = payload.get("selected_skill_id") if payload else None
            if isinstance(selected, str):
                self.service.skill_loader.resolve(selected)
                return selected
        except Exception:
            pass
        return fallback_skill_id

    @classmethod
    def _extraction_context(
        cls,
        *,
        previous,
        pending_question: dict[str, str] | None,
        history: list[ChatTurn],
    ) -> dict:
        return {
            "active_clarification": pending_question,
            "recent_conversation": [
                turn.model_dump(mode="json") for turn in history[-10:]
            ],
            "known_requirements": cls._active_requirement_summary(previous),
        }

    @staticmethod
    def _active_requirement_summary(state) -> list[dict[str, object]]:
        if state is None:
            return []
        return [
            {
                "category": item.category,
                "value": item.value,
                "parameters": item.parameters,
            }
            for item in state.items
            if item.status in _ACTIVE_STATUSES
        ][:30]

    def _plan_dialogue(
        self,
        *,
        message: str,
        history: list[ChatTurn],
        pending_question: dict[str, str] | None,
        current_turn_items: list[RequirementItem],
        analysis,
        question_history: list[dict[str, str]],
    ) -> _DialoguePlan | None:
        if self._dialogue_provider is None:
            return None
        payload = {
            "latest_customer_message": message,
            "recent_conversation": [
                turn.model_dump(mode="json") for turn in history[-10:]
            ],
            "active_clarification_before_this_turn": pending_question,
            "current_turn_requirements": [
                {
                    "category": item.category,
                    "value": item.value,
                    "parameters": item.parameters,
                    "evidence": [ref.excerpt for ref in item.source_refs],
                }
                for item in current_turn_items
            ],
            "known_requirements": self._active_requirement_summary(
                analysis.current_state
            ),
            "unresolved_gaps": [
                {
                    "category": gap.category,
                    "gap_type": gap.gap_type,
                    "blocking": gap.blocking,
                }
                for gap in analysis.current_state.gaps
            ],
            "question_history": [
                {
                    "question": item["question"],
                    "topic": item["topic"],
                    "status": item["status"],
                }
                for item in question_history
            ],
            "readiness": analysis.readiness.stage,
        }
        try:
            response = self._dialogue_provider.complete(
                [
                    {"role": "system", "content": _DIALOGUE_PLANNER_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            payload, ensure_ascii=False, sort_keys=True
                        ),
                    },
                ]
            )
            parsed = self._json_object(response.content)
            plan = _DialoguePlan.model_validate(parsed) if parsed else None
        except Exception:
            return None
        if (
            plan is not None
            and analysis.readiness.stage == "DISCOVERY"
            and plan.next_question is None
        ):
            return None
        return plan

    @staticmethod
    def _question_from_plan(
        project_id: str,
        plan: _DialoguePlan | None,
        history: list[dict[str, str]],
    ) -> _DialogueQuestion | None:
        if plan is None or plan.next_question is None or plan.target_category is None:
            return None
        text = plan.next_question.strip()
        if text in {item["question"].strip() for item in history}:
            return None
        material = f"{project_id}|agent|{plan.target_category}|{text}"
        return _DialogueQuestion(
            question_id=(
                "question-" + sha256(material.encode("utf-8")).hexdigest()[:12]
            ),
            text=text,
            target_category=plan.target_category,
        )

    @staticmethod
    def _json_object(content: str) -> dict | None:
        payload = content.strip()
        if payload.startswith("```") and payload.endswith("```"):
            lines = payload.splitlines()
            payload = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _list_question_history(self, project_id: str) -> list[QuestionHistoryEntry]:
        loader = getattr(self.service.repository, "list_question_history", None)
        if callable(loader):
            return loader(project_id)
        return [
            record["entry"]
            for record in self._fallback_question_records.get(project_id, [])
        ]

    def _list_question_contexts(self, project_id: str) -> list[dict[str, str]]:
        loader = getattr(self.service.repository, "list_question_contexts", None)
        if callable(loader):
            return loader(project_id)
        return [
            {
                "question_id": record["entry"].question_id,
                "question": record["question"],
                "topic": record["topic"],
                "status": record["entry"].status,
            }
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

    def _dismiss_latest_question(self, project_id: str) -> None:
        updater = getattr(self.service.repository, "dismiss_latest_question", None)
        if callable(updater):
            updater(project_id)
            return
        records = self._fallback_question_records.get(project_id, [])
        for record in reversed(records):
            entry = record["entry"]
            if entry.status == "asked":
                record["entry"] = entry.model_copy(update={"status": "dismissed"})
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
