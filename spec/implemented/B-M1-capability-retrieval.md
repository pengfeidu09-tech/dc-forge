# B-M1: CapabilityCapsule 能力胶囊库与确定性检索

**状态：** implemented

## 目标

根据 `ProcessSpec`，从能力胶囊库中检索与客户行业、部门、流程痛点、现有数据和业务约束匹配的候选组件，并转换成公共合同中的 `ComponentRef`。

## 输入

`backend.app.contracts.process.ProcessSpec`

## 输出

`list[backend.app.contracts.solution.ComponentRef]`

## 公开函数

```python
load_capabilities(path: Path | None = None) -> list[CapabilityCapsule]

retrieve_components(
    process: ProcessSpec,
    capabilities: list[CapabilityCapsule] | None = None,
    limit: int = 5
) -> list[ComponentRef]
```

## 验收标准

1. `data/capabilities.json` 包含恰好 15 个能力胶囊 ✅
2. `component_id` 唯一 ✅
3. JSON 可以通过 `CapabilityCapsule` 模型校验 ✅
4. 输入采购场景的 `process_spec.json` 时，返回结果非空 ✅
5. 返回的每个 `component_id` 都真实存在于能力胶囊库 ✅
6. 返回数量不超过 `limit` ✅
7. 输出满足 `ComponentRef` 公共合同 ✅
8. 有审批约束时，人工审批和审计能力应获得优先匹配 ✅
9. 没有匹配结果时返回空列表，不虚构组件 ✅
10. 检索结果顺序稳定，同一输入多次运行结果一致 ✅

## 实现文件

- `backend/app/solution/capabilities.py` — CapabilityCapsule 模型 + load_capabilities
- `backend/app/solution/retriever.py` — retrieve_components 确定性检索器
- `backend/app/solution/__init__.py` — 公开导出
- `data/capabilities.json` — 15 个能力胶囊数据

## 测试文件

- `tests/solution/test_capabilities.py` — 5 个模型与数据校验测试
- `tests/solution/test_retriever.py` — 7 个检索器行为测试

## 验证命令

```bash
.venv/Scripts/python.exe -m pytest tests/solution -q
.venv/Scripts/python.exe -m pytest tests/test_contracts.py -q
.venv/Scripts/python.exe -m pytest tests -q
```

## 实际测试结果

- tests/solution: 12 passed
- tests/test_contracts.py: 3 passed
- tests (全量): 15 passed

## 评分逻辑

- 行业匹配: +3
- 部门匹配: +2
- problem_tags 与痛点/目标匹配: 每项 +2
- required_data 与 available_data 匹配: 每项 +1
- supported_constraint_types 与约束类型匹配: 每项 +2
- approval 约束 + human-approval: 额外 +5
- risk 约束 + risk-scoring/audit-log: 额外 +3
- 只返回 score > 0 的组件
- 按 score 降序，同分按 component_id 升序（保证稳定）

## 当前限制

- 检索基于关键词子串匹配，不使用语义理解；
- 匹配粒度较粗，可能产生噪音匹配；
- 评分权重为人工设定，未经过数据验证。

## 后续可替换位置

`backend/app/solution/retriever.py` 中的 `retrieve_components` 函数可整体替换为：
- Embedding 检索（语义匹配）
- Hybrid Search（关键词 + 语义混合）
- Rerank（先粗排后精排）

替换时只需保持函数签名和返回类型不变，`_score_capsule` 等私有辅助函数可删除。

## 本阶段未做

- 不调用大模型；
- 不调用外部 API；
- 不使用向量数据库；
- 不修改公共合同；
- 不实现 SolutionCompiler；
- 不实现 Reviewer；
- 不实现 FastAPI 路由。
