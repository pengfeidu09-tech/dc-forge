"""Evidence-bound private orchestration for R-CHANGE1 formal removals."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import Field, field_validator

from backend.app.contracts.common import StrictModel
from backend.app.contracts.requirement_intelligence import (
    CustomerSourceRecord,
    RequirementBaseline,
    RequirementConfirmation,
    RequirementItem,
    RequirementState,
)
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier


def _non_blank(value: str, field: str) -> str:
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value


def _digest(payload: object) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"removal-audit-{sha256(material.encode('utf-8')).hexdigest()[:16]}"


class RemovalEvidenceBinding(StrictModel):
    source_id: str
    excerpt: str
    locator: str | None = None

    _source_id = field_validator("source_id")(lambda value: _non_blank(value, "source_id"))
    _excerpt = field_validator("excerpt")(lambda value: _non_blank(value, "excerpt"))


class RequirementChangeDecision(StrictModel):
    target_requirement_id: str
    action: Literal["REMOVE", "NOT_APPLICABLE"]
    evidence: RemovalEvidenceBinding
    confirmation_level: Literal["internal", "customer"]
    confirmed_by: str
    note: str | None = None

    _target = field_validator("target_requirement_id")(
        lambda value: _non_blank(value, "target_requirement_id")
    )
    _confirmed_by = field_validator("confirmed_by")(
        lambda value: _non_blank(value, "confirmed_by")
    )


class RequirementChangeAuditRecord(StrictModel):
    audit_id: str
    project_id: str
    target_requirement_id: str
    previous_baseline_id: str
    previous_baseline_version: int = Field(ge=1)
    action: Literal["REMOVE", "NOT_APPLICABLE"]
    evidence: RemovalEvidenceBinding
    confirmation_level: Literal["customer"]
    confirmed_by: str
    source_state_version: int = Field(ge=1)
    result_state_version: int = Field(ge=2)
    confirmation_id: str


class FileRemovalAuditRepository:
    """Append-only private persistence, kept separate from frozen RequirementRepository."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / sha256(project_id.encode("utf-8")).hexdigest()

    def _path(self, record: RequirementChangeAuditRecord) -> Path:
        return self._project_dir(record.project_id) / f"{record.audit_id}.json"

    def save(self, record: RequirementChangeAuditRecord) -> None:
        path = self._path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"formal removal audit already exists: {record.audit_id}")
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def list_records(self, project_id: str) -> list[RequirementChangeAuditRecord]:
        directory = self._project_dir(project_id)
        if not directory.exists():
            return []
        records: list[RequirementChangeAuditRecord] = []
        for path in sorted(directory.glob("removal-audit-*.json"), key=lambda item: item.name):
            try:
                record = RequirementChangeAuditRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid formal removal audit record: {path}") from exc
            if record.project_id != project_id or path.stem != record.audit_id:
                raise ValueError("formal removal audit repository closure failed")
            records.append(record)
        return sorted(records, key=lambda item: (item.source_state_version, item.audit_id))


@dataclass(frozen=True)
class RemovalResult:
    disposition: Literal["FORMAL_REMOVAL", "REJECTED_CANDIDATE"]
    state: RequirementState
    audit_record: RequirementChangeAuditRecord | None


