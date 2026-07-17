"""B-M4 重编译 Demo fixture 测试。"""

import json
from pathlib import Path

from backend.app.contracts.solution import RecompileRequest, RecompileResult
from backend.app.solution import recompile_solution

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_request() -> dict:
    return json.loads((FIXTURES / "recompile_request.json").read_text(encoding="utf-8"))


def _load_result() -> dict:
    return json.loads((FIXTURES / "recompile_result.json").read_text(encoding="utf-8"))


def test_recompile_request_validates_against_contract() -> None:
    RecompileRequest.model_validate(_load_request())


def test_recompile_result_validates_against_contract() -> None:
    RecompileResult.model_validate(_load_result())


def test_fixture_preserves_balanced_strategy() -> None:
    result = _load_result()
    assert result["new_solution"]["plan_type"] == "balanced"


def test_fixture_increments_version() -> None:
    request = _load_request()
    result = _load_result()
    old_id = request["selected_solution"]["solution_id"]
    new_id = result["new_solution"]["solution_id"]
    assert new_id != old_id
    assert "v2" in new_id


def test_fixture_adds_local_model() -> None:
    result = _load_result()
    comp_ids = {c["component_id"] for c in result["new_solution"]["selected_components"]}
    assert "local-model" in comp_ids


def test_fixture_adds_data_masking() -> None:
    result = _load_result()
    comp_ids = {c["component_id"] for c in result["new_solution"]["selected_components"]}
    assert "data-masking" in comp_ids


def test_fixture_keeps_audit_log() -> None:
    result = _load_result()
    comp_ids = {c["component_id"] for c in result["new_solution"]["selected_components"]}
    assert "audit-log" in comp_ids


def test_fixture_has_component_diff() -> None:
    result = _load_result()
    assert len(result["added_component_ids"]) > 0


def test_fixture_has_node_diff() -> None:
    result = _load_result()
    assert len(result["changed_node_ids"]) > 0


def test_fixture_has_change_explanations() -> None:
    result = _load_result()
    assert len(result["change_explanations"]) > 0


def test_fixture_has_no_dangling_edges() -> None:
    result = _load_result()
    node_ids = {n["id"] for n in result["new_solution"]["to_be_nodes"]}
    for node in result["new_solution"]["to_be_nodes"]:
        for nid in node["next_ids"]:
            assert nid in node_ids, f"悬空 next_id: {nid}"


def test_fixture_is_deterministically_regenerable() -> None:
    request = RecompileRequest.model_validate(_load_request())
    regenerated = recompile_solution(request)
    fixture = _load_result()
    assert regenerated.model_dump(mode="json") == fixture
