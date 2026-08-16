"""PRESALES-M1 unified orchestration across existing DCForge capabilities."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.contracts.process import PainPoint, ProcessNode, ProcessSpec
from backend.app.process.process_spec_adapter import ProcessSpecAdapter
from backend.app.solution.customer_engagement import CustomerEngagementService
from backend.app.solution.service import compile_solution, compile_solution_v2


_CUSTOMER_SOURCE_TYPES = {
    "customer_document",
    "meeting_minutes",
    "customer_email",
}
_SKILL_CONNECTIONS = {
    "requirement_analysis": "requirement_analysis",
    "case_matching": "knowledge_retrieval",
    "solution_recommendation": "solution_generation",
    "document_generation": "customer_output",
}
_STAGE_LABELS = {
    "opportunity": "客户机会与项目建立",
    "requirement_analysis": "需求分析与客户确认",
    "intelligence_research": "外部动态情报",
    "knowledge_retrieval": "企业知识与案例检索",
    "solution_generation": "三套方案与成果草稿",
    "internal_review": "内部评审",
    "customer_output": "客户发布",
    "feedback_iteration": "客户反馈与迭代",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value: str, length: int = 32) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:length]


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PresalesSource(_PrivateModel):
    source_id: str
    source_type: Literal[
        "customer_document",
        "meeting_minutes",
        "customer_email",
        "internal_material",
        "external_intelligence",
    ]
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=12000)
    source_url: str | None = Field(default=None, max_length=2000)
    occurred_at: str | None = Field(default=None, max_length=80)
    added_by: str = Field(min_length=1, max_length=120)
    added_at: str

    @model_validator(mode="after")
    def validate_external_source(self) -> "PresalesSource":
        if self.source_url:
            parsed = urlsplit(self.source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("source_url must be an HTTP or HTTPS URL")
        if self.source_type == "external_intelligence" and not self.source_url:
            raise ValueError("external intelligence requires source_url")
        return self


class ResearchSnapshot(_PrivateModel):
    research_version: int = Field(ge=1)
    query: str = Field(min_length=1, max_length=2000)
    reference_project_id: str
    knowledge_results: list[dict[str, Any]] = Field(default_factory=list)
    project_sources: list[dict[str, Any]] = Field(default_factory=list)
    external_sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, str]] = Field(default_factory=list)
    generated_by: str
    generated_at: str


class DeliverableContent(_PrivateModel):
    title: str = Field(min_length=1, max_length=240)
    customer_current_state: list[str] = Field(default_factory=list, max_length=100)
    problem_analysis: list[str] = Field(default_factory=list, max_length=100)
    requirement_understanding: list[str] = Field(default_factory=list, max_length=200)
    recommended_solution: str = Field(min_length=1, max_length=4000)
    value_hypotheses: list[str] = Field(default_factory=list, max_length=100)
    implementation_roadmap: list[str] = Field(default_factory=list, max_length=100)
    risks_and_boundaries: list[str] = Field(default_factory=list, max_length=100)
    case_references: list[str] = Field(default_factory=list, max_length=100)
    citations: list[dict[str, str]] = Field(default_factory=list, max_length=200)


class SolutionDraft(_PrivateModel):
    draft_version: int = Field(ge=1)
    baseline_version: int | None = Field(default=None, ge=1)
    requirement_state_version: int | None = Field(default=None, ge=1)
    requirement_basis: Literal[
        "confirmed_baseline", "latest_requirement_state"
    ] = "confirmed_baseline"
    research_version: int = Field(ge=1)
    plans: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    deliverable_revision: int = Field(ge=1)
    deliverable: DeliverableContent
    generated_by: str
    generated_at: str
    updated_by: str
    updated_at: str


class DraftReview(_PrivateModel):
    review_version: int = Field(ge=1)
    draft_version: int = Field(ge=1)
    deliverable_revision: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reviewed_by: str
    note: str | None = Field(default=None, max_length=2000)
    reviewed_at: str


class PublishedDeliverable(_PrivateModel):
    publication_version: int = Field(ge=1)
    draft_version: int = Field(ge=1)
    deliverable_revision: int = Field(ge=1)
    content: DeliverableContent
    published_by: str
    published_at: str


class PresalesProjectRecord(_PrivateModel):
    project_id: str
    title: str
    owner: str
    industry: str | None = None
    reference_project_id: str = "PRJ-TENDER-001"
    created_at: str
    updated_at: str
    sources: list[PresalesSource] = Field(default_factory=list)
    research_snapshots: list[ResearchSnapshot] = Field(default_factory=list)
    drafts: list[SolutionDraft] = Field(default_factory=list)
    reviews: list[DraftReview] = Field(default_factory=list)
    published_deliverables: list[PublishedDeliverable] = Field(default_factory=list)


class EnterpriseKnowledgeBoundary(Protocol):
    def search_knowledge(
        self,
        project_id: str,
        *,
        query: str,
        user_id: str,
        as_of: str,
        limit: int = 8,
    ) -> dict[str, Any]: ...


class PresalesSkillCatalog:
    """Read the packaged Skill definitions and expose honest runtime linkage."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise ValueError(f"presales skill catalog is missing: {self.root}")

    def list_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.yaml"), key=lambda item: item.name):
            payload = json.loads(path.read_text(encoding="utf-8"))
            name = str(payload["name"])
            connected_step = _SKILL_CONNECTIONS.get(name)
            skills.append(
                {
                    "name": name,
                    "version": str(payload.get("version", "")),
                    "description": str(payload.get("description", "")),
                    "connected_step": connected_step,
                    "execution_status": (
                        "connected" if connected_step else "definition_only"
                    ),
                    "outputs": [
                        str(item.get("name", ""))
                        for item in payload.get("outputs", [])
                        if isinstance(item, dict) and item.get("name")
                    ],
                }
            )
        return skills


