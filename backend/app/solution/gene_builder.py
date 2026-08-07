"""Deterministic ProcessSpec-to-AIGene construction for asset retrieval."""

from backend.app.contracts.process import ProcessSpec
from backend.app.contracts.solution_intelligence import AIGene, ExecutionMode


_EXECUTION_MODE_BY_NODE_TYPE: dict[str, ExecutionMode] = {
    "human": "human",
    "system": "system",
    "ai": "ai_assisted",
}


class GeneBuilder:
    """Build minimal retrieval genes from facts already present in ProcessSpec.

    Process-wide data, systems and constraints are copied as retrieval context.
    They do not claim that every individual action has confirmed requirements for them.
    """

    def build_from_process(self, process: ProcessSpec) -> list[AIGene]:
        constraint_statements = [constraint.statement for constraint in process.constraints]

        return [
            AIGene(
                gene_id=f"{process.project_id}:{node.id}",
                action_id=node.id,
                action_name=node.name,
                role=[node.actor] if node.actor else [],
                # These fields are shared query context in B-M8.2, not node-specific requirements.
                data_and_knowledge=list(process.available_data),
                standards_and_rules=constraint_statements,
                tools=list(process.existing_systems),
                inputs=list(process.available_data),
                execution_mode=_EXECUTION_MODE_BY_NODE_TYPE[node.node_type],
            )
            for node in process.as_is_nodes
        ]
