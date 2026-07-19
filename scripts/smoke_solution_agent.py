#!/usr/bin/env python
"""Solution Agent 真实 API 冒烟测试。

只在环境变量 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 存在时运行。
不写入 fixture，不产生真实业务结论，不打印 API Key。

用法：
    # 先设置环境变量
    export LLM_API_KEY="sk-xxx"
    export LLM_BASE_URL="https://api.example.com/v1"
    export LLM_MODEL="gpt-4o-mini"

    # 运行
    .venv/Scripts/python.exe scripts/smoke_solution_agent.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.contracts.process import ProcessSpec
from backend.app.solution import compile_solution
from backend.app.solution.agent import AgentRequest, run_solution_agent
from backend.app.solution.llm_provider import OpenAICompatibleProvider


def main() -> int:
    # 检查环境变量
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "")

    if not api_key or not base_url or not model:
        print("ERROR: 请设置 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 环境变量")
        print("参考 .env.example 和 docs/solution-agent-setup.md")
        return 1

    print(f"模型: {model}")
    print(f"API: {base_url}")
    print()

    # 加载 process_spec
    spec_path = ROOT / "data" / "fixtures" / "process_spec.json"
    spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
    process = ProcessSpec.model_validate(spec_data)

    # 获取 balanced 方案
    bundle = compile_solution(process)
    balanced = next(p for p in bundle.plans if p.plan_type == "balanced")

    provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url, model=model)

    # 指令一：compile
    print("=" * 60)
    print("指令一: 请根据当前采购流程生成三套方案，并推荐最平衡的一套。")
    print("=" * 60)
    request1 = AgentRequest(
        process=process,
        message="请根据当前采购流程生成三套方案，并推荐最平衡的一套。",
    )
    result1 = run_solution_agent(request1, provider=provider)
    print(f"意图: {result1.intent}")
    print(f"工具调用: {len(result1.tool_calls)} 次")
    for tc in result1.tool_calls:
        print(f"  Step {tc.step}: {tc.tool_name} ({tc.status}) - {tc.summary}")
    if result1.solution_bundle:
        for plan in result1.solution_bundle.plans:
            print(f"  {plan.plan_type}: {plan.solution_id}, score={plan.review_score:.1f}")
    if result1.warnings:
        print(f"警告: {result1.warnings}")
    print(f"回答: {result1.answer[:200]}")
    print()

    # 指令二：recompile
    print("=" * 60)
    print("指令二: 客户要求发票敏感数据不得出域，必须脱敏、本地处理并记录审计日志，请更新 balanced 方案。")
    print("=" * 60)
    request2 = AgentRequest(
        process=process,
        message="客户要求发票敏感数据不得出域，必须脱敏、本地处理并记录审计日志，请更新 balanced 方案。",
        selected_solution=balanced,
    )
    result2 = run_solution_agent(request2, provider=provider)
    print(f"意图: {result2.intent}")
    print(f"工具调用: {len(result2.tool_calls)} 次")
    for tc in result2.tool_calls:
        print(f"  Step {tc.step}: {tc.tool_name} ({tc.status}) - {tc.summary}")
    if result2.recompile_result:
        rr = result2.recompile_result
        print(f"  {rr.previous_solution_id} → {rr.new_solution.solution_id}")
        print(f"  added: {rr.added_component_ids}")
        print(f"  changed_nodes: {len(rr.changed_node_ids)}")
    if result2.warnings:
        print(f"警告: {result2.warnings}")
    print(f"回答: {result2.answer[:200]}")
    print()

    print("冒烟测试完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
