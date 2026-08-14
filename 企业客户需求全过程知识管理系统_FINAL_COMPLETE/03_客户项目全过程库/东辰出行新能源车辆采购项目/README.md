# 东辰出行新能源车辆采购项目（模拟）

这是一个用于展示客户需求全过程知识管理的合成案例。项目模拟某汽车租赁企业采购 100 台纯电轿车，从线索、需求版本、澄清和 Go/No-Go 开始，经过供应商询价、采购组合、客户方案、报价谈判、审批、合同订单，最终下沉到 100 个唯一模拟 VIN，并覆盖物流、分批交付、异常复验、发票、收付款、利润、售后和复购线索。

> 数据声明：本项目中的企业、人员、代码、VIN、价格、合同、日期、满意度和结果全部为 `synthetic_demo`，不代表真实业务成果。晚于数据制作日期的记录是 `simulated_future_scenario`，不表示已经发生。所有 VIN 都包含 `FAKE` 字样，仅用于演示关联关系。

## 主追溯链

`LEAD-AUTO-001 → REQ-AUTO-001 → REQ-AUTO-001-V3 → OPP-AUTO-001 → RFQ-AUTO-001 → SQ-* → PP-AUTO-001 → SOL-AUTO-001 → QUOTE-AUTO-001-V3 → SC-AUTO-001 → SO-* → PO-* → VIN → SHIP-* → DEL-* → ACC-* → INV/RCPT/PAY → AST-* → REP-*`

## 阅读顺序

1. `project_master.json`
2. `01_客户与需求/customer_requirement.json`
3. `02_澄清与评估/clarification_and_feasibility.json`
4. `03_商品与寻源/sourcing.json`
5. `04_方案商务/solution_commercial.json`
6. `05_合同订单/contracts_orders.json`
7. `06_履约交付/fulfillment.json`
8. `07_财务利润/finance.json`
9. `08_售后复盘/after_sales_review.json`

金额单位均为含税人民币元，利润率按小数保存；时间使用 `Asia/Shanghai`。
