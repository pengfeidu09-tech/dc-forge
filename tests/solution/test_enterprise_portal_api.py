"""PORTAL-M1 FastAPI boundary tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app, create_app


client = TestClient(app)


def test_enterprise_dashboard_and_solution_endpoints() -> None:
    dashboard = client.get(
        "/enterprise/projects/PRJ-TENDER-001/dashboard",
        params={
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
    )
    solution = client.post(
        "/enterprise/projects/PRJ-TENDER-001/compile",
        json={
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
    )

    assert dashboard.status_code == 200
    assert dashboard.json()["metrics"]["raw_evidence"] == 26
    assert solution.status_code == 200
    assert len(solution.json()["plans"]) == 3


def test_enterprise_assistant_and_http_mcp_share_tools() -> None:
    assistant = client.post(
        "/enterprise/assistant",
        json={
            "project_id": "PRJ-TENDER-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
            "message": "供应商三为什么未进入推荐？",
        },
    )
    mcp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 8, "method": "tools/list", "params": {}},
    )

    assert assistant.status_code == 200
    assert assistant.json()["tool_name"] == "search_solution_cases"
    assert assistant.json()["data_classification"] == "internal_case_knowledge"
    assert mcp.status_code == 200
    assert any(tool["name"] == "generate_solution_bundle" for tool in mcp.json()["result"]["tools"])


def test_enterprise_assistant_preserves_permission_denial_status() -> None:
    response = client.post(
        "/enterprise/assistant",
        json={
            "project_id": "PRJ-TENDER-001",
            "user_id": "user-observer",
            "as_of": "2026-10-30T23:59:59+08:00",
            "message": "请生成这个项目的三套方案",
        },
    )

    assert response.status_code == 200
    assert response.json()["tool_name"] == "search_solution_cases"


def test_document_review_endpoint_requires_as_of() -> None:
    response = client.get(
        "/enterprise/projects/PRJ-TENDER-001/document-reviews",
        params={"user_id": "user-procurement-owner"},
    )

    assert response.status_code == 422


def test_openapi_exposes_enterprise_and_mcp_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/enterprise/projects" in paths
    assert "/enterprise/projects/{project_id}/dashboard" in paths
    assert "/enterprise/assistant" in paths
    assert "/mcp" in paths


def test_fastapi_can_serve_built_enterprise_portal_without_hiding_api(tmp_path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><body>DCForge Enterprise Portal</body></html>", encoding="utf-8"
    )
    static_app = create_app(frontend_dist=tmp_path)
    static_client = TestClient(static_app)

    home = static_client.get("/")
    projects = static_client.get("/enterprise/projects")

    assert home.status_code == 200
    assert "DCForge Enterprise Portal" in home.text
    assert projects.status_code == 200
    assert len(projects.json()["projects"]) == 3


def test_http_mcp_catalog_and_search_are_directly_consumable_by_frontend() -> None:
    catalog = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 21, "method": "tools/list", "params": {}},
    )

    assert catalog.status_code == 200
    tools = catalog.json()["result"]["tools"]
    assert len(tools) == 12
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)

    result = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {
                    "project_id": "PRJ-TENDER-001",
                    "query": "年需求量",
                    "user_id": "user-procurement-owner",
                    "as_of": "2026-10-30T23:59:59+08:00",
                },
            },
        },
    )

    assert result.status_code == 200
    payload = result.json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"]["results"][0]["source_id"]
