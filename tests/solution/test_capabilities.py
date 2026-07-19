"""B-M1 能力胶囊模型与数据校验测试。"""

import json
from pathlib import Path

import pytest

from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES_PATH = ROOT / "data" / "capabilities.json"

REQUIRED_DEMO_COMPONENTS = [
    "document-extraction",
    "enterprise-rag",
    "field-completeness-check",
    "rule-engine",
    "anomaly-classification",
    "risk-scoring",
    "local-model",
    "data-masking",
    "human-approval",
    "ticket-routing",
    "feishu-notification",
    "audit-log",
    "quality-dashboard",
    "process-monitoring",
    "feedback-loop",
]


def _load_raw() -> list[dict]:
    return json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))


def test_capabilities_file_contains_15_items() -> None:
    """data/capabilities.json 必须包含恰好 15 个能力胶囊。"""
    data = _load_raw()
    assert isinstance(data, list), "根节点必须是数组"
    assert len(data) == 15, f"期望 15 个胶囊，实际 {len(data)}"


def test_capability_ids_are_unique() -> None:
    """所有 component_id 必须唯一。"""
    data = _load_raw()
    ids = [item["component_id"] for item in data]
    assert len(ids) == len(set(ids)), f"存在重复 component_id: {ids}"


def test_capabilities_validate_against_model() -> None:
    """每项必须能通过 CapabilityCapsule Pydantic 校验。"""
    data = _load_raw()
    for item in data:
        CapabilityCapsule.model_validate(item)


def test_required_demo_components_exist() -> None:
    """必须包含全部 15 个 required_demo_components。"""
    data = _load_raw()
    ids = {item["component_id"] for item in data}
    missing = set(REQUIRED_DEMO_COMPONENTS) - ids
    assert not missing, f"缺少 component_id: {missing}"


def test_capability_rejects_extra_fields() -> None:
    """CapabilityCapsule 必须拒绝合同外字段 (extra=forbid)。"""
    base = {
        "component_id": "test-extra",
        "name": "测试",
        "description": "测试描述",
        "problem_tags": ["test"],
        "applicable_industries": ["test"],
        "applicable_departments": ["test"],
        "required_data": ["test"],
        "supported_constraint_types": ["test"],
        "forbidden_conditions": [],
        "human_fallback": "人工处理",
        "executor_type": "ai",
        "evidence_urls": [],
        "evaluation_metrics": ["test"],
    }
    base["unexpected_field"] = "should_fail"
    with pytest.raises(Exception):
        CapabilityCapsule.model_validate(base)
