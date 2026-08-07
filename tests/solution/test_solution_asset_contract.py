from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.app.contracts.solution_intelligence import (
    EvidenceRecord,
    SolutionAsset,
    ValueClaim,
)


def _evidence() -> dict:
    return {
        "evidence_id": "ev-1",
        "source_type": "official_solution",
        "title": "Curated official material",
        "document_name": "Official material.pdf",
        "page_start": 1,
        "page_end": 1,
        "kind": "asset_definition",
        "statement": "A short curated statement.",
    }


def _asset_payload() -> dict:
    return {
        "asset_id": "asset-1",
        "name": "Test asset",
        "version": "1.0",
        "provider": "Digital China",
        "source_type": "official_solution",
        "industries": ["test"],
        "processes": ["test process"],
        "scenarios": ["test scenario"],
        "modules": [
            {
                "module_id": "module-1",
                "name": "Test module",
                "description": "A test module.",
                "evidence_refs": ["ev-1"],
            }
        ],
        "evidence": [_evidence()],
    }


def test_contracts_reject_unknown_fields() -> None:
    payload = _evidence()
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(payload)


def test_evidence_page_end_must_not_precede_page_start() -> None:
    payload = _evidence()
    payload["page_start"] = 3
    payload["page_end"] = 2

    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(payload)


def test_historical_value_claim_requires_evidence_and_no_run_report() -> None:
    with pytest.raises(ValidationError):
        ValueClaim(
            claim_id="claim-1",
            claim_type="historical",
            metric_name="result",
            value_text="reported result",
        )

    with pytest.raises(ValidationError):
        ValueClaim(
            claim_id="claim-2",
            claim_type="historical",
            metric_name="result",
            value_text="reported result",
            evidence_refs=["ev-1"],
            run_report_id="run-1",
        )


def test_expected_and_verified_value_claim_require_their_provenance() -> None:
    with pytest.raises(ValidationError):
        ValueClaim(
            claim_id="claim-1",
            claim_type="expected",
            metric_name="result",
            value_text="expected result",
            assumptions=["Known input volume"],
        )

    with pytest.raises(ValidationError):
        ValueClaim(
            claim_id="claim-2",
            claim_type="expected",
            metric_name="result",
            value_text="expected result",
            formula="baseline - target",
        )

    with pytest.raises(ValidationError):
        ValueClaim(
            claim_id="claim-3",
            claim_type="verified",
            metric_name="result",
            value_text="measured result",
        )


def test_asset_rejects_duplicate_module_and_evidence_ids() -> None:
    duplicate_module = _asset_payload()
    duplicate_module["modules"].append(deepcopy(duplicate_module["modules"][0]))

    with pytest.raises(ValidationError):
        SolutionAsset.model_validate(duplicate_module)

    duplicate_evidence = _asset_payload()
    duplicate_evidence["evidence"].append(deepcopy(duplicate_evidence["evidence"][0]))

    with pytest.raises(ValidationError):
        SolutionAsset.model_validate(duplicate_evidence)


def test_asset_rejects_dangling_module_evidence_reference() -> None:
    payload = _asset_payload()
    payload["modules"][0]["evidence_refs"] = ["missing-evidence"]

    with pytest.raises(ValidationError):
        SolutionAsset.model_validate(payload)
