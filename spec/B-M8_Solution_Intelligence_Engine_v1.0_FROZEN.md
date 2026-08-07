# B-M8 Solution Intelligence Engine 技术规格 v1.0

> **状态：FROZEN / 正式冻结版**  
> **项目：DCForge**  
> **模块负责人：B（Solution Intelligence & Compilation Engine）**  
> **冻结日期：2026-08-07**  
> **代码基线：`main@f7534b565875791e99e0ca9411a9e6858abf6b56`**  
> **现有回归基线：161 passed**  
> **正式工作区：`D:\ai_project\dc-forge`**  
> **目标阶段：40 强版本开发基线**

---

## 0. 本规格的地位

本文件是 DCForge B-M8 的**正式技术规格与实施约束**。Codex、成员 B、其他协作者后续对 B-M8 的实现、测试、接口协作、代码审查，应以本文件为第一依据。

本规格冻结后，除非团队明确形成新的版本（例如 v1.1 / v2.0），不得在实现过程中擅自改变以下核心产品逻辑：

1. B 的定位不是“从零生成方案”，而是“**历史解决方案资产匹配 + 可解释复用决策 + 客户化编译 + DemoBlueprint 输出**”。
2. B 必须同时使用 `SolutionAsset` 与现有 `CapabilityCapsule` 两级资产。
3. 客户流程与历史方案的核心匹配单位采用 AI for Process 的 Action / AI Gene 思路。
4. 推荐必须可解释、可追溯；不得输出无证据的“成功案例效果”。
5. Hard Gate 必须先于 FitScore。
6. `direct_reuse / configuration / customization / unavailable` 四类复用决策必须由确定性规则最终裁决。
7. `SolutionBundleV2` 的三套方案是三种**交付策略**，不是三篇由大模型自由发挥的文案。
8. B 只编译 `DemoBlueprint`，不负责 Runtime 真正执行。
9. 历史证据、当前客户预测值、Runtime 实测值必须严格区分。
10. 现有 v1 合同与 161 个测试在 B-M8 完成前必须保持兼容。

---

# 1. 产品定位

## 1.1 一句话定位

**DCForge B 模块将神州数码历史解决方案沉淀为可检索、可组合、可验证的 Solution-as-Code，通过客户流程 Action / AI Gene 与方案资产进行可解释匹配，自动判断“直接复用、配置适配、客户化开发、当前不可用”，并编译出三档客户方案及可交付给 Runtime 的 DemoBlueprint。**

## 1.2 B 要解决的真实业务问题

神州数码已经拥有大量产品、平台、行业解决方案和客户案例。B-M8 不再假设“企业缺少方案”，而是解决：

- 面对新客户，不知道最接近的历史方案在哪里；
- 找到历史 PPT 后，不知道哪些模块可以直接复用；
- 不知道哪些差异只需配置、哪些必须开发；
- 不知道方案是否满足客户数据、安全、系统、预算、时间等硬约束；
- 方案推荐缺少“为什么”的证据链；
- 方案仍然停留在 PPT，无法直接编译出 Demo 运行蓝图；
- 客户条件变化后，难以定位受影响模块并增量重编译。

## 1.3 核心产品链路

```text
ProcessSpec（A）
        │
        ▼
Action / AIGene Build
        │
        ▼
SolutionAsset Retriever
        │
        ▼
Hard Gate
        │
        ▼
FitAssessment
        │
        ▼
ReuseDecision
        │
        ▼
Solution Intelligence Compiler
        │
        ├── Quick Win
        ├── Production Fit
        └── Transform
        │
        ▼
SolutionBundleV2
        │
        ▼
DemoBlueprint
        │
        ▼
Runtime（C，非 B-M8 执行范围）
```

---

# 2. 官方方法论与业务依据

本规格的产品设计基于神州数码官方资料，而不是自行创造一套与命题割裂的方法。

## 2.1 AI for Process / TD 双驱动

《AI for Process 企业级流程数智化变革蓝皮书》提出 Twin-Drive（TD）建设方法：

- Top-Down Decomposition：从战略和流程逐级拆解；
- Bottom-Up Emergence：从业务痛点和速赢场景切入；
- AI 应用最终需要落到可执行 Action，而不只停在宏观业务域。

本项目不尝试完整实现企业流程治理体系，但 B-M8 必须兼容这一方法：**方案匹配和复用判断必须尽量落到 Action，而不是只匹配“行业标签”或“需求句子”。**

## 2.2 AI Gene

官方蓝皮书对 Action 进行 AI Gene 分析，核心包含：

- Role（角色）
- Object（执行对象）
- Data & Knowledge（数据与知识）
- Technology（技术实现）
- Standards & Rules（标准与规则）
- Tools（工具）

B-M8 将其工程化为 `AIGene` 合同，并在此基础上增加 DCForge 工程字段：

- input / output
- execution_mode
- risk_level
- evidence_refs

新增字段属于 DCForge 工程扩展，不声称为神州数码官方 AI Gene 原字段。

## 2.3 业务价值 × 落地难度

官方蓝皮书使用“业务价值”和“落地难度”对 AI 场景进行四象限评估：

- 高价值、低难度：Quick Win / 优先启动；
- 高价值、高难度：Strategic / 战略攻坚；
- 低价值、低难度：Experiment / 实验探索；
- 低价值、高难度：Avoid / 谨慎规避。

B-M8 必须输出 `business_value_score`、`implementation_difficulty_score` 与 `quadrant`，但具体数值权重属于 DCForge 的工程参数，不应宣称为官方权重。

## 2.4 智能招采是首个 Golden Domain

神州问学智能招采官方材料已经具备完整方案资产形态：

- 招采知识复用；
- 招采/招标/合同文档生成；
- 文档结构解析；
- 审查规则配置；
- 审查点匹配；
- 风险定位；
- 人工复核；
- 企业采购/OA/移动端/第三方系统触点；
- RAG、多模型、向量数据库等技术能力；
- 历史效果证据。

因此智能招采被指定为 B-M8 的首个 Golden Case。

## 2.5 跨行业能力复用依据

