"""Strict local loading and deterministic composition of Requirement Skills."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.contracts.requirement_intelligence import RequirementSkill


class RequirementSkillLoader:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._skills = self._load_skills()

    def _load_skills(self) -> dict[str, RequirementSkill]:
        skills: dict[str, RequirementSkill] = {}
        for path in sorted(self._root.glob("*.json"), key=lambda item: item.name):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                skill = RequirementSkill.model_validate(payload)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid requirement skill: {path}") from exc
            if skill.skill_id in skills:
                raise ValueError(f"duplicate skill_id: {skill.skill_id}")
            skills[skill.skill_id] = skill
        return skills

    def resolve(self, skill_id: str) -> RequirementSkill:
        if skill_id not in self._skills:
            raise KeyError(f"unknown requirement skill: {skill_id}")
        resolved = self._resolve(skill_id, ())
        weight = sum(dimension.weight for dimension in resolved.completeness_dimensions)
        if abs(weight - 100.0) > 1e-9:
            raise ValueError(f"resolved skill completeness weight must total 100: {skill_id}")
        return resolved

    def _resolve(self, skill_id: str, ancestry: tuple[str, ...]) -> RequirementSkill:
        if skill_id in ancestry:
            cycle = " -> ".join((*ancestry, skill_id))
            raise ValueError(f"cyclic requirement skill inheritance: {cycle}")
        skill = self._skills[skill_id]
        if skill.extends_skill_id is None:
            return skill
        if skill.extends_skill_id not in self._skills:
            raise ValueError(f"base skill does not exist: {skill.extends_skill_id}")
        base = self._resolve(skill.extends_skill_id, (*ancestry, skill_id))

        base_rule_ids = {rule.rule_id for rule in base.rules}
        child_rule_ids = {rule.rule_id for rule in skill.rules}
        overlap = sorted(base_rule_ids & child_rule_ids)
        if overlap:
            raise ValueError(f"overlay cannot override base rule_id: {overlap[0]}")
        base_dimension_ids = {dimension.dimension_id for dimension in base.completeness_dimensions}
        child_dimension_ids = {dimension.dimension_id for dimension in skill.completeness_dimensions}
        dimension_overlap = sorted(base_dimension_ids & child_dimension_ids)
        if dimension_overlap:
            raise ValueError(f"overlay cannot override base dimension_id: {dimension_overlap[0]}")

        return RequirementSkill(
            skill_id=skill.skill_id,
            version=skill.version,
            domain=skill.domain,
            extends_skill_id=skill.extends_skill_id,
            rules=[*base.rules, *skill.rules],
            completeness_dimensions=[*base.completeness_dimensions, *skill.completeness_dimensions],
            procurement_stages=self._stable_unique([*base.procurement_stages, *skill.procurement_stages]),
            probes=self._stable_unique([*base.probes, *skill.probes]),
        )

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result
