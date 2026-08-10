# Requirement Intelligence Engine 技术规格 v1.0（FROZEN）

> **状态：FROZEN / 正式冻结版；15 项产品与架构审计决策已收敛；R-M1 Requirement Foundation = CLOSED。**
> **项目：DCForge**
> **模块：Customer Context & Requirement Intelligence Engine**
> **模块负责人：B（Requirement Intelligence + Solution Intelligence）**
> **Draft 日期：2026-08-10**
> **RC 审计修订日期（历史）：2026-08-10**
> **Requirement Intelligence 正式实现基线：`main@0ca49c7d53f738234d42a63392f5cb17b797f25f`**
> **既有正式回归基线：259 passed, 1 warning**
> **正式工作区：`D:\ai_project\dc-forge`**
> **下游 B-M8 Solution Intelligence 冻结基线：`main@b6b5855487a7fc8b4dc9303c4f4ecdba4f3068ca`**

> **Freeze Notice：本文档现为 FROZEN / 正式冻结版。15 项产品与架构审计决策已收敛，R-M1 Requirement Foundation = CLOSED。文中 RC / Pre-Freeze 叙述仅保留为审计历史，不改变当前冻结状态。后续 R-M2 ~ R-M5 必须保持既有多源 Customer Context、动态 `ext:<domain>:<key>`、Process/Pain Typed Detail、Provenance、Confirmation、ContextEvidence、Repository、RequirementDiffRouter、customer-confirmed Baseline 与 Automotive Golden 语义。**

---

# 0. 本规格的地位

本文件是 DCForge **Requirement Intelligence Engine v1.0** 的正式冻结技术规格。

它冻结以下已确认的产品与工程语义：

- 产品边界；
- 客户上下文输入模型；
- Requirement Truth 数据模型；
- 多轮需求澄清状态机；
- 来源与证据追踪；
- 缺口、冲突、确认与版本语义；
- Readiness Gate；
- Next Best Question；
- Requirement Baseline；
- `RequirementBaseline -> ProcessSpec` 适配；
- Requirement Diff 与既有 B-M8.7 Recompile V2 的衔接；
- Golden Case 与测试策略。

**本文档当前状态为 FROZEN；15 项产品/架构审计决策已收敛，R-M1 Requirement Foundation = CLOSED。**

文中 Draft / RC / Pre-Freeze 仅为历史审计记录：

- 后续 R-M2 ~ R-M5 不得擅自修改本文冻结语义；
- 不应修改已冻结 B-M8 核心语义；
- 不应为了后续实现而破坏既有回归测试。

---

# 1. 官方命题依据

本模块直接响应《神州数码 x 飞书 AI 先锋大赛课题说明》与官方 “AI for Process：To B 直客售前流程的重新设计与实现” 图示。

官方明确要求售前工作同时综合三类信息：

1. **当前客户与项目**
   - 客户基本资料和组织关系；
   - 客户联系人及其职责；
   - 会议纪要、邮件和历史沟通记录；
   - 招标文件、需求说明或客户提供材料；
   - 客户明确提出的业务需求；
   - 项目目标、预算、时间和资源约束；
   - 项目当前状态和历史推进情况；
   - 销售、售前人员对项目的初步判断。

2. **企业内部知识资产**
   - 行业 Know-how 与专家经验；
   - 产品、服务、解决方案与能力边界；
   - 历史售前方案；
   - 成功与失败案例；
   - 咨询方法、模板、规则和评审标准等。

3. **外部动态信息**
   - 政策、法规与监管；
   - 行业、市场、标杆和经营数据；
   - 新技术与适用条件；
   - 竞争对手、替代方案；
   - 客户公开信息、新闻、研究报告等。

官方同时要求 AI 能够参与：

- 需求提取与需求补充；
- 会议纪要和招标文件分析；
- 项目上下文读取；
- 知识与工具调用；
- 人工修改、确认与继续执行；
- 客户反馈进入后续工作。

因此本模块**不能被设计成“只分析飞书聊天记录的 Agent”**。

---

# 2. 产品定位

## 2.1 一句话定位

**Requirement Intelligence Engine 将客户档案、会议纪要、邮件、历史沟通、招标/需求文件、项目状态与实时客户对话统一转化为可追溯、可确认、可版本化的 Requirement Truth；在需求足够完整并经人工/客户确认后，编译为现有 `ProcessSpec`，交给已冻结的 Solution Intelligence Engine。**

## 2.2 核心业务问题

真实 To B 售前中，客户需求通常不是一次性、结构化、稳定出现的。

典型问题：

- 信息散落在聊天、邮件、会议纪要、招标文件和 CRM；
- 同一需求在不同资料里表达方式不同；
- 客户前后说法可能变化；
- 销售判断、AI 推断和客户事实容易混在一起；
- 不知道哪些信息已经确认、哪些仍待确认；
- 不知道当前是否足够进入正式方案设计；
- 售前人员容易一次追问大量问题，客户体验差；
- 客户后续修改需求后，难以准确识别变化及其下游影响。

本模块解决的不是“写一份需求总结”，而是持续维护 **Requirement Truth**。

---

# 3. DCForge 新的双智能核心

DCForge Intelligence Core 由两个明确分层的智能引擎组成：

```text
客户 / 销售 / 项目资料
        │
        ▼
Customer Context
        │
        ▼
Requirement Intelligence Engine
        │
        ├── 多源信息理解
        ├── Requirement State
        ├── Gap / Conflict
        ├── Readiness
        ├── Next Best Question
        └── Confirmation / Version
        │
        ▼
Requirement Baseline
        │
        ▼
ProcessSpec
        │
        ▼
B-M8 Solution Intelligence Engine（FROZEN）
        │
        ├── AIGene
        ├── SolutionAsset Retrieval
        ├── Hard Gate
        ├── Fit
        ├── Reuse
        ├── 3 Strategies
        ├── DemoBlueprint
        └── Feedback Recompile V2
```

两层分别回答：

- **Requirement Intelligence：客户到底要什么？**
- **Solution Intelligence：基于已确认需求，我们应该给客户什么？**

---

# 4. 与成员 A 的正式职责边界

## 4.1 A：Conversation / Interaction Layer

A 负责：

- 飞书机器人；
- 客户消息收发；
- 会话 ID / Turn ID；
- 文件与附件入口；
- 展示 Requirement Engine 返回的问题；
- 收集客户回答；
- 客户确认动作的交互；
- 将原始上下文可靠传给 Requirement Intelligence。

A **不负责维护最终 Requirement Truth**。

A 不应提前将客户原话改写成“确定需求”再传给 B。

## 4.2 Requirement Intelligence

本模块负责：

- 多源客户上下文摄取；
- 需求提取；
- 语义归一；
- 来源追踪；
- 需求状态维护；
- 缺口检测；
- 冲突检测；
- Requirement Readiness；
- Next Best Question；
- 客户/售前确认；
- Requirement Baseline；
- Requirement Version / Diff；
- `RequirementBaseline -> ProcessSpec`。

正式边界：

> **A 管 Conversation；Requirement Intelligence 管 Requirement Truth。**

---

# 5. 信息层级与 Truth Boundary

系统必须严格区分：

## 5.1 Customer Truth Sources

可以产生 Requirement Candidate 的客户/项目资料：

- 客户档案；
- 组织及联系人信息；
- 实时客户对话；
- 会议纪要；
- 邮件；
- 历史沟通；
- 招标文件；
- 需求说明；
- 客户附件；
- 项目目标/状态；
- CRM 项目信息；
- 销售/售前记录。