官方案例集中，能源“严肃长文本智能生成助手”明确复用了烟草智能招采项目中的**文档审查与结构解析能力**，再结合火电行业规则、碳排放计算等能力形成新方案。

因此 B-M8 必须支持：

```text
已有行业 SolutionAsset
+ 可复用 Module / Capability
+ 新客户业务规则
+ 新客户数据/系统
→ 新客户 SolutionPlan
```

而不是“每个客户都从零生成”。

---

# 3. 范围与非范围

## 3.1 B-M8 P0 范围

必须完成：

1. `SolutionAsset`
2. `AIGene`
3. `EvidenceRecord / ValueClaim` 等支撑合同
4. SolutionAsset curated fixture 资产库
5. Asset Retriever
6. Hard Gate
7. `FitAssessment`
8. `ReuseDecision`
9. Evidence-backed Compilation
10. `SolutionBundleV2`
11. `DemoBlueprint`
12. 智能招采 Golden Case
13. 能源严肃长文本跨行业复用 Golden Case
14. 新约束下 V2 增量重编译 / Diff
15. 全量回归兼容

## 3.2 明确不在 B-M8 P0 范围

以下内容不得为了“看起来更完整”而在 B-M8 偷偷扩张：

- Runtime 真正执行；
- ERP / CRM / OA / SRM 的生产级 Connector；
- Human Gate 真正 pause/resume；
- 大规模互联网自动抓取；
- 全自动 PPT/PDF → 生产资产入库流水线；
- 自动构建几十个行业完整资产库；
- 企业知识图谱平台；
- 复杂多 Agent 自主循环；
- 自动修改现有客户生产系统；
- 自动生成生产级应用源码；
- 未经验证的 ROI 承诺；
- 飞书开放平台 API / 机器人 / 多维表格 / 审批等系统集成。

比赛可以使用飞书 AI 能力（例如秒搭）辅助项目展示或开发，但**飞书系统接入不属于本 B-M8 技术规格，也不得成为 B 的核心依赖**。

---

# 4. 现有代码基线与兼容性约束

当前仓库已有合同：

```text
ProcessSpec
SolutionBundle
SolutionPlan
WorkflowNode
ComponentRef
CompileRequest
RecompileRequest
RecompileResult
RuntimeRequest
RunReport
```

现有 `SolutionPlan` 使用：

```text
plan_type:
- conservative
- balanced
- innovative
```

现有 B 已完成：

```text
ProcessSpec
→ Capability Retriever
→ 3 档 SolutionPlan
→ Constraint Validator
→ Reviewer
→ Recompiler
→ Agent
```

## 4.1 兼容原则

B-M8 必须采用**增量扩展、并行演进**，禁止一开始直接重写 v1。

建议新增：

```text
backend/app/contracts/solution_intelligence.py
```

而不是立即破坏：

```text
backend/app/contracts/solution.py
```

在 B-M8.1 ~ B-M8.4 阶段：

- `/compile-solution` 行为保持不变；
- `/recompile-solution` 行为保持不变；
- `SolutionPlan` schema_version 仍为 `1.0`；
- Runtime v1 不改；
- 161 个历史测试必须继续通过。

只有到 B-M8.5 完成后，才允许增加**新的 v2 服务入口 / API**。

## 4.2 StrictModel 原则

所有新公共合同继续继承：

```python
StrictModel
```

保持：

```python
extra="forbid"
```

不得通过 `dict[str, Any]` 大量绕开合同约束。

---

# 5. 术语定义

| 术语 | 定义 |
|---|---|
| ProcessSpec | A 输出的客户需求与现状流程合同 |
| Action | 流程中可被分析、执行或赋能的基础动作单元 |
| AIGene | 对 Action 业务结构和落地条件的结构化描述 |
| CapabilityCapsule | 单一、可复用技术/业务能力组件 |
| SolutionAsset | 完整或半完整历史解决方案资产 |
| Module | SolutionAsset 内可复用的业务/技术模块 |
| Evidence | 支撑资产、能力、推荐、效果的来源证据 |
| FitAssessment | 客户条件与 SolutionAsset 的适配评估 |
| Hard Gate | 不满足则禁止推荐的硬约束裁决 |
| ReuseDecision | 模块复用方式裁决 |
| Quick Win | 快速验证型交付策略 |
| Production Fit | 生产适配型交付策略 |
| Transform | 流程重构型交付策略 |
| DemoBlueprint | B 输出给 C 的可运行 Demo 描述合同 |
| Historical Value | 历史案例真实结果 |
| Expected Value | 基于当前客户参数计算的预测 |
| Verified Value | Runtime 实际运行测得结果 |

---

# 6. 支撑枚举与基础合同

以下是目标 Pydantic 设计语义。实现时允许根据代码风格拆文件，但字段语义不可擅自改变。

```python
SourceType = Literal[
    "official_solution",
    "official_case",
    "official_bluebook",
    "internal_material",
    "curated_fixture",
]

EvidenceKind = Literal[
    "asset_definition",
    "capability",
    "historical_outcome",
    "business_rule",
    "technical_requirement",
    "reuse_basis",
]

ExecutionMode = Literal[
    "ai_autonomous",
    "ai_assisted",
    "human",
    "system",
]

RiskLevel = Literal["low", "medium", "high", "critical"]

ReuseMode = Literal[
    "direct_reuse",
    "configuration",
    "customization",
    "unavailable",
]

FitQuadrant = Literal[
    "quick_win",
    "strategic",
    "experiment",
    "avoid",
]

ValueClaimType = Literal[
    "historical",
    "expected",
    "verified",
]
```

---

# 7. 核心合同一：SolutionAsset

## 7.1 设计目标

`SolutionAsset` 是历史完整/半完整方案的机器可读表达，不等于 PDF 文本切片。

它必须能够回答：

- 这个方案以前解决什么业务问题？
- 适合哪些流程和 Action？
- 由哪些模块组成？
- 需要什么数据、知识、系统和规则？
- 有哪些部署/安全要求？
- 有什么官方证据？
- 有什么历史效果？
- 有什么边界和限制？

