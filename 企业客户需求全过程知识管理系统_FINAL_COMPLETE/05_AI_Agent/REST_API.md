# 企业客户全过程知识服务 REST API 约定

## 定位与边界

本文定义演示资料包中的接口语义，帮助前端、Agent和集成方理解资源关系，不代表仓库已经实现或部署这些接口。所有请求都必须携带调用者身份与项目上下文，服务端在检索前执行权限过滤。任何返回的模拟指标都必须保留 `data_classification`。

## 通用约定

基础路径示例为 `/api/v1`。请求使用JSON，时间使用ISO 8601和 `Asia/Shanghai`，分页参数为 `page_token` 与 `page_size`。响应包含 `request_id`、`data` 和 `audit`。错误至少区分参数错误、无权限、对象不存在、版本冲突和证据不足。更新需求基线等操作需要幂等键与乐观锁版本。

## 资源接口

### 客户与项目

`GET /customers/{customer_id}` 返回客户画像与授权字段；`GET /projects/{project_id}` 返回项目主索引、阶段和对象链接。列表查询不得默认返回价格、合同或个人联系方式。

### 需求与版本

`GET /requirements/{requirement_id}` 返回需求及版本历史。`POST /requirements/{requirement_id}/versions` 创建新版本，必须提交变更原因、影响范围和来源证据。`POST /requirements/{requirement_id}/baselines/{version_id}/confirm` 需要业务审批凭据，不能原地覆盖旧基线。

### 会议、沟通与文档

`GET /meetings/{meeting_id}` 返回议题、决策、行动项和关联对象。`GET /communications/{source_id}` 返回授权范围内的邮件或企微记录。`POST /documents/search` 接收查询、项目、过滤条件和最大结果数，返回来源路径、段落、版本、权限标签与相关度说明。

### 决策与追溯

`GET /decisions/{decision_id}/history` 返回提出、讨论、批准、变更和落实记录。`GET /trace/{object_id}` 沿稳定ID返回需求、方案、合同、订单、VIN、异常或复盘关联，但仅展示调用者有权限访问的节点。

## 搜索请求与响应

请求包含 `query`、`project_id`、`source_types`、`related_ids` 和 `as_of`。响应中的每个结果包含 `source_id`、`source_path`、`content`、`version`、`updated_at` 和 `permission_decision`。没有可靠结果时返回空列表和 `insufficient_evidence`，不得生成无来源答案。

## 写操作与审计

确认基线、修改行动项、记录人工复核等写操作必须保存操作者、时间、变更前后值、原因和证据。敏感正文不应完整进入普通日志；审计日志保存对象ID和操作摘要。接口限流、重试、幂等与错误处理需由实际实现另行设计和测试。
