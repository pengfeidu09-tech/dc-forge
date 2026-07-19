# B-M6: Solution Agent 与真实大模型 API 接入

**状态：** implemented

## Agent 架构

Solution Agent 在现有确定性工具之上，使用大模型 API 进行：
- 意图识别（compile / review / recompile / explain）
- 约束结构化（自然语言 → BusinessConstraint）
- 工具选择和调度
- 结果解释

大模型**不直接生成** SolutionBundle、review_score、组件列表、节点 Diff 等业务结果。

## Provider 抽象

- `LLMProvider` Protocol（依赖注入）
- `OpenAICompatibleProvider`：httpx 调用 Chat Completions API
- `FakeLLMProvider`：测试用预设响应

环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`

## 工具列表

Agent 只允许调用：
1. `compile_solution`
2. `review_solution`
3. `recompile_solution`
4. `validate_constraints`
5. `retrieve_components`

## 真实模型与确定性工具的边界

| 职责 | 执行者 |
|---|---|
| 意图识别 | LLM |
| 约束结构化 | LLM → BusinessConstraint.model_validate |
| 工具选择 | Agent（基于 LLM 意图） |
| SolutionBundle 生成 | compile_solution（确定性） |
| review_score 计算 | review_solution（确定性） |
| RecompileResult Diff | recompile_solution（确定性） |
| 结果解释 | LLM |

## 实现文件

- `backend/app/solution/llm_provider.py` — Provider 抽象与实现
- `backend/app/solution/agent.py` — Agent 核心
- `backend/app/solution/api.py` — 增加 POST /agent/solution
- `scripts/smoke_solution_agent.py` — 真实 API 冒烟脚本
- `docs/solution-agent-setup.md` — 配置说明

## 测试文件

- `tests/solution/test_llm_provider.py` — 5 个 Provider 测试
- `tests/solution/test_solution_agent.py` — 15 个 Agent 测试
- `tests/solution/test_solution_agent_api.py` — 4 个 API 测试

## 验证命令

```bash
.venv/Scripts/python.exe -m pytest tests -q
```

## 实际测试结果

- test_llm_provider: 5 passed
- test_solution_agent: 15 passed
- test_solution_agent_api: 4 passed
- tests (全量): 152 passed

## 真实 API 冒烟结果

**验证日期：** 2026-07-17
**服务类型：** OpenAI-compatible（阿里云百炼 DashScope）
**模型名称：** qwen3.7-plus
**API Key：** 未记录（仅存在于环境变量，未写入任何文件）

### compile 指令

- 意图：compile ✅
- 工具调用：Step 2: compile_solution (success) — 生成 3 套方案
- 返回方案：conservative (83.7) / balanced (84.7) / innovative (82.6)
- balanced solution_id：procurement-demo-001-balanced-v1

### recompile 指令

- 意图：recompile ✅
- 工具调用：Step 2: recompile_solution (success) — v1→v2
- previous_solution_id：procurement-demo-001-balanced-v1
- new_solution.solution_id：procurement-demo-001-balanced-v2
- added_component_ids：['data-masking', 'local-model']
- changed_node_ids：11 个
- 约束通过 BusinessConstraint 校验 ✅

### 安全验证

- 输出中无 API Key ✅
- 无 Authorization 头 ✅
- 无 Bearer token ✅
- Agent 业务结果全部来自确定性工具 ✅
- LLM 未直接覆盖 review_score / components / nodes / diff ✅

### 回归测试

- test_llm_provider: 5 passed
- test_solution_agent: 15 passed
- test_solution_agent_api: 4 passed
- tests (全量): 152 passed

**本次结果只证明 API 和工具调用链可用，不代表真实业务效果。**

## 当前限制

- Agent 最大步数为 4，复杂场景可能不够
- LLM 失败时仅支持 compile 回退
- 无对话历史（单轮交互）
- 真实 API 已验证可用（qwen3.7-plus），但不在 CI 中自动运行
