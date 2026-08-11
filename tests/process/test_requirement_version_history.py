import json
from pathlib import Path

import pytest

from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementConfirmation,
    RequirementConflict,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier
from backend.app.process.requirement_repository import FileRequirementRepository
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"
BASE = [
    "industry", "department", "business_goal", "current_process", "pain_point",
    "existing_system", "security", "available_data", "target_metric",
]


def _skill():
    return RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")


def _item(
    requirement_id: str,
    category: str,
    value: str,
    *,
    status: str = "confirmed",
    confirmation_level: str = "customer",
) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "current_process":
        detail["process_detail"] = {
            "process_node_id": "node-review", "name": "review", "actor": "buyer",
            "node_type": "human", "description": "manual review",
        }
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": "pain-review", "description": value, "severity": "high",
        }
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=category,
        value=value,
        provenance="ai_extracted",
        status=status,
        confirmation_level=confirmation_level,
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=value)],
        **detail,
    )


def _state_with_approval(
    approval: RequirementItem,
    *,
    version: int,
    conflicts: list[RequirementConflict] | None = None,
    extra: list[RequirementItem] | None = None,
) -> RequirementState:
    items = [
        _item(f"req-{category}", category, f"value-{category}")
        for category in BASE
    ] + [approval] + (extra or [])
    return RequirementState(
        project_id="synthetic-automotive-procurement", state_version=version,
        source_ids=["source-1"], items=items, conflicts=conflicts or [],
    )


def _assess(state: RequirementState):
    skill = _skill()
    conflicts = ConflictDetector().detect(state, skill)
    gaps = GapDetector().detect(state, skill, conflicts)
    analyzed = RequirementState.model_validate(
        {**state.model_dump(), "gaps": gaps, "conflicts": conflicts}
    )
    readiness = ReadinessEvaluator().evaluate(
        analyzed, skill, gaps, conflicts, customer_confirmation_complete=True,
    )
    return analyzed, readiness


def _baseline(version: int, source_version: int, value: str) -> RequirementBaseline:
    item = _item(f"approval-{value}", "approval", value)
    state, readiness = _assess(_state_with_approval(item, version=source_version))
    return RequirementBaselineBuilder(_skill()).build(
        state, readiness, baseline_version=version, confirmed_by="customer-owner",
        confirmation_summary=f"confirmed approval {value}",
    )


