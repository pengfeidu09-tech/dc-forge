import pytest
from pydantic import ValidationError
from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    RequirementConfirmation,
    RequirementConflict,
    RequirementItem,
    RequirementModification,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.requirement_confirmation import RequirementConfirmationApplier
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _item(
    requirement_id: str,
    value: str,
    *,
    category: str = "approval",
    status: str = "pending",
    confirmation_level: str = "none",
    provenance: str = "ai_extracted",
) -> RequirementItem:
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=category,
        value=value,
        provenance=provenance,
        status=status,
        confirmation_level=confirmation_level,
        confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt=value)],
    )


def _state(*items: RequirementItem, conflicts: list[RequirementConflict] | None = None, version: int = 1) -> RequirementState:
    return RequirementState(
        project_id="project-1",
        state_version=version,
        source_ids=["source-1"],
        items=list(items),
        conflicts=conflicts or [],
    )


def _confirmation(**updates: object) -> RequirementConfirmation:
    payload: dict[str, object] = {
        "project_id": "project-1",
        "state_version": 1,
        "confirmation_level": "customer",
        "confirmed_requirement_ids": ["approval-800"],
        "rejected_requirement_ids": [],
        "modifications": [],
        "confirmed_by": "customer-owner",
        "note": "confirmed in meeting",
    }
    payload.update(updates)
    return RequirementConfirmation(**payload)


def _approval_conflict() -> tuple[RequirementState, RequirementConflict]:
    old = _item(
        "approval-500", "500000", status="confirmed", confirmation_level="customer",
    )
    new = _item("approval-800", "800000", status="conflicted")
    conflict = RequirementConflict(
        conflict_id="conflict-approval", category="approval",
        requirement_ids=[old.requirement_id, new.requirement_id],
        description="approval values conflict", severity="high", status="open",
    )
    return _state(old, new, conflicts=[conflict]), conflict


def _three_value_conflict() -> RequirementState:
    items = [
        _item("approval-a", "500000"),
        _item("approval-b", "800000", status="conflicted"),
        _item("approval-c", "1000000", status="conflicted"),
    ]
    conflict = RequirementConflict(
        conflict_id="conflict-approval-three", category="approval",
        requirement_ids=[item.requirement_id for item in items],
        description="three approval values conflict", severity="high", status="open",
    )
    return _state(*items, conflicts=[conflict])


def test_confirmation_contract_rejects_empty_duplicates_overlap_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="action"):
        _confirmation(confirmed_requirement_ids=[])
    with pytest.raises(ValidationError, match="unique"):
        _confirmation(confirmed_requirement_ids=["a", "a"])
    with pytest.raises(ValidationError, match="overlap"):
        _confirmation(confirmed_requirement_ids=["a"], rejected_requirement_ids=["a"])
    with pytest.raises(ValidationError):
        RequirementConfirmation(**{**_confirmation().model_dump(), "status": "confirmed"})
    with pytest.raises(ValidationError, match="modify"):
        RequirementModification(target_requirement_id="a", reason="no actual change")
    modification = RequirementModification(
        target_requirement_id="a", new_value="changed", reason="change",
    )
    with pytest.raises(ValidationError, match="overlap"):
        _confirmation(confirmed_requirement_ids=["a"], modifications=[modification])
    with pytest.raises(ValidationError, match="unique"):
        _confirmation(
            confirmed_requirement_ids=[], modifications=[modification, modification],
        )


def test_confirmation_rejects_project_version_unknown_and_inactive_items() -> None:
    state = _state(_item("approval-800", "800000"))
    applier = RequirementConfirmationApplier()

    with pytest.raises(ValueError, match="project_id"):
        applier.apply(state, _confirmation(project_id="other"))
    with pytest.raises(ValueError, match="stale"):
        applier.apply(state, _confirmation(state_version=2))
    with pytest.raises(ValueError, match="unknown"):
        applier.apply(state, _confirmation(confirmed_requirement_ids=["missing"]))
    inactive = _state(_item("approval-800", "800000", status="superseded"))
    with pytest.raises(ValueError, match="inactive"):
        applier.apply(inactive, _confirmation())


