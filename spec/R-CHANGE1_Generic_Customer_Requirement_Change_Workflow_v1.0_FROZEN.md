# R-CHANGE1 客户需求变更智能工作台 v1.0（FROZEN）

> **状态：FROZEN / v1.0。** 本 Spec 冻结 R-CHANGE1 v1.0 的 workflow、orchestration、UX 与 integration semantics；不得据此重开 Requirement Intelligence v1.0 public contracts、B-M8 public contracts，或直接修改其冻结语义。
> **项目：DCForge**
> **模块：Customer Requirement Change Intelligence（客户需求变更智能工作台）**
> **设计基线：`main@3565811c2cdcd58d9b8506c8cc32ca1a8611579f`**
> **日期：2026-08-13**

---

## 1. Purpose

将已存在的 Requirement Intelligence、RequirementBaseline、RequirementDiff、RequirementDiffRouter 与 B-M8 Recompile 串为一个通用的客户需求变更工作流：任何新客户反馈都先成为可追溯的候选需求，经过逐条人工/客户确认后才形成新的正式 Baseline，并据此确定方案更新路径。

本模块不是审批金额修改器。`500000 -> 800000` 仅是持续回归案例。

## 2. Problem Statement

当前后端已能从 Baseline v1 / v2 得到 diff、route 与更新方案；Internal Console 的反馈交互仍以单一审批反馈为中心。它存在以下产品缺口：

- 不能将一段客户反馈展示为 `0..N` 条独立变更的审核队列；
- 不能通用呈现 added / updated / removed / conflict / clarification / no-op；
- 不能对每条候选独立执行接受、拒绝、修改或待澄清；
- UI 仍含 `category === approval`、`threshold_amount === 800000` 以及 50/80 万展示特化；
- 现有 “客户反馈与差异” 不能完整展示从客户证据到方案变更的审计链。

## 3. Non-Goals

R-CHANGE1 v1 不做以下事项：

- 不重开 Requirement Intelligence v1.0 的 Truth、State、Baseline、Readiness 或 Question 语义；
- 不重开 B-M8 Solution Intelligence Engine 的资产、检索、Fit、Reuse、Bundle、Blueprint 或 Recompile 合同；
- 不用 LLM 自动确认、删除或关闭客户正式需求；
- 不因某 Requirement 未在新反馈中再次出现而将其删除；
- 不修改 ProcessSpec、BusinessConstraint、RequirementDiff 或 B-M8 公共合同，除非后续冻结审计批准；
- 不把任何行业、金额、项目 ID、模型品牌或中文关键词写入通用变更路由；
- 不承诺在 v1 解决所有语义匹配歧义。

## 4. Current Capability Audit

### 4.1 已有通用后端能力

| 能力 | 当前事实 | R-CHANGE1 复用方式 |
|---|---|---|
| 多源输入 | `CustomerSourceRecord` 支持 source id/type/title/content/author role | 每轮 feedback 继续作为一个或多个 source 输入 |
| 候选抽取 | `RequirementExtractor` 从每个 source segment 产出多条 candidate | `one source -> 0..N candidate requirements` |
| 状态演进 | `RequirementReducer` 建立连续 `RequirementState` 版本 | 新反馈以当前 state version 为前置版本 |
| 冲突 | ConflictDetector / confirmation 在确认时保持冲突闭包 | 不能静默覆盖相冲突客户事实 |
| 确认 | `RequirementConfirmation` 支持批量 confirmed / rejected / modifications，生成 confirmation record | 保持逐条 requirement ID 的审计动作 |
| Baseline | 只从 customer-confirmed 且 CONFIRMED_READY 的 state 建立连续 Baseline | 新 Baseline 必须由确认后的 truth 建立 |
| 语义 diff | `RequirementDiffEngine` 比较两个正式 Baseline | 作为唯一正式 solution-facing diff 来源 |
| 路由 | `RequirementDiffRouter` 提供 no-op / incremental / full | 作为 route policy 的确定性执行器 |
| 方案更新 | `RequirementIntelligenceService.apply_baseline_change` 校验 previous artifact 并执行 no-op/incremental/full | 仅向其传递前一正式方案 snapshot |
| 存储审计 | FileRepository 持久化 states、baselines、confirmation records、diffs | 保留连续版本与审计证据 |