def test_repository_preserves_baseline_v1_v2_and_enforces_monotonic_versions(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    first = _baseline(1, 1, "500000")
    second = _baseline(2, 2, "800000")
    repository.save_baseline(first)
    repository.save_baseline(second)

    assert repository.list_baseline_versions(first.project_id) == [1, 2]
    assert repository.load_baseline(first.project_id, 1) == first
    assert repository.load_baseline(first.project_id) == second
    assert repository.list_baselines(first.project_id) == [first, second]
    with pytest.raises(FileExistsError):
        repository.save_baseline(first)
    with pytest.raises(ValueError, match="next version"):
        FileRequirementRepository(tmp_path / "skip").save_baseline(_baseline(2, 2, "800000"))
    before = repository.load_baseline(first.project_id, 1).model_dump()
    with pytest.raises(ValueError, match="next version"):
        repository.save_baseline(_baseline(4, 4, "1000000"))
    assert repository.load_baseline(first.project_id, 1).model_dump() == before


def test_repository_persists_append_only_confirmation_history(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    state = RequirementState(
        project_id="project-1", state_version=1, source_ids=["source-1"],
        items=[_item("approval-800", "approval", "800000", status="pending", confirmation_level="none")],
    )
    _, _, record = RequirementConfirmationApplier().apply(
        state,
        RequirementConfirmation(
            project_id="project-1", state_version=1, confirmation_level="customer",
            confirmed_requirement_ids=["approval-800"], confirmed_by="customer-owner",
        ),
    )
    repository.save_confirmation_record(record)

    assert repository.list_confirmation_records("project-1") == [record]
    with pytest.raises(FileExistsError):
        repository.save_confirmation_record(record)

    path = repository._confirmation_path("project-1", record.confirmation_id)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid RequirementConfirmationRecord"):
        repository.list_confirmation_records("project-1")


def test_confirmation_history_is_stably_ordered_and_project_isolated(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    applier = RequirementConfirmationApplier()
    records = []
    for version in (2, 1):
        state = RequirementState(
            project_id="project-1", state_version=version, source_ids=["source-1"],
            items=[
                _item(
                    f"scope-{version}", "scope", f"phase-{version}",
                    status="pending", confirmation_level="none",
                )
            ],
        )
        _, _, record = applier.apply(
            state,
            RequirementConfirmation(
                project_id="project-1", state_version=version,
                confirmation_level="customer",
                confirmed_requirement_ids=[f"scope-{version}"],
                confirmed_by="customer-owner",
            ),
        )
        repository.save_confirmation_record(record)
        records.append(record)

    loaded = repository.list_confirmation_records("project-1")
    assert [record.source_state_version for record in loaded] == [1, 2]
    assert repository.list_confirmation_records("project-2") == []


def test_repository_atomic_writes_leave_no_temporary_files(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    baseline = _baseline(1, 1, "500000")
    repository.save_baseline(baseline)
    state = RequirementState(
        project_id=baseline.project_id, state_version=1, source_ids=["source-1"],
        items=[_item("scope", "scope", "phase one", status="pending", confirmation_level="none")],
    )
    _, _, record = RequirementConfirmationApplier().apply(
        state,
        RequirementConfirmation(
            project_id=state.project_id, state_version=1,
            confirmation_level="customer", confirmed_requirement_ids=["scope"],
            confirmed_by="customer-owner",
        ),
    )
    repository.save_confirmation_record(record)
    directory = repository._project_dir(baseline.project_id)

    assert {path.name for path in directory.iterdir()} == {
        "baseline-00000001.json", f"{record.confirmation_id}.json",
    }


def test_repository_rejects_corrupt_and_cross_project_baseline_or_confirmation(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    baseline = _baseline(1, 1, "500000")
    repository.save_baseline(baseline)
    path = repository._baseline_path(baseline.project_id, 1)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid RequirementBaseline"):
        repository.load_baseline(baseline.project_id, 1)

    other = baseline.model_copy(update={"project_id": "other"})
    path.write_text(json.dumps(other.model_dump(mode="json")), encoding="utf-8")
    with pytest.raises(ValueError, match="project_id"):
        repository.load_baseline(baseline.project_id, 1)


def test_existing_state_repository_api_remains_compatible(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    state = RequirementState(project_id="project-1", state_version=1, source_ids=[], items=[])
    repository.save_state(state)

    assert repository.list_versions("project-1") == [1]
    assert repository.load_state("project-1") == state


def test_approval_500_to_800_produces_baseline_v2_without_overwriting_v1(tmp_path: Path) -> None:
    repository = FileRequirementRepository(tmp_path)
    old = _item("approval-500", "approval", "500000")
    state_v1, readiness_v1 = _assess(_state_with_approval(old, version=1))
    baseline_v1 = RequirementBaselineBuilder(_skill()).build(
        state_v1, readiness_v1, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="approval 500000 confirmed",
    )
    repository.save_baseline(baseline_v1)
    baseline_v1_before = repository.load_baseline(state_v1.project_id, 1).model_dump()

    new = _item(
        "approval-800", "approval", "800000",
        status="conflicted", confirmation_level="none",
    )
    conflict = RequirementConflict(
        conflict_id="conflict-approval", category="approval",
        requirement_ids=[old.requirement_id, new.requirement_id],
        description="approval changed", severity="high", status="open",
    )
    state_v2 = _state_with_approval(old, version=2, conflicts=[conflict], extra=[new])
    resolved, _, record = RequirementConfirmationApplier().apply(
        state_v2,
        RequirementConfirmation(
            project_id=state_v2.project_id, state_version=2,
            confirmation_level="customer",
            confirmed_requirement_ids=[new.requirement_id],
            confirmed_by="customer-owner",
        ),
    )
    analyzed_v2, readiness_v2 = _assess(resolved)
    baseline_v2 = RequirementBaselineBuilder(_skill()).build(
        analyzed_v2, readiness_v2, baseline_version=2,
        confirmed_by="customer-owner", confirmation_summary="approval 800000 confirmed",
    )
    repository.save_confirmation_record(record)
    repository.save_baseline(baseline_v2)

    persisted_v1 = repository.load_baseline(state_v1.project_id, 1)
    persisted_v2 = repository.load_baseline(state_v1.project_id, 2)
    assert any(item.value == "500000" for item in persisted_v1.confirmed_items)
    assert any(item.value == "800000" for item in persisted_v2.confirmed_items)
    assert not any(item.value == "500000" for item in persisted_v2.confirmed_items)
    assert repository.list_baseline_versions(state_v1.project_id) == [1, 2]
    assert persisted_v1.model_dump() == baseline_v1_before
    assert repository.list_confirmation_records(state_v1.project_id) == [record]
