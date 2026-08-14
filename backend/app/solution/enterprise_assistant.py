"""Project AI assistant that routes every business action through MCP tools."""

from __future__ import annotations

from itertools import count
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.solution.mcp_server import MCPDispatcher


class _AssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnterpriseAssistantRequest(_AssistantModel):
    project_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=12000)


class EnterpriseAssistantResponse(_AssistantModel):
    answer: str
    tool_name: str
    tool_call: dict[str, Any]
    citations: list[str] = []
    results: list[dict[str, Any]] = []
    solution_bundle: dict[str, Any] | None = None
    insufficient_evidence: bool = False
    data_classification: str = "synthetic_demo"


class EnterpriseAssistantService:
    """Deterministic routing layer suitable for web, Feishu, and other bots."""

    def __init__(self, dispatcher: MCPDispatcher) -> None:
        self.dispatcher = dispatcher
        self._ids = count(1)

    @staticmethod
    def _route(message: str) -> str:
        if any(word in message for word in ("项目目前", "项目数据", "有哪些数据", "项目概览")):
            return "get_project_dashboard"
        if any(word in message for word in ("合同金额", "发票", "对账", "收付款", "财务复算")):
            return "get_financial_reconciliation"
        if any(word in message for word in ("追踪", "追溯", "上下游", "关联链")):
            return "trace_business_object"
        if any(word in message for word in ("沟通", "邮件", "会议", "电话", "谁说")):
            return "search_communication"
        if any(word in message for word in ("决策", "决定", "批准原因")):
            return "get_decision_history"
        if any(word in message for word in ("生成", "方案", "编制方案")):
            return "generate_solution_bundle"
        if any(word in message for word in ("供应商", "资质", "交付", "PPM", "诉讼", "信用")):
            return "analyze_suppliers"
        if any(word in message for word in ("审查", "招标文件", "合同草案", "规则")):
            return "review_tender_document"
        if any(word in message for word in ("需求版本", "当时", "历史", "基线")):
            return "get_requirement_history"
        return "search_knowledge"

    @staticmethod
    def _supplier_id(message: str) -> str | None:
        aliases = {
            "供应商一": "SUP-BAT-001",
            "供应商1": "SUP-BAT-001",
            "SUP-BAT-001": "SUP-BAT-001",
            "供应商二": "SUP-BAT-002",
            "供应商2": "SUP-BAT-002",
            "SUP-BAT-002": "SUP-BAT-002",
            "供应商三": "SUP-BAT-003",
            "供应商3": "SUP-BAT-003",
            "SUP-BAT-003": "SUP-BAT-003",
            "供应商四": "SUP-BAT-004",
            "供应商4": "SUP-BAT-004",
            "SUP-BAT-004": "SUP-BAT-004",
            "供应商五": "SUP-BAT-005",
            "供应商5": "SUP-BAT-005",
            "SUP-BAT-005": "SUP-BAT-005",
        }
        return next((supplier_id for alias, supplier_id in aliases.items() if alias in message), None)

    @staticmethod
    def _document_id(message: str) -> str:
        for prefix in ("CONTROL-", "DEFECT-"):
            position = message.upper().find(prefix)
            if position >= 0:
                candidate = message.upper()[position : position + len(prefix) + 2]
                if candidate[-2:].isdigit():
                    return candidate
        return "DEFECT-01"

    @staticmethod
    def _object_id(message: str, supplier_id: str | None) -> str:
        for token in message.replace("，", " ").replace("。", " ").split():
            if token.startswith(("CON-BAT-", "REQ-BAT-", "TENDER-BAT-", "PRJ-TENDER-")):
                return token.strip("？?；;")
        return supplier_id or "REQ-BAT-001"

    @staticmethod
    def _citations(tool_name: str, result: dict[str, Any]) -> list[str]:
        if tool_name == "search_knowledge":
            return list(
                dict.fromkeys(
                    row["source_id"] for row in result.get("results", [])[:3]
                )
            )
        if tool_name == "analyze_suppliers":
            return sorted(
                {
                    source_id
                    for supplier in result.get("suppliers", [])
                    for source_id in supplier.get("source_ids", [])
                }
            )
        if tool_name == "review_tender_document":
            return list(result.get("evidence", []))
        if tool_name in {"get_decision_history", "search_communication"}:
            return list(result.get("evidence", []))
        if tool_name == "get_financial_reconciliation":
            return list(result.get("evidence_ids", []))
        if tool_name == "get_requirement_history":
            return [version["requirement_version_id"] for version in result.get("versions", [])]
        return []

    @staticmethod
    def _answer_text(tool_name: str, result: dict[str, Any]) -> str:
        if tool_name == "generate_solution_bundle":
            plans = result.get("plans", [])
            names = "、".join(plan["name"] for plan in plans)
            return f"已通过MCP生成{names}。全部基于模拟验收数据，不代表真实业务成果。"
        if tool_name == "get_project_dashboard":
            project = result["project"]
            metrics = "、".join(
                f"{key}={value}" for key, value in result.get("metrics", {}).items()
            )
            return f"已通过MCP读取{project['project_name']}的模拟驾驶舱：{metrics}。"
        if tool_name == "analyze_suppliers":
            suppliers = result.get("suppliers", [])
            risky = [
                supplier["supplier_name"]
                for supplier in suppliers
                if any(risk["level"] in {"high", "critical"} for risk in supplier["risk_records"])
            ]
            suffix = f"；高风险或关键风险供应商包括：{'、'.join(risky)}" if risky else ""
            return f"已通过MCP读取{len(suppliers)}家供应商的限定范围画像{suffix}。评分仅作为人工决策输入。"
        if tool_name == "review_tender_document":
            findings = result.get("findings", [])
            return f"已通过MCP读取文档审查结果，共{len(findings)}项预期命中；所有高影响结论仍需人工复核。"
        if tool_name == "get_decision_history":
            timeline = result.get("timeline", [])
            return f"已通过MCP找到{len(timeline)}条与该决定或对象相关的沟通证据；请结合来源时间线人工判断原因。"
        if tool_name == "search_communication":
            return f"已通过MCP找到{len(result.get('records', []))}条有权限且在时间点内的沟通记录。"
        if tool_name == "trace_business_object":
            return f"已通过MCP追踪到{len(result.get('nodes', []))}个业务对象和{len(result.get('edges', []))}条关系。"
        if tool_name == "get_financial_reconciliation":
            return f"已通过MCP完成模拟合同复算，发现{len(result.get('differences', []))}项金额差异；结果不是实际财务结论。"
        if tool_name == "get_requirement_history":
            return f"已通过MCP读取{len(result.get('versions', []))}个截至查询时间已记录的需求版本，当前适用版本为{result.get('applicable_version_id') or '无'}。"
        rows = result.get("results", [])
        if not rows:
            return "当前权限和时间点下没有足够证据回答该问题。"
        summaries = "；".join(row["content"] for row in rows[:3])
        return f"根据MCP检索到的模拟证据：{summaries}"

    def answer(self, request: EnterpriseAssistantRequest) -> EnterpriseAssistantResponse:
        tool_name = self._route(request.message)
        if request.project_id != "PRJ-TENDER-001" and tool_name not in {
            "get_project_dashboard",
            "get_requirement_history",
            "search_knowledge",
        }:
            tool_name = "search_knowledge"
        arguments: dict[str, Any] = {
            "project_id": request.project_id,
            "user_id": request.user_id,
        }
        supplier_id = self._supplier_id(request.message)
        if tool_name in {
            "get_project_dashboard",
            "search_knowledge",
            "get_requirement_history",
            "analyze_suppliers",
            "generate_solution_bundle",
            "get_decision_history",
            "search_communication",
            "trace_business_object",
            "get_financial_reconciliation",
        }:
            arguments["as_of"] = request.as_of
        if tool_name == "search_knowledge":
            arguments["query"] = request.message
        elif tool_name == "get_requirement_history":
            arguments["requirement_id"] = {
                "PRJ-KM-001": "REQ-001",
                "PRJ-AUTO-001": "REQ-AUTO-001",
                "PRJ-TENDER-001": "REQ-BAT-001",
            }.get(request.project_id, "REQ-BAT-001")
        elif tool_name == "review_tender_document":
            arguments["document_id"] = self._document_id(request.message)
            arguments["as_of"] = request.as_of
        elif tool_name == "get_decision_history":
            arguments["decision_or_object_id"] = supplier_id or "REQ-BAT-001"
        elif tool_name == "search_communication":
            arguments["query"] = request.message
        elif tool_name == "trace_business_object":
            arguments["object_id"] = self._object_id(request.message, supplier_id)
        elif tool_name == "get_financial_reconciliation":
            arguments["contract_id"] = (
                "CON-BAT-002" if "合同二" in request.message else "CON-BAT-001"
            )
        elif tool_name == "analyze_suppliers" and supplier_id:
            arguments["supplier_id"] = supplier_id
        tool_call = {
            "jsonrpc": "2.0",
            "id": f"assistant-{next(self._ids)}",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        response = self.dispatcher.handle(tool_call)
        if response is None or "error" in response:
            message = response["error"]["message"] if response else "MCP returned no response"
            if response and response["error"].get("code") == -32003:
                raise PermissionError(message)
            raise RuntimeError(message)
        result = response["result"]["structuredContent"]
        citations = self._citations(tool_name, result)
        return EnterpriseAssistantResponse(
            answer=self._answer_text(tool_name, result),
            tool_name=tool_name,
            tool_call=tool_call,
            citations=citations,
            results=result.get("results", []),
            solution_bundle=(result if tool_name == "generate_solution_bundle" else None),
            insufficient_evidence=bool(result.get("insufficient_evidence", False)),
        )
