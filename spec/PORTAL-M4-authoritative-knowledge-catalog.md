# PORTAL-M4 权威资料目录与需求证据查询

## 背景

当前企业门户和MCP服务已经能够读取三套模拟项目的驾驶舱、RAG片段和部分结构化业务对象，但尚未把
`企业客户需求全过程知识管理系统_FINAL_COMPLETE`中的项目文件统一编目。会议纪要、沟通记录、招标文件、
需求文档和项目数据虽然已经存在于资料包中，REST调用方仍无法稳定列出某项目的全部资料，也不能直接按需求
查询其关联来源。

本任务将该目录设为企业知识服务的唯一权威数据源。系统只读消费资料包，不引入外部动态仓库，不把模拟数据
描述为真实经营成果。

## 权威数据边界

- 权威根目录固定为`企业客户需求全过程知识管理系统_FINAL_COMPLETE`。
- 项目注册表来自`06_DEMO数据/demo_seed.json`，项目主数据来自各项目的`project_master.json`。
- 项目资料只从注册项目对应的目录读取；不得扫描工作区其他目录作为客户事实。
- 原始文件不被服务修改、移动或重新生成。
- 所有返回继续携带`synthetic_demo`和`is_real_business_result=false`语义。
- PDF等二进制文件进入目录元数据，但不伪造未抽取的正文；已有OCR/RAG派生文件仍按资料包中的真实记录查询。

## 自动资料目录

新增只读权威资料目录，启动后按需扫描三套项目：

1. 为每个文件生成稳定`source_id`；DATA-M3原始证据优先复用`source_manifest.json`中的正式来源ID。
2. 识别`meeting_minutes`、`communication`、`bid_document`、`requirement_document`、
   `customer_profile`、`project_data`、`document_review`和`attachment`等资料类型。
3. 对UTF-8的Markdown、JSON、JSONL、TXT和YAML读取可检索正文；二进制文件只返回元数据。
4. 从权威正文、结构化字段和显式`source_refs`提取需求ID、需求版本ID及其他业务对象ID。
5. 基础需求ID查询必须包含其版本资料，例如查询`REQ-001`应匹配`REQ-001-V1`至`REQ-001-V3`。
6. 返回相对权威根目录的路径，不向API或MCP暴露主机绝对路径。
7. DATA-M3正式来源继续使用既有ACL、撤权和`as_of`规则；其他项目沿用现有门户用户和时间点边界。

## REST查询

在现有企业API增加：

- `GET /enterprise/projects/{project_id}/sources`
- `GET /enterprise/projects/{project_id}/sources/{source_id}`
- `GET /enterprise/projects/{project_id}/requirements/{requirement_id}/sources`

资料列表支持`user_id`、`as_of`、`source_type`、`requirement_id`、`query`、`limit`和`offset`。
详情接口返回可用正文、资料元数据、关联需求和业务对象；无正文的二进制文件明确返回
`content_available=false`。

项目驾驶舱增加权威资料总数和按类型计数。需求历史响应增加`source_records`，但不得破坏现有字段。

## MCP与AI Agent

保持现有11个只读MCP工具契约，避免资料包中的MCP清单与运行时漂移：

- `search_knowledge`同时检索既有治理RAG和权威项目文件；结果必须包含稳定来源ID及相对路径。
- `get_requirement_history`返回该需求的`source_records`，供Agent追溯会议、沟通和业务文档。
- 其他工具继续遵守项目、角色和`as_of`边界。

不新增写工具，不允许Agent修改权威资料。

## 非目标

- 不接收资料包以外的任意文件上传。
- 不接入生产CRM、邮箱、会议平台或对象存储。
- 不修改`backend/app/contracts/`、`backend/app/process/`、`backend/app/runtime/`、`data/fixtures/`或前端。
- 不把资料包中的模拟金额、评分、交付和未来事件描述为真实业务成果。

## 验收

1. 项目注册表仍为`PRJ-KM-001`、`PRJ-AUTO-001`和`PRJ-TENDER-001`。
2. 每个项目均可通过REST列出权威目录中的资料，且路径限定在权威根目录内。
3. `PRJ-KM-001`可列出12份会议纪要、沟通记录和招标文件。
4. `PRJ-TENDER-001`原始证据复用`SRC-TENDER-001..026`，并按ACL和`as_of`过滤。
5. 按`REQ-001`、`REQ-AUTO-001`和`REQ-BAT-001`查询均返回关联资料。
6. 来源详情只返回相对路径；文本资料返回正文，PDF明确无直接正文。
7. REST OpenAPI暴露三个新增只读接口。
8. MCP工具数量保持11；知识检索和需求历史可返回权威资料来源。
9. 现有企业门户、MCP、Agent和合同测试保持通过。
10. `git diff --check`通过。
