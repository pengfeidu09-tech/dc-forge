import json
import os

import pytest

from backend.app.contracts.requirement_intelligence import RequirementDiff, RequirementState
from backend.app.process.requirement_repository import FileRequirementRepository


def _state(version: int, project_id: str = "project-1") -> RequirementState:
    return RequirementState(project_id=project_id, state_version=version, source_ids=[], items=[])


def test_file_repository_saves_loads_and_preserves_versions(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    first, second = _state(1), _state(2)
    repository.save_state(first)
    repository.save_state(second)

    assert repository.load_state("project-1").model_dump() == second.model_dump()
    assert repository.load_state("project-1", version=1).model_dump() == first.model_dump()
    assert repository.list_versions("project-1") == [1, 2]
    with pytest.raises(FileExistsError):
        repository.save_state(first)
    with pytest.raises(FileNotFoundError):
        repository.load_state("project-1", version=3)


def test_file_repository_rejects_corrupt_and_cross_project_data(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(_state(1))
    path = repository._state_path("project-1", 1)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        repository.load_state("project-1", version=1)

    path.write_text(json.dumps(_state(1, project_id="other").model_dump()), encoding="utf-8")
    with pytest.raises(ValueError, match="project"):
        repository.load_state("project-1", version=1)


def test_file_repository_isolates_projects_and_rejects_schema_invalid_json(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    repository.save_state(_state(1, project_id="project-1"))
    repository.save_state(_state(1, project_id="project-2"))
    assert repository._state_path("project-1", 1) != repository._state_path("project-2", 1)
    assert repository.load_state("project-2", 1).project_id == "project-2"

    path = repository._state_path("project-1", 1)
    path.write_text(json.dumps({"project_id": "project-1", "state_version": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        repository.load_state("project-1", 1)


def _diff(project_id: str = "project-1") -> RequirementDiff:
    return RequirementDiff(
        project_id=project_id,
        previous_baseline_id="baseline-old",
        current_baseline_id="baseline-new",
    )


def test_diff_repository_is_immutable_isolated_and_reloadable(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    diff = _diff()
    repository.save_diff(diff)
    loaded = repository.load_diff("project-1", "baseline-old", "baseline-new")
    assert loaded == diff
    assert repository.list_diff_pairs("project-1") == [("baseline-old", "baseline-new")]
    with pytest.raises(FileExistsError):
        repository.save_diff(diff)
    repository.save_diff(_diff("project-2"))
    assert repository._diff_path("project-1", "baseline-old", "baseline-new") != repository._diff_path("project-2", "baseline-old", "baseline-new")


def test_diff_repository_rejects_corrupt_or_mismatched_data(tmp_path) -> None:
    repository = FileRequirementRepository(tmp_path)
    repository.save_diff(_diff())
    path = repository._diff_path("project-1", "baseline-old", "baseline-new")
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid RequirementDiff"):
        repository.load_diff("project-1", "baseline-old", "baseline-new")


@pytest.mark.parametrize(
    ("previous_id", "current_id"),
    [("../../outside", "new"), ("..\\outside", "new"), ("C:\\outside", "new")],
)
def test_diff_repository_hashes_untrusted_pair_ids_without_path_escape(
    tmp_path, previous_id, current_id
) -> None:
    repository = FileRequirementRepository(tmp_path)
    diff = RequirementDiff(
        project_id="project-safe",
        previous_baseline_id=previous_id,
        current_baseline_id=current_id,
    )
    repository.save_diff(diff)
    path = repository._diff_path("project-safe", previous_id, current_id)
    assert path.parent == repository._project_dir("project-safe")
    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert repository.load_diff("project-safe", previous_id, current_id) == diff
    assert not list(path.parent.glob("tmp*"))


def test_diff_atomic_write_failure_leaves_no_formal_or_temp_file(tmp_path, monkeypatch) -> None:
    repository = FileRequirementRepository(tmp_path)
    diff = _diff()
    path = repository._diff_path(diff.project_id, diff.previous_baseline_id, diff.current_baseline_id)
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        repository.save_diff(diff)
    assert not path.exists()
    assert not list(path.parent.iterdir())
