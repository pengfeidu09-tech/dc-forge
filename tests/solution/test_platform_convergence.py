"""PLATFORM-M1 internal/external convergence acceptance checks."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from backend.app.solution.agent_configuration import (
    AgentConfigurationRepository,
    AgentConfigurationService,
    configured_agent_service,
)
from backend.app.solution.customer_engagement import CustomerEngagementService
from backend.app.solution.enterprise_portal import EnterpriseKnowledgeService
from backend.app.solution.mcp_server import MCPDispatcher
from backend.app.solution.presales_orchestration import PresalesOrchestrationService
from tests.process.rm5_helpers import PROJECT_ID, state_and_baseline

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SOLUTION = ROOT / "backend" / "app" / "solution"


def test_root_frontend_is_a_tool_shell_without_bundled_business_dashboard() -> None:
    app = (FRONTEND / "src/App.vue").read_text(encoding="utf-8")
    main = (FRONTEND / "src/main.js").read_text(encoding="utf-8")

    assert "内部工具" in app
    assert "统一售前工作台" in app
    assert "IntelligenceConsole" in app
    assert "useEnterprisePortal" not in app
    assert "PRJ-TENDER-001" not in app
    assert "solutionBundle" not in app
    assert "mock/" not in main


def test_presales_generation_has_no_legacy_compiler_fallback() -> None:
    source = (SOLUTION / "presales_orchestration.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "backend.app.solution.service"
        for alias in node.names
    }

    assert "compile_solution_v2" in imported
    assert "compile_solution" not in imported
    assert "通用三方案编译器" not in source
    assert "selected_solution_id" in source
    assert "solution_revision" in source
    assert "update_solution_plan" in source


def test_customer_contract_exposes_one_plan_and_shared_progress() -> None:
    service = (SOLUTION / "customer_engagement.py").read_text(encoding="utf-8")
    customer = (FRONTEND / "src/customer/CustomerEngagementCenter.vue").read_text(
        encoding="utf-8"
    )

    assert '"plan":' in service
    assert '"progress":' in service
    assert "solution?.plan" in customer
    assert "current.solution.plans" not in customer
    assert 'v-for="plan in current.solution.plans"' not in customer
    assert "当前进度" in customer


def test_agent_tool_and_skill_policy_has_database_and_internal_api() -> None:
    config = (SOLUTION / "agent_configuration.py").read_text(encoding="utf-8")
    api = (SOLUTION / "api.py").read_text(encoding="utf-8")
    assistant = (SOLUTION / "enterprise_assistant.py").read_text(encoding="utf-8")
    workbench = (FRONTEND / "src/presales/PresalesWorkbench.vue").read_text(
        encoding="utf-8"
    )

    assert "sqlite3" in config
    assert "agent_profiles" in config
    assert "/presales/agent-config" in api
    assert "capability_policy" in assistant
    assert "Tool 与 Skill" in workbench


def test_agent_policy_and_case_knowledge_persist_in_sqlite(tmp_path: Path) -> None:
    database = tmp_path / "workspace.sqlite3"
    tools = [
        {"name": "search_knowledge", "description": "检索知识"},
        {"name": "internal_review", "description": "内部评审"},
    ]
    skills = [
        {"name": "case_matching", "description": "案例匹配"},
        {"name": "solution_recommendation", "description": "方案推荐"},
    ]
    service = AgentConfigurationService(
        AgentConfigurationRepository(database), tools=tools, skills=skills
    )
    service.update_profile(
        "feishu-internal",
        enabled_tools=["search_knowledge"],
        enabled_skills=["case_matching"],
        updated_by="agent-owner",
    )
    service.save_case(
        {
            "case_id": "CASE-001",
            "title": "采购需求分析案例",
            "industry": "制造业",
            "problem": "需求信息分散。",
            "solution_summary": "建立确认基线后生成 V2 方案。",
            "tags": ["需求分析"],
            "evidence_refs": ["source://case-001"],
        }
    )

    restarted = AgentConfigurationService(
        AgentConfigurationRepository(database), tools=tools, skills=skills
    )
    assert restarted.enabled_tool_names("internal") == {"search_knowledge"}
    assert [item["name"] for item in restarted.enabled_skills("internal")] == [
        "case_matching"
    ]
    assert restarted.list_cases("确认基线")[0]["case_id"] == "CASE-001"
    with pytest.raises(PermissionError, match="customer Agent"):
        restarted.update_profile(
            "feishu-customer",
            enabled_tools=["internal_review"],
            enabled_skills=[],
            updated_by="agent-owner",
        )


def test_runtime_business_repositories_share_the_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "workspace.sqlite3"
    monkeypatch.setenv("DCFORGE_DATABASE_PATH", str(database))
    monkeypatch.delenv("REQUIREMENT_REPOSITORY_ROOT", raising=False)
    monkeypatch.delenv("CUSTOMER_ENGAGEMENT_ROOT", raising=False)
    monkeypatch.delenv("PRESALES_ORCHESTRATION_ROOT", raising=False)

    engagement = CustomerEngagementService.from_env()
    presales = PresalesOrchestrationService.from_env(
        engagement_service=engagement,
        knowledge_service=object(),
    )
    engagement.repository.register_project(
        "db-project", channel="customer_portal"
    )
    presales.repository.ensure_project(
        "db-project", title="数据库项目", owner="presales-owner"
    )
    state, _ = state_and_baseline()
    engagement.requirement_repository.save_state(state)

    restarted = CustomerEngagementService.from_env()
    requirement_projects = {
        project["project_id"] for project in restarted.list_internal_projects()
    }

    assert engagement.repository.database_path == database.resolve()
    assert engagement.requirement_repository.database_path == database.resolve()
    assert presales.repository.database_path == database.resolve()
    assert PROJECT_ID in requirement_projects
    with sqlite3.connect(database) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "requirement_states",
            "customer_projects",
            "presales_projects",
            "knowledge_cases",
            "agent_profiles",
        } <= table_names
        assert connection.execute(
            "SELECT COUNT(*) FROM customer_projects"
        ).fetchone()[0] >= 1
        assert connection.execute(
            "SELECT COUNT(*) FROM presales_projects"
        ).fetchone()[0] == 1
    assert not list(tmp_path.rglob("*.json"))


def test_presales_research_uses_database_cases_without_a_demo_reference_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "workspace.sqlite3"
    monkeypatch.setenv("DCFORGE_DATABASE_PATH", str(database))
    case_service = AgentConfigurationService(
        AgentConfigurationRepository(database), tools=[], skills=[]
    )
    case_service.save_case(
        {
            "case_id": "CASE-DB-001",
            "title": "已验证的需求澄清方法",
            "industry": "制造业",
            "problem": "需求边界尚未形成确认记录。",
            "solution_summary": "先建立版本化需求基线，再进入方案编排。",
            "tags": ["需求分析"],
            "evidence_refs": ["case-source://001"],
        }
    )
    engagement = CustomerEngagementService.from_env()
    presales = PresalesOrchestrationService.from_env(
        engagement_service=engagement,
        knowledge_service=EnterpriseKnowledgeService(ROOT),
    )
    project = presales.create_project(title="待分析需求", owner="owner")

    snapshot = presales.run_research(
        project["project_id"],
        query="需求基线",
        user_id="employee",
        as_of="2026-08-16T10:00:00+08:00",
        generated_by="owner",
    )

    assert project["reference_project_id"] == "CASE-KNOWLEDGE"
    assert snapshot["knowledge_results"] == [
        {
            "source_id": "case-source://001",
            "title": "已验证的需求澄清方法",
            "summary": "先建立版本化需求基线，再进入方案编排。",
            "locator": "case-source://001",
        }
    ]
    workbench = (FRONTEND / "src/presales/PresalesWorkbench.vue").read_text(
        encoding="utf-8"
    )
    assert "参考项目 ID" not in workbench
    assert "汽车制造企业供应商准入" not in workbench


def test_latest_agent_catalog_hides_legacy_demo_business_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DCFORGE_DATABASE_PATH", str(tmp_path / "workspace.sqlite3"))
    service = configured_agent_service(
        MCPDispatcher(EnterpriseKnowledgeService(ROOT))
    )

    assert {tool["name"] for tool in service.catalog()["tools"]} == {
        "search_knowledge",
        "search_solution_cases",
    }


def test_agent_profile_migration_removes_tools_missing_from_latest_catalog(
    tmp_path: Path,
) -> None:
    repository = AgentConfigurationRepository(tmp_path / "workspace.sqlite3")
    old_service = AgentConfigurationService(
        repository,
        tools=[
            {"name": "search_solution_cases", "description": "案例"},
            {"name": "legacy_demo_tool", "description": "旧工具"},
        ],
        skills=[],
    )
    old_service.update_profile(
        "feishu-internal",
        enabled_tools=["search_solution_cases", "legacy_demo_tool"],
        enabled_skills=[],
        updated_by="agent-owner",
    )

    latest = AgentConfigurationService(
        repository,
        tools=[{"name": "search_solution_cases", "description": "案例"}],
        skills=[],
    )

    assert latest.profile("feishu-internal").enabled_tools == [
        "search_solution_cases"
    ]
