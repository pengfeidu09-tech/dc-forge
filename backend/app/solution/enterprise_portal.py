"""Unified read-only service for the enterprise procurement portal and MCP tools."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from backend.app.solution.authoritative_knowledge import (
    AuthoritativeKnowledgeCatalog,
)
from backend.app.solution.knowledge_package_adapter import (
    SmartProcurementKnowledgeAdapter,
)


class EnterpriseKnowledgeService:
    """Expose the curated knowledge package through one governed service boundary."""

    def __init__(self, repository_root: Path | str) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.package_root = (
            self.repository_root / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
        )
        self.projects_root = self.package_root / "03_客户项目全过程库"
        self.tender_root = self.projects_root / "星瀚汽车动力电池智能招采项目"
        if not self.tender_root.is_dir():
            raise ValueError(f"DATA-M3 project is missing: {self.tender_root}")
        self.adapter = SmartProcurementKnowledgeAdapter(self.tender_root)
        self.authoritative_catalog = AuthoritativeKnowledgeCatalog(self.package_root)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    def _normalize_time(value: str, *, end_of_day: bool = False) -> str:
        normalized = value.strip().replace(" ", "T")
        if len(normalized) == 10:
            normalized += "T23:59:59" if end_of_day else "T00:00:00"
        elif len(normalized) == 16:
            normalized += ":00"
        if normalized[-6:-5] not in {"+", "-"} and not normalized.endswith("Z"):
            normalized += "+08:00"
        return normalized

    @classmethod
    def _at_or_before(cls, value: str, as_of: str) -> bool:
        return datetime.fromisoformat(cls._normalize_time(value)) <= datetime.fromisoformat(
            cls._normalize_time(as_of)
        )

    @classmethod
    def _date_at_or_before(cls, value: str, as_of: str) -> bool:
        return cls._at_or_before(cls._normalize_time(value, end_of_day=True), as_of)

    @staticmethod
    def _query_score(query: str, *values: str) -> int:
        compact_query = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", query).casefold()
        haystack = " ".join(values).casefold()
        compact_haystack = re.sub(
            r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", haystack
        )
        if not compact_query:
            return 0
        score = 30 if compact_query in compact_haystack else 0
        terms = {
            term.casefold()
            for term in re.split(r"[\s，。；、：:！？?/.]+", query)
            if len(term.strip()) >= 2
        }
        score += sum(8 for term in terms if term in haystack)
        ngrams = {
            compact_query[index : index + size]
            for size in (2, 3, 4)
            for index in range(max(0, len(compact_query) - size + 1))
        }
        score += sum(1 for term in ngrams if term in compact_haystack)
        return score

    @staticmethod
    def _search_row(
        chunk: dict[str, Any], *, source_id: str, occurred_at: str
    ) -> dict[str, Any]:
        return {
            "chunk_id": chunk["chunk_id"],
            "source_id": source_id,
            "source_path": chunk.get("source_path", ""),
            "title": chunk.get("title") or chunk.get("source_type") or chunk.get("lifecycle_stage", "知识记录"),
            "content": chunk["content"],
            "source_version": chunk.get("requirement_version_id") or "current_as_of",
            "occurred_at": occurred_at,
            "recorded_at": occurred_at,
            "valid_from": occurred_at,
            "valid_to": None,
            "permission_version": "PV-003",
            "masked_fields": [],
            "fields": {},
        }

    def _public_capability_search(
        self, *, query: str, limit: int
    ) -> list[dict[str, Any]]:
        documents = (
            (
                "CAP-AI-PROCESS",
                self.package_root / "01_公司能力知识库/AI_Process能力.md",
            ),
            (
                "CAP-SMART-PROCUREMENT",
                self.package_root / "01_公司能力知识库/智能招采能力.md",
            ),
            (
                "SOL-AUTOMOTIVE-PROCUREMENT",
                self.package_root / "02_行业解决方案库/汽车采购解决方案.md",
            ),
        )
        ranked: list[tuple[int, dict[str, Any]]] = []
        for source_id, path in documents:
            title = path.stem
            chunk_index = 0
            for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
                content = block.strip()
                if not content:
                    continue
                if content.startswith("#") and "\n" not in content:
                    title = content.lstrip("# ").strip() or title
                    continue
                lines = content.splitlines()
                if lines[0].startswith("#"):
                    title = lines[0].lstrip("# ").strip() or title
                    content = "\n".join(lines[1:]).strip()
                if not content:
                    continue
                chunk_index += 1
                score = self._query_score(query, title, content, path.stem)
                if not score:
                    continue
                ranked.append(
                    (
                        score,
                        {
                            "chunk_id": f"{source_id}-{chunk_index:03d}",
                            "source_id": source_id,
                            "source_path": str(path.relative_to(self.package_root)),
                            "title": title,
                            "content": content,
                            "source_version": "current",
                            "occurred_at": None,
                            "recorded_at": None,
                            "valid_from": None,
                            "valid_to": None,
                            "permission_version": "public-curated-v1",
                            "masked_fields": [],
                            "fields": {
                                "is_real_business_result": False,
                                "human_review_required_for_high_impact_decisions": True,
                            },
                        },
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1]["source_id"], item[1]["chunk_id"]))
        return [row for _, row in ranked[:limit]]

    def _knowledge_management_search(
        self, *, query: str, as_of: str, limit: int
    ) -> list[dict[str, Any]]:
        root = self.projects_root / "华东新程汽车项目"
        master = self._read_json(root / "project_master.json")
        requirements = self._read_json(root / "02_需求阶段/requirements.json")
        timeline = self._read_json(root / "04_沟通记录/沟通时间线.json")
        source_times: dict[str, str] = {
            "PRJ-KM-001": "2026-08-18T09:30:00+08:00",
            "DOC-CUSTOMER-001": "2026-08-18T09:30:00+08:00",
        }
        for milestone in master["milestones"]:
            source_times[milestone["meeting_id"]] = self._normalize_time(
                milestone["date"]
            )
        for requirement in requirements["requirements"]:
            source_times[requirement["requirement_id"]] = min(
                version["created_at"] for version in requirement["versions"]
            )
            for version in requirement["versions"]:
                source_times[version["requirement_version_id"]] = version["created_at"]
        for event in timeline:
            occurred_at = self._normalize_time(event["date"])
            for object_id in [*event.get("source_ids", []), *event.get("related", [])]:
                if object_id not in source_times or self._at_or_before(
                    occurred_at, source_times[object_id]
                ):
                    source_times[object_id] = occurred_at

        rows: list[tuple[int, dict[str, Any]]] = []
        for chunk in self._read_jsonl(
            self.package_root / "04_RAG知识库/knowledge_chunks.jsonl"
        ):
            if chunk.get("project_id") != "PRJ-KM-001":
                continue
            related_times = [
                source_times[object_id]
                for object_id in [chunk["source_id"], *chunk.get("related", [])]
                if object_id in source_times
            ]
            occurred_at = max(related_times) if related_times else "2026-08-18T09:30:00+08:00"
            if not self._at_or_before(occurred_at, as_of):
                continue
            score = self._query_score(
                query,
                chunk.get("content", ""),
                chunk.get("source_id", ""),
                " ".join(chunk.get("related", [])),
                " ".join(chunk.get("tags", [])),
            )
            if score:
                rows.append(
                    (score, self._search_row(chunk, source_id=chunk["source_id"], occurred_at=occurred_at))
                )
        for chunk in self._read_jsonl(
            self.package_root / "04_RAG知识库/communication_chunks.jsonl"
        ):
            if chunk.get("project_id") != "PRJ-KM-001":
                continue
            occurred_at = self._normalize_time(chunk["occurred_at"])
            if not self._at_or_before(occurred_at, as_of):
                continue
            score = self._query_score(
                query,
                chunk["content"],
                chunk["source_id"],
                " ".join(chunk.get("related", [])),
            )
            if score:
                rows.append(
                    (score, self._search_row(chunk, source_id=chunk["source_id"], occurred_at=occurred_at))
                )
        rows.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return [row for _, row in rows[:limit]]

    def _vehicle_search(
        self, *, query: str, user_id: str, as_of: str, limit: int
    ) -> list[dict[str, Any]]:
        stage_times = {
            "lead": "2026-08-13T09:30:00+08:00",
            "requirement": "2026-08-15T15:30:00+08:00",
            "clarification": "2026-08-15T15:30:00+08:00",
            "opportunity": "2026-08-18T10:00:00+08:00",
            "feasibility": "2026-08-17T17:00:00+08:00",
            "sourcing": "2026-08-21T11:00:00+08:00",
            "solution": "2026-08-22T10:00:00+08:00",
            "quote": "2026-08-27T16:00:00+08:00",
            "negotiation": "2026-08-25T10:00:00+08:00",
            "approval": "2026-08-26T09:30:00+08:00",
            "contract": "2026-08-31T16:00:00+08:00",
            "order": "2026-09-01T10:30:00+08:00",
            "purchase": "2026-09-01T15:30:00+08:00",
            "vehicle": "2026-09-22T23:59:59+08:00",
            "logistics": "2026-09-25T09:00:00+08:00",
            "delivery": "2026-09-27T10:00:00+08:00",
            "acceptance": "2026-09-27T23:59:59+08:00",
            "exception": "2026-09-28T10:40:00+08:00",
            "invoice": "2026-09-29T10:00:00+08:00",
            "cashflow": "2026-10-28T15:00:00+08:00",
            "profit": "2026-10-31T18:00:00+08:00",
            "after_sales": "2026-10-13T16:00:00+08:00",
            "repurchase": "2026-11-03T10:00:00+08:00",
            "review": "2026-11-05T14:00:00+08:00",
        }
        roles = set(self._user(user_id)["roles"])
        financial_stages = {"quote", "contract", "purchase", "invoice", "cashflow", "profit"}
        rows: list[tuple[int, dict[str, Any]]] = []
        for chunk in self._read_jsonl(
            self.package_root / "04_RAG知识库/customer_requirement_lifecycle_chunks.jsonl"
        ):
            stage = chunk["lifecycle_stage"]
            occurred_at = stage_times[stage]
            if not self._at_or_before(occurred_at, as_of):
                continue
            if stage in financial_stages and not (
                {"procurement_owner", "legal_finance"} & roles
            ):
                continue
            score = self._query_score(
                query,
                chunk["content"],
                stage,
                " ".join(chunk.get("source_object_ids", [])),
            )
            if not score:
                continue
            source_id = (
                chunk.get("requirement_version_id")
                if stage in {"requirement", "clarification"}
                else chunk.get("source_object_ids", [chunk["chunk_id"]])[0]
            )
            row = self._search_row(chunk, source_id=source_id, occurred_at=occurred_at)
            row["source_path"] = (
                "03_客户项目全过程库/东辰出行新能源车辆采购项目/"
                f"{stage}"
            )
            rows.append((score, row))
        rows.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return [row for _, row in rows[:limit]]

    def _require_tender_project(self, project_id: str) -> None:
        if project_id != "PRJ-TENDER-001":
            raise ValueError(
                f"project is indexed but does not yet expose the DATA-M3 portal contract: {project_id}"
            )

    def _security(self) -> dict[str, Any]:
        return self._read_json(self.tender_root / "08_权限与时间/security_model.json")

    def _user(self, user_id: str) -> dict[str, Any]:
        for user in self._security()["users"]:
            if user["user_id"] == user_id:
                return user
        raise ValueError(f"unknown portal user: {user_id}")

    def _is_revoked(self, user_id: str, as_of: str) -> bool:
        return any(
            event["user_id"] == user_id
            and self._at_or_before(event["effective_at"], as_of)
            for event in self._security()["revocation_events"]
        )

    def _source_recorded(self, source_id: str, as_of: str) -> bool:
        return self._at_or_before(self.adapter._sources[source_id]["recorded_at"], as_of)

    def _formal_solution_ready(self, as_of: str) -> bool:
        return self._source_recorded("SRC-TENDER-016", as_of)

    def list_projects(self) -> list[dict[str, Any]]:
        seed = self._read_json(self.package_root / "06_DEMO数据/demo_seed.json")
        result: list[dict[str, Any]] = []
        for project in seed["projects"]:
            item = dict(project)
            item.update(
                {
                    "data_classification": "synthetic_demo",
                    "timeline_classification": "simulated_future_scenario",
                    "is_real_business_result": False,
                    "portal_ready": True,
                }
            )
            result.append(item)
        return result

    def _visible_source_ids(self, user_id: str, as_of: str) -> set[str]:
        return set(self.adapter.load_customer_context(user_id, as_of).source_ids)

    def _metrics(self, *, user_id: str, as_of: str) -> dict[str, int]:
        manifest = self._read_json(self.tender_root / "00_原始证据/source_manifest.json")
        truth = self._read_json(
            self.tender_root / "02_采购立项与需求/requirement_truth.json"
        )
        suppliers = self._read_json(
            self.tender_root / "03_供应商画像/supplier_profiles.json"
        )
        reviews = self._read_json(
            self.tender_root / "05_文档生成与审查/review_expectations.json"
        )
        communications = self._read_jsonl(
            self.tender_root / "09_沟通记录/communications.jsonl"
        )
        chunks = self._read_jsonl(self.tender_root / "10_RAG/golden_chunks.jsonl")
        eval_cases = self._read_jsonl(
            self.tender_root / "11_评测集/eval_cases.jsonl"
        )
        visible_source_ids = self._visible_source_ids(user_id, as_of)
        visible_truth = [
            item
            for item in truth["items"]
            if {ref["source_id"] for ref in item["source_refs"]} <= visible_source_ids
        ]
        visible_suppliers = [
            supplier
            for supplier in suppliers["suppliers"]
            if self._at_or_before(supplier["valid_from"], as_of)
        ]
        visible_communications = [
            record
            for record in communications
            if self._at_or_before(record["occurred_at"], as_of)
            and self._at_or_before(record["recorded_at"], as_of)
            and set(record["related"].get("source_ids", [])) <= visible_source_ids
        ]
        visible_chunks = [
            chunk
            for chunk in chunks
            if self._at_or_before(chunk["occurred_at"], as_of)
            and self._at_or_before(chunk["recorded_at"], as_of)
            and chunk["source_id"] in visible_source_ids
        ]
        adversarial = list((self.tender_root / "adversarial").glob("*/scenario.json"))
        return {
            "raw_evidence": len(visible_source_ids),
            "requirement_truth_items": len(visible_truth),
            "suppliers": len(visible_suppliers),
            "document_review_samples": (
                len(reviews["samples"])
                if "SRC-TENDER-024" in visible_source_ids
                else 0
            ),
            "communications": len(visible_communications),
            "rag_chunks": len(visible_chunks),
            "eval_cases": (
                len(eval_cases) if "SRC-TENDER-024" in visible_source_ids else 0
            ),
            "adversarial_scenarios": (
                len(adversarial) if "SRC-TENDER-024" in visible_source_ids else 0
            ),
        }

    def get_project_dashboard(
        self, project_id: str, *, user_id: str, as_of: str
    ) -> dict[str, Any]:
        self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"portal authorization was revoked: {user_id}")
        if project_id == "PRJ-KM-001":
            dashboard = self._knowledge_management_dashboard(user_id=user_id, as_of=as_of)
            authority = self.list_project_sources(
                project_id, user_id=user_id, as_of=as_of, limit=1
            )
            dashboard["authority_sources"] = {
                "total": authority["total"],
                "type_counts": authority["type_counts"],
            }
            return dashboard
        if project_id == "PRJ-AUTO-001":
            dashboard = self._vehicle_procurement_dashboard(user_id=user_id, as_of=as_of)
            authority = self.list_project_sources(
                project_id, user_id=user_id, as_of=as_of, limit=1
            )
            dashboard["authority_sources"] = {
                "total": authority["total"],
                "type_counts": authority["type_counts"],
            }
            return dashboard
        self._require_tender_project(project_id)
        master = self._read_json(self.tender_root / "project_master.json")
        initiation = self._read_json(
            self.tender_root / "02_采购立项与需求/initiation_requirement.json"
        )
        history = self.get_requirement_history(
            project_id,
            "REQ-BAT-001",
            user_id=user_id,
            as_of=as_of,
        )
        suppliers = self.analyze_suppliers(
            project_id, user_id=user_id, as_of=as_of
        )
        reviews = self.get_document_reviews(
            project_id, user_id=user_id, as_of=as_of
        )
        metrics = self._metrics(user_id=user_id, as_of=as_of)
        metrics["document_review_samples"] = len(reviews["samples"])
        formal_source = self.adapter._sources["SRC-TENDER-016"]
        formal_solution_ready = self._formal_solution_ready(as_of)
        solution_role_allowed = bool(
            {"procurement_owner", "legal_finance"} & set(self._user(user_id)["roles"])
        )
        bundle = (
            self.generate_solution_bundle(project_id, user_id=user_id, as_of=as_of)
            if formal_solution_ready and solution_role_allowed
            else None
        )
        if not formal_solution_ready:
            solution_status = "not_ready_as_of"
        elif not solution_role_allowed:
            solution_status = "forbidden_for_role"
        else:
            solution_status = "ready"
        applicable_version = next(
            (
                version
                for version in history["versions"]
                if version["requirement_version_id"] == history["applicable_version_id"]
            ),
            None,
        )
        project_view = {
            key: master[key]
            for key in (
                "project_id",
                "project_name",
                "customer_name",
                "industry",
                "department",
                "procurement_object",
                "annual_quantity",
                "currency",
                "confirmed_requirement_version_id",
            )
        }
        if applicable_version is not None:
            project_view["annual_quantity"] = applicable_version["quantity"]
            project_view["confirmed_requirement_version_id"] = applicable_version[
                "requirement_version_id"
            ]
            project_view["procurement_object"] = (
                f"{applicable_version['quantity']:,}套磷酸铁锂动力电池包采购"
            )
        dashboard = {
            "project": project_view,
            "procurement_stages": self._stages_as_of(master["procurement_stages"], as_of),
            "ai_acceptance_capabilities": master["ai_acceptance_capabilities"],
            "metrics": metrics,
            "requirement_history": history,
            "open_items": (
                initiation["requirement"]["open_items_at_baseline"]
                if self._source_recorded("SRC-TENDER-013", as_of)
                else []
            ),
            "supplier_view": suppliers,
            "document_reviews": reviews,
            "solution_bundle": bundle,
            "solution_status": {
                "status": solution_status,
                "required_source_id": "SRC-TENDER-016",
                "required_recorded_at": formal_source["recorded_at"],
            },
            "viewer": {
                "user_id": user_id,
                "as_of": as_of,
                "permission_version": self._user(user_id)["permission_version"],
                "masked_fields": suppliers["masked_fields"],
            },
            "data_classification": master["data_classification"],
            "timeline_classification": master["timeline_classification"],
            "is_real_business_result": master["is_real_business_result"],
            "disclaimer": master["disclaimer"],
        }
        authority = self.list_project_sources(
            project_id, user_id=user_id, as_of=as_of, limit=1
        )
        dashboard["authority_sources"] = {
            "total": authority["total"],
            "type_counts": authority["type_counts"],
        }
        return dashboard

    def _knowledge_management_dashboard(
        self, *, user_id: str, as_of: str
    ) -> dict[str, Any]:
        self._user(user_id)
        root = self.projects_root / "华东新程汽车项目"
        master = self._read_json(root / "project_master.json")
        requirements = self._read_json(root / "02_需求阶段/requirements.json")
        wechat = self._read_json(root / "04_沟通记录/企业微信项目群.json")
        timeline = self._read_json(root / "04_沟通记录/沟通时间线.json")
        milestones = [
            milestone
            for milestone in master["milestones"]
            if self._date_at_or_before(milestone["date"], as_of)
        ]
        visible_meeting_ids = {milestone["meeting_id"] for milestone in milestones}
        visible_timeline = [
            event for event in timeline if self._date_at_or_before(event["date"], as_of)
        ]
        visible_wechat = [
            thread
            for thread in wechat
            if self._at_or_before(self._normalize_time(thread["time"]), as_of)
        ]
        visible_requirements = []
        for requirement in requirements["requirements"]:
            versions = [
                deepcopy(version)
                for version in requirement["versions"]
                if self._at_or_before(version["created_at"], as_of)
            ]
            if not versions:
                continue
            item = deepcopy(requirement)
            item["versions"] = versions
            visible_requirements.append(item)
        visible_document_ids = {
            related_id
            for event in visible_timeline
            for related_id in event.get("related", [])
            if related_id.startswith("DOC-")
        }
        metrics = {
            "requirements": len(visible_requirements),
            "meetings": len(visible_meeting_ids),
            "documents": len(visible_document_ids),
            "wechat_threads": len(visible_wechat),
            "communication_timeline": len(visible_timeline),
        }
        return {
            "project": {
                "project_id": master["project_id"],
                "project_name": master["project_name"],
                "customer_name": master["customer_name"],
                "industry": "汽车制造",
                "department": "采购数字化与信息化团队",
                "procurement_object": master["project_type"],
                "confirmed_requirement_version_id": "3条独立需求基线",
            },
            "portal_mode": "knowledge_management",
            "procurement_stages": [
                {
                    "code": milestone["stage"],
                    "name": milestone["name"],
                    "status": "recorded_as_of",
                    "date": milestone["date"],
                }
                for milestone in milestones
            ],
            "ai_acceptance_capabilities": master["scope"]["in_scope"],
            "metrics": metrics,
            "requirements": visible_requirements,
            "milestones": milestones,
            "dataset_files": master["dataset_files"],
            "data_classification": master["data_classification"],
            "timeline_classification": master["timeline_classification"],
            "is_real_business_result": master["is_real_business_result"],
            "disclaimer": master["disclaimer"],
            "viewer": {"user_id": user_id, "as_of": as_of, "masked_fields": []},
            "solution_bundle": None,
            "solution_status": {"status": "not_available_for_project_type"},
        }

    def _vehicle_procurement_dashboard(
        self, *, user_id: str, as_of: str
    ) -> dict[str, Any]:
        user = self._user(user_id)
        root = self.projects_root / "东辰出行新能源车辆采购项目"
        master = self._read_json(root / "project_master.json")
        customer = self._read_json(root / "01_客户与需求/customer_requirement.json")
        clarification = self._read_json(
            root / "02_澄清与评估/clarification_and_feasibility.json"
        )
        fulfillment = self._read_json(root / "06_履约交付/fulfillment.json")
        finance = self._read_json(root / "07_财务利润/finance.json")
        after_sales = self._read_json(root / "08_售后复盘/after_sales_review.json")
        roles = set(user["roles"])
        finance_visible = bool({"procurement_owner", "legal_finance"} & roles)
        visible_versions = [
            deepcopy(version)
            for version in customer["requirement"]["versions"]
            if self._at_or_before(version["created_at"], as_of)
        ]
        applicable_version_id = (
            visible_versions[-1]["requirement_version_id"] if visible_versions else None
        )
        visible_shipments = [
            deepcopy(shipment)
            for shipment in fulfillment["shipments"]
            if self._at_or_before(shipment["loaded_at"], as_of)
        ]
        for shipment in visible_shipments:
            if not self._at_or_before(shipment["departed_at"], as_of):
                shipment["departed_at"] = None
                shipment["arrived_at"] = None
                shipment["status"] = "loaded_as_of"
            elif not self._at_or_before(shipment["arrived_at"], as_of):
                shipment["arrived_at"] = None
                shipment["status"] = "in_transit_as_of"
        visible_deliveries = [
            deepcopy(delivery)
            for delivery in fulfillment["delivery_batches"]
            if self._at_or_before(delivery["delivered_at"], as_of)
        ]
        visible_acceptances = [
            deepcopy(acceptance)
            for acceptance in fulfillment["acceptances"]
            if self._date_at_or_before(acceptance["inspection_date"], as_of)
        ]
        visible_exceptions = [
            deepcopy(exception)
            for exception in fulfillment["exceptions"]
            if self._date_at_or_before(
                next(
                    acceptance["inspection_date"]
                    for acceptance in fulfillment["acceptances"]
                    if acceptance["acceptance_id"] == exception["acceptance_id"]
                ),
                as_of,
            )
        ]
        for exception in visible_exceptions:
            if not self._at_or_before(exception["resolved_at"], as_of):
                exception["resolved_at"] = None
                exception["reinspection"] = None
                exception["status"] = "open_as_of"
        open_exception_ids = {
            exception["exception_id"]
            for exception in visible_exceptions
            if exception["status"] == "open_as_of"
        }
        for acceptance in visible_acceptances:
            if open_exception_ids & set(acceptance["exception_ids"]):
                acceptance["accepted_quantity_final"] = acceptance[
                    "initial_passed_quantity"
                ]
                acceptance["final_result"] = "pending_reinspection_as_of"
        visible_vehicles = [
            deepcopy(vehicle)
            for vehicle in fulfillment["vehicles"]
            if self._date_at_or_before(vehicle["factory_release_date"], as_of)
        ]
        open_exception_vins = {
            exception["vin"]
            for exception in visible_exceptions
            if exception["status"] == "open_as_of"
        }
        delivered_vins = {
            vin for delivery in visible_deliveries for vin in delivery["vehicle_vins"]
        }
        accepted_vins = {
            vin
            for acceptance in visible_acceptances
            if acceptance["final_result"] != "pending_reinspection_as_of"
            for delivery in visible_deliveries
            if delivery["delivery_batch_id"] == acceptance["delivery_batch_id"]
            for vin in delivery["vehicle_vins"]
        }
        for vehicle in visible_vehicles:
            if vehicle["vin"] in open_exception_vins:
                vehicle["vehicle_status"] = "exception_open_as_of"
            elif vehicle["vin"] in accepted_vins:
                vehicle["vehicle_status"] = "accepted"
            elif vehicle["vin"] in delivered_vins:
                vehicle["vehicle_status"] = "delivered_pending_acceptance_as_of"
            else:
                vehicle["vehicle_status"] = "released_pending_delivery_as_of"
        visible_customer_invoices = [
            invoice
            for invoice in finance["customer_invoices"]
            if self._at_or_before(invoice["issued_at"], as_of)
        ]
        visible_supplier_invoices = [
            invoice
            for invoice in finance["supplier_invoices"]
            if self._at_or_before(invoice["issued_at"], as_of)
        ]
        visible_receipts = [
            receipt
            for receipt in finance["customer_receipts"]
            if self._at_or_before(receipt["received_at"], as_of)
        ]
        visible_payments = [
            payment
            for payment in finance["supplier_payments"]
            if self._at_or_before(payment["paid_at"], as_of)
        ]
        visible_tickets = [
            ticket
            for ticket in after_sales["after_sales_tickets"]
            if self._at_or_before(ticket["opened_at"], as_of)
        ]
        profit_visible = self._at_or_before(
            finance["profit_calculation"]["calculated_at"], as_of
        )
        stage_times = {
            "lead": "2026-08-13T09:30:00+08:00",
            "requirement": "2026-08-14T14:00:00+08:00",
            "clarification": "2026-08-15T15:30:00+08:00",
            "opportunity": "2026-08-18T10:00:00+08:00",
            "feasibility": "2026-08-17T17:00:00+08:00",
            "sourcing": "2026-08-21T11:00:00+08:00",
            "solution": "2026-08-22T10:00:00+08:00",
            "quote": "2026-08-27T16:00:00+08:00",
            "negotiation": "2026-08-25T10:00:00+08:00",
            "approval": "2026-08-26T09:30:00+08:00",
            "contract": "2026-08-31T16:00:00+08:00",
            "order": "2026-09-01T10:30:00+08:00",
            "purchase": "2026-09-01T15:30:00+08:00",
            "vehicle": "2026-09-03T23:59:59+08:00",
            "logistics": "2026-09-06T08:00:00+08:00",
            "delivery": "2026-09-08T10:00:00+08:00",
            "acceptance": "2026-09-08T23:59:59+08:00",
            "exception": "2026-09-08T23:59:59+08:00",
            "invoice": "2026-08-31T11:00:00+08:00",
            "cashflow": "2026-08-31T14:30:00+08:00",
            "profit": "2026-10-31T18:00:00+08:00",
            "after_sales": "2026-10-12T09:00:00+08:00",
            "repurchase": "2026-11-03T10:00:00+08:00",
            "review": "2026-11-05T14:00:00+08:00",
        }
        visible_stages = deepcopy(master["lifecycle_stages"])
        for stage in visible_stages:
            if not self._at_or_before(stage_times[stage["code"]], as_of):
                stage["status"] = "not_recorded_as_of"
        visible_finance = None
        if finance_visible and (
            visible_customer_invoices
            or visible_supplier_invoices
            or visible_receipts
            or visible_payments
            or profit_visible
        ):
            visible_finance = deepcopy(finance)
            visible_finance["customer_invoices"] = visible_customer_invoices
            visible_finance["supplier_invoices"] = visible_supplier_invoices
            visible_finance["customer_receipts"] = visible_receipts
            visible_finance["supplier_payments"] = visible_payments
            received_by_receivable: dict[str, int] = {}
            for receipt in visible_receipts:
                received_by_receivable[receipt["receivable_id"]] = (
                    received_by_receivable.get(receipt["receivable_id"], 0)
                    + receipt["amount_cny"]
                )
            for receivable in visible_finance["customer_receivables"]:
                received = received_by_receivable.get(receivable["receivable_id"], 0)
                receivable["received_cny"] = received
                receivable["outstanding_cny"] = receivable["amount_cny"] - received
                if received == receivable["amount_cny"]:
                    receivable["status"] = "settled_as_of"
                elif not self._date_at_or_before(receivable["due_date"], as_of):
                    receivable["status"] = "not_due_as_of"
                elif received:
                    receivable["status"] = "partially_received_as_of"
                else:
                    receivable["status"] = "due_as_of"
            paid_by_payable: dict[str, int] = {}
            for payment in visible_payments:
                paid_by_payable[payment["payable_id"]] = (
                    paid_by_payable.get(payment["payable_id"], 0)
                    + payment["amount_cny"]
                )
            for payable in visible_finance["supplier_payables"]:
                paid = paid_by_payable.get(payable["payable_id"], 0)
                payable["paid_cny"] = paid
                payable["outstanding_cny"] = payable["amount_cny"] - paid
                payable["status"] = (
                    "settled_as_of"
                    if paid == payable["amount_cny"]
                    else "partially_paid_as_of"
                    if paid
                    else "unpaid_as_of"
                )
            if not profit_visible:
                visible_finance["profit_calculation"] = None
        metrics = {
            "requirement_versions": len(visible_versions),
            "vehicles": len(visible_vehicles),
            "shipments": len(visible_shipments),
            "delivery_batches": len(visible_deliveries),
            "acceptances": len(visible_acceptances),
            "exceptions": len(visible_exceptions),
            "customer_invoices": len(visible_customer_invoices),
            "after_sales_cost_records": len(visible_tickets),
        }
        return {
            "project": {
                "project_id": master["project_id"],
                "project_name": master["project_name"],
                "customer_name": customer["customer"]["company_name"],
                "industry": customer["customer"]["industry"],
                "department": "战略采购部与车队运营部",
                "procurement_object": customer["requirement"]["title"],
                "annual_quantity": len(fulfillment["vehicles"]),
                "currency": master["currency"],
                "confirmed_requirement_version_id": master[
                    "confirmed_requirement_version_id"
                ],
            },
            "portal_mode": "vehicle_lifecycle",
            "procurement_stages": visible_stages,
            "ai_acceptance_capabilities": list(master["information_flows"]),
            "metrics": metrics,
            "requirement_history": {
                "requirement_id": master["requirement_id"],
                "versions": visible_versions,
                "applicable_version_id": applicable_version_id,
                "open_items": (
                    clarification["open_items_at_baseline"]
                    if applicable_version_id == master["confirmed_requirement_version_id"]
                    else []
                ),
                "as_of": as_of,
            },
            "vehicles": visible_vehicles,
            "shipments": visible_shipments,
            "delivery_batches": visible_deliveries,
            "acceptances": visible_acceptances,
            "exceptions": visible_exceptions,
            "finance": visible_finance,
            "data_classification": master["data_classification"],
            "timeline_classification": master["timeline_classification"],
            "is_real_business_result": master["is_real_business_result"],
            "disclaimer": master["disclaimer"],
            "viewer": {
                "user_id": user_id,
                "as_of": as_of,
                "masked_fields": [] if finance_visible else ["financial_amounts"],
            },
            "solution_bundle": None,
            "solution_status": {"status": "not_available_for_project_type"},
        }

    def _stages_as_of(
        self, stages: list[dict[str, Any]], as_of: str
    ) -> list[dict[str, Any]]:
        evidence_times = {
            "procurement_budget": "2026-08-19T11:30:00+08:00",
            "procurement_plan": "2026-08-19T15:00:00+08:00",
            "project_initiation": "2026-08-20T18:10:00+08:00",
            "procurement_scheme": "2026-09-25T18:00:00+08:00",
            "procurement_execution": "2026-09-25T18:00:00+08:00",
            "procurement_contract": "2026-10-20T16:00:00+08:00",
            "document_archive": "2026-09-30T17:00:00+08:00",
            "supplier_management": "2026-09-25T18:00:00+08:00",
            "statistics_analysis": "2027-04-15T23:59:59+08:00",
        }
        result = deepcopy(stages)
        for stage in result:
            if not self._at_or_before(evidence_times[stage["code"]], as_of):
                stage["status"] = "not_recorded_as_of"
        return result

    def _source_content_allowed(
        self, project_id: str, record: dict[str, Any], user_id: str
    ) -> bool:
        roles = set(self._user(user_id)["roles"])
        path = record["source_path"]
        if project_id == "PRJ-TENDER-001":
            if any(
                segment in path
                for segment in ("03_供应商画像/", "06_合同履约/", "07_归档统计/")
            ):
                return bool({"procurement_owner", "legal_finance"} & roles)
        if project_id == "PRJ-AUTO-001" and any(
            segment in path
            for segment in ("04_方案商务/", "05_合同订单/", "07_财务利润/")
        ):
            return bool({"procurement_owner", "legal_finance"} & roles)
        return True

    def _visible_authoritative_sources(
        self, project_id: str, *, user_id: str, as_of: str
    ) -> list[dict[str, Any]]:
        self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"source access was revoked: {user_id}")
        visible_tender_ids = (
            self._visible_source_ids(user_id, as_of)
            if project_id == "PRJ-TENDER-001"
            else set()
        )
        records: list[dict[str, Any]] = []
        for record in self.authoritative_catalog.records(project_id):
            recorded_at = record.get("recorded_at")
            if recorded_at and not self._at_or_before(recorded_at, as_of):
                continue
            if (
                project_id == "PRJ-TENDER-001"
                and record.get("_manifest_managed")
                and record["source_id"] not in visible_tender_ids
            ):
                continue
            records.append(record)
        return records

    def list_project_sources(
        self,
        project_id: str,
        *,
        user_id: str,
        as_of: str,
        source_type: str | None = None,
        requirement_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = min(max(limit, 1), 500)
        offset = max(offset, 0)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for record in self._visible_authoritative_sources(
            project_id, user_id=user_id, as_of=as_of
        ):
            if source_type and record["source_type"] != source_type:
                continue
            if requirement_id and not self.authoritative_catalog.matches_requirement(
                record, requirement_id
            ):
                continue
            score = 0
            if query:
                searchable_content = (
                    record.get("_content") or ""
                    if self._source_content_allowed(project_id, record, user_id)
                    else ""
                )
                score = self._query_score(
                    query,
                    record["source_id"],
                    record["title"],
                    record["source_path"],
                    " ".join(record["requirement_ids"]),
                    searchable_content,
                )
                if not score:
                    continue
                if query.strip().casefold() in {
                    record["source_id"].casefold(),
                    record["title"].casefold(),
                }:
                    score += 1000
            ranked.append((score, record))
        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1]["source_type"],
                item[1].get("recorded_at") or "",
                item[1]["source_id"],
            )
        )
        records = [record for _, record in ranked]
        type_counts: dict[str, int] = {}
        for record in records:
            type_counts[record["source_type"]] = type_counts.get(record["source_type"], 0) + 1
        page = records[offset : offset + limit]
        sources: list[dict[str, Any]] = []
        for record in page:
            summary = self.authoritative_catalog.summary(record)
            if not self._source_content_allowed(project_id, record, user_id):
                summary["content_available"] = False
                summary["content_preview"] = ""
                summary["masked_fields"] = ["content"]
            else:
                summary["masked_fields"] = []
            sources.append(summary)
        return {
            "project_id": project_id,
            "authority_root": self.package_root.name,
            "total": len(records),
            "offset": offset,
            "limit": limit,
            "type_counts": dict(sorted(type_counts.items())),
            "sources": sources,
            "as_of": as_of,
            "data_classification": "synthetic_demo",
            "is_real_business_result": False,
        }

    def get_project_source(
        self,
        project_id: str,
        source_id: str,
        *,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        record = next(
            (
                item
                for item in self._visible_authoritative_sources(
                    project_id, user_id=user_id, as_of=as_of
                )
                if item["source_id"] == source_id
            ),
            None,
        )
        if record is None:
            raise ValueError(f"unknown or unavailable authoritative source: {source_id}")
        return self.authoritative_catalog.detail(
            record,
            content_allowed=self._source_content_allowed(project_id, record, user_id),
        )

    def get_requirement_sources(
        self,
        project_id: str,
        requirement_id: str,
        *,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        result = self.list_project_sources(
            project_id,
            user_id=user_id,
            as_of=as_of,
            requirement_id=requirement_id,
            limit=500,
        )
        result["requirement_id"] = requirement_id
        return result

    def _authoritative_search_rows(
        self,
        project_id: str,
        *,
        query: str,
        user_id: str,
        as_of: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        catalog = self.list_project_sources(
            project_id,
            user_id=user_id,
            as_of=as_of,
            query=query,
            limit=limit,
        )
        return [
            {
                "chunk_id": f"authority:{record['source_id']}",
                "source_id": record["source_id"],
                "source_path": record["source_path"],
                "title": record["title"],
                "content": record["content_preview"],
                "source_version": record.get("source_version") or "current",
                "occurred_at": record.get("occurred_at"),
                "recorded_at": record.get("recorded_at"),
                "valid_from": record.get("occurred_at"),
                "valid_to": None,
                "permission_version": record.get("permission_version") or "package-read-v1",
                "masked_fields": [],
                "fields": {
                    "record_type": "authoritative_source",
                    "source_type": record["source_type"],
                    "requirement_ids": record["requirement_ids"],
                },
            }
            for record in catalog["sources"]
        ]

    def search_knowledge(
        self,
        project_id: str,
        *,
        query: str,
        user_id: str,
        as_of: str,
        limit: int = 8,
    ) -> dict[str, Any]:
        if project_id == "PUBLIC-CAPABILITIES":
            results = self._public_capability_search(query=query, limit=limit)
            return {
                "project_id": project_id,
                "query": query,
                "as_of": as_of,
                "results": results,
                "insufficient_evidence": not results,
                "permission_decision": "public_curated",
                "data_classification": "curated_capability_reference",
                "is_real_business_result": False,
            }
        self._user(user_id)
        revoked = self._is_revoked(user_id, as_of)
        if revoked:
            results = []
        elif project_id == "PRJ-KM-001":
            results = self._knowledge_management_search(
                query=query, as_of=as_of, limit=limit
            )
        elif project_id == "PRJ-AUTO-001":
            results = self._vehicle_search(
                query=query, user_id=user_id, as_of=as_of, limit=limit
            )
        else:
            self._require_tender_project(project_id)
            results = self.adapter.search(query, user_id, as_of)[:limit]
        source_records = (
            []
            if revoked
            else self._authoritative_search_rows(
                project_id,
                query=query,
                user_id=user_id,
                as_of=as_of,
                limit=limit,
            )
        )
        if not results:
            results = source_records[:limit]
        return {
            "project_id": project_id,
            "query": query,
            "as_of": as_of,
            "results": results,
            "source_records": source_records,
            "insufficient_evidence": not results and not source_records,
            "permission_decision": "revoked" if revoked else "allowed",
            "data_classification": "synthetic_demo",
        }

    def get_requirement_history(
        self,
        project_id: str,
        requirement_id: str,
        *,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"requirement access was revoked: {user_id}")
        if project_id == "PRJ-KM-001":
            root = self.projects_root / "华东新程汽车项目"
            requirements = self._read_json(root / "02_需求阶段/requirements.json")[
                "requirements"
            ]
            requirement = next(
                (
                    item
                    for item in requirements
                    if item["requirement_id"] == requirement_id
                ),
                None,
            )
            if requirement is None:
                raise ValueError(f"unknown requirement: {requirement_id}")
            versions = [
                deepcopy(version)
                for version in requirement["versions"]
                if self._at_or_before(version["created_at"], as_of)
            ]
            return {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "title": requirement["name"],
                "versions": versions,
                "applicable_version_id": (
                    versions[-1]["requirement_version_id"] if versions else None
                ),
                "open_items": [],
                "as_of": as_of,
                "data_classification": "synthetic_demo",
                "source_records": self.get_requirement_sources(
                    project_id,
                    requirement_id,
                    user_id=user_id,
                    as_of=as_of,
                )["sources"],
            }
        if project_id == "PRJ-AUTO-001":
            root = self.projects_root / "东辰出行新能源车辆采购项目"
            requirement = self._read_json(
                root / "01_客户与需求/customer_requirement.json"
            )["requirement"]
            if requirement["requirement_id"] != requirement_id:
                raise ValueError(f"unknown requirement: {requirement_id}")
            versions = [
                deepcopy(version)
                for version in requirement["versions"]
                if self._at_or_before(version["created_at"], as_of)
            ]
            return {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "title": requirement["title"],
                "versions": versions,
                "applicable_version_id": (
                    versions[-1]["requirement_version_id"] if versions else None
                ),
                "open_items": [],
                "as_of": as_of,
                "data_classification": "synthetic_demo",
                "source_records": self.get_requirement_sources(
                    project_id,
                    requirement_id,
                    user_id=user_id,
                    as_of=as_of,
                )["sources"],
            }
        self._require_tender_project(project_id)
        data = self._read_json(
            self.tender_root / "02_采购立项与需求/initiation_requirement.json"
        )["requirement"]
        if data["requirement_id"] != requirement_id:
            raise ValueError(f"unknown requirement: {requirement_id}")
        versions = [
            deepcopy(version)
            for version in data["versions"]
            if self._at_or_before(version["occurred_at"], as_of)
            and self._at_or_before(version["recorded_at"], as_of)
        ]
        applicable = [
            version
            for version in versions
            if self._at_or_before(version["valid_from"], as_of)
            and (
                version.get("valid_to") is None
                or not self._at_or_before(version["valid_to"], as_of)
            )
        ]
        return {
            "project_id": project_id,
            "requirement_id": requirement_id,
            "title": data["title"],
            "versions": versions,
            "applicable_version_id": (
                applicable[-1]["requirement_version_id"] if applicable else None
            ),
            "open_items": (
                data["open_items_at_baseline"]
                if self._source_recorded("SRC-TENDER-013", as_of)
                else []
            ),
            "as_of": as_of,
            "data_classification": "synthetic_demo",
            "source_records": self.get_requirement_sources(
                project_id,
                requirement_id,
                user_id=user_id,
                as_of=as_of,
            )["sources"],
        }

    def analyze_suppliers(
        self,
        project_id: str,
        *,
        user_id: str,
        as_of: str,
        supplier_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            return {
                "project_id": project_id,
                "suppliers": [],
                "masked_fields": [],
                "permission_decision": "revoked",
                "data_classification": "synthetic_demo",
            }
        data = self._read_json(
            self.tender_root / "03_供应商画像/supplier_profiles.json"
        )
        suppliers = [
            deepcopy(supplier)
            for supplier in data["suppliers"]
            if self._at_or_before(supplier["valid_from"], as_of)
            and (supplier_id is None or supplier["supplier_id"] == supplier_id)
        ]
        visible_source_ids = self._visible_source_ids(user_id, as_of)
        for supplier in suppliers:
            supplier["source_ids"] = [
                source_id
                for source_id in supplier["source_ids"]
                if source_id in visible_source_ids
            ]
            supplier["historical_quotes"] = [
                quote
                for quote in supplier.get("historical_quotes", [])
                if self._date_at_or_before(quote["quoted_at"], as_of)
            ]
        roles = set(user["roles"])
        masked_fields: list[str] = []
        if "procurement_owner" not in roles and "supplier_quality" not in roles:
            masked_fields.append("supplier_score")
            for supplier in suppliers:
                supplier.pop("score_detail", None)
                for record in supplier.get("performance_records", []):
                    record.pop("quality_ppm", None)
        if "procurement_owner" not in roles and "legal_finance" not in roles:
            masked_fields.append("unit_price_cny")
            for supplier in suppliers:
                supplier.pop("historical_quotes", None)
        return {
            "project_id": project_id,
            "suppliers": suppliers,
            "evaluation_weights": data["evaluation_weights"],
            "governance": data["governance"],
            "masked_fields": sorted(masked_fields),
            "permission_decision": "allowed",
            "data_classification": "synthetic_demo",
            "as_of": as_of,
        }

    def get_document_reviews(
        self, project_id: str, *, user_id: str, as_of: str
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"document review access was revoked: {user_id}")
        rules = self._read_json(
            self.tender_root / "05_文档生成与审查/rule_sets.json"
        )
        expectations = self._read_json(
            self.tender_root / "05_文档生成与审查/review_expectations.json"
        )
        if not self._source_recorded("SRC-TENDER-024", as_of):
            return {
                "project_id": project_id,
                "rule_set_id": rules["rule_set_id"],
                "rule_set_version": rules["version"],
                "rules": [],
                "samples": [],
                "summary": {"control": 0, "defective": 0, "findings": 0},
                "human_review_required": True,
                "status": "not_recorded_as_of",
                "data_classification": "synthetic_demo",
            }
        samples = deepcopy(expectations["samples"])
        for sample in samples:
            source = self.tender_root / sample["source_path"]
            sample["excerpt"] = source.read_text(encoding="utf-8")[:700]
        controls = sum(sample["sample_type"] == "control" for sample in samples)
        defective = sum(sample["sample_type"] == "defective" for sample in samples)
        findings = sum(len(sample["expected_findings"]) for sample in samples)
        return {
            "project_id": project_id,
            "rule_set_id": rules["rule_set_id"],
            "rule_set_version": rules["version"],
            "rules": rules["rules"],
            "samples": samples,
            "summary": {
                "control": controls,
                "defective": defective,
                "findings": findings,
            },
            "human_review_required": True,
            "data_classification": "synthetic_demo",
        }

    def get_decision_history(
        self,
        project_id: str,
        *,
        decision_or_object_id: str,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        self._user(user_id)
        if self._is_revoked(user_id, as_of):
            return {
                "project_id": project_id,
                "timeline": [],
                "current_status": "revoked",
                "evidence": [],
                "permission_filtered_count": 0,
                "permission_decision": "revoked",
                "data_classification": "synthetic_demo",
            }
        records = self._read_jsonl(
            self.tender_root / "09_沟通记录/communications.jsonl"
        )
        temporal = [
            record
            for record in records
            if self._at_or_before(record["occurred_at"], as_of)
            and self._at_or_before(record["recorded_at"], as_of)
            and (
                decision_or_object_id in record["related"].get("object_ids", [])
                or decision_or_object_id.casefold()
                in record["related"].get("topic", "").casefold()
                or decision_or_object_id.casefold() in record["content"].casefold()
            )
        ]
        visible_sources = self._visible_source_ids(user_id, as_of)
        timeline = [
            record
            for record in temporal
            if set(record["related"].get("source_ids", [])) <= visible_sources
        ]
        return {
            "project_id": project_id,
            "decision_or_object_id": decision_or_object_id,
            "timeline": timeline,
            "current_status": "evidence_found" if timeline else "insufficient_evidence",
            "evidence": sorted(
                {
                    source_id
                    for record in timeline
                    for source_id in record["related"].get("source_ids", [])
                }
            ),
            "permission_filtered_count": len(temporal) - len(timeline),
            "permission_decision": "allowed",
            "data_classification": "synthetic_demo",
        }

    def search_communication(
        self,
        project_id: str,
        *,
        query: str,
        user_id: str,
        as_of: str,
        channel: str | None = None,
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            return {
                "project_id": project_id,
                "records": [],
                "evidence": [],
                "permission_filtered_count": 0,
                "permission_decision": "revoked",
                "data_classification": "synthetic_demo",
            }
        records = self._read_jsonl(
            self.tender_root / "09_沟通记录/communications.jsonl"
        )
        visible_sources = set(
            self.adapter.load_customer_context(user_id, as_of).source_ids
        )
        temporal = [
            record
            for record in records
            if self._at_or_before(record["occurred_at"], as_of)
            and self._at_or_before(record["recorded_at"], as_of)
            and (channel is None or record["channel"] == channel)
            and query.casefold()
            in " ".join(
                (
                    record["context_before"],
                    record["content"],
                    record["context_after"],
                    record["related"].get("topic", ""),
                )
            ).casefold()
        ]
        visible = [
            record
            for record in temporal
            if set(record["related"].get("source_ids", [])) <= visible_sources
        ]
        return {
            "project_id": project_id,
            "records": visible,
            "evidence": sorted(
                {
                    source_id
                    for record in visible
                    for source_id in record["related"].get("source_ids", [])
                }
            ),
            "permission_filtered_count": len(temporal) - len(visible),
            "permission_decision": "allowed",
            "data_classification": "synthetic_demo",
        }

    def trace_business_object(
        self,
        project_id: str,
        *,
        object_id: str,
        user_id: str,
        as_of: str,
        direction: str = "both",
        max_depth: int = 3,
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "hidden_nodes": 1,
                "warnings": ["authorization revoked"],
                "permission_decision": "revoked",
                "data_classification": "synthetic_demo",
            }
        initiation = self._read_json(
            self.tender_root / "02_采购立项与需求/initiation_requirement.json"
        )
        sourcing = self._read_json(
            self.tender_root / "04_采购方案与执行/sourcing_execution.json"
        )
        fulfillment = self._read_json(
            self.tender_root / "06_合同履约/contract_fulfillment.json"
        )
        nodes: dict[str, dict[str, Any]] = {
            "PRJ-TENDER-001": {"id": "PRJ-TENDER-001", "type": "project"},
            "REQ-BAT-001": {"id": "REQ-BAT-001", "type": "requirement"},
        }
        edges = [
            {"from": "PRJ-TENDER-001", "to": "REQ-BAT-001", "relation": "contains"},
        ]
        visible_versions = [
            version
            for version in initiation["requirement"]["versions"]
            if self._at_or_before(version["occurred_at"], as_of)
            and self._at_or_before(version["recorded_at"], as_of)
        ]
        for version in visible_versions:
            version_id = version["requirement_version_id"]
            nodes[version_id] = {"id": version_id, "type": "requirement_version"}
            edges.append(
                {"from": "REQ-BAT-001", "to": version_id, "relation": "has_version"}
            )
        tender_visible = self._at_or_before(sourcing["execution"]["issued_at"], as_of)
        if tender_visible:
            tender_id = sourcing["execution"]["tender_id"]
            nodes[tender_id] = {"id": tender_id, "type": "tender"}
            applicable = [
                version
                for version in visible_versions
                if self._at_or_before(version["valid_from"], as_of)
                and (
                    version.get("valid_to") is None
                    or not self._at_or_before(version["valid_to"], as_of)
                )
            ]
            if applicable:
                edges.append(
                    {
                        "from": applicable[-1]["requirement_version_id"],
                        "to": tender_id,
                        "relation": "drives",
                    }
                )
        roles = set(user["roles"])
        contract_visible = bool({"procurement_owner", "legal_finance"} & roles)
        for contract in fulfillment["contracts"]:
            if not self._at_or_before(contract["signed_at"], as_of):
                continue
            if not contract_visible:
                continue
            nodes[contract["contract_id"]] = {
                "id": contract["contract_id"],
                "type": "contract",
                "supplier_id": contract["supplier_id"],
                "quantity": contract["quantity"],
            }
            nodes[contract["supplier_id"]] = {
                "id": contract["supplier_id"],
                "type": "supplier",
            }
            edges.extend(
                [
                    {
                        "from": sourcing["execution"]["tender_id"],
                        "to": contract["contract_id"],
                        "relation": "awards",
                    },
                    {
                        "from": contract["contract_id"],
                        "to": contract["supplier_id"],
                        "relation": "signed_with",
                    },
                ]
            )
        if object_id not in nodes:
            matching_contract = next(
                (
                    contract
                    for contract in fulfillment["contracts"]
                    if contract["contract_id"] == object_id
                ),
                None,
            )
            if matching_contract is not None and not contract_visible:
                return {
                    "project_id": project_id,
                    "nodes": [],
                    "edges": [],
                    "hidden_nodes": 1,
                    "warnings": [f"object access forbidden: {object_id}"],
                    "permission_decision": "forbidden",
                    "data_classification": "synthetic_demo",
                }
            if matching_contract is not None:
                warning = f"object not recorded as-of query time: {object_id}"
            else:
                warning = f"object not found: {object_id}"
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "hidden_nodes": 0,
                "warnings": [warning],
                "permission_decision": "allowed",
                "data_classification": "synthetic_demo",
            }
        selected_ids = {object_id}
        for _ in range(max(0, min(max_depth, 6))):
            for edge in edges:
                if direction in {"both", "downstream"} and edge["from"] in selected_ids:
                    selected_ids.add(edge["to"])
                if direction in {"both", "upstream"} and edge["to"] in selected_ids:
                    selected_ids.add(edge["from"])
        visible_edges = [
            edge
            for edge in edges
            if edge["from"] in selected_ids and edge["to"] in selected_ids
        ]
        return {
            "project_id": project_id,
            "nodes": [nodes[node_id] for node_id in sorted(selected_ids)],
            "edges": visible_edges,
            "hidden_nodes": 0,
            "warnings": [],
            "permission_decision": "allowed",
            "data_classification": "synthetic_demo",
            "source_requirement_title": initiation["requirement"]["title"],
        }

    def get_financial_reconciliation(
        self,
        project_id: str,
        *,
        contract_id: str,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        user = self._user(user_id)
        roles = set(user["roles"])
        if self._is_revoked(user_id, as_of) or not (
            {"procurement_owner", "legal_finance"} & roles
        ):
            raise PermissionError("financial reconciliation requires procurement or legal-finance role")
        data = self._read_json(
            self.tender_root / "06_合同履约/contract_fulfillment.json"
        )
        contract = next(
            (item for item in data["contracts"] if item["contract_id"] == contract_id),
            None,
        )
        if contract is None:
            raise ValueError(f"unknown contract: {contract_id}")
        if not self._at_or_before(contract["signed_at"], as_of):
            raise ValueError(f"contract is not recorded as-of this time: {contract_id}")
        calculated = contract["quantity"] * contract["unit_price_cny"]
        financial_summary = data["financial_summary"]
        summary_recorded = self._at_or_before(financial_summary["as_of"], as_of)
        differences = []
        if calculated != contract["total_amount_cny"]:
            differences.append(
                {
                    "type": "contract_amount_mismatch",
                    "expected_cny": calculated,
                    "recorded_cny": contract["total_amount_cny"],
                }
            )
        return {
            "project_id": project_id,
            "contract_id": contract_id,
            "reconciliation": {
                "quantity": contract["quantity"],
                "unit_price_cny": contract["unit_price_cny"],
                "calculated_total_cny": calculated,
                "recorded_total_cny": contract["total_amount_cny"],
                "project_financial_summary": (
                    financial_summary if summary_recorded else None
                ),
                "financial_summary_status": (
                    "recorded_as_of" if summary_recorded else "not_recorded_as_of"
                ),
            },
            "differences": differences,
            "evidence_ids": ["SRC-TENDER-022"],
            "as_of": as_of,
            "data_classification": "synthetic_demo",
        }

    def review_tender_document(
        self,
        project_id: str,
        *,
        document_id: str,
        user_id: str,
        as_of: str,
    ) -> dict[str, Any]:
        reviews = self.get_document_reviews(
            project_id, user_id=user_id, as_of=as_of
        )
        sample = next(
            (item for item in reviews["samples"] if item["sample_id"] == document_id),
            None,
        )
        if sample is None:
            if reviews.get("status") == "not_recorded_as_of":
                raise ValueError(f"review sample is not recorded as-of query time: {document_id}")
            raise ValueError(f"unknown review sample: {document_id}")
        return {
            "project_id": project_id,
            "document_id": document_id,
            "sample_type": sample["sample_type"],
            "findings": sample["expected_findings"],
            "human_review_required": True,
            "rule_version": reviews["rule_set_version"],
            "evidence": [sample["source_path"]],
            "data_classification": "synthetic_demo",
        }

    def generate_solution_bundle(
        self, project_id: str, *, user_id: str, as_of: str
    ) -> dict[str, Any]:
        self._require_tender_project(project_id)
        user = self._user(user_id)
        if self._is_revoked(user_id, as_of):
            raise PermissionError(f"solution generation authorization was revoked: {user_id}")
        if not ({"procurement_owner", "legal_finance"} & set(user["roles"])):
            raise PermissionError("solution generation requires procurement or legal-finance role")
        if not self._formal_solution_ready(as_of):
            raise ValueError(
                "formal solution is not ready as-of this time; current-process evidence SRC-TENDER-016 is not yet recorded"
            )
        context = self.adapter.load_customer_context(user_id, as_of)
        state = self.adapter.load_requirement_truth(context)
        process = self.adapter.build_process_spec(state)
        bundle = self.adapter.compile_solution_bundle(process).model_dump(mode="json")
        for plan in bundle["plans"]:
            warning = "本方案基于模拟验收数据，不代表真实业务成果。"
            if warning not in plan["warnings"]:
                plan["warnings"].append(warning)
        bundle.update(
            {
                "process": process.model_dump(mode="json"),
                "as_of": as_of,
                "data_classification": "synthetic_demo",
                "is_real_business_result": False,
            }
        )
        return bundle
