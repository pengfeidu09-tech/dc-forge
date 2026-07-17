from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """
    所有接口模型的父类。

    extra="forbid"表示：
    如果有人传入合同中不存在的字段，立即报错。
    """

    model_config = ConfigDict(extra="forbid")


class BusinessConstraint(StrictModel):
    """客户提出的业务约束。"""

    id: str

    type: Literal[
        "security",   # 数据安全，例如禁止公网模型
        "approval",   # 审批要求，例如超过50万元需人工审批
        "budget",     # 预算要求
        "time",       # 项目周期要求
        "data",       # 数据条件
        "risk",       # 风险控制
    ]

    statement: str
    hard: bool = True

    # 用于放金额、天数等结构化参数
    parameters: dict[str, Any] = Field(default_factory=dict)