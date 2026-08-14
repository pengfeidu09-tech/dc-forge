"""Feishu conversation orchestration over the frozen Requirement Intelligence engine."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Literal

from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    CustomerSourceRecord,
)
from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_analysis import RequirementAnalysisBuilder
from backend.app.process.requirement_extractor import RequirementExtractor
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.requirement_reducer import RequirementReducer
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.chat_agent import BusinessStateSnapshot
from backend.app.solution.llm_provider import LLMProvider, OpenAICompatibleProvider
from backend.app.solution.llm_provider import LLMResponse


_DEFAULT_SKILL_ID = "automotive-procurement-v1"
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

    @classmethod
    def from_env(
        cls,
        *,
        provider: LLMProvider | None = None,
    ) -> "FeishuRequirementOrchestrator":
        repository_root = os.getenv("REQUIREMENT_REPOSITORY_ROOT", "").strip()
        if not repository_root:
            raise RuntimeError(
                "Requirement Intelligence is not configured; missing "
                "REQUIREMENT_REPOSITORY_ROOT"
            )
        project_root = Path(__file__).parents[3].resolve()
        data_root = Path(repository_root).expanduser().resolve()
        if data_root == project_root or data_root.is_relative_to(project_root):
            raise RuntimeError(
                "REQUIREMENT_REPOSITORY_ROOT must be outside the Git working tree"
            )
        skill_root = project_root / "data" / "requirement_skills"
        skill_id = (
            os.getenv("FEISHU_REQUIREMENT_SKILL_ID", _DEFAULT_SKILL_ID).strip()
            or _DEFAULT_SKILL_ID
        )
        delegate = provider or OpenAICompatibleProvider(timeout=90.0)
        service = InternalConsoleService(
            repository=FileRequirementRepository(data_root),
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
            source = CustomerSourceRecord(
                source_id=self.source_id(project_id, message_id),
                project_id=project_id,
                source_type="conversation",
                title="飞书客户需求对话",
                inline_content=message,
                author_role="customer",
                locator=f"feishu:event:{message_id}",
                metadata={
                    "channel": "feishu",
                    "scenario": "automotive-intelligent-sourcing-procurement-compliance",
                    **(
                        {"sender_open_id": sender_open_id}
                        if sender_open_id
                        else {}
                    ),
                },
            )
            previous = (
                self.service.repository.load_state(project_id, previous_version)
                if previous_version is not None
                else None
            )
            skill = self.service.skill_loader.resolve(self._skill_id)
            context = CustomerContextPackage(
                project_id=project_id,
                sources=[source],
                previous_state_version=previous_version,
                requirement_skill_ids=[self._skill_id],
            )
            extraction = RequirementExtractor(self.service.provider).extract(context)
            if not extraction.candidates:
                raise RuntimeError("no valid requirement candidates were extracted")
            state, changes = RequirementReducer().reduce(
                previous, extraction.candidates, context
            )
            state = state.model_copy(update={"selected_skill_id": skill.skill_id})
            analysis = RequirementAnalysisBuilder().build(
                state,
                skill,
                changes=changes,
                previous_state_version=previous_version,
                customer_confirmation_complete=False,
            )
            self.service.repository.save_state(analysis.current_state)
            discovery_questions = self._discovery_questions(analysis, skill)
            next_question = discovery_questions[0].text if discovery_questions else None
            return FeishuRequirementTurnResult(
                answer=self._format_customer_answer(next_question),
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
            discovery_questions = self._discovery_questions(analysis, skill)
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
                pending_questions=[
                    question.text for question in discovery_questions[:3]
                ],
                requirement_summary=summary or "尚未提取出明确需求项",
            )

    @staticmethod
    def _discovery_questions(analysis, skill):
        discovery_gaps = [
            gap for gap in analysis.current_state.gaps if gap.gap_type != "unconfirmed"
        ]
        return QuestionPlanner().plan(
            analysis.current_state,
            skill,
            discovery_gaps,
            analysis.current_state.conflicts,
        )

    @staticmethod
    def _format_customer_answer(next_question: str | None) -> str:
        if next_question:
            return (
                "感谢您的说明。为了进一步梳理适合贵司的方案，"
                f"{next_question}"
            )
        return "感谢您的说明。我们会结合您提供的信息，进一步梳理适合贵司的方案。"

    @staticmethod
    def _label(category: str) -> str:
        if category.startswith("ext:"):
            return category.split(":")[-1].replace("_", " ")
        return _CATEGORY_LABELS.get(category, category)
