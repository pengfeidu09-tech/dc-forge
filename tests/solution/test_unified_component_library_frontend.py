"""PORTAL-M7 unified Ant Design Vue page acceptance checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"


def test_root_portal_installs_ant_design_vue_and_uses_enterprise_components() -> None:
    main = (SRC / "main.js").read_text(encoding="utf-8")
    app = (SRC / "App.vue").read_text(encoding="utf-8")

    assert "import Antd from 'ant-design-vue'" in main
    assert "ant-design-vue/dist/reset.css" in main
    assert ".use(Antd)" in main
    required = (
        "<a-layout",
        "<a-menu",
        "<a-alert",
        "<a-list",
        "<a-tag",
    )
    assert all(component in app for component in required)


def test_intelligence_console_uses_the_same_component_system() -> None:
    console = (SRC / "components/IntelligenceConsole.vue").read_text(encoding="utf-8")

    required = (
        "<a-card",
        "<a-button",
        "<a-input",
        "<a-textarea",
        "<a-segmented",
        "<a-alert",
        "<a-drawer",
    )
    assert all(component in console for component in required)
    assert "<table" not in console
    assert "<select" not in console
    assert "<button" not in console
    assert "<input" not in console


def test_root_tool_shell_uses_ant_design_navigation_controls() -> None:
    shell = (SRC / "App.vue").read_text(encoding="utf-8")

    required = ("<a-layout-sider", "<a-menu", "<a-list", "<a-tag")
    assert all(component in shell for component in required)
    assert "<button" not in shell
    assert "<input" not in shell
    assert not (SRC / "components/AppSidebar.vue").exists()


def test_customer_center_is_a_vite_ant_design_vue_page() -> None:
    vite = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")
    entry = (FRONTEND / "customer/engagement/index.html").read_text(encoding="utf-8")
    main = (SRC / "customer/main.js").read_text(encoding="utf-8")
    component = (SRC / "customer/CustomerEngagementCenter.vue").read_text(
        encoding="utf-8"
    )

    assert "customer/engagement/index.html" in vite
    assert "/src/customer/main.js" in entry
    assert "ant-design-vue" in main
    required = (
        "<a-layout",
        "<a-card",
        "<a-checkbox",
        "<a-radio",
        "<a-textarea",
        "<a-collapse",
        "<a-result",
    )
    assert all(item in component for item in required)
    assert "prompt(" not in component
    assert "alert(" not in component
    assert "innerHTML" not in component


def test_backend_customer_page_is_only_a_built_frontend_boundary() -> None:
    source = (
        ROOT / "backend/app/solution/customer_engagement_pages.py"
    ).read_text(encoding="utf-8")
    customer_source = source.split("def customer_center_html", maxsplit=1)[1]

    assert '"customer" / "engagement" / "index.html"' in customer_source
    assert "_build_fallback" in customer_source
    assert "前端资源尚未构建" in source
    assert "async function load" not in customer_source
    assert "confirmRequirements()" not in customer_source


def test_legacy_demo_visual_components_are_removed() -> None:
    obsolete = {
        "ScoreRing.vue",
        "WorkflowMap.vue",
        "CapabilityGrid.vue",
        "DetailPanel.vue",
        "DataImportModal.vue",
        "PlanCard.vue",
        "MetricTile.vue",
    }
    assert all(not (SRC / "components" / filename).exists() for filename in obsolete)
    assert (SRC / "presales/SolutionWorkflowGraph.vue").is_file()