### 4.2 已有语义匹配规则

`semantic_identity` / `semantic_payload` 当前规则可直接复用：

- `industry`、`department`、`business_goal`：类别级 scalar identity；
- `security`、`approval`、`budget`、`time`、`data`、`risk`：`category + normalized subject` 的 constraint identity；
- `current_process`：`process_node_id`；
- `pain_point`：`pain_point_id`；
- 其他类别：canonical semantic payload。

该设计已能稳定识别同一审批阈值的参数更新，且忽略 lineage ID 与排列差异。它不是通用自然语言实体消歧器；多条同类别、语义近似且 payload 不同的复杂场景，后续可能需要 v2 matching policy，但不得在本设计阶段修改 engine。

### 4.3 现有路由事实

`CONSTRAINT_CATEGORIES = {security, approval, budget, time, data, risk}`。仅这些类别的可表示 added/updated changes 才可 incremental；任何 removal/not-applicable 或 structural/mixed change 都 full。`integration` 不属于 constraint category，因此新增 SRM integration 当前正确路由为 `full_solution_recompile`，v1 冻结该行为。

### 4.4 当前 Console Golden 特化

当前 Console 已有 feedback、baseline version、diff、route、recompile 和 previous solution snapshot 基础，但仍特化于：汽车 Golden source、审批文本、`approval`、`threshold_amount === 800000`、50/80 万比较卡、审批 hard gate。R-CHANGE1 实现必须替换这些业务组件；Golden 仅保留为 “Load Golden Example”。

## 5. Domain Model

```text
Current RequirementBaseline vM
  + FeedbackSource[1..N]
  -> ExtractedRequirementCandidate[0..N]
  -> RequirementState vN+1 (pending/conflicted proposals)
  -> RequirementChangeSet (review projection; not truth)
  -> Confirmation actions per proposal
  -> RequirementState vN+2
  -> RequirementBaseline vM+1 (only confirmed truth)
  -> RequirementDiff(vM, vM+1)
  -> RequirementDiffRoute
  -> Updated solution artifacts and audit trace
```

`RequirementChangeSet` 是 R-CHANGE1 的 UI/orchestration view model，不是本轮新增公共 contract。每一项至少引用：candidate requirement ID、matched baseline requirement ID（如有）、suggested change type、previous/current semantic payload、source evidence、confidence、conflict status 与 confirmation disposition。

## 6. Change Semantics

| 类型 | 定义 | 正式生效条件 |
|---|---|---|
| ADDED | 当前 Baseline 无同一 semantic identity，新反馈有新业务语义 | 明确证据 + confirmation |
| UPDATED | 同 identity 的 value / parameters / typed detail 改变 | 明确证据 + confirmation；不得静默覆盖旧 truth |
| REMOVED / NOT_APPLICABLE | 客户明确取消、移出范围或确认不适用 | previous formal Baseline 的 active item + 本轮新反馈证据 + 非空 excerpt/closure + customer confirmation/confirmed_by + private evidence-bound removal guard；保留 lineage |
| CONFLICT | 新旧事实不能同时成立 | 不覆盖；进入 conflict resolution confirmation |
| CLARIFICATION | 新信息补充已有需求，但是否改变 semantic payload 由确定性 comparison 判断 | 仅 payload 有实质变化才成为 updated |
| NO MATERIAL CHANGE | 无新的 solution-facing confirmed semantic diff | diff 为空，route=no_op |

“客户没有再次提到”绝不等于 REMOVED。删除是历史状态变化，不是物理删除。

## 7. State Machine

