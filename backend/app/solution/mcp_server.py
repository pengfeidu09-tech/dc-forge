"""Minimal MCP JSON-RPC server exposing governed enterprise knowledge tools."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable

from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


class MCPDispatcher:
    """Handle the MCP methods needed by stdio, HTTP, agents, and tests."""

    def __init__(self, service: EnterpriseKnowledgeService) -> None:
        self.service = service
        text = {"type": "string"}
        integer = {"type": "integer", "minimum": 1}
        self._tools: dict[str, tuple[dict[str, Any], Callable[..., Any]]] = {
            "list_projects": (
                _object_schema({"user_id": text, "as_of": text}, []),
                lambda **_: {"projects": self.service.list_projects()},
            ),
            "get_project_dashboard": (
                _object_schema(
                    {"project_id": text, "user_id": text, "as_of": text},
                    ["project_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.get_project_dashboard(**args),
            ),
            "search_knowledge": (
                _object_schema(
                    {
                        "project_id": text,
                        "query": text,
                        "user_id": text,
                        "as_of": text,
                        "limit": integer,
                    },
                    ["project_id", "query", "user_id", "as_of"],
                ),
                lambda **args: self.service.search_knowledge(**args),
            ),
            "search_solution_cases": (
                _object_schema(
                    {"query": text, "limit": integer},
                    ["query"],
                ),
                lambda **args: self.service.search_solution_cases(**args),
            ),
            "get_requirement_history": (
                _object_schema(
                    {
                        "project_id": text,
                        "requirement_id": text,
                        "user_id": text,
                        "as_of": text,
                    },
                    ["project_id", "requirement_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.get_requirement_history(**args),
            ),
            "analyze_suppliers": (
                _object_schema(
                    {
                        "project_id": text,
                        "user_id": text,
                        "as_of": text,
                        "supplier_id": text,
                    },
                    ["project_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.analyze_suppliers(**args),
            ),
            "review_tender_document": (
                _object_schema(
                    {
                        "project_id": text,
                        "document_id": text,
                        "user_id": text,
                        "as_of": text,
                    },
                    ["project_id", "document_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.review_tender_document(**args),
            ),
            "generate_solution_bundle": (
                _object_schema(
                    {"project_id": text, "user_id": text, "as_of": text},
                    ["project_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.generate_solution_bundle(**args),
            ),
            "get_decision_history": (
                _object_schema(
                    {
                        "project_id": text,
                        "decision_or_object_id": text,
                        "user_id": text,
                        "as_of": text,
                    },
                    ["project_id", "decision_or_object_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.get_decision_history(**args),
            ),
            "search_communication": (
                _object_schema(
                    {
                        "project_id": text,
                        "query": text,
                        "user_id": text,
                        "as_of": text,
                        "channel": text,
                    },
                    ["project_id", "query", "user_id", "as_of"],
                ),
                lambda **args: self.service.search_communication(**args),
            ),
            "trace_business_object": (
                _object_schema(
                    {
                        "project_id": text,
                        "object_id": text,
                        "user_id": text,
                        "as_of": text,
                        "direction": text,
                        "max_depth": integer,
                    },
                    ["project_id", "object_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.trace_business_object(**args),
            ),
            "get_financial_reconciliation": (
                _object_schema(
                    {
                        "project_id": text,
                        "contract_id": text,
                        "user_id": text,
                        "as_of": text,
                    },
                    ["project_id", "contract_id", "user_id", "as_of"],
                ),
                lambda **args: self.service.get_financial_reconciliation(**args),
            ),
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        descriptions = {
            "list_projects": "列出企业内部可访问的模拟项目索引。",
            "get_project_dashboard": "读取采购九阶段、数据量、需求、供应商、审查与方案驾驶舱。",
            "search_knowledge": "按用户ACL和as_of时间检索知识，并返回来源和脱敏字段。",
            "search_solution_cases": "从数据库检索已沉淀的历史问题与解决方案案例。",
            "get_requirement_history": "读取需求版本历史和指定时间点适用版本。",
            "analyze_suppliers": "读取限定时间、工厂和品类的供应商画像与风险。",
            "review_tender_document": "读取文档审查黄金样本的规则命中并要求人工复核。",
            "generate_solution_bundle": "从客户确认需求真相生成保守、均衡和创新三套方案。",
            "get_decision_history": "沿沟通与来源返回业务决定的时间线和证据。",
            "search_communication": "在沟通ACL和时间范围内检索电话、会议、邮件和即时消息。",
            "trace_business_object": "沿需求、招标、合同和供应商稳定ID追踪上下游关系。",
            "get_financial_reconciliation": "复算合同金额并返回有权限的模拟财务摘要。",
        }
        return [
            {
                "name": name,
                "description": descriptions[name],
                "inputSchema": schema,
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
            }
            for name, (schema, _) in self._tools.items()
        ]

    @staticmethod
    def _success(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0":
            return self._error(request_id, -32600, "invalid JSON-RPC request")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "params must be an object")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            version = params.get("protocolVersion") or "2025-03-26"
            return self._success(
                request_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "dcforge-enterprise-knowledge",
                        "version": "1.0.0",
                    },
                    "instructions": (
                        "All data is synthetic_demo. Apply user_id and as_of controls; "
                        "never represent simulated metrics as real business outcomes."
                    ),
                },
            )
        if method == "ping":
            return self._success(request_id, {})
        if method == "tools/list":
            return self._success(request_id, {"tools": self.tool_definitions()})
        if method != "tools/call":
            return self._error(request_id, -32601, f"method not found: {method}")
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in self._tools:
            return self._error(request_id, -32602, f"unknown tool: {name}")
        if not isinstance(arguments, dict):
            return self._error(request_id, -32602, "tool arguments must be an object")
        try:
            result = self._tools[name][1](**arguments)
        except PermissionError as error:
            return self._error(request_id, -32003, str(error))
        except (TypeError, ValueError) as error:
            return self._error(request_id, -32602, str(error))
        text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        return self._success(
            request_id,
            {
                "content": [{"type": "text", "text": text}],
                "structuredContent": result,
                "isError": False,
            },
        )


def default_dispatcher() -> MCPDispatcher:
    repository_root = Path(__file__).resolve().parents[3]
    return MCPDispatcher(EnterpriseKnowledgeService(repository_root))


def main() -> int:
    dispatcher = default_dispatcher()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = dispatcher.handle(request)
        except (json.JSONDecodeError, ValueError) as error:
            response = MCPDispatcher._error(None, -32700, str(error))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
