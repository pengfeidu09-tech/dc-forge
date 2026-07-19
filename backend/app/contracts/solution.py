from typing import Literal

from pydantic import Field

from .common import BusinessConstraint, StrictModel
from .process import ProcessSpec


class ComponentRef(StrictModel):
    """被方案选中的一个能力胶囊。"""

    component_id: str
    name: str
    reason: str

    required_data: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class WorkflowNode(StrictModel):
    """目标方案中的一个工作流节点。"""

    id: str
    name: str
    component_id: str

    executor: Literal[
        "ai",
        "human",
        "system",
    ]

    next_ids: list[str] = Field(default_factory=list)

    human_gate: bool = False
    gate_reason: str | None = None


class SolutionPlan(StrictModel):
    """保守、均衡或创新方案中的一套。"""

    schema_version: Literal["1.0"] = "1.0"

    solution_id: str
    source_project_id: str

    plan_type: Literal[
        "conservative",
        "balanced",
        "innovative",
    ]

    name: str
    summary: str

    selected_components: list[ComponentRef]
    to_be_nodes: list[WorkflowNode]
    applied_constraints: list[BusinessConstraint]

    implementation_steps: list[str]
    expected_metrics: list[str]

    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    review_score: float = Field(ge=0, le=100)


class SolutionBundle(StrictModel):
    """成员B一次返回的三套方案。"""

    project_id: str
    plans: list[SolutionPlan]


class CompileRequest(StrictModel):
    """成员B的方案编译接口输入。"""

    process: ProcessSpec


class RecompileRequest(StrictModel):
    """客户增加约束后，重新编译方案的输入。"""

    process: ProcessSpec
    selected_solution: SolutionPlan
    new_constraints: list[BusinessConstraint]


class RecompileResult(StrictModel):
    """重新编译后的结果和变化说明。"""

    previous_solution_id: str
    new_solution: SolutionPlan

    changed_node_ids: list[str] = Field(default_factory=list)
    added_component_ids: list[str] = Field(default_factory=list)
    removed_component_ids: list[str] = Field(default_factory=list)

    change_explanations: list[str] = Field(default_factory=list)