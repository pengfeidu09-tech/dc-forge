# B-M5: 联调交付与 PR 准备

**状态：** implemented

## 目标

对成员 B 全部功能进行最终回归验证，创建联调文档，增加端到端冒烟测试，准备 PR。

## 稳定 API

- `GET /health` → {"status": "ok", "service": "dcforge-solution"}
- `POST /compile-solution` → CompileRequest → SolutionBundle
- `POST /recompile-solution` → RecompileRequest → RecompileResult
- `POST /review-solution` → ReviewRequest → SolutionReviewResult

## 稳定 Python 入口

```python
from backend.app.solution import compile_solution
from backend.app.solution import recompile_solution
from backend.app.solution import validate_constraints
from backend.app.solution import review_solution
```

## A、B、C 边界

- A → B：ProcessSpec（公共合同）
- B → C：SolutionBundle / SolutionPlan / RecompileResult（公共合同）
- C 不调用 B 的内部函数，只通过 API 或公共合同对象交互

## 文档文件

- `docs/b-solution-integration.md` — 联调说明
- `docs/b-solution-api-examples.md` — API 示例（curl + Python urllib）

## 端到端测试文件

- `tests/solution/test_solution_end_to_end.py` — 7 个冒烟测试

## 验证命令

```bash
.venv/Scripts/python.exe -m pytest tests -q
```

## 实际测试结果

- tests/solution/test_solution_end_to_end: 7 passed
- tests/solution (全部): 125 passed
- tests/test_contracts.py: 3 passed
- tests (全量): 128 passed

## RuntimeRequest 兼容验证

`test_compile_output_can_build_runtime_request` 验证 balanced SolutionPlan 可被 `RuntimeRequest` 公共合同消费 ✅

## 当前限制

- 本地合同兼容测试通过，但尚未进行真实三方运行；
- 无数据库、认证、CORS；
- budget/time 受公共合同字段限制；
- evidence_urls 尚未补充；
- 工作流为线性链。

## 尚未进行真实三方联调

本任务的测试验证了公共合同兼容性和 API 可用性，但成员 A 和 C 尚未使用真实数据调用。真实三方联调需在 PR 合并后进行。