```text
Baseline vM + feedback sources
  -> State vN+1: extracted proposals / conflicts / pending review
  -> per-item ACCEPT | REJECT | MODIFY | PENDING_CLARIFICATION
     or private REMOVE | NOT_APPLICABLE (previous formal Baseline item only)
  -> State vN+2: customer-confirmed truth and resolved conflicts
  -> readiness evaluation
  -> Baseline vM+1 only if CONFIRMED_READY
  -> Diff + Route + Solution update
```

State Version 与 Baseline Version 独立：一次反馈可产生 candidate state 与 confirmation state 两个连续 state；只有满足 readiness 的 customer-confirmed state 才创建下一个 baseline。多轮反馈重复此链，不限于 v1 -> v2。

## 8. Human Confirmation Gate

AI 可提取、匹配、建议 change type、标注冲突和提出澄清；AI 不可确认客户已改变正式需求、删除正式需求或创建 Baseline。

v1 confirmation UI 为每条 change 提供下列明确、可审计的语义动作：

- **ACCEPT**：使用 `confirmed_requirement_ids`；
- **REJECT**：仅用于不属于 previous formal Baseline 的新/更新 candidate；使用 `rejected_requirement_ids`，其 ChangeSet/UI/audit 语义为 `REJECTED_CANDIDATE`，不是 formal removal；
- **MODIFY**：使用 `RequirementModification`；
- **PENDING_CLARIFICATION**：本轮不提交该 candidate 的确认动作，保留 pending/conflicted，并展示 question/原因。
- **REMOVE / NOT_APPLICABLE**：仅适用于 previous formal Baseline 中仍为 active formal truth 的旧 requirement；它们是 R-CHANGE1 私有 orchestration semantic actions，不加入现有公共 confirmation enum。必须先通过第 25.1 节的 evidence-bound removal guard，才可 lower 为 `rejected_requirement_ids`，并持久化 private removal audit record。

批量操作只是多个独立 action 的一次提交。每项必须有 requirement ID、操作者、confirmation level、note、source evidence 和结果 state version。销售/售前 source 仍不是客户确认事实；internal confirmation 也不得移除 customer-confirmed formal truth。

## 9. Semantic Matching

1. 对新 source 抽取 `0..N` candidates；
2. 将每个 candidate 以现有 `semantic_identity` 和 `semantic_payload` 对 current Baseline 做 deterministic match；
3. 匹配同 identity 且 payload 不同：suggested UPDATED；无 identity：ADDED；显式取消 intent 的 candidate：suggested REMOVED/NOT_APPLICABLE，待确认；
4. 由 ConflictDetector 和 confirmation 处理互斥 truth；
5. 只以 Baseline-to-Baseline `RequirementDiff` 确认最终 solution-facing change。

候选层的“suggested”不是正式 diff。正式 diff 只比较两个 confirmed Baseline，避免 LLM、销售判断或未确认候选污染下游方案。

## 10. Multi-change Workflow

一个 feedback source 必须允许产生 `0..N` candidates。多段反馈只是多个 source 的组合，不能把全文压缩为一条 Requirement。

对于同一批 feedback：先生成 Change Review Table，再逐条/批量确认；所有真正确认后的结果共同形成一个新 state，并在 readiness 允许时形成一个 Baseline vM+1。Route 对整个 `RequirementDiff` 计算，而不是对单条候选分别更新方案。

## 11. RequirementDiff Integration

正式顺序固定为：`confirmed Baseline vM -> confirmed Baseline vM+1 -> RequirementDiffEngine.compare -> RequirementDiffRouter.route`。

当前 diff 的 removal item 在 `removed_requirement_ids` 中存在，但其 `RequirementChange.change_type` 仍表示为 `updated` 且 `after_value=null`。R-CHANGE1 UI 应以 ID set/after-null 显示 “Removed”，不得错误声称已有独立 `removed` enum。

## 12. Route Policy

