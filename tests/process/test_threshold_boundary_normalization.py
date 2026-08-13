"""R-CHANGE1 T1-T6: approval threshold boundary normalization."""

from __future__ import annotations

import pytest

from backend.app.process.process_spec_adapter import ProcessSpecAdapter
from tests.process.rm5_helpers import item, skill, state_and_baseline


def _approval(parameters: dict[str, object]):
    return item(
        "req-approval-boundary",
        "approval",
        "procurement approval threshold",
        "approval rule",
        parameters=parameters,
    )


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        pytest.param({"threshold_amount": 500000}, {"threshold": 500000}, id="T1-extraction-500"),
        pytest.param({"threshold_amount": 800000}, {"threshold": 800000}, id="T2-extraction-800"),
        pytest.param({"threshold": 500000}, {"threshold": 500000}, id="T3-legacy"),
        pytest.param(
            {"threshold_amount": 500000, "threshold": 500000},
            {"threshold": 500000},
            id="T4-equal-aliases",
        ),
    ],
)
def test_approval_threshold_boundary_normalizes_to_processspec_schema(
    parameters: dict[str, object], expected: dict[str, object]
) -> None:
    constraint = ProcessSpecAdapter().constraint_from_item("project-t", _approval(parameters), skill())

    assert constraint is not None
    assert constraint.parameters == expected


def test_approval_threshold_boundary_fails_closed_on_conflicting_aliases() -> None:
    with pytest.raises(ValueError, match="threshold.*conflict"):
        ProcessSpecAdapter().constraint_from_item(
            "project-t",
            _approval({"threshold_amount": 800000, "threshold": 500000}),
            skill(),
        )


def test_approval_threshold_update_keeps_stable_constraint_id_and_no_old_parameter_residue() -> None:
    previous_state, previous_baseline = state_and_baseline(approval=500000)
    current_state, current_baseline = state_and_baseline(
        state_version=2, baseline_version=2, approval=800000
    )
    previous_item = next(item for item in previous_baseline.confirmed_items if item.category == "approval")
    current_item = next(item for item in current_baseline.confirmed_items if item.category == "approval")
    previous_item = previous_item.model_copy(update={"parameters": {"threshold_amount": 500000}})
    current_item = current_item.model_copy(update={"parameters": {"threshold_amount": 800000}})

    adapter = ProcessSpecAdapter()
    previous = adapter.constraint_from_item(previous_baseline.project_id, previous_item, skill())
    current = adapter.constraint_from_item(current_baseline.project_id, current_item, skill())

    assert previous is not None and current is not None
    assert previous.id == current.id
    assert current.parameters == {"threshold": 800000}
    assert "threshold_amount" not in current.parameters
    assert 500000 not in current.parameters.values()


def test_non_approval_constraint_parameters_are_unchanged() -> None:
    security = item(
        "req-security-boundary",
        "security",
        "deployment boundary",
        "data must stay private",
        parameters={"retention_days": 30},
    )

    constraint = ProcessSpecAdapter().constraint_from_item("project-t", security, skill())

    assert constraint is not None
    assert constraint.parameters == {"retention_days": 30}