## 7.2 Pydantic 目标结构

```python
class EvidenceRecord(StrictModel):
    evidence_id: str
    source_type: SourceType
    title: str
    document_name: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    kind: EvidenceKind
    statement: str
    verified: bool = False
    source_locator: str | None = None


class ValueClaim(StrictModel):
    claim_id: str
    claim_type: ValueClaimType
    metric_name: str
    value_text: str
    evidence_refs: list[str] = Field(default_factory=list)
    formula: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    run_report_id: str | None = None


class SolutionAssetModule(StrictModel):
    module_id: str
    name: str
    description: str

    capability_ids: list[str] = Field(default_factory=list)

    required_data: list[str] = Field(default_factory=list)
    required_knowledge: list[str] = Field(default_factory=list)
    required_systems: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_rules: list[str] = Field(default_factory=list)

    configurable_items: list[str] = Field(default_factory=list)
    extension_points: list[str] = Field(default_factory=list)

    evidence_refs: list[str] = Field(default_factory=list)


class SolutionAsset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"

    asset_id: str
    name: str
    version: str

    provider: str
    source_type: SourceType

    industries: list[str]
    value_chains: list[str] = Field(default_factory=list)
    processes: list[str]
    scenarios: list[str]

    target_roles: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)

    action_genes: list["AIGene"] = Field(default_factory=list)
    modules: list[SolutionAssetModule]

    supported_data: list[str] = Field(default_factory=list)
    supported_knowledge: list[str] = Field(default_factory=list)
    supported_systems: list[str] = Field(default_factory=list)
    supported_deployments: list[str] = Field(default_factory=list)

    standards_and_rules: list[str] = Field(default_factory=list)
    security_characteristics: list[str] = Field(default_factory=list)

    evidence: list[EvidenceRecord]
    value_claims: list[ValueClaim] = Field(default_factory=list)

    limitations: list[str] = Field(default_factory=list)
    derived_from_asset_ids: list[str] = Field(default_factory=list)
```

## 7.3 校验规则

必须满足：

1. `asset_id` 全库唯一。
2. `module_id` 在单个资产内唯一。
3. `evidence_id` 在单个资产内唯一。
4. 所有 `module.evidence_refs` 必须能解析到本资产 Evidence。
5. `historical` ValueClaim：
   - `evidence_refs` 不得为空；
   - 不得存在 `run_report_id`。
6. `expected` ValueClaim：
   - 必须有 `formula` 或明确计算逻辑；
   - 必须有至少一个 assumption；
   - 不得伪装成历史实测。
7. `verified` ValueClaim：
   - 必须有 `run_report_id`；
   - B 在没有 C RunReport 时不得自行创建。
8. `page_end` 存在时必须 `>= page_start`。
9. 不允许把大段 PPT 原文直接塞进 `statement`。
10. 一个 Asset 没有 Evidence 时可以作为开发 fixture，但不得进入“正式推荐证据库”。

---

# 8. 核心合同二：AIGene

## 8.1 目标

将客户 Action 与历史 SolutionAsset 的业务结构映射到统一空间，避免只做文本相似度 RAG。

## 8.2 Pydantic 结构

```python
class AIGene(StrictModel):
    schema_version: Literal["1.0"] = "1.0"

    gene_id: str
    action_id: str | None = None
    action_name: str

    # 官方 AI Gene 六维
    role: list[str] = Field(default_factory=list)
    object: list[str] = Field(default_factory=list)
    data_and_knowledge: list[str] = Field(default_factory=list)
    technology: list[str] = Field(default_factory=list)
    standards_and_rules: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    # DCForge 工程扩展
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)

    execution_mode: ExecutionMode
    risk_level: RiskLevel = "medium"

    evidence_refs: list[str] = Field(default_factory=list)
```

## 8.3 客户 AIGene 构建来源

客户 Gene 只能来自：

- `ProcessSpec.industry`
- `ProcessSpec.department`
- `ProcessSpec.roles`
- `ProcessSpec.available_data`
- `ProcessSpec.existing_systems`
- `ProcessSpec.as_is_nodes`
- `ProcessSpec.pain_points`
- `ProcessSpec.constraints`
- `ProcessSpec.target_metrics`
- 明确的用户补充信息

不得凭空假设客户已经具备某数据库、接口、规则或组织能力。

## 8.4 LLM 与确定性边界

允许 LLM：

- 把 ProcessNode / pain point 语义映射为 Action；
- 将自然语言规则归一化为 Gene 标签；
- 从人工确认的方案文本中提取候选 Gene。

不得由 LLM 最终决定：

- Hard Gate；
- 资产是否 eligible；
- 最终 FitScore；
- ReuseMode；
- ROI 数值；
- Evidence 是否真实存在。

---

# 9. 核心合同三：FitAssessment

## 9.1 核心原则

**Hard Gate 先于 FitScore。**

不能出现“相似度很高，但客户硬性安全/数据条件完全不满足，仍被推荐”的情况。

## 9.2 支撑合同

```python
class HardGateResult(StrictModel):
    gate_id: str
    category: Literal[
        "security",
        "deployment",
        "data",
        "system",
        "rule",
        "budget",
        "time",
        "risk",
    ]
    passed: bool
    reason: str
    constraint_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FitDimensionScore(StrictModel):
    name: Literal[
        "role",
        "object",
        "data_knowledge",
        "rules",
        "tools_systems",
        "technology",
        "evidence",
    ]
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    explanation: str
```

## 9.3 FitAssessment

```python
class FitAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"

    project_id: str
    asset_id: str

    eligible: bool
    hard_gates: list[HardGateResult]

    dimensions: list[FitDimensionScore]

    raw_fit_score: float = Field(ge=0, le=100)
    effective_fit_score: float | None = Field(default=None, ge=0, le=100)

    business_value_score: float = Field(ge=0, le=100)
    implementation_difficulty_score: float = Field(ge=0, le=100)
    quadrant: FitQuadrant

    matched_action_ids: list[str] = Field(default_factory=list)
    unmatched_action_ids: list[str] = Field(default_factory=list)

    hard_blockers: list[str] = Field(default_factory=list)
    soft_gaps: list[str] = Field(default_factory=list)

    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)
```

