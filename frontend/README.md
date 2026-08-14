# DC Forge 企业智能招采门户

基于 Vue 3 + Vite 的企业内部招采可视化工作台。页面不再默认读取历史 Twitter/CFPB mock，而是通过 FastAPI 读取完善后的企业客户全过程知识包，展示采购九阶段、需求版本、供应商风险、文档审查、方案生成和通过 MCP 调度的 AI 助手。

## 启动

先在仓库根目录启动后端：

```bash
PYTHONPATH=. python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

开发模式启动前端：

```bash
cd frontend
npm ci
npm run dev
```

Vite 会把 `/enterprise` 和 `/mcp` 代理到 `http://127.0.0.1:8000`。

生产构建：

```bash
npm run build
```

构建后的 `frontend/dist` 会由 FastAPI 同源托管。重新启动后访问：

```text
http://127.0.0.1:8000/
```

## 数据与权限

- 三个项目均可浏览：`PRJ-KM-001`展示需求、会议和正式文档，`PRJ-AUTO-001`展示100个VIN、分批履约和角色化财务信息，`PRJ-TENDER-001`提供完整需求、供应商、审查、RAG、AI和方案交互。
- 页面可切换采购、法务财务、供应商质量和受限观察员角色。
- 所有查询携带 `as_of` 时间点，不会使用当时尚未发生或记录的未来需求版本。
- 观察员看不到合同单价与供应商评分；临时质量用户撤权后不能继续读取质量资料。
- 所有数据均为 `synthetic_demo`，页面中的计数、评分和预期指标不是实际经营成果。

## MCP与AI助手

AI助手通过后端MCP调度器调用以下工具：

- 知识检索和需求版本历史；
- 供应商分析和文档审查；
- 业务对象追踪和财务复算；
- 三套方案生成。

可单独启动stdio MCP服务：

```bash
PYTHONPATH=. python -m backend.app.solution.mcp_server
```

## 目录结构

```text
src/
├── components/      # 可复用展示与交互组件
├── composables/     # 企业门户API、角色、时间点和AI助手状态
├── styles/          # 设计变量、全局样式和响应式布局
├── App.vue          # 工作台编排
└── main.js
```
