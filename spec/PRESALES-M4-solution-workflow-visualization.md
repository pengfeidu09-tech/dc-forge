# PRESALES-M4：解决方案流程图可视化

## 背景

统一售前工作台已经按“方案编排”展示三套方案，但目标流程仍然隐含在能力卡片和文字列表中。每套方案的 `target_workflow` 已包含节点顺序、执行者、人工审批门和门控原因，适合用流程图呈现。

能力清单、数据要求和实施步骤目前没有显式父子 ID 或依赖边，不能擅自推断为树形关系。本任务只图形化有真实顺序语义的 `target_workflow`。

## 目标

- 使用 Vue Flow 在方案编排区展示当前所选方案的目标工作流。
- 支持在稳健合规、效率平衡和智能重构三套方案之间切换。
- 通过节点视觉区分 AI、系统和人工执行者。
- 明确标识人工审批门，并展示 `gate_reason`。
- 支持缩放、平移、适配视图和缩略导航，不允许用户在只读工作台中修改流程关系。

## 数据映射

1. 一个 `target_workflow` 项对应一个流程节点，节点编号使用数组顺序。
2. 相邻节点按数组顺序连接，边只表达现有顺序，不推断未提供的分支。
3. 节点显示 `name`、`executor`、序号和人工门状态。
4. `human_gate=true` 时显示审批门标识，并展示 `gate_reason`；无原因时不得编造说明。
5. 节点较多时使用多行蛇形布局，连接顺序保持不变，画布支持平移和缩放。
6. 方案没有 `target_workflow` 时显示明确空状态并保留原方案详情。

## 交互与布局

- 流程图位于“当前方案草稿”成果摘要之后、方案详情之前。
- 使用 Ant Design Vue `Segmented` 切换方案，默认选中后端标记的推荐方案。
- 图例固定展示 AI、系统、人工和人工审批门四种语义。
- 画布桌面高度固定，避免切换方案导致页面跳动；窄屏降低高度但保持可缩放。
- 方案详情卡继续展示摘要和能力原因，流程图不取代审计所需的文字信息。

## 技术方案

- 使用 `@vue-flow/core` 处理节点、边、缩放和平移。
- 使用 `@vue-flow/background`、`@vue-flow/controls` 和 `@vue-flow/minimap` 提供背景、视图控制与缩略导航。
- 使用独立 `SolutionWorkflowGraph.vue` 组件和纯函数 `solutionWorkflowGraph.js`，便于测试数据映射。
- Vue Flow 样式只加载到 presales 多页面入口，不影响主门户。

## 验收标准

1. `frontend/package.json` 直接依赖 Vue Flow 核心和所用插件。
2. 方案编排区包含方案切换控件和 Vue Flow 画布。
3. 节点数量等于 `target_workflow` 项数，边数量为非空流程节点数减一。
4. 所有边保持数组顺序，人工审批门和门控原因被保留。
5. 流程图为只读，不允许拖动节点或创建连接。
6. 新测试、既有售前前端测试、`tests/test_contracts.py` 和前端构建通过。
7. 在桌面和移动视口完成浏览器渲染检查，无空白画布、文字覆盖或异常滚动。

## 验证命令

```bash
pytest tests/solution/test_presales_solution_flow_frontend.py
cd frontend && npm test
cd frontend && npm run build
PYTHONPATH=. pytest tests/test_contracts.py
```
