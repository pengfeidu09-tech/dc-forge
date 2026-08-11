from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(
    category: str,
    *,
    suffix: str = "1",
    status: str = "pending",
    confirmation_level: str = "none",
    value: str | None = None,
    parameters: dict[str, object] | None = None,
) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "current_process":
        detail["process_detail"] = {
            "process_node_id": f"node-{suffix}", "name": "review", "actor": "buyer",
            "node_type": "human", "description": "manual review",
        }
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": f"pain-{suffix}", "description": "slow", "severity": "high",
        }
    return RequirementItem(
        requirement_id=f"req-{category}-{suffix}",
        category=category,
        subject=category,
        value=value or f"value-{category}-{suffix}",
        parameters=parameters or {},
        provenance="ai_extracted",
        status=status,
        confirmation_level=confirmation_level,
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=category)],
        **detail,
    )


def _state(categories: list[str], *, confirmed: bool = False, extra: list[RequirementItem] | None = None) -> RequirementState:
    status = "confirmed" if confirmed else "pending"
    confirmation = "customer" if confirmed else "none"
    items = [
        _item(category, status=status, confirmation_level=confirmation)
        for category in categories
    ] + (extra or [])
    return RequirementState(
        project_id="synthetic-automotive-procurement", state_version=1,
        source_ids=["source-1"], items=items,
    )


def _evaluate(state: RequirementState, *, customer_confirmation_complete: bool = False):
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    conflicts = ConflictDetector().detect(state, skill)
    gaps = GapDetector().detect(state, skill, conflicts)
    return ReadinessEvaluator().evaluate(
        state, skill, gaps, conflicts,
        customer_confirmation_complete=customer_confirmation_complete,
    )


BASE = [
    "industry", "department", "business_goal", "current_process", "pain_point",
    "existing_system", "security", "approval", "available_data", "target_metric",
]


def test_automotive_golden_moves_discovery_to_preliminary_to_confirmed() -> None:
    stage_a = _state(["industry", "department", "pain_point", "existing_system"])
    stage_b = _state(BASE)
    stage_c = _state(BASE, confirmed=True)

    discovery = _evaluate(stage_a)
    preliminary = _evaluate(stage_b)
    confirmed = _evaluate(stage_c, customer_confirmation_complete=True)

    assert discovery.stage == "DISCOVERY"
    assert discovery.completeness_score == 20
    assert not discovery.can_generate_preliminary_solution and not discovery.can_generate_formal_solution
    assert preliminary.stage == "PRELIMINARY_READY"
    assert preliminary.completeness_score == 75
    assert preliminary.can_generate_preliminary_solution and not preliminary.can_generate_formal_solution
    assert confirmed.stage == "CONFIRMED_READY"
    assert confirmed.completeness_score == 75
    assert confirmed.can_generate_preliminary_solution and confirmed.can_generate_formal_solution


def test_customer_confirmation_flag_is_explicit_and_cannot_be_inferred_from_items() -> None:
    assessment = _evaluate(_state(BASE, confirmed=True), customer_confirmation_complete=False)
    assert assessment.stage == "PRELIMINARY_READY"
    assert assessment.can_generate_formal_solution is False
    assert "customer confirmation is incomplete" in assessment.reasons


def test_high_completeness_does_not_bypass_missing_security_gate() -> None:
    nearly_complete = [
        "business_goal", "current_process", "pain_point", "available_data", "existing_system",
        "business_rule", "approval", "risk", "target_metric", "scope", "deliverable", "budget", "time",
        "industry", "department",
    ]
    assessment = _evaluate(_state(nearly_complete, confirmed=True), customer_confirmation_complete=True)

    assert assessment.completeness_score == 95
    assert assessment.stage == "DISCOVERY"
    assert assessment.can_generate_formal_solution is False


def test_high_hard_conflict_blocks_readiness_even_with_complete_information() -> None:
    complete = [
        "business_goal", "current_process", "pain_point", "available_data", "existing_system",
        "business_rule", "security", "approval", "risk", "target_metric", "scope", "deliverable",
        "budget", "time", "industry", "department",
    ]
    conflicting = _item(
        "approval", suffix="2", status="conflicted", value="800000",
    )
    state = _state(complete, confirmed=True, extra=[conflicting])
    assessment = _evaluate(state, customer_confirmation_complete=True)

    assert assessment.completeness_score == 100
    assert assessment.stage == "DISCOVERY"
    assert assessment.can_generate_preliminary_solution is False
    assert any("open high-severity approval conflict" == reason for reason in assessment.reasons)


def test_conflict_golden_budget_values_remain_open_and_block_formal_readiness() -> None:
    budget_values = [
        _item("budget", suffix="meeting", value="1000000"),
        _item("budget", suffix="email", value="500000"),
        _item("budget", suffix="conversation", value="800000"),
    ]
    state = _state(BASE, confirmed=True, extra=budget_values)
    assessment = _evaluate(state, customer_confirmation_complete=True)

    assert assessment.stage == "PRELIMINARY_READY"
    assert assessment.can_generate_preliminary_solution is True
    assert assessment.can_generate_formal_solution is False
    assert len(assessment.open_conflict_ids) == 1
    assert "open medium-severity budget conflict" in assessment.reasons


