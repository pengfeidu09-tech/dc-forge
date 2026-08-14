"""客户需求全过程模拟数据集的完整性和业务守恒测试。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = ROOT / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
PROJECT_ROOT = DATASET_ROOT / "03_客户项目全过程库" / "东辰出行新能源车辆采购项目"


def load_json(relative_path: str) -> dict:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_dataset_declares_synthetic_nature_and_complete_stages() -> None:
    master = load_json("project_master.json")

    assert master["data_classification"] == "synthetic_demo"
    assert master["timeline_classification"] == "simulated_future_scenario"
    assert master["is_real_business_result"] is False
    assert "模拟" in master["disclaimer"]

    expected_stages = {
        "lead",
        "requirement",
        "clarification",
        "opportunity",
        "feasibility",
        "sourcing",
        "solution",
        "quote",
        "negotiation",
        "approval",
        "contract",
        "order",
        "purchase",
        "vehicle",
        "logistics",
        "delivery",
        "acceptance",
        "exception",
        "invoice",
        "cashflow",
        "profit",
        "after_sales",
        "repurchase",
        "review",
    }
    assert {stage["code"] for stage in master["lifecycle_stages"]} == expected_stages
    assert set(master["information_flows"]) == {
        "requirement_flow",
        "product_flow",
        "commercial_flow",
        "cash_flow",
        "information_flow",
    }


def test_requirement_baseline_drives_downstream_commercial_objects() -> None:
    requirement = load_json("01_客户与需求/customer_requirement.json")
    sourcing = load_json("03_商品与寻源/sourcing.json")
    commercial = load_json("04_方案商务/solution_commercial.json")
    contracts = load_json("05_合同订单/contracts_orders.json")

    versions = requirement["requirement"]["versions"]
    assert [version["version"] for version in versions] == ["V1", "V2", "V3"]
    baselines = [version for version in versions if version["confirmed_baseline"]]
    assert len(baselines) == 1
    baseline_id = baselines[0]["requirement_version_id"]
    assert baseline_id == "REQ-AUTO-001-V3"
    assert baselines[0]["quantity"] == 100

    selected_plan = next(
        plan for plan in sourcing["procurement_plans"] if plan["status"] == "approved"
    )
    accepted_quote = next(
        quote for quote in commercial["customer_quotes"] if quote["status"] == "accepted"
    )
    assert selected_plan["requirement_version_id"] == baseline_id
    assert accepted_quote["requirement_version_id"] == baseline_id
    assert contracts["sales_contract"]["requirement_version_id"] == baseline_id
    assert all(
        order["requirement_version_id"] == baseline_id
        for order in contracts["sales_orders"]
    )


def test_quantity_and_vehicle_traceability_are_conserved() -> None:
    sourcing = load_json("03_商品与寻源/sourcing.json")
    contracts = load_json("05_合同订单/contracts_orders.json")
    fulfillment = load_json("06_履约交付/fulfillment.json")

    approved_plan = next(
        plan for plan in sourcing["procurement_plans"] if plan["status"] == "approved"
    )
    planned_quantity = sum(allocation["quantity"] for allocation in approved_plan["allocations"])
    po_quantity = sum(order["quantity"] for order in contracts["purchase_orders"])
    sales_order_quantity = sum(order["quantity"] for order in contracts["sales_orders"])
    delivery_quantity = sum(batch["quantity"] for batch in fulfillment["delivery_batches"])
    accepted_quantity = sum(
        batch["accepted_quantity_final"] for batch in fulfillment["acceptances"]
    )
    vehicles = fulfillment["vehicles"]
    vins = [vehicle["vin"] for vehicle in vehicles]

    assert planned_quantity == po_quantity == sales_order_quantity == 100
    assert len(vehicles) == len(set(vins)) == delivery_quantity == accepted_quantity == 100

    purchase_order_ids = {order["purchase_order_id"] for order in contracts["purchase_orders"]}
    sales_order_ids = {order["sales_order_id"] for order in contracts["sales_orders"]}
    delivery_batch_ids = {batch["delivery_batch_id"] for batch in fulfillment["delivery_batches"]}
    supplier_ids = {supplier["supplier_id"] for supplier in sourcing["suppliers"]}

    for vehicle in vehicles:
        assert vehicle["purchase_order_id"] in purchase_order_ids
        assert vehicle["sales_order_id"] in sales_order_ids
        assert vehicle["delivery_batch_id"] in delivery_batch_ids
        assert vehicle["supplier_id"] in supplier_ids


def test_contract_invoice_cash_and_profit_reconcile() -> None:
    contracts = load_json("05_合同订单/contracts_orders.json")
    finance = load_json("07_财务利润/finance.json")

    sales_contract_amount = contracts["sales_contract"]["total_amount_cny"]
    purchase_contract_amount = sum(
        contract["total_amount_cny"] for contract in contracts["purchase_contracts"]
    )

    assert sales_contract_amount == sum(
        order["total_amount_cny"] for order in contracts["sales_orders"]
    )
    assert sales_contract_amount == sum(
        invoice["amount_cny"] for invoice in finance["customer_invoices"]
    )
    assert sales_contract_amount == sum(
        receipt["amount_cny"] for receipt in finance["customer_receipts"]
    )

    assert purchase_contract_amount == sum(
        order["total_amount_cny"] for order in contracts["purchase_orders"]
    )
    assert purchase_contract_amount == sum(
        invoice["amount_cny"] for invoice in finance["supplier_invoices"]
    )
    assert purchase_contract_amount == sum(
        payment["amount_cny"] for payment in finance["supplier_payments"]
    )

    profit = finance["profit_calculation"]
    calculated_profit = profit["sales_revenue_cny"] - sum(
        item["amount_cny"] for item in profit["cost_items"]
    )
    assert profit["project_profit_cny"] == calculated_profit
    assert profit["profit_margin"] == round(
        calculated_profit / profit["sales_revenue_cny"], 4
    )


def test_exceptions_and_after_sales_are_closed_and_traceable() -> None:
    fulfillment = load_json("06_履约交付/fulfillment.json")
    after_sales = load_json("08_售后复盘/after_sales_review.json")

    vehicle_vins = {vehicle["vin"] for vehicle in fulfillment["vehicles"]}
    exceptions = fulfillment["exceptions"]

    assert exceptions
    assert all(exception["status"] == "closed" for exception in exceptions)
    assert all(exception["reinspection"]["result"] == "passed" for exception in exceptions)
    assert {exception["vin"] for exception in exceptions} <= vehicle_vins

    tickets = after_sales["after_sales_tickets"]
    assert tickets
    assert all(ticket["vin"] in vehicle_vins for ticket in tickets)
    assert all(ticket["status"] == "closed" for ticket in tickets)
    assert after_sales["repurchase_lead"]["object_type"] == "lead"
    assert after_sales["repurchase_lead"]["is_confirmed_order"] is False


def test_demo_seed_indexes_both_demo_projects() -> None:
    seed = json.loads(
        (DATASET_ROOT / "06_DEMO数据" / "demo_seed.json").read_text(encoding="utf-8")
    )

    assert seed["data_classification"] == "synthetic_demo"
    project_ids = {project["project_id"] for project in seed["projects"]}
    assert {"PRJ-KM-001", "PRJ-AUTO-001"} <= project_ids


def test_rag_chunks_cover_lifecycle_and_keep_source_traceability() -> None:
    master = load_json("project_master.json")
    rag_path = DATASET_ROOT / "04_RAG知识库" / "customer_requirement_lifecycle_chunks.jsonl"
    chunks = [json.loads(line) for line in rag_path.read_text(encoding="utf-8").splitlines()]

    expected_stages = {stage["code"] for stage in master["lifecycle_stages"]}
    assert {chunk["lifecycle_stage"] for chunk in chunks} == expected_stages
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)

    for chunk in chunks:
        assert chunk["data_classification"] == "synthetic_demo"
        assert chunk["project_id"] == "PRJ-AUTO-001"
        assert chunk["requirement_id"] == "REQ-AUTO-001"
        assert chunk["requirement_version_id"]
        assert chunk["source_object_ids"]
        assert len(chunk["content"]) >= 30
