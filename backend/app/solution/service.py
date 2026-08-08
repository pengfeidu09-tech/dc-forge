"""B 模块方案编译服务入口。

提供清晰的公开服务函数，实际逻辑委托给 compiler.py 和 recompiler.py。
"""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import RecompileRequest, RecompileResult, SolutionBundle
from backend.app.solution.compiler import compile_solution as _compile_solution
from backend.app.solution.recompiler import recompile_solution as _recompile_solution
from backend.app.contracts.solution_intelligence import SolutionBundleV2
from backend.app.contracts.solution_intelligence import DemoBlueprint, SolutionPlanV2
from backend.app.contracts.solution_intelligence import RecompileSolutionV2Result
from backend.app.contracts.common import BusinessConstraint
from backend.app.solution.demo_blueprint import DemoBlueprintCompiler
from backend.app.solution.solution_intelligence_recompiler import SolutionIntelligenceRecompiler
from backend.app.solution.solution_intelligence_compiler import SolutionIntelligenceCompiler


def compile_solution(process: ProcessSpec) -> SolutionBundle:
    """接收 ProcessSpec，返回包含三套方案的 SolutionBundle。"""
    return _compile_solution(process)


def recompile_solution(request: RecompileRequest) -> RecompileResult:
    """接收 RecompileRequest，返回增量重编译结果。"""
    return _recompile_solution(request)


def compile_solution_v2(process: ProcessSpec) -> SolutionBundleV2:
    return SolutionIntelligenceCompiler().compile(process)


def compile_demo_blueprint(process: ProcessSpec, solution: SolutionPlanV2) -> DemoBlueprint:
    """Service-level B-to-C handoff; it compiles metadata and never executes Runtime."""
    return DemoBlueprintCompiler().compile(process, solution)


def recompile_solution_v2(
    process: ProcessSpec,
    selected_solution: SolutionPlanV2,
    selected_blueprint: DemoBlueprint,
    new_constraints: list[BusinessConstraint],
) -> RecompileSolutionV2Result:
    return SolutionIntelligenceRecompiler().recompile(
        process, selected_solution, selected_blueprint, new_constraints
    )
