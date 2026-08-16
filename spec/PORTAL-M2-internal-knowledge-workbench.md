# PORTAL-M2 内部知识检索与MCP工具工作台

## 背景

PORTAL-M1已经提供三项目驾驶舱、AI助手以及HTTP/stdio MCP服务，但内部人员仍缺少两个直接操作入口：一是按项目、角色和时间点查询知识来源，二是查看MCP工具契约并试运行工具。仅能通过聊天间接触发工具，不足以作为内部知识系统的日常工作界面。

## 目标

在现有企业门户中增加“知识检索”和“MCP工具箱”两个工作视图。前端必须直接消费现有受治理接口，不复制搜索、权限、时间过滤或方案编译逻辑。

## 知识检索

- 调用`GET /enterprise/projects/{project_id}/search`。
- 查询必须携带当前`user_id`、`as_of`和结果上限。
- 展示命中内容、`source_id`、`source_version`、记录时间和脱敏字段。
- 无可靠证据时展示`insufficient_evidence`，不得生成补全内容。
- 切换项目、角色或时间点后，下一次查询必须使用新的上下文。

## MCP工具箱

- 通过`POST /mcp`调用`tools/list`加载运行时工具，不在前端维护一份静态工具名单。
- 展示工具名称、说明、只读属性、必填参数和JSON Schema类型。
- 根据所选工具的`inputSchema`生成参数表单。
- `project_id`、`user_id`和`as_of`自动使用门户当前上下文，允许用户在执行前检查。
- 通过`POST /mcp`调用`tools/call`，展示完整结构化响应或JSON-RPC错误。
- 空的可选参数不得发送；整数参数按整数发送。
- 工具执行不得绕过服务端ACL、撤权、字段脱敏和时间点规则。

## 交互边界

- 页面只在`tools/list`真实成功后显示MCP就绪状态。
- API不可用时显示可恢复错误，不使用假数据或硬编码成功响应。
- 所有结果继续标记为`synthetic_demo`；方案评分不描述为真实投产效果。
- 页面在桌面和移动端都不能发生横向内容遮挡；JSON结果允许自身滚动。

## 验收

1. 导航包含“知识检索”和“MCP工具箱”。
2. 知识查询调用现有项目检索API并展示来源与证据不足状态。
3. 工具目录来自MCP `tools/list`，当前应返回11个只读工具。
4. 工具表单由`inputSchema`生成，能通过`tools/call`执行`search_knowledge`和`generate_solution_bundle`。
5. 项目、角色、时间点切换会同步到工具参数。
6. JSON-RPC错误和HTTP错误均明确展示。
7. 新前端测试、MCP/API测试、`tests/test_contracts.py`和生产构建通过。
8. `git diff --check`通过，模拟数据声明保持可见。
