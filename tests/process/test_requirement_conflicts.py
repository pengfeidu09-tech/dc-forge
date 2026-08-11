from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    RequirementConflict,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(requirement_id: str, value: str, *, category: str = "budget", status: str = "pending") -> RequirementItem:
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=f"{category} threshold",
        value=value,
        provenance="ai_extracted",
        status=status,
        confirmation_level="customer" if status == "confirmed" else "none",
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id=f"source-{requirement_id}", excerpt=value)],
    )


def _state(*items: RequirementItem, conflicts: list[RequirementConflict] | None = None) -> RequirementState:
    return RequirementState(
        project_id="project-1",
        state_version=1,
        source_ids=sorted({ref.source_id for item in items for ref in item.source_refs}),
        items=list(items),
        conflicts=conflicts or [],
    )


def test_same_slot_different_pending_values_conflict_but_same_value_does_not() -> None:
    detector = ConflictDetector()
    different = detector.detect(_state(_item("one", "500000"), _item("two", "800000")))
    same = detector.detect(_state(_item("one", "500000"), _item("two", " 500000 ")))

    assert len(different) == 1
    assert different[0].requirement_ids == ["one", "two"]
    assert different[0].status == "open"
    assert same == []


def test_hard_conflict_is_high_and_ids_and_order_are_deterministic() -> None:
    state = _state(
        _item("security-b", "public", category="security"),
        _item("security-a", "private", category="security"),
    )
    first = ConflictDetector().detect(state)
    second = ConflictDetector().detect(state)

    assert [conflict.model_dump() for conflict in first] == [conflict.model_dump() for conflict in second]
    assert first[0].severity == "high"
    assert first[0].requirement_ids == ["security-a", "security-b"]
    assert first[0].conflict_id.startswith("conflict-")


def test_existing_reducer_conflict_is_not_duplicated() -> None:
    first, second = _item("one", "500000", category="approval"), _item("two", "800000", category="approval")
    existing = RequirementConflict(
        conflict_id="conflict-existing", category="approval", requirement_ids=["one", "two"],
        description="existing reducer conflict", severity="high", status="open",
    )
    conflicts = ConflictDetector().detect(_state(first, second, conflicts=[existing]))
    assert conflicts == [existing]


def test_existing_two_value_conflict_expands_to_one_three_value_group() -> None:
    first = _item("a", "500000", category="approval")
    second = _item("b", "800000", category="approval")
    third = _item("c", "1000000", category="approval")
    detector = ConflictDetector()
    initial = detector.detect(_state(first, second))[0]

    expanded = detector.detect(_state(first, second, third, conflicts=[initial]))
    fresh = detector.detect(_state(third, first, second))

    assert len(expanded) == 1
    assert expanded[0].requirement_ids == ["a", "b", "c"]
    assert expanded[0].status == "open"
    assert expanded[0].conflict_id == fresh[0].conflict_id
    assert expanded[0].model_dump() == fresh[0].model_dump()


def test_existing_reducer_conflict_expands_when_third_value_arrives() -> None:
    first = _item("a", "500000", category="approval")
    second = _item("b", "800000", category="approval")
    third = _item("c", "1000000", category="approval")
    reducer_conflict = RequirementConflict(
        conflict_id="conflict-reducer", category="approval", requirement_ids=["a", "b"],
        description="reducer conflict", severity="high", status="open",
    )
    conflicts = ConflictDetector().detect(_state(first, second, third, conflicts=[reducer_conflict]))

    assert len(conflicts) == 1
    assert conflicts[0].requirement_ids == ["a", "b", "c"]
    assert conflicts[0].status == "open"


def test_resolved_conflict_with_superseded_history_is_not_reopened() -> None:
    old = _item("old", "500000", category="approval").model_copy(update={"status": "superseded"})
    current = _item("current", "800000", category="approval", status="confirmed")
    resolved = RequirementConflict(
        conflict_id="conflict-resolved", category="approval", requirement_ids=["old", "current"],
        description="customer resolved", severity="high", status="resolved", resolution_requirement_id="current",
    )
    conflicts = ConflictDetector().detect(_state(old, current, conflicts=[resolved]))
    assert conflicts == [resolved]


def test_conflict_golden_preserves_all_values_and_source_ranking_does_not_resolve() -> None:
    state = _state(
        _item("meeting", "1000000"),
        _item("email", "500000"),
        _item("conversation", "800000"),
    )
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    conflicts = ConflictDetector().detect(state, skill)

    assert len(conflicts) == 1
    assert conflicts[0].requirement_ids == ["conversation", "email", "meeting"]
    assert conflicts[0].status == "open"
    assert {item.value for item in state.items} == {"500000", "800000", "1000000"}
