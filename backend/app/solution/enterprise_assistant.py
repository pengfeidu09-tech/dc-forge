"""Project AI assistant that routes every business action through MCP tools."""

from __future__ import annotations

import json
from itertools import count
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.solution.llm_provider import LLMProvider
from backend.app.solution.mcp_server import MCPDispatcher


class _AssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnterpriseAssistantRequest(_AssistantModel):
    project_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=12000)
    audience: Literal["customer", "internal"] = "internal"


class EnterpriseAssistantResponse(_AssistantModel):
    answer: str
    tool_name: str
    tool_call: dict[str, Any]
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    solution_bundle: dict[str, Any] | None = None
    insufficient_evidence: bool = False
    data_classification: str = "synthetic_demo"
    warnings: list[str] = Field(default_factory=list)


_CUSTOMER_PROJECT_ID = "PUBLIC-CAPABILITIES"
_CUSTOMER_USER_ID = "external-customer"
_CUSTOMER_TOOLS = frozenset({"search_knowledge"})
_MAX_TOOL_CALLS = 3
_CONTEXT_FIELDS = frozenset({"project_id", "user_id", "as_of"})
_CUSTOMER_FORBIDDEN_OUTPUT = re.compile(
    r"(?i)\b(?:PRJ-|SUP-BAT-|CON-BAT-|SRC-TENDER-|REQ-BAT-)"
)

_PLANNER_PROMPT = """You are the DCForge enterprise tool planner.
Return strict JSON only in this form:
{"tool_calls":[{"name":"<allowed tool>","arguments":{}}]}

Rules:
- Select zero to three tools from the supplied catalog.
- Use tools only when they help answer the latest message.
- Never invent a tool name.
- project_id, user_id, as_of, permissions, and audience are controlled by the
  application. Do not attempt to override them.
- Tools are read-only. High-impact business decisions remain human decisions.
- Customer audience may use only public capability knowledge search.
"""

_SYNTHESIS_PROMPT = """You are the DCForge evidence-grounded assistant.
Write a concise Chinese answer using only the supplied tool evidence.
- Do not invent facts, metrics, outcomes, permissions, or source IDs.
- If evidence is insufficient, say so clearly.
- Preserve human-review boundaries for approvals, supplier selection, contracts,
  payments, and compliance decisions.
- Synthetic project data and simulated metrics are not real business outcomes.
- For a customer audience, do not expose internal project IDs, supplier IDs,
  contract IDs, requirement IDs, tool names, workflow metadata, or private data.
"""