| 整体 Diff 条件 | 路由 |
|---|---|
| 无 changes | `no_op` |
| 所有类别在 constraint set，均为可映射 added/updated，且无 removal/not-applicable | `incremental_constraint_recompile` |
| 任一已通过 formal-removal guard 的 constraint removal / applicable -> not applicable | `full_solution_recompile` |
| 任一 structural 类别或 constraint + structural mixed | `full_solution_recompile` |

Structural 类别包括但不限于 `current_process`、`pain_point`、`scope`、`integration`、`deliverable`、`existing_system`、`target_metric`、`business_goal`。如 structural diff 在 current ProcessSpec 中不可表示，沿用现有 representability guard 失败，不得降级为 incremental。

## 13. Incremental Recompile

仅在 router 返回 incremental 时调用冻结 B-M8.7 append/override recompile。要求：

- 传入 feedback 发生前的 ProcessSpec、selected solution、DemoBlueprint snapshot；
- previous snapshot 必须通过 previous baseline guard；
- stable constraint ID 由 `project_id + category + subject` 保持；
- 同一语义约束更新后，旧值不可仍为 active truth，新值 active count 为一；
- 未受影响 assets/modules 不应无意义重选；
- 输出 RequirementDiff、Route、新 solution/blueprint 与 structured B-M8 diff。

## 14. Full Recompile

full 不等于丢弃旧方案或让 LLM 任意改写。它必须保留 previous snapshot，基于 current confirmed baseline 重新构建 ProcessSpec、Bundle、selected plan 和 Blueprint，并输出 before/after trace：changed requirements、categories、ProcessSpec、constraints、assets、modules、nodes、value claims 和 unchanged artifacts。

## 15. No-op

若 confirmed Baseline 语义等价，`RequirementDiff.changes=[]` 且 route=`no_op`。不得调用 B-M8 compile/recompile；应保留 previous current artifacts 并展示 “无实质方案影响”。

## 16. UI Model

Tab 名称升级为 **客户需求变更**，包含：

1. **客户最新反馈**：可添加多个 source record，含 type/title/content/author role；按钮“分析需求变化”。
2. **AI 识别的需求变化**：通用 table/cards，显示 suggested type、category、subject、previous/current values and parameters、evidence、source、confidence、conflict、confirmation status；支持逐条 ACCEPT/REJECT/MODIFY/PENDING_CLARIFICATION、全选及批量提交。对 previous formal Baseline 的 active item，另提供私有 REMOVE/NOT_APPLICABLE 审核入口；必须满足第 25.1 节 guard，不能以普通 REJECT 代替。
3. **方案影响**：确认后显示 Baseline vM -> vM+1、added/updated/removed/conflict resolved、changed categories、route、受影响 ProcessSpec/assets/modules/constraints/DemoBlueprint/value claims，以及“更新解决方案”。

禁止以 `approval`、`800000` 或任意 Golden 项目 ID 定位唯一 feedback candidate。审批阈值闭环可作为通用 constraint detail renderer 的一个示例，而不是页面主模型。

## 17. Auditability

每轮必须可追溯：

- raw feedback source、source ID、excerpt、provenance；
- candidate requirement ID、semantic match、suggested change；
- confirmation action、confirmed by、note、state versions；
- previous/current Baseline IDs and versions；
- RequirementDiff 与 Route explanation；
- previous/current ProcessSpec、solution、Blueprint；
- changed 与 unchanged solution artifacts。

历史 Requirement 不物理删除；通过 rejected/superseded/not-applicable lineage 与 confirmation record 保存历史。

## 18. Truth & Safety Rules

1. Customer raw、AI extracted/inferred、sales/presales judgment、human modified、customer confirmed 不可混同。
2. 只有 customer-confirmed truth 可进入 formal Baseline。
3. 缺失复述不构成取消；取消必须有新证据、明确 intent 和确认。
4. 冲突不得静默覆盖。
5. 路由必须 deterministic，且只能基于正式 RequirementDiff。
6. 不得为提高 incremental 比例将 structural change 伪装为 constraint。
7. previous/current solution snapshot 必须是独立对象并与对应 baseline 匹配。
8. backend previous-process validation 是安全 guard，前端不得绕过或放宽。

