from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.internal_console.api import get_internal_console_service
from backend.app.internal_console.service import InternalConsoleService
from backend.app.main import create_app
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService
from backend.app.solution.llm_provider import LLMResponse
from backend.app.solution.service import (
    compile_demo_blueprint,
    compile_solution_v2,
    recompile_solution_v2,
)


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _candidate(category: str, subject: str, value: str, quote: str, **extra) -> dict:
    return {
        "category": category,
        "subject": subject,
        "value": value,
        "parameters": extra.pop("parameters", {}),
        "confidence": 1.0,
        "candidate_kind": "extracted",
        "evidence_quote": quote,
        **extra,
    }


class GoldenSpyProvider:
    """Test-only provider: returns strict extraction JSON and records raw prompts."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        source = messages[-1]["content"]
        self.calls.append(source)
        candidates: list[dict] = []
        if "超过80万元才必须人工审批" in source:
            candidates = [
                _candidate(
                    "approval",
                    "procurement approval threshold",
                    "超过800000必须人工审批",
                    "审批规则调整，现在超过80万元才必须人工审批。",
                    parameters={"threshold": 800000},
                )
            ]
        elif "汽车制造企业" in source:
            candidates = [
                _candidate("industry", "industry", "制造", "汽车制造企业"),
                _candidate("department", "department", "采购中心", "采购中心"),
                _candidate("role", "buyer", "采购专员", "采购专员"),
                _candidate(
                    "current_process",
                    "document intake",
                    "接收招标文件",
                    "采购专员接收招标文件",
                    process_detail={
                        "process_node_id": "intake",
                        "name": "招标文件接收",
                        "actor": "采购专员",
                        "node_type": "human",
                        "description": "采购专员接收招标文件",
                        "next_node_ids": ["review"],
                    },
                ),
                _candidate(
                    "current_process",
                    "document review",
                    "审查招标文件并定位风险",
                    "采购专员依据审查规则审查招标文件并定位风险",
                    process_detail={
                        "process_node_id": "review",
                        "name": "招标文件审查",
                        "actor": "采购专员",
                        "node_type": "human",
                        "description": "采购专员依据审查规则审查招标文件并定位风险",
                        "next_node_ids": [],
                    },
                ),
                _candidate(
                    "pain_point",
                    "manual review",
                    "人工审查周期长且合规风险定位慢",
                    "人工审查周期长且合规风险定位慢",
                    pain_point_detail={
                        "pain_point_id": "manual-review",
                        "description": "人工审查周期长且合规风险定位慢",
                        "severity": "high",
                        "affected_process_node_ids": ["review"],
                    },
                ),
            ]
        elif "缩短招标文件编制与审查周期" in source:
            candidates = [
                _candidate(
                    "business_goal",
                    "goal",
                    "缩短招标文件编制与审查周期，降低合规风险",
                    "缩短招标文件编制与审查周期，降低合规风险",
                ),
                _candidate("existing_system", "OA", "OA", "OA"),
            ]
        elif "超过50万元必须人工审批" in source:
            candidates = [
                _candidate("available_data", "historical documents", "历史招标文件", "历史招标文件"),
                _candidate("available_data", "enterprise policy", "企业采购制度", "企业采购制度"),
                _candidate("available_data", "review rules", "审查规则", "审查规则"),
                _candidate("security", "deployment boundary", "数据不得出企业私域", "数据不得出企业私域"),
                _candidate(
                    "approval",
                    "procurement approval threshold",
                    "超过500000必须人工审批",
                    "超过50万元必须人工审批",
                    parameters={"threshold": 500000},
                ),
                _candidate("target_metric", "processing time", "processing_time", "processing_time"),
                _candidate("target_metric", "manual steps", "manual_steps", "manual_steps"),
                _candidate("target_metric", "risk findings", "risk_findings", "risk_findings"),
            ]
        return LLMResponse(content=json.dumps({"candidates": candidates}, ensure_ascii=False))


class WarningProvider:
    def complete(self, messages: list[dict], tools=None) -> LLMResponse:
        return LLMResponse(content="", warnings=["provider not configured"])


def _sources(project_id: str) -> list[dict]:
    return [
        {
            "source_id": "meeting-raw-v1",
            "project_id": project_id,
            "source_type": "meeting_minutes",
            "title": "汽车采购访谈纪要",
            "inline_content": (
                "客户为汽车制造企业，项目由采购中心负责。当前流程由采购专员接收招标文件，"
                "随后采购专员依据审查规则审查招标文件并定位风险。"
                "人工审查周期长且合规风险定位慢。"
            ),
        },
        {
            "source_id": "email-raw-v1",
            "project_id": project_id,
            "source_type": "email",
            "title": "项目目标邮件",
            "inline_content": "项目目标是缩短招标文件编制与审查周期，降低合规风险。现有系统包括OA。",
        },
        {
            "source_id": "document-raw-v1",
            "project_id": project_id,
            "source_type": "requirement_document",
            "title": "采购智能化需求文档",
            "inline_content": (
                "可用材料包括历史招标文件、企业采购制度和审查规则。数据不得出企业私域。"
                "审批规则为超过50万元必须人工审批。"
                "目标指标包括processing_time、manual_steps和risk_findings。"
            ),
        },
        {
            "source_id": "sales-raw-v1",
            "project_id": project_id,
            "source_type": "sales_note",
            "title": "售前备注",
            "inline_content": "客户希望先验证汽车采购招标文件审查场景。",
            "author_role": "presales",
        },
    ]


def _feedback_source(project_id: str, state_version: int) -> list[dict]:
    return [
        {
            "source_id": f"feedback-state-{state_version + 1}",
            "project_id": project_id,
            "source_type": "conversation",
            "title": "客户审批规则反馈",
            "inline_content": "审批规则调整，现在超过80万元才必须人工审批。",
        }
    ]


def _client_for(service: InternalConsoleService) -> TestClient:
    application = create_app(True)
    application.dependency_overrides[get_internal_console_service] = lambda: service
    return TestClient(application)


@pytest.fixture
def console_client(tmp_path):
    provider = GoldenSpyProvider()
    service = InternalConsoleService(
        repository=FileRequirementRepository(tmp_path),
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=provider,
    )
    with _client_for(service) as client:
        yield client, service, provider


def _analyze(client: TestClient, project_id: str, *, previous_version=None, sources=None):
    response = client.post(
        "/internal-console/analyze",
        json={
            "project_id": project_id,
            "sources": sources or _sources(project_id),
            "previous_state_version": previous_version,
            "skill_id": "automotive-procurement-v1",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _confirm(client: TestClient, analysis: dict, ids: list[str], *, level="customer"):
    response = client.post(
        "/internal-console/confirm",
        json={
            "confirmation": {
                "project_id": analysis["project_id"],
                "state_version": analysis["current_state"]["state_version"],
                "confirmation_level": level,
                "confirmed_requirement_ids": ids,
                "confirmed_by": "internal-console-user",
                "note": f"Explicit {level} confirmation in the internal console.",
            }
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _initial_baseline(client: TestClient, project_id: str):
    analyzed = _analyze(client, project_id)
    items = analyzed["analysis"]["current_state"]["items"]
    confirmed = _confirm(
        client,
        analyzed["analysis"],
        [item["requirement_id"] for item in items],
    )
    assert confirmed["analysis"]["readiness"]["stage"] == "CONFIRMED_READY"
    assert confirmed["baseline"]["baseline_version"] == 1
    return analyzed, confirmed


def _compile(client: TestClient, project_id: str, version: int = 1):
    response = client.post(
        "/internal-console/compile",
        json={"project_id": project_id, "baseline_version": version},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _feedback_baseline(client: TestClient, project_id: str, state_version: int):
    analyzed = _analyze(
        client,
        project_id,
        previous_version=state_version,
        sources=_feedback_source(project_id, state_version),
    )
    approval_items = [
        item
        for item in analyzed["analysis"]["current_state"]["items"]
        if item["category"] == "approval"
    ]
    new_item = next(
        item for item in approval_items if item["parameters"].get("threshold") == 800000
    )
    assert new_item["status"] == "conflicted"
    confirmed = _confirm(client, analyzed["analysis"], [new_item["requirement_id"]])
    assert confirmed["baseline"]["baseline_version"] == 2
    return analyzed, confirmed


def test_router_is_default_closed_and_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.delenv("DCFORGE_ENABLE_INTERNAL_CONSOLE", raising=False)
    default_app = create_app()
    enabled_app = create_app(True)

    default_paths = default_app.openapi()["paths"]
    enabled_paths = enabled_app.openapi()["paths"]
    assert "/internal-console/analyze" not in default_paths
    assert "/internal-console/analyze" in enabled_paths
    assert "/health" in default_paths and "/compile-solution-v2" in default_paths
    assert "/requirement/compile-process-spec" in default_paths
    assert "/health" in enabled_paths and "/requirement/compile-process-spec" in enabled_paths
    with TestClient(default_app) as default_client, TestClient(enabled_app) as enabled_client:
        assert default_client.get("/health").json()["status"] == "ok"
        assert enabled_client.get("/health").json()["status"] == "ok"
        assert default_client.post("/internal-console/analyze", json={}).status_code == 404

    for true_value in ("1", "true", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("DCFORGE_ENABLE_INTERNAL_CONSOLE", true_value)
        assert "/internal-console/analyze" in create_app().openapi()["paths"]


def test_repository_configuration_uses_workspace_database_outside_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("INTERNAL_CONSOLE_DATA_ROOT", raising=False)
    monkeypatch.delenv("REQUIREMENT_REPOSITORY_ROOT", raising=False)
    database = tmp_path / "workspace.sqlite3"
    monkeypatch.setenv("DCFORGE_DATABASE_PATH", str(database))
    get_internal_console_service.cache_clear()
    service = InternalConsoleService()
    assert service.repository.database_path == database.resolve()

    monkeypatch.setenv(
        "DCFORGE_DATABASE_PATH",
        str(Path(__file__).parents[2] / "data" / "workspace.sqlite3"),
    )
    with pytest.raises(RuntimeError, match="outside the Git working tree"):
        InternalConsoleService()
    get_internal_console_service.cache_clear()


def test_golden_uses_only_raw_sources_and_never_auto_confirms(console_client) -> None:
    client, service, provider = console_client
    payload = _analyze(client, "automotive-raw-only")
    state = payload["analysis"]["current_state"]

    assert len(provider.calls) == 4
    assert all("Untrusted business data" in call for call in provider.calls)
    assert len(state["items"]) == 18
    assert {item["status"] for item in state["items"]} == {"pending"}
    assert {item["confirmation_level"] for item in state["items"]} == {"none"}
    assert {item["provenance"] for item in state["items"]} == {"ai_extracted"}
    extension_items = [item for item in state["items"] if item["category"].startswith("ext:")]
    assert {item["category"] for item in extension_items} == {
        "ext:automotive:quality_compliance",
        "ext:automotive:system_boundary",
    }
    assert all(item["source_refs"] for item in extension_items)
    assert service.repository.list_baseline_versions("automotive-raw-only") == []


def test_internal_confirmation_cannot_create_baseline_but_customer_can(console_client) -> None:
    client, _, _ = console_client
    analyzed = _analyze(client, "confirmation-levels")
    ids = [item["requirement_id"] for item in analyzed["analysis"]["current_state"]["items"]]

    internal = _confirm(client, analyzed["analysis"], ids, level="internal")
    assert internal["baseline"] is None
    assert internal["analysis"]["readiness"]["stage"] != "CONFIRMED_READY"
    assert {item["confirmation_level"] for item in internal["analysis"]["current_state"]["items"]} == {"internal"}

    customer = _confirm(client, internal["analysis"], ids, level="customer")
    assert customer["baseline"]["baseline_version"] == 1
    assert {item["provenance"] for item in customer["baseline"]["confirmed_items"]} == {"ai_extracted"}
    assert {item["confirmation_level"] for item in customer["baseline"]["confirmed_items"]} == {"customer"}


def test_feedback_requires_explicit_customer_confirmation(console_client) -> None:
    client, service, _ = console_client
    _, initial = _initial_baseline(client, "feedback-confirmation")
    analyzed = _analyze(
        client,
        "feedback-confirmation",
        previous_version=initial["analysis"]["current_state"]["state_version"],
        sources=_feedback_source(
            "feedback-confirmation",
            initial["analysis"]["current_state"]["state_version"],
        ),
    )
    candidate = next(
        item
        for item in analyzed["analysis"]["current_state"]["items"]
        if item["parameters"].get("threshold") == 800000
    )
    assert candidate["status"] == "conflicted"
    assert candidate["confirmation_level"] == "none"
    assert service.repository.list_baseline_versions("feedback-confirmation") == [1]


def test_projects_are_isolated_and_replay_is_versioned_without_duplicates(console_client) -> None:
    client, service, _ = console_client
    first = _analyze(client, "project-a")
    second = _analyze(client, "project-b")
    replay = _analyze(client, "project-a", previous_version=1)

    first_ids = {item["requirement_id"] for item in first["analysis"]["current_state"]["items"]}
    second_ids = {item["requirement_id"] for item in second["analysis"]["current_state"]["items"]}
    replay_ids = {item["requirement_id"] for item in replay["analysis"]["current_state"]["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert replay_ids == first_ids
    assert replay["analysis"]["current_state"]["state_version"] == 2
    assert replay["analysis"]["changes"] == []
    assert service.repository.list_versions("project-a") == [1, 2]
    assert service.repository.list_versions("project-b") == [1]


def test_provider_failure_is_visible_and_cannot_create_truth_or_baseline(tmp_path) -> None:
    service = InternalConsoleService(
        repository=FileRequirementRepository(tmp_path),
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=WarningProvider(),
    )
    with _client_for(service) as client:
        response = client.post(
            "/internal-console/analyze",
            json={
                "project_id": "provider-failure",
                "sources": [_sources("provider-failure")[0]],
                "skill_id": "automotive-procurement-v1",
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["current_state"]["items"] == []
    assert {warning["code"] for warning in payload["extraction_warnings"]} == {
        "provider_warning",
        "empty_response",
    }
    assert service.repository.list_baseline_versions("provider-failure") == []


def test_compile_and_diff_load_authoritative_repository_baselines(console_client) -> None:
    client, _, _ = console_client
    project_id = "authoritative-baselines"
    _, initial = _initial_baseline(client, project_id)
    compiled = _compile(client, project_id)
    _, feedback = _feedback_baseline(
        client, project_id, initial["analysis"]["current_state"]["state_version"]
    )
    diff = client.post(
        "/internal-console/diff",
        json={
            "project_id": project_id,
            "previous_baseline_version": 1,
            "current_baseline_version": 2,
        },
    )
    browser_baseline_bypass = client.post(
        "/internal-console/compile",
        json={"baseline": feedback["baseline"]},
    )

    assert compiled["process_spec"]["project_id"] == project_id
    assert diff.status_code == 200
    assert diff.json()["route"]["decision"] == "incremental_constraint_recompile"
    assert browser_baseline_bypass.status_code == 422


def test_recompile_rejects_tampered_solution_blueprint_and_constraints(console_client) -> None:
    client, _, _ = console_client
    project_id = "stale-guard"
    _, initial = _initial_baseline(client, project_id)
    compiled = _compile(client, project_id)
    _feedback_baseline(client, project_id, initial["analysis"]["current_state"]["state_version"])
    base_request = {
        "project_id": project_id,
        "previous_baseline_version": 1,
        "current_baseline_version": 2,
        "previous_process": compiled["process_spec"],
        "selected_solution": compiled["recommended_solution"],
        "selected_blueprint": compiled["demo_blueprint"],
    }

    wrong_solution = json.loads(json.dumps(base_request))
    wrong_solution["selected_solution"]["source_project_id"] = "wrong-project"
    wrong_blueprint = json.loads(json.dumps(base_request))
    wrong_blueprint["selected_blueprint"]["solution_id"] = "wrong-solution"
    wrong_constraints = json.loads(json.dumps(base_request))
    approval = next(
        item for item in wrong_constraints["selected_solution"]["applied_constraints"]
        if item["type"] == "approval"
    )
    approval["parameters"]["threshold"] = 123

    for request in (wrong_solution, wrong_blueprint, wrong_constraints):
        response = client.post("/internal-console/recompile", json=request)
        assert response.status_code == 422, response.text


class CountingInternalConsoleService(InternalConsoleService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.b_calls = {"compile": 0, "recompile": 0}

    def requirement_service(self) -> RequirementIntelligenceService:
        def compile_spy(process):
            self.b_calls["compile"] += 1
            return compile_solution_v2(process)

        def recompile_spy(process, solution, blueprint, constraints):
            self.b_calls["recompile"] += 1
            return recompile_solution_v2(process, solution, blueprint, constraints)

        return RequirementIntelligenceService(
            self.repository,
            self.skill_loader,
            compile_solution_fn=compile_spy,
            compile_blueprint_fn=compile_demo_blueprint,
            recompile_solution_fn=recompile_spy,
        )


def test_no_op_route_invokes_zero_b_compile_or_recompile_calls(tmp_path) -> None:
    service = CountingInternalConsoleService(
        repository=FileRequirementRepository(tmp_path),
        skill_loader=RequirementSkillLoader(SKILL_ROOT),
        provider=GoldenSpyProvider(),
    )
    with _client_for(service) as client:
        _, initial = _initial_baseline(client, "no-op")
        compiled = _compile(client, "no-op")
        baseline_v1 = service.repository.load_baseline("no-op", 1)
        baseline_v2 = baseline_v1.model_copy(
            update={"baseline_id": "baseline-no-op-v2", "baseline_version": 2}
        )
        service.repository.save_baseline(baseline_v2)
        service.b_calls = {"compile": 0, "recompile": 0}
        response = client.post(
            "/internal-console/recompile",
            json={
                "project_id": "no-op",
                "previous_baseline_version": 1,
                "current_baseline_version": 2,
                "previous_process": compiled["process_spec"],
                "selected_solution": compiled["recommended_solution"],
                "selected_blueprint": compiled["demo_blueprint"],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "no_op"
    assert response.json()["requirement_diff"]["changes"] == []
    assert service.b_calls == {"compile": 0, "recompile": 0}


def test_500k_to_800k_full_backend_flow(console_client) -> None:
    client, _, _ = console_client
    project_id = "automotive-full-flow"
    analyzed, initial = _initial_baseline(client, project_id)
    compiled = _compile(client, project_id)
    feedback_analysis, feedback = _feedback_baseline(
        client, project_id, initial["analysis"]["current_state"]["state_version"]
    )
    diff = client.post(
        "/internal-console/diff",
        json={
            "project_id": project_id,
            "previous_baseline_version": 1,
            "current_baseline_version": 2,
        },
    ).json()
    recompiled_response = client.post(
        "/internal-console/recompile",
        json={
            "project_id": project_id,
            "previous_baseline_version": 1,
            "current_baseline_version": 2,
            "previous_process": compiled["process_spec"],
            "selected_solution": compiled["recommended_solution"],
            "selected_blueprint": compiled["demo_blueprint"],
        },
    )
    assert recompiled_response.status_code == 200, recompiled_response.text
    recompiled = recompiled_response.json()

    old_approval = next(
        constraint for constraint in compiled["process_spec"]["constraints"]
        if constraint["type"] == "approval"
    )
    new_approval = next(
        constraint for constraint in recompiled["solution"]["applied_constraints"]
        if constraint["type"] == "approval"
    )
    new_payload = json.dumps(
        [recompiled["solution"], recompiled["demo_blueprint"]],
        ensure_ascii=False,
    )
    assert analyzed["analysis"]["current_state"]["source_ids"] == [
        "document-raw-v1",
        "email-raw-v1",
        "meeting-raw-v1",
        "sales-raw-v1",
    ]
    assert feedback_analysis["analysis"]["current_state"]["conflicts"]
    assert initial["baseline"]["confirmed_items"]
    assert feedback["baseline"]["baseline_version"] == 2
    assert diff["route"]["decision"] == "incremental_constraint_recompile"
    assert old_approval["parameters"]["threshold"] == 500000
    assert new_approval["parameters"]["threshold"] == 800000
    assert old_approval["id"] == new_approval["id"]
    assert recompiled["recompile_result"]["diff"]["changed_demo_node_ids"] == [
        "hard-approval-gate"
    ]
    assert "500000" not in new_payload
    assert "800000" in new_payload