class EnterpriseAssistantService:
    """Audience-aware Agent over the governed MCP dispatcher."""

    def __init__(
        self,
        dispatcher: MCPDispatcher,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.provider = provider
        self._ids = count(1)

    @staticmethod
    def _parse_plan(content: str) -> list[dict[str, Any]] | None:
        payload = content.strip()
        if not payload:
            return None
        if payload.startswith("```") and payload.endswith("```"):
            payload = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload, flags=re.I)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        calls = parsed.get("tool_calls") if isinstance(parsed, dict) else None
        if not isinstance(calls, list):
            return None
        return [call for call in calls if isinstance(call, dict)]

    def _allowed_tools(self, audience: str) -> dict[str, dict[str, Any]]:
        definitions = {
            tool["name"]: tool for tool in self.dispatcher.tool_definitions()
        }
        if audience == "customer":
            return {
                name: definition
                for name, definition in definitions.items()
                if name in _CUSTOMER_TOOLS
            }
        return definitions

    def _plan(
        self, request: EnterpriseAssistantRequest
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        if self.provider is None:
            return [], [], False
        catalog = list(self._allowed_tools(request.audience).values())
        response = self.provider.complete(
            [
                {
                    "role": "system",
                    "content": (
                        f"{_PLANNER_PROMPT}\nAudience: {request.audience}\n"
                        f"Allowed tool catalog:\n{json.dumps(catalog, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": request.message},
            ]
        )
        calls = self._parse_plan(response.content)
        warnings = list(response.warnings)
        if calls is None:
            warnings.append("LLM 工具规划无效，已回退到确定性路由")
            return [], warnings, False
        allowed = self._allowed_tools(request.audience)
        validated: list[dict[str, Any]] = []
        for call in calls[:_MAX_TOOL_CALLS]:
            name = call.get("name")
            arguments = call.get("arguments", {})
            if name not in allowed or not isinstance(arguments, dict):
                continue
            validated.append({"name": name, "arguments": arguments})
        if request.audience == "customer":
            return (
                [{"name": "search_knowledge", "arguments": {}}],
                warnings,
                True,
            )
        return validated, warnings, bool(validated)

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

    def _fallback_plan(
        self, request: EnterpriseAssistantRequest
    ) -> list[dict[str, Any]]:
        if request.audience == "customer":
            return [{"name": "search_knowledge", "arguments": {}}]
        tool_name = self._route(request.message)
        if request.project_id != "PRJ-TENDER-001" and tool_name not in {
            "get_project_dashboard",
            "get_requirement_history",
            "search_knowledge",
        }:
            tool_name = "search_knowledge"
        return [{"name": tool_name, "arguments": {}}]

    def _arguments(
        self,
        request: EnterpriseAssistantRequest,
        tool_name: str,
        planned: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self._allowed_tools(request.audience)[tool_name]
        properties = definition["inputSchema"]["properties"]
        project_id = (
            _CUSTOMER_PROJECT_ID
            if request.audience == "customer"
            else request.project_id
        )
        user_id = (
            _CUSTOMER_USER_ID
            if request.audience == "customer"
            else request.user_id
        )
        defaults: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "as_of": request.as_of,
        }
        supplier_id = self._supplier_id(request.message)
        if tool_name in {"search_knowledge", "search_communication"}:
            defaults["query"] = request.message
        elif tool_name == "get_requirement_history":
            defaults["requirement_id"] = {
                "PRJ-KM-001": "REQ-001",
                "PRJ-AUTO-001": "REQ-AUTO-001",
                "PRJ-TENDER-001": "REQ-BAT-001",
            }.get(project_id, "REQ-BAT-001")
        elif tool_name == "review_tender_document":
            defaults["document_id"] = self._document_id(request.message)
        elif tool_name == "get_decision_history":
            defaults["decision_or_object_id"] = supplier_id or "REQ-BAT-001"
        elif tool_name == "trace_business_object":
            defaults["object_id"] = self._object_id(request.message, supplier_id)
        elif tool_name == "get_financial_reconciliation":
            defaults["contract_id"] = (
                "CON-BAT-002" if "合同二" in request.message else "CON-BAT-001"
            )
        elif tool_name == "analyze_suppliers" and supplier_id:
            defaults["supplier_id"] = supplier_id

        arguments: dict[str, Any] = {}
        for name in properties:
            if name in _CONTEXT_FIELDS:
                if name in defaults:
                    arguments[name] = defaults[name]
                continue
            value = planned.get(name, defaults.get(name))
            if value in (None, ""):
                continue
            if properties[name].get("type") == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    continue
                minimum = properties[name].get("minimum", 1)
                if value < minimum:
                    continue
            arguments[name] = value
        if request.audience == "customer":
            arguments["project_id"] = _CUSTOMER_PROJECT_ID
            arguments["user_id"] = _CUSTOMER_USER_ID
            arguments["as_of"] = request.as_of
            arguments["query"] = request.message
        return arguments

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
    def _answer_text(
        tool_name: str,
        result: dict[str, Any],
        *,
        audience: str = "internal",
    ) -> str:
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
            if audience == "customer":
                return "根据目前可公开的能力资料，暂时没有足够证据回答该问题。"
            return "当前权限和时间点下没有足够证据回答该问题。"
        summaries = "；".join(row["content"] for row in rows[:3])
        if audience == "customer":
            return f"根据我们的公开能力资料：{summaries}"
        return f"根据MCP检索到的模拟证据：{summaries}"

    @staticmethod
    def _synthesis_evidence(
        tool_name: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        keys_by_tool = {
            "get_project_dashboard": ("project", "metrics", "viewer"),
            "search_knowledge": ("results", "insufficient_evidence"),
            "get_requirement_history": (
                "requirement",
                "versions",
                "applicable_version_id",
            ),
            "analyze_suppliers": ("suppliers", "scope", "warnings"),
            "review_tender_document": (
                "findings",
                "human_review_required",
                "evidence",
            ),
            "generate_solution_bundle": ("plans", "as_of", "data_classification"),
            "get_decision_history": ("timeline", "evidence", "current_status"),
            "search_communication": ("records", "evidence", "permission_decision"),
            "trace_business_object": ("nodes", "edges", "warnings"),
            "get_financial_reconciliation": (
                "calculated_contract_amount_cny",
                "differences",
                "evidence_ids",
            ),
        }
        selected = {
            key: result[key]
            for key in keys_by_tool.get(tool_name, tuple(result))
            if key in result
        }
        for key in ("results", "suppliers", "versions", "timeline", "records", "nodes", "edges", "plans"):
            if isinstance(selected.get(key), list):
                selected[key] = selected[key][:5]
        return selected

    def _synthesize(
        self,
        request: EnterpriseAssistantRequest,
        tool_results: list[tuple[str, dict[str, Any]]],
    ) -> tuple[str | None, list[str]]:
        if self.provider is None:
            return None, []
        evidence = [
            {
                "tool": tool_name,
                "result": self._synthesis_evidence(tool_name, result),
            }
            for tool_name, result in tool_results
        ]
        response = self.provider.complete(
            [
                {
                    "role": "system",
                    "content": f"{_SYNTHESIS_PROMPT}\nAudience: {request.audience}",
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{request.message}\n\nTool evidence:\n"
                        f"{json.dumps(evidence, ensure_ascii=False)}"
                    ),
                },
            ]
        )
        answer = response.content.strip()
        if not answer:
            return None, list(response.warnings)
        if request.audience == "customer" and _CUSTOMER_FORBIDDEN_OUTPUT.search(answer):
            return None, [*response.warnings, "客户回答包含内部标识，已使用确定性回退"]
        return answer, list(response.warnings)

    def answer(self, request: EnterpriseAssistantRequest) -> EnterpriseAssistantResponse:
        planned, warnings, llm_plan_valid = self._plan(request)
        if not planned:
            planned = self._fallback_plan(request)
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[tuple[str, dict[str, Any]]] = []
        citations: list[str] = []
        for plan in planned[:_MAX_TOOL_CALLS]:
            tool_name = plan["name"]
            arguments = self._arguments(
                request, tool_name, plan.get("arguments", {})
            )
            tool_call = {
                "jsonrpc": "2.0",
                "id": f"assistant-{next(self._ids)}",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
            tool_calls.append(tool_call)
            response = self.dispatcher.handle(tool_call)
            if response is None or "error" in response:
                message = (
                    response["error"]["message"]
                    if response
                    else "MCP returned no response"
                )
                if response and response["error"].get("code") == -32003:
                    raise PermissionError(message)
                warnings.append(f"{tool_name}: {message}")
                continue
            result = response["result"]["structuredContent"]
            tool_results.append((tool_name, result))
            citations.extend(self._citations(tool_name, result))
        if not tool_results:
            raise RuntimeError("all planned MCP tool calls failed")

        primary_tool, primary_result = tool_results[0]
        deterministic_answer = "\n".join(
            self._answer_text(name, result, audience=request.audience)
            for name, result in tool_results
        )
        answer = deterministic_answer
        if llm_plan_valid:
            synthesized, synthesis_warnings = self._synthesize(request, tool_results)
            warnings.extend(synthesis_warnings)
            if synthesized:
                answer = synthesized
        if (
            request.audience == "internal"
            and any(
                result.get("data_classification") == "synthetic_demo"
                for _, result in tool_results
            )
            and "模拟" not in answer
        ):
            answer += "\n\n以上内容基于模拟演示数据，仅供验证流程，不代表真实业务成果；高影响结论仍需人工复核。"
        unique_citations = list(dict.fromkeys(citations))
        solution_bundle = next(
            (
                result
                for name, result in tool_results
                if name == "generate_solution_bundle"
            ),
            None,
        )
        return EnterpriseAssistantResponse(
            answer=answer,
            tool_name=primary_tool,
            tool_call=tool_calls[0],
            tool_calls=tool_calls,
            citations=unique_citations,
            results=primary_result.get("results", []),
            solution_bundle=solution_bundle,
            insufficient_evidence=bool(
                primary_result.get("insufficient_evidence", False)
            ),
            data_classification=primary_result.get(
                "data_classification", "synthetic_demo"
            ),
            warnings=warnings,
        )
