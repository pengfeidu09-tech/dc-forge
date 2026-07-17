# DCForge 成员 B 联调说明

## 1. 模块职责

成员 B 负责：

- 接收成员 A 的 `ProcessSpec`；
- 从能力胶囊库检索匹配组件；
- 生成 conservative / balanced / innovative 三套 `SolutionPlan`；
- 封装为 `SolutionBundle`；
- 对每套方案执行设计阶段硬约束校验；
- 为每套方案生成确定性 `review_score`（0—100）；
- 接收客户新增约束，输出 `RecompileResult`（含组件和流程 Diff）；
- 提供 FastAPI 接口供前端和其他模块调用。

**不执行**：成员 C 的真实业务运行、价值指标计算、订单级金额判断。

## 2. 输入输出链路

```
成员 A
ProcessSpec
→ POST /compile-solution
→ SolutionBundle (3 套 SolutionPlan)
→ 成员 C 选择一个 SolutionPlan
→ RuntimeRequest

客户新增约束
→ POST /recompile-solution
→ RecompileResult (新 SolutionPlan + Diff)
→ 成员 C 展示组件、流程和评分变化
```

## 3. 成员 A 必须提供的字段

`ProcessSpec`（`backend/app/contracts/process.py`）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | 否 | 默认 `"1.0"` |
| `project_id` | `str` | 是 | 必须稳定，用于 solution_id |
| `industry` | `str` | 是 | 行业，用于检索匹配 |
| `department` | `str` | 是 | 部门，用于检索匹配 |
| `business_goal` | `str` | 是 | 业务目标 |
| `roles` | `list[str]` | 是 | 角色 |
| `available_data` | `list[str]` | 是 | 可用数据源 |
| `existing_systems` | `list[str]` | 是 | 现有系统 |
| `as_is_nodes` | `list[ProcessNode]` | 是 | 当前流程节点 |
| `pain_points` | `list[PainPoint]` | 是 | 痛点 |
| `constraints` | `list[BusinessConstraint]` | 是 | 客户约束 |
| `target_metrics` | `list[str]` | 是 | 目标指标 |
| `missing_information` | `list[str]` | 是 | 缺失信息 |
| `clarification_questions` | `list[str]` | 是 | 待澄清问题 |
| `readiness_score` | `float` | 是 | 0—100 |

**重点**：

- `project_id` 必须稳定，直接决定 `solution_id` 格式；
- `constraints` 必须使用 `BusinessConstraint`；
- `BusinessConstraint.id` 必须唯一；
- `hard=true` 表示不能静默忽略；
- approval 阈值应放在 `parameters.amount_threshold`；
- 缺失信息应进入 `missing_information`，不由 B 模块猜测。

## 4. 成员 C 可直接消费的字段

### SolutionBundle

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_id` | `str` | 与输入一致 |
| `plans` | `list[SolutionPlan]` | 固定顺序：conservative, balanced, innovative |

### SolutionPlan 关键字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `solution_id` | `str` | 格式 `{project_id}-{plan_type}-vN` |
| `plan_type` | `Literal[...]` | conservative / balanced / innovative |
| `selected_components` | `list[ComponentRef]` | 选中的能力胶囊 |
| `to_be_nodes` | `list[WorkflowNode]` | 目标流程节点 |
| `applied_constraints` | `list[BusinessConstraint]` | 保留的约束 |
| `review_score` | `float` | 设计阶段评分 0—100，非实际效果 |
| `expected_metrics` | `list[str]` | 待验证指标名称，非已取得成果 |
| `warnings` | `list[str]` | 必须在页面保留 |
| `assumptions` | `list[str]` | 假设 |

### WorkflowNode 关键字段

| 字段 | 说明 |
|---|---|
| `human_gate` | `true` 时需成员 C 实现人工审批交互 |
| `gate_reason` | 应显示给用户 |
| `executor` | ai / human / system |
| `next_ids` | 流程连接，无悬空 |

### RecompileResult 关键字段

| 字段 | 说明 |
|---|---|
| `previous_solution_id` | 原方案 ID |
| `new_solution` | 重编译后的新方案 |
| `added_component_ids` | 新增组件，用于 Diff 展示 |
| `removed_component_ids` | 移除组件 |
| `changed_node_ids` | 变化节点，用于高亮流程变化 |
| `change_explanations` | 重编译原因说明 |

**重点**：

- balanced 是当前 Demo 默认推荐，不代表客户必须选择；
- `review_score` 是设计阶段评分，不是实际业务效果；
- `expected_metrics` 是待验证指标，不是已取得成果；
- `warnings` 必须在页面保留。

## 5. API 启动方式

```bash
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

访问：
- Swagger 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

## 6. 联调顺序

1. `GET /health` → 确认 200
2. 使用 `data/fixtures/process_spec.json` 调用 `POST /compile-solution`
3. 确认返回 3 套方案（conservative / balanced / innovative）
4. 选择 balanced
5. 将 balanced 交给成员 C 组装 `RuntimeRequest`
6. 使用 `data/fixtures/recompile_request.json` 调用 `POST /recompile-solution`
7. 展示 local-model 和 data-masking 被加入
8. 展示 solution_id v1 → v2
9. 展示 changed_node_ids
10. 展示 review_score 84.7 → 82.9
11. 强调分数下降源于实施复杂度增加，不代表方案无效

## 7. 当前限制

- 当前为确定性规则和 Demo 实现；
- 无数据库、无身份认证、无 CORS；
- 无真实客户数据、无实际 ROI 结论；
- budget/time 因公共合同字段不足可能不可验证；
- evidence_urls 尚未补充；
- 工作流当前为线性链；
- 订单级金额判断应由成员 C Runtime 执行。

## 8. 联调验收标准

- `GET /health` 返回 200；
- `POST /compile-solution` 返回 3 套方案；
- 三套方案通过 `SolutionBundle.model_validate`；
- balanced 可被 `RuntimeRequest` 消费；
- `POST /recompile-solution` 返回合法 `RecompileResult`；
- 新约束不会被静默忽略；
- 无悬空 next_id；
- API 无效字段返回 422；
- 相同输入结果确定一致。
