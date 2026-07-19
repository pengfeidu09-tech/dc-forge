# B-M3: 硬约束校验、方案 Reviewer 与质量报告

**状态：** implemented

## 目标

对 `SolutionPlan` 进行设计阶段硬约束校验，并根据需求覆盖、约束合规、工作流完整性、可解释性和实施复杂度进行确定性评分。

## 公开入口

```python
from backend.app.solution import validate_constraints, review_solution

validate_constraints(plan: SolutionPlan, constraints: list[BusinessConstraint]) -> ConstraintValidationResult
review_solution(plan: SolutionPlan, process: ProcessSpec, validation: ConstraintValidationResult | None = None) -> SolutionReviewResult
```

## 支持的约束类型

1. **approval** — 检查 human_gate 和 gate_reason 体现阈值
2. **security** — 检查 audit-log / local-model / data-masking
3. **data** — 检查 data-masking / local-model
4. **risk** — 检查 risk-scoring / human-approval / audit-log
5. **budget** — 当前合同无成本字段 → unverifiable
6. **time** — 当前合同无时间字段 → unverifiable

## budget/time 不可验证原因

公共合同 `SolutionPlan` 缺少 `estimated_cost`、`budget`、`sla`、`implementation_period` 等字段，设计阶段无法验证预算和时间约束。硬约束标记为 unverifiable 并使总体 is_valid=false；软约束不使总体无效但产生 warning。

## 评分维度（总分 100）

1. **约束合规**（30 分）：全部 hard passed=30，hard failed -20，hard unverifiable -15，soft -3
2. **需求与痛点覆盖**（25 分）：痛点覆盖 10 + 业务目标 5 + 指标覆盖 5 + 关键流程区域 5
3. **工作流完整性**（20 分）：节点存在/唯一/无悬空/终止/组件一致/human gate/executor
4. **可解释性与证据**（15 分）：reason 非空/非占位/required_data/evidence/assumptions
5. **实施可行性**（10 分）：steps 非空/匹配/组件数量/数据覆盖率

## 实际评分结果

| 策略 | review_score | recommendation | is_valid |
|---|---|---|---|
| conservative | 83.7 | acceptable | True |
| balanced | 84.7 | acceptable | True |
| innovative | 82.6 | acceptable | True |

balanced 综合评分最高（覆盖与可行性的平衡）。

## 实现文件

- `backend/app/solution/constraints.py` — 约束校验器
- `backend/app/solution/reviewer.py` — 方案 Reviewer
- `backend/app/solution/compiler.py` — 编译器集成校验和评分
- `backend/app/solution/service.py` — 服务入口
- `backend/app/solution/__init__.py` — 公开导出

## 测试文件

- `tests/solution/test_constraints.py` — 14 个约束校验测试
- `tests/solution/test_reviewer.py` — 12 个 Reviewer 测试
- `tests/solution/test_compiler_review_integration.py` — 8 个集成测试
- `tests/solution/test_solution_quality_fixture.py` — 8 个质量报告测试

## Fixture

- `data/fixtures/solution_bundle.json` — 三套方案（含正式 review_score）
- `data/fixtures/solution_quality_report.json` — 质量报告（含校验和评分明细）

## 验证命令

```bash
.venv/Scripts/python.exe -m pytest tests/solution -q
.venv/Scripts/python.exe -m pytest tests/test_contracts.py -q
.venv/Scripts/python.exe -m pytest tests -q
```

## 实际测试结果

- tests/solution: 63 passed（B-M1 12 + B-M2 22 + B-M3 42 - 1 旧测试更新）
- tests/test_contracts.py: 3 passed
- tests (全量): 79 passed

## 当前限制

- review_score 基于设计阶段结构评分，非运行时实际验证；
- budget/time 约束无法在设计阶段验证（合同缺字段）；
- 工作流为线性链，未支持分支和并行；
- evidence_urls 全部为空，需后续补充公开引用。

## 后续任务

- B-M4：增量重编译 + FastAPI 路由
- Runtime 阶段仍需执行订单级金额和实际业务规则
