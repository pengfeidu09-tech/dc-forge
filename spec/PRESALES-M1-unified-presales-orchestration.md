# PRESALES-M1 统一售前编排与模板串联

## 目标

把现有飞书客户沟通、Requirement Intelligence、企业知识与 MCP、方案生成、内部评审、客户发布和反馈迭代串成一条可操作、可追踪的售前流程。

本规格对应《分析.pptx》中的以下模块：

- 当前客户与项目
- 企业内部知识资产
- 外部动态信息
- 用户需求与进展状态管理
- 方案生成系统
- 飞书客户与内部工作台
- 内部 Skill
- 成果展示

## 约束

- 不修改公共 contracts、`backend/app/process/`、`backend/app/runtime/`、`data/fixtures/` 和 Vue 前端。
- 复用现有 Requirement Intelligence、Customer Engagement、Enterprise Knowledge、MCP 和 Solution Intelligence，不复制核心算法。
- 文件存储仍按单进程写入运行，多实例上线需要迁移到数据库。
- 模拟验收数据不得描述为真实业务成果。
- 外部情报必须保留来源 URL、发生时间和录入人，不自动把外部信息当作客户确认需求。

## 售前阶段

统一工作流包含八个阶段：

1. `opportunity`：客户机会与项目建立
2. `requirement_analysis`：客户资料进入 Requirement Intelligence
3. `intelligence_research`：外部政策、标准、市场或竞品资料归档
4. `knowledge_retrieval`：检索企业知识、案例和历史资料
5. `solution_generation`：基于正式 Baseline 生成三套方案
6. `internal_review`：企业员工批准或驳回方案与成果稿
7. `customer_output`：发布客户安全方案和可编辑 HTML 成果
8. `feedback_iteration`：客户反馈回流并形成新需求版本

每个项目返回全部阶段及 `completed`、`current`、`pending` 状态。阶段状态必须由持久化事实推导，不能由前端自行填写。

## 项目资料输入

内部员工可以创建售前项目并录入以下资料：

- 客户需求文档
- 会议纪要
- 邮件或历史沟通
- 企业内部资料
- 外部动态情报

客户需求文档、会议纪要和客户邮件进入 Requirement Intelligence，形成新的 RequirementState 版本。企业内部资料和外部情报只能作为研究证据，不能直接成为客户确认需求。

每条资料记录来源类型、标题、正文、来源 URL、发生时间、录入人和录入时间。

## 知识与情报研究

- 项目关联一个企业知识参考项目。
- 知识检索调用现有 `EnterpriseKnowledgeService.search_knowledge`。
- 研究快照同时包含企业知识结果和项目已录入的外部情报。
- 每个结果保留来源 ID、标题、摘要、来源路径或 URL。
- 研究快照版本化，不覆盖历史版本。

## Skill 模板串联

读取知识包 `07_Skill技能库` 中的七个 Skill 定义，并展示版本与说明。

本里程碑把四个核心模板连接到确定性处理步骤：

| Skill | 对应处理步骤 |
|---|---|
| `requirement_analysis` | Requirement Intelligence 分析与 Baseline |
| `case_matching` | 企业知识和案例检索 |
| `solution_recommendation` | Solution Intelligence 三套方案 |
| `document_generation` | 客户成果稿生成与 HTML 展示 |

`meeting_intelligence`、`supplier_analysis`、`project_reuse` 先作为可检索模板展示。不得声称这些模板已经被 Agent 自动执行。

## 方案草稿与内部评审

- 只有正式 Baseline 存在且已生成研究快照时，才能生成方案草稿。
- 方案草稿保存 Baseline 版本、研究版本、三套方案和客户成果稿。
- 成果稿是结构化内容，包含：客户现状、问题分析、需求理解、推荐方案、价值验证假设、实施路线、风险边界、案例参考和来源引用。
- 内部员工可以编辑成果稿。编辑后修订号递增，之前的批准自动失效。
- 评审记录包含批准或驳回、评审人、意见、草稿版本、成果稿修订号和时间。
- 未批准的草稿不得发布给客户。

## 客户发布与成果展示

- 发布调用现有 Customer Engagement 发布边界。
- 发布后生成客户安全的成果版本。
- 客户需求与方案中心展示正式方案和成果入口。
- 成果 HTML 支持浏览器直接编辑文本并下载 HTML 文件，但系统保存内容仍需走内部修订接口。
- 成果必须明确价值指标是待验证假设，不是已实现成果。
- 客户成果不得暴露内部评审分数、资产 ID、工具名、内部项目路径或权限配置。

## 统一内部工作台

新增 `/presales/workbench`，展示：

- 客户项目列表
- 售前阶段进度
- 飞书沟通时间线
- RequirementState、缺口和 Baseline
- 项目资料与外部情报
- 企业知识研究快照及引用
- Skill 模板链路
- 方案草稿和内部评审
- 客户发布版本与成果入口

飞书内部员工的“客户工作台”入口改为该统一工作台。旧 `/customer-engagement/workbench` 保留为兼容别名。

## API

内部接口继续使用 `X-DCForge-Internal-Token`：

- `GET /presales/projects`
- `POST /presales/projects`
- `GET /presales/projects/{project_id}`
- `POST /presales/projects/{project_id}/sources`
- `POST /presales/projects/{project_id}/research`
- `POST /presales/projects/{project_id}/drafts`
- `POST /presales/projects/{project_id}/drafts/{draft_version}/deliverable`
- `POST /presales/projects/{project_id}/reviews`
- `POST /presales/projects/{project_id}/publish`

客户接口继续使用 URL Fragment 中的令牌，并通过请求头传递：

- `GET /customer/engagement/{access_id}/deliverable`

## 验收标准

1. 已存在的飞书项目自动出现在统一售前工作台，不需要重复建档。
2. 客户资料进入需求分析；内部资料和外部情报不会污染客户需求事实。
3. 研究快照同时返回企业知识结果和带 URL 的外部情报。
4. 七个 Skill 模板可见，四个核心模板显示其实际连接步骤。
5. 没有 Baseline、没有研究快照或没有内部批准时，方案发布会被拒绝。
6. 编辑成果稿后，旧批准失效，必须重新评审。
7. 通过评审后可以发布客户方案，并生成不含内部字段的 HTML 成果。
8. 客户反馈仍能进入 Requirement Intelligence，并在工作流中显示为反馈迭代。
9. 新增测试通过，`tests/test_contracts.py` 通过。
