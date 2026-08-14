# DATA-M3 汽车制造智能招采黄金验收集

## 背景

现有 `PRJ-KM-001` 侧重企业采购知识管理软件项目，`PRJ-AUTO-001` 侧重整车采购交易全过程。两者能够验证对象结构、数量金额守恒和知识追溯，但没有一套项目同时覆盖汽车制造企业真实招采主链与智能招采能力验收，也缺少原始证据、权限数据、时间点语义、供应商画像、文档审查黄金样本和机器可判分问题。

本任务保留前两套项目，新增 `PRJ-TENDER-001`“星瀚汽车动力电池智能招采项目（模拟）”，作为与图片版智能招采PPT业务主链对齐的黄金验收集。

## 数据性质

- 企业、人员、供应商、资质、报价、合同、履约、诉讼、舆情、指标和结论均为 `synthetic_demo`。
- 晚于2026-08-14的事件为 `simulated_future_scenario`。
- PPT中的60%、50%、95%、6倍、86%等数字只作为带页码的 `unverified_marketing_claim`，不得成为项目验收结果。
- `valid/` 是内部业务一致的黄金案例；`adversarial/` 是故意植入问题的负向样本，不得与黄金项目聚合统计。

## 业务主链

黄金案例必须完整覆盖：

`采购预算 → 采购计划 → 采购立项 → 采购方案 → 采购执行 → 采购合同 → 文件归档 → 供应商管理 → 统计分析`

采购对象为2027款纯电平台的动力电池包，业务过程同时使用并验收以下智能招采能力：

- 采购需求、招标文件与合同附件辅助生成；
- 规则审查、语义风险提示与人工复核；
- 招采制度问答与证据引用；
- 供应商画像、资质、履约、质量、财务与风险分析；
- 权限过滤、字段脱敏、撤权和时间点查询。

## 三层证据模型

每个关键结论同时具备：

1. 原始证据：电话转写、会议逐字稿、邮件线程、附件、表格、OCR文本、供应商证照或正式文档；
2. 结构化对象：预算、计划、需求版本、供应商、规则命中、合同、履约、权限和分析对象；
3. RAG知识块：来源ID、来源路径、页码或段落、时间有效性、ACL和可独立理解的正文。

结构化Requirement Truth的每个来源摘录必须能在原始证据中找到。内部解释、模型推断和客户/业务正式确认使用不同状态。

## 文件结构

在 `03_客户项目全过程库/星瀚汽车动力电池智能招采项目/` 建立：

- `project_master.json`：项目索引和九阶段状态；
- `00_原始证据/`：20—30份原始证据文件及 `source_manifest.json`；
- `01_采购预算与计划/budget_plan.json`；
- `02_采购立项与需求/initiation_requirement.json` 和 `requirement_truth.json`；
- `03_供应商画像/supplier_profiles.json`；
- `04_采购方案与执行/sourcing_execution.json`；
- `05_文档生成与审查/`：规则集、预期命中和10份控制/问题样本；
- `06_合同履约/contract_fulfillment.json`；
- `07_归档统计/archive_analytics.json`；
- `08_权限与时间/security_model.json`；
- `09_沟通记录/communications.jsonl`：不少于50条上下文沟通；
- `10_RAG/golden_chunks.jsonl`：带ACL和双时态字段的知识块；
- `11_评测集/eval_cases.jsonl`：30—50个机器可判分问题；
- `adversarial/`：四套独立负向变体。

## 权限与时间语义

至少定义采购业务、法务财务、供应商质量、受限观察四类角色和对应测试用户。每个来源和知识块包含：

- `security_label`
- `acl_id`
- `allowed_roles`
- `allowed_departments`
- `field_masking`
- `permission_version`

撤权事件包含生效时间、旧新权限版本、影响对象和验证状态。

每个版本化对象和知识块包含：

- `occurred_at`
- `recorded_at`
- `valid_from`
- `valid_to`
- `supersedes`
- `source_version`

`as_of`查询不得返回在该时间点尚未发生、尚未记录或尚未生效的信息。

## 供应商画像

黄金案例包含5家风险特征不同的模拟供应商。每家至少包含企业与工厂覆盖、品类、资质证书及有效期、历史报价、交付及时率、质量PPM、投诉和整改、财务与信用风险、黑名单/诉讼/舆情、时间与工厂限定评价。评分配置保存权重、原始值、归一化、缺失值处理、人工调整与原因；排名不自动形成中标。

## 文档审查

准备4份无问题控制样本和6份故意植入问题的招标/合同样本。规则集版本化并定义适用文档、定位方式、严重度与人工要求。预期命中记录规则ID、原文位置、严重度、预期状态和人工确认/驳回/调整。至少包含招标文件—投标响应—合同之间的不一致。

## 评测集

`eval_cases.jsonl` 每条包含：

- `case_id`
- `query`
- `project_id`
- `user_context`
- `as_of`
- `expected_facts`
- `expected_source_ids`
- `forbidden_claims`
- `expected_refusal`
- `expected_masked_fields`
- `grading_rules`

题型覆盖正常事实、原因追溯、版本选择、时间点、证据不足、权限拒绝、字段脱敏、规则审查、供应商分析和异常识别。

## 负向变体

四套负向数据分别覆盖：

1. 邮件与会议在预算、数量或交期上冲突，未解决冲突不得形成正式方案；
2. 供应商报价过期且关键资质失效；
3. Go/No-Go或内部审批拒绝，项目不得进入合同执行；
4. 合同、发票、收付款、VIN或供应商引用不一致。

每套变体包含 `expected_findings`，明确检测器应发现的问题，不要求变体通过黄金守恒。

## 系统接入

在 `backend/app/solution/` 新增只读适配器，不修改contracts/process/runtime：

- 从来源清单构建现有 `CustomerContextPackage`；
- 应用ACL、字段脱敏、撤权和 `as_of` 过滤；
- 加载并验证Requirement Truth的来源闭包；
- 构建现有 `RequirementState`、`RequirementBaseline` 和 `ProcessSpec`；
- 调用现有方案编译器生成三套方案；
- 提供受权限和时间过滤的知识块检索。

## 验收标准

1. 九阶段完整，第三项目进入demo索引；
2. 20—30份原始证据、50条以上沟通、5家供应商、10份审查样本、30—50条评测、4套负向变体；
3. 原始证据、结构化对象和RAG三层来源闭包成立；
4. ACL、字段脱敏、撤权和时间点测试可机器执行；
5. 文档审查控制样本无预期问题，问题样本具有精确规则和位置；
6. 适配器能完成 `原始资料 → CustomerContextPackage → Requirement Truth → ProcessSpec → SolutionBundle`；
7. 新测试、DATA-M1、DATA-M2和 `tests/test_contracts.py` 全部通过；
8. 所有JSON/JSONL/YAML可解析且 `git diff --check` 通过。
