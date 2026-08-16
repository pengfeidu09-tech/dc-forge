"""Shared SQLite persistence for runtime business records."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

from backend.app.contracts.requirement_intelligence import (
    QuestionHistoryEntry,
    RequirementBaseline,
    RequirementConfirmationRecord,
    RequirementDiff,
    RequirementState,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS requirement_states (
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, version)
);
CREATE TABLE IF NOT EXISTS requirement_baselines (
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, version)
);
CREATE TABLE IF NOT EXISTS requirement_confirmations (
    project_id TEXT NOT NULL,
    confirmation_id TEXT NOT NULL,
    source_state_version INTEGER NOT NULL,
    result_state_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, confirmation_id)
);
CREATE TABLE IF NOT EXISTS requirement_diffs (
    project_id TEXT NOT NULL,
    previous_baseline_id TEXT NOT NULL,
    current_baseline_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, previous_baseline_id, current_baseline_id)
);
CREATE TABLE IF NOT EXISTS requirement_question_history (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    target_category TEXT NOT NULL,
    asked_state_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    answer_source_ids_json TEXT NOT NULL,
    UNIQUE (project_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_requirement_question_status
    ON requirement_question_history (project_id, status, sequence);
CREATE TABLE IF NOT EXISTS feishu_event_claims (
    event_id TEXT PRIMARY KEY,
    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS customer_projects (
    project_id TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feishu_chat_sessions (
    session_key TEXT PRIMARY KEY,
    tenant_key TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_messages (
    project_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, record_id)
);
CREATE TABLE IF NOT EXISTS customer_access (
    project_id TEXT PRIMARY KEY,
    access_id TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_publications (
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (project_id, version)
);
CREATE TABLE IF NOT EXISTS presales_projects (
    project_id TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
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


def serialize(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("database record must contain a JSON object")
    return payload


class WorkspaceSQLite:
    def __init__(self, path: Path | str) -> None:
        self.database_path = Path(path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self.connect() as connection:
            connection.executescript(_SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


class SqliteFeishuEventClaimStore(WorkspaceSQLite):
    """Atomically claims Feishu events across bot processes."""

    def claim(self, event_id: str) -> bool:
        normalized = event_id.strip()
        if not normalized:
            raise ValueError("event_id must not be blank")
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO feishu_event_claims (event_id) VALUES (?)",
                (normalized,),
            )
        return cursor.rowcount == 1


class SqliteRequirementRepository(WorkspaceSQLite):
    """Immutable Requirement Intelligence records stored in the workspace DB."""

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("project_id must not be blank")

    def list_versions(self, project_id: str) -> list[int]:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT version FROM requirement_states "
                "WHERE project_id = ? ORDER BY version",
                (project_id,),
            ).fetchall()
        return [int(row["version"]) for row in rows]

    def list_project_ids(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT project_id FROM requirement_states "
                "ORDER BY project_id"
            ).fetchall()
        return [str(row["project_id"]) for row in rows]

    def record_question(
        self,
        *,
        project_id: str,
        question_id: str,
        question_text: str,
        target_category: str,
        asked_state_version: int,
    ) -> None:
        self._validate_project_id(project_id)
        if not question_id.strip() or not question_text.strip():
            raise ValueError("question identity and text must not be blank")
        if asked_state_version < 1:
            raise ValueError("asked_state_version must be positive")
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO requirement_question_history "
                "(project_id, question_id, question_text, target_category, "
                "asked_state_version, status, answer_source_ids_json) "
                "VALUES (?, ?, ?, ?, ?, 'asked', '[]')",
                (
                    project_id,
                    question_id,
                    question_text,
                    target_category,
                    asked_state_version,
                ),
            )

    def answer_latest_question(self, project_id: str, source_id: str) -> bool:
        self._validate_project_id(project_id)
        if not source_id.strip():
            raise ValueError("source_id must not be blank")
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT sequence, answer_source_ids_json "
                "FROM requirement_question_history "
                "WHERE project_id = ? AND status = 'asked' "
                "ORDER BY sequence DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if row is None:
                return False
            source_ids = json.loads(row["answer_source_ids_json"])
            if source_id not in source_ids:
                source_ids.append(source_id)
            connection.execute(
                "UPDATE requirement_question_history "
                "SET status = 'answered', answer_source_ids_json = ? "
                "WHERE sequence = ?",
                (json.dumps(source_ids, ensure_ascii=False), row["sequence"]),
            )
        return True

    def list_question_history(self, project_id: str) -> list[QuestionHistoryEntry]:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT question_id, asked_state_version, status, "
                "answer_source_ids_json FROM requirement_question_history "
                "WHERE project_id = ? ORDER BY sequence",
                (project_id,),
            ).fetchall()
        return [
            QuestionHistoryEntry(
                question_id=row["question_id"],
                asked_state_version=row["asked_state_version"],
                status=row["status"],
                answer_source_ids=json.loads(row["answer_source_ids_json"]),
            )
            for row in rows
        ]

    def latest_question_context(
        self, project_id: str, *, status: str = "asked"
    ) -> dict[str, str] | None:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT question_id, question_text, target_category, status "
                "FROM requirement_question_history "
                "WHERE project_id = ? AND status = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (project_id, status),
            ).fetchone()
        if row is None:
            return None
        return {
            "question_id": str(row["question_id"]),
            "question": str(row["question_text"]),
            "topic": str(row["target_category"]),
            "status": str(row["status"]),
        }

    def save_state(self, state: RequirementState) -> None:
        try:
            with self._lock, self.connect() as connection:
                connection.execute(
                    "INSERT INTO requirement_states "
                    "(project_id, version, payload_json) VALUES (?, ?, ?)",
                    (
                        state.project_id,
                        state.state_version,
                        serialize(state.model_dump(mode="json")),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise FileExistsError(
                "RequirementState version already exists: "
                f"{state.project_id}/{state.state_version}"
            ) from error

    def load_state(
        self, project_id: str, version: int | None = None
    ) -> RequirementState | None:
        self._validate_project_id(project_id)
        query = "SELECT version, payload_json FROM requirement_states WHERE project_id = ?"
        parameters: tuple[Any, ...] = (project_id,)
        if version is None:
            query += " ORDER BY version DESC LIMIT 1"
        else:
            if version < 1:
                raise ValueError("state version must be positive")
            query += " AND version = ?"
            parameters = (project_id, version)
        with self.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            if version is None:
                return None
            raise FileNotFoundError(
                f"RequirementState version does not exist: {project_id}/{version}"
            )
        state = RequirementState.model_validate(deserialize(row["payload_json"]))
        if state.project_id != project_id or state.state_version != row["version"]:
            raise ValueError("database RequirementState identity mismatch")
        return state

    def list_baseline_versions(self, project_id: str) -> list[int]:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT version FROM requirement_baselines "
                "WHERE project_id = ? ORDER BY version",
                (project_id,),
            ).fetchall()
        return [int(row["version"]) for row in rows]

    def list_baselines(self, project_id: str) -> list[RequirementBaseline]:
        return [
            baseline
            for version in self.list_baseline_versions(project_id)
            if (baseline := self.load_baseline(project_id, version)) is not None
        ]

    def save_baseline(self, baseline: RequirementBaseline) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT MAX(version) AS version FROM requirement_baselines "
                "WHERE project_id = ?",
                (baseline.project_id,),
            ).fetchone()
            expected = int(row["version"] or 0) + 1
            if baseline.baseline_version != expected:
                raise ValueError(f"RequirementBaseline next version must be {expected}")
            try:
                connection.execute(
                    "INSERT INTO requirement_baselines "
                    "(project_id, version, payload_json) VALUES (?, ?, ?)",
                    (
                        baseline.project_id,
                        baseline.baseline_version,
                        serialize(baseline.model_dump(mode="json")),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise FileExistsError(
                    "RequirementBaseline version already exists: "
                    f"{baseline.project_id}/{baseline.baseline_version}"
                ) from error

    def load_baseline(
        self, project_id: str, version: int | None = None
    ) -> RequirementBaseline | None:
        self._validate_project_id(project_id)
        query = (
            "SELECT version, payload_json FROM requirement_baselines "
            "WHERE project_id = ?"
        )
        parameters: tuple[Any, ...] = (project_id,)
        if version is None:
            query += " ORDER BY version DESC LIMIT 1"
        else:
            if version < 1:
                raise ValueError("baseline version must be positive")
            query += " AND version = ?"
            parameters = (project_id, version)
        with self.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        if row is None:
            if version is None:
                return None
            raise FileNotFoundError(
                f"RequirementBaseline version does not exist: {project_id}/{version}"
            )
        baseline = RequirementBaseline.model_validate(deserialize(row["payload_json"]))
        if baseline.project_id != project_id or baseline.baseline_version != row["version"]:
            raise ValueError("database RequirementBaseline identity mismatch")
        return baseline

    def save_confirmation_record(self, record: RequirementConfirmationRecord) -> None:
        try:
            with self._lock, self.connect() as connection:
                connection.execute(
                    "INSERT INTO requirement_confirmations "
                    "(project_id, confirmation_id, source_state_version, "
                    "result_state_version, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        record.project_id,
                        record.confirmation_id,
                        record.source_state_version,
                        record.result_state_version,
                        serialize(record.model_dump(mode="json")),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise FileExistsError(
                f"RequirementConfirmationRecord already exists: {record.confirmation_id}"
            ) from error

    def list_confirmation_records(
        self, project_id: str
    ) -> list[RequirementConfirmationRecord]:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM requirement_confirmations "
                "WHERE project_id = ? ORDER BY source_state_version, "
                "result_state_version, confirmation_id",
                (project_id,),
            ).fetchall()
        return [
            RequirementConfirmationRecord.model_validate(
                deserialize(row["payload_json"])
            )
            for row in rows
        ]

    def save_diff(self, diff: RequirementDiff) -> None:
        try:
            with self._lock, self.connect() as connection:
                connection.execute(
                    "INSERT INTO requirement_diffs "
                    "(project_id, previous_baseline_id, current_baseline_id, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        diff.project_id,
                        diff.previous_baseline_id,
                        diff.current_baseline_id,
                        serialize(diff.model_dump(mode="json")),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise FileExistsError(
                "RequirementDiff pair already exists: "
                f"{diff.previous_baseline_id}/{diff.current_baseline_id}"
            ) from error

    def load_diff(
        self, project_id: str, previous_baseline_id: str, current_baseline_id: str
    ) -> RequirementDiff:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM requirement_diffs WHERE project_id = ? "
                "AND previous_baseline_id = ? AND current_baseline_id = ?",
                (project_id, previous_baseline_id, current_baseline_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(
                "RequirementDiff pair does not exist: "
                f"{previous_baseline_id}/{current_baseline_id}"
            )
        diff = RequirementDiff.model_validate(deserialize(row["payload_json"]))
        if (
            diff.project_id != project_id
            or diff.previous_baseline_id != previous_baseline_id
            or diff.current_baseline_id != current_baseline_id
        ):
            raise ValueError("database RequirementDiff identity mismatch")
        return diff

    def list_diff_pairs(self, project_id: str) -> list[tuple[str, str]]:
        self._validate_project_id(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT previous_baseline_id, current_baseline_id "
                "FROM requirement_diffs WHERE project_id = ? "
                "ORDER BY previous_baseline_id, current_baseline_id",
                (project_id,),
            ).fetchall()
        return [
            (row["previous_baseline_id"], row["current_baseline_id"])
            for row in rows
        ]
