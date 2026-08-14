"""DATA-M3 知识包适配器与现有合同/方案编译的端到端测试。"""

from __future__ import annotations

from pathlib import Path

from backend.app.contracts.requirement_intelligence import CustomerContextPackage, RequirementState
from backend.app.solution.knowledge_package_adapter import SmartProcurementKnowledgeAdapter


ROOT = Path(__file__).resolve().parents[2]
PROJECT = (
    ROOT
    / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
    / "03_客户项目全过程库"
    / "星瀚汽车动力电池智能招采项目"
)


def adapter() -> SmartProcurementKnowledgeAdapter:
    return SmartProcurementKnowledgeAdapter(PROJECT)


def test_adapter_builds_customer_context_and_validates_truth_evidence() -> None:
    service = adapter()
    context = service.load_customer_context(
        user_id="user-procurement-owner",
        as_of="2026-09-30T23:59:59+08:00",
    )
    state = service.load_requirement_truth(context)

    assert isinstance(context, CustomerContextPackage)
    assert isinstance(state, RequirementState)
    assert context.project_id == state.project_id == "PRJ-TENDER-001"
    assert len(context.sources) >= 20
    assert service.validate_truth_evidence(context, state) == []
    assert all(item.status == "confirmed" for item in state.items)
    assert all(item.confirmation_level == "customer" for item in state.items)


def test_adapter_enforces_as_of_without_leaking_future_requirement_versions() -> None:
    service = adapter()
    early_context = service.load_customer_context(
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )
    early_truth = service.load_requirement_truth(early_context)
    early = service.search(
        query="最终年需求量和交付日期",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )
    late = service.search(
        query="最终年需求量和交付日期",
        user_id="user-procurement-owner",
        as_of="2026-08-20T23:59:59+08:00",
    )

    assert "REQ-BAT-001-V3" not in {result["source_version"] for result in early}
    assert "REQ-BAT-001-V3" in {result["source_version"] for result in late}
    assert all(result["valid_from"] <= "2026-08-14T23:59:59+08:00" for result in early)
    assert all(
        ref.source_id in set(early_context.source_ids)
        for item in early_truth.items
        for ref in item.source_refs
    )
    assert not any(item.value == "2027-03-01进入SOP" for item in early_truth.items)


def test_adapter_applies_acl_masking_and_revocation() -> None:
    service = adapter()
    procurement = service.search(
        query="合同单价和供应商评分",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )
    observer = service.search(
        query="合同单价和供应商评分",
        user_id="user-observer",
        as_of="2026-10-30T23:59:59+08:00",
    )
    before_revoke = service.search(
        query="供应商质量整改",
        user_id="user-quality-temp",
        as_of="2026-09-14T12:00:00+08:00",
    )
    after_revoke = service.search(
        query="供应商质量整改",
        user_id="user-quality-temp",
        as_of="2026-09-16T12:00:00+08:00",
    )

    assert procurement
    assert any("unit_price_cny" not in result["masked_fields"] for result in procurement)
    assert observer
    assert all(
        {"unit_price_cny", "supplier_score"} <= set(result["masked_fields"])
        for result in observer
    )
    assert before_revoke
    assert after_revoke == []


def test_adapter_compiles_existing_process_and_solution_contracts_end_to_end() -> None:
    service = adapter()
    context = service.load_customer_context(
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )
    state = service.load_requirement_truth(context)
    process = service.build_process_spec(state)
    bundle = service.compile_solution_bundle(process)

    assert process.project_id == "PRJ-TENDER-001"
    assert process.industry == "汽车制造"
    assert process.department == "集团采购中心"
    assert len(process.as_is_nodes) == 9
    assert {node.name for node in process.as_is_nodes} >= {"采购预算", "采购立项", "供应商评审", "合同履约"}
    assert process.available_data
    assert {"SRM", "ERP", "OA", "合同管理平台"} <= set(process.existing_systems)
    assert process.constraints

    assert bundle.project_id == process.project_id
    assert len(bundle.plans) == 3
    assert {plan.plan_type for plan in bundle.plans} == {"conservative", "balanced", "innovative"}
    assert all(plan.selected_components for plan in bundle.plans)
    assert all(plan.warnings for plan in bundle.plans)
