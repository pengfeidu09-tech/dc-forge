"""B 模块方案编译入口。

公开导出：
- CapabilityCapsule: 能力胶囊私有模型
- load_capabilities: 能力胶囊加载器
- retrieve_components: 确定性组件检索器
"""

from backend.app.solution.capabilities import CapabilityCapsule, load_capabilities
from backend.app.solution.retriever import retrieve_components

__all__ = [
    "CapabilityCapsule",
    "load_capabilities",
    "retrieve_components",
]
