"""PRESALES-M1 unified presales orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.internal_console.service import InternalConsoleService
from backend.app.main import create_app
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.solution.api import (
    set_customer_engagement_service,
    set_presales_orchestration_service,
)
from backend.app.solution.customer_engagement import (
    CustomerEngagementService,
    FileCustomerEngagementRepository,
)
from backend.app.solution.customer_engagement_pages import internal_workbench_html
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.presales_orchestration import (
    DeliverableContent,
    EditableSolutionPlan,
    FilePresalesOrchestrationRepository,
    PresalesOrchestrationService,
    PresalesSkillCatalog,
)
from tests.process.rm5_helpers import PROJECT_ID, SKILL_ROOT, state_and_baseline


class NoopProvider:
    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        return LLMResponse(
            content='{"intent":"general","answer":"请继续介绍您的需求。"}'
        )


class RecordingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def analyze_turn(self, **kwargs):
        self.calls.append(kwargs)
        return type("AnalysisResult", (), {"state_version": len(self.calls)})()


class FakeKnowledgeService:
    def search_knowledge(self, project_id: str, **kwargs) -> dict:
        return {
            "project_id": project_id,
            "results": [
                {
                    "source_id": "SRC-CASE-001",
                    "title": "汽车智能招采参考案例",
                    "snippet": "供应商准入、询比价和合规审查参考做法。",
                    "source_path": "02_行业解决方案库/汽车智能招采.md",
                }
            ],
            "source_records": [],
            "insufficient_evidence": False,
        }


def _engagement_service(
    tmp_path: Path,
    *,
    analyzer: RecordingAnalyzer | None = None,
) -> CustomerEngagementService:
    requirement_repository = FileRequirementRepository(tmp_path / "requirements")
    internal_console = InternalConsoleService(
        repository=requirement_repository,
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=NoopProvider(),
    )
    return CustomerEngagementService(
        repository=FileCustomerEngagementRepository(tmp_path / "engagement"),
        requirement_repository=requirement_repository,
        internal_console=internal_console,
        feedback_analyzer=analyzer,
        public_base_url="https://dcforge.example.com",
    )


def _orchestration(
    tmp_path: Path,
    *,
    analyzer: RecordingAnalyzer | None = None,
) -> PresalesOrchestrationService:
    engagement = _engagement_service(tmp_path, analyzer=analyzer)
    engagement.repository.register_project(PROJECT_ID, channel="customer_portal")
    engagement.repository.ensure_access(PROJECT_ID)
    return PresalesOrchestrationService(
        repository=FilePresalesOrchestrationRepository(tmp_path / "presales"),
        engagement_service=engagement,
        knowledge_service=FakeKnowledgeService(),
        skill_catalog=PresalesSkillCatalog(
            Path(__file__).parents[2]
            / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
            / "07_Skill技能库"
        ),
    )


def test_skill_catalog_exposes_seven_templates_and_connects_four_core_steps() -> None:
    catalog = PresalesSkillCatalog(
        Path(__file__).parents[2]
        / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
        / "07_Skill技能库"
    )

    skills = catalog.list_skills()

    assert len(skills) == 7
    connected = {item["name"]: item["connected_step"] for item in skills}
    assert connected["requirement_analysis"] == "requirement_analysis"
    assert connected["case_matching"] == "knowledge_retrieval"
    assert connected["solution_recommendation"] == "solution_generation"
    assert connected["document_generation"] == "customer_output"
    assert connected["meeting_intelligence"] is None


def test_customer_sources_enter_requirement_analysis_but_external_evidence_does_not(
    tmp_path,
) -> None:
    analyzer = RecordingAnalyzer()
    service = _orchestration(tmp_path, analyzer=analyzer)

    customer_source = service.add_source(
        PROJECT_ID,
        source_type="customer_document",
        title="客户需求说明",
        content="供应商准入和采购合规审查目前主要依赖人工。",
        added_by="presales-owner",
    )
    external_source = service.add_source(
        PROJECT_ID,
        source_type="external_intelligence",
        title="汽车行业采购合规标准更新",
        content="该资料作为外部研究证据，不代表客户已确认要求。",
        source_url="https://example.com/automotive-procurement-standard",
        occurred_at="2026-08-15T09:00:00+08:00",
        added_by="research-owner",
    )

    assert customer_source["analysis_state_version"] == 1
    assert external_source["analysis_state_version"] is None
    assert len(analyzer.calls) == 1
    assert analyzer.calls[0]["message"] == "供应商准入和采购合规审查目前主要依赖人工。"
    stored = service.get_workspace(PROJECT_ID)["sources"]
    assert {item["source_type"] for item in stored} == {
        "customer_document",
        "external_intelligence",
    }
    assert next(
        item for item in stored if item["source_type"] == "external_intelligence"
    )["source_url"].startswith("https://")


def test_research_draft_review_edit_reapproval_publish_and_customer_deliverable(
    tmp_path,
) -> None:
    service = _orchestration(tmp_path)
    engagement = service.engagement_service
    state, baseline = state_and_baseline()
    engagement.requirement_repository.save_state(state)
    engagement.requirement_repository.save_baseline(baseline)
    service.add_source(
        PROJECT_ID,
        source_type="external_intelligence",
        title="汽车采购监管资料",
        content="用于售前研究的公开监管资料。",
        source_url="https://example.com/regulation",
        occurred_at="2026-08-15T09:00:00+08:00",
        added_by="research-owner",
    )

    research = service.run_research(
        PROJECT_ID,
        query="汽车制造企业供应商准入与采购合规",
        user_id="user-procurement-owner",
        as_of="2026-08-15T10:00:00+08:00",
        generated_by="presales-owner",
    )
    draft = service.generate_draft(
        PROJECT_ID,
        baseline_version=1,
        generated_by="presales-owner",
    )
    first_review = service.review_draft(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        decision="approved",
        reviewed_by="solution-owner",
        note="方案结构和风险边界可以对客展示。",
    )

    assert research["knowledge_results"][0]["source_id"] == "SRC-CASE-001"
    assert research["external_sources"][0]["source_url"] == "https://example.com/regulation"
    assert draft["plans"]
    assert draft["deliverable"]["citations"]
    assert first_review["decision"] == "approved"

    edited_content = DeliverableContent.model_validate(draft["deliverable"])
    edited_content = edited_content.model_copy(
        update={
            "recommended_solution": "先验证供应商准入与合规审查，再决定后续扩展范围。"
        }
    )
    edited = service.update_deliverable(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        content=edited_content,
        updated_by="presales-owner",
    )
    assert edited["deliverable_revision"] == 2

    with pytest.raises(ValueError, match="approved"):
        service.publish_project(
            PROJECT_ID,
            draft_version=draft["draft_version"],
            published_by="presales-owner",
        )

    service.review_draft(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        decision="approved",
        reviewed_by="solution-owner",
        note="已复核修订后的客户成果稿。",
    )
    published = service.publish_project(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        published_by="presales-owner",
    )
    access = engagement.ensure_customer_access(PROJECT_ID)
    customer_deliverable = service.get_customer_deliverable_for_access(
        access["access_id"], access["token"]
    )
    html = service.render_customer_deliverable_html(customer_deliverable)
    set_customer_engagement_service(engagement)
    set_presales_orchestration_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        customer_data_response = client.get(
            f"/customer/engagement/{access['access_id']}/data",
            headers={"X-DCForge-Customer-Token": access["token"]},
        )
        deliverable_response = client.get(
            f"/customer/engagement/{access['access_id']}/deliverable",
            headers={"X-DCForge-Customer-Token": access["token"]},
        )
    finally:
        set_presales_orchestration_service(None)
        set_customer_engagement_service(None)

    assert published["publication_version"] == 1
    assert customer_deliverable["recommended_solution"].startswith("先验证")
    assert "待验证" in json.dumps(customer_deliverable, ensure_ascii=False)
    assert "汽车智能招采参考案例" in html
    assert "https://example.com/regulation" in html
    assert "contenteditable=\"true\"" in html
    assert "review_score" not in html
    assert "asset_id" not in html
    assert customer_data_response.json()["deliverable"]["publication_version"] == 1
    assert deliverable_response.status_code == 200
    assert "可编辑" not in deliverable_response.text
    assert "contenteditable=\"true\"" in deliverable_response.text
    assert deliverable_response.headers["cache-control"] == "no-store"

    workspace = service.get_workspace(PROJECT_ID)
    stage_status = {item["stage"]: item["status"] for item in workspace["stages"]}
    assert stage_status["customer_output"] == "completed"
    assert stage_status["feedback_iteration"] == "current"


def test_employee_can_select_edit_and_publish_only_one_v2_plan(tmp_path) -> None:
    service = _orchestration(tmp_path)
    state, baseline = state_and_baseline()
    service.engagement_service.requirement_repository.save_state(state)
    service.engagement_service.requirement_repository.save_baseline(baseline)
    service.run_research(
        PROJECT_ID,
        query="车辆采购方案案例",
        user_id="user-procurement-owner",
        as_of="2026-08-15T10:00:00+08:00",
        generated_by="presales-owner",
    )
    draft = service.generate_draft(
        PROJECT_ID,
        baseline_version=1,
        generated_by="presales-owner",
    )
    assert draft["selected_solution_id"] == next(
        plan["solution_id"] for plan in draft["plans"] if plan["recommended"]
    )

    alternative = next(plan for plan in draft["plans"] if not plan["recommended"])
    selected = service.select_solution_plan(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        solution_id=alternative["solution_id"],
        updated_by="solution-owner",
    )
    edited_plan = EditableSolutionPlan.model_validate(alternative).model_copy(
        update={
            "name": "员工确认后的客户方案",
            "summary": "按客户当前约束人工修订后的单一交付方案。",
        }
    )
    edited = service.update_solution_plan(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        solution_id=alternative["solution_id"],
        plan=edited_plan,
        updated_by="solution-owner",
    )

    assert selected["solution_revision"] == 2
    assert edited["solution_revision"] == 3
    assert [record["action"] for record in edited["solution_edits"]] == [
        "selected",
        "edited",
    ]
    service.review_draft(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        decision="approved",
        reviewed_by="review-owner",
    )
    service.publish_project(
        PROJECT_ID,
        draft_version=draft["draft_version"],
        published_by="presales-owner",
    )
    access = service.engagement_service.ensure_customer_access(PROJECT_ID)
    customer = service.engagement_service.get_customer_view(access["token"])

    assert customer["solution"]["plan"]["name"] == "员工确认后的客户方案"
    assert "plans" not in customer["solution"]
    assert "solution_id" not in customer["solution"]["plan"]


def test_demo_draft_uses_latest_requirement_state_without_a_baseline(
    tmp_path,
) -> None:
    service = _orchestration(tmp_path)
    state, _ = state_and_baseline()
    service.engagement_service.requirement_repository.save_state(state)
    service.run_research(
        PROJECT_ID,
        query="汽车制造企业供应商准入与采购合规",
        user_id="user-procurement-owner",
        as_of="2026-08-15T10:00:00+08:00",
        generated_by="presales-owner",
    )

    set_customer_engagement_service(service.engagement_service)
    set_presales_orchestration_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        response = client.post(
            f"/presales/projects/{PROJECT_ID}/drafts",
            json={"generated_by": "demo-workbench"},
        )
    finally:
        set_presales_orchestration_service(None)
        set_customer_engagement_service(None)

    assert response.status_code == 201
    draft = response.json()
    assert draft["baseline_version"] is None
    assert draft["requirement_state_version"] == state.state_version
    assert draft["requirement_basis"] == "latest_requirement_state"
    assert len(draft["plans"]) == 3
    assert any("演示预览" in warning for warning in draft["warnings"])
    assert any(
        "尚未形成正式确认基线" in risk
        for risk in draft["deliverable"]["risks_and_boundaries"]
    )


def test_demo_draft_auto_researches_and_compiles_explicit_rules_with_v2(
    tmp_path,
) -> None:
    service = _orchestration(tmp_path)
    complete_state, _ = state_and_baseline(goal="采购10台 Xiaomi SU7")
    budget_rule = next(
        item
        for item in complete_state.items
        if item.category == "available_data" and item.value == "审查规则"
    ).model_copy(
        update={
            "requirement_id": "req-demo-budget-rule",
            "category": "budget",
            "subject": "采购价格目标",
            "value": "采购价格低于市场价 10%",
            "parameters": {"benchmark_discount_percent": 10.0},
        }
    )
    sparse_state = complete_state.model_copy(
        update={
            "items": [
                item
                for item in complete_state.items
                if item.category in {"department", "business_goal", "role"}
            ]
            + [budget_rule],
            "gaps": [],
            "process_observations": [],
            "pain_observations": [],
        }
    )
    service.engagement_service.requirement_repository.save_state(sparse_state)

    set_customer_engagement_service(service.engagement_service)
    set_presales_orchestration_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        response = client.post(
            f"/presales/projects/{PROJECT_ID}/drafts",
            json={"generated_by": "demo-workbench"},
        )
    finally:
        set_presales_orchestration_service(None)
        set_customer_engagement_service(None)

    assert response.status_code == 201
    draft = response.json()
    workspace = service.get_workspace(PROJECT_ID)
    assert len(workspace["research_snapshots"]) == 1
    assert "采购10台 Xiaomi SU7" in workspace["research_snapshots"][0]["query"]
    assert draft["research_version"] == 1
    assert len(draft["plans"]) == 3
    assert next(plan for plan in draft["plans"] if plan["recommended"])[
        "strategy"
    ] == "生产适配"
    assert all(plan["solution_id"].endswith("-v2") for plan in draft["plans"])
    assert any("自动生成知识研究快照" in warning for warning in draft["warnings"])


def test_v2_workbench_generates_from_current_state_without_version_prompt() -> None:
    html = internal_workbench_html()

    assert "prompt('Baseline 版本'" not in html
    assert "baseline_version:Number(raw)" not in html
    assert "生成前需要正式 Baseline" not in html
    assert "Solution Intelligence V2 方案" in html
    assert "生成演示方案" not in html


def test_unified_presales_pages_and_api_are_the_internal_and_customer_entries(
    tmp_path,
) -> None:
    service = _orchestration(tmp_path)
    engagement = service.engagement_service
    set_customer_engagement_service(engagement)
    set_presales_orchestration_service(service)
    try:
        client = TestClient(create_app(frontend_dist=tmp_path / "missing-dist"))
        page = client.get("/presales/workbench")
        legacy_page = client.get("/customer-engagement/workbench")
        projects = client.get("/presales/projects")
    finally:
        set_presales_orchestration_service(None)
        set_customer_engagement_service(None)

    assert page.status_code == 200
    assert "统一售前工作台" in page.text
    assert legacy_page.status_code == 200
    assert "统一售前工作台" in legacy_page.text
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["project_id"] == PROJECT_ID
    assert engagement.internal_workbench_url().endswith("/presales/workbench")
