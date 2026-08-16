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
        "<a-card",
        "<a-statistic",
        "<a-table",
        "<a-result",
        "<a-input-search",
        "<a-segmented",
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


def test_legacy_sidebar_uses_ant_design_navigation_controls() -> None:
    sidebar = (SRC / "components/AppSidebar.vue").read_text(encoding="utf-8")

    required = ("<a-layout-sider", "<a-menu", "<a-input-search", "<a-list", "<a-button")
    assert all(component in sidebar for component in required)
    assert "<button" not in sidebar
    assert "<input" not in sidebar


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


def test_shared_visual_components_use_ant_design_vue_primitives() -> None:
    expected = {
        "ScoreRing.vue": "<a-progress",
        "WorkflowMap.vue": "<a-steps",
        "CapabilityGrid.vue": "<a-card",
        "DetailPanel.vue": "<a-alert",
        "DataImportModal.vue": "<a-modal",
        "PlanCard.vue": "<a-card",
        "MetricTile.vue": "<a-statistic",
    }
    for filename, component in expected.items():
        source = (SRC / f"components/{filename}").read_text(encoding="utf-8")
        assert component in source, filename
