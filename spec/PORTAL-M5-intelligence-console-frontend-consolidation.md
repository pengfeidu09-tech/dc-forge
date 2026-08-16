# PORTAL-M5：Intelligence Console 前端项目合并

## 背景

仓库当前同时维护 `frontend/` 企业招采门户和 `tools/intelligence_console/` 内部智能引擎控制台两个 Vue/Vite 前端项目。团队只保留一个前端工程，避免重复的依赖、构建入口、开发端口和部署方式。

## 目标

将 Intelligence Console 的完整交互能力合并到 `frontend/`，作为企业招采门户中的一个内部工作台视图。合并后，前端依赖安装、开发、测试和生产构建统一从 `frontend/` 执行。

## 范围

- 在主门户侧边栏增加“智能引擎控制台”入口。
- 将需求分析、需求确认、方案生成、客户反馈、需求差异和方案重编译界面迁入主前端组件。
- 将 Console API 客户端和会话快照工具迁入 `frontend/src/`。
- 主前端 Vite 开发服务器代理 `/internal-console` 到 FastAPI 的 8000 端口。
- 将原 Console 的会话快照单元测试迁入主前端测试目录。
- 移除 `tools/intelligence_console/` 的独立 Vite 工程文件。

## 非目标

- 不修改 `/internal-console` 的后端 HTTP 合同或业务实现。
- 不改变 `DCFORGE_ENABLE_INTERNAL_CONSOLE` 的启用规则。
- 不把内部调试控制台描述为客户生产能力或真实经营成果。
- 不重构企业门户现有业务视图。

## 交互与运行规则

1. 用户可从主门户侧边栏进入“智能引擎控制台”。
2. Console 视图不依赖企业门户 Dashboard 请求成功后才可打开；其健康检查和业务请求独立执行。
3. Console 会话继续保存到浏览器 `sessionStorage`，保持现有 key 和快照语义。
4. 所有 Console 请求继续使用 `/health` 和 `/internal-console/*` 相对路径。
5. 当后端未启用 Internal Console 时，界面必须诚实显示连接或请求失败，不伪造成功结果。

## 验收标准

- `frontend/src/App.vue` 导入并渲染 Intelligence Console 组件，侧边栏存在对应入口。
- `frontend/vite.config.js` 同时代理 `/enterprise`、`/mcp` 和 `/internal-console`。
- 主前端源码包含原 Console 的七个 API 操作：`analyze`、`confirm`、`compile`、`diff`、`recompile`、`change-set` 和 `change-set/review`。
- 会话快照与重编译 payload 单元测试从 `frontend/` 运行并通过。
- `npm run build` 在 `frontend/` 成功生成单一生产构建。
- `tools/intelligence_console/` 不再包含独立的 `package.json`、Vite 配置或应用入口。
- `tests/test_contracts.py` 通过。

## 验证命令

```bash
pytest tests/solution/test_intelligence_console_frontend_integration.py
cd frontend && npm test
cd frontend && npm run build
pytest tests/test_contracts.py
```
