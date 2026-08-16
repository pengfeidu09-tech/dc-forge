"""Database-backed Agent capability policy and reusable case catalog."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


_CUSTOMER_TOOL_CEILING = frozenset(
    {"search_knowledge", "search_solution_cases"}
)
_CURRENT_AGENT_TOOLS = _CUSTOMER_TOOL_CEILING


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentProfile(_Model):
    agent_id: Literal["feishu-customer", "feishu-internal"]
    audience: Literal["customer", "internal"]
    enabled_tools: list[str]
    enabled_skills: list[str]
    updated_by: str
    updated_at: str


class KnowledgeCase(_Model):
    case_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    industry: str | None = Field(default=None, max_length=120)
    problem: str = Field(min_length=1, max_length=12000)
    solution_summary: str = Field(min_length=1, max_length=12000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[str] = Field(default_factory=list, max_length=200)
    created_at: str
    updated_at: str


class AgentConfigurationRepository:
    """Small SQLite store for non-secret Agent policy and internal case records."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_profiles (
                    agent_id TEXT PRIMARY KEY,
                    audience TEXT NOT NULL,
                    enabled_tools_json TEXT NOT NULL,
                    enabled_skills_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_cases (
                    case_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    industry TEXT,
                    problem TEXT NOT NULL,
                    solution_summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _profile(row: sqlite3.Row) -> AgentProfile:
        return AgentProfile(
            agent_id=row["agent_id"],
            audience=row["audience"],
            enabled_tools=json.loads(row["enabled_tools_json"]),
            enabled_skills=json.loads(row["enabled_skills_json"]),
            updated_by=row["updated_by"],
            updated_at=row["updated_at"],
        )

    def get_profile(self, agent_id: str) -> AgentProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_profiles WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        return self._profile(row) if row is not None else None

    def save_profile(self, profile: AgentProfile) -> AgentProfile:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_profiles (
                    agent_id, audience, enabled_tools_json, enabled_skills_json,
                    updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    audience = excluded.audience,
                    enabled_tools_json = excluded.enabled_tools_json,
                    enabled_skills_json = excluded.enabled_skills_json,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.agent_id,
                    profile.audience,
                    json.dumps(profile.enabled_tools, ensure_ascii=False),
                    json.dumps(profile.enabled_skills, ensure_ascii=False),
                    profile.updated_by,
                    profile.updated_at,
                ),
            )
        return profile

    @staticmethod
    def _case(row: sqlite3.Row) -> KnowledgeCase:
        return KnowledgeCase(
            case_id=row["case_id"],
            title=row["title"],
            industry=row["industry"],
            problem=row["problem"],
            solution_summary=row["solution_summary"],
            tags=json.loads(row["tags_json"]),
            evidence_refs=json.loads(row["evidence_refs_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_case(self, case: KnowledgeCase) -> KnowledgeCase:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_cases (
                    case_id, title, industry, problem, solution_summary,
                    tags_json, evidence_refs_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    title = excluded.title,
                    industry = excluded.industry,
                    problem = excluded.problem,
                    solution_summary = excluded.solution_summary,
                    tags_json = excluded.tags_json,
                    evidence_refs_json = excluded.evidence_refs_json,
                    updated_at = excluded.updated_at
                """,
                (
                    case.case_id,
                    case.title,
                    case.industry,
                    case.problem,
                    case.solution_summary,
                    json.dumps(case.tags, ensure_ascii=False),
                    json.dumps(case.evidence_refs, ensure_ascii=False),
                    case.created_at,
                    case.updated_at,
                ),
            )
        return case

    def list_cases(self, query: str = "") -> list[KnowledgeCase]:
        term = query.strip().casefold()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_cases ORDER BY updated_at DESC"
            ).fetchall()
        cases = [self._case(row) for row in rows]
        if not term:
            return cases
        return [
            case
            for case in cases
            if term
            in " ".join(
                [
                    case.title,
                    case.industry or "",
                    case.problem,
                    case.solution_summary,
                    *case.tags,
                    *case.evidence_refs,
                ]
            ).casefold()
        ]


class AgentConfigurationService:
    def __init__(
        self,
        repository: AgentConfigurationRepository,
        *,
        tools: list[dict[str, Any]],
        skills: list[dict[str, Any]],
    ) -> None:
        self.repository = repository
        self._tools = {str(item["name"]): dict(item) for item in tools}
        self._skills = {str(item["name"]): dict(item) for item in skills}
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        defaults = {
            "feishu-customer": AgentProfile(
                agent_id="feishu-customer",
                audience="customer",
                enabled_tools=[
                    name for name in self._tools if name in _CUSTOMER_TOOL_CEILING
                ],
                enabled_skills=[
                    name
                    for name in self._skills
                    if name in {"requirement_analysis", "case_matching"}
                ],
                updated_by="system-default",
                updated_at=_now(),
            ),
            "feishu-internal": AgentProfile(
                agent_id="feishu-internal",
                audience="internal",
                enabled_tools=[
                    name
                    for name in self._tools
                    if name == "search_solution_cases"
                ],
                enabled_skills=list(self._skills),
                updated_by="system-default",
                updated_at=_now(),
            ),
        }
        for agent_id, profile in defaults.items():
            current = self.repository.get_profile(agent_id)
            if current is None:
                self.repository.save_profile(profile)
                continue
            allowed_tools = set(self._tools)
            if current.audience == "customer":
                allowed_tools &= _CUSTOMER_TOOL_CEILING
            enabled_tools = [
                name for name in current.enabled_tools if name in allowed_tools
            ]
            enabled_skills = [
                name for name in current.enabled_skills if name in self._skills
            ]
            if (
                enabled_tools != current.enabled_tools
                or enabled_skills != current.enabled_skills
            ):
                self.repository.save_profile(
                    current.model_copy(
                        update={
                            "enabled_tools": enabled_tools,
                            "enabled_skills": enabled_skills,
                            "updated_at": _now(),
                        }
                    )
                )

    def catalog(self) -> dict[str, Any]:
        return {
            "tools": list(self._tools.values()),
            "skills": list(self._skills.values()),
            "profiles": [
                self.profile("feishu-customer").model_dump(mode="json"),
                self.profile("feishu-internal").model_dump(mode="json"),
            ],
        }

    def profile(self, agent_id: str) -> AgentProfile:
        profile = self.repository.get_profile(agent_id)
        if profile is None:
            raise FileNotFoundError("agent profile does not exist")
        return profile

    def update_profile(
        self,
        agent_id: str,
        *,
        enabled_tools: list[str],
        enabled_skills: list[str],
        updated_by: str,
    ) -> AgentProfile:
        current = self.profile(agent_id)
        unknown_tools = set(enabled_tools) - set(self._tools)
        unknown_skills = set(enabled_skills) - set(self._skills)
        if unknown_tools:
            raise ValueError(f"unknown Agent tools: {', '.join(sorted(unknown_tools))}")
        if unknown_skills:
            raise ValueError(f"unknown Agent skills: {', '.join(sorted(unknown_skills))}")
        if current.audience == "customer" and set(enabled_tools) - _CUSTOMER_TOOL_CEILING:
            raise PermissionError("customer Agent cannot enable internal tools")
        profile = current.model_copy(
            update={
                "enabled_tools": list(dict.fromkeys(enabled_tools)),
                "enabled_skills": list(dict.fromkeys(enabled_skills)),
                "updated_by": updated_by,
                "updated_at": _now(),
            }
        )
        return self.repository.save_profile(profile)

    def enabled_tool_names(self, audience: str) -> set[str]:
        agent_id = "feishu-customer" if audience == "customer" else "feishu-internal"
        return set(self.profile(agent_id).enabled_tools) & set(self._tools)

    def enabled_skills(self, audience: str) -> list[dict[str, Any]]:
        agent_id = "feishu-customer" if audience == "customer" else "feishu-internal"
        return [
            self._skills[name]
            for name in self.profile(agent_id).enabled_skills
            if name in self._skills
        ]

    def list_cases(self, query: str = "") -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.repository.list_cases(query)]

    def save_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = _now()
        existing = next(
            (
                item
                for item in self.repository.list_cases()
                if item.case_id == payload.get("case_id")
            ),
            None,
        )
        case = KnowledgeCase.model_validate(
            {
                **payload,
                "created_at": existing.created_at if existing else timestamp,
                "updated_at": timestamp,
            }
        )
        return self.repository.save_case(case).model_dump(mode="json")


def _skill_catalog(project_root: Path) -> list[dict[str, Any]]:
    root = project_root / "企业客户需求全过程知识管理系统_FINAL_COMPLETE" / "07_Skill技能库"
    skills: list[dict[str, Any]] = []
    if not root.is_dir():
        return skills
    for path in sorted(root.glob("*.yaml"), key=lambda item: item.name):
        payload = json.loads(path.read_text(encoding="utf-8"))
        skills.append(
            {
                "name": str(payload["name"]),
                "version": str(payload.get("version", "")),
                "description": str(payload.get("description", "")),
            }
        )
    return skills


def configured_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    configured = os.getenv("DCFORGE_DATABASE_PATH", "").strip()
    if configured:
        database_path = Path(configured).expanduser().resolve()
    else:
        database_path = (
            Path.home() / ".local" / "share" / "dcforge" / "workspace.sqlite3"
        ).resolve()
    if database_path == project_root or database_path.is_relative_to(project_root):
        raise RuntimeError("DCFORGE_DATABASE_PATH must be outside the Git working tree")
    return database_path


def configured_case_repository() -> AgentConfigurationRepository:
    return AgentConfigurationRepository(configured_database_path())


def configured_agent_service(dispatcher) -> AgentConfigurationService:
    project_root = Path(__file__).resolve().parents[3]
    return AgentConfigurationService(
        configured_case_repository(),
        tools=[
            tool
            for tool in dispatcher.tool_definitions()
            if tool.get("name") in _CURRENT_AGENT_TOOLS
        ],
        skills=_skill_catalog(project_root),
    )
