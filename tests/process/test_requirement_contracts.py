import pytest
from pydantic import ValidationError

from backend.app.contracts.requirement_intelligence import (
    ContextEvidence,
    CustomerOrganizationContext,
    CustomerContextPackage,
    CustomerSourceChunk,
    CustomerSourceRecord,
    PainPointObservation,
    ProcessObservation,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)


def _source(source_id: str = "source-1", project_id: str = "project-1") -> CustomerSourceRecord:
    return CustomerSourceRecord(
        source_id=source_id,
        project_id=project_id,
        source_type="meeting_minutes",
        title="Meeting",
        inline_content="Customer confirmed the current process.",
    )


def _item(**updates: object) -> RequirementItem:
    payload: dict[str, object] = {
        "requirement_id": "req-1",
        "category": "business_goal",
        "subject": "procurement",
        "value": "reduce review time",
        "provenance": "customer_raw",
        "status": "pending",
        "confirmation_level": "none",
        "confidence": 0.8,
        "source_refs": [
            RequirementSourceRef(
                source_id="source-1", locator="p1", excerpt="reduce review time"
            )
        ],
    }
    payload.update(updates)
    return RequirementItem(**payload)


def test_sources_are_strict_project_scoped_and_support_document_chunks() -> None:
    document = CustomerSourceRecord(
        source_id="source-document",
        project_id="project-1",
        source_type="bid_document",
        title="Bid document",
        document_ref="documents/bid.pdf",
        chunks=[CustomerSourceChunk(chunk_id="chunk-1", text="private deployment", locator="p.3")],
    )
    package = CustomerContextPackage(project_id="project-1", sources=[_source(), document])

    assert package.source_ids == ["source-1", "source-document"]
    with pytest.raises(ValidationError):
        CustomerSourceRecord(
            source_id="bad", project_id="project-1", source_type="email", title="bad"
        )
    with pytest.raises(ValidationError):
        CustomerContextPackage(project_id="project-1", sources=[_source(project_id="other")])
    with pytest.raises(ValidationError):
        CustomerSourceRecord(
            source_id="strict", project_id="project-1", source_type="email", title="strict",
            inline_content="content", extra_field="forbidden"
        )


def test_requirement_category_truth_confirmation_and_typed_details_are_enforced() -> None:
    assert _item(category="ext:procurement:tender_method").category == "ext:procurement:tender_method"
    with pytest.raises(ValidationError, match="category"):
        _item(category="ext:Procurement:bad key")
    for invalid_category in ("ext:", "ext:automotive:", "ext::key", "ext:automotive:bad key"):
        with pytest.raises(ValidationError, match="category"):
            _item(category=invalid_category)
    with pytest.raises(ValidationError, match="source"):
        _item(status="confirmed", source_refs=[])
    with pytest.raises(ValidationError, match="process_detail"):
        _item(category="current_process")
    process_item = _item(
        category="current_process",
        process_detail=ProcessObservation(
            process_node_id="node-1",
            name="Review", actor="buyer", node_type="human", description="manual review"
        ),
    )
    assert process_item.process_detail is not None
    with pytest.raises(ValidationError, match="pain_point_detail"):
        _item(category="pain_point")
    pain_item = _item(
        category="pain_point",
        pain_point_detail=PainPointObservation(
            pain_point_id="pain-1", description="slow", severity="high", affected_process_node_ids=["node-1"]
        ),
    )
    assert pain_item.pain_point_detail is not None
    with pytest.raises(ValidationError, match="current_process"):
        _item(
            category="current_process",
            pain_point_detail=PainPointObservation(pain_point_id="x", description="x", severity="low"),
        )
    with pytest.raises(ValidationError, match="typed categories"):
        _item(
            process_detail=ProcessObservation(
                process_node_id="x", name="x", actor="x", node_type="human", description="x"
            )
        )
    with pytest.raises(ValidationError, match="customer confirmation"):
        _item(status="pending", confirmation_level="customer")
    assert _item(status="confirmed", confirmation_level="internal").confirmation_level == "internal"


def test_requirement_state_enforces_reference_closure_and_keeps_context_evidence_separate() -> None:
    item = _item()
    state = RequirementState(
        project_id="project-1", state_version=1, source_ids=["source-1"], items=[item]
    )
    assert state.items == [item]
    with pytest.raises(ValidationError, match="source_ids"):
        RequirementState(project_id="project-1", state_version=1, source_ids=[], items=[item])
    package = CustomerContextPackage(
        project_id="project-1",
        sources=[_source()],
        context_evidence=[
            ContextEvidence(
                evidence_id="ctx-1", evidence_type="external_benchmark", title="Benchmark",
                source_name="Public report", source_ref="https://example.invalid/report",
                reliability="high", summary="Industry reference only"
            )
        ],
    )
    assert package.context_evidence[0].evidence_id == "ctx-1"


def test_requirement_source_reference_cannot_escape_project_source_closure() -> None:
    foreign_item = _item(
        source_refs=[RequirementSourceRef(source_id="foreign-source", locator=None, excerpt="foreign")]
    )
    with pytest.raises(ValidationError, match="source_refs"):
        RequirementState(
            project_id="project-1", state_version=1, source_ids=["source-1"], items=[foreign_item]
        )


def test_state_keeps_customer_context_and_typed_observations_without_becoming_process_spec() -> None:
    process_item = _item(
        requirement_id="process-1",
        category="current_process",
        process_detail=ProcessObservation(
            process_node_id="node-1", name="Review", actor="buyer", node_type="human", description="manual"
        ),
    )
    pain_item = _item(
        requirement_id="pain-1",
        category="pain_point",
        pain_point_detail=PainPointObservation(
            pain_point_id="pain-1", description="slow", severity="high", affected_process_node_ids=["node-1"]
        ),
    )
    state = RequirementState(
        project_id="project-1", state_version=1, source_ids=["source-1"], items=[process_item, pain_item],
        organization=CustomerOrganizationContext(organization_name="Customer"),
        created_at="2026-08-10T00:00:00Z", updated_at="2026-08-10T00:00:00Z",
    )
    assert [item.process_node_id for item in state.process_observations] == ["node-1"]
    assert [item.pain_point_id for item in state.pain_observations] == ["pain-1"]
    assert state.organization.organization_name == "Customer"
