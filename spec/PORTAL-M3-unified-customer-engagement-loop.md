# PORTAL-M3 飞书客户需求与方案闭环

## 1. 背景

当前飞书机器人、Requirement Intelligence 状态池、企业知识门户和方案编译器已经分别存在，但真实客户会话仍只保存在机器人进程内存中。企业员工无法在同一入口查看客户原话与结构化需求，客户也没有可持续访问的需求确认和方案页面。

本里程碑把现有能力连接为一条可追溯闭环：

```text
飞书客户消息
  -> 持久化会话
  -> RequirementState
  -> 内部客户工作台
  -> 客户确认
  -> RequirementBaseline
  -> SolutionBundle
  -> 内部发布
  -> 客户需求与方案中心
```

## 2. 范围

### 2.1 飞书入口

- 每条客户消息和机器人回复必须持久化，机器人重启后仍可读取历史上下文。
- 客户发送“查看需求”“查看方案”“项目进展”或 `/项目` 时，机器人返回该客户项目的专属访问链接。
- 已授权内部员工发送“客户工作台”或 `/客户工作台` 时，机器人返回内部工作台入口。
- 飞书客户项目继续使用现有 `feishu:{tenant_key}:{chat_id}` 标识，RequirementState、会话与发布物必须使用同一个 project_id。

### 2.2 内部客户工作台

内部工作台必须提供：

- 客户项目列表、最后沟通时间与消息数；
- 完整客户/机器人会话时间线；
- 当前 RequirementState、历史 state/baseline 版本；
- 需求项、证据、缺口、冲突和确认状态；
- 当前客户访问链接；
- 正式方案发布动作与发布历史。

内部数据不得通过客户访问链接暴露。

### 2.3 客户需求与方案中心

客户页面通过公开 access_id 和高熵访问令牌进入。访问令牌只放在 URL Fragment 中，并由页面通过请求头提交；不得进入 HTTP 路径、查询参数或访问日志。页面展示：

- 当前需求理解的客户友好摘要；
- 客户可确认或否定的需求项；
- 补充/纠正需求的反馈入口；
- 当前是否已形成客户确认需求；
- 经内部发布的解决方案、能力模块、目标流程、实施步骤、前置数据、系统集成、假设和风险。

客户页面禁止展示：

- Requirement ID、source ID、状态池路径；
- confidence、readiness score、内部成熟度枚举；
- MCP、技能 ID、模型提示词、内部备注；
- 资产 ID、复用率、review score 等内部方案评价。

## 3. 真相与发布规则

1. 飞书消息是客户原始证据，不等同于已确认需求。
2. 客户页面确认必须调用现有 `RequirementConfirmation`，且 confirmation level 固定为 `customer`。
3. 只有 `CONFIRMED_READY` 产生的 `RequirementBaseline` 可以进入正式方案编译。
4. 发布动作必须显式发生，不允许机器人自动发布方案。
5. 客户只能看到最新已发布快照；新需求进入状态池后，不得静默改写已发布方案。
6. 方案中的指标和价值描述只能表述为待验证目标，不得描述为真实业务成果。

## 4. 持久化

会话与发布数据保存在 Git 工作树之外。默认根目录由 `REQUIREMENT_REPOSITORY_ROOT` 派生，也可通过 `CUSTOMER_ENGAGEMENT_ROOT` 指定。

每个项目保存：

- 项目元数据；
- 幂等的会话消息记录；
- 客户访问令牌；
- 不可变发布版本。

访问令牌不得写入日志或内部需求状态。

## 5. HTTP 边界

内部入口：

- `GET /customer-engagement/workbench`
- `GET /customer-engagement/projects`
- `GET /customer-engagement/projects/{project_id}`
- `POST /customer-engagement/projects/{project_id}/publish`

客户入口：

- `GET /customer/engagement/{access_id}`
- `GET /customer/engagement/{access_id}/data`
- `POST /customer/engagement/{access_id}/confirm`
- `POST /customer/engagement/{access_id}/feedback`

数据、确认和反馈接口通过 `X-DCForge-Customer-Token` 接收高熵令牌。

内部 API 通过 `CUSTOMER_ENGAGEMENT_INTERNAL_TOKEN` 和 `X-DCForge-Internal-Token` 保护；未配置时仅允许回环地址和测试客户端访问，远程访问必须拒绝。

## 6. 错误与并发

- 重复飞书 event/message 不得产生重复会话记录。
- 客户提交过期状态确认返回冲突，不覆盖最新状态。
- 没有正式 Baseline 时发布必须失败。
- 无效或未知客户令牌返回 404，不泄露项目是否存在。
- LLM 分析失败时保留客户原始消息和失败回复，不制造 Requirement Truth。

## 7. 验收标准

- **AC-01** 飞书往返消息在进程重启后仍可被工作台读取。
- **AC-02** 工作台可聚合真实飞书会话与同 project_id 的 RequirementState。
- **AC-03** 客户链接不暴露内部字段。
- **AC-04** 客户确认使用现有冻结确认引擎并产生连续 state 版本。
- **AC-05** 只有正式 Baseline 可生成并发布方案。
- **AC-06** 发布快照与 baseline version 绑定且版本不可变。
- **AC-07** 客户反馈重新进入 Requirement Intelligence，而不是直接改方案。
- **AC-08** 飞书可返回客户中心和内部工作台入口。
- **AC-09** 新增测试通过，`tests/test_contracts.py` 通过。
- **AC-10** 所有演示或预期指标明确为待验证，不声称真实业务成果。

## 8. 本里程碑限制

依据当前 `AGENTS.md`，不修改 `frontend/`、`backend/app/contracts/`、`backend/app/process/` 或 `backend/app/runtime/`。本次通过 `backend/app/solution/` 提供独立可用的页面和 API；后续经团队确认后，可把同一 API 接入现有 Vue 门户导航。