def test_confirmed_not_applicable_satisfies_hard_constraint_but_pending_does_not() -> None:
    categories_without_security = [category for category in BASE if category != "security"]
    confirmed_na = _item(
        "security", status="confirmed", confirmation_level="customer",
        parameters={"not_applicable": True},
    )
    pending_na = _item("security", parameters={"not_applicable": True})
    internal_na = _item(
        "security", status="confirmed", confirmation_level="internal",
        parameters={"not_applicable": True},
    )
    confirmed_state = _state(categories_without_security, confirmed=True, extra=[confirmed_na])
    pending_state = _state(categories_without_security, confirmed=True, extra=[pending_na])
    internal_state = _state(categories_without_security, confirmed=True, extra=[internal_na])

    assert _evaluate(confirmed_state, customer_confirmation_complete=True).stage == "CONFIRMED_READY"
    assert _evaluate(pending_state, customer_confirmation_complete=True).stage == "PRELIMINARY_READY"
    assert _evaluate(internal_state, customer_confirmation_complete=True).stage == "PRELIMINARY_READY"


def test_not_applicable_cannot_bypass_process_minimum_business_goal() -> None:
    without_goal = [category for category in BASE if category != "business_goal"]
    goal_na = _item(
        "business_goal", status="confirmed", confirmation_level="customer",
        parameters={"not_applicable": True},
    )
    assessment = _evaluate(
        _state(without_goal, confirmed=True, extra=[goal_na]),
        customer_confirmation_complete=True,
    )

    assert assessment.stage == "DISCOVERY"
    assert assessment.can_generate_formal_solution is False
    assert any("business_goal" in reason for reason in assessment.reasons)


def test_active_statuses_count_once_and_inactive_statuses_do_not_count() -> None:
    state = _state(
        ["business_goal"],
        extra=[
            _item("business_goal", suffix="duplicate"),
            _item("current_process", suffix="rejected", status="rejected"),
            _item("pain_point", suffix="superseded", status="superseded"),
            _item("available_data", suffix="conflicted", status="conflicted"),
            _item("existing_system", suffix="confirmed", status="confirmed"),
        ],
    )
    assessment = _evaluate(state)

    assert assessment.completeness_score == 35


def test_hard_requirement_requires_customer_confirmed_truth_for_formal_readiness() -> None:
    without_security = [category for category in BASE if category != "security"]
    missing = _evaluate(_state(without_security, confirmed=True), customer_confirmation_complete=True)
    pending = _evaluate(
        _state(without_security, confirmed=True, extra=[_item("security")]),
        customer_confirmation_complete=True,
    )
    internal = _evaluate(
        _state(
            without_security, confirmed=True,
            extra=[_item("security", status="confirmed", confirmation_level="internal")],
        ),
        customer_confirmation_complete=True,
    )
    customer = _evaluate(
        _state(
            without_security, confirmed=True,
            extra=[_item("security", status="confirmed", confirmation_level="customer")],
        ),
        customer_confirmation_complete=True,
    )

    assert missing.stage == "DISCOVERY"
    assert pending.stage == "PRELIMINARY_READY"
    assert internal.stage == "PRELIMINARY_READY"
    assert customer.stage == "CONFIRMED_READY"


def test_customer_confirmation_flag_cannot_override_pending_or_conflicted_facts() -> None:
    pending_goal = _state(
        [category for category in BASE if category != "business_goal"],
        confirmed=True,
        extra=[_item("business_goal")],
    )
    approval_conflict = _state(
        BASE, confirmed=True,
        extra=[_item("approval", suffix="conflict", status="conflicted", value="different")],
    )

    assert _evaluate(pending_goal, customer_confirmation_complete=True).stage == "PRELIMINARY_READY"
    assert _evaluate(approval_conflict, customer_confirmation_complete=True).stage == "DISCOVERY"


def test_recommended_missing_categories_do_not_block_preliminary_readiness() -> None:
    assessment = _evaluate(_state(BASE))

    assert assessment.stage == "PRELIMINARY_READY"
    assert assessment.can_generate_preliminary_solution is True
    assert assessment.can_generate_formal_solution is False
    assert not any(reason in {"budget missing", "time missing", "integration missing"} for reason in assessment.reasons)


def test_detectors_are_pure_and_repeatable_without_state_mutation() -> None:
    state = _state(
        BASE,
        extra=[_item("budget", suffix="a", value="500000"), _item("budget", suffix="b", value="800000")],
    )
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    before = state.model_dump()

    first_conflicts = ConflictDetector().detect(state, skill)
    first_gaps = GapDetector().detect(state, skill, first_conflicts)
    first_readiness = ReadinessEvaluator().evaluate(state, skill, first_gaps, first_conflicts)
    second_conflicts = ConflictDetector().detect(state, skill)
    second_gaps = GapDetector().detect(state, skill, second_conflicts)
    second_readiness = ReadinessEvaluator().evaluate(state, skill, second_gaps, second_conflicts)

    assert state.model_dump() == before
    assert first_conflicts == second_conflicts
    assert first_gaps == second_gaps
    assert first_readiness == second_readiness


def test_completeness_and_reasons_are_exact_and_deterministic() -> None:
    complete = [
        "business_goal", "current_process", "pain_point", "available_data", "existing_system",
        "business_rule", "security", "approval", "risk", "target_metric", "scope", "deliverable",
        "budget", "time", "industry", "department",
    ]
    state = _state(complete, confirmed=True)
    first = _evaluate(state, customer_confirmation_complete=True)
    second = _evaluate(state, customer_confirmation_complete=True)

    assert first.completeness_score == 100
    assert first.model_dump() == second.model_dump()
    assert first.blocking_gap_ids == sorted(first.blocking_gap_ids)
    assert first.non_blocking_gap_ids == sorted(first.non_blocking_gap_ids)
    assert first.open_conflict_ids == sorted(first.open_conflict_ids)
    assert first.reasons == sorted(first.reasons)
