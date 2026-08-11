from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.contracts.requirement_intelligence import (
    ReadinessAssessment,
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
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"
BASE = [
    "industry", "department", "business_goal", "current_process", "pain_point",
    "existing_system", "security", "approval", "available_data", "target_metric",
]


def _skill():
    return RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")


def _item(
    category: str,
    *,
    suffix: str = "1",
    status: str = "confirmed",
    confirmation_level: str = "customer",
) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "current_process":
        detail["process_detail"] = {
            "process_node_id": f"node-{suffix}", "name": "review", "actor": "buyer",
            "node_type": "human", "description": "manual review",
        }
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": f"pain-{suffix}", "description": "slow",
            "severity": "high",
        }
    return RequirementItem(
        requirement_id=f"req-{category}-{suffix}",
        category=category,
        subject=category,
        value=f"value-{category}-{suffix}",
        provenance="ai_extracted",
        status=status,
        confirmation_level=confirmation_level,
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=category)],
        **detail,
    )


def _state(
    *,
    status: str = "confirmed",
    confirmation_level: str = "customer",
    extra: list[RequirementItem] | None = None,
) -> RequirementState:
    return RequirementState(
        project_id="synthetic-automotive-procurement",
        state_version=3,
        source_ids=["source-1"],
        items=[
            _item(category, status=status, confirmation_level=confirmation_level)
            for category in BASE
        ] + (extra or []),
    )


def _analyze(state: RequirementState, *, confirmation_complete: bool):
    skill = _skill()
    conflicts = ConflictDetector().detect(state, skill)
    gaps = GapDetector().detect(state, skill, conflicts)
    analyzed = RequirementState.model_validate(
        {**state.model_dump(), "gaps": gaps, "conflicts": conflicts}
    )
    readiness = ReadinessEvaluator().evaluate(
        analyzed, skill, gaps, conflicts,
        customer_confirmation_complete=confirmation_complete,
    )
    return analyzed, readiness


def test_customer_ready_state_builds_deterministic_customer_only_baseline() -> None:
    historical = _item("budget", suffix="old", status="superseded", confirmation_level="none")
    state, readiness = _analyze(_state(extra=[historical]), confirmation_complete=True)
    builder = RequirementBaselineBuilder(_skill())

    first = builder.build(
        state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="Customer confirmed the formal requirement set.",
    )
    second = builder.build(
        state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="Customer confirmed the formal requirement set.",
    )

    assert readiness.stage == "CONFIRMED_READY"
    assert first == second
    assert first.baseline_id.startswith("baseline-")
    assert first.baseline_version == 1
    assert first.source_state_version == 3
    assert all(item.status == "confirmed" for item in first.confirmed_items)
    assert all(item.confirmation_level == "customer" for item in first.confirmed_items)
    assert historical.requirement_id not in {item.requirement_id for item in first.confirmed_items}
    assert first.confirmed_items == sorted(first.confirmed_items, key=lambda item: item.requirement_id)


def test_preliminary_internal_or_false_confirmation_cannot_build_baseline() -> None:
    internal_state, internal_readiness = _analyze(
        _state(confirmation_level="internal"), confirmation_complete=True,
    )
    customer_state, incomplete_readiness = _analyze(
        _state(), confirmation_complete=False,
    )
    builder = RequirementBaselineBuilder(_skill())

    assert internal_readiness.stage == "PRELIMINARY_READY"
    assert incomplete_readiness.stage == "PRELIMINARY_READY"
    for state, readiness in (
        (internal_state, internal_readiness),
        (customer_state, incomplete_readiness),
    ):
        with pytest.raises(ValueError, match="CONFIRMED_READY"):
            builder.build(
                state, readiness, baseline_version=1, confirmed_by="customer-owner",
                confirmation_summary="not ready",
            )


def test_blocking_gap_or_open_conflict_cannot_be_smuggled_into_baseline() -> None:
    state, readiness = _analyze(_state(), confirmation_complete=True)
    forged = ReadinessAssessment(
        stage="CONFIRMED_READY", completeness_score=readiness.completeness_score,
        blocking_gap_ids=[], non_blocking_gap_ids=[], open_conflict_ids=[],
        can_generate_preliminary_solution=True, can_generate_formal_solution=True,
        reasons=["forged"],
    )
    blocked = state.model_copy(
        update={
            "gaps": [
                state.gaps[0].model_copy(update={"blocking": True})
            ]
        }
    )
    with pytest.raises(ValueError, match="blocking gap"):
        RequirementBaselineBuilder(_skill()).build(
            blocked, forged, baseline_version=1, confirmed_by="customer-owner",
            confirmation_summary="forged",
        )
    conflict = RequirementConflict(
        conflict_id="conflict-forged", category="approval",
        requirement_ids=["req-approval-1"], description="forged open conflict",
        severity="high", status="open",
    )
    conflicted = state.model_copy(update={"conflicts": [conflict], "gaps": []})
    with pytest.raises(ValueError, match="open conflict"):
        RequirementBaselineBuilder(_skill()).build(
            conflicted, forged, baseline_version=1, confirmed_by="customer-owner",
            confirmation_summary="forged",
        )


