"""PORTAL-M5 Intelligence Console single-frontend acceptance checks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LEGACY_CONSOLE = ROOT / "tools" / "intelligence_console"


def test_enterprise_frontend_exposes_the_intelligence_console_view() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")

    assert "import IntelligenceConsole from './components/IntelligenceConsole.vue'" in app
    assert "智能引擎控制台" in app
    assert "activeView = 'console'" in app
    assert "activeView === 'tools'" in app
    assert "<IntelligenceConsole" in app


def test_console_component_preserves_the_complete_internal_workflow() -> None:
    component = (FRONTEND / "src/components/IntelligenceConsole.vue").read_text(
        encoding="utf-8"
    )

    required_workflow_copy = (
        "DCForge Intelligence Console",
        "开始需求分析",
        "需求确认",
        "解决方案生成",
        "分析客户反馈",
        "提交变化审核",
        "更新解决方案",
        "sessionStorage",
    )
    assert all(text in component for text in required_workflow_copy)


def test_console_uses_database_project_history_and_text_upload() -> None:
    component = (FRONTEND / "src/components/IntelligenceConsole.vue").read_text(
        encoding="utf-8"
    )

    assert "<a-list" in component
    assert "分析记录" in component
    assert "<a-upload" in component
    assert "上传文本资料" in component
    assert "开始需求分析并保存" in component
    assert "consoleApi.createProject" in component
    assert "consoleApi.saveProject" in component
    assert "Date.now()" not in component
    assert "<label>项目 ID" not in component


def test_console_summarizes_extraction_warnings_and_hides_technical_noise() -> None:
    component = (FRONTEND / "src/components/IntelligenceConsole.vue").read_text(
        encoding="utf-8"
    )

    assert "summarizeExtractionWarnings" in component
    assert "查看技术详情" in component
    assert "字段格式不符合需求合同" in (
        FRONTEND / "src/utils/extractionWarnings.js"
    ).read_text(encoding="utf-8")
    assert 'v-for="warning in session.extractionWarnings"' not in component


def test_console_api_and_session_tools_live_under_frontend() -> None:
    api = (FRONTEND / "src/services/intelligenceConsoleApi.js").read_text(
        encoding="utf-8"
    )
    session = (FRONTEND / "src/utils/intelligenceConsoleSession.js").read_text(
        encoding="utf-8"
    )

    for endpoint in (
        "/internal-console/projects",
        "/internal-console/analyze",
        "/internal-console/confirm",
        "/internal-console/compile",
        "/internal-console/diff",
        "/internal-console/recompile",
        "/internal-console/change-set",
        "/internal-console/change-set/review",
    ):
        assert endpoint in api
    assert "captureFeedbackCycleSnapshot" in session
    assert "buildRecompilePayload" in session


def test_main_frontend_owns_console_proxy_build_and_tests() -> None:
    vite_config = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    assert "'/health'" in vite_config
    assert "'/internal-console'" in vite_config
    assert package["scripts"]["test"] == "node --test tests/*.test.mjs"
    assert (FRONTEND / "tests/intelligence_console_session.test.mjs").is_file()


def test_legacy_console_is_no_longer_an_independent_frontend_project() -> None:
    assert not (LEGACY_CONSOLE / "package.json").exists()
    assert not (LEGACY_CONSOLE / "vite.config.js").exists()
    assert not (LEGACY_CONSOLE / "index.html").exists()
    assert not (LEGACY_CONSOLE / "src/main.js").exists()
