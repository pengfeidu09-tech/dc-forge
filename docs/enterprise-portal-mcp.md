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

## stdio MCP客户端

可运行命令：

```bash
cd /Volumes/DataSSD/HomeFolders/MyProject/dc-forge
PYTHONPATH=. .venv/bin/python -m backend.app.solution.mcp_server
```

客户端配置示例见 `docs/enterprise-mcp-client.example.json`。当前配置使用本机绝对路径；复制到其他服务器时需要修改`command`和`cwd`。

MCP暴露11个只读工具：项目列表、驾驶舱、知识检索、需求历史、供应商分析、文档审查、方案生成、决策历史、沟通检索、业务对象追踪和财务复算。

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