## 5.2 Internal Knowledge

企业内部知识用于：

- 提供行业 Know-how；
- 提供需求澄清框架；
- 提醒可能遗漏的问题；
- 帮助解释客户场景；
- 后续进入 Solution Intelligence。

**内部知识不能自动成为当前客户事实。**

例如：

> “某历史汽车客户存在供应商准入不统一问题”

不能自动得到：

> “当前客户存在供应商准入不统一问题”。

它只能触发候选追问。

## 5.3 External Intelligence

外部政策、行业案例、竞品和市场信息用于：

- 提醒潜在约束；
- 辅助风险识别；
- 触发客户确认问题；
- 后续进入方案 Evidence。

**外部信息也不能自动成为当前客户 Requirement Truth。**

---

# 6. 核心数据流

```text
CustomerContextPackage
        │
        ▼
Source Ingestion
        │
        ▼
Requirement Extraction
        │
        ▼
Normalization
        │
        ▼
Requirement Candidate
        │
        ▼
Deterministic State Reducer
        │
        ├── Provenance
        ├── Conflict
        ├── Supersede
        └── Version
        │
        ▼
RequirementState
        │
        ├── Gap Detector
        ├── Readiness Evaluator
        └── Question Planner
        │
        ▼
RequirementAnalysis
        │
        ├── updated_state
        ├── changes
        ├── next_questions
        └── readiness
        │
        ▼
A / 前端继续客户沟通
        │
        └───────────────↺

人工 / 客户确认
        │
        ▼
RequirementBaseline
        │
        ▼
ProcessSpecAdapter
        │
        ▼
ProcessSpec
        │
        ▼
B-M8 Solution Intelligence
```

---

# 7. 公共合同设计

所有公共合同必须继承现有 `StrictModel`，保持 `extra="forbid"`。

---

## 7.1 `CustomerSourceChunk`

用于长文档的可定位文本片段。Requirement Engine 不要求把整份 PDF / DOCX / PPTX 全量塞入单个字符串。

```python
class CustomerSourceChunk(StrictModel):
    chunk_id: str
    text: str
    locator: str | None
```

要求：

- `chunk_id` 在同一 `CustomerSourceRecord` 内唯一；
- `text` 不得为空；
- `locator` 可表达页码、段落、sheet、slide、message id 等定位；
- chunk 是客户来源材料的分析表示，不改变原始文件本身。

---

## 7.2 `CustomerContact` / `CustomerOrganizationContext`

v1 需要轻量表达客户组织、联系人与职责，但**不建设完整 CRM**。

```python
class CustomerContact(StrictModel):
    contact_id: str
    name: str
    role: str | None
    department: str | None
    influence: Literal["unknown", "user", "influencer", "decision_maker"] = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerOrganizationContext(StrictModel):
    organization_name: str
    industry: str | None
    department: str | None
    organization_notes: list[str] = Field(default_factory=list)
```

说明：

- 联系人/组织字段只用于客户项目上下文；
- 不在 v1 建设组织权限、CRM 同步、通讯录治理；
- 若后续发现额外客户组织信息，可放入 `metadata` 或动态 Requirement Category，不能因为合同固定字段而丢弃信息。

---

## 7.3 `CustomerSourceRecord`

表示进入 Requirement Engine 的一条客户/项目来源。

```python
class CustomerSourceRecord(StrictModel):
    source_id: str
    project_id: str

    source_type: Literal[
        "customer_profile",
        "conversation",
        "meeting_minutes",
        "email",
        "historical_communication",
        "bid_document",
        "requirement_document",
        "customer_attachment",
        "crm_record",
        "project_status",
        "sales_note",
    ]

    title: str

    inline_content: str | None = None
    document_ref: str | None = None
    chunks: list[CustomerSourceChunk] = Field(default_factory=list)

    occurred_at: str | None = None
    author_role: str | None = None

    locator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

严格规则：

- `inline_content / document_ref / chunks` 至少有一种可用内容表示；
- 短消息、邮件正文、会议摘要优先使用 `inline_content`；
- 大文件优先使用 `document_ref + chunks`；
- 二进制 PDF/OCR/Office 文档解析不是本合同职责；
- `metadata` 只承载来源级动态补充信息，不允许替代 Requirement Truth；
- 不能因 source type 枚举未覆盖某个业务字段而丢弃该信息：未知业务事实应进入动态 Requirement Category，而不是随意增加未受控顶层字段。

---

## 7.4 `CustomerContextPackage`

一次分析的客户上下文包。

```python
class CustomerContextPackage(StrictModel):
    project_id: str

    organization: CustomerOrganizationContext | None = None
    contacts: list[CustomerContact] = Field(default_factory=list)

    sources: list[CustomerSourceRecord]

    previous_state_version: int | None = None

    requirement_skill_ids: list[str] = Field(default_factory=list)

    context_evidence: list["ContextEvidence"] = Field(default_factory=list)
```

要求：

- `sources` 至少 1 条；
- 所有 `source.project_id` 必须与 package 一致；
- `source_id` 在项目内唯一；
- `contact_id` 在项目内唯一；
- Skill 支持叠加，而不是单一绑定：例如 `procurement-core-v1 + automotive-procurement-v1`；
- `context_evidence` 只影响问题建议、风险提示和后续 Solution Evidence，**不得自动成为客户 Requirement Truth**。

---

## 7.5 `RequirementSourceRef`

Requirement 对原始来源的证据引用。

```python
class RequirementSourceRef(StrictModel):
    source_id: str
    locator: str | None
    excerpt: str
```

要求：

- `source_id` 必须存在于当前项目来源集中；
- `excerpt` 不得为空；
- Requirement 的来源必须可追溯。

---

## 7.6 `ProcessObservation` / `PainPointObservation`

普通需求继续由通用 `RequirementItem` 表达；但 `current_process` 与 `pain_point` 需要稳定映射到现有 `ProcessSpec`，因此 v1 增加两个轻量 Typed Detail。

```python
class ProcessObservation(StrictModel):
    process_node_id: str
    name: str
    actor: str
    node_type: Literal["human", "system", "ai"]
    description: str
    next_node_ids: list[str] = Field(default_factory=list)


class PainPointObservation(StrictModel):
    pain_point_id: str
    description: str
    severity: Literal["low", "medium", "high"]
    affected_process_node_ids: list[str] = Field(default_factory=list)
```

严格语义：

- `category=current_process` 时，正式 Baseline 中必须有 `process_detail`；
- `category=pain_point` 时，正式 Baseline 中必须有 `pain_point_detail`；
- 其他 category 不应伪造这两个 detail；
- 这样既保留通用 RequirementItem，也避免在 R-M5 依靠自由 `parameters` 猜测 `ProcessNode/PainPoint`。

---

## 7.7 `ContextEvidence`

外部情报和内部 Know-how 可以形成独立 Context Evidence，但不属于 Customer Truth。

```python
class ContextEvidence(StrictModel):
    evidence_id: str
    evidence_type: Literal[
        "internal_knowhow",
        "internal_solution",
        "external_policy",
        "external_benchmark",
        "public_business_data",
    ]

    title: str
    source_name: str
    source_ref: str
    published_at: str | None = None
    reliability: Literal["low", "medium", "high"]
    applicable_scope: list[str] = Field(default_factory=list)
    summary: str
