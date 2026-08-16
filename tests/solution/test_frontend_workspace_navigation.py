"""PORTAL-M6 root workspace navigation acceptance checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_root_portal_links_to_the_presales_workspace() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert "业务工作台" in app
    assert "售前协作工作台" in app
    assert 'href="/presales/workbench"' in app


def test_workspace_link_uses_sidebar_navigation_styles() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    styles = (FRONTEND / "src/styles/enterprise.css").read_text(encoding="utf-8")

    assert 'class="enterprise-workspace-link"' in app
    assert ".enterprise-workspace-link" in styles
    assert ".enterprise-workspace-link:focus-visible" in styles
