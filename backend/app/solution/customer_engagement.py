"""Durable customer conversation, requirement, and published-solution boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.contracts.requirement_intelligence import RequirementConfirmation
from backend.app.internal_console.service import InternalConsoleService
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.chat_agent import ChatTurn


_CATEGORY_LABELS = {
    "customer_context": "客户背景",
    "industry": "所属行业",
    "department": "业务部门",
    "business_goal": "业务目标",
    "role": "参与角色",
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
    "budget": "预算约束",
    "time": "实施周期",
    "data": "数据要求",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EngagementProject(_PrivateModel):
    project_id: str = Field(min_length=1)
    channel: Literal["feishu", "customer_portal", "requirement_state"] = "feishu"
    tenant_key: str | None = None
    chat_id: str | None = None
    sender_open_id: str | None = None
    created_at: str
    updated_at: str


class FeishuChatSession(_PrivateModel):
    tenant_key: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    active_project_id: str = Field(min_length=1)
    session_number: int = Field(ge=1)
    previous_project_ids: list[str] = Field(default_factory=list, max_length=1000)
    updated_at: str


class EngagementMessage(_PrivateModel):
    record_id: str
    project_id: str
    channel: Literal["feishu", "customer_portal"]
    role: Literal["customer", "employee", "assistant"]
    message_id: str
    event_id: str
    content: str = Field(min_length=1, max_length=12000)
    delivery_status: Literal["received", "replied", "failed"]
    recorded_at: str


class CustomerAccess(_PrivateModel):
    project_id: str
    access_id: str
    token: str
    created_at: str
    expires_at: str


class PublishedSolution(_PrivateModel):
    project_id: str
    publication_version: int = Field(ge=1)
    baseline_version: int | None = Field(default=None, ge=1)
    requirement_state_version: int | None = Field(default=None, ge=1)
    publication_basis: Literal[
        "confirmed_baseline", "latest_requirement_state"
    ] = "confirmed_baseline"
    published_by: str
    published_at: str
    requirements: list[dict[str, Any]]
    plans: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_publication_basis(self) -> "PublishedSolution":
        if self.publication_basis == "confirmed_baseline" and self.baseline_version is None:
            raise ValueError("confirmed publication requires baseline_version")
        if (
            self.publication_basis == "latest_requirement_state"
            and self.requirement_state_version is None
        ):
            raise ValueError("demo publication requires requirement_state_version")
        return self


class RequirementFeedbackAnalyzer(Protocol):
    def analyze_turn(
        self,
        *,
        project_id: str,
        message_id: str,
        message: str,
        sender_open_id: str | None = None,
    ): ...


class FileCustomerEngagementRepository:
    """Small file repository kept outside the Git working tree."""

    def __init__(
        self,
        root: Path | str,
        *,
        access_ttl_days: int = 30,
    ) -> None:
        if not 1 <= access_ttl_days <= 3650:
            raise ValueError("access_ttl_days must be between 1 and 3650")
        self.root = Path(root)
        self.access_ttl_days = access_ttl_days
        self._lock = RLock()

    def _project_dir(self, project_id: str) -> Path:
        if not project_id.strip():
            raise ValueError("project_id must not be blank")
        return self.root / _digest(project_id, 64)

    def _chat_session_path(self, tenant_key: str, chat_id: str) -> Path:
        if not tenant_key.strip() or not chat_id.strip():
            raise ValueError("tenant_key and chat_id must not be blank")
        identity = _digest(f"{tenant_key}|{chat_id}", 64)
        return self.root / "chat-sessions" / f"{identity}.json"

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
    def _read(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid customer engagement data: {path}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"invalid customer engagement data: {path}")
        return payload

    def register_project(
        self,
        project_id: str,
        *,
        channel: Literal[
            "feishu", "customer_portal", "requirement_state"
        ] = "feishu",
        tenant_key: str | None = None,
        chat_id: str | None = None,
        sender_open_id: str | None = None,
    ) -> EngagementProject:
        with self._lock:
            path = self._project_dir(project_id) / "project.json"
            timestamp = _now()
            if path.exists():
                current = EngagementProject.model_validate(self._read(path))
                project = current.model_copy(
                    update={
                        "channel": current.channel or channel,
                        "tenant_key": tenant_key or current.tenant_key,
                        "chat_id": chat_id or current.chat_id,
                        "sender_open_id": sender_open_id or current.sender_open_id,
                        "updated_at": timestamp,
                    }
                )
            else:
                project = EngagementProject(
                    project_id=project_id,
                    channel=channel,
                    tenant_key=tenant_key,
                    chat_id=chat_id,
                    sender_open_id=sender_open_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            self._atomic_write(path, project.model_dump(mode="json"))
            return project

    def get_project(self, project_id: str) -> EngagementProject:
        path = self._project_dir(project_id) / "project.json"
        if not path.exists():
            raise FileNotFoundError("customer project does not exist")
        return EngagementProject.model_validate(self._read(path))

    def list_projects(self) -> list[EngagementProject]:
        if not self.root.exists():
            return []
        projects = [
            EngagementProject.model_validate(self._read(path))
            for path in self.root.glob("*/project.json")
        ]
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def active_feishu_project_id(self, tenant_key: str, chat_id: str) -> str:
        with self._lock:
            path = self._chat_session_path(tenant_key, chat_id)
            if path.exists():
                return FeishuChatSession.model_validate(
                    self._read(path)
                ).active_project_id
            project_id = f"feishu:{tenant_key}:{chat_id}"
            session = FeishuChatSession(
                tenant_key=tenant_key,
                chat_id=chat_id,
                active_project_id=project_id,
                session_number=1,
                updated_at=_now(),
            )
            self._atomic_write(path, session.model_dump(mode="json"))
            return project_id

    def start_new_feishu_project(
        self,
        tenant_key: str,
        chat_id: str,
        *,
        sender_open_id: str | None = None,
    ) -> str:
        with self._lock:
            path = self._chat_session_path(tenant_key, chat_id)
            current_project_id = self.active_feishu_project_id(tenant_key, chat_id)
            current = FeishuChatSession.model_validate(self._read(path))
            session_number = current.session_number + 1
            project_id = (
                f"feishu:{tenant_key}:{chat_id}:session:{session_number:04d}"
            )
            previous = [*current.previous_project_ids, current_project_id]
            session = current.model_copy(
                update={
                    "active_project_id": project_id,
                    "session_number": session_number,
                    "previous_project_ids": list(dict.fromkeys(previous))[-1000:],
                    "updated_at": _now(),
                }
            )
            self._atomic_write(path, session.model_dump(mode="json"))
            self.register_project(
                project_id,
                channel="feishu",
                tenant_key=tenant_key,
                chat_id=chat_id,
                sender_open_id=sender_open_id,
            )
            self.ensure_access(project_id)
            return project_id

    def append_message(
        self,
        *,
        project_id: str,
        channel: Literal["feishu", "customer_portal"],
        role: Literal["customer", "employee", "assistant"],
        message_id: str,
        event_id: str,
        content: str,
        delivery_status: Literal["received", "replied", "failed"],
    ) -> EngagementMessage:
        record_id = _digest(f"{project_id}|{channel}|{message_id}|{role}")
        message = EngagementMessage(
            record_id=record_id,
            project_id=project_id,
            channel=channel,
            role=role,
            message_id=message_id,
            event_id=event_id,
            content=content,
            delivery_status=delivery_status,
            recorded_at=_now(),
        )
        with self._lock:
            path = self._project_dir(project_id) / "messages" / f"{record_id}.json"
            if path.exists():
                existing = EngagementMessage.model_validate(self._read(path))
                comparable = (
                    existing.project_id,
                    existing.channel,
                    existing.role,
                    existing.content,
                )
                expected = (
                    message.project_id,
                    message.channel,
                    message.role,
                    message.content,
                )
                if comparable != expected:
                    raise ValueError("message idempotency key contains different content")
                return existing
            self._atomic_write(path, message.model_dump(mode="json"))
            return message

    def list_messages(self, project_id: str) -> list[EngagementMessage]:
        directory = self._project_dir(project_id) / "messages"
        if not directory.exists():
            return []
        messages = [
            EngagementMessage.model_validate(self._read(path))
            for path in directory.glob("*.json")
        ]
        role_order = {"customer": 0, "employee": 0, "assistant": 1}
        return sorted(
            messages,
            key=lambda item: (item.recorded_at, item.message_id, role_order[item.role]),
        )

    def _expires_at(self, created_at: str) -> str:
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError as error:
            raise ValueError("invalid customer access created_at") from error
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return (created.astimezone(UTC) + timedelta(days=self.access_ttl_days)).isoformat()

    @staticmethod
    def _access_expired(access: CustomerAccess) -> bool:
        try:
            expires_at = datetime.fromisoformat(access.expires_at)
        except ValueError as error:
            raise ValueError("invalid customer access expires_at") from error
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at.astimezone(UTC) <= datetime.now(UTC)

    def _load_access(self, path: Path) -> CustomerAccess:
        payload = self._read(path)
        changed = False
        if not payload.get("access_id"):
            payload["access_id"] = secrets.token_urlsafe(16)
            changed = True
        if not payload.get("expires_at"):
            created_at = payload.get("created_at")
            if not isinstance(created_at, str) or not created_at.strip():
                raise ValueError("invalid customer access created_at")
            payload["expires_at"] = self._expires_at(created_at)
            changed = True
        access = CustomerAccess.model_validate(payload)
        if changed:
            self._atomic_write(path, access.model_dump(mode="json"))
        return access

    def _new_access(self, project_id: str) -> CustomerAccess:
        created_at = _now()
        return CustomerAccess(
            project_id=project_id,
            access_id=secrets.token_urlsafe(16),
            token=secrets.token_urlsafe(32),
            created_at=created_at,
            expires_at=self._expires_at(created_at),
        )

    def ensure_access(self, project_id: str) -> CustomerAccess:
        with self._lock:
            self.get_project(project_id)
            path = self._project_dir(project_id) / "access.json"
            if path.exists():
                access = self._load_access(path)
                if not self._access_expired(access):
                    return access
            access = self._new_access(project_id)
            self._atomic_write(path, access.model_dump(mode="json"))
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return access

    def rotate_access(self, project_id: str) -> CustomerAccess:
        with self._lock:
            self.get_project(project_id)
            rotated = self._new_access(project_id)
            path = self._project_dir(project_id) / "access.json"
            self._atomic_write(path, rotated.model_dump(mode="json"))
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return rotated

    def project_for_token(self, token: str) -> str:
        if not token.strip() or not self.root.exists():
            raise FileNotFoundError("customer access does not exist")
        for path in self.root.glob("*/access.json"):
            access = self._load_access(path)
            if self._access_expired(access):
                continue
            if hmac.compare_digest(access.token, token):
                return access.project_id
        raise FileNotFoundError("customer access does not exist")

    def project_for_access_id(self, access_id: str) -> str:
        if not access_id.strip() or not self.root.exists():
            raise FileNotFoundError("customer access does not exist")
        for path in self.root.glob("*/access.json"):
            access = self._load_access(path)
            if self._access_expired(access):
                continue
            if hmac.compare_digest(access.access_id, access_id):
                return access.project_id
        raise FileNotFoundError("customer access does not exist")

    def project_for_access(self, access_id: str, token: str) -> str:
        project_id = self.project_for_access_id(access_id)
        access = self.ensure_access(project_id)
        if not token.strip() or not hmac.compare_digest(access.token, token):
            raise FileNotFoundError("customer access does not exist")
        return project_id

    def save_publication(
        self,
        *,
        project_id: str,
        baseline_version: int | None,
        requirement_state_version: int | None = None,
        publication_basis: Literal[
            "confirmed_baseline", "latest_requirement_state"
        ] = "confirmed_baseline",
        published_by: str,
        requirements: list[dict[str, Any]],
        plans: list[dict[str, Any]],
    ) -> PublishedSolution:
        with self._lock:
            versions = self.list_publications(project_id)
            publication = PublishedSolution(
                project_id=project_id,
                publication_version=(versions[-1].publication_version + 1 if versions else 1),
                baseline_version=baseline_version,
                requirement_state_version=requirement_state_version,
                publication_basis=publication_basis,
                published_by=published_by,
                published_at=_now(),
                requirements=requirements,
                plans=plans,
            )
            path = (
                self._project_dir(project_id)
                / "publications"
                / f"publication-{publication.publication_version:08d}.json"
            )
            self._atomic_write(path, publication.model_dump(mode="json"))
            return publication

    def list_publications(self, project_id: str) -> list[PublishedSolution]:
        directory = self._project_dir(project_id) / "publications"
        if not directory.exists():
            return []
        publications = [
            PublishedSolution.model_validate(self._read(path))
            for path in directory.glob("publication-*.json")
        ]
        return sorted(publications, key=lambda item: item.publication_version)


class CustomerEngagementService:
    """Joins durable conversations to Requirement Intelligence and publication."""

    def __init__(
        self,
        *,
        repository: FileCustomerEngagementRepository,
        requirement_repository: FileRequirementRepository,
        internal_console: InternalConsoleService,
        feedback_analyzer: RequirementFeedbackAnalyzer | None = None,
        public_base_url: str = "http://127.0.0.1:8000",
    ) -> None:
        self.repository = repository
        self.requirement_repository = requirement_repository
        self.internal_console = internal_console
        self.feedback_analyzer = feedback_analyzer
        self.public_base_url = public_base_url.rstrip("/")

    @classmethod
    def from_env(
        cls,
        *,
        feedback_analyzer: RequirementFeedbackAnalyzer | None = None,
    ) -> "CustomerEngagementService":
        requirement_root_raw = os.getenv("REQUIREMENT_REPOSITORY_ROOT", "").strip()
        if not requirement_root_raw:
            raise RuntimeError(
                "Customer engagement is not configured; missing REQUIREMENT_REPOSITORY_ROOT"
            )
        project_root = Path(__file__).parents[3].resolve()
        requirement_root = Path(requirement_root_raw).expanduser().resolve()
        if requirement_root == project_root or requirement_root.is_relative_to(project_root):
            raise RuntimeError("REQUIREMENT_REPOSITORY_ROOT must be outside the Git working tree")
        engagement_raw = os.getenv("CUSTOMER_ENGAGEMENT_ROOT", "").strip()
        engagement_root = (
            Path(engagement_raw).expanduser().resolve()
            if engagement_raw
            else requirement_root.parent / f"{requirement_root.name}-engagement"
        )
        if engagement_root == project_root or engagement_root.is_relative_to(project_root):
            raise RuntimeError("CUSTOMER_ENGAGEMENT_ROOT must be outside the Git working tree")
        try:
            access_ttl_days = int(
                os.getenv("CUSTOMER_ACCESS_TTL_DAYS", "30").strip() or "30"
            )
        except ValueError as error:
            raise RuntimeError("CUSTOMER_ACCESS_TTL_DAYS must be an integer") from error
        if not 1 <= access_ttl_days <= 3650:
            raise RuntimeError(
                "CUSTOMER_ACCESS_TTL_DAYS must be between 1 and 3650"
            )
        requirement_repository = FileRequirementRepository(requirement_root)
        internal_console = InternalConsoleService(
            repository=requirement_repository,
            skill_loader=RequirementSkillLoader(project_root / "data" / "requirement_skills"),
        )
        return cls(
            repository=FileCustomerEngagementRepository(
                engagement_root,
                access_ttl_days=access_ttl_days,
            ),
            requirement_repository=requirement_repository,
            internal_console=internal_console,
            feedback_analyzer=feedback_analyzer,
            public_base_url=os.getenv(
                "CUSTOMER_PORTAL_BASE_URL", "http://127.0.0.1:8000"
            ),
        )

    def record_customer_message(
        self,
        *,
        project_id: str,
        channel: Literal["feishu", "customer_portal"],
        message_id: str,
        event_id: str,
        content: str,
        tenant_key: str | None = None,
        chat_id: str | None = None,
        sender_open_id: str | None = None,
    ) -> None:
        self.repository.register_project(
            project_id,
            channel=channel,
            tenant_key=tenant_key,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
        )
        self.repository.append_message(
            project_id=project_id,
            channel=channel,
            role="customer",
            message_id=message_id,
            event_id=event_id,
            content=content,
            delivery_status="received",
        )
        self.repository.ensure_access(project_id)

    def active_feishu_project_id(self, tenant_key: str, chat_id: str) -> str:
        return self.repository.active_feishu_project_id(tenant_key, chat_id)

    def start_new_feishu_project(
        self,
        tenant_key: str,
        chat_id: str,
        *,
        sender_open_id: str | None = None,
    ) -> str:
        return self.repository.start_new_feishu_project(
            tenant_key,
            chat_id,
            sender_open_id=sender_open_id,
        )

    def record_agent_message(
        self,
        *,
        project_id: str,
        channel: Literal["feishu", "customer_portal"],
        message_id: str,
        event_id: str,
        content: str,
        delivery_status: Literal["replied", "failed"],
    ) -> None:
        self.repository.append_message(
            project_id=project_id,
            channel=channel,
            role="assistant",
            message_id=message_id,
            event_id=event_id,
            content=content,
            delivery_status=delivery_status,
        )

    def chat_history(self, project_id: str, limit: int = 20) -> list[ChatTurn]:
        messages = self.repository.list_messages(project_id)
        turns = [
            ChatTurn(
                role="assistant" if message.role == "assistant" else "user",
                content=message.content,
            )
            for message in messages
            if message.delivery_status != "failed"
        ]
        return turns[-limit:]

    def ensure_customer_access(self, project_id: str) -> dict[str, str]:
        self._ensure_registered_project(project_id)
        access = self.repository.ensure_access(project_id)
        return {
            "access_id": access.access_id,
            "token": access.token,
            "url": (
                f"{self.public_base_url}/customer/engagement/{access.access_id}"
                f"#access_token={access.token}"
            ),
        }

    def customer_portal_url(self, project_id: str) -> str:
        return self.ensure_customer_access(project_id)["url"]

    def validate_customer_access_id(self, access_id: str) -> None:
        self.repository.project_for_access_id(access_id)

    def get_customer_view_for_access(
        self, access_id: str, token: str
    ) -> dict[str, Any]:
        project_id = self.repository.project_for_access(access_id, token)
        expected_project = self.repository.project_for_token(token)
        if project_id != expected_project:
            raise FileNotFoundError("customer access does not exist")
        return self.get_customer_view(token)

    def internal_workbench_url(self) -> str:
        return f"{self.public_base_url}/presales/workbench"

    def _requirement_project_ids(self) -> set[str]:
        project_ids: set[str] = set()
        root = self.requirement_repository._root
        if not root.exists():
            return project_ids
        for path in root.glob("*/state-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid RequirementState discovery data: {path}") from error
            project_id = payload.get("project_id") if isinstance(payload, dict) else None
            if isinstance(project_id, str) and project_id.strip():
                project_ids.add(project_id)
        return project_ids

    def _ensure_registered_project(self, project_id: str) -> EngagementProject:
        try:
            return self.repository.get_project(project_id)
        except FileNotFoundError:
            if not self.requirement_repository.list_versions(project_id):
                raise
        tenant_key = chat_id = None
        if project_id.startswith("feishu:"):
            parts = project_id.split(":", 2)
            if len(parts) == 3:
                tenant_key, chat_id = parts[1], parts[2]
        return self.repository.register_project(
            project_id,
            channel="feishu" if project_id.startswith("feishu:") else "requirement_state",
            tenant_key=tenant_key,
            chat_id=chat_id,
        )

    def _sync_requirement_projects(self) -> None:
        known = {project.project_id for project in self.repository.list_projects()}
        for project_id in sorted(self._requirement_project_ids() - known):
            self._ensure_registered_project(project_id)

    def list_internal_projects(self) -> list[dict[str, Any]]:
        self._sync_requirement_projects()
        projects: list[dict[str, Any]] = []
        for project in self.repository.list_projects():
            messages = self.repository.list_messages(project.project_id)
            state_versions = self.requirement_repository.list_versions(project.project_id)
            baseline_versions = self.requirement_repository.list_baseline_versions(
                project.project_id
            )
            publications = self.repository.list_publications(project.project_id)
            projects.append(
                {
                    "project_id": project.project_id,
                    "channel": project.channel,
                    "chat_id": project.chat_id,
                    "sender_open_id": project.sender_open_id,
                    "message_count": len(messages),
                    "last_message_at": messages[-1].recorded_at if messages else None,
                    "latest_state_version": state_versions[-1] if state_versions else None,
                    "latest_baseline_version": (
                        baseline_versions[-1] if baseline_versions else None
                    ),
                    "latest_publication_version": (
                        publications[-1].publication_version if publications else None
                    ),
                    "customer_url": self.customer_portal_url(project.project_id),
                }
            )
        return projects

    def get_internal_project(self, project_id: str) -> dict[str, Any]:
        project = self._ensure_registered_project(project_id)
        state_versions = self.requirement_repository.list_versions(project_id)
        baseline_versions = self.requirement_repository.list_baseline_versions(project_id)
        state = (
            self.requirement_repository.load_state(project_id, state_versions[-1])
            if state_versions
            else None
        )
        baselines = self.requirement_repository.list_baselines(project_id)
        messages = self.repository.list_messages(project_id)
        publications = self.repository.list_publications(project_id)
        return {
            "project": project.model_dump(mode="json"),
            "conversation": [message.model_dump(mode="json") for message in messages],
            "requirement_state": state.model_dump(mode="json") if state else None,
            "state_versions": state_versions,
            "baseline_versions": baseline_versions,
            "baselines": [baseline.model_dump(mode="json") for baseline in baselines],
            "publications": [item.model_dump(mode="json") for item in publications],
            "customer_url": self.customer_portal_url(project_id),
        }

    @staticmethod
    def _category_label(category: str) -> str:
        if category.startswith("ext:"):
            return "行业专项要求"
        return _CATEGORY_LABELS.get(category, "其他需求")

    @staticmethod
    def _active_items(state) -> list:
        return [
            item
            for item in state.items
            if item.status not in {"rejected", "superseded"}
        ]

    def _confirmation_revision(self, token: str, state) -> str:
        return _digest(f"{token}|state|{state.state_version}|{state.updated_at or ''}", 32)

    def _item_key(self, token: str, state_version: int, requirement_id: str) -> str:
        return _digest(f"{token}|item|{state_version}|{requirement_id}", 32)

    def get_customer_view(self, token: str) -> dict[str, Any]:
        project_id = self.repository.project_for_token(token)
        project = self.repository.get_project(project_id)
        state = self.requirement_repository.load_state(project_id)
        baseline = self.requirement_repository.load_baseline(project_id)
        publication_versions = self.repository.list_publications(project_id)
        conflict_by_item: dict[str, str] = {}
        if state is not None:
            for conflict in state.conflicts:
                if conflict.status != "open":
                    continue
                public_group = _digest(
                    f"{token}|conflict|{state.state_version}|{conflict.conflict_id}", 20
                )
                for requirement_id in conflict.requirement_ids:
                    conflict_by_item[requirement_id] = public_group
        requirements = []
        if state is not None:
            for item in self._active_items(state):
                requirements.append(
                    {
                        "item_key": self._item_key(
                            token, state.state_version, item.requirement_id
                        ),
                        "category": self._category_label(item.category),
                        "subject": item.subject,
                        "value": item.value,
                        "status": (
                            "已由您确认"
                            if item.confirmation_level == "customer"
                            else "待您确认"
                        ),
                        "choice_group": conflict_by_item.get(item.requirement_id),
                    }
                )
        requirements_confirmed = bool(
            state is not None
            and baseline is not None
            and baseline.source_state_version == state.state_version
        )
        latest_publication = publication_versions[-1] if publication_versions else None
        solution = None
        if latest_publication is not None:
            demo_preview = (
                latest_publication.publication_basis == "latest_requirement_state"
            )
            solution = {
                "publication_version": latest_publication.publication_version,
                "baseline_version": latest_publication.baseline_version,
                "requirement_state_version": latest_publication.requirement_state_version,
                "publication_basis": latest_publication.publication_basis,
                "published_at": latest_publication.published_at,
                "requirements": latest_publication.requirements,
                "plans": latest_publication.plans,
                "notice": (
                    "演示预览：本方案基于当前需求理解生成，尚未形成正式客户确认基线；"
                    "方案效果与目标指标仍需在客户环境中验证。"
                    if demo_preview
                    else "方案效果与目标指标需在客户环境中验证，不代表已实现业务成果。"
                ),
            }
        return {
            "project": {
                "channel": project.channel,
                "updated_at": project.updated_at,
            },
            "requirements": requirements,
            "confirmation_revision": (
                self._confirmation_revision(token, state) if state is not None else None
            ),
            "requirements_confirmed": requirements_confirmed,
            "solution": solution,
        }

    def confirm_customer_requirements(
        self,
        *,
        token: str,
        confirmation_revision: str,
        accepted_item_keys: list[str],
        rejected_item_keys: list[str],
        note: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.repository.project_for_token(token)
        state = self.requirement_repository.load_state(project_id)
        if state is None:
            raise ValueError("RequirementState does not exist")
        expected_revision = self._confirmation_revision(token, state)
        if not hmac.compare_digest(expected_revision, confirmation_revision):
            raise RuntimeError("customer confirmation is stale")
        key_to_id = {
            self._item_key(token, state.state_version, item.requirement_id): item.requirement_id
            for item in self._active_items(state)
        }
        supplied = set(accepted_item_keys) | set(rejected_item_keys)
        unknown = supplied - set(key_to_id)
        if unknown:
            raise ValueError("unknown customer requirement item")
        analysis, baseline = self.internal_console.confirm(
            RequirementConfirmation(
                project_id=project_id,
                state_version=state.state_version,
                confirmation_level="customer",
                confirmed_requirement_ids=[key_to_id[key] for key in accepted_item_keys],
                rejected_requirement_ids=[key_to_id[key] for key in rejected_item_keys],
                confirmed_by=f"customer-portal:{_digest(token, 12)}",
                note=note,
            )
        )
        return {
            "accepted": True,
            "baseline_created": baseline is not None,
            "requirements_confirmed": baseline is not None,
            "message": (
                "需求已确认，企业团队可以据此生成正式方案。"
                if baseline is not None
                else "本轮确认已记录，仍有信息需要继续补充或确认。"
            ),
            "updated_at": analysis.current_state.updated_at,
        }

    @staticmethod
    def _safe_requirement(item) -> dict[str, str]:
        return {
            "category": CustomerEngagementService._category_label(item.category),
            "subject": item.subject,
            "value": item.value,
        }

    @staticmethod
    def _safe_plan(plan, recommended_solution_id: str) -> dict[str, Any]:
        return {
            "recommended": plan.solution_id == recommended_solution_id,
            "name": plan.name,
            "summary": plan.summary,
            "strategy": {
                "quick_win": "快速验证",
                "production_fit": "生产适配",
                "transform": "体系升级",
            }[plan.display_strategy],
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
            "data_requirements": list(plan.data_requirements),
            "system_integrations": list(plan.system_integrations),
            "assumptions": list(plan.assumptions),
            "risks": list(plan.risks),
        }

    def publish_project(
        self,
        project_id: str,
        *,
        baseline_version: int,
        published_by: str,
    ) -> dict[str, Any]:
        try:
            baseline = self.requirement_repository.load_baseline(
                project_id, baseline_version
            )
        except FileNotFoundError as error:
            raise ValueError("RequirementBaseline does not exist") from error
        if baseline is None:
            raise ValueError("RequirementBaseline does not exist")
        handoff = self.internal_console.compile(project_id, baseline_version)
        publication = self.repository.save_publication(
            project_id=project_id,
            baseline_version=baseline_version,
            requirement_state_version=baseline.source_state_version,
            publication_basis="confirmed_baseline",
            published_by=published_by,
            requirements=[self._safe_requirement(item) for item in baseline.confirmed_items],
            plans=[
                self._safe_plan(plan, handoff.bundle.recommended_solution_id)
                for plan in handoff.bundle.plans
            ],
        )
        return {
            "publication_version": publication.publication_version,
            "baseline_version": publication.baseline_version,
            "published_at": publication.published_at,
            "customer_url": self.customer_portal_url(project_id),
        }

    def publish_demo_preview(
        self,
        project_id: str,
        *,
        requirement_state_version: int,
        plans: list[dict[str, Any]],
        published_by: str,
    ) -> dict[str, Any]:
        state = self.requirement_repository.load_state(
            project_id, requirement_state_version
        )
        if state is None:
            raise ValueError("RequirementState does not exist")
        publication = self.repository.save_publication(
            project_id=project_id,
            baseline_version=None,
            requirement_state_version=requirement_state_version,
            publication_basis="latest_requirement_state",
            published_by=published_by,
            requirements=[
                self._safe_requirement(item) for item in self._active_items(state)
            ],
            plans=plans,
        )
        return {
            "publication_version": publication.publication_version,
            "baseline_version": None,
            "requirement_state_version": publication.requirement_state_version,
            "publication_basis": publication.publication_basis,
            "published_at": publication.published_at,
            "customer_url": self.customer_portal_url(project_id),
        }

    def submit_customer_feedback(self, *, token: str, message: str) -> dict[str, Any]:
        project_id = self.repository.project_for_token(token)
        if self.feedback_analyzer is None:
            raise RuntimeError("Requirement feedback analyzer is unavailable")
        identifier = f"portal-{secrets.token_hex(12)}"
        self.record_customer_message(
            project_id=project_id,
            channel="customer_portal",
            message_id=identifier,
            event_id=identifier,
            content=message,
        )
        result = self.feedback_analyzer.analyze_turn(
            project_id=project_id,
            message_id=identifier,
            message=message,
            sender_open_id=None,
        )
        return {
            "accepted": True,
            "message": "补充信息已提交，企业团队将根据新信息更新需求理解。",
            "updated": bool(getattr(result, "state_version", None)),
        }
