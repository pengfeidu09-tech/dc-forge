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

环境变量未设置，smoke 脚本正确检测并提示配置。真实 API 调用需用户配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 后运行 `scripts/smoke_solution_agent.py`。

## 当前限制

- 真实 API 尚未在 CI 中验证（需用户手动配置密钥）
- Agent 最大步数为 4，复杂场景可能不够
- LLM 失败时仅支持 compile 回退
- 无对话历史（单轮交互）
