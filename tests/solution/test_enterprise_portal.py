"""PORTAL-M1 unified enterprise knowledge service tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService


ROOT = Path(__file__).resolve().parents[2]


def service() -> EnterpriseKnowledgeService:
    return EnterpriseKnowledgeService(ROOT)


def test_project_registry_and_dashboard_are_computed_from_the_package() -> None:
    portal = service()
    projects = portal.list_projects()
    dashboard = portal.get_project_dashboard(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )

    assert {project["project_id"] for project in projects} == {
        "PRJ-KM-001",
        "PRJ-AUTO-001",
        "PRJ-TENDER-001",
    }
    assert all(project["portal_ready"] for project in projects)
    assert dashboard["project"]["project_id"] == "PRJ-TENDER-001"
    assert len(dashboard["procurement_stages"]) == 9
    assert dashboard["metrics"] == {
        "raw_evidence": 26,
        "requirement_truth_items": 52,
        "suppliers": 5,
        "document_review_samples": 10,
        "communications": 54,
        "rag_chunks": 27,
        "eval_cases": 36,
        "adversarial_scenarios": 4,
    }
    assert dashboard["data_classification"] == "synthetic_demo"
    assert dashboard["is_real_business_result"] is False


def test_all_three_projects_have_browseable_data_views() -> None:
    portal = service()
    knowledge = portal.get_project_dashboard(
        "PRJ-KM-001",
        user_id="user-procurement-owner",
        as_of="2027-02-10T23:59:59+08:00",
    )
    vehicles = portal.get_project_dashboard(
        "PRJ-AUTO-001",
        user_id="user-procurement-owner",
        as_of="2026-11-01T23:59:59+08:00",
    )

    assert knowledge["project"]["project_id"] == "PRJ-KM-001"
    assert knowledge["metrics"]["requirements"] == 3
    assert knowledge["metrics"]["meetings"] == 12
    assert knowledge["metrics"]["documents"] == 8
    assert vehicles["project"]["project_id"] == "PRJ-AUTO-001"
    assert vehicles["metrics"]["vehicles"] == 100
    assert vehicles["metrics"]["delivery_batches"] == 3
    assert vehicles["metrics"]["customer_invoices"] == 3


def test_other_project_dashboards_do_not_leak_future_objects() -> None:
    portal = service()
    knowledge = portal.get_project_dashboard(
        "PRJ-KM-001",
        user_id="user-procurement-owner",
        as_of="2026-08-20T23:59:59+08:00",
    )
    vehicles = portal.get_project_dashboard(
        "PRJ-AUTO-001",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )

    assert knowledge["metrics"] == {
        "requirements": 3,
        "meetings": 1,
        "documents": 2,
        "wechat_threads": 1,
        "communication_timeline": 2,
    }
    assert [item["requirement_id"] for item in knowledge["requirements"]] == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
    ]
    assert [item["requirement_version_id"] for item in knowledge["requirements"][0]["versions"]] == [
        "REQ-001-V1"
    ]

    assert vehicles["requirement_history"]["applicable_version_id"] == "REQ-AUTO-001-V2"
    assert [item["requirement_version_id"] for item in vehicles["requirement_history"]["versions"]] == [
        "REQ-AUTO-001-V1",
        "REQ-AUTO-001-V2",
    ]
    assert vehicles["metrics"]["vehicles"] == 0
    assert vehicles["metrics"]["delivery_batches"] == 0
    assert vehicles["metrics"]["customer_invoices"] == 0
    assert vehicles["vehicles"] == []
    assert vehicles["finance"] is None
    visible_stage_codes = {
        stage["code"]
        for stage in vehicles["procurement_stages"]
        if stage["status"] != "not_recorded_as_of"
    }
    assert visible_stage_codes == {"lead", "requirement"}


def test_vehicle_dashboard_projects_intermediate_status_and_finance_as_of() -> None:
    portal = service()
    loaded = portal.get_project_dashboard(
        "PRJ-AUTO-001",
        user_id="user-procurement-owner",
        as_of="2026-09-06T08:30:00+08:00",
    )
    first_batch = portal.get_project_dashboard(
        "PRJ-AUTO-001",
        user_id="user-procurement-owner",
        as_of="2026-09-08T23:59:59+08:00",
    )

    assert loaded["shipments"][0]["status"] == "loaded_as_of"
    assert loaded["shipments"][0]["departed_at"] is None
    assert loaded["shipments"][0]["arrived_at"] is None
    assert loaded["metrics"]["vehicles"] == 60
    assert all(
        vehicle["vehicle_status"] == "released_pending_delivery_as_of"
        for vehicle in loaded["vehicles"]
    )

    assert first_batch["metrics"]["vehicles"] == 60
    assert sum(
        vehicle["vehicle_status"] == "released_pending_delivery_as_of"
        for vehicle in first_batch["vehicles"]
    ) == 30
    assert first_batch["metrics"]["delivery_batches"] == 1
    assert first_batch["metrics"]["acceptances"] == 1
    assert first_batch["metrics"]["exceptions"] == 1
    assert first_batch["exceptions"][0]["status"] == "open_as_of"
    assert first_batch["exceptions"][0]["resolved_at"] is None
    assert first_batch["acceptances"][0]["accepted_quantity_final"] == 29
    assert first_batch["acceptances"][0]["final_result"] == "pending_reinspection_as_of"
    damaged = next(
        vehicle
        for vehicle in first_batch["vehicles"]
        if vehicle["vin"] == "LDCFAKE0000000007"
    )
    assert damaged["vehicle_status"] == "exception_open_as_of"
    assert first_batch["finance"]["profit_calculation"] is None
    assert [item["receivable_id"] for item in first_batch["finance"]["customer_receivables"]] == [
        "AR-AUTO-001",
        "AR-AUTO-002",
    ]
    assert first_batch["finance"]["customer_receivables"][1]["status"] == "not_due_as_of"
    assert first_batch["finance"]["supplier_payables"][0]["status"] == "partially_paid_as_of"


def test_dashboard_and_search_apply_temporal_acl_and_masking() -> None:
    portal = service()
    early = portal.search_knowledge(
        "PRJ-TENDER-001",
        query="最终年需求量和交付日期",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )
    observer = portal.search_knowledge(
        "PRJ-TENDER-001",
        query="合同单价和供应商评分",
        user_id="user-observer",
        as_of="2026-10-30T23:59:59+08:00",
    )
    revoked = portal.search_knowledge(
        "PRJ-TENDER-001",
        query="供应商质量整改",
        user_id="user-quality-temp",
        as_of="2026-09-16T12:00:00+08:00",
    )

    assert early["results"]
    assert "REQ-BAT-001-V3" not in {
        result["source_version"] for result in early["results"]
    }
    assert observer["results"]
    assert all(
        {"unit_price_cny", "supplier_score"} <= set(result["masked_fields"])
        for result in observer["results"]
    )
    assert revoked["results"] == []
    assert revoked["permission_decision"] == "revoked"


def test_requirement_supplier_review_and_solution_views_are_executable() -> None:
    portal = service()
    history = portal.get_requirement_history(
        "PRJ-TENDER-001",
        "REQ-BAT-001",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )
    suppliers = portal.analyze_suppliers(
        "PRJ-TENDER-001",
        user_id="user-quality",
        as_of="2026-09-30T23:59:59+08:00",
    )
    reviews = portal.get_document_reviews(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )
    bundle = portal.generate_solution_bundle(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )

    assert [version["requirement_version_id"] for version in history["versions"]] == [
        "REQ-BAT-001-V1",
        "REQ-BAT-001-V2",
    ]
    assert len(suppliers["suppliers"]) == 5
    assert {risk["type"] for supplier in suppliers["suppliers"] for risk in supplier["risk_records"]} >= {
        "expired_certificate",
        "litigation",
        "quality",
        "delivery",
        "credit",
    }
    assert reviews["summary"] == {"control": 4, "defective": 6, "findings": 10}
    assert {plan["plan_type"] for plan in bundle["plans"]} == {
        "conservative",
        "balanced",
        "innovative",
    }
    assert all(plan["warnings"] for plan in bundle["plans"])

    supplier_three = portal.analyze_suppliers(
        "PRJ-TENDER-001",
        user_id="user-quality",
        as_of="2026-09-30T23:59:59+08:00",
        supplier_id="SUP-BAT-003",
    )
    assert [supplier["supplier_id"] for supplier in supplier_three["suppliers"]] == [
        "SUP-BAT-003"
    ]


def test_observer_supplier_view_hides_scores_and_prices() -> None:
    result = service().analyze_suppliers(
        "PRJ-TENDER-001",
        user_id="user-observer",
        as_of="2026-10-30T23:59:59+08:00",
    )

    assert result["suppliers"]
    assert all("score_detail" not in supplier for supplier in result["suppliers"])
    assert all("historical_quotes" not in supplier for supplier in result["suppliers"])
    assert {"supplier_score", "unit_price_cny"} <= set(result["masked_fields"])

    dashboard = service().get_project_dashboard(
        "PRJ-TENDER-001",
        user_id="user-observer",
        as_of="2026-10-30T23:59:59+08:00",
    )
    assert dashboard["solution_bundle"] is None
    assert dashboard["solution_status"]["status"] == "forbidden_for_role"
    assert {"supplier_score", "unit_price_cny"} <= set(
        dashboard["viewer"]["masked_fields"]
    )


def test_historical_dashboard_stays_readable_before_formal_solution_readiness() -> None:
    dashboard = service().get_project_dashboard(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )

    assert dashboard["requirement_history"]["applicable_version_id"] == "REQ-BAT-001-V2"
    assert dashboard["project"]["confirmed_requirement_version_id"] == "REQ-BAT-001-V2"
    assert "REQ-BAT-001-V3" not in {
        version["requirement_version_id"]
        for version in dashboard["requirement_history"]["versions"]
    }
    assert dashboard["solution_bundle"] is None
    assert dashboard["solution_status"]["status"] == "not_ready_as_of"
    assert all(
        stage["status"] == "not_recorded_as_of"
        for stage in dashboard["procurement_stages"]
    )
    assert dashboard["document_reviews"]["samples"] == []
    assert dashboard["metrics"]["document_review_samples"] == 0
    assert dashboard["open_items"] == []
    assert dashboard["requirement_history"]["open_items"] == []

    v1_dashboard = service().get_project_dashboard(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-08-12T23:59:59+08:00",
    )
    assert v1_dashboard["project"]["annual_quantity"] == 10000
    assert v1_dashboard["project"]["confirmed_requirement_version_id"] == "REQ-BAT-001-V1"
    assert "12,000" not in v1_dashboard["project"]["procurement_object"]


def test_financial_reconciliation_does_not_leak_future_snapshot() -> None:
    portal = service()
    historical = portal.get_financial_reconciliation(
        "PRJ-TENDER-001",
        contract_id="CON-BAT-001",
        user_id="user-procurement-owner",
        as_of="2026-10-30T23:59:59+08:00",
    )
    mature = portal.get_financial_reconciliation(
        "PRJ-TENDER-001",
        contract_id="CON-BAT-001",
        user_id="user-procurement-owner",
        as_of="2027-04-15T23:59:59+08:00",
    )

    assert historical["reconciliation"]["project_financial_summary"] is None
    assert historical["reconciliation"]["financial_summary_status"] == "not_recorded_as_of"
    assert mature["reconciliation"]["project_financial_summary"]["as_of"] == (
        "2027-04-15T23:59:59+08:00"
    )
    assert mature["reconciliation"]["financial_summary_status"] == "recorded_as_of"


def test_extended_tools_enforce_source_acl_recording_and_revocation() -> None:
    portal = service()
    owner = portal.get_decision_history(
        "PRJ-TENDER-001",
        decision_or_object_id="SUP-BAT-003",
        user_id="user-procurement-owner",
        as_of="2026-09-30T23:59:59+08:00",
    )
    observer = portal.get_decision_history(
        "PRJ-TENDER-001",
        decision_or_object_id="SUP-BAT-003",
        user_id="user-observer",
        as_of="2026-09-30T23:59:59+08:00",
    )
    legal = portal.search_communication(
        "PRJ-TENDER-001",
        query="证书过期",
        user_id="user-legal-finance",
        as_of="2026-09-30T23:59:59+08:00",
    )
    revoked = portal.get_decision_history(
        "PRJ-TENDER-001",
        decision_or_object_id="SUP-BAT-003",
        user_id="user-quality-temp",
        as_of="2026-09-16T12:00:00+08:00",
    )

    assert len(owner["timeline"]) == 3
    assert owner["evidence"] == ["SRC-TENDER-019", "SRC-TENDER-021"]
    assert observer["timeline"] == []
    assert observer["permission_filtered_count"] == 3
    assert legal["records"] == []
    assert legal["permission_filtered_count"] >= 1
    assert revoked["timeline"] == []
    assert revoked["permission_decision"] == "revoked"


def test_supplier_projection_does_not_include_future_quotes_or_sources() -> None:
    result = service().analyze_suppliers(
        "PRJ-TENDER-001",
        user_id="user-procurement-owner",
        as_of="2026-09-30T23:59:59+08:00",
        supplier_id="SUP-BAT-001",
    )

    supplier = result["suppliers"][0]
    assert "SRC-TENDER-022" not in supplier["source_ids"]
    assert [quote["quote_id"] for quote in supplier["historical_quotes"]] == [
        "SQ-001-V1"
    ]


def test_document_review_and_object_trace_honor_time_and_acl() -> None:
    portal = service()

    try:
        portal.review_tender_document(
            "PRJ-TENDER-001",
            document_id="DEFECT-01",
            user_id="user-procurement-owner",
            as_of="2026-09-01T23:59:59+08:00",
        )
    except ValueError as error:
        assert "not recorded" in str(error)
    else:
        raise AssertionError("future review sample should not be readable")

    early_trace = portal.trace_business_object(
        "PRJ-TENDER-001",
        object_id="CON-BAT-001",
        user_id="user-procurement-owner",
        as_of="2026-10-19T23:59:59+08:00",
    )
    observer_trace = portal.trace_business_object(
        "PRJ-TENDER-001",
        object_id="CON-BAT-001",
        user_id="user-observer",
        as_of="2026-10-30T23:59:59+08:00",
    )

    assert early_trace["nodes"] == []
    assert early_trace["warnings"] == ["object not recorded as-of query time: CON-BAT-001"]
    assert observer_trace["nodes"] == []
    assert observer_trace["permission_decision"] == "forbidden"

    requirement_trace = portal.trace_business_object(
        "PRJ-TENDER-001",
        object_id="REQ-BAT-001",
        user_id="user-procurement-owner",
        as_of="2026-08-14T23:59:59+08:00",
    )
    node_ids = {node["id"] for node in requirement_trace["nodes"]}
    assert "REQ-BAT-001-V1" in node_ids
    assert "REQ-BAT-001-V2" in node_ids
    assert "REQ-BAT-001-V3" not in node_ids
    assert "TENDER-BAT-001" not in node_ids


def test_revoked_user_cannot_read_document_review_tool() -> None:
    try:
        service().get_document_reviews(
            "PRJ-TENDER-001",
            user_id="user-quality-temp",
            as_of="2026-09-30T23:59:59+08:00",
        )
    except PermissionError as error:
        assert "revoked" in str(error)
    else:
        raise AssertionError("revoked user should not read review data")

    try:
        service().get_project_dashboard(
            "PRJ-AUTO-001",
            user_id="user-quality-temp",
            as_of="2026-09-16T12:00:00+08:00",
        )
    except PermissionError as error:
        assert "revoked" in str(error)
    else:
        raise AssertionError("revoked user should not browse another project")
