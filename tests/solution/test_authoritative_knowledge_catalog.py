from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
from backend.app.solution.mcp_server import MCPDispatcher


ROOT = Path(__file__).parents[2]
AS_OF = "2030-12-31T23:59:59+08:00"
USER_ID = "user-procurement-owner"


def _service() -> EnterpriseKnowledgeService:
    return EnterpriseKnowledgeService(ROOT)


def test_authoritative_catalog_covers_registered_project_files_and_types() -> None:
    service = _service()
    project_root = (
        ROOT
        / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
        / "03_客户项目全过程库"
        / "华东新程汽车项目"
    )

    payload = service.list_project_sources(
        "PRJ-KM-001",
        user_id=USER_ID,
        as_of=AS_OF,
        limit=200,
    )

    assert payload["authority_root"] == "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
    assert payload["total"] == sum(1 for path in project_root.rglob("*") if path.is_file())
    assert payload["type_counts"]["meeting_minutes"] == 12
    assert {item["source_id"] for item in payload["sources"]} >= {
        "MTG-001",
        "DOC-TENDER-001",
    }
    assert all(not Path(item["source_path"]).is_absolute() for item in payload["sources"])
    assert all(item["data_classification"] == "synthetic_demo" for item in payload["sources"])


def test_requirement_sources_link_versions_meetings_documents_and_project_data() -> None:
    service = _service()

    km = service.get_requirement_sources(
        "PRJ-KM-001", "REQ-001", user_id=USER_ID, as_of=AS_OF
    )
    km_ids = {item["source_id"] for item in km["sources"]}
    assert {"MTG-001", "DOC-TENDER-001"} <= km_ids
    assert all(
        any(
            requirement_id == "REQ-001" or requirement_id.startswith("REQ-001-V")
            for requirement_id in item["requirement_ids"]
        )
        for item in km["sources"]
    )

    auto = service.get_requirement_sources(
        "PRJ-AUTO-001", "REQ-AUTO-001", user_id=USER_ID, as_of=AS_OF
    )
    assert auto["total"] >= 8

    tender = service.get_requirement_sources(
        "PRJ-TENDER-001", "REQ-BAT-001", user_id=USER_ID, as_of=AS_OF
    )
    assert {"SRC-TENDER-002", "SRC-TENDER-004"} <= {
        item["source_id"] for item in tender["sources"]
    }


def test_source_detail_returns_authoritative_text_without_absolute_host_path() -> None:
    source = _service().get_project_source(
        "PRJ-KM-001", "MTG-001", user_id=USER_ID, as_of=AS_OF
    )

    assert source["content_available"] is True
    assert "首次需求沟通" in source["content"]
    assert source["source_path"].startswith("03_客户项目全过程库/")
    assert str(ROOT) not in source["source_path"]
    assert source["is_real_business_result"] is False


def test_tender_catalog_reuses_manifest_ids_and_applies_as_of_visibility() -> None:
    payload = _service().list_project_sources(
        "PRJ-TENDER-001",
        user_id=USER_ID,
        as_of="2026-08-11T23:59:59+08:00",
        source_type="meeting_minutes",
        limit=200,
    )

    source_ids = {item["source_id"] for item in payload["sources"]}
    assert "SRC-TENDER-003" in source_ids
    assert "SRC-TENDER-006" not in source_ids
    assert all(item["source_id"].startswith("SRC-TENDER-") for item in payload["sources"])


def test_restricted_structured_source_masks_content_in_list_and_detail() -> None:
    service = _service()
    payload = service.list_project_sources(
        "PRJ-TENDER-001",
        user_id="user-observer",
        as_of=AS_OF,
        limit=200,
    )
    supplier_source = next(
        item for item in payload["sources"] if "03_供应商画像/" in item["source_path"]
    )

    assert supplier_source["content_available"] is False
    assert supplier_source["content_preview"] == ""
    assert supplier_source["masked_fields"] == ["content"]

    detail = service.get_project_source(
        "PRJ-TENDER-001",
        supplier_source["source_id"],
        user_id="user-observer",
        as_of=AS_OF,
    )
    assert detail["content"] is None
    assert detail["masked_fields"] == ["content"]


def test_rest_exposes_source_catalog_and_requirement_evidence() -> None:
    client = TestClient(create_app())
    params = {"user_id": USER_ID, "as_of": AS_OF}

    listed = client.get("/enterprise/projects/PRJ-KM-001/sources", params=params)
    assert listed.status_code == 200
    assert listed.json()["type_counts"]["meeting_minutes"] == 12

    detail = client.get(
        "/enterprise/projects/PRJ-KM-001/sources/MTG-001", params=params
    )
    assert detail.status_code == 200
    assert "首次需求沟通" in detail.json()["content"]

    related = client.get(
        "/enterprise/projects/PRJ-KM-001/requirements/REQ-001/sources",
        params=params,
    )
    assert related.status_code == 200
    assert {item["source_id"] for item in related.json()["sources"]} >= {
        "MTG-001",
        "DOC-TENDER-001",
    }


def test_mcp_keeps_eleven_tools_and_returns_authoritative_requirement_sources() -> None:
    dispatcher = MCPDispatcher(_service())
    assert len(dispatcher.tool_definitions()) == 11

    response = dispatcher.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_requirement_history",
                "arguments": {
                    "project_id": "PRJ-KM-001",
                    "requirement_id": "REQ-001",
                    "user_id": USER_ID,
                    "as_of": AS_OF,
                },
            },
        }
    )

    structured = response["result"]["structuredContent"]
    assert {item["source_id"] for item in structured["source_records"]} >= {
        "MTG-001",
        "DOC-TENDER-001",
    }

    search = dispatcher.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {
                    "project_id": "PRJ-KM-001",
                    "query": "MTG-001 首次需求沟通",
                    "user_id": USER_ID,
                    "as_of": AS_OF,
                },
            },
        }
    )
    search_content = search["result"]["structuredContent"]
    assert any(item["source_id"] == "MTG-001" for item in search_content["source_records"])
