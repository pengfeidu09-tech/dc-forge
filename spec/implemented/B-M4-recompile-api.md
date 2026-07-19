# B-M4: 约束增量重编译与 FastAPI 接口

**状态：** implemented

## 目标

接收原 ProcessSpec、已选择 SolutionPlan 和新增约束，重新编译同一策略方案，输出新 SolutionPlan 和变化 Diff。

## 公开函数

```python
from backend.app.solution import recompile_solution
recompile_solution(request: RecompileRequest) -> RecompileResult
```

## API 路由

- `GET /health` → {"status": "ok", "service": "dcforge-solution"}
- `POST /compile-solution` → CompileRequest → SolutionBundle
- `POST /recompile-solution` → RecompileRequest → RecompileResult
- `POST /review-solution` → ReviewRequest → SolutionReviewResult

## 实现文件

- `backend/app/solution/recompiler.py` — 增量重编译器
- `backend/app/solution/api.py` — FastAPI 路由
- `backend/app/main.py` — FastAPI 应用
- `backend/app/solution/service.py` — 服务入口
- `backend/app/solution/__init__.py` — 公开导出

## 测试文件

- `tests/solution/test_recompiler.py` — 20 个重编译测试
- `tests/solution/test_solution_api.py` — 10 个 API 测试
- `tests/solution/test_recompile_fixture.py` — 12 个 fixture 测试

## Fixture

- `data/fixtures/recompile_request.json` — Demo 请求（security 约束）
- `data/fixtures/recompile_result.json` — Demo 结果（v1→v2，+data-masking +local-model）

## Diff 语义

- `added_component_ids`：new - old，按 ID 排序
- `removed_component_ids`：old - new，按 ID 排序
- `changed_node_ids`：新增/删除/修改的节点 ID，去重排序
- `change_explanations`：约束/组件/节点/评分/校验状态变化说明

## 版本规则

- 有实质变化时：`-vN` → `-v(N+1)`
- 无实质变化时：保持原 solution_id，空 Diff

## 实际测试结果

- tests/solution/test_recompiler: 20 passed
- tests/solution/test_solution_api: 10 passed
- tests/solution/test_recompile_fixture: 12 passed
- tests/solution (全部): 118 passed
- tests/test_contracts.py: 3 passed
- tests (全量): 121 passed
- uvicorn 启动: /health 200 ✅

## 当前限制

- Runtime 阶段仍需执行订单级金额和实际业务规则
- budget/time 仍受公共合同字段限制（unverifiable）
- 工作流为线性链，未支持分支和并行
- 无数据库、认证、CORS

## 后续

- 与成员 A、C 三方联调
- 可能需要扩展公共合同以支持 budget/time 验证
