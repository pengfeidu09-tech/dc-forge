# PORTAL-M9：需求提取合同约束与清晰警告

## 背景

Internal Console 的通用需求提取直接调用基础 OpenAI-compatible Provider。基础提示只要求候选包含若干字段，没有列出合法需求分类，也没有明确 `confidence`、流程详情和痛点详情的严格类型。真实模型因此可能返回中文分类、自创分类或字符串置信度，随后被冻结合同拒绝。

控制台当前把每个 Pydantic 校验错误逐条原样展示，例如 `candidate 0 rejected by strict schema`。这些信息适合调试，但不适合作为主要用户提示：同一原因会重复多次，用户无法快速判断是否有有效需求被保留、应该采取什么操作。

## 产品目标

1. Internal Console 默认需求提取必须使用已有的严格合同适配器，为模型补充合法 category、数值置信度、typed detail 和 evidence quote 规则。
2. 严格合同不放宽：未知分类、非法数值、伪造 truth 字段和无法闭合的证据仍必须拒绝，不能静默写入 Requirement Truth。
3. 前端把提取警告按资料来源和错误类型汇总，主要区域展示中文原因、影响和处理结果。
4. 原始 warning code、candidate 序号和 Pydantic 消息保留在“查看技术详情”折叠区域，满足内部调试需要。
5. 不把被拒绝候选描述成已成功提取；只能说明它们已被安全忽略，通过校验的其他候选会继续保留。

## 合同约束

默认提取提示至少明确：

- 合法核心 category 列表以及 `ext:<domain>:<key>` 格式；
- 禁止输出中文 category 或自创格式；
- `confidence` 必须是 `0.0` 到 `1.0` 的 JSON number，不能是 `high`、`medium` 等字符串；
- `candidate_kind` 只能是 `extracted` 或 `inferred`；
- `evidence_quote` 必须是资料原文的连续子串；
- `current_process` 和 `pain_point` 各自需要对应的 typed detail，其他分类不得携带这些详情。

## 展示规则

- `invalid_candidate`：显示“模型输出字段不符合需求合同，已安全忽略”。
- `invalid_json`：显示“模型返回格式不是有效 JSON，本次未采用”。
- `evidence_not_found`：显示“模型引用无法在原始资料中定位，已安全忽略”。
- `provider_warning`：显示“模型服务返回警告，请检查模型配置或服务状态”。
- `empty_response`：显示“部分资料未得到模型返回内容”。
- `document_text_unavailable`：显示“资料没有可读取文本”。
- 来源 ID 映射为用户可读名称：会议纪要、客户邮件、需求 / 招标材料、销售备注；未知来源保留原 ID。
- 汇总必须包含各来源的数量；原始技术信息默认折叠。

## 验收标准

1. 测试证明默认 Internal Console Provider 包含严格提取合同适配器，同时保留原有 timeout、thinking 和 response format 配置。
2. 测试证明警告汇总能把多条 `invalid_candidate` 按来源合并，并生成清晰中文说明。
3. 前端主要警告区不再逐条平铺内部英文异常，且存在“查看技术详情”。
4. 既有严格候选拒绝、安全证据闭合和有效 sibling 保留测试继续通过。
5. 新测试、相关 process/Internal Console 测试、`tests/test_contracts.py`、前端测试和构建通过。
