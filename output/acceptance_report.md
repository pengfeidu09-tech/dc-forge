# DCForge PRJ-TENDER-001 真实数据 E2E Acceptance

## 结论

- E2E_PIPELINE = PASS
- DCFORGE_SOLUTION_READY_FOR_MANUAL_A_B = PARTIAL
- 真实 Requirement Extraction：26/26 source，26 次调用，0 次技术重试，模型 `qwen3.7-plus`
- 后续 Baseline、ProcessSpec、Retrieval、Solution、Eval、Change Workflow 全部为离线确定性执行，新增真实 LLM/API 调用为 0
- 全量回归：585 passed, 1 warning
- Frontend build：PASS
- git diff --check：PASS

E2E 已可执行，但 Requirement 的结构化完整性、企业知识问答命中率和方案业务深度仍不足，不宜将本次输出当作最终比赛级方案；可以用于有明确缺陷清单约束下的人工 A/B 评审。

## Requirement

- Golden Truth：52 项 confirmed customer truth
- 实际正式 Baseline：108 项 customer-confirmed item
- 严格可用结构覆盖（人工事后审计）：23/52，44.2%
- 语义在某处出现（包括合并项/错分类/部分表达）：约 40/52，76.9%
- Latest Version Accuracy：PASS。当前量 12,000 套、单套上限 104,000 元、SOP 2027-03-01 均选择 V3；V1/V2 未泄漏为当前值
- Obsolete Requirement Leakage：0
- Provenance closure：108/108 均有 source ref；无无来源的 formal truth
- 主要缺失/错误：4 个角色未抽取；4 个真正 target metric 被错分或丢失；3 个 automotive ext category 未形成；九阶段流程被压成单一 typed node，8 个节点未进入 ProcessSpec 图；available data、existing systems、deliverables 被合并成粗粒度项；risk 和 evidence-closure 未形成 Golden 所需的统一结构
- 过抽取：大量供应商事实、评测说明和资料事实被确认为正式 Requirement。虽然有来源，但不等于客户需求；108 对 52 的差异是显著 P1

## ProcessSpec

- PASS（合同、约束、人工作业边界和 fail-closed 校验均有效）
- readiness：100
- 正确保留：汽车制造、集团采购中心、V3 时间/预算约束、ACL/审批/证据相关硬约束、5 个核心痛点
- lost semantics：角色为空；现状流程仅保留 2 个节点且无完整九阶段边；目标指标只剩 12,000/70%/30%，丢失引用正确率、版本正确率、权限泄露率、文档审查可判分性；系统/数据粒度过粗

## Retrieval / Reuse

- Retrieval 顺序：`dc-smart-procurement`、`dc-energy-serious-longtext`、`dc-tobacco-smart-procurement`
- `dc-smart-procurement`：相关且唯一产生可执行 ReuseDecision 的资产，复用文档工作台与审查/风险定位模块
- `dc-energy-serious-longtext`、`dc-tobacco-smart-procurement`：仅弱相似候选，没有可执行复用决策；未被冒充为适配案例
- Reuse quality：证据约束正确，但覆盖面窄；未覆盖供应商画像、ACL/双时态检索、跨系统引用、评分与合同闭环等关键场景

## Solution

- Quick Win：1 个 direct-reuse 模块，最小范围真实区别于 Production Fit
- Production Fit：2 个模块，含人工审查 gate
- Transform：同 2 个模块，增加 system handoff 拓扑；未虚构新资产或 customization
- DemoBlueprint：5 个节点，2 个 human gate
- 三套方案均使用 `dc-smart-procurement`，review score 均为 45；Production Fit 与 Transform 的能力范围仍接近
- ValueClaim：仅历史案例 claim，全部有 evidence ref；明确标注不是当前客户已验证结果；没有 current/verified 成果冒充

### Solution Quality /60

