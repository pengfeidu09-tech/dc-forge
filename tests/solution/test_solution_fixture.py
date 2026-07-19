"""B-M2 solution_bundle.json fixture 校验测试。"""

import json
from pathlib import Path

from backend.app.contracts.solution import SolutionBundle
from backend.app.solution.capabilities import load_capabilities

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_bundle() -> dict:
    return json.loads((FIXTURES / "solution_bundle.json").read_text(encoding="utf-8"))


def _load_process_project_id() -> str:
    data = json.loads((FIXTURES / "process_spec.json").read_text(encoding="utf-8"))
    return data["project_id"]


def test_solution_fixture_contains_three_plans() -> None:
    """fixture 包含恰好 3 套方案。"""
    data = _load_bundle()
    assert len(data["plans"]) == 3, f"期望 3 套方案，实际 {len(data['plans'])}"


def test_solution_fixture_contains_all_plan_types() -> None:
    """fixture 包含 conservative、balanced、innovative 三种 plan_type。"""
    data = _load_bundle()
    types = {p["plan_type"] for p in data["plans"]}
    assert types == {"conservative", "balanced", "innovative"}


def test_solution_fixture_validates_against_contract() -> None:
    """fixture 通过 SolutionBundle 公共合同校验。"""
    data = _load_bundle()
    SolutionBundle.model_validate(data)


def test_solution_fixture_project_matches_process_fixture() -> None:
    """fixture 的 project_id 与 process_spec.json 一致。"""
    data = _load_bundle()
    assert data["project_id"] == _load_process_project_id()


def test_solution_fixture_component_ids_exist_in_catalog() -> None:
    """fixture 中所有 component_id 都存在于能力胶囊库。"""
    data = _load_bundle()
    capabilities = load_capabilities()
    known_ids = {cap.component_id for cap in capabilities}
    for plan in data["plans"]:
        for comp in plan["selected_components"]:
            assert comp["component_id"] in known_ids, (
                f"未知 component_id: {comp['component_id']}"
            )


def test_solution_fixture_has_no_dangling_workflow_edges() -> None:
    """fixture 中不存在悬空 next_id。"""
    data = _load_bundle()
    for plan in data["plans"]:
        node_ids = {n["id"] for n in plan["to_be_nodes"]}
        for node in plan["to_be_nodes"]:
            for next_id in node["next_ids"]:
                assert next_id in node_ids, (
                    f"{plan['plan_type']} 节点 {node['id']} 的 next_id {next_id} 悬空"
                )