class FilePresalesOrchestrationRepository:
    """Single-process file repository for presales orchestration facts."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._lock = RLock()

    def _path(self, project_id: str) -> Path:
        if not project_id.strip():
            raise ValueError("project_id must not be blank")
        return self.root / _digest(project_id, 64) / "workspace.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _read(path: Path) -> PresalesProjectRecord:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid presales workspace data: {path}") from error
        return PresalesProjectRecord.model_validate(payload)

    def ensure_project(
        self,
        project_id: str,
        *,
        title: str | None = None,
        owner: str | None = None,
        industry: str | None = None,
        reference_project_id: str | None = None,
    ) -> PresalesProjectRecord:
        with self._lock:
            path = self._path(project_id)
            timestamp = _now()
            if path.exists():
                current = self._read(path)
                updates = {"updated_at": timestamp}
                if title:
                    updates["title"] = title
                if owner:
                    updates["owner"] = owner
                if industry:
                    updates["industry"] = industry
                if reference_project_id:
                    updates["reference_project_id"] = reference_project_id
                project = current.model_copy(update=updates)
            else:
                project = PresalesProjectRecord(
                    project_id=project_id,
                    title=title or project_id,
                    owner=owner or "unassigned",
                    industry=industry,
                    reference_project_id=reference_project_id or "PRJ-TENDER-001",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            self._atomic_write(path, project.model_dump(mode="json"))
            return project

    def get_project(self, project_id: str) -> PresalesProjectRecord:
        path = self._path(project_id)
        if not path.exists():
            raise FileNotFoundError("presales project does not exist")
        return self._read(path)

    def list_projects(self) -> list[PresalesProjectRecord]:
        if not self.root.exists():
            return []
        projects = [self._read(path) for path in self.root.glob("*/workspace.json")]
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def _save(self, project: PresalesProjectRecord) -> PresalesProjectRecord:
        updated = project.model_copy(update={"updated_at": _now()})
        self._atomic_write(self._path(project.project_id), updated.model_dump(mode="json"))
        return updated

    def add_source(self, project_id: str, source: PresalesSource) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            if any(item.source_id == source.source_id for item in project.sources):
                raise ValueError("presales source already exists")
            return self._save(
                project.model_copy(update={"sources": [*project.sources, source]})
            )

    def add_research(
        self, project_id: str, snapshot: ResearchSnapshot
    ) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            return self._save(
                project.model_copy(
                    update={
                        "research_snapshots": [
                            *project.research_snapshots,
                            snapshot,
                        ]
                    }
                )
            )

    def add_draft(self, project_id: str, draft: SolutionDraft) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            return self._save(
                project.model_copy(update={"drafts": [*project.drafts, draft]})
            )

    def replace_draft(
        self, project_id: str, draft: SolutionDraft
    ) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            found = False
            drafts: list[SolutionDraft] = []
            for item in project.drafts:
                if item.draft_version == draft.draft_version:
                    drafts.append(draft)
                    found = True
                else:
                    drafts.append(item)
            if not found:
                raise FileNotFoundError("solution draft does not exist")
            return self._save(project.model_copy(update={"drafts": drafts}))

    def add_review(self, project_id: str, review: DraftReview) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            return self._save(
                project.model_copy(update={"reviews": [*project.reviews, review]})
            )

    def add_publication(
        self, project_id: str, publication: PublishedDeliverable
    ) -> PresalesProjectRecord:
        with self._lock:
            project = self.get_project(project_id)
            return self._save(
                project.model_copy(
                    update={
                        "published_deliverables": [
                            *project.published_deliverables,
                            publication,
                        ]
                    }
                )
            )


class PresalesOrchestrationService:
    """Connect customer facts, research, solution drafts, reviews, and output."""

    def __init__(
        self,
        *,
        repository: FilePresalesOrchestrationRepository,
        engagement_service: CustomerEngagementService,
        knowledge_service: EnterpriseKnowledgeBoundary,
        skill_catalog: PresalesSkillCatalog,
    ) -> None:
        self.repository = repository
        self.engagement_service = engagement_service
        self.knowledge_service = knowledge_service
        self.skill_catalog = skill_catalog

    @classmethod
    def from_env(
        cls,
        *,
        engagement_service: CustomerEngagementService,
        knowledge_service: EnterpriseKnowledgeBoundary,
    ) -> "PresalesOrchestrationService":
        project_root = Path(__file__).resolve().parents[3]
        raw_root = os.getenv("PRESALES_ORCHESTRATION_ROOT", "").strip()
        if raw_root:
            root = Path(raw_root).expanduser().resolve()
        else:
            engagement_root = engagement_service.repository.root.resolve()
            root = engagement_root.parent / f"{engagement_root.name}-presales"
        if root == project_root or root.is_relative_to(project_root):
            raise RuntimeError("PRESALES_ORCHESTRATION_ROOT must be outside the Git working tree")
        return cls(
            repository=FilePresalesOrchestrationRepository(root),
            engagement_service=engagement_service,
            knowledge_service=knowledge_service,
            skill_catalog=PresalesSkillCatalog(
                project_root
                / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
                / "07_Skill技能库"
            ),
        )

    def _ensure_project(self, project_id: str) -> PresalesProjectRecord:
        try:
            return self.repository.get_project(project_id)
        except FileNotFoundError:
            self.engagement_service._ensure_registered_project(project_id)
            return self.repository.ensure_project(project_id)

    def create_project(
        self,
        *,
        title: str,
        owner: str,
        industry: str | None = None,
        reference_project_id: str = "PRJ-TENDER-001",
    ) -> dict[str, Any]:
        project_id = f"presales:{secrets.token_hex(12)}"
        self.engagement_service.repository.register_project(
            project_id, channel="customer_portal"
        )
        self.engagement_service.repository.ensure_access(project_id)
        project = self.repository.ensure_project(
            project_id,
            title=title,
            owner=owner,
            industry=industry,
            reference_project_id=reference_project_id,
        )
        return project.model_dump(mode="json")

    def _sync_engagement_projects(self) -> None:
        known = {item.project_id for item in self.repository.list_projects()}
        for item in self.engagement_service.list_internal_projects():
            if item["project_id"] not in known:
                self.repository.ensure_project(item["project_id"])

    def add_source(
        self,
        project_id: str,
        *,
        source_type: str,
        title: str,
        content: str,
        added_by: str,
        source_url: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_project(project_id)
        source_id = f"PSRC-{secrets.token_hex(10).upper()}"
        source = PresalesSource(
            source_id=source_id,
            source_type=source_type,
            title=title,
            content=content,
            source_url=source_url,
            occurred_at=occurred_at,
            added_by=added_by,
            added_at=_now(),
        )
        self.repository.add_source(project_id, source)
        analysis_state_version = None
        if source.source_type in _CUSTOMER_SOURCE_TYPES:
            analyzer = self.engagement_service.feedback_analyzer
            if analyzer is None:
                raise RuntimeError("Requirement analysis is unavailable")
            self.engagement_service.record_customer_message(
                project_id=project_id,
                channel="customer_portal",
                message_id=source.source_id,
                event_id=source.source_id,
                content=source.content,
            )
            result = analyzer.analyze_turn(
                project_id=project_id,
                message_id=source.source_id,
                message=source.content,
                sender_open_id=None,
            )
            analysis_state_version = getattr(result, "state_version", None)
        return {
            **source.model_dump(mode="json"),
            "analysis_state_version": analysis_state_version,
        }

    @staticmethod
    def _normalize_knowledge_result(item: dict[str, Any]) -> dict[str, str]:
        source_ids = item.get("source_ids")
        source_id = item.get("source_id") or item.get("chunk_id")
        if not source_id and isinstance(source_ids, list) and source_ids:
            source_id = source_ids[0]
        preview = (
            item.get("snippet")
            or item.get("content_preview")
            or item.get("content")
            or ""
        )
        return {
            "source_id": str(source_id or "KNOWLEDGE-UNRESOLVED"),
            "title": str(item.get("title") or source_id or "企业知识资料"),
            "summary": str(preview)[:600],
            "locator": str(item.get("source_path") or item.get("locator") or ""),
        }

    def run_research(
        self,
        project_id: str,
        *,
        query: str,
        user_id: str,
        as_of: str,
        generated_by: str,
    ) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        response = self.knowledge_service.search_knowledge(
            project.reference_project_id,
            query=query,
            user_id=user_id,
            as_of=as_of,
            limit=8,
        )
        knowledge_results = [
            self._normalize_knowledge_result(item)
            for item in response.get("results", [])
            if isinstance(item, dict)
        ]
        project_sources = [
            {
                "source_id": item.source_id,
                "title": item.title,
                "source_type": item.source_type,
                "summary": item.content[:600],
                "source_url": item.source_url or "",
                "occurred_at": item.occurred_at or "",
            }
            for item in project.sources
            if item.source_type in {"internal_material", "external_intelligence"}
        ]
        external_sources = [
            item for item in project_sources if item["source_type"] == "external_intelligence"
        ]
        citations = [
            {
                "source_id": item["source_id"],
                "title": item["title"],
                "locator": item["locator"],
            }
            for item in knowledge_results
        ] + [
            {
                "source_id": item["source_id"],
                "title": item["title"],
                "locator": item["source_url"],
            }
            for item in project_sources
        ]
        snapshot = ResearchSnapshot(
            research_version=len(project.research_snapshots) + 1,
            query=query,
            reference_project_id=project.reference_project_id,
            knowledge_results=knowledge_results,
            project_sources=project_sources,
            external_sources=external_sources,
            citations=citations,
            generated_by=generated_by,
            generated_at=_now(),
        )
        self.repository.add_research(project_id, snapshot)
        return snapshot.model_dump(mode="json")

    @staticmethod
    def _active_requirement_items(state) -> list:
        return [
            item
            for item in state.items
            if item.status not in {"rejected", "superseded"}
        ]

    @staticmethod
    def _preferred_item(items: list, category: str):
        candidates = [item for item in items if item.category == category]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda item: (
                item.status == "confirmed",
                item.confirmation_level == "customer",
                item.confidence,
                item.requirement_id,
            ),
            reverse=True,
        )[0]

    @classmethod
    def _requirement_values(cls, items: list, category: str) -> list[str]:
        values: list[str] = []
        for item in items:
            if item.category == category and item.value not in values:
                values.append(item.value)
        return values

    def _demo_process_spec(self, project: PresalesProjectRecord, state) -> ProcessSpec:
        items = self._active_requirement_items(state)
        messages = self.engagement_service.repository.list_messages(project.project_id)
        latest_customer_message = next(
            (
                message.content
                for message in reversed(messages)
                if message.role == "customer" and message.delivery_status != "failed"
            ),
            "",
        )

        def scalar(category: str, fallback: str) -> str:
            item = self._preferred_item(items, category)
            return item.value if item is not None else fallback

        process_details = [
            item.process_detail
            for item in items
            if item.category == "current_process" and item.process_detail is not None
        ]
        process_ids = {detail.process_node_id for detail in process_details}
        process_nodes = [
            ProcessNode(
                id=detail.process_node_id,
                name=detail.name,
                actor=detail.actor,
                node_type=detail.node_type,
                description=detail.description,
                next_ids=[
                    node_id
                    for node_id in detail.next_node_ids
                    if node_id in process_ids
                ],
            )
            for detail in process_details
        ]
        pain_points = []
        for item in items:
            detail = item.pain_point_detail
            if item.category != "pain_point" or detail is None:
                continue
            pain_points.append(
                PainPoint(
                    id=detail.pain_point_id,
                    description=detail.description,
                    severity=detail.severity,
                    affected_node_ids=[
                        node_id
                        for node_id in detail.affected_process_node_ids
                        if node_id in process_ids
                    ],
                )
            )

        missing_information = [
            f"[{gap.category}] {gap.description}"
            for gap in state.gaps
        ]
        missing_information.extend(
            f"[conflict] {conflict.description}"
            for conflict in state.conflicts
            if conflict.status == "open"
        )
        missing_information.append(
            "当前方案为基于最新需求状态生成的演示预览，尚未形成正式客户确认基线。"
        )

        constraints = []
        if state.selected_skill_id:
            skill = self.engagement_service.internal_console.skill_loader.resolve(
                state.selected_skill_id
            )
            for item in items:
                if item.category not in {
                    "security", "approval", "budget", "time", "data", "risk"
                }:
                    continue
                try:
                    constraint = ProcessSpecAdapter.constraint_from_item(
                        project.project_id, item, skill
                    )
                except ValueError as error:
                    missing_information.append(
                        f"[{item.category}] 约束仍待确认：{error}"
                    )
                    continue
                if constraint is None:
                    continue
                if not (
                    item.status == "confirmed"
                    and item.confirmation_level == "customer"
                ):
                    constraint = constraint.model_copy(update={"hard": False})
                constraints.append(constraint)

        core_categories = {
            "industry", "department", "business_goal", "current_process", "pain_point"
        }
        present_categories = {item.category for item in items} & core_categories
        readiness_score = round(
            len(present_categories) / len(core_categories) * 100,
            2,
        )
        blocking_gaps = [gap for gap in state.gaps if gap.blocking]
        return ProcessSpec(
            project_id=project.project_id,
            industry=scalar("industry", project.industry or "待确认行业"),
            department=scalar("department", "待确认业务部门"),
            business_goal=scalar(
                "business_goal",
                latest_customer_message or "基于当前客户需求生成演示方案",
            ),
            roles=self._requirement_values(items, "role") or ["待确认项目角色"],
            available_data=self._requirement_values(items, "available_data"),
            existing_systems=self._requirement_values(items, "existing_system"),
            as_is_nodes=process_nodes,
            pain_points=pain_points,
            constraints=constraints,
            target_metrics=self._requirement_values(items, "target_metric"),
            missing_information=list(dict.fromkeys(missing_information)),
            clarification_questions=[
                f"请确认：{gap.description}" for gap in blocking_gaps[:3]
            ],
            readiness_score=readiness_score,
        )

    @staticmethod
    def _safe_general_plan(plan, recommended_solution_id: str) -> dict[str, Any]:
        data_requirements = list(
            dict.fromkeys(
                requirement
                for component in plan.selected_components
                for requirement in component.required_data
            )
        )
        return {
            "recommended": plan.solution_id == recommended_solution_id,
            "name": plan.name,
            "summary": plan.summary,
            "strategy": {
                "conservative": "快速验证",
                "balanced": "生产适配",
                "innovative": "体系升级",
            }[plan.plan_type],
            "capabilities": [
                {"name": component.name, "reason": component.reason}
                for component in plan.selected_components
            ],
            "target_workflow": [
                {
                    "name": node.name,
                    "executor": {"ai": "AI", "human": "人工", "system": "系统"}[
                        node.executor
                    ],
                    "human_gate": node.human_gate,
                    "gate_reason": node.gate_reason,
                }
                for node in plan.to_be_nodes
            ],
            "implementation_steps": list(plan.implementation_steps),
            "data_requirements": data_requirements,
            "system_integrations": [],
            "assumptions": list(plan.assumptions),
            "risks": list(plan.warnings),
        }

    def _deliverable(
        self,
        project: PresalesProjectRecord,
        requirement_items: list,
        research: ResearchSnapshot,
        plans: list[dict[str, Any]],
        *,
        provisional: bool,
    ) -> DeliverableContent:
        recommended = next((plan for plan in plans if plan.get("recommended")), plans[0])
        current_categories = {"customer_context", "industry", "department", "current_process"}
        problem_categories = {"pain_point"}
        current_state = [
            f"{self.engagement_service._category_label(item.category)}：{item.value}"
            for item in requirement_items
            if item.category in current_categories
        ]
        problems = [
            item.value
            for item in requirement_items
            if item.category in problem_categories
        ]
        metrics = [
            item.value
            for item in requirement_items
            if item.category == "target_metric"
        ]
        value_hypotheses = [
            f"待验证：{metric}。目标值和计算口径待确认，并需在客户环境中验证。"
            for metric in metrics
        ] or ["待验证：当前尚未确认可量化目标指标，需在实施前补充验证口径。"]
        citations = list(research.citations)
        return DeliverableContent(
            title=f"{project.title}售前解决方案",
            customer_current_state=current_state or ["客户现状仍需继续补充确认。"],
            problem_analysis=problems or ["当前尚未形成客户确认的问题分析。"],
            requirement_understanding=[
                f"{self.engagement_service._category_label(item.category)}：{item.value}"
                for item in requirement_items
            ],
            recommended_solution=str(recommended.get("summary") or recommended.get("name")),
            value_hypotheses=value_hypotheses,
            implementation_roadmap=list(recommended.get("implementation_steps", [])),
            risks_and_boundaries=[
                *(
                    ["演示预览：当前需求尚未形成正式确认基线，方案内容需继续核对。"]
                    if provisional
                    else []
                ),
                *[str(item) for item in recommended.get("risks", [])],
                *[f"待确认假设：{item}" for item in recommended.get("assumptions", [])],
                "方案效果和目标指标需在客户环境中验证，不代表已实现业务成果。",
            ],
            case_references=[item["title"] for item in research.knowledge_results],
            citations=citations,
        )

    def generate_draft(
        self,
        project_id: str,
        *,
        baseline_version: int | None,
        generated_by: str,
    ) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        baseline_versions = self.engagement_service.requirement_repository.list_baseline_versions(
            project_id
        )
        selected_baseline = baseline_version or (
            baseline_versions[-1] if baseline_versions else None
        )
        if not project.research_snapshots:
            raise ValueError("knowledge research snapshot is required")
        baseline = None
        state = None
        draft_warnings: list[str] = []
        if selected_baseline is not None:
            baseline = self.engagement_service.requirement_repository.load_baseline(
                project_id, selected_baseline
            )
        if baseline is not None:
            handoff = self.engagement_service.internal_console.compile(
                project_id, selected_baseline
            )
            bundle = handoff.bundle
            plans = [
                self.engagement_service._safe_plan(
                    plan, bundle.recommended_solution_id
                )
                for plan in bundle.plans
            ]
            requirement_items = list(baseline.confirmed_items)
            requirement_state_version = baseline.source_state_version
            requirement_basis = "confirmed_baseline"
        else:
            state = self.engagement_service.requirement_repository.load_state(project_id)
            if state is None:
                raise ValueError("latest RequirementState is required")
            process = self._demo_process_spec(project, state)
            try:
                bundle = compile_solution_v2(process)
                plans = [
                    self.engagement_service._safe_plan(
                        plan, bundle.recommended_solution_id
                    )
                    for plan in bundle.plans
                ]
            except ValueError as error:
                if "no executable reuse decisions" not in str(error):
                    raise
                general_bundle = compile_solution(process)
                recommended = next(
                    plan
                    for plan in general_bundle.plans
                    if plan.plan_type == "balanced"
                )
                plans = [
                    self._safe_general_plan(plan, recommended.solution_id)
                    for plan in general_bundle.plans
                ]
                draft_warnings.append(
                    "当前需求信息不足以匹配可执行方案资产，演示预览已自动使用通用三方案编译器。"
                )
            requirement_items = self._active_requirement_items(state)
            requirement_state_version = state.state_version
            requirement_basis = "latest_requirement_state"
            selected_baseline = None
            draft_warnings.append(
                "演示预览：方案基于最新 RequirementState 实时生成，尚未形成正式客户确认基线。"
            )
        research = project.research_snapshots[-1]
        timestamp = _now()
        draft = SolutionDraft(
            draft_version=len(project.drafts) + 1,
            baseline_version=selected_baseline,
            requirement_state_version=requirement_state_version,
            requirement_basis=requirement_basis,
            research_version=research.research_version,
            plans=plans,
            warnings=draft_warnings,
            deliverable_revision=1,
            deliverable=self._deliverable(
                project,
                requirement_items,
                research,
                plans,
                provisional=requirement_basis == "latest_requirement_state",
            ),
            generated_by=generated_by,
            generated_at=timestamp,
            updated_by=generated_by,
            updated_at=timestamp,
        )
        self.repository.add_draft(project_id, draft)
        return draft.model_dump(mode="json")

    def _draft(self, project: PresalesProjectRecord, draft_version: int) -> SolutionDraft:
        draft = next(
            (item for item in project.drafts if item.draft_version == draft_version),
            None,
        )
        if draft is None:
            raise FileNotFoundError("solution draft does not exist")
        return draft

    def update_deliverable(
        self,
        project_id: str,
        *,
        draft_version: int,
        content: DeliverableContent,
        updated_by: str,
    ) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        draft = self._draft(project, draft_version)
        updated = draft.model_copy(
            update={
                "deliverable_revision": draft.deliverable_revision + 1,
                "deliverable": content,
                "updated_by": updated_by,
                "updated_at": _now(),
            }
        )
        self.repository.replace_draft(project_id, updated)
        return updated.model_dump(mode="json")

    def review_draft(
        self,
        project_id: str,
        *,
        draft_version: int,
        decision: Literal["approved", "rejected"],
        reviewed_by: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        draft = self._draft(project, draft_version)
        review = DraftReview(
            review_version=len(project.reviews) + 1,
            draft_version=draft_version,
            deliverable_revision=draft.deliverable_revision,
            decision=decision,
            reviewed_by=reviewed_by,
            note=note,
            reviewed_at=_now(),
        )
        self.repository.add_review(project_id, review)
        return review.model_dump(mode="json")

    @staticmethod
    def _approved_review(
        project: PresalesProjectRecord, draft: SolutionDraft
    ) -> DraftReview | None:
        return next(
            (
                review
                for review in reversed(project.reviews)
                if review.draft_version == draft.draft_version
                and review.deliverable_revision == draft.deliverable_revision
                and review.decision == "approved"
            ),
            None,
        )

    def publish_project(
        self,
        project_id: str,
        *,
        draft_version: int,
        published_by: str,
    ) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        draft = self._draft(project, draft_version)
        if self._approved_review(project, draft) is None:
            raise ValueError("current solution draft and deliverable must be approved")
        if draft.baseline_version is None:
            if draft.requirement_state_version is None:
                raise ValueError("demo draft requirement state is missing")
            publication = self.engagement_service.publish_demo_preview(
                project_id,
                requirement_state_version=draft.requirement_state_version,
                plans=draft.plans,
                published_by=published_by,
            )
        else:
            publication = self.engagement_service.publish_project(
                project_id,
                baseline_version=draft.baseline_version,
                published_by=published_by,
            )
        published = PublishedDeliverable(
            publication_version=publication["publication_version"],
            draft_version=draft.draft_version,
            deliverable_revision=draft.deliverable_revision,
            content=draft.deliverable,
            published_by=published_by,
            published_at=publication["published_at"],
        )
        self.repository.add_publication(project_id, published)
        return {
            **publication,
            "draft_version": draft.draft_version,
            "deliverable_revision": draft.deliverable_revision,
        }

    def _stages(
        self,
        project: PresalesProjectRecord,
        engagement: dict[str, Any],
    ) -> list[dict[str, str]]:
        state = engagement.get("requirement_state")
        external_ready = any(
            item.source_type == "external_intelligence" for item in project.sources
        )
        research_ready = bool(
            project.research_snapshots
            and project.research_snapshots[-1].knowledge_results
        )
        latest_draft = project.drafts[-1] if project.drafts else None
        approved = bool(
            latest_draft and self._approved_review(project, latest_draft)
        )
        output_ready = bool(project.published_deliverables)
        feedback_ready = False
        if project.published_deliverables:
            published_at = project.published_deliverables[-1].published_at
            feedback_ready = any(
                item.get("channel") == "customer_portal"
                and item.get("role") == "customer"
                and str(item.get("recorded_at", "")) > published_at
                for item in engagement.get("conversation", [])
            )
        facts = {
            "opportunity": bool(
                engagement.get("conversation") or project.sources or state
            ),
            "requirement_analysis": bool(state),
            "intelligence_research": external_ready,
            "knowledge_retrieval": research_ready,
            "solution_generation": bool(latest_draft),
            "internal_review": approved,
            "customer_output": output_ready,
            "feedback_iteration": feedback_ready,
        }
        stages: list[dict[str, str]] = []
        current_found = False
        for stage, label in _STAGE_LABELS.items():
            if facts[stage]:
                status = "completed"
            elif not current_found:
                status = "current"
                current_found = True
            else:
                status = "pending"
            stages.append({"stage": stage, "label": label, "status": status})
        return stages

    def get_workspace(self, project_id: str) -> dict[str, Any]:
        project = self._ensure_project(project_id)
        engagement = self.engagement_service.get_internal_project(project_id)
        stages = self._stages(project, engagement)
        stage_status = {item["stage"]: item["status"] for item in stages}
        template_chain = []
        for skill in self.skill_catalog.list_skills():
            connected_step = skill["connected_step"]
            template_chain.append(
                {
                    **skill,
                    "workflow_status": (
                        stage_status.get(connected_step, "definition_only")
                        if connected_step
                        else "definition_only"
                    ),
                }
            )
        return {
            "project": project.model_dump(
                mode="json",
                exclude={
                    "sources",
                    "research_snapshots",
                    "drafts",
                    "reviews",
                    "published_deliverables",
                },
            ),
            "stages": stages,
            "template_chain": template_chain,
            "sources": [item.model_dump(mode="json") for item in project.sources],
            "research_snapshots": [
                item.model_dump(mode="json") for item in project.research_snapshots
            ],
            "drafts": [item.model_dump(mode="json") for item in project.drafts],
            "reviews": [item.model_dump(mode="json") for item in project.reviews],
            "published_deliverables": [
                item.model_dump(mode="json")
                for item in project.published_deliverables
            ],
            **engagement,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        self._sync_engagement_projects()
        projects = []
        for project in self.repository.list_projects():
            workspace = self.get_workspace(project.project_id)
            current_stage = next(
                (item for item in workspace["stages"] if item["status"] == "current"),
                workspace["stages"][-1],
            )
            projects.append(
                {
                    "project_id": project.project_id,
                    "title": project.title,
                    "owner": project.owner,
                    "industry": project.industry,
                    "current_stage": current_stage["stage"],
                    "current_stage_label": current_stage["label"],
                    "message_count": len(workspace["conversation"]),
                    "latest_state_version": (
                        workspace["state_versions"][-1]
                        if workspace["state_versions"]
                        else None
                    ),
                    "latest_baseline_version": (
                        workspace["baseline_versions"][-1]
                        if workspace["baseline_versions"]
                        else None
                    ),
                    "latest_publication_version": (
                        workspace["published_deliverables"][-1][
                            "publication_version"
                        ]
                        if workspace["published_deliverables"]
                        else None
                    ),
                }
            )
        return projects

    def get_customer_deliverable_for_access(
        self, access_id: str, token: str
    ) -> dict[str, Any] | None:
        project_id = self.engagement_service.repository.project_for_access(
            access_id, token
        )
        try:
            project = self.repository.get_project(project_id)
        except FileNotFoundError:
            return None
        if not project.published_deliverables:
            return None
        published = project.published_deliverables[-1]
        content = published.content.model_dump(mode="json")
        content["citations"] = [
            {
                "title": str(item.get("title", "来源资料")),
                **(
                    {"url": str(item.get("locator"))}
                    if str(item.get("locator", "")).startswith(("http://", "https://"))
                    else {}
                ),
            }
            for item in content["citations"]
        ]
        return {
            "publication_version": published.publication_version,
            "published_at": published.published_at,
            **content,
        }

    @staticmethod
    def render_customer_deliverable_html(deliverable: dict[str, Any] | None) -> str:
        if deliverable is None:
            raise FileNotFoundError("published customer deliverable does not exist")

        def list_items(values: list[Any]) -> str:
            return "".join(f"<li>{escape(str(value))}</li>" for value in values)

        citation_items = []
        for item in deliverable.get("citations", []):
            title = escape(str(item.get("title", "来源资料")))
            url = str(item.get("url", ""))
            if url.startswith(("http://", "https://")):
                citation_items.append(
                    f'<li><a href="{escape(url, quote=True)}" rel="noreferrer">{title}</a></li>'
                )
            else:
                citation_items.append(f"<li>{title}</li>")
        sections = [
            ("客户现状", list_items(deliverable.get("customer_current_state", []))),
            ("问题分析", list_items(deliverable.get("problem_analysis", []))),
            ("需求理解", list_items(deliverable.get("requirement_understanding", []))),
            (
                "推荐方案",
                f"<p>{escape(str(deliverable.get('recommended_solution', '')))}</p>",
            ),
            ("价值验证假设", list_items(deliverable.get("value_hypotheses", []))),
            ("实施路线", list_items(deliverable.get("implementation_roadmap", []))),
            ("风险与边界", list_items(deliverable.get("risks_and_boundaries", []))),
            ("案例参考", list_items(deliverable.get("case_references", []))),
            ("来源引用", "<ul>" + "".join(citation_items) + "</ul>"),
        ]
        body = "".join(
            f'<section><h2>{escape(title)}</h2><div contenteditable="true"><ul>{content}</ul></div></section>'
            if title not in {"推荐方案", "来源引用"}
            else f'<section><h2>{escape(title)}</h2><div contenteditable="true">{content}</div></section>'
            for title, content in sections
        )
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(str(deliverable.get('title', '客户售前解决方案')))}</title>
<style>body{{font-family:Inter,"PingFang SC",sans-serif;margin:0;background:#f4f7fb;color:#172033}}main{{max-width:960px;margin:30px auto;padding:0 20px}}header,section{{background:white;border:1px solid #dbe3f0;border-radius:14px;padding:22px;margin-bottom:16px}}header{{background:#172554;color:white}}h1,h2{{margin-top:0}}li{{margin:7px 0}}.notice{{color:#92400e;background:#fffbeb;padding:12px;border-radius:8px}}button{{padding:10px 14px;border:0;border-radius:8px;background:#1d4ed8;color:white}}</style>
</head><body><main><header><h1>{escape(str(deliverable.get('title', '客户售前解决方案')))}</h1><p>发布版本 {escape(str(deliverable.get('publication_version', '')))}</p><button onclick="downloadHtml()">下载当前 HTML</button></header><p class="notice">价值指标和方案效果需要在客户环境中验证，本成果不代表已取得业务结果。</p>{body}</main>
<script>function downloadHtml(){{const blob=new Blob([document.documentElement.outerHTML],{{type:'text/html'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='dcforge-presales-solution.html';link.click();URL.revokeObjectURL(link.href)}}</script></body></html>"""