## 19. Regression Cases

| Case | 输入变化 | 预期 |
|---|---|---|
| A 单约束更新 | approval 500000 -> 800000 | UPDATED；incremental |
| B 多约束更新 | approval 更新 + security added + time added | 3 个独立 changes；batch confirmation；incremental（均可映射时） |
| C 结构性变化 | integration: OA -> OA + SRM | full_solution_recompile |
| D 混合变化 | approval update + integration added + scope change | full_solution_recompile |
| E 无实质变化 | “按当前确认方案执行，没有新增要求” | empty diff；no_op；零方案重编译 |

## 20. Acceptance Criteria

- **AC-01** 任意 feedback source 产生 `0..N` candidates。
- **AC-02** 一次支持多个独立 requirement changes。
- **AC-03** 支持 added、updated、removed/not-applicable 的 review semantics。
- **AC-04** 不得因未再次提及自动 removed。
- **AC-05** AI 不得绕过 confirmation gate。
- **AC-06** 新 Baseline 只来自 confirmed truth。
- **AC-07** RequirementDiff 只比较 Baseline。
- **AC-08** 单一可表示 constraint update 可 incremental。
- **AC-09** 多个兼容 constraint changes 可 incremental。
- **AC-10** structural/mixed change 自动 full。
- **AC-11** 无实质变化为 no_op。
- **AC-12** 每项变化可 provenance trace。
- **AC-13** 每项 solution change 可回溯到 RequirementDiff。
- **AC-14** 历史 Requirement 不物理删除。
- **AC-15** 支持连续多轮 feedback。
- **AC-16** 通用流程不硬编码 approval/800000。
- **AC-17** Golden 500k->800k 持续通过。
- **AC-18** 旧值不得残留为 active truth。
- **AC-19** previous/current solution snapshots 可比较且不可 alias。
- **AC-20** route decision deterministic。

## 21. Invariants

- `previous_baseline_version < current_baseline_version`；
- Baseline project closure、state closure、diff closure、route closure 必须成立；
- one semantic identity 在一个 Baseline 内不可包含冲突 payload；
- non-no-op route 必须有 sorted changed categories；
- incremental 必须有非空且唯一 ID 的 new constraints；
- full/no-op 不能携带 incremental new constraints；
- 未确认 candidate 永不作为 ProcessSpec 或 B-M8 输入；
- current compile 不得重写 previous solution snapshot。

## 22. Failure Modes

| Failure | 安全行为 |
|---|---|
| Provider empty/invalid JSON | 显示 extraction warning；不产生 truth 或 Baseline |
| 候选无原文证据 | 丢弃候选并记录 warning |
| 语义匹配歧义 | 保留 pending clarification，不自动 merge/remove |
| Open conflict | 不静默覆盖；要求 customer resolution |
| Baseline 不 ready | 不创建 Baseline，不更新方案 |
| Previous artifact 与 baseline 不匹配 | 后端拒绝 recompile |
| Snapshot 不完整 | UI 禁用更新，payload builder 拒绝请求 |
| Structural diff 不可表示 | full route 的 representability guard 报错；不改为 incremental |
| Network/LLM failure | 不改变旧 Baseline 或旧 solution |

## 23. Compatibility

R-CHANGE1 v1 必须兼容并复用当前 `RequirementConfirmation`、`RequirementBaseline`、`RequirementDiff`、`RequirementDiffRoute`、ProcessSpecAdapter 和 B-M8.7 APIs。UI implementation 可新增私有 view model 与 API orchestration，但不得改变 frozen public contracts。阈值字段的跨层 ownership 与 fail-closed mapping 已由第 25.2 节冻结：Requirement/Extraction 使用 `parameters.threshold_amount`；ProcessSpec/BusinessConstraint/B-M8 使用 `parameters.threshold`；ProcessSpecAdapter 是唯一 translator。

