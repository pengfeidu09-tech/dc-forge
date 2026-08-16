# PRESALES-M3：Ant Design Vue 统一售前工作台重写

## 背景

`/presales/workbench` 当前由后端返回单文件 HTML。项目列表、阶段进度、沟通、需求、资料、研究、Skill、方案、评审和发布全部平铺在同一页面，新增、编辑、评审等操作依赖浏览器 `prompt` 和 `alert`。页面可以调用业务接口，但缺少工作台应有的信息层级、操作反馈和高频任务效率。

仓库已经统一为一个 `frontend/` Vue/Vite 工程。本次重写必须继续遵守单一前端工程约束，不新增独立前端包。

## 目标

使用 Ant Design Vue 将统一售前工作台重写为面向售前负责人和方案负责人的运营工作台：

- 快速切换和检索客户项目；
- 一眼识别当前阶段、需求状态、阻断缺口和待评审事项；
- 按“项目总览、资料与研究、方案编排、评审发布”组织业务信息；
- 通过结构化表单、确认框和状态反馈完成所有原有操作；
- 保持 `/presales/workbench` URL、兼容别名和现有 API 合同不变。

## 技术方案

1. 在现有 `frontend/` 中增加 `presales/workbench/index.html` 多页面入口，继续使用同一份 `package.json`、Vite 配置和构建命令。
2. 页面使用 Vue 3 与 Ant Design Vue，图标使用 `@ant-design/icons-vue`。
3. `frontend/src/presales/` 持有页面组件和 API 客户端，不在后端 Python 字符串中维护业务 UI。
4. Vite 构建生成 `frontend/dist/presales/workbench/index.html` 及同源资源；嵌套输出让 `base: './'` 在原 URL 下仍正确解析 `/assets`，不破坏主门户的 GitHub Pages 相对路径构建。
5. 后端 `/presales/workbench` 和 `/customer-engagement/workbench` 优先返回该构建产物；构建产物不存在时返回明确的构建提示页面，不能回退到旧工作台。
6. 现有 `X-DCForge-Internal-Token`、CSP 和其他安全响应头保持不变。

## 信息架构

### 全局框架

- 左侧固定项目导航：项目搜索、新建项目、阶段与消息数量。
- 顶部紧凑工具栏：当前项目、负责人、行业、刷新、内部访问令牌设置。
- 项目头部：当前阶段、客户中心入口和关键行动。
- 指标栏：沟通数量、结构化需求、阻断缺口、方案/发布状态。指标只描述当前系统对象，不描述真实业务成果。
- 八阶段进度条：保留 completed、current、pending 状态语义。

### 工作区标签

1. **项目总览**：飞书与客户沟通时间线、Requirement Intelligence、需求缺口。
2. **资料与研究**：客户/内部/外部资料、研究快照、企业知识结果和外部引用。
3. **方案编排**：Skill 模板链、三套方案草稿、成果稿编辑和生成操作。
4. **评审发布**：评审历史、批准/驳回、发布记录与客户中心入口。

## 交互规则

- 新建项目、添加资料、发起研究、编辑成果、评审和发布均使用 Ant Design Vue 表单弹窗或确认框，不使用 `prompt`、`alert` 或拼接 `innerHTML`。
- 加载过程使用 Skeleton/Spin；空数据使用 Empty；失败使用 Alert 和 message；破坏性操作明确标色。
- 项目搜索只过滤当前已加载项目，不修改服务端数据。
- 切换或刷新项目后保持当前标签页，不产生无关页面跳转。
- 未批准草稿时发布按钮禁用，并显示原因。
- 演示预览、方案评分和预期指标不得描述为已经实现的客户业务成果。
- 桌面端优先支持高密度扫描；窄屏下项目导航折叠，表格允许横向滚动，文字不得互相覆盖。

## API 保持

- `GET /presales/projects`
- `POST /presales/projects`
- `GET /presales/projects/{project_id}`
- `POST /presales/projects/{project_id}/sources`
- `POST /presales/projects/{project_id}/research`
- `POST /presales/projects/{project_id}/drafts`
- `POST /presales/projects/{project_id}/drafts/{draft_version}/deliverable`
- `POST /presales/projects/{project_id}/reviews`
- `POST /presales/projects/{project_id}/publish`

## 验收标准

1. `frontend/package.json` 直接依赖 Ant Design Vue 和 Ant Design Vue 图标包。
2. `frontend/presales/workbench/index.html` 作为 Vite 多页面入口，`npm run build` 生成 `dist/presales/workbench/index.html`。
3. 工作台组件包含项目导航、四个业务标签、八阶段进度、结构化表格/时间线和所有原操作弹窗。
4. 工作台源码不包含 `prompt(`、`alert(` 或 `innerHTML`。
5. 后端页面函数不再包含旧工作台的内联业务脚本和样式。
6. `/presales/workbench` 与兼容别名仍返回 200，并保留安全响应头。
7. 新测试、`tests/solution/test_presales_orchestration.py`、`tests/test_contracts.py` 和前端构建通过。

## 验证命令

```bash
pytest tests/solution/test_presales_workbench_frontend.py
cd frontend && npm run build
PYTHONPATH=. pytest tests/solution/test_presales_orchestration.py
PYTHONPATH=. pytest tests/test_contracts.py
```
