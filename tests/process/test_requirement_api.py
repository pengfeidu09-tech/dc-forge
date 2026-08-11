from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.process.api import get_requirement_service
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader
from backend.app.process.service import RequirementIntelligenceService
from tests.process.rm5_helpers import SKILL_ROOT, state_and_baseline


def test_requirement_api_compile_diff_route_and_existing_routes(tmp_path) -> None:
    state1, baseline1 = state_and_baseline(approval=500000)
    state2, baseline2 = state_and_baseline(state_version=2, baseline_version=2, approval=800000)
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state1); repository.save_state(state2)
    service = RequirementIntelligenceService(repository, RequirementSkillLoader(SKILL_ROOT))
    app.dependency_overrides[get_requirement_service] = lambda: service
    try:
        client = TestClient(app)
        compile_response = client.post(
            "/requirement/compile-process-spec", json={"baseline": baseline1.model_dump(mode="json")}
        )
        diff_response = client.post(
            "/requirement/diff", json={"previous": baseline1.model_dump(mode="json"), "current": baseline2.model_dump(mode="json")}
        )
        route_response = client.post(
            "/requirement/route-diff", json={"previous": baseline1.model_dump(mode="json"), "current": baseline2.model_dump(mode="json")}
        )
        assert compile_response.status_code == 200
        assert diff_response.status_code == 200
        assert diff_response.json()["changed_requirement_ids"] == ["req-approval-800000"]
        assert route_response.status_code == 200
        assert route_response.json()["decision"] == "incremental_constraint_recompile"
        schema = client.get("/openapi.json").json()["paths"]
        assert "/health" in schema and "/compile-solution-v2" in schema and "/recompile-solution-v2" in schema
    finally:
        app.dependency_overrides.clear()


def test_requirement_api_without_repository_configuration_is_503(monkeypatch) -> None:
    monkeypatch.delenv("REQUIREMENT_REPOSITORY_ROOT", raising=False)
    app.dependency_overrides.clear()
    _, baseline = state_and_baseline()
    response = TestClient(app).post(
        "/requirement/compile-process-spec", json={"baseline": baseline.model_dump(mode="json")}
    )
    assert response.status_code == 503


def test_requirement_api_invalid_state_closure_is_4xx(tmp_path) -> None:
    state, baseline = state_and_baseline()
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state)
    service = RequirementIntelligenceService(repository, RequirementSkillLoader(SKILL_ROOT))
    app.dependency_overrides[get_requirement_service] = lambda: service
    try:
        stale = baseline.model_copy(update={"source_state_version": 99})
        response = TestClient(app).post(
            "/requirement/compile-process-spec", json={"baseline": stale.model_dump(mode="json")}
        )
        assert 400 <= response.status_code < 500

        forged_item = baseline.confirmed_items[0].model_copy(update={"value": "forged truth"})
        forged = baseline.model_copy(
            update={
                "confirmed_items": [forged_item, *baseline.confirmed_items[1:]],
            }
        )
        forged_response = TestClient(app).post(
            "/requirement/compile-process-spec", json={"baseline": forged.model_dump(mode="json")}
        )
        assert forged_response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_requirement_api_rejects_invalid_contract(tmp_path) -> None:
    state, _ = state_and_baseline()
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(state)
    service = RequirementIntelligenceService(repository, RequirementSkillLoader(SKILL_ROOT))
    app.dependency_overrides[get_requirement_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/requirement/diff", json={"previous": {}, "current": {}, "extra": True}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
