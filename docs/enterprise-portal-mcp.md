# 企业招采门户与MCP运行说明

## 一条服务启动门户、API和HTTP MCP

先构建前端：

```bash
cd /Volumes/DataSSD/HomeFolders/MyProject/dc-forge/frontend
npm ci
npm run build
```

再启动FastAPI：

```bash
cd /Volumes/DataSSD/HomeFolders/MyProject/dc-forge
PYTHONPATH=. .venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

企业内网人员访问服务器的8000端口即可打开门户。当前机器本地地址为：

```text
http://127.0.0.1:8000/
```

同一进程还提供：

- OpenAPI：`/docs`
- 企业知识API：`/enterprise/*`
- HTTP MCP JSON-RPC：`POST /mcp`
- 飞书事件：`POST /integrations/feishu/events`

## 唯一权威数据源

企业知识门户只读使用仓库内的`企业客户需求全过程知识管理系统_FINAL_COMPLETE`。项目注册表来自
`06_DEMO数据/demo_seed.json`，项目资料来自三套注册项目目录；服务不会把工作区其他文件或外置需求仓库
混入企业知识查询。

系统会自动编目项目目录中的Markdown、JSON、JSONL、TXT、YAML和二进制附件，识别会议纪要、沟通记录、
招标文件、需求文档及项目数据，并从正文和结构化字段关联需求ID。DATA-M3原始证据继续复用
`SRC-TENDER-001..026`及其ACL、撤权和`as_of`规则。所有数据均为`synthetic_demo`。

资料查询接口：

- `GET /enterprise/projects/{project_id}/sources`
- `GET /enterprise/projects/{project_id}/sources/{source_id}`
- `GET /enterprise/projects/{project_id}/requirements/{requirement_id}/sources`

资料列表支持按类型、需求ID和关键词过滤。接口只返回相对权威目录的路径；没有可读正文的附件会明确返回
`content_available=false`，受限资料会返回`masked_fields=["content"]`而不是正文预览。

## 内部知识工作台

门户左侧提供两个面向内部使用的直接入口：

- `知识检索`：按当前项目、角色和数据时间点调用`GET /enterprise/projects/{project_id}/search`，结果显示来源ID、来源版本、记录时间和脱敏字段；没有可靠证据时明确显示`insufficient_evidence`。
- `MCP 工具箱`：通过`POST /mcp`的`tools/list`读取运行时工具目录，根据每个工具的`inputSchema`生成参数表单，再通过`tools/call`试运行。工具响应以`structuredContent`原样展示，JSON-RPC错误不会被包装成成功结果。

项目、查看角色或数据时间点改变后，知识查询和MCP工具参数会同步更新。页面不维护静态工具名单，因此运行时工具契约与界面保持一致。

HTTP MCP调用示例：

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_knowledge",
      "arguments": {
        "project_id": "PRJ-TENDER-001",
        "query": "年需求量",
        "user_id": "user-procurement-owner",
        "as_of": "2026-10-30T23:59:59+08:00"
      }
    }
  }'
```

## stdio MCP客户端

可运行命令：

```bash
cd /Volumes/DataSSD/HomeFolders/MyProject/dc-forge
PYTHONPATH=. .venv/bin/python -m backend.app.solution.mcp_server
```

客户端配置示例见 `docs/enterprise-mcp-client.example.json`。当前配置使用本机绝对路径；复制到其他服务器时需要修改`command`和`cwd`。

MCP暴露11个只读工具：项目列表、驾驶舱、知识检索、需求历史、供应商分析、文档审查、方案生成、决策历史、沟通检索、业务对象追踪和财务复算。`search_knowledge`的结构化响应包含权威资料命中，`get_requirement_history`包含`source_records`，因此Agent无需新增写工具即可追溯需求对应的会议、沟通和业务文档。

`search_knowledge`和`get_requirement_history`可用于三套项目；供应商画像、文档审查、正式方案、决策追踪、对象图和财务复算等深度工具当前以`PRJ-TENDER-001`黄金案例为权威契约。网页AI在其他两套项目遇到相关问题时会回退到各项目已有RAG语料，不会调用不适用的专用工具。所有点-in-time工具（包括文档审查）都要求显式传入带时区的`as_of`。

## AI机器人

网页AI助手直接调用MCP调度器。飞书机器人可使用：

```text
/mcp 供应商三为什么未进入推荐？
/mcp 2026-08-14当时客户确认了什么？
/mcp 请生成这个项目的三套方案
```

飞书MCP入口默认映射到`PRJ-TENDER-001`，可通过以下变量修改：

```text
FEISHU_ENTERPRISE_PROJECT_ID
FEISHU_ENTERPRISE_USER_ID
FEISHU_ENTERPRISE_AS_OF
```

## 数据边界

所有企业、供应商、合同、价格、风险、评分和结果均为`synthetic_demo`。晚于2026-08-14的记录是`simulated_future_scenario`。方案评分、PPT营销数字和模拟统计都不是已实现的真实业务成果。
