"""PORTAL-M1 enterprise Vue source acceptance checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_frontend_uses_enterprise_api_instead_of_default_mock_jsonl() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    composable = (FRONTEND / "src/composables/useEnterprisePortal.js").read_text(
        encoding="utf-8"
    )

    assert "useEnterprisePortal" in app
    assert "/enterprise/projects" in composable
    assert "/enterprise/assistant" in composable
    assert "input_solutions_10.jsonl" not in composable
    assert "solution_bundles_10.jsonl" not in composable


def test_frontend_exposes_enterprise_procurement_views_and_controls() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    required_copy = (
        "企业招采驾驶舱",
        "采购主链",
        "需求版本",
        "供应商风险",
        "文档审查",
        "方案生成",
        "AI 助手",
        "查看角色",
        "数据时间点",
        "模拟验收数据",
        "车辆与VIN",
        "交付批次",
        "会议纪要",
        "业务文档",
    )

    assert all(text in app for text in required_copy)


def test_frontend_html_metadata_names_the_enterprise_procurement_portal() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "企业招采知识门户" in html
    assert "输入输出方案可视化与策略对比" not in html


def test_frontend_uses_an_editable_time_control_and_does_not_claim_live_state() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert 'type="datetime-local"' in app
    assert "已接入实时服务" not in app
    assert "MCP 服务已连接" not in app
    assert "not_available_for_project_type" in app
    assert "forbidden_for_role" in app
    assert "versionBudget" in app
    assert "versionMilestone" in app
    assert "versionRecordedAt" in app


def test_vite_proxies_enterprise_and_mcp_to_fastapi() -> None:
    config = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")

    assert "'/enterprise'" in config
    assert "'/mcp'" in config
    assert "http://127.0.0.1:8000" in config


def test_frontend_exposes_direct_knowledge_search_and_mcp_tool_workbench() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    composable = (FRONTEND / "src/composables/useEnterprisePortal.js").read_text(
        encoding="utf-8"
    )

    assert "知识检索" in app
    assert "MCP 工具箱" in app
    assert "source_id" in app
    assert "insufficient_evidence" in app
    assert "inputSchema" in app
    assert "structuredContent" in app
    assert "/search?" in composable
    assert "tools/list" in composable
    assert "tools/call" in composable
    assert "mcpTools" in composable
