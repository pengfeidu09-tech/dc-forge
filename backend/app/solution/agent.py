"""Solution Agent — 使用大模型进行意图识别和工具调度。

大模型负责：意图识别、约束结构化、工具选择、结果解释。
确定性工具负责：所有业务结果（SolutionBundle、review_score、Diff 等）。
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import (
    RecompileRequest,
    RecompileResult,
    SolutionBundle,
    SolutionPlan,
)
from backend.app.solution.constraints import validate_constraints
from backend.app.solution.llm_provider import LLMProvider, LLMResponse
from backend.app.solution.reviewer import SolutionReviewResult, review_solution


# ---------------------------------------------------------------------------
# 私有模型
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Agent 请求。"""

    model_config = ConfigDict(extra="forbid")

    process: ProcessSpec
    message: str
    selected_solution: SolutionPlan | None = None


class AgentToolCall(BaseModel):
    """单次工具调用记录。"""

    model_config = ConfigDict(extra="forbid")

    step: int
    tool_name: str
    arguments: dict
    status: Literal["success", "failed"]
    summary: str


class AgentResponse(BaseModel):
    """Agent 响应。"""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["compile", "review", "recompile", "explain"]
    answer: str
    solution_bundle: SolutionBundle | None = None
    recompile_result: RecompileResult | None = None
    review: SolutionReviewResult | None = None
    tool_calls: list[AgentToolCall] = []
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# 允许的工具注册表
# ---------------------------------------------------------------------------

_ALLOWED_TOOLS = frozenset({
    "compile_solution",
    "review_solution",
    "recompile_solution",
    "validate_constraints",
    "retrieve_components",
})


# ---------------------------------------------------------------------------
# 系统提示
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are DCForge Solution Agent. Analyze the user message and respond with ONLY a JSON object (no markdown).

Available intents: compile, review, recompile, explain

Rules:
- "compile": user wants to generate solution plans from process spec
- "review": user wants to review/evaluate an existing solution (requires selected_solution)
- "recompile": user wants to add new constraints and recompile (requires selected_solution)
- "explain": user wants explanation of existing results

For "recompile", extract the constraint from user message into:
{
  "intent": "recompile",
  "constraint": {
    "id": "constraint-<type>-<number>",
    "type": "security|approval|data|risk|budget|time",
    "statement": "<full statement from user>",
    "hard": true,
    "parameters": {}
  },
  "missing_info": null,
  "answer": "<brief>"
}

If essential constraint info is missing (id, type, statement), set constraint to null and explain in missing_info.

