"""Customer-only RequirementBaseline construction for R-M4."""

from __future__ import annotations

import json
from hashlib import sha256

from backend.app.contracts.requirement_intelligence import (
    ReadinessAssessment,
    RequirementBaseline,
    RequirementSkill,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator


class RequirementBaselineBuilder:
    def __init__(self, skill: RequirementSkill) -> None:
        self._skill = skill

    def build(
        self,
        state: RequirementState,
        readiness: ReadinessAssessment,
        *,
        baseline_version: int,
        confirmed_by: str,
        confirmation_summary: str,
        assumptions: list[str] | None = None,
    ) -> RequirementBaseline:
        if readiness.stage != "CONFIRMED_READY" or not readiness.can_generate_formal_solution:
            raise ValueError("RequirementBaseline requires CONFIRMED_READY")
        supplied_blocking_gaps = sorted(gap.gap_id for gap in state.gaps if gap.blocking)
        if supplied_blocking_gaps:
            raise ValueError(
                f"RequirementBaseline cannot contain blocking gap: {supplied_blocking_gaps[0]}"
            )
        supplied_open_conflicts = sorted(
            conflict.conflict_id for conflict in state.conflicts if conflict.status == "open"
        )
        if supplied_open_conflicts:
            raise ValueError(
                f"RequirementBaseline cannot contain open conflict: {supplied_open_conflicts[0]}"
            )
        latest_conflicts = ConflictDetector().detect(state, self._skill)
        latest_gaps = GapDetector().detect(state, self._skill, latest_conflicts)
        latest_readiness = ReadinessEvaluator().evaluate(
            state,
            self._skill,
            latest_gaps,
            latest_conflicts,
            customer_confirmation_complete=True,
        )
        if (
            latest_readiness.stage != "CONFIRMED_READY"
            or not latest_readiness.can_generate_formal_solution
        ):
            raise ValueError(
                "current RequirementState does not satisfy CONFIRMED_READY"
            )
        blocking_gaps = sorted(gap.gap_id for gap in latest_gaps if gap.blocking)
        if blocking_gaps:
            raise ValueError(f"RequirementBaseline cannot contain blocking gap: {blocking_gaps[0]}")
        open_conflicts = sorted(
            conflict.conflict_id
            for conflict in latest_conflicts
            if conflict.status == "open"
        )
        if open_conflicts:
            raise ValueError(f"RequirementBaseline cannot contain open conflict: {open_conflicts[0]}")
        if readiness.blocking_gap_ids or readiness.open_conflict_ids:
            raise ValueError("RequirementBaseline readiness references unresolved blockers")

        confirmed_items = sorted(
            (
                item
                for item in state.items
                if item.status == "confirmed" and item.confirmation_level == "customer"
            ),
            key=lambda item: item.requirement_id,
        )
        state_source_ids = set(state.source_ids)
        for item in confirmed_items:
            if not {ref.source_id for ref in item.source_refs} <= state_source_ids:
                raise ValueError(
                    f"RequirementBaseline item source refs are not closed: {item.requirement_id}"
                )

        non_blocking_gaps = sorted(
            (gap for gap in latest_gaps if not gap.blocking),
            key=lambda gap: gap.gap_id,
        )
        assumption_values = {
            value.strip()
            for value in (assumptions or [])
            if value.strip()
        }
        assumption_values.update(
            f"未关闭的非阻塞缺口 [{gap.category}]：{gap.description}"
            for gap in non_blocking_gaps
        )
        item_ids = [item.requirement_id for item in confirmed_items]
        identity_payload = {
            "project_id": state.project_id,
            "baseline_version": baseline_version,
            "source_state_version": state.state_version,
            "confirmed_requirement_ids": item_ids,
        }
        material = json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        baseline_id = f"baseline-{sha256(material.encode('utf-8')).hexdigest()[:12]}"
        return RequirementBaseline(
            baseline_id=baseline_id,
            project_id=state.project_id,
            baseline_version=baseline_version,
            source_state_version=state.state_version,
            confirmed_items=confirmed_items,
            non_blocking_gaps=non_blocking_gaps,
            assumptions=sorted(assumption_values),
            confirmed_by=confirmed_by,
            confirmation_summary=confirmation_summary,
        )
