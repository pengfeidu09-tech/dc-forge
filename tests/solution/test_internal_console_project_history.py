"""PORTAL-M8 Internal Console database project history acceptance tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.internal_console.api import (
    get_internal_console_project_repository,
)
from backend.app.internal_console.service import InternalConsoleService
from backend.app.main import create_app
from backend.app.solution.internal_console_projects import (
    InternalConsoleProjectRepository,
)
from backend.app.solution.workspace_database import SqliteRequirementRepository


def test_default_console_service_uses_the_workspace_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "workspace.sqlite3"
    monkeypatch.setenv("DCFORGE_DATABASE_PATH", str(database))
    monkeypatch.delenv("INTERNAL_CONSOLE_DATA_ROOT", raising=False)
    monkeypatch.delenv("REQUIREMENT_REPOSITORY_ROOT", raising=False)

    service = InternalConsoleService()

    assert isinstance(service.repository, SqliteRequirementRepository)
    assert service.repository.database_path == database.resolve()


def test_demo_is_first_and_user_projects_are_monotonic(tmp_path: Path) -> None:
    database = tmp_path / "workspace.sqlite3"
    repository = InternalConsoleProjectRepository(database)

    first_listing = repository.list_projects()
    second = repository.create_project(
        sources={"meeting": "第二条会议资料", "email": "", "document": "", "sales": ""},
        uploaded_files=[],
    )
    third = repository.create_project(
        sources={"meeting": "", "email": "第三条邮件", "document": "", "sales": ""},
        uploaded_files=["customer.txt"],
    )

    assert [(item.sequence, item.title, item.kind) for item in first_listing] == [
        (1, "汽车采购示例", "demo")
    ]
    assert (second.sequence, second.title, second.project_id) == (
        2,
        "需求分析 2",
        "internal-console-0002",
    )
    assert (third.sequence, third.title, third.project_id) == (
        3,
        "需求分析 3",
        "internal-console-0003",
    )

    restarted = InternalConsoleProjectRepository(database)
    projects = restarted.list_projects()
    assert [item.sequence for item in projects] == [1, 2, 3]
    assert projects[0].snapshot["sources"]["document"]
    assert projects[2].snapshot["uploadedFiles"] == ["customer.txt"]


def test_project_snapshot_can_be_saved_and_restored(tmp_path: Path) -> None:
    repository = InternalConsoleProjectRepository(tmp_path / "workspace.sqlite3")
    project = repository.create_project(
        sources={"meeting": "访谈", "email": "", "document": "", "sales": ""},
        uploaded_files=[],
    )
    snapshot = {
        **project.snapshot,
        "projectId": "client-supplied-id-must-not-win",
        "analysis": {"current_state": {"state_version": 1}},
    }

    saved = repository.save_snapshot(project.project_id, snapshot)

    assert saved.project_id == project.project_id
    assert saved.snapshot["projectId"] == project.project_id
    assert saved.snapshot["analysis"]["current_state"]["state_version"] == 1
    assert repository.get_project(project.project_id) == saved


def test_demo_snapshot_is_read_only(tmp_path: Path) -> None:
    repository = InternalConsoleProjectRepository(tmp_path / "workspace.sqlite3")
    demo = repository.list_projects()[0]

    with pytest.raises(PermissionError, match="demo is read-only"):
        repository.save_snapshot(demo.project_id, {"sources": {"meeting": "覆盖"}})


def test_internal_console_project_api_uses_database_catalog(tmp_path: Path) -> None:
    repository = InternalConsoleProjectRepository(tmp_path / "workspace.sqlite3")
    application = create_app(True)
    application.dependency_overrides[
        get_internal_console_project_repository
    ] = lambda: repository

    with TestClient(application) as client:
        listing = client.get("/internal-console/projects")
        created = client.post(
            "/internal-console/projects",
            json={
                "sources": {
                    "meeting": "用户上传后的会议资料",
                    "email": "",
                    "document": "采购约束",
                    "sales": "",
                },
                "uploaded_files": ["requirement.md"],
            },
        )
        saved = client.put(
            "/internal-console/projects/internal-console-0002",
            json={
                "snapshot": {
                    **created.json()["snapshot"],
                    "projectId": "forged-id",
                    "baseline": {"baseline_version": 1},
                }
            },
        )

    assert listing.status_code == 200
    assert [item["title"] for item in listing.json()["projects"]] == ["汽车采购示例"]
    assert created.status_code == 201
    assert created.json()["project_id"] == "internal-console-0002"
    assert saved.status_code == 200
    assert saved.json()["snapshot"]["projectId"] == "internal-console-0002"
    assert saved.json()["snapshot"]["baseline"]["baseline_version"] == 1
