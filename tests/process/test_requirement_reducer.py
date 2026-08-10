from backend.app.contracts.requirement_intelligence import (
    ContextEvidence,
    CustomerContextPackage,
    CustomerSourceRecord,
    RequirementItem,
    RequirementSourceRef,
)
from backend.app.process.requirement_reducer import RequirementReducer


def _context(*source_ids: str) -> CustomerContextPackage:
    return CustomerContextPackage(
        project_id="project-1",
        sources=[
            CustomerSourceRecord(
                source_id=source_id,
                project_id="project-1",
                source_type="meeting_minutes",
                title=source_id,
                inline_content=f"content for {source_id}",
            )
            for source_id in source_ids
        ],
    )


def _candidate(value: str = "500000", **updates: object) -> RequirementItem:
    payload: dict[str, object] = {
        "requirement_id": "",
        "category": "approval",
        "subject": "approval threshold",
        "value": value,
        "provenance": "customer_raw",
        "status": "pending",
        "confirmation_level": "none",
        "confidence": 0.9,
        "source_refs": [RequirementSourceRef(source_id="source-1", locator=None, excerpt=value)],
    }
    payload.update(updates)
    return RequirementItem(**payload)


def test_reducer_is_deterministic_deduplicates_and_appends_sources() -> None:
    reducer = RequirementReducer()
    context = _context("source-1", "source-2")
    candidate = _candidate()

    first, first_changes = reducer.reduce(None, [candidate], context)
    second, second_changes = reducer.reduce(None, [candidate], context)

    assert first.model_dump() == second.model_dump()
    assert [change.model_dump() for change in first_changes] == [change.model_dump() for change in second_changes]
    duplicate = candidate.model_copy(
        update={"source_refs": [RequirementSourceRef(source_id="source-2", locator=None, excerpt="500000")]}
    )
    updated, changes = reducer.reduce(first, [duplicate], context)
    assert len(updated.items) == 1
    assert {ref.source_id for ref in updated.items[0].source_refs} == {"source-1", "source-2"}
    assert updated.state_version == 2
    assert [change.change_type for change in changes] == ["updated"]
    no_op, no_op_changes = reducer.reduce(updated, [duplicate], context)
    assert no_op.items == updated.items
    assert no_op_changes == []


def test_inferred_and_internal_judgments_do_not_auto_confirm_customer_truth() -> None:
    reducer = RequirementReducer()
    context = _context("source-1")
    for provenance in ("ai_inferred", "sales_judgment", "presales_judgment"):
        state, _ = reducer.reduce(
            None,
            [_candidate(provenance=provenance, status="confirmed", confirmation_level="customer")],
            context,
        )
        assert state.items[0].status == "pending"
        assert state.items[0].confirmation_level == "none"


def test_high_confidence_does_not_change_confirmation_semantics() -> None:
    state, _ = RequirementReducer().reduce(
        None,
        [_candidate(provenance="ai_inferred", status="confirmed", confirmation_level="customer", confidence=1.0)],
        _context("source-1"),
    )
    assert state.items[0].status == "pending"
    assert state.items[0].confirmation_level == "none"


def test_confirmed_conflict_creates_candidate_and_preserves_existing_fact() -> None:
    reducer = RequirementReducer()
    context = _context("source-1")
    initial, _ = reducer.reduce(
        None,
        [_candidate(status="confirmed", confirmation_level="customer")],
        context,
    )
    conflicting, changes = reducer.reduce(initial, [_candidate(value="800000")], context)

    assert any(item.value == "500000" and item.status == "confirmed" for item in conflicting.items)
    assert any(item.value == "800000" and item.status == "conflicted" for item in conflicting.items)
    assert len(conflicting.conflicts) == 1
    assert any(change.change_type == "conflicted" for change in changes)
    candidate = next(item for item in conflicting.items if item.value == "800000")
    resolved, resolved_changes = reducer.reduce(
        conflicting,
        [
            _candidate(
                value="800000",
                status="confirmed",
                confirmation_level="customer",
                supersedes_requirement_ids=[initial.items[0].requirement_id],
            )
        ],
        context,
    )
    old = next(item for item in resolved.items if item.value == "500000")
    new = next(item for item in resolved.items if item.value == "800000")
    assert old.status == "superseded"
    assert new.requirement_id == candidate.requirement_id
    assert new.status == "confirmed" and new.confirmation_level == "customer"
    assert new.supersedes_requirement_ids == [old.requirement_id]
    assert resolved.conflicts[0].status == "resolved"
    assert any(change.change_type == "superseded" for change in resolved_changes)
    assert any(change.change_type == "confirmed" for change in resolved_changes)


def test_superseded_history_is_preserved() -> None:
    reducer = RequirementReducer()
    context = _context("source-1")
    first, _ = reducer.reduce(None, [_candidate()], context)
    replacement = _candidate(
        value="800000", supersedes_requirement_ids=[first.items[0].requirement_id]
    )
    second, changes = reducer.reduce(first, [replacement], context)

    assert len(second.items) == 2
    assert next(item for item in second.items if item.value == "500000").status == "superseded"
    assert any(change.change_type == "superseded" for change in changes)


def test_context_evidence_never_becomes_a_requirement_item() -> None:
    reducer = RequirementReducer()
    context = _context("source-1").model_copy(
        update={
            "context_evidence": [
                ContextEvidence(
                    evidence_id="ctx-1", evidence_type="external_benchmark", title="Benchmark",
                    source_name="public", source_ref="reference", reliability="high", summary="context only"
                )
            ]
        }
    )
    state, changes = reducer.reduce(None, [], context)
    assert state.items == []
    assert changes == []