## 9.4 Hard Gate v1 规则

至少实现：

- **Security Gate**：客户要求数据不出域/禁止公网模型/必须私有部署，而 Asset 不支持时失败。
- **Data Gate**：必需数据明确不存在且无替代来源时，模块不可直接推荐；若主模块不可替代则整体 block。
- **System Gate**：客户必须接入系统 X，资产无 connector/extension point 且硬性项目周期不可满足时 block；否则作为 customization gap。
- **Rule / Approval Gate**：方案不能保留客户强制审批、人审、合规规则时 block。
- **Budget / Time Gate**：只有已有结构化成本/工期估算明确违反约束时才 block；不得凭感觉判断。

## 9.5 FitScore v1 权重

以下权重为 **DCForge v1 工程参数，不是神州数码官方权重**：

```text
Role                 10%
Object               10%
Data & Knowledge     20%
Standards & Rules    20%
Tools / Systems      15%
Technology           15%
Evidence             10%
                    ----
                    100%
```

```text
raw_fit_score = Σ(dimension_score × weight)
```

规则：

```text
if any required Hard Gate failed:
    eligible = False
    effective_fit_score = None
else:
    eligible = True
    effective_fit_score = raw_fit_score
```

禁止用 LLM 直接输出最终 87、91 等分数。

## 9.6 维度评分最小规则

v1 不追求复杂机器学习 Ranking，先保证可解释和可复现。

每个维度由：

```text
exact / normalized tag match
+ required item coverage
+ explicit gap penalty
```

组成。

同样输入、同样资产库，结果必须完全一致。

---

# 10. Business Value × Implementation Difficulty

## 10.1 原则

四象限思想来自官方 AI for Process；下面的具体评分因子属于 DCForge v1 自定义工程实现。

## 10.2 Business Value v1

| 因子 | 权重 |
|---|---:|
| business_goal_alignment | 30% |
| pain_point_severity | 25% |
| target_metric_relevance | 20% |
| historical_evidence_strength | 15% |
| reuse_leverage | 10% |

## 10.3 Implementation Difficulty v1

| 因子 | 权重 |
|---|---:|
| data_gap | 25% |
| integration_gap | 20% |
| rule_complexity | 20% |
| deployment_security_complexity | 20% |
| customization_effort | 15% |

## 10.4 四象限默认阈值

v1 工程默认：

```text
high value      >= 60
high difficulty >= 60
```

```text
value >= 60 and difficulty < 60  -> quick_win
value >= 60 and difficulty >= 60 -> strategic
value < 60  and difficulty < 60  -> experiment
value < 60  and difficulty >= 60 -> avoid
```

阈值必须集中配置，不得散落 hard-code。

---

# 11. 核心合同四：ReuseDecision

```python
class ReuseDecision(StrictModel):
    schema_version: Literal["1.0"] = "1.0"

    project_id: str
    asset_id: str
    module_id: str

    decision: ReuseMode
    rationale: str

    matched_requirements: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    estimated_effort: Literal[
        "none",
        "small",
        "medium",
        "large",
        "unknown",
    ]

    human_review_required: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
```

## 11.1 四类决策确定性定义

### direct_reuse

必须满足：

- 核心功能一致；
- 必需数据形态已具备；
- 必需规则无冲突；
- 系统/工具已有或无需客户化；
- 不存在硬约束冲突；
- 不需要新增业务代码。

### configuration

核心能力不变，只需要：

- Prompt / 模板；
- 阈值；
- 字段映射；
- 模型选择；
- 审查项；
- 规则参数；
- 审批金额；
- 部署参数；
- 已有 connector 配置。

### customization

至少存在一项：

- 新 API / Connector；
- 新业务流程代码；
- 新算法模块；
- 新规则引擎逻辑；
- 新数据处理链；
- 现有扩展点之外的实现。

### unavailable

存在不可绕过条件：

- 核心数据不存在且无法替代；
- 权限不具备；
- 法规/安全禁止；
- 技术条件当前无法实现；
- 客户要求与方案能力本质冲突；
- 时间/预算硬约束已有明确证据表明不可达。

## 11.2 禁止的错误实现

禁止：

```text
score > 80 -> direct_reuse
score > 60 -> configuration
...
```

ReuseDecision 必须基于**模块级条件规则**，不能仅按总分映射。

---

# 12. Reuse Summary

```python
class ReuseSummary(StrictModel):
    direct_reuse_count: int = Field(ge=0)
    configuration_count: int = Field(ge=0)
    customization_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)

    direct_reuse_ratio: float = Field(ge=0, le=1)
    configuration_ratio: float = Field(ge=0, le=1)
    customization_ratio: float = Field(ge=0, le=1)
    unavailable_ratio: float = Field(ge=0, le=1)
```

ratio 分母为参与本方案决策的模块总数。

```text
abs(sum(ratios) - 1.0) < 1e-6
```

空模块方案不得生成。

---

# 13. 核心合同五：SolutionBundleV2

## 13.1 三种策略

| v1 内部 | v2 展示语义 |
|---|---|
| conservative | Quick Win |
| balanced | Production Fit |
| innovative | Transform |

### Quick Win
成熟资产优先、直接复用最大、客户化最少、Demo 最快，Hard Gate 不放松。

### Production Fit
默认推荐；在成熟资产上适配客户关键规则、系统、安全、人审，平衡价值和落地难度。

### Transform
允许跨 SolutionAsset 组合、更多 customization、重新设计多个 Action，强调流程重构而不是“多加 Agent”。

## 13.2 合同