def test_internal_and_customer_confirmation_create_new_versions_without_changing_provenance() -> None:
    original = _item("approval-800", "800000")
    state = _state(original)
    applier = RequirementConfirmationApplier()
    before = state.model_dump()
    internal_state, internal_changes, internal_record = applier.apply(
        state,
        _confirmation(confirmation_level="internal", confirmed_by="presales-owner"),
    )

    assert state.model_dump() == before
    assert internal_state.state_version == 2
    internal_item = internal_state.items[0]
    assert internal_item.status == "confirmed"
    assert internal_item.confirmation_level == "internal"
    assert internal_item.provenance == "ai_extracted"
    assert [change.change_type for change in internal_changes] == ["confirmed"]
    assert internal_record.source_state_version == 1
    assert internal_record.result_state_version == 2
    repeated_state, repeated_changes, repeated_record = applier.apply(
        state,
        _confirmation(confirmation_level="internal", confirmed_by="presales-owner"),
    )
    assert repeated_state == internal_state
    assert repeated_changes == internal_changes
    assert repeated_record == internal_record

    customer_state, _, customer_record = applier.apply(
        internal_state,
        _confirmation(state_version=2, confirmation_level="customer"),
    )
    assert customer_state.state_version == 3
    assert customer_state.items[0].confirmation_level == "customer"
    assert customer_state.items[0].provenance == "ai_extracted"
    assert customer_record.confirmation_id != internal_record.confirmation_id


def test_internal_confirmation_cannot_resolve_or_reject_open_customer_conflict() -> None:
    state, conflict = _approval_conflict()
    applier = RequirementConfirmationApplier()
    internal, _, _ = applier.apply(
        state,
        _confirmation(confirmation_level="internal"),
    )

    assert internal.conflicts[0] == conflict
    assert next(item for item in internal.items if item.requirement_id == "approval-800").confirmation_level == "internal"
    with pytest.raises(ValueError, match="internal confirmation cannot reject"):
        applier.apply(
            state,
            _confirmation(
                confirmation_level="internal",
                confirmed_requirement_ids=[],
                rejected_requirement_ids=["approval-500"],
            ),
        )


def test_customer_selects_one_conflict_winner_and_preserves_loser_history() -> None:
    state, _ = _approval_conflict()
    resolved, changes, record = RequirementConfirmationApplier().apply(state, _confirmation())

    winner = next(item for item in resolved.items if item.requirement_id == "approval-800")
    loser = next(item for item in resolved.items if item.requirement_id == "approval-500")
    assert winner.status == "confirmed" and winner.confirmation_level == "customer"
    assert winner.provenance == "ai_extracted"
    assert loser.status == "superseded"
    assert resolved.conflicts[0].status == "resolved"
    assert resolved.conflicts[0].resolution_requirement_id == winner.requirement_id
    assert {change.change_type for change in changes} == {"confirmed", "resolved", "superseded"}
    assert record.confirmation_id.startswith("confirmation-")


def test_customer_cannot_confirm_two_conflict_winners_but_can_reject_all() -> None:
    state, _ = _approval_conflict()
    applier = RequirementConfirmationApplier()
    with pytest.raises(ValueError, match="multiple winners"):
        applier.apply(
            state,
            _confirmation(confirmed_requirement_ids=["approval-500", "approval-800"]),
        )

    rejected, _, _ = applier.apply(
        state,
        _confirmation(
            confirmed_requirement_ids=[],
            rejected_requirement_ids=["approval-500", "approval-800"],
        ),
    )
    assert {item.status for item in rejected.items} == {"rejected"}
    assert rejected.conflicts[0].status == "resolved"
    assert rejected.conflicts[0].resolution_requirement_id is None
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    gaps = GapDetector().detect(rejected, skill, rejected.conflicts)
    assert any(gap.category == "approval" and gap.gap_type == "missing" for gap in gaps)


