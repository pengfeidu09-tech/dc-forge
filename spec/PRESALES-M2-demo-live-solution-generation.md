# PRESALES-M2 Demo 实时方案生成

## 背景

统一售前工作台当前要求演示人员手工输入 `RequirementBaseline` 版本，且在项目尚未形成正式 Baseline 时直接暴露底层版本不存在错误。Baseline 是内部审计概念，不应成为 Demo 操作负担。

## 目标

演示人员点击“生成三套方案与成果草稿”后，系统直接读取该项目的最新需求事实并实时调用现有 Solution Intelligence 编译器：

- 有正式 Baseline 时，自动使用最新 Baseline；
- 没有正式 Baseline 时，基于最新 RequirementState 生成标记为“演示预览”的方案草稿；
- 不要求用户输入或理解 Baseline 版本号；
- 不把未确认信息描述成客户已确认事实，也不把演示指标描述成真实业务成果。

## 行为约束

1. 工作台生成按钮直接调用生成接口，不再显示 Baseline 版本或生成人输入框；演示工作台使用固定的内部生成身份。
2. `POST /presales/projects/{project_id}/drafts` 的 `baseline_version` 保持可选，以兼容既有调用方。
3. 当正式 Baseline 存在时，服务自动选择最新版本并保持既有正式编译行为。
4. 当正式 Baseline 不存在时：
   - 必须存在最新 RequirementState；
   - 将当前有效需求项适配为仅用于 Demo 的 `ProcessSpec`；
   - 缺失字段使用明确的“待确认”占位，不伪造客户事实；
   - 调用现有 `compile_solution_v2` 实时生成三套方案；
   - 若当前信息不足以匹配可执行方案资产，则自动降级调用现有通用三方案编译器，不向演示人员暴露底层编译异常；
   - 草稿保存 `requirement_state_version`、`requirement_basis=latest_requirement_state`、`baseline_version=null`；
   - 草稿和客户成果稿明确提示需求尚未形成正式确认基线。
5. 正式 Baseline 草稿保存 `requirement_basis=confirmed_baseline`。
6. 页面不得再展示“生成前需要正式 Baseline”的阻断文案。
7. 方案效果与指标只能表述为待验证假设。
8. 基于最新 RequirementState 的演示草稿经内部批准后可以发布到客户中心；发布记录必须保存 `requirement_state_version`、`publication_basis=latest_requirement_state` 和明确的演示预览提示，不得伪装成正式 Baseline 方案。

## 验收标准

1. 无 Baseline、有 RequirementState 和研究快照时可生成三套演示方案。
2. 请求无需提交 `baseline_version`。
3. 草稿可追溯到生成时使用的 State 版本，并明确为演示预览。
4. 有 Baseline 时仍自动使用最新 Baseline。
5. 工作台 HTML 不包含 `prompt('Baseline 版本'`。
6. 新测试、`tests/test_contracts.py` 和既有售前编排测试通过。
7. 演示草稿经批准后可在客户中心查看，且客户页面明确显示“演示预览”。
