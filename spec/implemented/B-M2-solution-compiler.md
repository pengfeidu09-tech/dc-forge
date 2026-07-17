# B-M2: SolutionCompiler 三套方案编译器

**状态：** implemented

## 目标

接收成员 A 输出的 `ProcessSpec`，调用 B-M1 的能力检索器，根据三种实施策略生成恰好三套符合公共合同的 `SolutionPlan`，并封装为 `SolutionBundle`。

## 公开入口

```python
from backend.app.solution import compile_solution
compile_solution(process: ProcessSpec) -> SolutionBundle
```

## 输入

`ProcessSpec`

## 输出

`SolutionBundle`，包含 conservative、balanced、innovative 三套 `SolutionPlan`。

## 验收标准（全部通过 ✅）

1. 返回对象是 `SolutionBundle` ✅
2. `project_id` 等于输入 `ProcessSpec.project_id` ✅
3. `plans` 长度恰好为 3 ✅
4. `plan_type` 集合恰好为 conservative、balanced、innovative ✅
5. `solution_id` 唯一且稳定 ✅
6. `source_project_id` 全部等于输入 `project_id` ✅
7. 每套方案至少选择一个真实存在于能力胶囊库的组件 ✅
8. `selected_components` 全部是公共 `ComponentRef` ✅
9. `to_be_nodes` 全部是公共 `WorkflowNode` ✅
10. 所有 `WorkflowNode.next_ids` 指向同一方案中真实存在的节点 ✅
11. 不允许悬空 `next_id` ✅
12. 每套方案都保留输入中的 `BusinessConstraint` ✅
13. 三套方案都有 `human_gate=true` 节点 ✅
14. conservative 人工控制程度不低于 balanced（2 gates vs 1 gate）✅
15. innovative 自动化组件数量不低于 balanced（12 vs 8）✅
16. 三套方案不完全相同 ✅
17. 同一输入重复编译结果一致 ✅
18. 不修改传入的 `ProcessSpec` ✅
19. `assumptions` 只记录真实假设 ✅
20. `warnings` 记录 Reviewer 未执行 ✅
21. `review_score` 固定为 0.0 ✅
22. 输出通过 `SolutionBundle.model_validate` ✅
23. `data/fixtures/solution_bundle.json` 已更新为三套方案 ✅
24. fixture 通过既有合同测试 ✅

## 实现文件

- `backend/app/solution/compiler.py` — SolutionCompiler 核心实现
- `backend/app/solution/service.py` — 服务入口（委托 compiler.py）
- `backend/app/solution/__init__.py` — 公开导出 compile_solution
- `data/fixtures/solution_bundle.json` — 三套方案联调 fixture

## 测试文件

- `tests/solution/test_compiler.py` — 16 个编译器行为测试
- `tests/solution/test_solution_fixture.py` — 6 个 fixture 校验测试

## 验证命令

```bash
.venv/Scripts/python.exe -m pytest tests/solution -q
.venv/Scripts/python.exe -m pytest tests/test_contracts.py -q
.venv/Scripts/python.exe -m pytest tests -q
```

## 实际测试结果

- tests/solution: 34 passed（B-M1 12 + B-M2 22）
- tests/test_contracts.py: 3 passed
- tests (全量): 37 passed

## 三套方案概要

| 策略 | 组件数 | 节点数 | human_gate 数 | 自动化组件数 |
|---|---|---|---|---|
| conservative | 6 | 6 | 2 | 5 |
| balanced | 9 | 9 | 1 | 8 |
| innovative | 13 | 13 | 1 | 12 |

## 当前限制

- `review_score` 固定为 0.0，等待 B-M3 的 Reviewer 模块更新；
- 硬约束校验尚未实现（B-M3 将实现完整约束校验）；
- 增量重编译（RecompileResult）尚未实现（B-M4）；
- FastAPI 路由尚未实现（B-M4）；
- 工作流为线性链，未支持分支和并行。

## 后续任务

- B-M3：硬约束校验 + Reviewer 正式评分
- B-M4：增量重编译 + FastAPI 路由