def test_three_value_conflict_partial_reject_and_single_winner_are_safe() -> None:
    state = _three_value_conflict()
    applier = RequirementConfirmationApplier()
    partial, _, _ = applier.apply(
        state,
        _confirmation(
            confirmed_requirement_ids=[], rejected_requirement_ids=["approval-a"],
        ),
    )
    assert next(item for item in partial.items if item.requirement_id == "approval-a").status == "rejected"
    assert partial.conflicts[0].status == "open"
    refreshed = ConflictDetector().detect(partial)
    active = [conflict for conflict in refreshed if conflict.status == "open"]
    assert len(active) == 1
    assert active[0].requirement_ids == ["approval-b", "approval-c"]

    winner, _, _ = applier.apply(
        state,
        _confirmation(confirmed_requirement_ids=["approval-b"]),
    )
    assert next(item for item in winner.items if item.requirement_id == "approval-b").confirmation_level == "customer"
    assert {
        item.requirement_id
        for item in winner.items
        if item.status == "superseded"
    } == {"approval-a", "approval-c"}
    assert winner.conflicts[0].status == "resolved"
    assert winner.conflicts[0].resolution_requirement_id == "approval-b"

    for two_winners in (["approval-a", "approval-b"], ["approval-b", "approval-c"]):
        with pytest.raises(ValueError, match="multiple winners"):
            applier.apply(state, _confirmation(confirmed_requirement_ids=two_winners))


def test_confirmation_rejects_stale_conflict_snapshot() -> None:
    state = _state(
        _item("approval-a", "500000"),
        _item("approval-b", "800000", status="conflicted"),
        conflicts=[],
    )
    with pytest.raises(ValueError, match="stale conflict"):
        RequirementConfirmationApplier().apply(
            state,
            _confirmation(confirmed_requirement_ids=["approval-b"]),
        )


def test_confirmation_id_is_order_invariant_and_result_is_idempotent_by_version() -> None:
    items = (
        _item("scope-a", "phase one", category="scope"),
        _item("budget-b", "800000", category="budget"),
        _item("time-c", "six months", category="time"),
    )
    state = _state(*items, version=5)
    first_action = _confirmation(
        state_version=5,
        confirmed_requirement_ids=["scope-a", "budget-b", "time-c"],
    )
    second_action = _confirmation(
        state_version=5,
        confirmed_requirement_ids=["time-c", "scope-a", "budget-b"],
    )
    applier = RequirementConfirmationApplier()
    first_state, _, first_record = applier.apply(state, first_action)
    second_state, _, second_record = applier.apply(state, second_action)

    assert first_state == second_state
    assert first_record.confirmation_id == second_record.confirmation_id
    with pytest.raises(ValueError, match="stale"):
        applier.apply(first_state, first_action)


def test_rejection_and_modification_order_do_not_change_confirmation_identity() -> None:
    items = (
        _item("scope-a", "phase one", category="scope"),
        _item("budget-b", "800000", category="budget"),
        _item("time-c", "six months", category="time"),
        _item("metric-d", "processing_time", category="target_metric"),
    )
    state = _state(*items)
    modifications = [
        RequirementModification(
            target_requirement_id="time-c", new_value="four months", reason="updated plan",
        ),
        RequirementModification(
            target_requirement_id="metric-d", new_value="processing_time_minutes",
            reason="measurable metric",
        ),
    ]
    first = _confirmation(
        confirmed_requirement_ids=[], rejected_requirement_ids=["scope-a", "budget-b"],
        modifications=modifications,
    )
    second = _confirmation(
        confirmed_requirement_ids=[], rejected_requirement_ids=["budget-b", "scope-a"],
        modifications=list(reversed(modifications)),
    )
    applier = RequirementConfirmationApplier()
    first_state, _, first_record = applier.apply(state, first)
    second_state, _, second_record = applier.apply(state, second)

    assert first_state == second_state
    assert first_record.confirmation_id == second_record.confirmation_id


def test_human_modification_supersedes_old_item_and_requires_second_customer_confirmation() -> None:
    old = _item("metric-old", "processing_time", category="target_metric")
    state = _state(old)
    modification = RequirementModification(
        target_requirement_id=old.requirement_id,
        new_value="processing_time_minutes",
        reason="make the metric measurable",
    )
    modified, changes, _ = RequirementConfirmationApplier().apply(
        state,
        _confirmation(
            confirmation_level="customer",
            confirmed_requirement_ids=[],
            modifications=[modification],
        ),
    )

    old_after = next(item for item in modified.items if item.requirement_id == old.requirement_id)
    new_item = next(item for item in modified.items if item.requirement_id != old.requirement_id)
    assert old_after.status == "superseded"
    assert new_item.value == "processing_time_minutes"
    assert new_item.provenance == "human_modified"
    assert new_item.status == "confirmed"
    assert new_item.confirmation_level == "internal"
    assert old.requirement_id in new_item.supersedes_requirement_ids
    assert new_item.source_refs == old.source_refs
    assert new_item.source_refs[0].excerpt == "processing_time"
    assert {change.change_type for change in changes} == {"added", "superseded"}

    customer, _, _ = RequirementConfirmationApplier().apply(
        modified,
        _confirmation(
            state_version=2,
            confirmed_requirement_ids=[new_item.requirement_id],
        ),
    )
    customer_item = next(item for item in customer.items if item.requirement_id == new_item.requirement_id)
    assert customer_item.confirmation_level == "customer"
    assert customer_item.provenance == "human_modified"


