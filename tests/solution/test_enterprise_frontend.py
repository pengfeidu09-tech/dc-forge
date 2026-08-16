"""PLATFORM-M1 internal tool-shell frontend acceptance checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_root_frontend_contains_no_embedded_business_portal_or_mock_data() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert "useEnterprisePortal" not in app
    assert "solutionBundle" not in app
    assert "PRJ-TENDER-001" not in app
    assert not (FRONTEND / "src/composables/useEnterprisePortal.js").exists()
    assert not (FRONTEND / "mock/input_solutions_10.jsonl").exists()
    assert not (FRONTEND / "mock/solution_bundles_10.jsonl").exists()


def test_root_frontend_is_an_internal_tool_directory() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    required_copy = (
        "内部工具目录",
        "统一售前工作台",
        "客户专属中心",
        "案例知识库与 MCP",
        "飞书 Agent 配置",
        "智能引擎控制台",
        "/presales/workbench",
    )

    assert all(text in app for text in required_copy)


def test_frontend_html_metadata_names_the_internal_tool() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "DC Forge · 内部工具" in html
    assert "企业招采知识门户" not in html


def test_root_tool_shell_does_not_claim_business_results() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert "不包含内置业务数据" in app
    assert "模拟验收数据" not in app
    assert "已接入实时服务" not in app


def test_vite_proxies_operational_apis_to_fastapi() -> None:
    config = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")

    for path in ("'/health'", "'/internal-console'", "'^/presales/projects'"):
        assert path in config
    assert "http://127.0.0.1:8000" in config


def test_presales_frontend_exposes_database_knowledge_and_agent_configuration() -> None:
    api = (FRONTEND / "src/presales/api.js").read_text(encoding="utf-8")
    workbench = (FRONTEND / "src/presales/PresalesWorkbench.vue").read_text(
        encoding="utf-8"
    )

    assert "/presales/knowledge/cases" in api
    assert "/presales/agent-config" in api
    assert "历年解决案例" in workbench
    assert "可用 Tool" in workbench
    assert "可用 Skill" in workbench
