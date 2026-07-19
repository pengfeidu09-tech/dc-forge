# B-M7: 跨场景自适应方案编译与人工审批修复

**状态：** implemented

## 初始问题

1. 非采购场景仍出现采购订单、发票、收货记录等硬编码
2. 不同业务场景的组件、节点和实施步骤过于相同
3. human-approval 节点可能出现 human_gate=false
4. balanced summary 无条件声称"默认推荐"

## 场景识别逻辑

使用 industry、department、business_goal、available_data、pain_points、target_metrics 进行关键词匹配（不使用 project_id）。

支持 7 种场景：incident_response、fraud_risk、identity_account、dispute_investigation、customer_service、procurement_exception、generic。

## 场景与组件映射

每种场景有独立的 conservative/balanced/innovative 组件列表、节点名称、实施步骤和审批理由。详见 `backend/app/solution/scenario.py`。

## human_gate 修复

human-approval 节点统一设置 `executor="human"`, `human_gate=true`，gate_reason 根据场景生成（不再固定写"超过50万元"）。

## 10 条 A 数据重新编译结果

- 10/10 编译成功
- 5 种场景：incident_response(3), customer_service(1), identity_account(1), fraud_risk(2), dispute_investigation(3)
- 5 种不同组件集合
- 5 种不同节点序列
- 30/30 human-approval 节点 human_gate=true
- 0 采购术语违规

## 测试结果

- test_domain_adaptive_compiler: 7 passed
- tests/solution: 156 passed
- tests/test_contracts.py: 3 passed
- tests (全量): 159 passed

## 真实 Agent 验证

qwen3.7-plus 正确识别 compile 意图，调用 compile_solution，返回场景化方案，无 API Key 泄露。

## 当前限制

- 场景识别基于关键词匹配，后续可替换为语义理解
- 工作流仍为线性链
- capabilities.json 的 required_data 仍包含采购相关术语（共享数据，不在本任务修改范围）