```

允许用途：

- 触发 Next Best Question；
- 形成风险提示；
- 进入后续 Solution Evidence；
- 帮助解释行业背景。

禁止：

- 自动生成 `status=confirmed` 的客户 Requirement；
- 用行业共性替代当前客户事实；
- 用历史案例效果替代当前客户目标值。

---

## 7.8 `RequirementItem`

表示系统当前维护的一条需求事实/候选事实。

```python
class RequirementItem(StrictModel):
    requirement_id: str

    category: RequirementCategory

    subject: str
    value: str
    parameters: dict[str, Any]

    provenance: Literal[
        "customer_raw",
        "ai_extracted",
        "ai_inferred",
        "human_modified",
        "sales_judgment",
        "presales_judgment",
    ]

    status: Literal[
        "pending",
        "confirmed",
        "rejected",
        "conflicted",
        "superseded",
    ]

    confirmation_level: Literal[
        "none",
        "internal",
        "customer",
    ] = "none"

    confidence: float

    source_refs: list[RequirementSourceRef]

    process_detail: ProcessObservation | None = None
    pain_point_detail: PainPointObservation | None = None

    supersedes_requirement_ids: list[str]
```

### 关键语义

`provenance` 与 `status` 必须分离。

例如：

```text
provenance = ai_extracted
status = confirmed
```

表示该条目最初由 AI 从客户资料提取，但后来已经得到人工/客户确认。

### 禁止事项

- `ai_inferred` 不得自动变为 `confirmed`；
- `sales_judgment / presales_judgment` 只能作为内部判断来源，不能自动成为 Customer Confirmed Truth；
- 无来源 Requirement 不得成为 `confirmed`；
- `confidence` 不得代替人工确认；
- `confirmation_level=internal` 只能支撑 Preliminary 分析，不能生成正式 RequirementBaseline；
- 正式 Baseline 的事实必须满足 `status=confirmed` 且 `confirmation_level=customer`；
- `status=confirmed` 不代表来源是 AI 生成。

---

# 8. Requirement Categories v1：核心分类 + 动态扩展

v1 不把客户需求锁死在一组永远不变的字段中。

## 8.1 Core Categories

核心标准分类用于保证现有 `ProcessSpec` 和通用售前能力稳定：

```text
customer_context
industry
department

business_goal
pain_point
role
current_process

available_data
existing_system

business_rule

security
approval
budget
time
data
risk

target_metric

integration
scope
deliverable
```

## 8.2 Dynamic Extension Categories

若客户出现核心字段之外、但对项目有价值的信息，允许动态增加：

```text
ext:<domain>:<key>
```

例如：

```text
ext:automotive:supplier_tier
ext:procurement:tender_method
ext:procurement:supplier_entry_policy
ext:security:data_classification
```

工程规则：

- `RequirementItem.category` 在实现层可以使用 `str + validator`；
- category 必须属于 Core Categories，或符合 `^ext:[a-z0-9_-]+:[a-z0-9_-]+$`；
- 动态字段仍必须遵守 provenance、source、status、confirmation、version 规则；
- 动态字段不得绕开 StrictModel，随意添加未知 top-level JSON 字段；
- 若动态字段后续需要进入 `ProcessSpec`，必须存在明确 Adapter 映射；否则保留为 Requirement Context，不强塞进现有 ProcessSpec。

## 8.3 与现有 ProcessSpec 的兼容

- `security / approval / budget / time / data / risk` 与现有 `BusinessConstraint.type` 对齐；
- `current_process` 使用 `ProcessObservation` 确定性生成 `ProcessNode`；
- `pain_point` 使用 `PainPointObservation` 确定性生成现有 `PainPoint`；
- 行业差异由可叠加 `RequirementSkill` 表达；
- 核心合同稳定，但业务信息允许按动态扩展类别增长。

---

# 9. `RequirementGap`

Gap 表示目前缺失或尚不能作为正式需求使用的信息。

```python
class RequirementGap(StrictModel):
    gap_id: str

    category: RequirementCategory

    gap_type: Literal[
        "missing",
        "ambiguous",
        "unconfirmed",
        "conflicted",
    ]

    description: str

    blocking: bool
    reason: str

    related_requirement_ids: list[str]
```

注意：

`missing` 不应伪装成一个 `RequirementItem`。

---

# 10. `RequirementConflict`

表示多来源或多轮沟通中出现的冲突。

```python
class RequirementConflict(StrictModel):
    conflict_id: str
    category: RequirementCategory

    requirement_ids: list[str]

    description: str

    severity: Literal[
        "low",
        "medium",
        "high",
    ]

    status: Literal[
        "open",
        "resolved",
    ]

    resolution_requirement_id: str | None
```

## 10.1 冲突基本规则

以下情况应产生 conflict：

- 同一 scalar requirement 出现不一致值；
- 已确认值被新来源明确否定；
- hard constraint 前后矛盾；
- 文档与最新客户明确口径冲突。

例如：

```text
会议纪要：预算 100 万
邮件：一期预算 50 万
最新客户消息：希望先按 80 万以内
```

系统不得静默覆盖。

---

# 11. 来源可信与冲突处理

默认来源优先级只作为**提示**，不得作为不可解释的绝对真理。

建议默认参考顺序：

```text
最新明确客户确认
    >
正式客户需求/招标文件
    >
客户邮件
    >
会议纪要
    >
CRM / 项目状态
    >
销售或售前 note
    >
AI inference
```

但：

- hard constraint 的变化必须重新确认；
- 已 confirmed Requirement 被修改时必须保留旧版本；
- 新值不能直接破坏历史记录；
- Source Ranking 不得自动绕过人工确认。

---

# 12. `RequirementState`

Requirement Engine 的核心状态。

```python
class RequirementState(StrictModel):
    schema_version: Literal["1.0"]

    project_id: str
    state_version: int

    source_ids: list[str]

    items: list[RequirementItem]
    gaps: list[RequirementGap]
    conflicts: list[RequirementConflict]

    selected_skill_id: str | None
```

要求：

- `requirement_id` 全项目唯一；
- `source_ids` 唯一；
- 所有 source ref 必须闭环；
- `supersedes_requirement_ids` 必须引用已有 item；
- supersede 不删除旧 item；
- 相同输入与相同 extractor 输出必须产生相同 State。

---

# 13. Extraction 层

## 13.1 目标

从 `CustomerSourceRecord` 中提取 Requirement Candidate。

## 13.2 LLM 负责

LLM 可以负责：

- 自然语言理解；
- 候选需求提取；
- category 分类；
- value 归一建议；
- source excerpt 定位；
- 候选冲突提示；
- 候选问题语言生成。

## 13.3 LLM 不负责

LLM 不得最终决定：

- Requirement 是否 confirmed；
- Requirement 是否 superseded；
- state_version；
- Baseline version；
- 是否允许进入正式方案；
- Requirement Diff；
- 下游 ReuseMode；
- Solution Fit。

## 13.4 Provider

复用现有：

- `LLMProvider`
- `OpenAICompatibleProvider`
- `FakeLLMProvider`

不得新增对特定模型 SDK 的硬依赖。

测试不得调用真实 API。

---

# 14. Deterministic State Reducer

Extractor 的候选输出进入 deterministic reducer。

Reducer 负责：

1. ID 稳定生成；
2. Requirement 去重；
3. 相同语义候选合并；
4. 新旧 Requirement 关系；
5. 状态迁移；
6. supersede；
7. conflict；
8. state_version；
9. source closure；
10. provenance preservation。

核心原则：

> **LLM 理解语言，Reducer 管理真相。**

---

# 15. RequirementChange

每轮分析必须给出清晰变化。

```python
class RequirementChange(StrictModel):
    requirement_id: str

    change_type: Literal[
        "added",
        "updated",
        "confirmed",
        "rejected",
        "conflicted",
        "resolved",
        "superseded",
    ]

    before_value: str | None
    after_value: str | None

    explanation: str
