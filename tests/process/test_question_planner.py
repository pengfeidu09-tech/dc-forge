from pathlib import Path

import pytest

from backend.app.contracts.requirement_intelligence import (
    QuestionHistoryEntry,
    RequirementConflict,
    RequirementGap,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.question_planner import QuestionPlanner
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(
    requirement_id: str,
    category: str,
    value: str,
    *,
    status: str = "pending",
    confirmation_level: str = "none",
) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "current_process":
        detail["process_detail"] = {
            "process_node_id": f"node-{requirement_id}", "name": "review",
            "actor": "buyer", "node_type": "human", "description": "manual review",
        }
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": f"pain-{requirement_id}", "description": value,
            "severity": "high",
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


def _state(items: list[RequirementItem], conflicts: list[RequirementConflict] | None = None) -> RequirementState:
    return RequirementState(
        project_id="synthetic-automotive-procurement",
        state_version=1,
        source_ids=["source-1"],
        items=items,
        conflicts=conflicts or [],
    )


def _skill():
    return RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")


def test_conflict_question_is_first_critical_blocking_and_deterministic() -> None:
    first = _item("approval-500", "approval", "500000")
    second = _item("approval-800", "approval", "800000")
    state = _state([first, second])
    conflicts = ConflictDetector().detect(state, _skill())
    gaps = GapDetector().detect(state, _skill(), conflicts)
    planner = QuestionPlanner()

    planned = planner.plan(state, _skill(), gaps, conflicts)
    repeated = planner.plan(state, _skill(), list(reversed(gaps)), list(reversed(conflicts)))

    assert len(planned) <= 3
    assert planned == repeated
    assert planned[0].priority == "critical"
    assert planned[0].blocking is True
    assert planned[0].target_category == "approval"
    assert planned[0].related_conflict_ids == [conflicts[0].conflict_id]
    assert "500000" in planned[0].text and "800000" in planned[0].text


def test_automotive_stage_a_asks_only_top_three_hard_or_feasibility_questions() -> None:
    state = _state(
        [
            _item("industry", "industry", "automotive"),
            _item("department", "department", "procurement"),
            _item("pain", "pain_point", "manual review"),
            _item("system", "existing_system", "OA and procurement platform"),
        ]
    )
    conflicts = ConflictDetector().detect(state, _skill())
    gaps = GapDetector().detect(state, _skill(), conflicts)
    questions = QuestionPlanner().plan(state, _skill(), gaps, conflicts)

    assert len(questions) == 3
    assert {question.target_category for question in questions} == {
        "security", "approval", "available_data",
    }
    assert all(question.priority == "high" for question in questions)
    assert not {"budget", "time"} & {question.target_category for question in questions}


def test_confirmed_fact_is_not_asked_and_question_history_suppresses_same_issue() -> None:
    security = _item(
        "security", "security", "private deployment",
        status="confirmed", confirmation_level="customer",
    )
    state = _state([security])
    gaps = GapDetector().detect(state, _skill(), [])
    planner = QuestionPlanner()
    first = planner.plan(state, _skill(), gaps, [])
    asked = QuestionHistoryEntry(
        question_id=first[0].question_id,
        asked_state_version=state.state_version,
        status="asked",
    )
    second = planner.plan(state, _skill(), gaps, [], history=[asked])

    assert not any(question.target_category == "security" for question in first)
    assert first[0].question_id not in {question.question_id for question in second}


def test_expanded_conflict_has_new_question_id_and_can_be_asked_again() -> None:
    first = _item("approval-a", "approval", "500000")
    second = _item("approval-b", "approval", "800000")
    state_v1 = _state([first, second])
    conflict_v1 = ConflictDetector().detect(state_v1, _skill())
    question_v1 = QuestionPlanner().plan(state_v1, _skill(), [], conflict_v1)[0]
    history = [
        QuestionHistoryEntry(
            question_id=question_v1.question_id,
            asked_state_version=1,
            status="asked",
        )
    ]
    third = _item("approval-c", "approval", "1000000")
    state_v2 = _state([first, second, third], conflicts=conflict_v1).model_copy(
        update={"state_version": 2}
    )
    conflict_v2 = ConflictDetector().detect(state_v2, _skill())
    question_v2 = QuestionPlanner().plan(state_v2, _skill(), [], conflict_v2, history=history)[0]

    assert conflict_v2[0].requirement_ids == ["approval-a", "approval-b", "approval-c"]
    assert question_v2.question_id != question_v1.question_id
    assert question_v2.related_conflict_ids == [conflict_v2[0].conflict_id]


def test_question_planner_groups_equivalent_category_gaps() -> None:
    state = _state([])
    gaps = [
        RequirementGap(
            gap_id="gap-a", category="security", gap_type="missing",
            description="security missing", blocking=True, reason="process",
        ),
        RequirementGap(
            gap_id="gap-b", category="security", gap_type="missing",
            description="security missing", blocking=True, reason="skill",
        ),
    ]
    questions = QuestionPlanner().plan(state, _skill(), gaps, [])

    assert len(questions) == 1
    assert questions[0].related_gap_ids == ["gap-a", "gap-b"]


def test_changed_unconfirmed_requirement_has_new_issue_signature() -> None:
    planner = QuestionPlanner()
    first_state = _state([_item("security-a", "security", "private")])
    first_gap = RequirementGap(
        gap_id="gap-security-unconfirmed", category="security", gap_type="unconfirmed",
        description="security unconfirmed", blocking=True, reason="customer confirmation required",
        related_requirement_ids=["security-a"],
    )
    first_question = planner.plan(first_state, _skill(), [first_gap], [])[0]
    history = [
        QuestionHistoryEntry(
            question_id=first_question.question_id,
            asked_state_version=1,
            status="asked",
        )
    ]
    old = _item("security-a", "security", "private", status="superseded")
    replacement = _item("security-b", "security", "private v2")
    second_state = _state([old, replacement]).model_copy(update={"state_version": 2})
    second_gap = first_gap.model_copy(update={"related_requirement_ids": ["security-b"]})
    second_question = planner.plan(
        second_state, _skill(), [second_gap], [], history=history,
    )[0]

    assert second_question.question_id != first_question.question_id


@pytest.mark.parametrize("status", ["asked", "answered", "dismissed"])
def test_all_question_history_statuses_suppress_unchanged_issue(status: str) -> None:
    state = _state([])
    gap = RequirementGap(
        gap_id="gap-security", category="security", gap_type="missing",
        description="security missing", blocking=True, reason="security required",
    )
    planner = QuestionPlanner()
    question = planner.plan(state, _skill(), [gap], [])[0]
    history = [
        QuestionHistoryEntry(
            question_id=question.question_id,
            asked_state_version=1,
            status=status,
        )
    ]

    assert planner.plan(state, _skill(), [gap], [], history=history) == []