class FormalRemovalService:
    """Lowers validated private actions to the existing confirmation primitive."""

    def __init__(self, audit_repository: FileRemovalAuditRepository) -> None:
        self._audit_repository = audit_repository

    def reject_candidate(
        self, state: RequirementState, target_requirement_id: str, *, confirmed_by: str
    ) -> RemovalResult:
        item = self._require_item(state, target_requirement_id)
        if item.status in {"confirmed", "rejected", "superseded"} or item.confirmation_level == "customer":
            raise ValueError("REJECTED_CANDIDATE requires an active non-baseline candidate")
        confirmation = RequirementConfirmation(
            project_id=state.project_id,
            state_version=state.state_version,
            confirmation_level="internal",
            rejected_requirement_ids=[target_requirement_id],
            confirmed_by=confirmed_by,
            note="R-CHANGE1 candidate rejection",
        )
        result, _, _ = RequirementConfirmationApplier().apply(state, confirmation)
        return RemovalResult("REJECTED_CANDIDATE", result, None)

    def list_formal_removals(
        self,
        previous_baseline: RequirementBaseline,
        state: RequirementState,
        feedback_sources: list[CustomerSourceRecord],
    ) -> list[RequirementChangeDecision]:
        """No explicit human decision means no removal, regardless of source wording."""
        self._validate_context(previous_baseline, state, feedback_sources)
        return []

    def apply(
        self,
        previous_baseline: RequirementBaseline,
        state: RequirementState,
        feedback_sources: list[CustomerSourceRecord],
        decision: RequirementChangeDecision,
    ) -> RemovalResult:
        self._validate_context(previous_baseline, state, feedback_sources)
        target = self._require_item(state, decision.target_requirement_id)
        baseline_ids = {item.requirement_id for item in previous_baseline.confirmed_items}
        if decision.target_requirement_id not in baseline_ids:
            raise ValueError("formal removal target must belong to previous formal Baseline")
        if target.status != "confirmed" or target.confirmation_level != "customer":
            raise ValueError("formal removal target must be active customer-confirmed truth")
        if decision.confirmation_level != "customer":
            raise ValueError("formal removal requires customer confirmation")

        source = next((source for source in feedback_sources if source.source_id == decision.evidence.source_id), None)
        if source is None or source.source_id not in state.source_ids:
            raise ValueError("formal removal evidence must belong to the new feedback source set")
        if not self._excerpt_is_closed(source, decision.evidence.excerpt):
            raise ValueError("formal removal evidence excerpt must close over its feedback source")

        confirmation = RequirementConfirmation(
            project_id=state.project_id,
            state_version=state.state_version,
            confirmation_level="customer",
            rejected_requirement_ids=[decision.target_requirement_id],
            confirmed_by=decision.confirmed_by,
            note=decision.note or f"R-CHANGE1 {decision.action}",
        )
        result, _, confirmation_record = RequirementConfirmationApplier().apply(state, confirmation)
        payload = {
            "project_id": state.project_id,
            "target_requirement_id": decision.target_requirement_id,
            "previous_baseline_id": previous_baseline.baseline_id,
            "previous_baseline_version": previous_baseline.baseline_version,
            "action": decision.action,
            "evidence": decision.evidence.model_dump(mode="json"),
            "source_state_version": state.state_version,
            "result_state_version": result.state_version,
            "confirmation_id": confirmation_record.confirmation_id,
        }
        audit = RequirementChangeAuditRecord(
            audit_id=_digest(payload),
            project_id=state.project_id,
            target_requirement_id=decision.target_requirement_id,
            previous_baseline_id=previous_baseline.baseline_id,
            previous_baseline_version=previous_baseline.baseline_version,
            action=decision.action,
            evidence=decision.evidence,
            confirmation_level="customer",
            confirmed_by=decision.confirmed_by,
            source_state_version=state.state_version,
            result_state_version=result.state_version,
            confirmation_id=confirmation_record.confirmation_id,
        )
        self._audit_repository.save(audit)
        return RemovalResult("FORMAL_REMOVAL", result, audit)

    @staticmethod
    def _require_item(state: RequirementState, requirement_id: str) -> RequirementItem:
        item = next((item for item in state.items if item.requirement_id == requirement_id), None)
        if item is None:
            raise ValueError(f"unknown requirement_id: {requirement_id}")
        return item

    @staticmethod
    def _validate_context(
        previous_baseline: RequirementBaseline,
        state: RequirementState,
        feedback_sources: list[CustomerSourceRecord],
    ) -> None:
        if previous_baseline.project_id != state.project_id:
            raise ValueError("previous formal Baseline project_id must match RequirementState")
        source_ids = [source.source_id for source in feedback_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("new feedback source IDs must be unique")
        if any(source.project_id != state.project_id for source in feedback_sources):
            raise ValueError("new feedback source project_id must match RequirementState")

    @staticmethod
    def _excerpt_is_closed(source: CustomerSourceRecord, excerpt: str) -> bool:
        texts = [source.inline_content or "", *(chunk.text for chunk in source.chunks)]
        return any(excerpt in text for text in texts)