```

RequirementAnalysis 不允许只返回“新状态”，必须可解释本轮变化。

---

# 16. Gap Detector

Gap 来源三层：

1. **ProcessSpec Closure**
2. **通用售前必需信息**
3. **RequirementSkill 行业/场景要求**

例如：

- ProcessSpec 需要 `industry`，当前缺失；
- Procurement Skill 要求确认数据安全路径；
- 当前已有“采购系统”，但 API/集成可用性未知；
- 当前业务目标过于模糊。

Gap Detector 必须是可复现规则，不由 LLM 自由决定全部结果。

---

# 17. Requirement Skill

## 17.1 定位

Requirement Skill 是咨询方法的工程化表达。

它定义：

- 应关注哪些 category；
- 哪些条件属于场景相关 blocking requirement；
- 行业术语；
- 典型业务阶段；
- 典型风险；
- 建议问题模板；
- Completeness 展示权重；
- Context Evidence 推荐规则。

Skill **不能提供当前客户答案**。

## 17.2 两层 Skill 机制

v1 不在“generic procurement”和“automotive procurement”之间二选一，而采用叠加：

```text
procurement-core-v1
        +
automotive-procurement-v1
```

### `procurement-core-v1`

提供招采通用方法框架：

- 采购需求；
- 采购计划；
- 采购立项；
- 采购方案；
- 采购执行；
- 采购合同；
- 合同履约；
- 供应商管理；
- 统计分析。

通用痛点探针：

- 采购政策；
- 采购方案；
- 采购执行；
- 供应商管理；
- 合同；
- 效率；
- 合规；
- 人工审批；
- 数据安全。

### `automotive-procurement-v1`

作为行业 Overlay，只补充汽车制造场景可能值得确认的问题，例如：

- 多组织/多基地采购流程是否统一；
- 供应商准入与分层；
- 零部件/非生产/IT 等不同采购类别；
- 集团审批层级；
- 采购平台与 OA/SRM/ERP 等实际系统边界；
- 汽车行业特定合规、质量或数据边界。

Overlay 不得覆盖 Customer Truth。

## 17.3 禁止语义

> “历史客户有该问题” ≠ “当前客户也有该问题”。

Skill、内部 Know-how、外部 Benchmark 只能：

- 提醒；
- 触发追问；
- 形成风险候选；
- 帮助解释。

不能替客户回答。

---

# 18. ReadinessAssessment

```python
class ReadinessAssessment(StrictModel):
    stage: Literal[
        "DISCOVERY",
        "PRELIMINARY_READY",
        "CONFIRMED_READY",
    ]

    completeness_score: float

    blocking_gap_ids: list[str]
    non_blocking_gap_ids: list[str]
    open_conflict_ids: list[str]

    can_generate_preliminary_solution: bool
    can_generate_formal_solution: bool

    reasons: list[str]
```

---

# 19. Readiness Gate

Readiness 必须“保守但不过严”。

## 19.1 DISCOVERY

适用：

- 关键客户背景或业务目标仍不清楚；
- 当前流程/核心痛点尚不足以形成基本问题定义；
- 存在 unresolved core conflict；
- 场景明确需要的关键 Hard Constraint 仍未知；
- ProcessSpec 最低闭包无法满足。

系统继续澄清。

## 19.2 PRELIMINARY_READY

适用：

- 已具备形成初步方案/需求分析的最低信息；
- 允许存在 non-blocking gaps；
- 允许预算、工期、接口细节等尚未完全确认；
- assumptions 必须明确展示；
- 可以有 `confirmation_level=internal` 的内部售前判断；
- 不得伪装成客户已确认正式方案。

## 19.3 CONFIRMED_READY

必须同时满足：

1. 无 unresolved **核心 Requirement Conflict**；
2. 对当前场景明确必要的 security / data / approval 等 Hard Constraint 已确认或明确标记“不适用”；
3. Requirement Baseline 可以确定性转换成合法 `ProcessSpec`；
4. 已发生 **customer-level confirmation**；
5. 所有进入正式 ProcessSpec 的事实均为 `status=confirmed` 且 `confirmation_level=customer`；
6. 不存在会使正式方案明显失真的 blocking gap。

以下信息通常可以作为 non-blocking gap 保留，而不必默认阻止正式需求确认：

- 预算尚未完全精确；
- 具体实施工期未最终确认；
- Connector/API 细节尚待技术调研；
- 非核心组织信息；
- 未来二期范围。

但若某项预算/时间/接口信息在具体项目中被声明为强制投标条件或 Hard Constraint，则 Skill 可将其升级为 blocking。

**`completeness_score` 不是唯一 Gate。**

---

# 20. Completeness Score

Completeness 只用于：

- UI；
- 排序缺口；
- 展示需求成熟度。

它不得单独决定正式方案资格。

默认工程权重可由 Skill 配置。

建议 Generic v1：

```text
Business Goal                       15
Current Process + Pain              20
Data                                10
Systems                             10
Business Rules + Constraints        20
Target Metrics                      10
Scope + Deliverable                 10
Budget + Timeline                    5
--------------------------------------
Total                              100
```

权重是 DCForge 工程参数，不是甲方官方权重。

---

# 21. Next Best Question Planner

## 21.1 目标

不是“把所有缺失字段一次问完”，而是选择当前最有价值的 2～3 个问题。

## 21.2 优先级

```text
P0  Open Conflict
P1  Hard Constraint
P2  Solution Feasibility
P3  Business Goal
P4  Current Process / Pain
P5  Data / System
P6  Metrics
P7  Scope / Deliverable
P8  Budget / Timeline
```

## 21.3 `NextQuestion`

```python
class NextQuestion(StrictModel):
    question_id: str
    text: str

    target_category: RequirementCategory

    priority: Literal[
        "critical",
        "high",
        "medium",
        "low",
    ]

    blocking: bool
    reason: str

    related_gap_ids: list[str]
    related_conflict_ids: list[str]
```

规则：

- 每轮最多 3 个；
- 不重复询问已 confirmed 信息；
- 同一未回答问题不得原样无限重复；
- conflict question 优先；
- hard security/data/approval question 优先；
- 行业 Skill 只能建议问题，不能生成客户答案。

---

# 22. RequirementAnalysis

每轮统一返回：

```python
class RequirementAnalysis(StrictModel):
    project_id: str

    previous_state_version: int | None
    current_state: RequirementState

    changes: list[RequirementChange]

    readiness: ReadinessAssessment

    next_questions: list[NextQuestion]

    customer_confirmation_summary: str