```python
class SolutionPlanV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"

    solution_id: str
    source_project_id: str

    plan_type: Literal[
        "conservative",
        "balanced",
        "innovative",
    ]

    display_strategy: Literal[
        "quick_win",
        "production_fit",
        "transform",
    ]

    name: str
    summary: str

    primary_asset_ids: list[str]
    supporting_asset_ids: list[str] = Field(default_factory=list)

    fit_assessments: list[FitAssessment]
    reuse_decisions: list[ReuseDecision]
    reuse_summary: ReuseSummary

    selected_components: list[ComponentRef]
    to_be_nodes: list[WorkflowNode]
    applied_constraints: list[BusinessConstraint]

    data_requirements: list[str] = Field(default_factory=list)
    knowledge_requirements: list[str] = Field(default_factory=list)
    system_integrations: list[str] = Field(default_factory=list)

    implementation_steps: list[str]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    evidence_refs: list[str] = Field(default_factory=list)
    value_claims: list[ValueClaim] = Field(default_factory=list)

    demo_blueprint_id: str | None = None

    review_score: float = Field(ge=0, le=100)


class SolutionBundleV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"

    project_id: str
    recommended_solution_id: str

    plans: list[SolutionPlanV2]

    retrieval_asset_ids: list[str]
    warnings: list[str] = Field(default_factory=list)
```

## 13.3 强制规则

1. 必须恰好输出 3 个 plan。
2. 三个 plan_type 必须各出现一次。
3. `recommended_solution_id` 必须引用其中一个方案。
4. 默认推荐应优先 `production_fit`，但若 Hard Gate / Value-Difficulty 明确不支持，可由确定性规则选择其他方案。
5. 每个正式推荐模块必须有 Evidence 或明确标记为 `customization`。
6. `unavailable` 模块不得出现在最终可执行 workflow 中。
7. `historical` ValueClaim 不得脱离 Evidence。
8. `expected` ValueClaim 必须显式显示为预测。
9. B 无 Runtime 数据时不得生成 `verified` ValueClaim。

---

# 14. Evidence / Provenance 规则

任何关键推荐都必须回答：

```text
Why this asset?
Why this module?
Why this reuse mode?
Where did the claim come from?
```

最小闭环：

```text
Recommendation
    │
    ├── Customer Fact / Constraint
    ├── Process Action
    ├── SolutionAsset
    ├── Module
    └── Official Evidence
```

P0：

```text
Evidence Coverage = 100%
Unsupported Historical Claim = 0
```

`customization` 可以没有历史能力证据，但必须有客户 Gap、开发原因、依赖和风险。

---

# 15. 历史、预测、验证价值严格分离

## Historical Value
来自官方方案/案例/确认的历史材料。只能描述历史事实，不能承诺当前客户一定复现。

## Expected Value
必须有公式、输入、assumptions，并明确标记预测/估算。数据不足时应输出 `insufficient_data`，而不是编数字。

示例：

```text
年化流程时间价值
= (原平均时长 - 预计方案时长)
  × 年业务量
  × 单位工时价值
```

## Verified Value
只能由 C Runtime / RunReport 回传；没有 `run_report_id` 不得生成 verified。

---

# 16. 核心合同六：DemoBlueprint

```python
class DemoInput(StrictModel):
    name: str
    type: str
    required: bool = True
    description: str
    fixture_ref: str | None = None


class DemoAssertion(StrictModel):
    assertion_id: str
    description: str
    severity: Literal["info", "warning", "blocking"]
    metric_name: str | None = None
    expected_condition: str


class DemoNode(StrictModel):
    id: str
    name: str

    node_type: Literal[
        "retrieval",
        "transform",
        "llm",
        "rule",
        "tool",
        "human_gate",
        "report",
    ]

    executor: Literal["ai", "human", "system"]

    component_id: str | None = None
    asset_module_id: str | None = None

    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)

    next_ids: list[str] = Field(default_factory=list)

    human_gate: bool = False
    gate_reason: str | None = None

    timeout_seconds: int | None = Field(default=None, gt=0)
    fallback_node_id: str | None = None


class DemoBlueprint(StrictModel):
    schema_version: Literal["1.0"] = "1.0"

    demo_id: str
    project_id: str
    solution_id: str

    title: str
    objective: str

    source_asset_ids: list[str]

    inputs: list[DemoInput]
    nodes: list[DemoNode]

    expected_outputs: list[str]

    metric_names: list[str]
    assertions: list[DemoAssertion]

    required_integrations: list[str] = Field(default_factory=list)
    security_requirements: list[str] = Field(default_factory=list)

    evidence_refs: list[str] = Field(default_factory=list)
```

## 16.1 图结构校验

- node.id 唯一；
- `next_ids` 指向真实节点；
- `fallback_node_id` 存在；
- 不允许不可达孤岛节点；
- `human_gate=True` 时必须是 human executor 或 human_gate node；
- 至少一个起点和终点；
- 禁止明显无限环；
- `unavailable` 模块不得绑定 DemoNode。

---

# 17. 智能招采 Golden Case

这是 DCForge 自己构造的**比赛演示客户 fixture**，不是神州数码官方客户事实。

```yaml
project_id: procurement-demo-40
industry: 制造
department: 采购
business_goal: 缩短招标文件编制与审查周期，并降低合规风险

roles:
  - 采购专员
  - 法务
  - 采购经理

available_data:
  - 历史采购方案
  - 历史招标文件
  - 企业采购制度
  - 审查规则

existing_systems:
  - OA
  - 采购系统

pain_points:
  - 历史案例难检索
  - 招标文件人工编制耗时
  - 审查依赖专家
  - 审查规则多且易遗漏

constraints:
  - type: security
    statement: 数据不得出企业私域
    hard: true

  - type: approval
    statement: 金额超过500000必须人工审批
    hard: true
    parameters:
      threshold: 500000

target_metrics:
  - processing_time
  - manual_steps
  - risk_findings
```

Golden Expectations：

1. `dc-smart-procurement` 进入 Top 3。
2. `dc-tobacco-smart-procurement` 进入 Top 3 或作为强 supporting asset。
3. 不因行业“制造”而错误过滤智能招采。
4. Security Gate 必须验证部署兼容。
5. Human approval constraint 必须保留。
6. 至少识别知识/案例检索、文档生成、文档解析、审查、风险定位、人工复核。
7. 若采购系统没有现成 connector，应为 `customization`，不得伪装 `direct_reuse`。
8. DemoBlueprint 必须包含 human gate。
9. Historical Value 必须明确标记历史案例。
10. 不得产生未经 Evidence 支撑的客户收益承诺。

