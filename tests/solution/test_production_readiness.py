"""PROD-M1 production readiness and customer boundary tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


_PRODUCTION_ENV_NAMES = (
    "DCFORGE_PRODUCTION_MODE",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "DCFORGE_DATABASE_PATH",
    "CUSTOMER_PORTAL_BASE_URL",
    "CUSTOMER_ENGAGEMENT_INTERNAL_TOKEN",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_INTERNAL_OPEN_IDS",
    "FEISHU_ALLOWED_OPEN_ID",
    "WEB_CONCURRENCY",
)


def _clear_production_env(monkeypatch) -> None:
    for name in _PRODUCTION_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _configured_production_env(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "workspace.sqlite3"
    settings = {
        "DCFORGE_PRODUCTION_MODE": "true",
        "LLM_API_KEY": "sk-production-secret-value",
        "LLM_BASE_URL": "https://api.example.com/v1",
        "LLM_MODEL": "production-model",
        "DCFORGE_DATABASE_PATH": str(database_path),
        "CUSTOMER_PORTAL_BASE_URL": "https://dcforge.example.com",
        "CUSTOMER_ENGAGEMENT_INTERNAL_TOKEN": "i" * 32,
        "FEISHU_APP_ID": "cli_production",
        "FEISHU_APP_SECRET": "feishu-production-secret",
        "FEISHU_INTERNAL_OPEN_IDS": "ou-internal-owner",
        "WEB_CONCURRENCY": "1",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)


def test_liveness_is_stable_and_development_readiness_is_non_strict(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_production_env(monkeypatch)
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["production_mode"] is False


def test_production_readiness_rejects_missing_configuration_without_leaking_secrets(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_production_env(monkeypatch)
    _configured_production_env(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_MODEL")
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))

    response = client.get("/health/ready")
    serialized = response.text

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "sk-production-secret-value" not in serialized
    assert "feishu-production-secret" not in serialized
    assert any(
        check["name"] == "llm" and check["status"] == "error"
        for check in response.json()["checks"]
    )


def test_complete_single_worker_production_configuration_is_ready(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_production_env(monkeypatch)
    _configured_production_env(monkeypatch, tmp_path)
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert all(check["status"] != "error" for check in response.json()["checks"])


def test_sqlite_workspace_allows_multiple_production_workers(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_production_env(monkeypatch)
    _configured_production_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert any(
        check["name"] == "worker_model" and check["status"] == "ok"
        for check in response.json()["checks"]
    )
