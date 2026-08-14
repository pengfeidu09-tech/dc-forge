"""DATA-M3 智能招采黄金验收集的数据完整性与机器可判分测试。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
PROJECT = PACKAGE / "03_客户项目全过程库" / "星瀚汽车动力电池智能招采项目"


def load_json(relative: str) -> dict | list:
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


def load_jsonl(relative: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (PROJECT / relative).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_project_aligns_with_ppt_procurement_chain_and_demo_index() -> None:
    master = load_json("project_master.json")
    expected = [
        "procurement_budget",
        "procurement_plan",
        "project_initiation",
        "procurement_scheme",
        "procurement_execution",
        "procurement_contract",
        "document_archive",
        "supplier_management",
        "statistics_analysis",
    ]
    assert master["project_id"] == "PRJ-TENDER-001"
    assert master["data_classification"] == "synthetic_demo"
    assert master["timeline_classification"] == "simulated_future_scenario"
    assert [stage["code"] for stage in master["procurement_stages"]] == expected
    assert {
        "document_generation",
        "document_review",
        "policy_qa",
        "supplier_portrait",
    } <= set(master["ai_acceptance_capabilities"])

    seed = json.loads(
        (PACKAGE / "06_DEMO数据" / "demo_seed.json").read_text(encoding="utf-8")
    )
    assert "PRJ-TENDER-001" in {project["project_id"] for project in seed["projects"]}


def test_raw_evidence_truth_and_rag_form_three_layer_closure() -> None:
    manifest = load_json("00_原始证据/source_manifest.json")
    truth = load_json("02_采购立项与需求/requirement_truth.json")
    chunks = load_jsonl("10_RAG/golden_chunks.jsonl")

    sources = manifest["sources"]
    assert 20 <= len(sources) <= 30
    source_by_id = {source["source_id"]: source for source in sources}
    assert len(source_by_id) == len(sources)
    for source in sources:
        path = PROJECT / source["source_path"]
        assert path.exists(), source["source_id"]
        assert len(path.read_text(encoding="utf-8")) >= 200
        assert source["security_label"]
        assert source["acl_id"]
        assert source["occurred_at"] and source["recorded_at"]
        assert source["valid_from"] and source["source_version"]

    for item in truth["items"]:
        for ref in item["source_refs"]:
            source = source_by_id[ref["source_id"]]
            source_text = (PROJECT / source["source_path"]).read_text(encoding="utf-8")
            assert ref["excerpt"] in source_text

    assert len(chunks) >= len(sources)
    for chunk in chunks:
        assert chunk["source_id"] in source_by_id
        assert chunk["source_path"] == source_by_id[chunk["source_id"]]["source_path"]
        assert chunk["occurred_at"] and chunk["recorded_at"]
        assert chunk["valid_from"] and chunk["source_version"]
        assert chunk["security_label"] and chunk["acl_id"]


def test_supplier_portraits_support_time_factory_category_and_risk_analysis() -> None:
    data = load_json("03_供应商画像/supplier_profiles.json")
    suppliers = data["suppliers"]
    assert len(suppliers) == 5
    assert len(data["evaluation_weights"]) >= 6
    assert sum(item["weight"] for item in data["evaluation_weights"]) == 1.0

    risk_types = set()
    for supplier in suppliers:
        assert supplier["certificates"]
        assert all(cert["valid_from"] and cert["valid_to"] for cert in supplier["certificates"])
        assert len(supplier["performance_records"]) >= 2
        assert {record["factory"] for record in supplier["performance_records"]}
        assert {record["category"] for record in supplier["performance_records"]}
        assert supplier["historical_quotes"]
        assert supplier["financial_credit"]
        assert "missing_value_handling" in supplier["score_detail"]
        assert "manual_adjustments" in supplier["score_detail"]
        risk_types.update(risk["type"] for risk in supplier["risk_records"])

    assert {"expired_certificate", "litigation", "quality", "delivery", "credit"} <= risk_types


def test_document_review_has_controls_defects_rules_and_human_outcomes() -> None:
    rules = load_json("05_文档生成与审查/rule_sets.json")
    expectations = load_json("05_文档生成与审查/review_expectations.json")

    assert rules["rule_set_id"] == "RULESET-TENDER-002"
    assert len(rules["rules"]) >= 10
    rule_ids = {rule["rule_id"] for rule in rules["rules"]}

    samples = expectations["samples"]
    assert len(samples) == 10
    assert len([sample for sample in samples if sample["sample_type"] == "control"]) == 4
    assert len([sample for sample in samples if sample["sample_type"] == "defective"]) == 6
    for sample in samples:
        path = PROJECT / sample["source_path"]
        assert path.exists()
        assert len(path.read_text(encoding="utf-8")) >= 500
        for finding in sample["expected_findings"]:
            assert finding["rule_id"] in rule_ids
            assert finding["locator"]
            assert finding["severity"] in {"low", "medium", "high", "critical"}
            assert finding["human_outcome"] in {"confirmed", "rejected", "risk_adjusted"}

    assert any(
        finding["issue_type"] == "cross_document_inconsistency"
        for sample in samples
        for finding in sample["expected_findings"]
    )


def test_acl_revocation_and_temporal_fields_are_executable() -> None:
    security = load_json("08_权限与时间/security_model.json")
    chunks = load_jsonl("10_RAG/golden_chunks.jsonl")

    assert len(security["roles"]) >= 4
    assert len(security["users"]) >= 4
    assert security["acls"]
    assert security["revocation_events"]
    event = security["revocation_events"][0]
    assert event["effective_at"]
    assert event["old_permission_version"] != event["new_permission_version"]
    assert event["affected_source_ids"]
    assert event["verification_status"] == "passed_simulation"

    for chunk in chunks:
        for field in (
            "occurred_at",
            "recorded_at",
            "valid_from",
            "valid_to",
            "supersedes",
            "source_version",
            "security_label",
            "acl_id",
            "allowed_roles",
            "allowed_departments",
            "field_masking",
            "permission_version",
        ):
            assert field in chunk


def test_communications_and_machine_gradable_eval_cases_cover_failure_modes() -> None:
    communications = load_jsonl("09_沟通记录/communications.jsonl")
    eval_cases = load_jsonl("11_评测集/eval_cases.jsonl")

    assert len(communications) >= 50
    assert len({record["communication_id"] for record in communications}) == len(communications)
    assert len({record["content"] for record in communications}) == len(communications)
    assert all(record["context_before"] and record["content"] and record["related"] for record in communications)

    assert 30 <= len(eval_cases) <= 50
    required_fields = {
        "case_id",
        "query",
        "project_id",
        "user_context",
        "as_of",
        "expected_facts",
        "expected_source_ids",
        "forbidden_claims",
        "expected_refusal",
        "expected_masked_fields",
        "grading_rules",
    }
    assert all(required_fields <= set(case) for case in eval_cases)
    categories = {case["category"] for case in eval_cases}
    assert {
        "fact",
        "causal_trace",
        "version_as_of",
        "insufficient_evidence",
        "permission_refusal",
        "field_masking",
        "document_review",
        "supplier_analysis",
        "adversarial_detection",
    } <= categories
    assert any(case["expected_refusal"] for case in eval_cases)
    assert any(case["forbidden_claims"] for case in eval_cases)


def test_adversarial_variants_are_isolated_and_have_expected_findings() -> None:
    variants = sorted((PROJECT / "adversarial").glob("*/scenario.json"))
    assert len(variants) == 4
    finding_types = set()
    for path in variants:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        assert scenario["data_classification"] == "synthetic_adversarial"
        assert scenario["base_project_id"] == "PRJ-TENDER-001"
        assert scenario["isolated_from_golden"] is True
        assert scenario["expected_findings"]
        finding_types.update(finding["type"] for finding in scenario["expected_findings"])
    assert {
        "requirement_conflict",
        "expired_quote",
        "expired_certificate",
        "approval_rejected",
        "contract_amount_mismatch",
        "duplicate_vin",
    } <= finding_types
