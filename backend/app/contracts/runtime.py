from typing import Literal

from pydantic import Field

from .common import StrictModel
from .process import ProcessSpec
from .solution import SolutionPlan


class RuntimeRequest(StrictModel):
    """成员C运行Demo时接收的数据。"""

    process: ProcessSpec
    solution: SolutionPlan
    case_id: str


class MetricSnapshot(StrictModel):
    """流程运行前或运行后的指标。"""

    average_processing_minutes: float
    manual_steps: int

    automation_rate: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=100)

    estimated_cost: float


class AuditEvent(StrictModel):
    """工作流运行过程中产生的一条审计记录。"""

    node_id: str
    action: str
    executor: str
    result: str
    timestamp: str


class RunReport(StrictModel):
    """成员C运行流程后交付的报告。"""

    schema_version: Literal["1.0"] = "1.0"

    run_id: str
    case_id: str
    solution_id: str

    status: Literal[
        "success",
        "failed",
        "needs_human_review",
    ]

    before: MetricSnapshot
    after: MetricSnapshot

    audit_events: list[AuditEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)