---

# 18. 跨行业复用 Golden Case

官方业务依据：

```text
烟草智能招采
    │
    ├── 文档审查
    └── 结构解析
            │
            ▼
迁移到能源严肃长文本
    +
火电行业规则
    +
碳排放计算
```

Golden Expectations：

1. 能源长文本 SolutionAsset 可被直接召回。
2. 系统能展示其 `derived_from_asset_ids` / lineage。
3. 文档结构解析模块具备跨行业可复用属性。
4. 文档审查模块可复用/配置。
5. 火电行业标准、碳计算不得错误判成“直接复用自招采”。
6. 行业专属规则进入 `configuration` 或 `customization`。
7. 方案说明解释哪些来自历史招采能力、哪些是能源新增。
8. 不允许因为文本语义相似就声称技术完全相同。

---

# 19. 初始 SolutionAsset Corpus

P0 至少完成 6 个经过人工校验的 curated assets：

```text
1. dc-smart-procurement
   神州问学智能招采解决方案

2. dc-tobacco-smart-procurement
   烟草智能招采助手

3. dc-energy-serious-longtext
   能源严肃长文本智能生成助手

4. dc-super-employee
   神州数码超级员工

5. dc-medical-evidence-assistant
   医药智能循证助手

6. dc-auto-store-mate
   汽车门店 Mate / 智能陪练案例
```

P0 禁止为了数量扩张而批量生成低质量资产。

---

# 20. Asset Repository 与检索

## 20.1 P0 存储

```text
data/solution_assets/
    dc-smart-procurement.json
    dc-tobacco-smart-procurement.json
    dc-energy-serious-longtext.json
    dc-super-employee.json
    dc-medical-evidence-assistant.json
    dc-auto-store-mate.json
```

无需一开始引入数据库。

## 20.2 Repository

```python
class AssetRepository:
    def list_assets(self) -> list[SolutionAsset]: ...
    def get_asset(self, asset_id: str) -> SolutionAsset: ...
```

加载时严格校验并 fail fast。

## 20.3 Retriever P0

```text
结构化过滤
+
关键词/标签
+
轻量语义召回
```

建议顺序：

```text
industry/process/action candidate recall
        ↓
hard-compatible filtering
        ↓
gene-level pre-score
        ↓
Top-K
```

```python
class AssetCandidate(StrictModel):
    asset_id: str
    retrieval_score: float = Field(ge=0, le=100)
    matched_terms: list[str] = Field(default_factory=list)
    matched_gene_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
```

**Retriever score != FitScore。**

---

# 21. LLM 职责冻结

## LLM 可以做

- 自然语言需求语义归一化；
- AIGene 候选提取；
- 资产文档候选字段抽取；
- 语义召回辅助；
- 适配说明；
- 客户化方案文案；
- implementation narrative；
- Diff 解释；
- 用户可读摘要。

## 必须确定性

- Pydantic validation；
- Hard Gate；
- Constraint 判断；
- FitScore 最终计算；
- Value/Difficulty 最终计算；
- ReuseMode 最终裁决；
- Evidence 引用合法性；
- Historical/Expected/Verified 分类；
- ROI 数学计算；
- DemoBlueprint 图校验；
- Recompile Diff；
- Unsupported Claim 检测。

> **LLM 负责理解与建议；程序负责裁决与证明。**

---

# 22. 无 LLM 安全回退

- 单元测试不得依赖真实 Qwen；
- Golden Case 必须无 API Key 可跑；
- 允许 Fake Provider；
- Fit / Reuse / Evidence / Blueprint 必须无 LLM 可复现；
- 有 LLM 时只增强语义理解和说明质量。

---

# 23. 建议代码目录

```text
backend/app/
├── contracts/
│   ├── common.py
│   ├── process.py
│   ├── solution.py
│   ├── runtime.py
│   └── solution_intelligence.py
│
└── solution/
    ├── asset_repository.py
    ├── asset_retriever.py
    ├── gene_builder.py
    ├── fit_engine.py
    ├── reuse_planner.py
    ├── evidence.py
    ├── value_engine.py
    ├── compiler_v2.py
    └── demo_blueprint.py

data/
└── solution_assets/
    ├── dc-smart-procurement.json
    ├── dc-tobacco-smart-procurement.json
    ├── dc-energy-serious-longtext.json
    ├── dc-super-employee.json
    ├── dc-medical-evidence-assistant.json
    └── dc-auto-store-mate.json

tests/solution/
├── test_solution_asset_contract.py
├── test_asset_repository.py
├── test_gene_builder.py
├── test_asset_retriever.py
├── test_fit_engine.py
├── test_hard_gates.py
├── test_reuse_planner.py
├── test_evidence_rules.py
├── test_value_engine.py
├── test_solution_bundle_v2.py
├── test_demo_blueprint.py
├── test_golden_procurement_v2.py
└── test_golden_cross_industry_reuse.py

spec/
└── B-M8_Solution_Intelligence_Engine_v1.0.md
```

不要求 Codex 一次性创建全部文件，必须按里程碑逐步落地。

---

# 24. 服务层建议接口

```python
class GeneBuilder:
    def build_from_process(self, process: ProcessSpec) -> list[AIGene]:
        ...


class AssetRetriever:
    def retrieve(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        top_k: int = 5,
    ) -> list[AssetCandidate]:
        ...


class FitEngine:
    def assess(
        self,
        process: ProcessSpec,
        genes: list[AIGene],
        asset: SolutionAsset,
    ) -> FitAssessment:
        ...


class ReusePlanner:
    def plan(
        self,
        process: ProcessSpec,
        asset: SolutionAsset,
        fit: FitAssessment,
    ) -> list[ReuseDecision]:
        ...


class SolutionIntelligenceCompiler:
    def compile(self, process: ProcessSpec) -> SolutionBundleV2:
        ...


class DemoBlueprintCompiler:
    def compile(
        self,
        process: ProcessSpec,
        solution: SolutionPlanV2,
    ) -> DemoBlueprint:
        ...
```

