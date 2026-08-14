"""PORTAL-M1 MCP JSON-RPC and project assistant tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from backend.app.solution.enterprise_assistant import EnterpriseAssistantRequest, EnterpriseAssistantService
from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
from backend.app.solution.mcp_server import MCPDispatcher


ROOT = Path(__file__).resolve().parents[2]


def dispatcher() -> MCPDispatcher:
    return MCPDispatcher(EnterpriseKnowledgeService(ROOT))


def test_mcp_initialize_list_tools_and_call_search() -> None:
    mcp = dispatcher()
    initialized = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
    )
    tools = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    result = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {
                    "project_id": "PRJ-TENDER-001",
                    "query": "最终年需求量和交付日期",
                    "user_id": "user-procurement-owner",
                    "as_of": "2026-08-14T23:59:59+08:00",
                },
            },
        }
    )

    assert initialized["result"]["serverInfo"]["name"] == "dcforge-enterprise-knowledge"
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert {
        "list_projects",
        "get_project_dashboard",
        "search_knowledge",
        "get_requirement_history",
        "analyze_suppliers",
        "review_tender_document",
        "generate_solution_bundle",
        "get_decision_history",
        "search_communication",
        "trace_business_object",
        "get_financial_reconciliation",
    } <= names
    structured = result["result"]["structuredContent"]
    assert structured["results"]
    assert "REQ-BAT-001-V3" not in {
        row["source_version"] for row in structured["results"]
    }


def test_mcp_solution_tool_uses_existing_solution_bundle() -> None:
    response = dispatcher().handle(
        {
            "jsonrpc": "2.0",
            "id": "solution-1",
            "method": "tools/call",
            "params": {
                "name": "generate_solution_bundle",
                "arguments": {
                    "project_id": "PRJ-TENDER-001",
                    "user_id": "user-procurement-owner",
                    "as_of": "2026-10-30T23:59:59+08:00",
                },
            },
        }
    )

    result = response["result"]["structuredContent"]
    assert result["project_id"] == "PRJ-TENDER-001"
    assert {plan["plan_type"] for plan in result["plans"]} == {
        "conservative",
        "balanced",
        "innovative",
    }
    assert all("真实业务成果" in "".join(plan["warnings"]) for plan in result["plans"])


def test_mcp_solution_tool_refuses_before_current_process_is_recorded() -> None:
    response = dispatcher().handle(
        {
            "jsonrpc": "2.0",
            "id": "solution-early",
            "method": "tools/call",
            "params": {
                "name": "generate_solution_bundle",
                "arguments": {
                    "project_id": "PRJ-TENDER-001",
                    "user_id": "user-procurement-owner",
                    "as_of": "2026-08-20T23:59:59+08:00",
                },
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert "not ready" in response["error"]["message"]


def test_project_ai_assistant_routes_through_mcp_dispatcher() -> None:
    mcp = dispatcher()
    assistant = EnterpriseAssistantService(mcp)
    response = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-TENDER-001",
            user_id="user-procurement-owner",
            as_of="2026-10-30T23:59:59+08:00",
            message="请生成这个项目的三套方案",
        )
    )

    assert response.tool_name == "generate_solution_bundle"
    assert response.solution_bundle is not None
    assert len(response.solution_bundle["plans"]) == 3
    assert response.tool_call["method"] == "tools/call"
    assert "模拟" in response.answer

    supplier = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-TENDER-001",
            user_id="user-procurement-owner",
            as_of="2026-10-30T23:59:59+08:00",
            message="供应商三为什么未进入推荐？",
        )
    )
    assert supplier.tool_name == "analyze_suppliers"
    assert supplier.citations == ["SRC-TENDER-019", "SRC-TENDER-021"]
    assert "海卓储能" in supplier.answer


def test_project_ai_assistant_can_summarize_other_browseable_projects() -> None:
    assistant = EnterpriseAssistantService(dispatcher())
    response = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-AUTO-001",
            user_id="user-procurement-owner",
            as_of="2026-11-01T23:59:59+08:00",
            message="这个项目目前有哪些数据？",
        )
    )

    assert response.tool_name == "get_project_dashboard"
    assert "100台新能源运营车辆采购项目" in response.answer
    assert "vehicles=100" in response.answer


def test_project_ai_assistant_answers_knowledge_and_vehicle_questions() -> None:
    assistant = EnterpriseAssistantService(dispatcher())
    knowledge = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-KM-001",
            user_id="user-procurement-owner",
            as_of="2027-02-10T23:59:59+08:00",
            message="为什么一期不替换SRM？",
        )
    )
    vehicle = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-AUTO-001",
            user_id="user-procurement-owner",
            as_of="2026-11-05T23:59:59+08:00",
            message="客户最终确认了多少台白色车辆？",
        )
    )
    history = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-AUTO-001",
            user_id="user-procurement-owner",
            as_of="2026-08-14T23:59:59+08:00",
            message="需求版本历史是什么？",
        )
    )

    assert knowledge.tool_name == "search_knowledge"
    assert "旁路" in knowledge.answer
    assert {"MTG-003", "WX-002"} & set(knowledge.citations)
    assert len(knowledge.citations) <= 3
    assert vehicle.tool_name == "search_knowledge"
    assert "100台白色" in vehicle.answer
    assert "REQ-AUTO-001-V3" in vehicle.citations
    assert history.tool_name == "get_requirement_history"
    assert history.citations == ["REQ-AUTO-001-V1", "REQ-AUTO-001-V2"]
    assert "REQ-AUTO-001-V3" not in history.answer

    review = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-KM-001",
            user_id="user-procurement-owner",
            as_of="2027-02-10T23:59:59+08:00",
            message="招标审查能否自动废标？",
        )
    )
    financial = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-AUTO-001",
            user_id="user-procurement-owner",
            as_of="2026-11-05T23:59:59+08:00",
            message="合同金额和模拟利润是多少？",
        )
    )

    assert review.tool_name == "search_knowledge"
    assert "不得自动" in review.answer or "人工" in review.answer
    assert financial.tool_name == "search_knowledge"
    assert "1438万元" in financial.answer
    assert "64.5万元" in financial.answer


def test_cross_project_search_does_not_leak_future_aggregate_chunks() -> None:
    portal = EnterpriseKnowledgeService(ROOT)
    knowledge = portal.search_knowledge(
        "PRJ-KM-001",
        query="全过程知识关联",
        user_id="user-procurement-owner",
        as_of="2026-08-20T23:59:59+08:00",
    )
    vehicle = portal.search_knowledge(
        "PRJ-AUTO-001",
        query="最终白色车辆基线",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )

    assert all("REQ-001-V2" not in row["content"] for row in knowledge["results"])
    assert all(row["chunk_id"] != "KM-003" for row in knowledge["results"])
    assert vehicle["results"] == []
    assert vehicle["insufficient_evidence"] is True


def test_mcp_stdio_server_processes_json_lines() -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "backend.app.solution.mcp_server"],
        cwd=ROOT,
        input="\n".join(json.dumps(item) for item in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line]

    assert [response["id"] for response in responses] == [1, 2]
    assert responses[0]["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert responses[1]["result"]["tools"]


def test_data_package_mcp_contract_matches_runtime_tool_registry() -> None:
    contract = json.loads(
        (
            ROOT
            / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
            / "05_AI_Agent"
            / "MCP_tools.json"
        ).read_text(encoding="utf-8")
    )
    runtime = {tool["name"]: tool for tool in dispatcher().tool_definitions()}
    documented = {tool["name"]: tool for tool in contract["tools"]}

    assert set(documented) == set(runtime)
    for name, runtime_tool in runtime.items():
        assert documented[name]["input_schema"] == runtime_tool["inputSchema"]
    assert contract["implementation"]["status"] == "implemented_locally"


def test_all_mcp_tools_execute_with_representative_arguments() -> None:
    calls = {
        "list_projects": {},
        "get_project_dashboard": {
            "project_id": "PRJ-TENDER-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "search_knowledge": {
            "project_id": "PRJ-TENDER-001",
            "query": "年需求量",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "get_requirement_history": {
            "project_id": "PRJ-TENDER-001",
            "requirement_id": "REQ-BAT-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "analyze_suppliers": {
            "project_id": "PRJ-TENDER-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "review_tender_document": {
            "project_id": "PRJ-TENDER-001",
            "document_id": "DEFECT-01",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "generate_solution_bundle": {
            "project_id": "PRJ-TENDER-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "get_decision_history": {
            "project_id": "PRJ-TENDER-001",
            "decision_or_object_id": "SUP-BAT-003",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "search_communication": {
            "project_id": "PRJ-TENDER-001",
            "query": "证书过期",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "trace_business_object": {
            "project_id": "PRJ-TENDER-001",
            "object_id": "CON-BAT-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
        "get_financial_reconciliation": {
            "project_id": "PRJ-TENDER-001",
            "contract_id": "CON-BAT-001",
            "user_id": "user-procurement-owner",
            "as_of": "2026-10-30T23:59:59+08:00",
        },
    }

    for index, (name, arguments) in enumerate(calls.items(), 1):
        response = dispatcher().handle(
            {
                "jsonrpc": "2.0",
                "id": index,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert "error" not in response, (name, response)
        assert response["result"]["isError"] is False


def test_document_review_mcp_requires_explicit_as_of() -> None:
    definition = next(
        tool
        for tool in dispatcher().tool_definitions()
        if tool["name"] == "review_tender_document"
    )
    assert "as_of" in definition["inputSchema"]["required"]


def test_repository_includes_a_runnable_mcp_client_configuration() -> None:
    config = json.loads(
        (ROOT / "docs" / "enterprise-mcp-client.example.json").read_text(
            encoding="utf-8"
        )
    )
    server = config["mcpServers"]["dcforge-enterprise"]

    assert server["type"] == "stdio"
    assert server["args"] == ["-m", "backend.app.solution.mcp_server"]
    assert server["env"]["PYTHONPATH"] == "."
