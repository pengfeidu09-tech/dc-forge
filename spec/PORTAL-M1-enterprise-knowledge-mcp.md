# PORTAL-M1 企业招采可视化门户与MCP服务

## 背景

DATA-M1至DATA-M3已经形成三套模拟项目，其中`PRJ-TENDER-001`具备原始证据、Requirement Truth、供应商画像、文档审查、权限、时间点、RAG、评测和方案编译闭环。当前前端仍默认读取历史mock JSONL，`05_AI_Agent/MCP_tools.json`也明确标注为“契约示例、尚未实现”，因此企业内部人员、AI机器人和方案生成能力尚未共享同一套可执行服务。

本任务建立一个只读的企业招采知识服务，并让HTTP门户、内置AI助手、MCP客户端和现有方案编译器共享它。不得复制业务逻辑或绕过DATA-M3适配器中的ACL、字段脱敏、撤权和`as_of`规则。

## 数据与诚实性

- 所有项目数据继续标记为`synthetic_demo`；晚于2026-08-14的记录是`simulated_future_scenario`。
- 前端、API、MCP和AI回答必须显示模拟数据声明。
- PPT中的60%、50%、95%、6倍、86%等数字不得成为项目已实现指标。
- 方案评分和预期指标属于设计输出，不得描述为真实投产成效。

## 统一服务

在`backend/app/solution/`实现`EnterpriseKnowledgeService`，提供：

1. 项目列表；
2. 项目驾驶舱；
3. 受ACL和`as_of`约束的知识检索；
4. 需求版本历史；
5. 供应商画像和风险分析；
6. 文档审查黄金样本；
7. 从Requirement Truth编译三套方案。

`PRJ-TENDER-001`使用`SmartProcurementKnowledgeAdapter`作为权威读取路径。观察员不得看到合同单价和供应商评分；临时质量用户撤权后不得看到质量资料。

所有点-in-time接口都必须按`as_of`裁剪返回内容：需求基线形成前不得返回基线未决项，合同签署前不得返回合同复算，财务汇总快照时间晚于查询时间时必须明确返回`not_recorded_as_of`，不得把未来汇总混入历史回答。

这一规则同样适用于另外两套可浏览项目以及扩展MCP工具：项目驾驶舱中的版本、会议、沟通、车辆、履约和财务对象只能在其形成时间之后出现；决策历史、沟通检索、文档审查、对象追踪和财务复算必须复用来源清单的ACL、撤权和记录时间，不得另开绕过权限的读取路径。驾驶舱计数必须表示当前角色在当前`as_of`下实际可见的对象数，不能混用全量语料计数。

## MCP服务

在`backend/app/solution/mcp_server.py`实现可运行的MCP JSON-RPC服务，至少支持：

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`

工具至少包括：

- `list_projects`
- `get_project_dashboard`
- `search_knowledge`
- `get_requirement_history`
- `analyze_suppliers`
- `review_tender_document`
- `generate_solution_bundle`

服务支持标准输入输出启动：

```bash
PYTHONPATH=. python -m backend.app.solution.mcp_server
```

同时由FastAPI提供`POST /mcp` JSON-RPC入口，便于内部AI机器人通过HTTP调用。工具结果使用结构化JSON并保留来源ID、脱敏字段、模拟数据性质和人工复核边界。

## AI机器人接入

实现项目AI助手边界。助手不直接访问文件，而是调用同一个MCP调度器：

- 普通知识问题调用`search_knowledge`；
- 需求版本问题调用`get_requirement_history`；
- 供应商问题调用`analyze_suppliers`；
- 文档审查问题调用`review_tender_document`；
- 方案请求调用`generate_solution_bundle`。

回答必须包含来源ID或工具调用记录；证据不足时明确返回证据不足；高影响决定不得自动批准。

## 可视化门户

现有Vue前端改为企业内部招采工作台，并从FastAPI读取真实知识包数据。至少展示：

- 三个项目均可浏览：知识管理项目展示需求、会议与业务文档，车辆项目展示100个VIN、分批履约与角色化财务视图，智能招采黄金项目提供完整交互验收；
- `PRJ-TENDER-001`的九阶段采购主链；
- 原始证据、Requirement Truth、供应商、审查样本、评测题等数据量；
- 需求版本时间线和非阻断未决项；
- 供应商风险和评分的角色化视图；
- 文档审查控制/缺陷样本；
- 三套方案及组件、人工审批门和警告；
- 带来源引用的知识检索和AI助手；
- 角色选择、`as_of`时间点和模拟数据声明。

前端不得再以Twitter/CFPB mock作为默认业务数据。API不可用时应显示明确错误，不得静默伪造后台结果。

## API

至少提供：

- `GET /enterprise/projects`
- `GET /enterprise/projects/{project_id}/dashboard`
- `GET /enterprise/projects/{project_id}/search`
- `GET /enterprise/projects/{project_id}/requirements/{requirement_id}/history`
- `GET /enterprise/projects/{project_id}/suppliers`
- `GET /enterprise/projects/{project_id}/document-reviews`
- `POST /enterprise/projects/{project_id}/compile`
- `POST /enterprise/assistant`
- `POST /mcp`

## 验收

1. 服务计算的项目计数与DATA-M3文件一致；
2. 观察员字段脱敏和临时用户撤权可执行；
3. `as_of=2026-08-14`不得泄漏V3；
4. MCP能够列工具并调用知识检索与方案生成；
5. AI助手的工具调用来自MCP调度器；
6. 方案生成返回现有公共`SolutionBundle`的三种策略；
7. Vue生产构建成功且默认请求企业门户API；
8. 新测试、相关DATA测试和`tests/test_contracts.py`通过；
9. `git diff --check`通过。
10. 历史驾驶舱和财务复算均不得泄漏查询时间之后形成的对象或汇总快照；门户HTML标题和描述必须明确为企业招采门户。
11. 三个项目的历史驾驶舱均按`as_of`裁剪；扩展MCP工具对受限来源、撤权用户和未记录对象执行一致的拒绝或过滤；门户使用可编辑时间控件并显示时间点可见计数。
