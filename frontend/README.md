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

Vite 会把 `/health`、`/enterprise`、`/mcp`、`/internal-console` 和 `/presales/projects` 代理到 `http://127.0.0.1:8000`。

门户包含独立的`知识检索`和`MCP 工具箱`视图。知识检索直接调用项目搜索API；MCP工具箱从运行时`tools/list`生成目录和参数表单，并可执行`tools/call`。两者都使用页面顶部当前选择的项目、角色和`as_of`时间点。

门户侧边栏还包含`智能引擎控制台`内部视图，提供需求分析、显式确认、方案编译、客户反馈差异和重编译工作流。该视图沿用后端的条件启用规则；需要在启动后端前设置：

```bash
export DCFORGE_ENABLE_INTERNAL_CONSOLE=true
```

未启用时，控制台会显示请求失败，不会模拟成功结果。

生产构建：

```bash
npm run build
```

构建后的 `frontend/dist` 会由 FastAPI 同源托管。重新启动后访问：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/presales/workbench
```

`/presales/workbench` 是同一 Vite 工程的 Ant Design Vue 多页面入口，提供项目导航、需求与缺口、资料研究、方案编排、内部评审和客户发布操作，不需要单独安装或启动另一套前端。

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
├── presales/        # Ant Design Vue 统一售前工作台
├── styles/          # 设计变量、全局样式和响应式布局
├── App.vue          # 工作台编排
└── main.js
```
