from typing import Literal

from pydantic import Field

from .common import BusinessConstraint, StrictModel


class RequirementInput(StrictModel):
    """前端第一次提交给成员A的客户需求。"""

    project_id: str
    raw_requirement: str
    answers: dict[str, str] = Field(default_factory=dict)


class ProcessNode(StrictModel):
    """客户当前流程中的一个节点。"""

    id: str
    name: str
    actor: str

    node_type: Literal[
        "human",
        "system",
        "ai",
    ]

    description: str
    next_ids: list[str] = Field(default_factory=list)


class PainPoint(StrictModel):
    """当前流程中发现的一个问题。"""

    id: str
    description: str

    severity: Literal[
        "low",
        "medium",
        "high",
    ]

    affected_node_ids: list[str] = Field(default_factory=list)


class ProcessSpec(StrictModel):
    """
    成员A的最终交付对象。

    成员B只读取这个对象，
    不读取成员A的Prompt、函数或内部变量。
    """

    schema_version: Literal["1.0"] = "1.0"

    project_id: str
    industry: str
    department: str
    business_goal: str

    roles: list[str]
    available_data: list[str]
    existing_systems: list[str]

    as_is_nodes: list[ProcessNode]
    pain_points: list[PainPoint]
    constraints: list[BusinessConstraint]

    target_metrics: list[str]

    missing_information: list[str]
    clarification_questions: list[str]

    readiness_score: float = Field(ge=0, le=100)