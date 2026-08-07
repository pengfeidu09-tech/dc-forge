import json
from pathlib import Path

import pytest

from backend.app.solution.asset_repository import AssetRepository


def test_repository_loads_all_six_curated_assets_with_unique_ids() -> None:
    repository = AssetRepository()
    assets = repository.list_assets()

    assert len(assets) == 6
    assert len({asset.asset_id for asset in assets}) == 6
    assert all(asset.evidence for asset in assets)


def test_repository_returns_asset_and_reports_missing_id() -> None:
    repository = AssetRepository()

    asset = repository.get_asset("dc-smart-procurement")

    assert asset.name == "神州问学智能招采"
    with pytest.raises(KeyError, match="does-not-exist"):
        repository.get_asset("does-not-exist")


def test_energy_asset_declares_tobacco_lineage_without_inheriting_energy_rules() -> None:
    asset = AssetRepository().get_asset("dc-energy-serious-longtext")
    tobacco_asset = AssetRepository().get_asset("dc-tobacco-smart-procurement")
    limitations = "\n".join(asset.limitations)
    tobacco_serialized = json.dumps(tobacco_asset.model_dump(), ensure_ascii=False)

    assert "dc-tobacco-smart-procurement" in asset.derived_from_asset_ids
    assert "文档结构解析" in "\n".join(module.name for module in asset.modules)
    assert "文档审查" in "\n".join(module.name for module in asset.modules)
    assert "火电行业规则" in limitations
    assert "碳排放计算" in limitations
    assert "不从烟草智能招采继承" in limitations
    assert "火电行业规则" not in tobacco_serialized
    assert "碳排放计算" not in tobacco_serialized


def test_all_historical_claims_reference_asset_evidence() -> None:
    for asset in AssetRepository().list_assets():
        evidence_ids = {evidence.evidence_id for evidence in asset.evidence}
        for claim in asset.value_claims:
            if claim.claim_type == "historical":
                assert claim.evidence_refs
                assert set(claim.evidence_refs) <= evidence_ids
                assert claim.run_report_id is None
                assert all(
                    evidence.verified
                    for evidence in asset.evidence
                    if evidence.evidence_id in claim.evidence_refs
                )


def test_corpus_contains_verified_historical_claims_in_tobacco_asset() -> None:
    repository = AssetRepository()
    assets = repository.list_assets()
    tobacco_asset = repository.get_asset("dc-tobacco-smart-procurement")

    assert any(
        claim.claim_type == "historical"
        for asset in assets
        for claim in asset.value_claims
    )
    assert any(claim.claim_type == "historical" for claim in tobacco_asset.value_claims)


def test_curated_corpus_has_no_expected_or_verified_claims() -> None:
    for asset in AssetRepository().list_assets():
        assert all(claim.claim_type == "historical" for claim in asset.value_claims)


def test_repository_fails_fast_for_duplicate_asset_ids(tmp_path: Path) -> None:
    fixture = {
        "asset_id": "duplicate",
        "name": "Duplicate",
        "version": "1.0",
        "provider": "Digital China",
        "source_type": "curated_fixture",
        "industries": ["test"],
        "processes": ["test"],
        "scenarios": ["test"],
        "modules": [],
        "evidence": [],
    }
    for filename in ("one.json", "two.json"):
        (tmp_path / filename).write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate asset_id"):
        AssetRepository(assets_dir=tmp_path)