def test_non_blocking_gaps_and_explicit_assumptions_are_preserved_separately() -> None:
    state, readiness = _analyze(_state(), confirmation_complete=True)
    baseline = RequirementBaselineBuilder(_skill()).build(
        state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="confirmed",
        assumptions=["API details remain to be validated", "API details remain to be validated"],
    )

    assert baseline.non_blocking_gaps
    assert all(not gap.blocking for gap in baseline.non_blocking_gaps)
    assert baseline.assumptions == sorted(set(baseline.assumptions))
    assert "API details remain to be validated" in baseline.assumptions
    assert not any(item.provenance == "ai_inferred" for item in baseline.confirmed_items)


def test_baseline_contract_rejects_internal_items_blocking_gaps_and_extra_fields() -> None:
    state, readiness = _analyze(_state(), confirmation_complete=True)
    baseline = RequirementBaselineBuilder(_skill()).build(
        state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="confirmed",
    )
    internal = baseline.confirmed_items[0].model_copy(update={"confirmation_level": "internal"})
    with pytest.raises(ValidationError, match="customer"):
        RequirementBaseline.model_validate(
            {**baseline.model_dump(), "confirmed_items": [internal]}
        )
    with pytest.raises(ValidationError):
        RequirementBaseline.model_validate({**baseline.model_dump(), "unexpected": True})


def test_automotive_internal_and_customer_confirmation_golden() -> None:
    stage_b = _state(status="pending", confirmation_level="none")
    requirement_ids = [item.requirement_id for item in stage_b.items]
    applier = RequirementConfirmationApplier()
    internal, _, _ = applier.apply(
        stage_b,
        RequirementConfirmation(
            project_id=stage_b.project_id, state_version=stage_b.state_version,
            confirmation_level="internal", confirmed_requirement_ids=requirement_ids,
            confirmed_by="presales-owner",
        ),
    )
    internal_state, internal_readiness = _analyze(internal, confirmation_complete=True)
    assert internal_readiness.stage == "PRELIMINARY_READY"
    with pytest.raises(ValueError, match="CONFIRMED_READY"):
        RequirementBaselineBuilder(_skill()).build(
            internal_state, internal_readiness, baseline_version=1,
            confirmed_by="presales-owner", confirmation_summary="internal only",
        )

    customer, _, _ = applier.apply(
        stage_b,
        RequirementConfirmation(
            project_id=stage_b.project_id, state_version=stage_b.state_version,
            confirmation_level="customer", confirmed_requirement_ids=requirement_ids,
            confirmed_by="customer-owner",
        ),
    )
    customer_state, customer_readiness = _analyze(customer, confirmation_complete=True)
    baseline = RequirementBaselineBuilder(_skill()).build(
        customer_state, customer_readiness, baseline_version=1,
        confirmed_by="customer-owner", confirmation_summary="customer confirmed",
    )
    assert customer_readiness.stage == "CONFIRMED_READY"
    assert baseline.confirmation_level == "customer"
    assert len(baseline.confirmed_items) == len(BASE)


def test_stale_confirmed_readiness_cannot_bypass_current_pending_hard_truth() -> None:
    state = _state()
    stale_readiness = ReadinessAssessment(
        stage="CONFIRMED_READY", completeness_score=75,
        blocking_gap_ids=[], non_blocking_gap_ids=[], open_conflict_ids=[],
        can_generate_preliminary_solution=True, can_generate_formal_solution=True,
        reasons=["stale assessment from prior state"],
    )
    pending_security = next(item for item in state.items if item.category == "security").model_copy(
        update={"status": "pending", "confirmation_level": "none"}
    )
    current = RequirementState.model_validate(
        {
            **state.model_dump(mode="json"),
            "state_version": 4,
            "items": [
                pending_security.model_dump(mode="json")
                if item.category == "security"
                else item.model_dump(mode="json")
                for item in state.items
            ],
            "gaps": [],
            "conflicts": [],
        }
    )

    with pytest.raises(ValueError, match="current RequirementState"):
        RequirementBaselineBuilder(_skill()).build(
            current, stale_readiness, baseline_version=1,
            confirmed_by="customer-owner", confirmation_summary="stale",
        )


def test_baseline_id_and_assumptions_are_order_invariant_without_input_mutation() -> None:
    state, readiness = _analyze(_state(), confirmation_complete=True)
    reversed_state = state.model_copy(
        update={"items": list(reversed(state.items)), "gaps": list(reversed(state.gaps))}
    )
    before = state.model_dump()
    builder = RequirementBaselineBuilder(_skill())
    first = builder.build(
        state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="confirmed", assumptions=["Z boundary", "A boundary"],
    )
    second = builder.build(
        reversed_state, readiness, baseline_version=1, confirmed_by="customer-owner",
        confirmation_summary="confirmed", assumptions=["A boundary", "Z boundary"],
    )

    assert state.model_dump() == before
    assert first.baseline_id == second.baseline_id
    assert first.model_dump() == second.model_dump()
    assert first.assumptions == sorted(first.assumptions)
    assert not any("1000000" in assumption for assumption in first.assumptions)


def test_baseline_rejects_source_refs_outside_current_state_even_with_forged_readiness() -> None:
    state, readiness = _analyze(_state(), confirmation_complete=True)
    first = state.items[0].model_copy(
        update={
            "source_refs": [RequirementSourceRef(source_id="foreign", excerpt="foreign")]
        }
    )
    invalid_state = state.model_copy(update={"items": [first, *state.items[1:]]})
    with pytest.raises(ValueError, match="source refs"):
        RequirementBaselineBuilder(_skill()).build(
            invalid_state, readiness, baseline_version=1,
            confirmed_by="customer-owner", confirmation_summary="forged",
        )
