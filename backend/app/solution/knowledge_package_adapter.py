"""Read-only adapter for the synthetic smart-procurement acceptance package.

The adapter intentionally consumes existing public contracts instead of creating a
parallel requirement or process model. It applies temporal and access controls at
read time, validates source excerpts, and then delegates process/solution building
to the repository's existing deterministic services.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    CustomerContextPackage,
    CustomerOrganizationContext,
    CustomerSourceRecord,
    ReadinessAssessment,
    RequirementBaseline,
    RequirementState,
)
from backend.app.contracts.solution import SolutionBundle
from backend.app.process.process_spec_adapter import ProcessSpecAdapter
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.service import compile_solution


_QUERY_SEPARATOR = re.compile(r"[\s，。；、：:：/]+")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SmartProcurementKnowledgeAdapter:
    """Consume one DATA-M3 project directory without mutating source data."""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root)
        if not self.project_root.is_dir():
            raise ValueError(f"knowledge package project does not exist: {self.project_root}")
        self._manifest = self._load_json("00_原始证据/source_manifest.json")
        self._security = self._load_json("08_权限与时间/security_model.json")
        self._sources = {
            source["source_id"]: source for source in self._manifest["sources"]
        }
        self._users = {user["user_id"]: user for user in self._security["users"]}
        self._acls = {acl["acl_id"]: acl for acl in self._security["acls"]}

    def _load_json(self, relative_path: str) -> dict[str, Any]:
        path = self.project_root / relative_path
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_jsonl(self, relative_path: str) -> list[dict[str, Any]]:
        path = self.project_root / relative_path
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _user(self, user_id: str) -> dict[str, Any]:
        try:
            return self._users[user_id]
        except KeyError as exc:
            raise ValueError(f"unknown knowledge-package user: {user_id}") from exc

    def _is_revoked(self, user_id: str, as_of: str) -> bool:
        instant = _parse_time(as_of)
        return any(
            event["user_id"] == user_id
            and instant >= _parse_time(event["effective_at"])
            for event in self._security["revocation_events"]
        )

    def _can_access(self, record: dict[str, Any], user: dict[str, Any]) -> bool:
        acl = self._acls.get(record["acl_id"])
        if acl is None:
            return False
        roles = set(user["roles"])
        allowed_roles = set(record.get("allowed_roles", acl["allowed_roles"]))
        allowed_departments = set(
            record.get("allowed_departments", acl["allowed_departments"])
        )
        return bool(roles & allowed_roles) and user["department"] in allowed_departments

    @staticmethod
    def _recorded_by(record: dict[str, Any], as_of: str) -> bool:
        instant = _parse_time(as_of)
        return (
            _parse_time(record["occurred_at"]) <= instant
            and _parse_time(record["recorded_at"]) <= instant
        )

    @classmethod
    def _temporally_valid(cls, record: dict[str, Any], as_of: str) -> bool:
        if not cls._recorded_by(record, as_of):
            return False
        instant = _parse_time(as_of)
        if _parse_time(record["valid_from"]) > instant:
            return False
        valid_to = record.get("valid_to")
        return valid_to is None or instant < _parse_time(valid_to)

    def load_customer_context(
        self, user_id: str, as_of: str
    ) -> CustomerContextPackage:
        """Build a contract-valid context from evidence recorded by ``as_of``.

        Historical sources remain in the context after their business-valid period
        ends so Requirement Truth can cite version history. Search, by contrast,
        applies ``valid_from`` and ``valid_to`` to select the applicable fact.
        """

        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"user authorization was revoked by {as_of}: {user_id}")

        source_records: list[CustomerSourceRecord] = []
        for source in self._manifest["sources"]:
            if not self._recorded_by(source, as_of) or not self._can_access(source, user):
                continue
            source_path = self.project_root / source["source_path"]
            content = source_path.read_text(encoding="utf-8")
            source_records.append(
                CustomerSourceRecord(
                    source_id=source["source_id"],
                    project_id=source["project_id"],
                    source_type=source["source_type"],
                    title=source["title"],
                    inline_content=content,
                    document_ref=source["source_path"],
                    occurred_at=source["occurred_at"],
                    author_role="客户或经客户确认的业务角色",
                    locator="全文",
                    metadata={
                        key: source.get(key)
                        for key in (
                            "recorded_at",
                            "valid_from",
                            "valid_to",
                            "supersedes",
                            "source_version",
                            "security_label",
                            "acl_id",
                            "permission_version",
                            "data_classification",
                        )
                    },
                )
            )

        return CustomerContextPackage(
            project_id=self._manifest["project_id"],
            organization=CustomerOrganizationContext(
                organization_name="星瀚汽车制造集团（模拟）",
                industry="汽车制造",
                department="集团采购中心",
                organization_notes=[
                    "synthetic_demo",
                    "晚于2026-08-14的记录属于simulated_future_scenario",
                ],
            ),
            contacts=[],
            sources=source_records,
            requirement_skill_ids=["automotive-procurement-v1"],
        )

    def load_requirement_truth(
        self, context: CustomerContextPackage
    ) -> RequirementState:
        """Load Requirement Truth without retaining evidence unavailable as-of context."""

        payload = self._load_json("02_采购立项与需求/requirement_truth.json")
        available_source_ids = set(context.source_ids)
        payload["source_ids"] = list(context.source_ids)
        payload["items"] = [
            item
            for item in payload["items"]
            if {ref["source_id"] for ref in item["source_refs"]} <= available_source_ids
        ]
        if "SRC-TENDER-007" not in available_source_ids:
            payload["items"].extend(self._historical_requirement_items(available_source_ids))
        if set(self._sources) != available_source_ids:
            payload["gaps"] = []
            payload["conflicts"] = []
        payload["process_observations"] = []
        payload["pain_observations"] = []
        recorded = [
            source.metadata.get("recorded_at")
            for source in context.sources
            if source.metadata.get("recorded_at")
        ]
        payload["updated_at"] = max(recorded) if recorded else payload.get("created_at")
        state = RequirementState.model_validate(payload)
        if state.project_id != context.project_id:
            raise ValueError("context and Requirement Truth project_id must match")
        return state

    @staticmethod
    def _historical_requirement_items(
        available_source_ids: set[str],
    ) -> list[dict[str, Any]]:
        if "SRC-TENDER-005" in available_source_ids:
            source_id = "SRC-TENDER-005"
            version = "V2"
            facts = (
                ("ext:automotive:annual_quantity", "历史有效年需求量", "12,000套", "年需求量调整为12,000套"),
                ("time", "历史有效SOP日期", "2027-03-15进入SOP", "SOP日期提前到2027-03-15"),
                ("budget", "历史有效单套预算", "单套预算上限105,000元", "单套预算上限同步收紧到105,000元"),
            )
        elif "SRC-TENDER-002" in available_source_ids:
            source_id = "SRC-TENDER-002"
            version = "V1"
            facts = (
                ("ext:automotive:annual_quantity", "历史有效年需求量", "10,000套", "第一版按年需求10,000套磷酸铁锂动力电池包测算"),
                ("time", "历史有效SOP日期", "2027-04-01进入SOP", "目标SOP日期是2027-04-01"),
                ("budget", "历史有效单套预算", "单套预算上限108,000元", "单套预算先按108,000元上限估算"),
            )
        else:
            return []
        return [
            {
                "requirement_id": f"REQ-TRUTH-ASOF-{version}-{index:02d}",
                "category": category,
                "subject": subject,
                "value": value,
                "parameters": {"historical_version": version},
                "provenance": "customer_raw",
                "status": "confirmed",
                "confirmation_level": "customer",
                "confidence": 0.99,
                "source_refs": [
                    {"source_id": source_id, "locator": "正文", "excerpt": excerpt}
                ],
                "supersedes_requirement_ids": [],
            }
            for index, (category, subject, value, excerpt) in enumerate(facts, 1)
        ]

    def validate_truth_evidence(
        self, context: CustomerContextPackage, state: RequirementState
    ) -> list[str]:
        """Return deterministic evidence-closure errors; an empty list is valid."""

        errors: list[str] = []
        context_by_id = {source.source_id: source for source in context.sources}
        for item in state.items:
            for ref in item.source_refs:
                source = context_by_id.get(ref.source_id)
                if source is None:
                    errors.append(
                        f"{item.requirement_id}: source unavailable in context: {ref.source_id}"
                    )
                    continue
                haystack = source.inline_content or ""
                if ref.excerpt not in haystack:
                    errors.append(
                        f"{item.requirement_id}: excerpt not found in source: {ref.source_id}"
                    )
        return errors

    @staticmethod
    def _query_score(query: str, chunk: dict[str, Any]) -> int:
        terms = {term for term in _QUERY_SEPARATOR.split(query) if term}
        for keyword in chunk.get("keywords", []):
            if keyword and keyword in query:
                terms.add(keyword)
        haystack = " ".join(
            [chunk.get("title", ""), chunk.get("content", ""), *chunk.get("keywords", [])]
        )
        score = sum(2 for term in terms if term in haystack)
        score += sum(1 for keyword in chunk.get("keywords", []) if keyword in query)
        return score

    def _masked_fields(
        self, chunk: dict[str, Any], user: dict[str, Any]
    ) -> list[str]:
        masking = chunk.get("field_masking", {})
        fields: set[str] = set()
        for role in user["roles"]:
            fields.update(masking.get(role, []))
        return sorted(fields)

    def search(self, query: str, user_id: str, as_of: str) -> list[dict[str, Any]]:
        """Search temporally valid RAG chunks after ACL and revocation checks."""

        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            return []

        results: list[tuple[int, dict[str, Any]]] = []
        for chunk in self._load_jsonl("10_RAG/golden_chunks.jsonl"):
            if not self._temporally_valid(chunk, as_of):
                continue
            if not self._can_access(chunk, user):
                continue
            score = self._query_score(query, chunk)
            if score <= 0:
                continue
            masked_fields = self._masked_fields(chunk, user)
            fields = {
                key: value
                for key, value in chunk.get("fields", {}).items()
                if key not in masked_fields
            }
            result = {
                "chunk_id": chunk["chunk_id"],
                "source_id": chunk["source_id"],
                "source_path": chunk["source_path"],
                "title": chunk["title"],
                "content": chunk["content"],
                "source_version": chunk["source_version"],
                "occurred_at": chunk["occurred_at"],
                "recorded_at": chunk["recorded_at"],
                "valid_from": chunk["valid_from"],
                "valid_to": chunk["valid_to"],
                "permission_version": chunk["permission_version"],
                "masked_fields": masked_fields,
                "fields": fields,
            }
            results.append((score, result))
        results.sort(
            key=lambda item: (
                -item[0],
                -_parse_time(item[1]["valid_from"]).timestamp(),
                item[1]["chunk_id"],
            )
        )
        return [result for _, result in results]

    def _skill_root(self) -> Path:
        for parent in (self.project_root, *self.project_root.parents):
            candidate = parent / "data" / "requirement_skills"
            if candidate.is_dir():
                return candidate
        raise ValueError("data/requirement_skills could not be located from project root")

    def build_process_spec(self, state: RequirementState) -> ProcessSpec:
        """Adapt reviewed customer truth through the repository's ProcessSpec adapter."""

        confirmed = [
            item
            for item in state.items
            if item.status == "confirmed" and item.confirmation_level == "customer"
        ]
        baseline = RequirementBaseline(
            baseline_id="BASELINE-PRJ-TENDER-001-V3",
            project_id=state.project_id,
            baseline_version=3,
            source_state_version=state.state_version,
            confirmed_items=confirmed,
            non_blocking_gaps=list(state.gaps),
            assumptions=[],
            confirmed_by="星瀚汽车跨部门基线复核组（模拟）",
            confirmation_summary="V3需求及九阶段智能招采验收范围已由客户侧逐项确认。",
        )
        readiness = ReadinessAssessment(
            stage="CONFIRMED_READY",
            completeness_score=96.0,
            blocking_gap_ids=[],
            non_blocking_gap_ids=[gap.gap_id for gap in state.gaps],
            open_conflict_ids=[],
            can_generate_preliminary_solution=True,
            can_generate_formal_solution=True,
            reasons=["所有正式必需项已获得客户确认；保留两项非阻断未决事项。"],
        )
        skill = RequirementSkillLoader(self._skill_root()).resolve(
            state.selected_skill_id or "automotive-procurement-v1"
        )
        return ProcessSpecAdapter().adapt(
            baseline=baseline,
            state=state,
            skill=skill,
            readiness=readiness,
            outstanding_questions=[],
        )

    @staticmethod
    def compile_solution_bundle(process: ProcessSpec) -> SolutionBundle:
        """Compile three deterministic plans through the existing solution service."""

        return compile_solution(process)