| 维度 | 分数 | 依据与扣分 |
|---|---:|---|
| Requirement Accuracy | 3/5 | V3 与硬约束正确；存在大量事实型过抽取和分类错误 |
| Requirement Completeness | 2/5 | 角色、目标指标、扩展字段和 8 个流程节点缺失 |
| Evidence Traceability | 5/5 | formal truth 与 ValueClaim 均闭合到来源，无无来源 claim |
| Constraint Handling | 4/5 | 预算、时间、ACL、审批进入 ProcessSpec；部分约束粒度分散 |
| Human Decision Boundary | 5/5 | 定标/偏差/审批保留人工 gate，未由 AI 自动决定 |
| Solution Architecture | 3/5 | 可执行蓝图成立；企业知识、供应商与跨系统能力未形成完整架构 |
| Implementation Feasibility | 3/5 | 模块与依赖保守可落地；系统集成仅形成粗粒度声明 |
| Risk Management | 2/5 | 有 unresolved/module 风险，但客户风险未形成具体闭环计划 |
| Enterprise Knowledge Reuse | 3/5 | 正确复用招采资产；其余候选不强行复用，但资产覆盖窄 |
| Business Value Discipline | 4/5 | 历史 claim 与当前结果明确隔离；缺少当前客户参数化价值模型 |
| Plan Differentiation | 3/5 | Quick Win 范围已缩小，Transform 有拓扑差异；后两套模块仍相同 |
| Presales Readability | 3/5 | 摘要已绑定客户目标、资产和模块；仍缺客户化叙事与实施细节 |
| **总分** | **40/60** | 可供受控人工评审，尚非比赛最终稿 |

## Evidence / Hidden Eval

- ValueClaim unsupported：0
- Hidden Eval：36 cases
- 原始 harness fact hit：2/36 = 5.56%
- 原始 harness citation hit：14/36 = 38.89%；剔除 5 个不要求 citation 的 case 后，真实 source-required citation hit 为 9/31 = 29.03%
- forbidden claim：0
- temporal leakage：0
- permission leakage：2
- insufficient-evidence 严格通过：0/3（仅 1 case 真正返回 insufficient-evidence 状态；另外 2 case 给出泛化结果）
- 安全性边界好于回答效用：没有编造禁止结论或未来泄漏，但路由与答案组装过于通用，事实、引用和权限拒绝质量不足

## Requirement Change Workflow

- 离线历史重放窗口：Baseline v1 使用 SRC-TENDER-001..016；new feedback 使用 SRC-TENDER-017..026
- ChangeSet：52 项，人工确认 ACCEPT 36 / REJECT 16，未默认全量确认
- Baseline：v1（70 项）→ v2（106 项）
- RequirementDiff：Added 36 / Updated 0 / Removed 0
- Route：`full_solution_recompile`
- Solution update：PASS，生成新 ProcessSpec、SolutionPlan、DemoBlueprint
- stable previous IDs retained：70；old active residue：0；previous snapshot 由正式 service guard 验证
- Formal removal：DATA_GAP。后续 source 没有明确客户删除指令，因此没有伪造 removal

## Defects

1. P1 EXTRACTION_PROBLEM — typed process 可包含不存在的 next node。期望 normalization 删除悬空引用；实际此前由 ProcessSpec 才 fail-closed。根因是 extractor 仅清理 pain refs，未清理 process next refs。已修复。
2. P1 EXTRACTION_PROBLEM — 角色、目标指标、ext 字段和流程节点漏抽/错分类，同时把大量资料事实当 Requirement。根因是单 source LLM 抽取粒度与 taxonomy 约束仍不足。未在本轮为 Golden 硬编码。
3. P1 SOLUTION_COMPILER_PROBLEM — 多个 direct reuse 时 Quick Win 曾等同 Production Fit，摘要模板化且系统集成/历史 claim 边界表达不足。已做通用修复；剩余方案深度仍为 P1。
4. P1 EVIDENCE_PROBLEM — Enterprise Assistant 的 query routing 和结构化 answer composition 造成 fact/citation 命中低、permission leakage 2、insufficient-evidence 0/3。未做面向 36 个 Golden case 的答案硬编码。
5. P2 RETRIEVAL_PROBLEM — 3 个候选中仅 1 个有可执行模块；结果安全但企业能力覆盖不足。
6. P2 CHANGE_WORKFLOW_PROBLEM — 数据只支持 post-baseline additions，没有证据闭合的正式 removal；按 Frozen guard 报 DATA_GAP。

## Fixes / Regression

- `backend/app/process/requirement_extractor.py`：通用清理 dangling `next_node_ids`
- `tests/process/test_requirement_extractor.py`：增加 typed process dangling-edge 回归
- `backend/app/solution/solution_intelligence_compiler.py`：Quick Win 单模块边界、客户目标化摘要、现有系统集成、unresolved risk、历史 claim 警示
- `tests/solution/test_solution_bundle_v2.py`：多 direct-reuse、摘要与 system integration 回归
- 定向回归：33 passed, 1 warning
- 全量回归：585 passed, 1 warning
- Frontend Vite build：PASS
- git diff --check：PASS
- commit/push：未执行
