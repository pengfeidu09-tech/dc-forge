import json
from pathlib import Path

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.runtime import RunReport
from backend.app.contracts.solution import SolutionBundle


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures"


def load_json(filename: str) -> dict:
    path = FIXTURES / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_process_spec_contract() -> None:
    data = load_json("process_spec.json")
    ProcessSpec.model_validate(data)


def test_solution_bundle_contract() -> None:
    data = load_json("solution_bundle.json")
    SolutionBundle.model_validate(data)


def test_run_report_contract() -> None:
    data = load_json("run_report.json")
    RunReport.model_validate(data)