def test_human_modification_id_and_evidence_lineage_are_deterministic() -> None:
    old = _item("metric-old", "processing_time", category="target_metric")
    state = _state(old)
    action = _confirmation(
        confirmed_requirement_ids=[],
        modifications=[
            RequirementModification(
                target_requirement_id=old.requirement_id,
                new_value="processing_time_minutes",
                reason="make the metric measurable",
            )
        ],
    )
    applier = RequirementConfirmationApplier()
    first, _, first_record = applier.apply(state, action)
    second, _, second_record = applier.apply(state, action)
    first_new = next(item for item in first.items if item.requirement_id != old.requirement_id)
    second_new = next(item for item in second.items if item.requirement_id != old.requirement_id)

    assert first_new.requirement_id == second_new.requirement_id
    assert first_new.source_refs == old.source_refs
    assert first_record == second_record


def test_customer_confirmation_preserves_all_supported_provenance_values() -> None:
    items = (
        _item("extracted", "one", category="scope", provenance="ai_extracted"),
        _item("inferred", "two", category="budget", provenance="ai_inferred"),
        _item("human", "three", category="time", provenance="human_modified"),
    )
    confirmed, _, _ = RequirementConfirmationApplier().apply(
        _state(*items),
        _confirmation(confirmed_requirement_ids=[item.requirement_id for item in items]),
    )
    assert {
        item.requirement_id: item.provenance for item in confirmed.items
    } == {
        "extracted": "ai_extracted",
        "inferred": "ai_inferred",
        "human": "human_modified",
    }


def test_human_modification_cannot_target_open_conflict_or_make_no_actual_change() -> None:
    state, _ = _approval_conflict()
    applier = RequirementConfirmationApplier()
    with pytest.raises(ValueError, match="open conflict"):
        applier.apply(
            state,
            _confirmation(
                confirmed_requirement_ids=[],
                modifications=[
                    RequirementModification(
                        target_requirement_id="approval-800",
                        new_value="900000",
                        reason="manual guess",
                    )
                ],
            ),
        )
    plain = _state(_item("approval-800", "800000"))
    with pytest.raises(ValueError, match="does not change"):
        applier.apply(
            plain,
            _confirmation(
                confirmed_requirement_ids=[],
                modifications=[
                    RequirementModification(
                        target_requirement_id="approval-800",
                        new_value="800000",
                        reason="same value",
                    )
                ],
            ),
        )


def test_typed_human_modification_preserves_contract_closure() -> None:
    process = RequirementItem(
        requirement_id="process-old", category="current_process", subject="review",
        value="manual review", provenance="ai_extracted", status="pending",
        confirmation_level="none", confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt="manual review")],
        process_detail={
            "process_node_id": "node-review", "name": "review", "actor": "buyer",
            "node_type": "human", "description": "manual review",
        },
    )
    state = _state(process)
    modified, _, _ = RequirementConfirmationApplier().apply(
        state,
        _confirmation(
            confirmed_requirement_ids=[],
            modifications=[
                RequirementModification(
                    target_requirement_id=process.requirement_id,
                    new_value="review with AI assistance",
                    process_detail={
                        "process_node_id": "node-review", "name": "review",
                        "actor": "buyer", "node_type": "ai",
                        "description": "AI-assisted review",
                    },
                    reason="reflect the reviewed future process",
                )
            ],
        ),
    )
    new_item = next(item for item in modified.items if item.requirement_id != process.requirement_id)
    assert new_item.category == "current_process"
    assert new_item.process_detail is not None
    assert new_item.pain_point_detail is None
