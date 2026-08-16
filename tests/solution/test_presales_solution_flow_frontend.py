"""PRESALES-M4 solution workflow visualization acceptance checks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PRESALES = FRONTEND / "src" / "presales"


def test_frontend_uses_vue_flow_for_solution_workflows() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    for dependency in (
        "@vue-flow/core",
        "@vue-flow/background",
        "@vue-flow/controls",
        "@vue-flow/minimap",
    ):
        assert dependency in package["dependencies"]


def test_solution_flow_component_is_interactive_but_read_only() -> None:
    graph = (PRESALES / "SolutionWorkflowGraph.vue").read_text(encoding="utf-8")

    required_components = ("<VueFlow", "<Background", "<Controls", "<MiniMap")
    assert all(component in graph for component in required_components)
    assert ':nodes-draggable="false"' in graph
    assert ':nodes-connectable="false"' in graph
    assert ':edges-updatable="false"' in graph
    assert "gateReason" in graph
    assert "humanGate" in graph
    assert "compact.value ? 'compact' : 'wide'" in graph
    assert "AI 执行" in graph
    assert "系统执行" in graph
    assert "人工执行" in graph


def test_solution_tab_selects_a_plan_and_renders_its_workflow() -> None:
    workbench = (PRESALES / "PresalesWorkbench.vue").read_text(encoding="utf-8")

    assert "import SolutionWorkflowGraph" in workbench
    assert "selectedFlowPlan" in workbench
    assert "<a-segmented" in workbench
    assert "<SolutionWorkflowGraph" in workbench
    assert "目标工作流" in workbench


def test_graph_mapper_preserves_real_workflow_order_and_gate_metadata() -> None:
    mapper = (PRESALES / "solutionWorkflowGraph.js").read_text(encoding="utf-8")

    assert "target_workflow" in mapper
    assert "workflow.length - 1" in mapper
    assert "source: `step-${index}`" in mapper
    assert "target: `step-${index + 1}`" in mapper
    assert "humanGate: step.human_gate" in mapper
    assert "gateReason: step.gate_reason" in mapper


def test_flow_canvas_has_stable_responsive_dimensions() -> None:
    styles = (PRESALES / "presales.css").read_text(encoding="utf-8")

    assert ".solution-flow-canvas" in styles
    assert "height: 520px" in styles
    assert "height: 440px" in styles
