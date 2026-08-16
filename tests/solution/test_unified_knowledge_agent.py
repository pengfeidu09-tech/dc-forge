"""CHAT-M5 audience-aware knowledge and MCP Agent tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.solution.enterprise_assistant import (
    EnterpriseAssistantRequest,
    EnterpriseAssistantService,
)
from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.mcp_server import MCPDispatcher


ROOT = Path(__file__).resolve().parents[2]


class SequenceProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        self.calls.append(messages)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return LLMResponse(content=self.responses[index])


def _dispatcher() -> MCPDispatcher:
    return MCPDispatcher(EnterpriseKnowledgeService(ROOT))


def test_public_capability_scope_searches_only_curated_customer_documents() -> None:
    result = EnterpriseKnowledgeService(ROOT).search_knowledge(
        "PUBLIC-CAPABILITIES",
        query="智能招采可以在哪些环节提供帮助？",
        user_id="external-customer",
        as_of="2026-08-15T23:59:59+08:00",
    )

    assert result["results"]
    assert result["data_classification"] == "curated_capability_reference"
    assert {row["source_id"] for row in result["results"]} <= {
        "CAP-AI-PROCESS",
        "CAP-SMART-PROCUREMENT",
        "SOL-AUTOMOTIVE-PROCUREMENT",
    }
    serialized = json.dumps(result, ensure_ascii=False)
    assert "SUP-BAT-" not in serialized
    assert "CON-BAT-" not in serialized


def test_customer_agent_cannot_select_an_internal_mcp_tool_or_scope() -> None:
    provider = SequenceProvider(
        [
            json.dumps(
                {
                    "tool_calls": [
                        {
                            "name": "analyze_suppliers",
                            "arguments": {
                                "project_id": "PRJ-TENDER-001",
                                "user_id": "user-procurement-owner",
                                "as_of": "2027-01-01T00:00:00+08:00",
                                "supplier_id": "SUP-BAT-003",
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "我们可在需求结构化、招标审查和供应商分析等环节提供辅助，并保留证据和人工复核边界。",
        ]
    )
    assistant = EnterpriseAssistantService(_dispatcher(), provider=provider)

    response = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-TENDER-001",
            user_id="user-procurement-owner",
            as_of="2026-10-30T23:59:59+08:00",
            audience="customer",
            message="你们的智能招采能力有哪些？",
        )
    )

    assert response.tool_name == "search_knowledge"
    assert len(response.tool_calls) == 1
    arguments = response.tool_calls[0]["params"]["arguments"]
    assert arguments["project_id"] == "PUBLIC-CAPABILITIES"
    assert arguments["user_id"] == "external-customer"
    assert {citation for citation in response.citations} <= {
        "CAP-AI-PROCESS",
        "CAP-SMART-PROCUREMENT",
        "SOL-AUTOMOTIVE-PROCUREMENT",
    }
    assert "SUP-BAT" not in response.model_dump_json()


def test_internal_agent_plans_multiple_tools_but_cannot_override_context() -> None:
    provider = SequenceProvider(
        [
            json.dumps(
                {
                    "tool_calls": [
                        {
                            "name": "analyze_suppliers",
                            "arguments": {
                                "supplier_id": "SUP-BAT-003",
                                "project_id": "PRJ-AUTO-001",
                                "user_id": "user-observer",
                            },
                        },
                        {
                            "name": "search_communication",
                            "arguments": {
                                "query": "证书过期",
                                "as_of": "2026-08-14T00:00:00+08:00",
                            },
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            "供应商三未进入推荐与证书过期风险有关，相关结论应结合来源记录人工复核。",
        ]
    )
    assistant = EnterpriseAssistantService(_dispatcher(), provider=provider)
    request = EnterpriseAssistantRequest(
        project_id="PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
        audience="internal",
        message="供应商三为什么没推荐，相关沟通怎么说？",
    )

    response = assistant.answer(request)

    assert [call["params"]["name"] for call in response.tool_calls] == [
        "analyze_suppliers",
        "search_communication",
    ]
    for call in response.tool_calls:
        arguments = call["params"]["arguments"]
        assert arguments["project_id"] == request.project_id
        assert arguments["user_id"] == request.user_id
        assert arguments["as_of"] == request.as_of
    assert "SRC-TENDER-019" in response.citations
    assert len(provider.calls) == 2


def test_invalid_llm_plan_falls_back_to_deterministic_mcp_routing() -> None:
    assistant = EnterpriseAssistantService(
        _dispatcher(), provider=SequenceProvider(["not-json", "unused"])
    )

    response = assistant.answer(
        EnterpriseAssistantRequest(
            project_id="PRJ-TENDER-001",
            user_id="user-procurement-owner",
            as_of="2026-10-30T23:59:59+08:00",
            audience="internal",
            message="供应商三为什么未进入推荐？",
        )
    )

    assert response.tool_name == "analyze_suppliers"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["params"]["name"] == "analyze_suppliers"

