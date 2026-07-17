"""B 模块私有能力胶囊模型与加载器。

CapabilityCapsule 是成员 B 的内部领域模型，不放入公共 contracts/。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CapabilityCapsule(BaseModel):
    """能力胶囊：一个可被方案选中的原子能力单元。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"

    component_id: str
    name: str
    description: str

    problem_tags: list[str] = Field(default_factory=list)
    applicable_industries: list[str] = Field(default_factory=list)
    applicable_departments: list[str] = Field(default_factory=list)

    required_data: list[str] = Field(default_factory=list)
    supported_constraint_types: list[str] = Field(default_factory=list)
    forbidden_conditions: list[str] = Field(default_factory=list)

    human_fallback: str
    executor_type: Literal["ai", "human", "system", "hybrid"]

    evidence_urls: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)


def _default_capabilities_path() -> Path:
    """返回项目根目录下的 data/capabilities.json，不依赖终端工作目录。"""
    return Path(__file__).resolve().parents[3] / "data" / "capabilities.json"


def load_capabilities(path: Path | None = None) -> list[CapabilityCapsule]:
    """从 JSON 文件加载能力胶囊列表。

    Args:
        path: JSON 文件路径，默认为项目根目录 data/capabilities.json。

    Returns:
        校验通过的能力胶囊列表。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 文件为空、根节点非数组、或 component_id 重复。
        pydantic.ValidationError: 某项不符合 CapabilityCapsule 模型。
    """
    file_path = path if path is not None else _default_capabilities_path()

    if not file_path.exists():
        raise FileNotFoundError(f"能力胶囊文件不存在: {file_path}")

    raw_text = file_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(f"能力胶囊文件为空: {file_path}")

    data = json.loads(raw_text)
    if not isinstance(data, list):
        raise ValueError(
            f"能力胶囊根节点必须是数组，实际类型: {type(data).__name__}"
        )

    capsules = [CapabilityCapsule.model_validate(item) for item in data]

    seen_ids: set[str] = set()
    for cap in capsules:
        if cap.component_id in seen_ids:
            raise ValueError(f"重复的 component_id: {cap.component_id}")
        seen_ids.add(cap.component_id)

    return capsules