---

# 25. HTTP API 策略

B-M8.1 ~ B-M8.4：不增加公开 API，先稳定 contracts/services/fixtures/tests。

B-M8.5 后建议增加：

```text
POST /compile-solution-v2
POST /recompile-solution-v2
```

现有 `/compile-solution`、`/recompile-solution` 保持不变。

---

# 26. 增量重编译 V2

```text
new constraint
    ↓
detect affected genes
    ↓
rerun related hard gates
    ↓
rerun related fit dimensions
    ↓
rerun affected reuse decisions
    ↓
recompile affected plan modules
    ↓
recompile affected demo nodes
    ↓
emit diff
```

建议：

```python
class SolutionIntelligenceDiff(StrictModel):
    changed_asset_ids: list[str] = Field(default_factory=list)
    changed_fit_asset_ids: list[str] = Field(default_factory=list)
    changed_module_ids: list[str] = Field(default_factory=list)
    reuse_mode_changes: dict[str, str] = Field(default_factory=dict)

    added_demo_node_ids: list[str] = Field(default_factory=list)
    removed_demo_node_ids: list[str] = Field(default_factory=list)
    changed_demo_node_ids: list[str] = Field(default_factory=list)

    value_claim_changes: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
```

关键要求：

```text
审批阈值变化
→ 只影响 rule / human gate / 相关指标
→ 不应无意义重写检索与知识模块
```

---

# 27. 测试策略

B-M8 必须继续：

```text
Spec
→ failing test
→ minimal implementation
→ regression
```

## 27.1 Contract Tests

验证 strict model、enum、required fields、range、bad refs、bad historical claim、bad verified claim、Demo 图错误。

## 27.2 Repository Tests

验证：

- 6 个资产全部可加载；
- id 唯一；
- evidence refs 完整；
- ValueClaim 合法；
- 无 silently ignored 字段。

## 27.3 Hard Gate Tests

至少：

- private deployment pass/fail；
- data unavailable；
- required approval missing；
- system customization vs hard block；
- budget/time 只有结构化证据才能 block。

## 27.4 Fit Engine Tests

- 同输入同输出；
- weights 总和为 1；
- hard fail 后 effective score=None；
- 高语义相似不能绕过 Hard Gate；
- dimension explanation 非空。

## 27.5 Reuse Tests

每种状态必须有正反例：

```text
direct_reuse
configuration
customization
unavailable
```

## 27.6 Evidence Tests

- historical 没 Evidence -> fail；
- expected 没 assumption/formula -> fail；
- verified 没 RunReport -> fail；
- dangling evidence ref -> fail；
- golden final bundle Evidence Coverage 100%。

## 27.7 Golden Procurement

完整跑：

```text
ProcessSpec
→ Gene
→ Retrieval
→ Fit
→ Reuse
→ BundleV2
→ DemoBlueprint
```

不使用真实 LLM API。

## 27.8 Cross-industry

验证 tobacco procurement → document parsing/review → energy long text 的 lineage 与能力迁移。

## 27.9 Regression

每个里程碑结束：

```powershell
python -m pytest tests/test_contracts.py -q
python -m pytest tests/solution -q
python -m pytest -q
```

现有历史测试必须继续通过。

---

# 28. 业务验收指标

| 指标 | P0 标准 |
|---|---|
| Golden Asset Recall@3 | 智能招采核心资产进入 Top3 |
| Hard Constraint Violation | 0 |
| Evidence Coverage | 100% |
| Unsupported Historical Claim | 0 |
| Fit Determinism | 100% |
| Reuse Determinism | 100% |
| DemoBlueprint Schema Valid | 100% |
| Golden Case End-to-End | 通过 |
| Cross-industry Reuse Case | 通过 |
| Existing Regression | 现有测试全绿 |

---

# 29. B-M8.1 ~ B-M8.7 实施顺序

## B-M8.1 — Asset Foundation

只做：

- 新合同基础；
- `SolutionAsset`
- `AIGene`
- `EvidenceRecord`
- `ValueClaim`
- 6 个 curated asset fixtures；
- contract/repository tests。

**DoD：**资产可严格加载，证据引用闭环，旧测试全绿。

## B-M8.2 — Asset Retrieval

只做：

- GeneBuilder v1；
- AssetCandidate；
- AssetRetriever；
- Top-K；
- procurement retrieval tests。

**DoD：**智能招采 Golden 输入核心资产进入 Top3；无真实 LLM 也可跑。

## B-M8.3 — Gene Fit Engine

只做：

- HardGateResult；
- FitDimensionScore；
- FitAssessment；
- Hard Gate；
- deterministic FitScore；
- Value × Difficulty。

**DoD：**所有评分可解释、可复现；Hard Gate 无法被高相似度绕过。

## B-M8.4 — Reuse Planner

只做：

- ReuseDecision；
- ReuseSummary；
- module-level rules；
- gap analysis；
- cross-industry reuse lineage。

**DoD：**四种 reuse mode 完整测试；能源跨行业案例成立。

## B-M8.5 — SolutionBundleV2

只做：

- Quick Win；
- Production Fit；
- Transform；
- Evidence-backed plan；
- value claim separation；
- v2 service/API。

**DoD：**三种方案不是纯文案差异，而是资产选择、复用比例、客户化程度、流程改造程度可解释地不同。

## B-M8.6 — DemoBlueprint

只做：

- DemoInput；
- DemoNode；
- DemoAssertion；
- DemoBlueprint；
- graph validator；
- procurement blueprint。

**DoD：**C 无需阅读 B 内部代码，仅凭 Blueprint 就能理解 Demo 输入、节点、工具、人审和指标。

## B-M8.7 — Feedback Recompile V2

只做：

- 新 BusinessConstraint；
- affected scope；
- Fit / Reuse incremental recompute；
- Solution diff；
- Blueprint diff。

**DoD：**改变一个审批阈值，不允许把整个方案无意义重写。

