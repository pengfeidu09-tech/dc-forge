"""Read-only catalog for the packaged enterprise customer knowledge dataset."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
import re
from typing import Any


_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
_REQUIREMENT_ID = re.compile(r"\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
_OBJECT_ID = re.compile(r"\b[A-Z]{2,12}(?:-[A-Z0-9]+){1,6}\b")
_TIMESTAMP = re.compile(
    r"\b20\d{2}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?\b"
)
_DOCUMENT_ID = re.compile(r"文档\s*ID[：:]\s*`?(DOC-[A-Z0-9-]+)", re.IGNORECASE)
_MEETING_ID = re.compile(r"^(MTG-[A-Z0-9-]+?)(?:_|$)", re.IGNORECASE)


class AuthoritativeKnowledgeCatalog:
    """Index files below the one authoritative knowledge-package root."""

    def __init__(self, package_root: Path | str) -> None:
        self.package_root = Path(package_root).resolve()
        if not self.package_root.is_dir():
            raise ValueError(f"authoritative knowledge package is missing: {self.package_root}")
        seed_path = self.package_root / "06_DEMO数据/demo_seed.json"
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        self._projects: dict[str, dict[str, Any]] = {}
        for item in seed["projects"]:
            entry = (self.package_root / item["entry"]).resolve()
            project_root = entry if entry.is_dir() else entry.parent
            if not project_root.is_relative_to(self.package_root) or not project_root.is_dir():
                raise ValueError(f"invalid authoritative project entry: {item['entry']}")
            self._projects[item["project_id"]] = {
                **item,
                "project_root": project_root,
            }

    @staticmethod
    def _read_text(path: Path) -> str | None:
        if path.suffix.casefold() not in _TEXT_SUFFIXES:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _normalize_timestamp(value: str) -> str:
        normalized = value.strip().replace(" ", "T")
        if len(normalized) == 10:
            normalized += "T23:59:59"
        elif len(normalized) == 16:
            normalized += ":00"
        if not normalized.endswith("Z") and normalized[-6:-5] not in {"+", "-"}:
            normalized += "+08:00"
        return normalized

    @classmethod
    def _latest_timestamp(cls, content: str | None) -> str | None:
        if not content:
            return None
        values: list[tuple[datetime, str]] = []
        for match in _TIMESTAMP.findall(content):
            normalized = cls._normalize_timestamp(match)
            try:
                values.append((datetime.fromisoformat(normalized), normalized))
            except ValueError:
                continue
        return max(values)[1] if values else None

    @staticmethod
    def _title(path: Path, content: str | None, manifest: dict[str, Any] | None) -> str:
        if manifest and manifest.get("title"):
            return str(manifest["title"])
        if content and path.suffix.casefold() == ".md":
            for line in content.splitlines():
                if line.startswith("#"):
                    return line.lstrip("# ").strip() or path.stem
        return path.stem

    @staticmethod
    def _source_type(path: Path, manifest: dict[str, Any] | None) -> str:
        if manifest and manifest.get("source_type"):
            source_type = str(manifest["source_type"])
            return "communication" if source_type == "historical_communication" else source_type
        relative = path.as_posix()
        if "会议记录" in relative:
            return "meeting_minutes"
        if "沟通记录" in relative:
            return "communication"
        if "招标" in relative:
            return "bid_document"
        if "客户画像" in relative:
            return "customer_profile"
        if "需求" in relative:
            return "requirement_document"
        if "文档生成与审查" in relative or "review" in path.stem.casefold():
            return "document_review"
        if path.suffix.casefold() not in _TEXT_SUFFIXES:
            return "attachment"
        return "project_data"

    @staticmethod
    def _source_id(
        project_id: str,
        project_relative_path: str,
        path: Path,
        content: str | None,
        manifest: dict[str, Any] | None,
    ) -> str:
        if manifest and manifest.get("source_id"):
            return str(manifest["source_id"])
        meeting = _MEETING_ID.match(path.stem)
        if meeting:
            return meeting.group(1).upper()
        if content and path.suffix.casefold() == ".md":
            document = _DOCUMENT_ID.search(content[:2000])
            if document:
                return document.group(1).upper()
        digest = sha256(f"{project_id}|{project_relative_path}".encode("utf-8")).hexdigest()[:16]
        return f"FILE-{digest.upper()}"

    @staticmethod
    def _requirement_ids(content: str | None, manifest: dict[str, Any] | None) -> list[str]:
        values = set(_REQUIREMENT_ID.findall(content or ""))
        if manifest:
            source_version = str(manifest.get("source_version") or "")
            values.update(_REQUIREMENT_ID.findall(source_version))
        return sorted(values)

    @staticmethod
    def _object_ids(content: str | None) -> list[str]:
        return sorted(set(_OBJECT_ID.findall(content or "")))

    def _manifest(self, project_root: Path) -> dict[str, dict[str, Any]]:
        path = project_root / "00_原始证据/source_manifest.json"
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["source_path"]: item for item in payload.get("sources", [])}

    @lru_cache(maxsize=None)
    def records(self, project_id: str) -> tuple[dict[str, Any], ...]:
        project = self._projects.get(project_id)
        if project is None:
            raise ValueError(f"unknown authoritative project: {project_id}")
        project_root: Path = project["project_root"]
        manifest = self._manifest(project_root)
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for path in sorted(item for item in project_root.rglob("*") if item.is_file()):
            project_relative = path.relative_to(project_root).as_posix()
            authority_relative = path.relative_to(self.package_root).as_posix()
            manifest_item = manifest.get(project_relative)
            content = self._read_text(path)
            source_id = self._source_id(
                project_id, project_relative, path, content, manifest_item
            )
            if source_id in seen:
                digest = sha256(
                    f"{project_id}|{project_relative}".encode("utf-8")
                ).hexdigest()[:16]
                source_id = f"FILE-{digest.upper()}"
            seen.add(source_id)
            recorded_at = (
                str(manifest_item.get("recorded_at"))
                if manifest_item and manifest_item.get("recorded_at")
                else self._latest_timestamp(content)
            )
            if (
                recorded_at is None
                and project_id == "PRJ-AUTO-001"
                and project_relative in {"README.md", "project_master.json"}
            ):
                recorded_at = "2026-11-05T14:00:00+08:00"
            occurred_at = (
                str(manifest_item.get("occurred_at"))
                if manifest_item and manifest_item.get("occurred_at")
                else recorded_at
            )
            requirement_ids = self._requirement_ids(content, manifest_item)
            object_ids = self._object_ids(content)
            preview = re.sub(r"\s+", " ", content or "").strip()[:360]
            records.append(
                {
                    "source_id": source_id,
                    "project_id": project_id,
                    "title": self._title(path, content, manifest_item),
                    "source_type": self._source_type(path, manifest_item),
                    "source_path": authority_relative,
                    "media_type": mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    "size_bytes": path.stat().st_size,
                    "content_available": content is not None,
                    "content_preview": preview,
                    "requirement_ids": requirement_ids,
                    "object_ids": object_ids,
                    "occurred_at": occurred_at,
                    "recorded_at": recorded_at,
                    "source_version": (
                        manifest_item.get("source_version") if manifest_item else None
                    ),
                    "permission_version": (
                        manifest_item.get("permission_version") if manifest_item else None
                    ),
                    "data_classification": "synthetic_demo",
                    "is_real_business_result": False,
                    "_content": content,
                    "_manifest_managed": manifest_item is not None,
                }
            )
        return tuple(records)

    @staticmethod
    def matches_requirement(record: dict[str, Any], requirement_id: str) -> bool:
        requested = requirement_id.strip().upper()
        return any(
            value == requested or value.startswith(f"{requested}-V")
            for value in record["requirement_ids"]
        )

    @staticmethod
    def summary(record: dict[str, Any]) -> dict[str, Any]:
        return deepcopy({key: value for key, value in record.items() if not key.startswith("_")})

    @classmethod
    def detail(
        cls, record: dict[str, Any], *, content_allowed: bool = True
    ) -> dict[str, Any]:
        result = cls.summary(record)
        result["content_available"] = bool(
            record["content_available"] and content_allowed
        )
        result["content"] = record["_content"] if result["content_available"] else None
        result["masked_fields"] = [] if content_allowed else ["content"]
        return result
