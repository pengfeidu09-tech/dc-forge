import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.contracts.requirement_intelligence import (
    CompletenessDimension,
    RequirementItem,
    RequirementSkill,
    RequirementSourceRef,
    RequirementState,
    SkillRequirementRule,
)
from backend.app.process.gap_detector import GapDetector
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"


def _base_payload(skill_id: str, extends: str | None = None) -> dict[str, object]:
    return {
        "skill_id": skill_id,
        "version": "1.0",
        "domain": "test",
        "extends_skill_id": extends,
        "rules": [],
        "completeness_dimensions": [],
        "procurement_stages": [],
        "probes": [],
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_procurement_core_and_automotive_overlay_resolve_strictly_and_deterministically() -> None:
    loader = RequirementSkillLoader(SKILL_ROOT)
    core = loader.resolve("procurement-core-v1")
    automotive = loader.resolve("automotive-procurement-v1")
    repeated = loader.resolve("automotive-procurement-v1")

    assert sum(dimension.weight for dimension in core.completeness_dimensions) == 100
    assert "采购需求" in core.procurement_stages
    core_rule_ids = {rule.rule_id for rule in core.rules}
    automotive_rule_ids = {rule.rule_id for rule in automotive.rules}
    assert core_rule_ids < automotive_rule_ids
    assert automotive.extends_skill_id == "procurement-core-v1"
    assert any("供应商准入" in probe for probe in automotive.probes)
    assert automotive.model_dump() == repeated.model_dump()
    with pytest.raises(ValidationError):
        RequirementSkill.model_validate({**core.model_dump(), "unexpected": True})


def test_skill_contract_rejects_invalid_categories_weights_and_duplicate_rule_ids() -> None:
    with pytest.raises(ValidationError, match="category"):
        SkillRequirementRule(
            rule_id="bad", category="unknown", requirement_level="recommended",
            missing_blocks_preliminary=False, unconfirmed_blocks_formal=False,
            requires_customer_confirmation=False, hard_constraint=False,
            question_template="question", description="description",
        )
    with pytest.raises(ValidationError, match="weight"):
        CompletenessDimension(dimension_id="bad", categories=["business_goal"], weight=101)
    with pytest.raises(ValidationError, match="weight"):
        CompletenessDimension(dimension_id="negative", categories=["business_goal"], weight=-1)
    with pytest.raises(ValidationError, match="requirement_level"):
        SkillRequirementRule(
            rule_id="bad-level", category="security", requirement_level="required",
            missing_blocks_preliminary=False, unconfirmed_blocks_formal=False,
            requires_customer_confirmation=False, hard_constraint=False,
            question_template="question", description="description",
        )
    rule = SkillRequirementRule(
        rule_id="duplicate", category="security", requirement_level="recommended",
        missing_blocks_preliminary=False, unconfirmed_blocks_formal=False,
        requires_customer_confirmation=False, hard_constraint=False,
        question_template="question", description="description",
    )
    with pytest.raises(ValidationError, match="rule_id"):
        RequirementSkill(**{**_base_payload("duplicates"), "rules": [rule, rule]})
    dimension = CompletenessDimension(
        dimension_id="duplicate", categories=["business_goal"], weight=50,
    )
    with pytest.raises(ValidationError, match="dimension_id"):
        RequirementSkill(
            **{
                **_base_payload("duplicate-dimensions"),
                "completeness_dimensions": [dimension, dimension],
            }
        )


def test_skill_loader_rejects_unknown_base_duplicate_ids_and_cycles(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    _write(missing / "child.json", _base_payload("child", "absent"))
    with pytest.raises(ValueError, match="base skill"):
        RequirementSkillLoader(missing).resolve("child")

    duplicates = tmp_path / "duplicates"
    duplicates.mkdir()
    _write(duplicates / "one.json", _base_payload("same"))
    _write(duplicates / "two.json", _base_payload("same"))
    with pytest.raises(ValueError, match="duplicate skill_id"):
        RequirementSkillLoader(duplicates).resolve("same")

    cyclic = tmp_path / "cyclic"
    cyclic.mkdir()
    _write(cyclic / "a.json", _base_payload("a", "b"))
    _write(cyclic / "b.json", _base_payload("b", "a"))
    with pytest.raises(ValueError, match="cyclic"):
        RequirementSkillLoader(cyclic).resolve("a")
    with pytest.raises(KeyError, match="unknown"):
        RequirementSkillLoader(SKILL_ROOT).resolve("unknown")


def test_skill_loader_uses_exact_ids_and_rejects_path_like_input() -> None:
    loader = RequirementSkillLoader(SKILL_ROOT)

    assert loader.resolve("automotive-procurement-v1").skill_id == "automotive-procurement-v1"
    for invalid_id in (
        "procurement_core_v1",
        "procurement_core_v1.json",
        "../../procurement_core_v1",
        r"..\procurement_core_v1",
    ):
        with pytest.raises(KeyError, match="unknown requirement skill"):
            loader.resolve(invalid_id)


def test_skill_overlay_cannot_override_base_rules_or_dimensions(tmp_path: Path) -> None:
    base = _base_payload("base")
    base["rules"] = [
        {
            "rule_id": "shared-rule", "category": "security",
            "requirement_level": "recommended", "missing_blocks_preliminary": False,
            "unconfirmed_blocks_formal": False, "requires_customer_confirmation": False,
            "hard_constraint": False, "question_template": "question",
            "description": "description",
        }
    ]
    base["completeness_dimensions"] = [
        {"dimension_id": "shared-dimension", "categories": ["business_goal"], "weight": 100}
    ]
    child_rule = _base_payload("child-rule", "base")
    child_rule["rules"] = base["rules"]
    child_dimension = _base_payload("child-dimension", "base")
    child_dimension["completeness_dimensions"] = base["completeness_dimensions"]

    rule_root = tmp_path / "rule-override"
    rule_root.mkdir()
    _write(rule_root / "base.json", base)
    _write(rule_root / "child.json", child_rule)
    with pytest.raises(ValueError, match="cannot override base rule_id"):
        RequirementSkillLoader(rule_root).resolve("child-rule")

    dimension_root = tmp_path / "dimension-override"
    dimension_root.mkdir()
    _write(dimension_root / "base.json", base)
    _write(dimension_root / "child.json", child_dimension)
    with pytest.raises(ValueError, match="cannot override base dimension_id"):
        RequirementSkillLoader(dimension_root).resolve("child-dimension")


def test_resolved_automotive_skill_weight_is_exactly_one_hundred() -> None:
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    assert sum(dimension.weight for dimension in skill.completeness_dimensions) == 100


def test_automotive_skill_creates_only_gaps_and_never_customer_truth() -> None:
    item = RequirementItem(
        requirement_id="req-industry", category="industry", subject="industry", value="automotive",
        provenance="ai_extracted", status="pending", confirmation_level="none", confidence=0.9,
        source_refs=[RequirementSourceRef(source_id="source-1", excerpt="automotive")],
    )
    state = RequirementState(
        project_id="project-1", state_version=1, source_ids=["source-1"], items=[item]
    )
    before = state.model_dump()
    skill = RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")
    gaps = GapDetector().detect(state, skill, [])

    assert state.model_dump() == before
    assert state.items == [item]
    assert any(gap.category == "ext:procurement:supplier_entry_policy" for gap in gaps)
    assert not any(requirement.category == "pain_point" for requirement in state.items)