---

# 30. Codex 实现纪律

Codex 读取本规格后必须遵守：

1. 先检查当前仓库真实实现，不能假设文件不存在/存在。
2. 每次只实现当前指定里程碑。
3. 先写/更新对应测试，再实现。
4. 不擅自修改 A/C 模块。
5. 不擅自替换当前 v1 API。
6. 不擅自引入大型依赖。
7. 不把确定性逻辑改成 LLM。
8. 不调用真实付费模型完成单元测试。
9. 不伪造官方案例数据。
10. 不伪造客户 ROI。
11. 不删除现有 outputs / fixtures。
12. 不修改 Git 历史。
13. 每阶段结束必须跑全量回归。
14. 若规格与真实代码冲突：停止、报告冲突、给出最小兼容方案，不自行改规格。

---

# 31. 禁止事项

违反以下任一项视为违反 Spec：

1. 把 `SolutionAsset` 退化成 `title + description + embedding`。
2. 只用向量相似度作为最终推荐分数。
3. LLM 直接输出 FitScore。
4. 用 FitScore 阈值直接映射 ReuseMode。
5. Hard Gate 失败仍进入推荐方案。
6. 历史案例值直接当当前客户预测值。
7. 没有 RunReport 却输出 verified。
8. 把 customization 写成 direct reuse 以提高复用率。
9. 为 Demo 好看伪造 ERP/CRM/SRM 已接通。
10. 一口气重构现有 B-M1~B-M7。

---

# 32. Definition of Done — B-M8 总体验收

## Contracts
- [ ] SolutionAsset 完成
- [ ] AIGene 完成
- [ ] FitAssessment 完成
- [ ] ReuseDecision 完成
- [ ] SolutionBundleV2 完成
- [ ] DemoBlueprint 完成

## Assets
- [ ] 至少 6 个官方资料人工校验 SolutionAsset
- [ ] Evidence 引用完整
- [ ] 历史 ValueClaim 可追溯
- [ ] 跨行业 lineage 可表达

## Intelligence
- [ ] Retriever 可解释
- [ ] Hard Gate 可用
- [ ] FitScore deterministic
- [ ] Value/Difficulty 可解释
- [ ] ReuseMode deterministic

## Compilation
- [ ] Quick Win 可生成
- [ ] Production Fit 可生成
- [ ] Transform 可生成
- [ ] 三套策略实际结构不同
- [ ] 推荐来源可解释

## Demo
- [ ] Golden procurement DemoBlueprint 合法
- [ ] Human Gate 保留
- [ ] unavailable module 不进入 workflow
- [ ] metric/assertion 合法

## Value
- [ ] Historical / Expected / Verified 严格分离
- [ ] Unsupported Historical Claim = 0

## Golden
- [ ] 智能招采全链路通过
- [ ] 能源跨行业复用通过

## Regression
- [ ] 旧合同兼容
- [ ] 旧 API 未破坏
- [ ] 现有历史测试全部通过
- [ ] B-M8 新测试全部通过
- [ ] Git 工作区无意外污染

---

# 33. 40 强版本 B 的最终对外表达

不得表述成：

> “我们用大模型生成三套方案。”

正式表述：

> **DCForge 不让 AI 替神州数码重新发明解决方案，而是把历史成功交付沉淀成 SolutionAsset，以 AI for Process 的 Action / AI Gene 为业务匹配骨架，对新客户执行 Hard Gate、Fit Assessment 和模块级复用裁决，明确哪些能力可直接复用、哪些只需配置、哪些需要定制、哪些当前不可用，再编译为 Quick Win、Production Fit、Transform 三种交付策略和可运行 DemoBlueprint。**

推荐产品句：

> **让神州数码过去每一次成功交付，都成为下一次客户方案可复用、可解释、可验证的资产。**

> **传统方案让客户想象未来，DCForge 让方案先被编译，再让未来被运行验证。**

---

# 34. 来源依据（供 Codex / 团队核查）

本规格设计主要依据用户提供的神州数码官方材料：

1. **《AI for Process 企业级流程数智化变革蓝皮书》**
   - TD 双驱动、L1~L5、AI Gene：约第 11~13 页；
   - 场景分类、业务价值 × 落地难度：约第 14~18 页；
   - 企业 AI ROI 测算：约第 22~27 页；
   - 智能流程工作台、AI 渗透率、流程数据闭环：后续技术体系章节。

2. **《神州问学-智能招采解决方案》**
   - 招采用户旅程与痛点：第 5 页；
   - 业务蓝图：第 7 页；
   - 技术架构：第 8 页；
   - 招标文件生成：第 9 页；
   - 招标文件审查：第 10~12 页；
   - 招采知识库：第 13 页。

3. **《神州问学案例合集》**
   - 能源严肃长文本：第 14 页；
   - 神州数码超级员工：第 16 页；
   - 烟草数字员工与风险识别：第 17 页；
   - 烟草智能招采：第 18 页；
   - 汽车门店 Mate：第 19 页。

4. **《神州问学产品 deck》**
   - AI for Process / Agent 平台：第 10 页；
   - 知识治理与人机协作：第 11 页；
   - 神州问学产品与企业级 AI 构建能力：第 13~15 页。

说明：

- Fit 权重、阈值、Pydantic 字段、Reuse 四分类、代码目录等属于 **DCForge 工程设计**；
- 不得对外声称这些字段和权重全部来自神州数码官方方法论；
- 官方方法论提供方向和业务依据，DCForge 负责将其工程化。

---

# 35. Freeze Notice

**本文件自 v1.0 起正式冻结。**

下一步开发必须从：

```text
B-M8.1 — Asset Foundation
```

开始。

在 B-M8.1 完成并通过回归之前，禁止 Codex 直接实现 B-M8.2 ~ B-M8.7。

任何需要改变本规格核心合同、Reuse 语义、Evidence 规则、Hard Gate 原则或 B/C 边界的变更，都必须先形成新的 Spec 版本再实施。

---

**END OF SPEC — B-M8 Solution Intelligence Engine v1.0 / FROZEN**
