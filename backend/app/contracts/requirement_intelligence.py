"""Strict, deterministic contracts for Requirement Intelligence R-M1."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.contracts.common import StrictModel


CORE_REQUIREMENT_CATEGORIES = {
    "customer_context",
    "industry",
    "department",
    "business_goal",
    "pain_point",
    "role",
    "current_process",
    "available_data",
    "existing_system",
    "business_rule",
    "security",
    "approval",
    "budget",
    "time",
    "data",
    "risk",
    "target_metric",
    "integration",
    "scope",
    "deliverable",
}
_EXT_CATEGORY = re.compile(r"^ext:[a-z0-9_-]+:[a-z0-9_-]+$")
RequirementCategory = str


def _non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_requirement_category(value: str) -> str:
    if value not in CORE_REQUIREMENT_CATEGORIES and not _EXT_CATEGORY.fullmatch(value):
        raise ValueError("category must be a core category or ext:<domain>:<key>")
    return value


class CustomerSourceChunk(StrictModel):
    chunk_id: str
    text: str
    locator: str | None = None

    _validate_chunk_id = field_validator("chunk_id")(lambda value: _non_empty(value, "chunk_id"))
    _validate_text = field_validator("text")(lambda value: _non_empty(value, "text"))


class CustomerContact(StrictModel):
    contact_id: str
    name: str
    role: str | None = None
    department: str | None = None
    influence: Literal["unknown", "user", "influencer", "decision_maker"] = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerOrganizationContext(StrictModel):
    organization_name: str
    industry: str | None = None
    department: str | None = None
    organization_notes: list[str] = Field(default_factory=list)


class CustomerSourceRecord(StrictModel):
    source_id: str
    project_id: str
    source_type: Literal[
        "customer_profile",
        "conversation",
        "meeting_minutes",
        "email",
        "historical_communication",
        "bid_document",
        "requirement_document",
        "customer_attachment",
        "crm_record",
        "project_status",
        "sales_note",
    ]
    title: str
    inline_content: str | None = None
    document_ref: str | None = None
    chunks: list[CustomerSourceChunk] = Field(default_factory=list)
    occurred_at: str | None = None
    author_role: str | None = None
    locator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _validate_source_id = field_validator("source_id")(lambda value: _non_empty(value, "source_id"))
    _validate_project_id = field_validator("project_id")(lambda value: _non_empty(value, "project_id"))
    _validate_title = field_validator("title")(lambda value: _non_empty(value, "title"))

    @model_validator(mode="after")
    def validate_content(self) -> "CustomerSourceRecord":
        if not any(
            (
                self.inline_content and self.inline_content.strip(),
                self.document_ref and self.document_ref.strip(),
                self.chunks,
            )
        ):
            raise ValueError("CustomerSourceRecord requires inline_content, document_ref, or chunks")
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("CustomerSourceRecord chunk_id values must be unique")
        return self


class ContextEvidence(StrictModel):
    evidence_id: str
    evidence_type: Literal[
        "internal_knowhow",
        "internal_solution",
        "external_policy",
        "external_benchmark",
        "public_business_data",
    ]
    title: str
    source_name: str
    source_ref: str
    published_at: str | None = None
    reliability: Literal["low", "medium", "high"]
    applicable_scope: list[str] = Field(default_factory=list)
    summary: str


class CustomerContextPackage(StrictModel):
    project_id: str
    organization: CustomerOrganizationContext | None = None
    contacts: list[CustomerContact] = Field(default_factory=list)
    sources: list[CustomerSourceRecord]
    previous_state_version: int | None = Field(default=None, ge=1)
    requirement_skill_ids: list[str] = Field(default_factory=list)
    context_evidence: list[ContextEvidence] = Field(default_factory=list)

    @property
    def source_ids(self) -> list[str]:
        return [source.source_id for source in self.sources]

    @model_validator(mode="after")
    def validate_project_closure(self) -> "CustomerContextPackage":
        if not self.sources:
            raise ValueError("CustomerContextPackage requires at least one source")
        if any(source.project_id != self.project_id for source in self.sources):
            raise ValueError("CustomerContextPackage source project_id must match package project_id")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("CustomerContextPackage source_id values must be unique")
        contact_ids = [contact.contact_id for contact in self.contacts]
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("CustomerContextPackage contact_id values must be unique")
        return self


class RequirementSourceRef(StrictModel):
    source_id: str
    locator: str | None = None
    excerpt: str

    _validate_source_id = field_validator("source_id")(lambda value: _non_empty(value, "source_id"))
    _validate_excerpt = field_validator("excerpt")(lambda value: _non_empty(value, "excerpt"))


class ProcessObservation(StrictModel):
    process_node_id: str
    name: str
    actor: str
    node_type: Literal["human", "system", "ai"]
    description: str
    next_node_ids: list[str] = Field(default_factory=list)


class PainPointObservation(StrictModel):
    pain_point_id: str
    description: str
    severity: Literal["low", "medium", "high"]
    affected_process_node_ids: list[str] = Field(default_factory=list)


class RequirementItem(StrictModel):
    requirement_id: str = ""
    category: RequirementCategory
    subject: str
    value: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    provenance: Literal[
        "customer_raw",
        "ai_extracted",
        "ai_inferred",
        "human_modified",
        "sales_judgment",
        "presales_judgment",
    ]
    status: Literal["pending", "confirmed", "rejected", "conflicted", "superseded"]
    confirmation_level: Literal["none", "internal", "customer"] = "none"
    confidence: float = Field(ge=0, le=1)
    source_refs: list[RequirementSourceRef]
    process_detail: ProcessObservation | None = None
    pain_point_detail: PainPointObservation | None = None
    supersedes_requirement_ids: list[str] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        return _validate_requirement_category(value)

    @model_validator(mode="after")
    def validate_truth_semantics(self) -> "RequirementItem":
        if self.status == "confirmed" and not self.source_refs:
            raise ValueError("confirmed RequirementItem requires at least one source reference")
        if self.confirmation_level == "customer" and self.status != "confirmed":
            raise ValueError("customer confirmation requires status=confirmed")
        if self.category == "current_process":
            if self.process_detail is None or self.pain_point_detail is not None:
                raise ValueError("current_process requires process_detail only")
        elif self.category == "pain_point":
            if self.pain_point_detail is None or self.process_detail is not None:
                raise ValueError("pain_point requires pain_point_detail only")
        elif self.process_detail is not None or self.pain_point_detail is not None:
            raise ValueError("process_detail and pain_point_detail are only valid for typed categories")
        return self


class ExtractedRequirementCandidate(StrictModel):
    """Narrow, untrusted LLM extraction payload; it is not Requirement Truth."""

    category: RequirementCategory
    subject: str
    value: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    candidate_kind: Literal["extracted", "inferred"]
    evidence_quote: str
    process_detail: ProcessObservation | None = None
    pain_point_detail: PainPointObservation | None = None

    _validate_category = field_validator("category")(_validate_requirement_category)
    _validate_subject = field_validator("subject")(lambda value: _non_empty(value, "subject"))
    _validate_value = field_validator("value")(lambda value: _non_empty(value, "value"))
    _validate_quote = field_validator("evidence_quote")(lambda value: _non_empty(value, "evidence_quote"))

    @model_validator(mode="after")
    def validate_typed_details(self) -> "ExtractedRequirementCandidate":
        if self.category == "current_process":
            if self.process_detail is None or self.pain_point_detail is not None:
                raise ValueError("current_process requires process_detail only")
        elif self.category == "pain_point":
            if self.pain_point_detail is None or self.process_detail is not None:
                raise ValueError("pain_point requires pain_point_detail only")
        elif self.process_detail is not None or self.pain_point_detail is not None:
            raise ValueError("process_detail and pain_point_detail are only valid for typed categories")
        return self


class RequirementExtractionWarning(StrictModel):
    code: Literal[
        "document_text_unavailable",
        "empty_response",
        "evidence_not_found",
        "invalid_candidate",
        "invalid_json",
        "provider_warning",
    ]
    message: str
    source_id: str
    locator: str | None = None

    _validate_message = field_validator("message")(lambda value: _non_empty(value, "message"))
    _validate_source_id = field_validator("source_id")(lambda value: _non_empty(value, "source_id"))


class RequirementExtractionResult(StrictModel):
    candidates: list[RequirementItem] = Field(default_factory=list)
    warnings: list[RequirementExtractionWarning] = Field(default_factory=list)


class SkillRequirementRule(StrictModel):
    rule_id: str
    category: RequirementCategory
    requirement_level: Literal["preliminary_required", "formal_required", "recommended"]
    missing_blocks_preliminary: bool
    unconfirmed_blocks_formal: bool
    requires_customer_confirmation: bool
    hard_constraint: bool
    question_template: str
    description: str

    _validate_rule_id = field_validator("rule_id")(lambda value: _non_empty(value, "rule_id"))
    _validate_category = field_validator("category")(_validate_requirement_category)
    _validate_question = field_validator("question_template")(
        lambda value: _non_empty(value, "question_template")
    )
    _validate_description = field_validator("description")(
        lambda value: _non_empty(value, "description")
    )


class CompletenessDimension(StrictModel):
    dimension_id: str
    categories: list[RequirementCategory]
    weight: float = Field(gt=0, le=100)

    _validate_dimension_id = field_validator("dimension_id")(
        lambda value: _non_empty(value, "dimension_id")
    )

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("categories must not be empty")
        if len(values) != len(set(values)):
            raise ValueError("categories must be unique")
        return [_validate_requirement_category(value) for value in values]


class RequirementSkill(StrictModel):
    skill_id: str
    version: str
    domain: str
    extends_skill_id: str | None = None
    rules: list[SkillRequirementRule] = Field(default_factory=list)
    completeness_dimensions: list[CompletenessDimension] = Field(default_factory=list)
    procurement_stages: list[str] = Field(default_factory=list)
    probes: list[str] = Field(default_factory=list)

    _validate_skill_id = field_validator("skill_id")(lambda value: _non_empty(value, "skill_id"))
    _validate_version = field_validator("version")(lambda value: _non_empty(value, "version"))
    _validate_domain = field_validator("domain")(lambda value: _non_empty(value, "domain"))

    @model_validator(mode="after")
    def validate_skill_closure(self) -> "RequirementSkill":
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("RequirementSkill rule_id values must be unique")
        dimension_ids = [dimension.dimension_id for dimension in self.completeness_dimensions]
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError("RequirementSkill dimension_id values must be unique")
        if len(self.procurement_stages) != len(set(self.procurement_stages)):
            raise ValueError("RequirementSkill procurement_stages must be unique")
        if len(self.probes) != len(set(self.probes)):
            raise ValueError("RequirementSkill probes must be unique")
        return self


class ReadinessAssessment(StrictModel):
    stage: Literal["DISCOVERY", "PRELIMINARY_READY", "CONFIRMED_READY"]
    completeness_score: float = Field(ge=0, le=100)
    blocking_gap_ids: list[str] = Field(default_factory=list)
    non_blocking_gap_ids: list[str] = Field(default_factory=list)
    open_conflict_ids: list[str] = Field(default_factory=list)
    can_generate_preliminary_solution: bool
    can_generate_formal_solution: bool
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stage_flags(self) -> "ReadinessAssessment":
        expected = {
            "DISCOVERY": (False, False),
            "PRELIMINARY_READY": (True, False),
            "CONFIRMED_READY": (True, True),
        }[self.stage]
        actual = (self.can_generate_preliminary_solution, self.can_generate_formal_solution)
        if actual != expected:
            raise ValueError("readiness capability flags must match stage")
        return self


class RequirementGap(StrictModel):
    gap_id: str
    category: RequirementCategory
    gap_type: Literal["missing", "ambiguous", "unconfirmed", "conflicted"]
    description: str
    blocking: bool
    reason: str
    related_requirement_ids: list[str] = Field(default_factory=list)

    _validate_category = field_validator("category")(_validate_requirement_category)


class RequirementConflict(StrictModel):
    conflict_id: str
    category: RequirementCategory
    requirement_ids: list[str]
    description: str
    severity: Literal["low", "medium", "high"]
    status: Literal["open", "resolved"]
    resolution_requirement_id: str | None = None

    _validate_category = field_validator("category")(_validate_requirement_category)


class RequirementState(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    state_version: int = Field(ge=1)
    source_ids: list[str]
    items: list[RequirementItem] = Field(default_factory=list)
    gaps: list[RequirementGap] = Field(default_factory=list)
    conflicts: list[RequirementConflict] = Field(default_factory=list)
    selected_skill_id: str | None = None
    organization: CustomerOrganizationContext | None = None
    contacts: list[CustomerContact] = Field(default_factory=list)
    process_observations: list[ProcessObservation] = Field(default_factory=list)
    pain_observations: list[PainPointObservation] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    @model_validator(mode="after")
    def validate_closure(self) -> "RequirementState":
        item_ids = [item.requirement_id for item in self.items]
        if any(not item_id for item_id in item_ids):
            raise ValueError("RequirementState items require generated requirement_id values")
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("RequirementState requirement_id values must be unique")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("RequirementState source_ids must be unique")
        if any(not source_id.strip() for source_id in self.source_ids):
            raise ValueError("RequirementState source_ids must not contain blanks")
        contact_ids = [contact.contact_id for contact in self.contacts]
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("RequirementState contact_id values must be unique")
        source_ids = set(self.source_ids)
        for item in self.items:
            if not {ref.source_id for ref in item.source_refs} <= source_ids:
                raise ValueError("RequirementState item source_refs must be contained in source_ids")
            if not set(item.supersedes_requirement_ids) <= set(item_ids):
                raise ValueError("RequirementState supersedes_requirement_ids must reference existing items")
            if item.requirement_id in item.supersedes_requirement_ids:
                raise ValueError("RequirementState item cannot supersede itself")
        for conflict in self.conflicts:
            if not set(conflict.requirement_ids) <= set(item_ids):
                raise ValueError("RequirementState conflict requirement_ids must reference existing items")
            if conflict.resolution_requirement_id and conflict.resolution_requirement_id not in item_ids:
                raise ValueError("RequirementState conflict resolution_requirement_id must reference an item")
        typed_process = sorted(
            (item.process_detail for item in self.items if item.process_detail is not None),
            key=lambda detail: detail.process_node_id,
        )
        typed_pain = sorted(
            (item.pain_point_detail for item in self.items if item.pain_point_detail is not None),
            key=lambda detail: detail.pain_point_id,
        )
        if self.process_observations and self.process_observations != typed_process:
            raise ValueError("RequirementState process_observations must match current_process items")
        if self.pain_observations and self.pain_observations != typed_pain:
            raise ValueError("RequirementState pain_observations must match pain_point items")
        if not self.process_observations:
            self.process_observations = typed_process
        if not self.pain_observations:
            self.pain_observations = typed_pain
        return self


class RequirementChange(StrictModel):
    requirement_id: str
    change_type: Literal["added", "updated", "confirmed", "rejected", "conflicted", "resolved", "superseded"]
    before_value: str | None = None
    after_value: str | None = None
    explanation: str


class NextQuestion(StrictModel):
    question_id: str
    text: str
    target_category: RequirementCategory
    priority: Literal["critical", "high", "medium", "low"]
    blocking: bool
    reason: str
    related_gap_ids: list[str] = Field(default_factory=list)
    related_conflict_ids: list[str] = Field(default_factory=list)

    _validate_question_id = field_validator("question_id")(
        lambda value: _non_empty(value, "question_id")
    )
    _validate_text = field_validator("text")(lambda value: _non_empty(value, "text"))
    _validate_target_category = field_validator("target_category")(_validate_requirement_category)
    _validate_reason = field_validator("reason")(lambda value: _non_empty(value, "reason"))

    @model_validator(mode="after")
    def validate_references(self) -> "NextQuestion":
        for field_name, values in (
            ("related_gap_ids", self.related_gap_ids),
            ("related_conflict_ids", self.related_conflict_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        if not self.related_gap_ids and not self.related_conflict_ids:
            raise ValueError("NextQuestion requires a related gap or conflict")
        return self


class QuestionHistoryEntry(StrictModel):
    question_id: str
    asked_state_version: int = Field(ge=1)
    status: Literal["asked", "answered", "dismissed"]
    answer_source_ids: list[str] = Field(default_factory=list)

    _validate_question_id = field_validator("question_id")(
        lambda value: _non_empty(value, "question_id")
    )

    @field_validator("answer_source_ids")
    @classmethod
    def validate_answer_sources(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("answer_source_ids values must be unique")
        return [_non_empty(value, "answer_source_id") for value in values]


class RequirementModification(StrictModel):
    target_requirement_id: str
    new_subject: str | None = None
    new_value: str | None = None
    new_parameters: dict[str, Any] | None = None
    process_detail: ProcessObservation | None = None
    pain_point_detail: PainPointObservation | None = None
    reason: str

    _validate_target = field_validator("target_requirement_id")(
        lambda value: _non_empty(value, "target_requirement_id")
    )
    _validate_reason = field_validator("reason")(lambda value: _non_empty(value, "reason"))

    @model_validator(mode="after")
    def validate_has_change(self) -> "RequirementModification":
        if all(
            value is None
            for value in (
                self.new_subject,
                self.new_value,
                self.new_parameters,
                self.process_detail,
                self.pain_point_detail,
            )
        ):
            raise ValueError("RequirementModification must modify at least one field")
        if self.new_subject is not None:
            _non_empty(self.new_subject, "new_subject")
        if self.new_value is not None:
            _non_empty(self.new_value, "new_value")
        return self


def _validate_confirmation_actions(
    confirmed_requirement_ids: list[str],
    rejected_requirement_ids: list[str],
    modifications: list[RequirementModification],
) -> None:
    if not confirmed_requirement_ids and not rejected_requirement_ids and not modifications:
        raise ValueError("confirmation requires at least one action")
    for field_name, values in (
        ("confirmed_requirement_ids", confirmed_requirement_ids),
        ("rejected_requirement_ids", rejected_requirement_ids),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} values must be unique")
    modified_ids = [modification.target_requirement_id for modification in modifications]
    if len(modified_ids) != len(set(modified_ids)):
        raise ValueError("modification target_requirement_id values must be unique")
    confirmed = set(confirmed_requirement_ids)
    rejected = set(rejected_requirement_ids)
    modified = set(modified_ids)
    if confirmed & rejected or confirmed & modified or rejected & modified:
        raise ValueError("confirmed, rejected, and modified requirement IDs must not overlap")


class RequirementConfirmation(StrictModel):
    project_id: str
    state_version: int = Field(ge=1)
    confirmation_level: Literal["internal", "customer"]
    confirmed_requirement_ids: list[str] = Field(default_factory=list)
    rejected_requirement_ids: list[str] = Field(default_factory=list)
    modifications: list[RequirementModification] = Field(default_factory=list)
    confirmed_by: str
    note: str | None = None

    _validate_project_id = field_validator("project_id")(
        lambda value: _non_empty(value, "project_id")
    )
    _validate_confirmed_by = field_validator("confirmed_by")(
        lambda value: _non_empty(value, "confirmed_by")
    )

    @model_validator(mode="after")
    def validate_actions(self) -> "RequirementConfirmation":
        _validate_confirmation_actions(
            self.confirmed_requirement_ids,
            self.rejected_requirement_ids,
            self.modifications,
        )
        return self


class RequirementConfirmationRecord(StrictModel):
    confirmation_id: str
    project_id: str
    source_state_version: int = Field(ge=1)
    result_state_version: int = Field(ge=2)
    confirmation_level: Literal["internal", "customer"]
    confirmed_requirement_ids: list[str] = Field(default_factory=list)
    rejected_requirement_ids: list[str] = Field(default_factory=list)
    modifications: list[RequirementModification] = Field(default_factory=list)
    confirmed_by: str
    note: str | None = None
    recorded_at: str | None = None

    _validate_confirmation_id = field_validator("confirmation_id")(
        lambda value: _non_empty(value, "confirmation_id")
    )
    _validate_project_id = field_validator("project_id")(
        lambda value: _non_empty(value, "project_id")
    )
    _validate_confirmed_by = field_validator("confirmed_by")(
        lambda value: _non_empty(value, "confirmed_by")
    )

    @model_validator(mode="after")
    def validate_record(self) -> "RequirementConfirmationRecord":
        if self.result_state_version != self.source_state_version + 1:
            raise ValueError("confirmation result_state_version must equal source_state_version + 1")
        _validate_confirmation_actions(
            self.confirmed_requirement_ids,
            self.rejected_requirement_ids,
            self.modifications,
        )
        return self


class RequirementBaseline(StrictModel):
    baseline_id: str
    project_id: str
    baseline_version: int = Field(ge=1)
    source_state_version: int = Field(ge=1)
    confirmed_items: list[RequirementItem]
    non_blocking_gaps: list[RequirementGap] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confirmation_level: Literal["customer"] = "customer"
    confirmed_by: str
    confirmation_summary: str

    _validate_baseline_id = field_validator("baseline_id")(
        lambda value: _non_empty(value, "baseline_id")
    )
    _validate_project_id = field_validator("project_id")(
        lambda value: _non_empty(value, "project_id")
    )
    _validate_confirmed_by = field_validator("confirmed_by")(
        lambda value: _non_empty(value, "confirmed_by")
    )
    _validate_summary = field_validator("confirmation_summary")(
        lambda value: _non_empty(value, "confirmation_summary")
    )

    @model_validator(mode="after")
    def validate_customer_truth(self) -> "RequirementBaseline":
        if not self.confirmed_items:
            raise ValueError("RequirementBaseline requires confirmed_items")
        item_ids = [item.requirement_id for item in self.confirmed_items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("RequirementBaseline requirement_id values must be unique")
        if any(
            item.status != "confirmed" or item.confirmation_level != "customer"
            for item in self.confirmed_items
        ):
            raise ValueError("RequirementBaseline items must be confirmed at customer level")
        if any(gap.blocking for gap in self.non_blocking_gaps):
            raise ValueError("RequirementBaseline cannot contain blocking gaps")
        if len(self.assumptions) != len(set(self.assumptions)):
            raise ValueError("RequirementBaseline assumptions must be unique")
        return self


class RequirementAnalysis(StrictModel):
    project_id: str
    previous_state_version: int | None = Field(default=None, ge=1)
    current_state: RequirementState
    changes: list[RequirementChange] = Field(default_factory=list)
    readiness: ReadinessAssessment
    next_questions: list[NextQuestion] = Field(default_factory=list, max_length=3)
    customer_confirmation_summary: str

    _validate_project_id = field_validator("project_id")(
        lambda value: _non_empty(value, "project_id")
    )
    _validate_summary = field_validator("customer_confirmation_summary")(
        lambda value: _non_empty(value, "customer_confirmation_summary")
    )

    @model_validator(mode="after")
    def validate_analysis_closure(self) -> "RequirementAnalysis":
        if self.current_state.project_id != self.project_id:
            raise ValueError("RequirementAnalysis project_id must match current_state")
        if (
            self.previous_state_version is not None
            and self.previous_state_version >= self.current_state.state_version
        ):
            raise ValueError("previous_state_version must be earlier than current state")
        item_ids = {item.requirement_id for item in self.current_state.items}
        if not {change.requirement_id for change in self.changes} <= item_ids:
            raise ValueError("RequirementAnalysis changes must reference current_state items")
        gap_ids = {gap.gap_id for gap in self.current_state.gaps}
        conflict_ids = {conflict.conflict_id for conflict in self.current_state.conflicts}
        for question in self.next_questions:
            if not set(question.related_gap_ids) <= gap_ids:
                raise ValueError("NextQuestion gap references must exist in current_state")
            if not set(question.related_conflict_ids) <= conflict_ids:
                raise ValueError("NextQuestion conflict references must exist in current_state")
        return self