## 24. Resolved V1 Decisions

下列决策不增加公共合同，且可作为 R-CHANGE1 v1 的设计边界：

1. **PENDING_CLARIFICATION** 是 ChangeSet/UI disposition：不进入 confirmed/rejected/modifications，继续保留 pending/conflicted，并由现有 gap/conflict/question 表达。若未来需要 SLA 或任务持久化，再设计 v2 contract。
2. **RequirementChangeSet** 是 Internal Console/API orchestration 的 private view model，不加入 `backend/app/contracts/requirement_intelligence.py`。正式 Truth 仍只由 RequirementState、RequirementBaseline、RequirementDiff 与 RequirementDiffRoute 定义。
3. **Semantic matcher v1** 只复用 `semantic_identity` / `semantic_payload`。歧义、多 target、近义不确定或多值 identity 不稳时进入 PENDING_CLARIFICATION；不得 auto merge、auto remove 或 auto supersede。
4. **Full recompile impact projection** 是 R-CHANGE1 private deterministic projection：对 previous/current ProcessSpec、constraints、assets、modules、DemoBlueprint nodes 与 value claims 做 changed/unchanged/added/removed 比较。无稳定 ID 的 artifact 只可保守比较，不能由 LLM 自报影响。
5. **Real dataset acceptance** 不阻塞 Spec 设计决议，但阻塞 implementation closure：完成实现和六类 Golden 回归后，必须用 A 组 initial + round-2 + optional round-3 资料验证多变更、多轮、provenance、confirmation、baseline versioning、route 与 solution update。
6. **Route matrix** 保持不扩大：no diff -> no_op；仅 `security/approval/budget/time/data/risk` 的可表示 add/update -> incremental；constraint removal、integration、structural 或 mixed -> full。

## 25. Frozen V1 Closure Decisions

### 25.1 REMOVAL_EXECUTION = RESOLVED_BY_PRIVATE_ORCHESTRATION_GUARD

只读审计确认：`RequirementConfirmationApplier` 可通过现有 `rejected_requirement_ids` 将 item 置为 `status=rejected`；internal confirmation 已禁止拒绝 customer-confirmed truth；`RequirementBaselineBuilder` 只选 customer-confirmed items。因此 customer-confirmed rejection 后，旧正式 item 退出 current Baseline，历史 Requirement、旧 evidence、confirmation record、state 与 baseline lineage 都保留。

R-CHANGE1 v1 不改变该 core primitive，而在产品工作流调用它**之前**执行 private deterministic removal guard。建议 private persisted model：

```text
RequirementChangeDecision / RemovalEvidenceBinding / RequirementChangeAuditRecord
  change_decision_id
  project_id
  target_requirement_id
  previous_baseline_id / previous_baseline_version
  action: REMOVE | NOT_APPLICABLE
  evidence: source_id, excerpt, locator?
  confirmation_level: customer
  confirmed_by
  source_state_version / result_state_version
  confirmation_id (after apply)
```

Formal removal guard 必须在构造 lower-level `RequirementConfirmation` 前验证：

1. target requirement 属于 previous formal Baseline，且仍是 active formal truth；
2. evidence source ID 属于本轮 new feedback source set；
3. evidence excerpt 非空，并可复用现有 source/excerpt closure 验证；
4. 人工 semantic action 明确为 REMOVE 或 NOT_APPLICABLE；
5. confirmation level 是 `customer`，且 `confirmed_by` 非空；
6. 仅 guard 通过后，才将 target 写入 `rejected_requirement_ids` 并保存 private audit record；
7. guard 不以中文/英文关键词或 deterministic NLP 猜 removal intent；intent 来自明确人类 action + customer confirmation。

