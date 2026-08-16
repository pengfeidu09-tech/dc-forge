"""PORTAL-M6 root workspace navigation acceptance checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_root_portal_links_to_the_presales_workspace() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert "内部工具目录" in app
    assert "统一售前工作台" in app
    assert "href: '/presales/workbench'" in app


def test_workspace_link_uses_sidebar_navigation_styles() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    styles = (FRONTEND / "src/styles/internal.css").read_text(encoding="utf-8")

    assert 'class="tool-link"' in app
    assert ".tool-link" in styles
    assert ".tool-link:focus-visible" in styles
