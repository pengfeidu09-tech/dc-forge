"""PRESALES-M3 Ant Design Vue workbench acceptance checks."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.solution.customer_engagement_pages import presales_workbench_html


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PRESALES = FRONTEND / "src" / "presales"


def test_presales_workbench_is_an_ant_design_vue_entry_in_main_frontend() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    vite = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")
    entry = (FRONTEND / "presales/workbench/index.html").read_text(encoding="utf-8")

    assert "ant-design-vue" in package["dependencies"]
    assert "@ant-design/icons-vue" in package["dependencies"]
    assert "presales/workbench/index.html" in vite
    assert "/src/presales/main.js" in entry
    assert "统一售前工作台" in entry


def test_workbench_uses_operational_information_architecture() -> None:
    component = (PRESALES / "PresalesWorkbench.vue").read_text(encoding="utf-8")

    required_components = (
        "<a-layout",
        "<a-menu",
        "<a-steps",
        "<a-tabs",
        "<a-table",
        "<a-timeline",
        "<a-modal",
        "<a-form",
    )
    required_views = (
        "项目总览",
        "资料与研究",
        "方案编排",
        "评审发布",
        "阻断缺口",
        "打开客户中心",
    )

    assert all(item in component for item in required_components)
    assert all(item in component for item in required_views)


def test_workbench_replaces_browser_prompts_with_structured_vue_actions() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PRESALES.glob("*"))
    )

    assert "prompt(" not in source
    assert "alert(" not in source
    assert "innerHTML" not in source
    assert "Modal.confirm" in source
    assert "message.success" in source


def test_presales_api_client_preserves_existing_business_operations() -> None:
    api = (PRESALES / "api.js").read_text(encoding="utf-8")

    required_paths = (
        "/presales/projects",
        "/sources",
        "/research",
        "/drafts",
        "/deliverable",
        "/reviews",
        "/publish",
    )
    assert all(path in api for path in required_paths)
    assert "X-DCForge-Internal-Token" in api


def test_backend_workbench_page_is_only_a_built_frontend_boundary(tmp_path: Path) -> None:
    source = (
        ROOT / "backend/app/solution/customer_engagement_pages.py"
    ).read_text(encoding="utf-8")
    presales_source = source.split("def internal_workbench_html", maxsplit=1)[0]
    fallback = presales_workbench_html(frontend_dist=tmp_path)

    assert '"presales" / "workbench" / "index.html"' in presales_source
    assert "function renderStages" not in presales_source
    assert "prompt(" not in presales_source
    assert "统一售前工作台" in fallback
    assert "前端资源尚未构建" in fallback