Respond format:
{"intent": "...", "constraint": null or {...}, "missing_info": null or "...", "answer": "..."}
"""


def _build_user_message(request: AgentRequest) -> str:
    """构建发送给 LLM 的用户消息。"""
    parts = [f"用户指令: {request.message}"]
    parts.append(f"项目: {request.process.project_id}")
    parts.append(f"行业: {request.process.industry}")
    parts.append(f"业务目标: {request.process.business_goal}")
    if request.selected_solution:
        parts.append(f"已选方案: {request.selected_solution.solution_id} ({request.selected_solution.plan_type})")
    else:
        parts.append("已选方案: 无")
    return "\n".join(parts)


def _parse_llm_json(content: str) -> dict | None:
    """解析 LLM 返回的 JSON。"""
    if not content or not content.strip():
        return None
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        # 尝试提取 JSON 块
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
        return None


# ---------------------------------------------------------------------------
# Agent 主函数
# ---------------------------------------------------------------------------


def run_solution_agent(
    request: AgentRequest,
    provider: LLMProvider | None = None,
    max_steps: int = 4,
) -> AgentResponse:
    """运行 Solution Agent。

    Args:
        request: 包含 ProcessSpec、用户消息和可选已选方案。
        provider: LLM Provider，为 None 时尝试从环境变量创建。
        max_steps: 最大执行步数。

    Returns:
        AgentResponse，包含意图、工具调用轨迹和结构化结果。
    """
    from backend.app.solution.llm_provider import OpenAICompatibleProvider

    if provider is None:
        provider = OpenAICompatibleProvider()

    tool_calls: list[AgentToolCall] = []
    warnings: list[str] = []
    step = 0

    # Step 1: LLM 意图识别
    step += 1
    llm_resp = provider.complete([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(request)},
    ])

    if llm_resp.warnings:
        warnings.extend(llm_resp.warnings)

    parsed = _parse_llm_json(llm_resp.content)

    if parsed is None:
        # LLM 失败，回退到确定性 compile
        warnings.append("LLM 意图识别失败，回退到确定性编译")
        return _fallback_compile(request, tool_calls, warnings, step, max_steps)

    intent_raw = parsed.get("intent", "compile")
    if intent_raw not in ("compile", "review", "recompile", "explain"):
        intent_raw = "compile"
    intent = intent_raw  # type: ignore[assignment]

    answer_parts: list[str] = []

    # Step 2-N: 执行工具
    if intent == "compile":
        step, bundle = _do_compile(request, provider, tool_calls, warnings, step, max_steps, answer_parts)
        return AgentResponse(
            intent=intent,
            answer="\n".join(answer_parts),
            solution_bundle=bundle,
            tool_calls=tool_calls,
            warnings=warnings,
        )

    elif intent == "review":
        if request.selected_solution is None:
            warnings.append("review 需要已选方案，但未提供 selected_solution")
            return AgentResponse(
                intent=intent,
                answer="无法执行评审：未提供已选方案。请先编译方案并选择一个。",
                tool_calls=tool_calls,
                warnings=warnings,
            )
        step, review = _do_review(request, tool_calls, warnings, step, max_steps, answer_parts)
        return AgentResponse(
            intent=intent,
            answer="\n".join(answer_parts),
            review=review,
            tool_calls=tool_calls,
            warnings=warnings,
        )

    elif intent == "recompile":
        if request.selected_solution is None:
            warnings.append("recompile 需要已选方案，但未提供 selected_solution")
            return AgentResponse(
                intent=intent,
                answer="无法执行重编译：未提供已选方案。请先编译方案并选择一个。",
                tool_calls=tool_calls,
                warnings=warnings,
            )
        constraint_data = parsed.get("constraint")
        missing_info = parsed.get("missing_info")
        if constraint_data is None:
            msg = missing_info or "无法从用户指令中提取约束信息"
            warnings.append(msg)
            return AgentResponse(
                intent=intent,
                answer=f"无法执行重编译：{msg}",
                tool_calls=tool_calls,
                warnings=warnings,
            )
        step, result = _do_recompile(
            request, constraint_data, tool_calls, warnings, step, max_steps, answer_parts
        )
        if result is None:
            return AgentResponse(
                intent=intent,
                answer="\n".join(answer_parts) or "重编译失败",
                tool_calls=tool_calls,
                warnings=warnings,
            )
        return AgentResponse(
            intent=intent,
            answer="\n".join(answer_parts),
            recompile_result=result,
            tool_calls=tool_calls,
            warnings=warnings,
        )

    else:  # explain
        if request.selected_solution is None:
            warnings.append("explain 需要已选方案")
            return AgentResponse(
                intent=intent,
                answer="无法解释：未提供已选方案。",
                tool_calls=tool_calls,
                warnings=warnings,
            )
        step, review = _do_review(request, tool_calls, warnings, step, max_steps, answer_parts)
        # LLM 解释
        explain_resp = provider.complete([
            {"role": "system", "content": "解释方案评审结果，不修改任何数据。用中文回答。"},
            {"role": "user", "content": f"方案: {request.selected_solution.name}\n评分: {review.score}\n维度: {json.dumps([d.model_dump() for d in review.dimensions], ensure_ascii=False)}"},
        ])
        if explain_resp.content:
            answer_parts.append(explain_resp.content)
        return AgentResponse(
            intent=intent,
            answer="\n".join(answer_parts),
            review=review,
            tool_calls=tool_calls,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# 工具执行辅助
# ---------------------------------------------------------------------------


def _do_compile(
    request: AgentRequest,
    provider: LLMProvider,
    tool_calls: list[AgentToolCall],
    warnings: list[str],
    step: int,
    max_steps: int,
    answer_parts: list[str],
) -> tuple[int, SolutionBundle | None]:
    """执行 compile 意图。"""
    from backend.app.solution.service import compile_solution

    if step >= max_steps:
        warnings.append("达到最大步骤限制")
        return step, None

    step += 1
    try:
        bundle = compile_solution(request.process)
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="compile_solution",
            arguments={"project_id": request.process.project_id},
            status="success",
            summary=f"生成 {len(bundle.plans)} 套方案",
        ))
        balanced = next((p for p in bundle.plans if p.plan_type == "balanced"), None)
        answer_parts.append(f"已生成三套方案：conservative、balanced、innovative。")
        if balanced:
            answer_parts.append(f"推荐 balanced 方案（{balanced.solution_id}），review_score={balanced.review_score:.1f}。")
        return step, bundle
    except Exception as e:
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="compile_solution",
            arguments={"project_id": request.process.project_id},
            status="failed",
            summary=str(e),
        ))
        warnings.append(f"编译失败: {e}")
        return step, None


def _do_review(
    request: AgentRequest,
    tool_calls: list[AgentToolCall],
    warnings: list[str],
    step: int,
    max_steps: int,
    answer_parts: list[str],
) -> tuple[int, SolutionReviewResult]:
    """执行 review 意图。"""
    from backend.app.solution.service import compile_solution

    plan = request.selected_solution  # type: ignore[assignment]
    process = request.process

    # validate_constraints
    if step < max_steps:
        step += 1
        validation = validate_constraints(plan, list(process.constraints))
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="validate_constraints",
            arguments={"solution_id": plan.solution_id, "constraint_count": len(process.constraints)},
            status="success",
            summary=f"passed={validation.passed_count}, failed={validation.failed_count}, unverifiable={validation.unverifiable_count}",
        ))
        answer_parts.append(f"约束校验: {validation.passed_count} 通过, {validation.failed_count} 失败, {validation.unverifiable_count} 不可验证。")

    # review_solution
    if step < max_steps:
        step += 1
        validation = validate_constraints(plan, list(process.constraints))
        review = review_solution(plan, process, validation)
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="review_solution",
            arguments={"solution_id": plan.solution_id},
            status="success",
            summary=f"score={review.score:.1f}, recommendation={review.recommendation}",
        ))
        answer_parts.append(f"方案评分: {review.score:.1f}/100, 建议: {review.recommendation}。")
        for dim in review.dimensions:
            answer_parts.append(f"  {dim.name}: {dim.score:.1f}/{dim.max_score:.0f}")
        return step, review

    warnings.append("达到最大步骤限制")
    validation = validate_constraints(plan, list(process.constraints))
    return step, review_solution(plan, process, validation)


def _do_recompile(
    request: AgentRequest,
    constraint_data: dict,
    tool_calls: list[AgentToolCall],
    warnings: list[str],
    step: int,
    max_steps: int,
    answer_parts: list[str],
) -> tuple[int, RecompileResult | None]:
    """执行 recompile 意图。"""
    # 验证约束
    try:
        constraint = BusinessConstraint.model_validate(constraint_data)
    except Exception as e:
        warnings.append(f"约束校验失败: {e}")
        answer_parts.append(f"约束格式不合法: {e}")
        return step, None

    if step >= max_steps:
        warnings.append("达到最大步骤限制")
        return step, None

    step += 1
    from backend.app.solution.service import recompile_solution

    recompile_req = RecompileRequest(
        process=request.process,
        selected_solution=request.selected_solution,  # type: ignore[arg-type]
        new_constraints=[constraint],
    )
    try:
        result = recompile_solution(recompile_req)
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="recompile_solution",
            arguments={
                "previous_solution_id": result.previous_solution_id,
                "new_constraint_id": constraint.id,
            },
            status="success",
            summary=f"v1→v2, added={result.added_component_ids}, changed_nodes={len(result.changed_node_ids)}",
        ))
        answer_parts.append(f"重编译完成: {result.previous_solution_id} → {result.new_solution.solution_id}")
        if result.added_component_ids:
            answer_parts.append(f"新增组件: {', '.join(result.added_component_ids)}")
        if result.change_explanations:
            answer_parts.append("变更说明: " + "; ".join(result.change_explanations[:3]))
        return step, result
    except Exception as e:
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="recompile_solution",
            arguments={"new_constraint_id": constraint.id},
            status="failed",
            summary=str(e),
        ))
        warnings.append(f"重编译失败: {e}")
        return step, None


def _fallback_compile(
    request: AgentRequest,
    tool_calls: list[AgentToolCall],
    warnings: list[str],
    step: int,
    max_steps: int,
) -> AgentResponse:
    """LLM 失败时回退到确定性编译。"""
    from backend.app.solution.service import compile_solution

    step += 1
    try:
        bundle = compile_solution(request.process)
        tool_calls.append(AgentToolCall(
            step=step,
            tool_name="compile_solution",
            arguments={"project_id": request.process.project_id, "fallback": True},
            status="success",
            summary=f"确定性回退编译成功, {len(bundle.plans)} 套方案",
        ))
        return AgentResponse(
            intent="compile",
            answer="LLM 不可用，已回退到确定性编译。生成了三套方案。",
            solution_bundle=bundle,
            tool_calls=tool_calls,
            warnings=warnings,
        )
    except Exception as e:
        warnings.append(f"回退编译也失败: {e}")
        return AgentResponse(
            intent="compile",
            answer=f"编译失败: {e}",
            tool_calls=tool_calls,
            warnings=warnings,
        )