```

A/前端的主要消费对象：

- `current_state`
- `readiness`
- `next_questions`
- `customer_confirmation_summary`

---

# 22.5 Source Ranking：只做提示，不自动决策

系统可以维护来源建议优先级，用于解释与提醒，例如：

```text
客户最新明确确认
>
正式招标/需求文件
>
客户正式邮件
>
会议纪要
>
CRM / 项目状态
>
销售/售前判断
>
AI 推断
```

但这只是**默认可信提示**，不是静默覆盖算法。

正式规则：

- 新来源不能仅因为 ranking 更高就自动覆盖旧 confirmed fact；
- 出现语义冲突必须进入 `RequirementConflict`；
- 时间新旧、来源正式程度、客户/内部确认共同参与解释；
- 最终 Requirement Truth 由明确确认动作决定；
- `ai_inferred` 永远不能因为 high confidence 获得高于客户来源的事实地位。

---

# 23. Customer / Internal Confirmation

确认不能由 LLM 自己宣布。

必须存在真实业务动作：

```text
确认
修改
拒绝
继续沟通
```

建议合同：

```python
class RequirementConfirmation(StrictModel):
    project_id: str
    state_version: int

    confirmation_level: Literal[
        "internal",
        "customer",
    ]

    confirmed_requirement_ids: list[str]
    rejected_requirement_ids: list[str]

    modifications: list[RequirementModification]

    confirmed_by: str
    note: str | None
```

语义：

### Internal Confirmation

售前/销售内部确认可用于：

- 消除内部判断歧义；
- 支撑 `PRELIMINARY_READY`；
- 形成初步需求分析；
- 决定下一轮客户问题。

但**不能生成正式 `RequirementBaseline`**。

### Customer Confirmation

客户确认用于：

- 正式确认 Requirement Truth；
- 解决关键冲突；
- 形成正式 Baseline；
- 进入 `CONFIRMED_READY`；
- 允许编译正式 `ProcessSpec`。

若人工修改：

- 创建 provenance=`human_modified` 的新 item；
- 默认 `confirmation_level=internal`；
- 原 item 进入 superseded；
- 若修改内容需要成为正式客户事实，必须再次获得 `confirmation_level=customer`；
- 不能原地静默改写。

---

# 24. RequirementBaseline

```python
class RequirementBaseline(StrictModel):
    baseline_id: str
    project_id: str

    baseline_version: int
    source_state_version: int

    confirmed_items: list[RequirementItem]

    non_blocking_gaps: list[RequirementGap]
    assumptions: list[str] = Field(default_factory=list)

    confirmation_level: Literal["customer"] = "customer"
    confirmed_by: str

    confirmation_summary: str
```

严格规则：

- `confirmed_items` 的 status 必须全部为 `confirmed`；
- `confirmed_items.confirmation_level` 必须全部为 `customer`；
- 不允许 `pending / conflicted / rejected / superseded`；
- source refs 必须闭环；
- baseline 不删除历史 State；
- 新 Baseline 必须有单调递增 version。

---

# 25. ProcessSpec Adapter

现有 `ProcessSpec` 保持不变。

Adapter：

```text
RequirementBaseline
        ↓
ProcessSpecAdapter
        ↓
ProcessSpec v1.0
```

映射：

| Requirement | ProcessSpec |
|---|---|
| industry | industry |
| department | department |
| business_goal | business_goal |
| role | roles |
| available_data | available_data |
| existing_system | existing_systems |
| current_process + ProcessObservation | as_is_nodes |
| pain_point + PainPointObservation | pain_points |
| security | BusinessConstraint.security |
| approval | BusinessConstraint.approval |
| budget | BusinessConstraint.budget |
| time | BusinessConstraint.time |
| data | BusinessConstraint.data |
| risk | BusinessConstraint.risk |
| target_metric | target_metrics |
| non-blocking gaps | missing_information |
| outstanding questions | clarification_questions |
| readiness | readiness_score |

## 25.1 Hard Rule

**只有 `status=confirmed` 且 `confirmation_level=customer` 的 Requirement 才能进入正式 ProcessSpec 的事实字段。**

禁止：

```text
ai_inferred / internal-only / pending
        ↓
ProcessSpec hard fact
```

---


## 25.2 Dynamic Category Rule

`ext:*` 动态需求默认保留在 Requirement Baseline/Context 中。

只有在存在明确、测试覆盖的 Adapter 映射时，才允许写入现有 `ProcessSpec`。

禁止：

```text
未知 ext 字段
→ 自由猜测
→ 塞入 business_goal / constraints / pain_points
```

---

# 26. RequirementDiff

客户反馈后的 Requirement 变化必须先在 Requirement 层被准确表达。

```python
class RequirementDiff(StrictModel):
    project_id: str

    previous_baseline_id: str
    current_baseline_id: str

    added_requirement_ids: list[str]
    removed_requirement_ids: list[str]
    changed_requirement_ids: list[str]

    changes: list[RequirementChange]
```

典型：

```text
approval threshold
500000 -> 800000
```

旧 Requirement：

```text
superseded
```

新 Requirement：

```text
confirmed
```

---

# 27. Requirement Diff Router 与 B-M8 最小侵入衔接

B-M8.7 保持 FROZEN，不为了 Requirement Intelligence 扩展其核心 Recompiler。

正式路由：

```text
Requirement Baseline v1
        ↓
ProcessSpec v1
        ↓
Solution v1

客户新反馈
        ↓
Requirement State v2
        ↓
Customer Confirmation
        ↓
Requirement Baseline v2
        ↓
Requirement Diff
        ↓
RequirementDiffRouter
        ├── No-op
        ├── Constraint-only Change
        └── Structural Requirement Change
```

## 27.1 No-op

如果 Baseline 的业务语义没有变化：

```text
不重新编译 Solution
不调用 Recompile
返回 no-op
```

## 27.2 Constraint-only Change

以下 Requirement Category：

```text
security
approval
budget
time
data
risk
```

如果能够确定性映射为现有 `BusinessConstraint`，则：

```text
RequirementDiff
→ new_constraints
→ 既有 B-M8.7 RecompileSolutionV2Request
→ Incremental Recompile
```

当前 B-M8.7 仍只接收既有：

```text
new_constraints: list[BusinessConstraint]
```

Requirement 层不得修改这一冻结合同的核心语义。

## 27.3 Structural Requirement Change

以下变化通常属于结构性变化：

```text
business_goal
pain_point
current_process
role
available_data（非 constraint 语义）
existing_system
scope
deliverable
integration
以及影响 ProcessSpec 结构的 ext:* 字段
```

处理方式：

```text
RequirementBaseline v2
→ 新 ProcessSpec
→ 现有 Solution Intelligence 完整 compile v2
```

**不得为了“所有变化都走增量”而强行修改 B-M8.7。**

## 27.4 Router Determinism

同一 `RequirementDiff` 必须稳定得到相同 routing decision：

```text
no_op
incremental_constraint_recompile
full_solution_recompile
```

并给出 routing explanation。

---

# 28. Persistence / Versioning

官方要求项目能够持续推进并保存主要状态。

本规格要求：

- RequirementState 可持久化；
- CustomerSourceRecord 可持久化或保留可解析引用；
- Baseline 可持久化；
- 历史版本不可因新版本被破坏；
- 重新进入项目后能够恢复最新 State/Baseline。

Engine 与存储解耦：

```python
class RequirementStateRepository(Protocol):
    load_state(project_id: str) -> RequirementState | None
    save_state(state: RequirementState) -> None

    list_baselines(project_id: str) -> list[RequirementBaseline]
    save_baseline(baseline: RequirementBaseline) -> None
