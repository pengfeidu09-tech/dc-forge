"""Deterministic customer-confirmed RequirementBaseline to ProcessSpec adapter."""

from __future__ import annotations

from hashlib import sha256
import re

from backend.app.contracts.common import BusinessConstraint
from backend.app.contracts.process import PainPoint, ProcessNode, ProcessSpec
from backend.app.contracts.requirement_intelligence import (
    NextQuestion,
    ReadinessAssessment,
    RequirementBaseline,
    RequirementItem,
    RequirementSkill,
    RequirementState,
)


_SPACE = re.compile(r"\s+")
_CONSTRAINT_CATEGORIES = {"security", "approval", "budget", "time", "data", "risk"}


def normalize_text(value: str) -> str:
    return _SPACE.sub(" ", value).strip().casefold()


def display_text(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _canonical_parameter(value):
    if isinstance(value, dict):
        return {key: _canonical_parameter(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical_parameter(item) for item in value]
    return value


def _normalize_constraint_parameters(item: RequirementItem) -> dict[str, object]:
    """Normalize only the frozen Requirement -> ProcessSpec approval boundary."""
    parameters = {
        key: _canonical_parameter(value)
        for key, value in item.parameters.items()
        if key not in {"hard", "not_applicable"}
    }
    if item.category != "approval":
        return {key: parameters[key] for key in sorted(parameters)}

    threshold_amount = parameters.pop("threshold_amount", None)
    legacy_threshold = parameters.pop("threshold", None)
    if threshold_amount is not None and legacy_threshold is not None:
        if threshold_amount != legacy_threshold:
            raise ValueError("approval threshold alias conflict")
        parameters["threshold"] = threshold_amount
    elif threshold_amount is not None:
        parameters["threshold"] = threshold_amount
    elif legacy_threshold is not None:
        parameters["threshold"] = legacy_threshold
    return {key: parameters[key] for key in sorted(parameters)}


def stable_constraint_id(project_id: str, category: str, subject: str) -> str:
    material = "|".join((project_id, category, normalize_text(subject)))
    return f"constraint-{sha256(material.encode('utf-8')).hexdigest()[:16]}"


class ProcessSpecAdapter:
    def adapt(
        self,
        baseline: RequirementBaseline,
        state: RequirementState,
        skill: RequirementSkill,
        readiness: ReadinessAssessment,
        outstanding_questions: list[NextQuestion],
    ) -> ProcessSpec:
        self._validate_closure(baseline, state, readiness)
        items = list(baseline.confirmed_items)
        process_nodes = self._process_nodes(items)
        pain_points = self._pain_points(items, {node.id for node in process_nodes})
        constraint_by_id: dict[str, BusinessConstraint] = {}
        for item in items:
            if item.category not in _CONSTRAINT_CATEGORIES:
                continue
            constraint = self.constraint_from_item(baseline.project_id, item, skill)
            if constraint is None:
                continue
            existing = constraint_by_id.get(constraint.id)
            if existing is not None and existing.model_dump() != constraint.model_dump():
                raise ValueError(f"constraint ID collision has different business payload: {constraint.id}")
            constraint_by_id[constraint.id] = constraint
        constraints = sorted(constraint_by_id.values(), key=lambda item: (item.type, item.id))
        questions = sorted(
            outstanding_questions,
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.priority],
                item.target_category,
                item.question_id,
            ),
        )[:3]
        return ProcessSpec(
            project_id=baseline.project_id,
            industry=self._scalar(items, "industry"),
            department=self._scalar(items, "department"),
            business_goal=self._scalar(items, "business_goal"),
            roles=self._values(items, "role"),
            available_data=self._values(items, "available_data"),
            existing_systems=self._values(items, "existing_system"),
            as_is_nodes=process_nodes,
            pain_points=pain_points,
            constraints=constraints,
            target_metrics=self._values(items, "target_metric"),
            missing_information=sorted(
                {f"[{gap.category}] {display_text(gap.description)}" for gap in baseline.non_blocking_gaps},
                key=lambda value: (value.casefold(), value),
            ),
            clarification_questions=[question.text for question in questions],
            readiness_score=readiness.completeness_score,
        )

    @staticmethod
    def _validate_closure(
        baseline: RequirementBaseline,
        state: RequirementState,
        readiness: ReadinessAssessment,
    ) -> None:
        if baseline.project_id != state.project_id:
            raise ValueError("RequirementBaseline and RequirementState project_id must match")
        if baseline.source_state_version != state.state_version:
            raise ValueError("RequirementBaseline source_state_version must match RequirementState")
        if readiness.stage != "CONFIRMED_READY" or not readiness.can_generate_formal_solution:
            raise ValueError("ProcessSpec requires formal CONFIRMED_READY readiness")
        state_by_id = {item.requirement_id: item for item in state.items}
        expected_ids = {
            item.requirement_id
            for item in state.items
            if item.status == "confirmed" and item.confirmation_level == "customer"
        }
        baseline_ids = {item.requirement_id for item in baseline.confirmed_items}
        if baseline_ids != expected_ids:
            raise ValueError("RequirementBaseline must exactly contain source state customer-confirmed truth")
        for item in baseline.confirmed_items:
            if item.status != "confirmed" or item.confirmation_level != "customer":
                raise ValueError("ProcessSpec accepts only customer-confirmed baseline truth")
            if item.requirement_id not in state_by_id or state_by_id[item.requirement_id].model_dump() != item.model_dump():
                raise ValueError(f"RequirementBaseline item is not closed over source state: {item.requirement_id}")

    @staticmethod
    def _scalar(items: list[RequirementItem], category: str) -> str:
        values: dict[str, list[str]] = {}
        for item in items:
            if item.category == category:
                values.setdefault(normalize_text(item.value), []).append(display_text(item.value))
        if not values:
            raise ValueError(f"{category} requires exactly one customer-confirmed semantic value")
        if len(values) > 1:
            raise ValueError(f"{category} has multiple distinct customer-confirmed semantic values")
        return sorted(next(iter(values.values())), key=lambda value: (value.casefold(), value))[0]

    @staticmethod
    def _values(items: list[RequirementItem], category: str) -> list[str]:
        by_semantic: dict[str, list[str]] = {}
        for item in items:
            if item.category == category:
                by_semantic.setdefault(normalize_text(item.value), []).append(display_text(item.value))
        return [
            sorted(values, key=lambda value: (value.casefold(), value))[0]
            for _, values in sorted(by_semantic.items())
        ]

    @staticmethod
    def _process_nodes(items: list[RequirementItem]) -> list[ProcessNode]:
        by_id: dict[str, object] = {}
        for item in items:
            if item.category != "current_process":
                continue
            detail = item.process_detail
            if detail is None:
                raise ValueError("current_process requires ProcessObservation")
            existing = by_id.get(detail.process_node_id)
            if existing is not None and existing.model_dump() != detail.model_dump():
                raise ValueError(f"duplicate process_node_id conflicts: {detail.process_node_id}")
            by_id[detail.process_node_id] = detail
        nodes = [
            ProcessNode(
                id=detail.process_node_id,
                name=detail.name,
                actor=detail.actor,
                node_type=detail.node_type,
                description=detail.description,
                next_ids=sorted(set(detail.next_node_ids)),
            )
            for _, detail in sorted(by_id.items())
        ]
        node_ids = {node.id for node in nodes}
        dangling = sorted({target for node in nodes for target in node.next_ids if target not in node_ids})
        if dangling:
            raise ValueError(f"current process contains dangling next_node_id: {dangling[0]}")
        return nodes

    @staticmethod
    def _pain_points(items: list[RequirementItem], node_ids: set[str]) -> list[PainPoint]:
        by_id: dict[str, object] = {}
        for item in items:
            if item.category != "pain_point":
                continue
            detail = item.pain_point_detail
            if detail is None:
                raise ValueError("pain_point requires PainPointObservation")
            existing = by_id.get(detail.pain_point_id)
            if existing is not None and existing.model_dump() != detail.model_dump():
                raise ValueError(f"duplicate pain_point_id conflicts: {detail.pain_point_id}")
            by_id[detail.pain_point_id] = detail
        result = []
        for _, detail in sorted(by_id.items()):
            affected = sorted(set(detail.affected_process_node_ids))
            missing = sorted(set(affected) - node_ids)
            if missing:
                raise ValueError(f"pain point affected node is missing: {missing[0]}")
            result.append(
                PainPoint(
                    id=detail.pain_point_id,
                    description=detail.description,
                    severity=detail.severity,
                    affected_node_ids=affected,
                )
            )
        return result

    @staticmethod
    def constraint_from_item(
        project_id: str,
        item: RequirementItem,
        skill: RequirementSkill,
    ) -> BusinessConstraint | None:
        if item.category not in _CONSTRAINT_CATEGORIES:
            raise ValueError(f"unsupported BusinessConstraint category: {item.category}")
        explicit_hard = item.parameters.get("hard")
        if explicit_hard is not None and not isinstance(explicit_hard, bool):
            raise ValueError("constraint parameter hard must be bool")
        not_applicable = item.parameters.get("not_applicable")
        if not_applicable is not None and not isinstance(not_applicable, bool):
            raise ValueError("constraint parameter not_applicable must be bool")
        if not_applicable is True:
            return None
        skill_hard = any(
            rule.category == item.category and rule.hard_constraint for rule in skill.rules
        )
        parameters = _normalize_constraint_parameters(item)
        return BusinessConstraint(
            id=stable_constraint_id(project_id, item.category, item.subject),
            type=item.category,
            statement=item.value,
            hard=skill_hard or explicit_hard is True,
            parameters=parameters,
        )
