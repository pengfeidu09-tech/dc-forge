# DCForge 成员 B API 示例

## 1. Health

```bash
curl http://127.0.0.1:8000/health
```

响应：

```json
{"status": "ok", "service": "dcforge-solution"}
```

## 2. Compile

```bash
curl -X POST http://127.0.0.1:8000/compile-solution \
  -H "Content-Type: application/json" \
  -d @data/fixtures/process_spec.json
```

> 注意：`/compile-solution` 接收 `CompileRequest`，其结构为 `{"process": <ProcessSpec>}`。
> 如果直接使用 `process_spec.json`（它本身就是 ProcessSpec），需要包裹一层：

```bash
curl -X POST http://127.0.0.1:8000/compile-solution \
  -H "Content-Type: application/json" \
  -d "{\"process\": $(cat data/fixtures/process_spec.json)}"
```

响应：`SolutionBundle`，包含 3 套 `SolutionPlan`。

关键字段：

```json
{
  "project_id": "procurement-demo-001",
  "plans": [
    {"plan_type": "conservative", "review_score": 83.7, ...},
    {"plan_type": "balanced", "review_score": 84.7, ...},
    {"plan_type": "innovative", "review_score": 82.6, ...}
  ]
}
```

## 3. Recompile

```bash
curl -X POST http://127.0.0.1:8000/recompile-solution \
  -H "Content-Type: application/json" \
  -d @data/fixtures/recompile_request.json
```

> `recompile_request.json` 已经是 `RecompileRequest` 结构（含 `process`、`selected_solution`、`new_constraints`）。

响应：`RecompileResult`。

关键字段：

```json
{
  "previous_solution_id": "procurement-demo-001-balanced-v1",
  "new_solution": {"solution_id": "procurement-demo-001-balanced-v2", ...},
  "added_component_ids": ["data-masking", "local-model"],
  "removed_component_ids": [],
  "changed_node_ids": ["balanced-001", "balanced-002", ...],
  "change_explanations": ["新增或覆盖约束: ...", "新增组件: ...", ...]
}
```

## 4. Review

```bash
curl -X POST http://127.0.0.1:8000/review-solution \
  -H "Content-Type: application/json" \
  -d "{\"process\": $(cat data/fixtures/process_spec.json), \"solution\": <balanced_plan_json>}"
```

响应：`SolutionReviewResult`。

关键字段：

```json
{
  "score": 84.7,
  "recommendation": "acceptable",
  "dimensions": [
    {"name": "约束合规", "score": 30, "max_score": 30},
    {"name": "需求与痛点覆盖", "score": 24, "max_score": 25},
    ...
  ],
  "warnings": ["..."]
}
```

## 5. Python 示例（标准库 urllib）

```python
"""使用 Python 标准库调用 B 模块 API，无需额外依赖。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1. Health
with urllib.request.urlopen(f"{BASE}/health") as resp:
    print("health:", json.loads(resp.read()))

# 2. Compile
with open("data/fixtures/process_spec.json", encoding="utf-8") as f:
    process_spec = json.load(f)

compile_body = json.dumps({"process": process_spec}).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/compile-solution",
    data=compile_body,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    bundle = json.loads(resp.read())

# 3. 选择 balanced
balanced = next(p for p in bundle["plans"] if p["plan_type"] == "balanced")
print(f"solution_id: {balanced['solution_id']}")
print(f"review_score: {balanced['review_score']}")
print(f"warnings: {balanced['warnings']}")

# 4. Recompile
with open("data/fixtures/recompile_request.json", encoding="utf-8") as f:
    recompile_body = f.read()
req2 = urllib.request.Request(
    f"{BASE}/recompile-solution",
    data=recompile_body.encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req2) as resp:
    result = json.loads(resp.read())

print(f"new solution_id: {result['new_solution']['solution_id']}")
print(f"added: {result['added_component_ids']}")
```

## 6. 响应字段说明

### SolutionBundle

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_id` | `str` | 项目 ID |
| `plans` | `list[SolutionPlan]` | 三套方案 |

### SolutionPlan

| 字段 | 类型 | 说明 |
|---|---|---|
| `solution_id` | `str` | 方案 ID（含版本） |
| `plan_type` | `str` | conservative / balanced / innovative |
| `review_score` | `float` | **设计阶段评分**，非实际效果 |
| `selected_components` | `list` | 选中的能力组件 |
| `to_be_nodes` | `list` | 目标工作流节点 |
| `expected_metrics` | `list[str]` | **待验证指标名称**，非已取得成果 |
| `warnings` | `list[str]` | 风险和待验证事项 |

### RecompileResult

| 字段 | 类型 | 说明 |
|---|---|---|
| `previous_solution_id` | `str` | 原方案 ID |
| `new_solution` | `SolutionPlan` | 重编译后的方案 |
| `added_component_ids` | `list[str]` | 新增组件 |
| `removed_component_ids` | `list[str]` | 移除组件 |
| `changed_node_ids` | `list[str]` | 变化节点 |
| `change_explanations` | `list[str]` | 变更说明 |

### SolutionReviewResult

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | `float` | 综合评分 0—100 |
| `recommendation` | `str` | recommended / acceptable / needs_revision / rejected |
| `dimensions` | `list` | 5 个评分维度明细 |
| `warnings` | `list[str]` | 评审警告 |

> **注意**：`review_score` 是设计阶段基于方案结构的评分，不是实际业务运行后的效果分。