```

**P0 正式实现采用 `FileRequirementRepository`（本地 JSON/JSONL 版本化持久化）作为默认实现**，同时保留 Repository Protocol，未来可无侵入替换为 SQLite/数据库 Adapter。

测试使用 InMemory/Fake Repository。

要求：

- State / Baseline / Diff 可以重新加载；
- 旧版本不可覆盖；
- 写入采用原子替换/临时文件策略，避免半写入状态；
- 不把大文件正文复制进每个版本，只保存 `document_ref/chunk refs`；
- Repository 不负责客户权限体系。

---

# 29. A ↔ Requirement Engine Service / API 设计

## 29.1 核心调用边界：内部 Python Service

正式业务真相以：

```text
RequirementIntelligenceService
```

为核心。

A 的飞书机器人/Interaction Adapter 调用内部 Python Service，不要求核心业务逻辑依赖 HTTP。

建议方法：

```python
analyze(
    context: CustomerContextPackage
) -> RequirementAnalysis

confirm(
    confirmation: RequirementConfirmation
) -> RequirementBaseline

compile_process_spec(
    baseline: RequirementBaseline
) -> ProcessSpec

diff(
    previous: RequirementBaseline,
    current: RequirementBaseline
) -> RequirementDiff

route_diff(
    diff: RequirementDiff
) -> RequirementDiffRoute
```

## 29.2 薄 HTTP API

为了前端、联调或未来飞书服务隔离，可以并行提供薄 API：

```text
POST /requirement/analyze
POST /requirement/confirm
POST /requirement/compile-process-spec
POST /requirement/diff
```

但：

- HTTP 不是 Requirement Truth 的唯一实现；
- API 层只做合同校验、错误映射和 Service 调用；
- 不在 API 层重新实现 gap/conflict/readiness；
- 不修改现有 v1 solution API 语义。

---

# 30. Binary Document Boundary

会议纪要、PDF、Word、PPT、邮件附件属于重要输入，但 v1 Requirement Engine 的核心职责是**理解已经转化为文本的客户材料**。

以下能力可由 A/File Adapter/独立 parser 提供：

```text
PDF / DOCX / PPTX / Feishu message
        ↓
Parser / File Adapter
        ↓
document_ref + CustomerSourceChunk[]
        ↓
CustomerSourceRecord
```

P0 不要求 Requirement Engine 自己实现：

- OCR；
- Office 全格式解析器；
- 企业邮箱 Connector；
- CRM Connector；
- 飞书开放平台 Connector。

但合同必须兼容这些来源。

---

# 31. Human-in-the-loop

必须明确三类 Human Gate：

## 31.1 Conflict Resolution

同一需求存在关键冲突时：

```text
AI 不自动决定真值
↓
用户确认
```

## 31.2 Formal Requirement Confirmation

进入 `CONFIRMED_READY` 前必须发生显式确认。

## 31.3 Requirement Change Confirmation

已确认 Requirement 被客户新反馈改变时：

- 新值先作为 candidate；
- hard requirement 改动必须重新确认；
- 然后才形成新 Baseline。

---

# 31.5 Internal / External Context Evidence Policy

内部方案资料与外部公开案例进入 Requirement Intelligence 时必须保留来源身份。

正式类别：

```text
internal_knowhow
internal_solution
external_policy
external_benchmark
public_business_data
```

使用原则：

```text
客户资料
→ 可以形成 Requirement Candidate

内部 Know-how
→ 帮助判断“该问什么 / 有什么能力边界”

外部 Benchmark / Policy
→ 帮助发现“该确认什么 / 有什么风险”

但内部/外部 Context Evidence
→ 不能替客户回答
```

Context Evidence 可以在后续 Solution Intelligence 中继续作为辅助 Evidence，但其身份不能被改写。

---

# 32. Automotive Procurement Golden Case

正式 Golden：

**汽车制造 × 智能招采 / 采购合规售前**

Golden 客户必须明确标记：

```text
synthetic / de-identified test customer
```

不得把公开案例中的真实企业包装成当前客户。

## 32.0 Golden Knowledge / Evidence Set

### 神州数码 / 甲方材料

1. 甲方提供《智能招采一体化平台》PPT；
2. 神州问学智能招采解决方案/案例资料；
3. 神州数码官网公开智能招采案例。

用途：

- Internal Know-how；
- Internal Solution Evidence；
- Procurement Skill；
- SolutionAsset / Evidence 边界校验。

### 汽车行业 External Benchmark

4. 理想汽车 × SAP Ariba 采购数字化案例；
5. Honda × Oracle Procurement 案例；
6. Toyota × SAP Ariba IT 采购案例。

用途：

- 汽车行业问题探针；
- 外部标杆；
- 需求追问建议。

### Public Business Data

7. 东风汽车采购招投标平台公开业务数据。

用途：

- 理解真实汽车采购流程、公告和业务语境；
- 构造脱敏/synthetic Golden 输入。

### AI 招采 External Practice

8. 深圳交易集团 / 中国政府采购网公开 AI 辅助评审案例。

用途：

- 外部 AI 招采能力验证背景；
- 风险/评审问题探针。

严格禁止：

- 将上述 External Benchmark 自动写成当前客户 Requirement；
- 将外部案例效果写成当前客户 ValueClaim；
- 声称 synthetic Golden 客户就是上述真实企业。


---

## 32.1 Initial Sources

项目进入时已经拥有：

```text
Customer Profile
- 某大型汽车制造集团
- 采购中心

Meeting Minutes
- 采购方案和招标文件主要依赖人工
- 合规压力较大

Historical Email
- 已部署 OA 与采购系统

Sales Note
- 客户希望 AI 提效
```

Requirement Engine 首轮分析：

```text
industry          -> ai_extracted / pending
department        -> ai_extracted / pending
pain_point        -> ai_extracted / pending
existing_system   -> ai_extracted / pending
sales_note intent -> sales_judgment / pending

missing:
- private/public security
- approval rule
- data availability
- target metrics
```

说明：

- 会议纪要、历史邮件和销售备注产生 Candidate，不因“资料存在”自动 customer-confirmed；
- 正式需求确认阶段统一由客户确认摘要完成 customer-level confirmation；
- Sales Note 永远不能独立升级为 Customer Truth。

---

## 32.2 Follow-up Turn 1

客户：

> 所有采购资料不能离开企业私域。

输出：

```text
security = 数据不得出企业私域
provenance = customer_raw / ai_extracted
status = pending
confirmation_level = none
```

若该轮由客户在飞书中明确回复确认该事实，可记录 customer-level confirmation；否则统一进入最终 Requirement Confirmation Summary。

---

## 32.3 Follow-up Turn 2

客户：

> 超过 50 万元的项目必须人工审批。

输出：

```text
approval threshold = 500000
status = pending
source = latest customer conversation
```

在正式 Confirmation 后：

```text
status = confirmed
confirmation_level = customer
```

---

## 32.4 Follow-up Turn 3

客户确认数据与指标：

```text
历史采购方案
历史招标文件
企业采购制度
审查规则

processing_time
manual_steps
risk_findings
```

此时系统最多进入：

```text
PRELIMINARY_READY
```

并生成 Requirement Confirmation Summary。

只有客户明确确认后：

```text
customer confirmation
        ↓
CONFIRMED_READY
        ↓
RequirementBaseline v1
        ↓
ProcessSpec
        ↓
