"""SQLite-backed project history for the private Internal Console."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from backend.app.contracts.common import StrictModel
from backend.app.solution.workspace_database import (
    WorkspaceSQLite,
    deserialize,
    serialize,
)


GOLDEN_SOURCES = {
    "meeting": (
        "客户为汽车制造企业，项目由采购中心负责。当前流程由采购专员接收招标文件，"
        "随后采购专员依据审查规则审查招标文件并定位风险。人工审查周期长且合规风险定位慢。"
    ),
    "email": "项目目标是缩短招标文件编制与审查周期，降低合规风险。现有系统包括OA。",
    "document": (
        "可用材料包括历史招标文件、企业采购制度和审查规则。数据不得出企业私域。"
        "审批规则为超过50万元必须人工审批。目标指标包括processing_time、manual_steps和risk_findings。"
    ),
    "sales": "客户希望先验证汽车采购招标文件审查场景。",
}


class InternalConsoleSources(StrictModel):
    meeting: str = Field(default="", max_length=2_000_000)
    email: str = Field(default="", max_length=2_000_000)
    document: str = Field(default="", max_length=2_000_000)
    sales: str = Field(default="", max_length=2_000_000)


class InternalConsoleProjectCreateRequest(StrictModel):
    sources: InternalConsoleSources
    uploaded_files: list[str] = Field(default_factory=list, max_length=100)


class InternalConsoleProjectSnapshotRequest(StrictModel):
    snapshot: dict[str, Any]


class InternalConsoleProjectRecord(StrictModel):
    sequence: int = Field(ge=1)
    project_id: str
    title: str
    kind: Literal["demo", "analysis"]
    created_at: str
    updated_at: str
    snapshot: dict[str, Any]


class InternalConsoleProjectListResponse(StrictModel):
    projects: list[InternalConsoleProjectRecord]


def _initial_snapshot(
    project_id: str,
    sources: InternalConsoleSources | dict[str, str],
    uploaded_files: list[str],
) -> dict[str, Any]:
    source_payload = (
        sources.model_dump()
        if isinstance(sources, InternalConsoleSources)
        else dict(sources)
    )
    return {
        "projectId": project_id,
        "sources": source_payload,
        "uploadedFiles": list(uploaded_files),
    }


class InternalConsoleProjectRepository(WorkspaceSQLite):
    """Persists ordered console projects and their complete UI snapshots."""

    _DEMO_ID = "internal-console-demo"

    def __init__(self, path: Path | str) -> None:
        super().__init__(path)
        self._ensure_demo()

    @staticmethod
    def _record(row) -> InternalConsoleProjectRecord:
        return InternalConsoleProjectRecord(
            sequence=int(row["sequence"]),
            project_id=str(row["project_id"]),
            title=str(row["title"]),
            kind=str(row["kind"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            snapshot=deserialize(row["snapshot_json"]),
        )

    def _ensure_demo(self) -> None:
        snapshot = _initial_snapshot(self._DEMO_ID, GOLDEN_SOURCES, [])
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO internal_console_projects "
                "(sequence, project_id, title, kind, created_at, updated_at, snapshot_json) "
                "VALUES (1, ?, '汽车采购示例', 'demo', "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?)",
                (self._DEMO_ID, serialize(snapshot)),
            )

    def list_projects(self) -> list[InternalConsoleProjectRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, project_id, title, kind, created_at, updated_at, "
                "snapshot_json FROM internal_console_projects ORDER BY sequence"
            ).fetchall()
        return [self._record(row) for row in rows]

    def get_project(self, project_id: str) -> InternalConsoleProjectRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT sequence, project_id, title, kind, created_at, updated_at, "
                "snapshot_json FROM internal_console_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Internal Console project does not exist")
        return self._record(row)

    def create_project(
        self,
        *,
        sources: InternalConsoleSources | dict[str, str],
        uploaded_files: list[str],
    ) -> InternalConsoleProjectRecord:
        validated_sources = InternalConsoleSources.model_validate(sources)
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                "FROM internal_console_projects"
            ).fetchone()
            sequence = int(row["next_sequence"])
            project_id = f"internal-console-{sequence:04d}"
            title = f"需求分析 {sequence}"
            snapshot = _initial_snapshot(project_id, validated_sources, uploaded_files)
            connection.execute(
                "INSERT INTO internal_console_projects "
                "(sequence, project_id, title, kind, created_at, updated_at, snapshot_json) "
                "VALUES (?, ?, ?, 'analysis', "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?)",
                (sequence, project_id, title, serialize(snapshot)),
            )
        return self.get_project(project_id)

    def save_snapshot(
        self, project_id: str, snapshot: dict[str, Any]
    ) -> InternalConsoleProjectRecord:
        normalized = dict(snapshot)
        normalized["projectId"] = project_id
        with self._lock, self.connect() as connection:
            existing = connection.execute(
                "SELECT kind FROM internal_console_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if existing is None:
                raise FileNotFoundError("Internal Console project does not exist")
            if existing["kind"] == "demo":
                raise PermissionError("Internal Console demo is read-only")
            cursor = connection.execute(
                "UPDATE internal_console_projects SET snapshot_json = ?, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                "WHERE project_id = ?",
                (serialize(normalized), project_id),
            )
        if cursor.rowcount != 1:
            raise FileNotFoundError("Internal Console project does not exist")
        return self.get_project(project_id)
