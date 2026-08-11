from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.contracts.requirement_intelligence import (
    RequirementAnalysis,
    RequirementChange,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.requirement_analysis import RequirementAnalysisBuilder
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(requirement_id: str, category: str, value: str) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": "pain-1", "description": value, "severity": "high",
        }
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=category,
        value=value,
        provenance="ai_extracted",
        status="pending",
        confirmation_level="none",
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=value)],
        **detail,
    )


def test_analysis_builds_deterministic_closed_result_and_honest_summary() -> None:
    state = RequirementState(
        project_id="synthetic-automotive-procurement",
        state_version=2,
        source_ids=["source-1"],
        items=[
            _item("industry", "industry", "automotive"),
            _item("pain", "pain_point", "manual review"),
        ],
    )
    change = RequirementChange(
        requirement_id="pain", change_type="added", before_value=None,
        after_value="manual review", explanation="extracted from meeting",
    )
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    builder = RequirementAnalysisBuilder()

    first = builder.build(
        state, skill, changes=[change], previous_state_version=1,
        customer_confirmation_complete=False,
    )
    second = builder.build(
        state, skill, changes=[change], previous_state_version=1,
        customer_confirmation_complete=False,
    )

    assert first == second
    assert first.project_id == state.project_id
    assert first.previous_state_version == 1
    assert first.current_state.state_version == 2
    assert first.current_state.gaps
    assert first.readiness.stage == "DISCOVERY"
    assert len(first.next_questions) <= 3
    assert "待客户确认" in first.customer_confirmation_summary
    assert "客户已确认" not in first.customer_confirmation_summary
    assert "open conflict" in first.customer_confirmation_summary
    assert "blocking gap" in first.customer_confirmation_summary


def test_analysis_contract_rejects_project_version_and_question_reference_mismatch() -> None:
    state = RequirementState(
        project_id="project-1", state_version=2, source_ids=[], items=[],
    )
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    analysis = RequirementAnalysisBuilder().build(
        state, skill, changes=[], previous_state_version=1,
    )

    with pytest.raises(ValidationError, match="project"):
        RequirementAnalysis.model_validate({**analysis.model_dump(), "project_id": "other"})
    with pytest.raises(ValidationError, match="previous_state_version"):
        RequirementAnalysis.model_validate({**analysis.model_dump(), "previous_state_version": 2})
    question = analysis.next_questions[0].model_copy(
        update={"related_gap_ids": ["gap-does-not-exist"]}
    )
    with pytest.raises(ValidationError, match="gap"):
        RequirementAnalysis.model_validate(
            {**analysis.model_dump(), "next_questions": [question]}
        )


def test_analysis_does_not_mutate_input_requirement_state() -> None:
    state = RequirementState(
        project_id="project-1", state_version=1, source_ids=["source-1"],
        items=[_item("goal", "business_goal", "reduce cycle time")],
    )
    before = state.model_dump()
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")

    RequirementAnalysisBuilder().build(state, skill, changes=[])

    assert state.model_dump() == before


def test_customer_confirmation_complete_flag_cannot_bypass_missing_core_truth() -> None:
    budget = RequirementItem(
        requirement_id="budget", category="budget", subject="budget", value="800000",
        provenance="customer_raw", status="confirmed", confirmation_level="customer",
        confidence=1.0,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt="800000")],
    )
    state = RequirementState(
        project_id="project-1", state_version=2, source_ids=["source-1"], items=[budget],
    )
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    analysis = RequirementAnalysisBuilder().build(
        state, skill, changes=[], previous_state_version=1,
        customer_confirmation_complete=True,
    )

    assert analysis.readiness.stage == "DISCOVERY"
    assert analysis.readiness.can_generate_formal_solution is False
