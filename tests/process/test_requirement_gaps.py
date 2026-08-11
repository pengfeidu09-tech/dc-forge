from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    RequirementConflict,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.gap_detector import GapDetector
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(
    requirement_id: str,
    category: str,
    *,
    status: str = "pending",
    confirmation_level: str = "none",
    parameters: dict[str, object] | None = None,
) -> RequirementItem:
    detail: dict[str, object] = {}
    if category == "current_process":
        detail["process_detail"] = {
            "process_node_id": "node-1", "name": "review", "actor": "buyer",
            "node_type": "human", "description": "manual review",
        }
    if category == "pain_point":
        detail["pain_point_detail"] = {
            "pain_point_id": "pain-1", "description": "slow", "severity": "high",
        }
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=category,
        value=f"value-{category}",
        parameters=parameters or {},
        provenance="ai_extracted",
        status=status,
        confirmation_level=confirmation_level,
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=category)],
        **detail,
    )


def _state(*items: RequirementItem) -> RequirementState:
    return RequirementState(
        project_id="project-1", state_version=1,
        source_ids=["source-1"] if items else [], items=list(items),
    )


def _skill():
    return RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")


def test_gap_detector_covers_process_closure_generic_presales_and_skill_rules() -> None:
    gaps = GapDetector().detect(_state(), _skill(), [])
    categories = {gap.category for gap in gaps}

    assert {"industry", "department", "business_goal", "current_process", "pain_point"} <= categories
    assert {"available_data", "existing_system", "target_metric", "budget", "time"} <= categories
    assert {"security", "approval", "ext:procurement:supplier_entry_policy"} <= categories
    assert all(gap.gap_type == "missing" for gap in gaps)


def test_known_pending_hard_constraint_allows_preliminary_but_blocks_formal() -> None:
    pending = _item("security", "security")
    gaps = GapDetector().detect(_state(pending), _skill(), [])
    security = next(gap for gap in gaps if gap.category == "security")

    assert security.gap_type == "unconfirmed"
    assert security.blocking is True
    assert security.related_requirement_ids == ["security"]


def test_confirmed_customer_and_confirmed_not_applicable_close_formal_gap() -> None:
    confirmed = _item("security", "security", status="confirmed", confirmation_level="customer")
    not_applicable = _item(
        "approval", "approval", status="confirmed", confirmation_level="customer",
        parameters={"not_applicable": True},
    )
    pending_not_applicable = _item(
        "data", "available_data", parameters={"not_applicable": True},
    )
    gaps = GapDetector().detect(_state(confirmed, not_applicable, pending_not_applicable), _skill(), [])

    assert not any(gap.category == "security" for gap in gaps)
    assert not any(gap.category == "approval" for gap in gaps)
    assert any(gap.category == "available_data" and gap.gap_type == "unconfirmed" for gap in gaps)


def test_budget_and_time_are_default_nonblocking_and_gap_ids_are_deterministic() -> None:
    first = GapDetector().detect(_state(), _skill(), [])
    second = GapDetector().detect(_state(), _skill(), [])
    budget_time = [gap for gap in first if gap.category in {"budget", "time"}]

    assert budget_time and all(gap.blocking is False for gap in budget_time)
    assert [gap.model_dump() for gap in first] == [gap.model_dump() for gap in second]
    assert [gap.gap_id for gap in first] == sorted(gap.gap_id for gap in first)


def test_gap_deduplication_and_missing_unconfirmed_conflicted_precedence() -> None:
    skill = _skill()
    missing = [gap for gap in GapDetector().detect(_state(), skill, []) if gap.category == "security"]
    pending_item = _item("security", "security")
    unconfirmed = [
        gap for gap in GapDetector().detect(_state(pending_item), skill, []) if gap.category == "security"
    ]
    second = _item("security-2", "security").model_copy(update={"value": "other"})
    conflict = RequirementConflict(
        conflict_id="conflict-security", category="security",
        requirement_ids=["security", "security-2"], description="security conflict",
        severity="high", status="open",
    )
    conflicted = [
        gap
        for gap in GapDetector().detect(_state(pending_item, second), skill, [conflict])
        if gap.category == "security"
    ]

    assert [gap.gap_type for gap in missing] == ["missing"]
    assert [gap.gap_type for gap in unconfirmed] == ["unconfirmed"]
    assert [gap.gap_type for gap in conflicted] == ["conflicted"]


def test_rejected_and_superseded_items_do_not_satisfy_active_gaps() -> None:
    superseded = _item(
        "security-old", "security", status="superseded", confirmation_level="none"
    )
    rejected = _item("approval-old", "approval", status="rejected", confirmation_level="none")
    gaps = GapDetector().detect(_state(superseded, rejected), _skill(), [])

    assert any(gap.category == "security" and gap.gap_type == "missing" for gap in gaps)
    assert any(gap.category == "approval" and gap.gap_type == "missing" for gap in gaps)


def test_gap_ids_and_related_order_are_invariant_to_item_order() -> None:
    first_item = _item("security-b", "security")
    second_item = _item("security-a", "security")
    first = GapDetector().detect(_state(first_item, second_item), _skill(), [])
    second = GapDetector().detect(_state(second_item, first_item), _skill(), [])

    assert [gap.model_dump() for gap in first] == [gap.model_dump() for gap in second]