B-M8
```

---

## 32.5 Feedback Turn

客户：

> 审批规则调整，现在超过 80 万元才必须人工审批。

要求：

客户新说法先形成：

```text
old 500000 -> still historical confirmed
new 800000 -> pending candidate
```

客户再次确认 change 后：

```text
old 500000 -> superseded
new 800000 -> confirmed / customer
```

形成：

```text
RequirementBaseline v2
RequirementDiff
```

下游 B-M8.7 应只影响 approval scope。

---

# 33. Conflict Golden

必须增加一个独立冲突 Case。

例如：

```text
meeting_minutes:
预算约 100 万

customer_email:
一期控制在 50 万

latest_conversation:
希望先按 80 万以内
```

期望：

- 不静默覆盖；
- 建立 RequirementConflict；
- readiness 阻止正式确认；
- Next Best Question 请求确认；
- 人工确认后旧值 superseded；
- 来源完整保留。

---

# 34. Requirement Truth 安全原则

整个模块必须满足三层“不伪造”：

```text
Requirement 层：
不伪造客户事实

Solution 层：
不伪造企业能力

Value 层：
不伪造客户收益
```

正式 P0：

> **Unsupported Confirmed Fact = 0**

任何 `confirmed` Requirement 必须满足：

- 有客户/项目来源；
- 或有明确 human modification；
- 且存在 confirmation 行为；
- source closure 成立。

---

# 35. P0 业务验收指标

| 指标 | P0 |
|---|---:|
| Requirement Source Closure | 100% |
| Requirement Provenance Coverage | 100% |
| Unsupported Confirmed Fact | 0 |
| State Reducer Determinism | 100% |
| Question Planner Determinism（固定 State） | 100% |
| Golden Conflict Detection | 100% |
| Blocking Gap Gate Violation | 0 |
| Confirmed Baseline Validity | 100% |
| ProcessSpec Closure | 100% |
| B-M8 Existing Regression | 0 failed |

说明：

真实 LLM 文本生成本身不声称跨 Provider 完全 deterministic。

Determinism P0 适用于：

- 固定 extractor 输出；
- Reducer；
- Gap；
- Conflict；
- Readiness；
- Question Planning；
- Adapter；
- Diff。

---

# 36. 测试策略

## 36.1 Contract Tests

验证：

- extra field 拒绝；
- invalid enum 拒绝；
- invalid confidence；
- invalid source ref；
- invalid supersede ref；
- baseline 中非 confirmed item 拒绝；
- project closure；
- source closure。

## 36.2 Reducer Tests

验证：

- 新 Requirement；
- 重复 Requirement；
- source merge；
- status transition；
- confirmed 更新；
- supersede；
- deterministic ordering；
- no silent overwrite。

## 36.3 Conflict Tests

验证：

- same field inconsistent values；
- hard constraint change；
- source conflict；
- resolved conflict；
- historical source preservation。

## 36.4 Gap / Readiness Tests

验证：

- DISCOVERY；
- PRELIMINARY_READY；
- CONFIRMED_READY；
- 95% completeness 但 blocking security gap；
- open conflict prevents formal；
- confirmation required。

## 36.5 Question Planner Tests

验证：

- conflict first；
- hard constraint first；
- max 3 questions；
- no duplicate confirmed questions；
- procurement skill only creates questions, not facts。

## 36.6 Golden E2E

```text
Multi-source context
→ RequirementAnalysis
→ Next Questions
→ Customer Answers
→ Confirmation
→ RequirementBaseline
→ ProcessSpec
→ Existing B-M8 compile
```

## 36.7 Feedback E2E

```text
500000
→ Baseline v1
→ Solution v1
→ 800000
→ Baseline v2
→ RequirementDiff
→ B-M8.7 Recompile
→ precise solution diff
```

## 36.8 Full Regression

每个 Milestone 完成后执行：

```text
tests/process/*
tests/test_contracts.py
tests/solution/*
full pytest
```

既有 B-M8 测试不得退化。

---

# 37. Milestones

---

## R-M1 Requirement Foundation

### 范围

- Contracts；
- Source model；
- RequirementItem；
- RequirementState；
- RequirementChange；
- deterministic reducer；
- source/provenance closure；
- RequirementRepository interface；
- `FileRequirementRepository`；
- RequirementState version persistence。

### DoD

- 多源 customer context 能形成稳定 state；
- AI inference 不会自动 confirmed；
- source closure 100%；
- reducer deterministic；
- RequirementState version persistence is immutable；
- 既有回归全绿。

---

## R-M2 Requirement Understanding

### 范围

- LLM extractor；
- normalized candidate；
- existing LLMProvider reuse；
- Fake Provider；
- invalid JSON handling；
- extraction evidence refs。

### DoD

- meeting / email / conversation / requirement document 至少四类来源可提取；
- tests 不访问真实网络；
- every extracted item has source ref；
- unsupported confirmed fact=0。

---

## R-M3 Gap / Conflict / Readiness

### 范围

- Gap Detector；
- Conflict Detector；
- Skill；
- Readiness Evaluator；
- completeness。

### DoD

- Golden conflict 正确识别；
- blocking gap 不可越过；
- score 不成为唯一 Gate；
- deterministic。

---

## R-M4 Question / Confirmation / Version

### 范围

- Next Best Question；
- max 3；
- no duplicate；
- RequirementConfirmation；
- RequirementBaseline；
- RequirementBaseline persistence；
- confirmation history；
- baseline/version history extension。

### DoD

- 多轮沟通能持续推进；
- 客户确认是真实业务动作；
- baseline 只包含 confirmed facts；
- old versions preserved。

---

## R-M5 ProcessSpec / Recompile Handoff

### 范围

- ProcessSpec Adapter；
- RequirementDiff；
- RequirementDiffRouter；
- no-op / constraint incremental / structural full compile routing；
- Requirement -> B-M8 compile；
- constraint-only change -> B-M8.7 recompile；
- structural change -> existing compile-solution-v2；
- API/service integration。

### DoD

- automotive procurement Golden E2E；
- Baseline -> ProcessSpec closure 100%；
- 500000 -> 800000 能形成正确 RequirementDiff，并路由到 constraint incremental recompile；
- business_goal/current_process 等结构变化稳定路由到 full solution recompile；
- 不修改 B-M8.7 核心裁决；
- full regression 0 failed。

---

# 38. 推荐目录结构

建议：

```text
backend/app/
├── contracts/
│   ├── process.py
│   └── requirement_intelligence.py
│
├── process/
│   ├── requirement_agent.py
│   ├── requirement_extractor.py
│   ├── requirement_reducer.py
│   ├── conflict_detector.py
│   ├── gap_detector.py
│   ├── readiness.py
│   ├── question_planner.py
│   ├── requirement_repository.py
│   ├── file_requirement_repository.py
│   ├── requirement_diff_router.py
│   ├── process_spec_adapter.py
│   ├── service.py
│   └── api.py
│
data/
└── requirement_skills/
    ├── procurement_core_v1.json
    └── automotive_procurement_v1.json
│
tests/
└── process/
    ├── test_requirement_contracts.py
    ├── test_requirement_reducer.py
    ├── test_requirement_conflicts.py
    ├── test_requirement_readiness.py
    ├── test_question_planner.py
    ├── test_requirement_confirmation.py
    ├── test_process_spec_adapter.py
    └── test_requirement_golden.py
```

现有 `backend/app/process/service.py` 可作为 service 入口，不应把 Requirement Engine 塞进 `backend/app/solution/`。

---

# 39. 明确非范围

Requirement Intelligence v1.0 P0 不做：

- 飞书开放平台底层接入；
- CRM 生产 Connector；
- 邮箱生产 Connector；
- OCR 引擎；
- 通用 Office 文档解析平台；
- 企业级全文搜索平台；
- 大规模自动互联网抓取；
- 自动将外部 benchmark 写成客户事实；
- 自动将内部历史案例写成客户事实；
- 复杂 Multi-Agent 自主循环；
- 自动替客户确认；
- 自动修改已冻结 Solution Fit/Reuse 规则；
- Runtime；
- PPT/HTML 成果生成。

这些可以由其他模块或后续版本承担。

---

# 40. 禁止事项

1. 不允许“对话轮数 >= N”直接视为需求完成；
2. 不允许“completeness > threshold”单独进入正式方案；
3. 不允许 LLM confidence 代替客户确认；
4. 不允许 AI inference 自动 confirmed；
5. 不允许新来源静默覆盖旧 confirmed fact；
6. 不允许删除 superseded 历史；
7. 不允许无 source ref 的 confirmed fact；
8. 不允许内部 SolutionAsset 自动变成客户需求；
9. 不允许外部 benchmark 自动变成客户需求；
10. 不允许 Requirement Agent 自行生成最终 Solution；
11. 不允许重新实现 Fit / Reuse；
12. 不允许 Requirement 层直接修改 DemoBlueprint；
13. 不允许测试依赖真实 API key；
14. 不允许为了新模块破坏 B-M8 259-test 基线；
15. 不允许将 Skill 中的问题模板当成客户事实。

---

# 41. Definition of Done

Requirement Intelligence Engine v1.0 完成必须同时满足：

## Contracts

- [ ] 所有公共合同 StrictModel；
- [ ] source/project/reference closure；
- [ ] invalid state rejected。

## Multi-source Context

- [ ] conversation；
- [ ] meeting minutes；
- [ ] email；
- [ ] requirement/bid material；
- [ ] project status / sales note；
- [ ] inline content + document ref/chunk；
- [ ] contacts / organization context；
- [ ] 多源可以共同更新一个 RequirementState。

## Truth

- [ ] provenance 100%；
- [ ] source closure 100%；
- [ ] unsupported confirmed fact=0；
- [ ] inference never silently confirmed；
- [ ] sales/presales judgment never silently becomes customer truth；
- [ ] dynamic ext categories preserve source/status/version。

## Intelligence

- [ ] extraction；
- [ ] normalization；
- [ ] gap；
- [ ] conflict；
- [ ] readiness；
- [ ] next best question。

## Human

- [ ] conflict confirmation；
- [ ] internal vs customer confirmation clearly separated；
- [ ] formal requirement confirmation requires customer-level action；
- [ ] change confirmation requires customer confirmation。

## Version

- [ ] State version；
- [ ] Baseline version；
- [ ] supersede history；
- [ ] RequirementDiff。

## Downstream

- [ ] confirmed Baseline -> legal ProcessSpec；
- [ ] ProcessSpec -> B-M8 existing compile；
- [ ] constraint-only Requirement change -> B-M8.7 handoff；
- [ ] structural Requirement change -> existing full compile；
- [ ] Diff Router deterministic。

## Golden

- [ ] Automotive Procurement multi-source case；
- [ ] conflict case；
- [ ] 500000 -> 800000 feedback case。

## Regression

- [ ] Requirement tests pass；
- [ ] Process tests pass；
- [ ] Solution tests pass；
- [ ] full pytest 0 failed；
- [ ] B-M8 behavior unchanged。

---

# 42. 对外表达

正式答辩中不建议只说：

> “我们做了一个需求分析 Agent。”

建议表达为：

> **DCForge 在方案生成前增加了一层 Customer Context & Requirement Intelligence：它能够融合客户档案、会议纪要、邮件、历史沟通、招标/需求材料、项目状态和实时对话，持续维护一份可追溯、可确认、可版本化的客户 Requirement Truth。系统会主动识别缺失信息与前后冲突，通过飞书交互发起 Next Best Question；只有经过确认的 Requirement Baseline 才会进入 Solution Intelligence，从源头避免 AI 把推测当事实、把不完整需求直接编成正式方案。**

整个 DCForge Intelligence Core 可以概括为：

> **第一次编译：把零散客户上下文编译成客户需求真相。**
> **第二次编译：把需求真相与企业知识资产编译成可执行解决方案。**

---

# 43. 冻结产品审计决策（15/15 已收敛）

以下 15 项产品/架构问题已经人工确认，不再作为开放问题。

| # | 审计项 | RC 决策 |
|---|---|---|
| 1 | Source/Requirement 字段是否锁死 | 核心字段稳定 + `ext:<domain>:<key>` 动态扩展 |
| 2 | generic parameters 是否足够支撑 Process/Pain | 不足；增加 `ProcessObservation` / `PainPointObservation` |
| 3 | 联系人/组织结构 | P0 增加轻量合同，不建设 CRM |
| 4 | Readiness blocking 是否过严 | 放松；仅核心冲突、场景必要 Hard Constraint、正式确认等阻断 |
| 5 | Procurement Skill | `procurement-core-v1 + automotive-procurement-v1 overlay` |
| 6 | Source ranking | 仅提示/解释，不自动覆盖 |
| 7 | Baseline non-blocking gap | 允许，并显式携带 assumptions |
| 8 | P0 持久化 | 需要；默认 `FileRequirementRepository` |
| 9 | A ↔ Requirement Engine | 内部 Python Service 为核心，可选薄 HTTP API |
| 10 | R-M5 接 B-M8.7 | `RequirementDiffRouter`；constraint 增量，结构变化 full compile |
| 11 | 大文件输入 | `document_ref + chunks`，不强制全文 inline |
| 12 | 外部情报 | 允许形成独立 `ContextEvidence`，不得成为 Customer Truth |
| 13 | 销售初步判断 | 增加 `sales_judgment / presales_judgment` provenance |
| 14 | 客户 vs 内部确认 | 必须区分；正式 Baseline 需要 customer-level confirmation |
| 15 | Automotive Golden 来源 | 使用神州数码/甲方材料 + 已筛选公开汽车/AI 招采案例 |

因此本冻结规格不存在重大产品决策悬空项。

冻结前完成的最终验证型审计：

1. Contract field closure；
2. Dynamic category validator；
3. typed Process/Pain mapping；
4. customer-level confirmation closure；
5. Readiness Golden；
6. Source / ContextEvidence truth boundary；
7. File Repository version semantics；
8. Diff Router 对 B-M8 冻结边界；
9. Automotive Golden provenance；
10. full regression compatibility。

这些验证均不改变产品核心逻辑；后续实现若发现与冻结语义冲突，必须形成新版本 Spec 后再调整。

---

# 44. 当前冻结关系

```text
B-M8 Solution Intelligence Engine v1.0
状态：FROZEN
基线：
b6b5855487a7fc8b4dc9303c4f4ecdba4f3068ca

Requirement Intelligence Engine v1.0
状态：FROZEN / 正式冻结版
15 项产品与架构审计决策已收敛
R-M1 Requirement Foundation = CLOSED
后续 R-M2 ~ R-M5 不得破坏 B-M8 冻结行为或本文冻结语义
```

后续建议流程：

```text
Requirement Intelligence Engine v1.0 FROZEN
    ↓
R-M1 Requirement Foundation（CLOSED）
    ↓
R-M2
    ↓
R-M3
    ↓
R-M4
    ↓
R-M5
    ↓
Overall Acceptance
```
