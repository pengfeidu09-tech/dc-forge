# PORTAL-M7 全站 Ant Design Vue 页面统一

## 背景

DCForge 当前存在三类页面实现：主企业门户使用自定义 HTML/CSS，售前工作台已经使用 Ant Design Vue，客户需求与方案中心仍由后端拼接内嵌 HTML。组件体系、交互反馈、表单校验和响应式行为不一致，增加演示和上线维护成本。

## 目标

全站统一使用项目已经安装的 Ant Design Vue 4，不引入第二套 UI 组件库：

- 企业招采知识门户 `/`；
- 智能引擎控制台（主门户内页）；
- 统一售前工作台 `/presales/workbench`；
- 客户需求与方案中心 `/customer/engagement/{access_id}`；
- 上述页面复用的卡片、指标、流程、方案详情和弹窗组件。

## 实现要求

1. 根入口统一安装 Ant Design Vue 和 reset 样式。
2. 主门户使用 `Layout`、`Menu`、`Card`、`Row/Col`、`Statistic`、`Table/List`、`Tabs/Segmented`、`Form/Input`、`Alert/Result/Spin` 等组件表达主要信息架构。
3. Intelligence Console 的标签切换、按钮、输入框、提示、卡片和抽屉改用 Ant Design Vue；保留全部需求分析、确认、编译、反馈、Diff 与重编译能力。
4. 客户中心迁入 `frontend/`，成为独立 Vite 多页入口；后端只返回构建后的 HTML 边界，不再维护内嵌应用脚本。
5. 客户中心必须保留：
   - access token 校验；
   - 需求单选/多选确认；
   - 冲突选择；
   - 补充反馈；
   - 三套方案和推荐标记；
   - 演示预览提示；
   - 客户成果稿下载。
6. 售前工作台继续使用现有 Ant Design Vue 实现，不倒退为后端模板。
7. 页面不得使用浏览器 `prompt`、`alert` 或通过 `innerHTML` 拼业务界面。
8. 保留所有现有业务文案、权限边界、时间语义和“模拟数据不是业务成果”的诚实性提示。
9. 构建产物由 FastAPI 同源提供，满足现有 CSP 和安全响应头。

## 验收标准

1. 主门户、智能控制台、售前工作台和客户中心源码均出现 Ant Design Vue 组件。
2. 客户中心存在独立 Vite entry，构建后生成 `dist/customer/engagement/index.html`。
3. 后端客户页函数只读取构建入口或显示明确的未构建回退页，不包含业务应用 JavaScript。
4. 主要共用组件使用 `Card`、`Progress`、`Steps`、`Tag`、`Alert` 等组件库能力。
5. `npm run build`、前端源码验收测试、相关后端页面测试及 `tests/test_contracts.py` 通过。