该规则只约束 R-CHANGE1 产品 API/UI；`RequirementConfirmation` 仍是 lower-level core primitive，不对外被该工作流包装为“任意拒绝旧 Baseline requirement”的操作。若绕过 R-CHANGE1 直接调用 core primitive，不得把结果声称为 evidence-bound formal removal。

Candidate rejection 与 formal removal 必须区分：不在 previous formal Baseline 中的 target 被 reject 是 `REJECTED_CANDIDATE`；在 previous formal Baseline 中且完整通过 guard 的 customer rejection 才在 ChangeSet/UI/audit 投影为 `FORMAL_REMOVAL`。未再次提及永远不得触发 removal。

Phase defer（“一期不做 X，二期再做”）不自动等于 permanent removal：优先表达 current scope change + future phase requirement；当前 contract 无法无损表达时，保持 PENDING_CLARIFICATION 或保守 scope statement，不得丢失 future intent。

### 25.2 THRESHOLD_SCHEMA_AUDIT = RESOLVED_BY_EXPLICIT_LAYER_MAPPING

只读审计确认当前跨层字段不一致：RequirementExtractor candidate 已使用 `threshold_amount`；ProcessSpecAdapter 当前透传 parameters；现有 ProcessSpec/Internal Console API Golden/router/B-M8 recompile 路径使用 `threshold`；Console 当前错误地将 ProcessSpec/solution artifact 也按 `threshold_amount` 展示。

R-CHANGE1 v1 冻结明确 layer ownership，而非要求所有层同名：

| Layer | Approval monetary threshold canonical field |
|---|---|
| Requirement / Extraction semantic layer | `parameters.threshold_amount` |
| ProcessSpec / BusinessConstraint / B-M8 solution layer | `parameters.threshold` |

`ProcessSpecAdapter` 是唯一 boundary translator。其后续实现必须遵循：

| RequirementItem input | BusinessConstraint output |
|---|---|
| `threshold_amount=X`，无 `threshold` | `threshold=X` |
| legacy `threshold=X`，无 `threshold_amount` | `threshold=X` |
| 两者均有且相等 | 仅 `threshold=X`，不得双 alias 输出 |
| 两者均有且不相等 | FAIL CLOSED，明确 schema conflict |

旧 persisted ProcessSpec/B-M8 artifacts 的 `threshold` 必须继续工作；不要求重写历史数据。新的 extraction `threshold_amount` 必须经 adapter 稳定映射为 ProcessSpec `threshold`。Internal Console 的 RequirementItem renderer 读取 `threshold_amount`；ProcessSpec/Solution renderer 读取 `threshold`，或由一个明确 layer-aware view model 统一显示值。当前 Console 的跨层 `threshold_amount` 读取是后续 implementation work，不是本轮文档外的修复。

R-CHANGE1 generic candidate extraction、semantic matching、ChangeSet 和 RequirementDiff decision 继续比较 `category + subject + value + parameters + typed details`；不得以 `threshold`、`threshold_amount`、`800000` 或任何金额作为流程分支。

## 26. Regression Matrix Additions

### 26.1 Removal regressions

| Case | Expected |
|---|---|
| R1 Candidate rejection | new unconfirmed candidate -> reject -> REJECTED_CANDIDATE；不是 formal removal |
| R2 Formal removal valid | old formal item + new evidence + REMOVE + customer confirmation -> inactive/history retained/current Baseline removes active item/Diff removal/full route |
| R3 Missing evidence | old formal item + REMOVE but no new feedback evidence -> BLOCK |
| R4 Internal-only removal | old customer-confirmed truth + internal action -> BLOCK |
| R5 Missing repetition | new feedback does not mention X -> no removal |

### 26.2 Threshold regressions

