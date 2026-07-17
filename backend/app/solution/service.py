"""B 模块方案编译服务入口。

提供清晰的公开服务函数，实际逻辑委托给 compiler.py 和 recompiler.py。
"""

from __future__ import annotations

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution import RecompileRequest, RecompileResult, SolutionBundle
from backend.app.solution.compiler import compile_solution as _compile_solution
from backend.app.solution.recompiler import recompile_solution as _recompile_solution


def compile_solution(process: ProcessSpec) -> SolutionBundle:
    """接收 ProcessSpec，返回包含三套方案的 SolutionBundle。"""
    return _compile_solution(process)


def recompile_solution(request: RecompileRequest) -> RecompileResult:
    """接收 RecompileRequest，返回增量重编译结果。"""
    return _recompile_solution(request)
