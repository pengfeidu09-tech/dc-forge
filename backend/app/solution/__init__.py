"""B 模块方案编译入口。

公开导出：
- CapabilityCapsule: 能力胶囊私有模型
- load_capabilities: 能力胶囊加载器
- retrieve_components: 确定性组件检索器
- compile_solution: 三套方案编译器
- ConstraintCheck: 单条约束校验结果
- ConstraintValidationResult: 约束校验总体结果
- validate_constraints: 硬约束校验器
- ReviewDimension: 评分维度
- SolutionReviewResult: 方案评审结果
- review_solution: 方案 Reviewer
"""

from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities
from backend.app.solution.constraints import (
    ConstraintCheck,
    ConstraintValidationResult,
    validate_constraints,
)
from backend.app.solution.retriever import retrieve_components
from backend.app.solution.reviewer import (
    ReviewDimension,
    SolutionReviewResult,
    review_solution,
)
from backend.app.solution.service import compile_solution, recompile_solution

__all__ = [
    "CapabilityCapsule",
    "load_capabilities",
    "retrieve_components",
    "compile_solution",
    "recompile_solution",
    "ConstraintCheck",
    "ConstraintValidationResult",
    "validate_constraints",
    "ReviewDimension",
    "SolutionReviewResult",
    "review_solution",
]