| Case | Expected |
|---|---|
| T1 | Requirement `threshold_amount=500000` -> ProcessSpec `threshold=500000` |
| T2 | Requirement `threshold_amount=800000` -> ProcessSpec `threshold=800000` |
| T3 Legacy | Requirement `threshold=500000` -> ProcessSpec `threshold=500000` |
| T4 Alias Same | both aliases equal -> output only `threshold=500000` |
| T5 Alias Conflict | `threshold_amount=800000`, `threshold=500000` -> FAIL CLOSED |
| T6 Incremental | semantic 500000 -> 800000 -> Process constraints threshold 500000 -> 800000, stable ID, old active residue 0 |

## 27. Future Extensions

以下属于不阻塞本 Spec 冻结的后续演进；它们不得改变本 v1 已冻结的私有 guard、public-contract boundary 或 route semantics：

1. public explicit removal action enum 与 public evidence-linkage contract（v1 不需要，且不得替代 private evidence-bound removal guard）；
2. persistent clarification workflow；
3. public ChangeSet contract；
4. semantic matcher v2；
5. shared machine-readable impact contract；
6. advanced multi-phase modeling。

## 28. Regression Cases

在第 19 节 A-E 的基础上，增加：

| Case | 输入变化 | 预期 |
|---|---|---|
| F 明确删除 | previous Baseline 中 scope/capability X active；新客户证据为“本期明确取消 X”；customer confirms removal | 旧 item inactive 且历史保留；current Baseline 不含 active X；RequirementDiff removal；full_solution_recompile |

“未再次提及 X”不得触发 Case F。

## 29. Additional Acceptance Criteria

- **AC-21** formal removal 必须有本轮新 feedback 的 explicit evidence、customer confirmation、R-CHANGE1 private evidence-bound removal guard 与 persisted removal audit record；在这些 private workflow 能力实现并通过回归前，不得宣称 R-CHANGE1 implementation closed。
- **AC-22** candidate rejection 与 formal removal 必须在 ChangeSet/UI 与审计中可区分。
- **AC-23** pending clarification 不得进入 Baseline。
- **AC-24** ambiguous semantic match 不得 auto merge/remove。
- **AC-25** real dataset acceptance 不阻塞 Spec 设计，但阻塞 R-CHANGE1 implementation closure。
- **AC-26** formal removal 必须经过 R-CHANGE1 evidence-bound removal guard。
- **AC-27** formal removal evidence 必须来自本轮 new feedback source set。
- **AC-28** internal action 不得移除 customer-confirmed formal truth。
- **AC-29** Requirement approval `threshold_amount` 必须确定性映射为 BusinessConstraint `threshold`。
- **AC-30** threshold alias conflict 必须 fail closed。

## 30. Implementation Readiness

**FREEZE_AUDIT = PASS。**

已冻结 private removal guard、threshold layer mapping、Pending Clarification、private ChangeSet、matcher policy、full impact projection、real-data acceptance role 与 route matrix 的 v1 架构决议；这些能力尚待后续 implementation 依照本文与回归矩阵落地。

后续 implementation 必须先以 R1-R5 与 T1-T6 为失败回归测试，再实施 private guard、private audit persistence、adapter normalization 和 layer-aware UI renderer；不得以实现前的现有 core primitive 或 Console Golden 特化冒充这些能力已完成。

本文件为 **FROZEN / v1.0**。R-CHANGE1 后续实现必须遵守本文冻结的 workflow、orchestration、UX 与 integration semantics；不得据此修改 frozen Requirement Intelligence v1.0 public contracts 或 B-M8 public contracts。

### 30.1 Final Freeze Criteria

| Criterion | Result |
|---|---|
| `REMOVAL_TRUTH_CLOSURE` | PASS |
| `THRESHOLD_LAYER_CLOSURE` | PASS |
| `HUMAN_ACTION_MODEL` | PASS |
| `GENERIC_WORKFLOW` | PASS |
| `ROUTE_MATRIX` | PASS |
| `REGRESSION_MATRIX` | PASS |
| `AC_CONSISTENCY` | PASS |
| `PUBLIC_CONTRACT_BOUNDARY` | PASS |
| `NO_STALE_BLOCKERS` | PASS |
