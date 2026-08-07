from backend.app.contracts.process import ProcessSpec
from backend.app.solution.gene_builder import GeneBuilder


def _process() -> ProcessSpec:
    return ProcessSpec.model_validate(
        {
            "project_id": "gene-builder-test",
            "industry": "制造",
            "department": "采购",
            "business_goal": "缩短招标文件审查周期",
            "roles": ["采购专员", "法务"],
            "available_data": ["历史招标文件", "企业采购制度", "审查规则"],
            "existing_systems": ["OA", "采购系统"],
            "as_is_nodes": [
                {
                    "id": "review-bid-document",
                    "name": "招标文件审查",
                    "actor": "采购专员",
                    "node_type": "human",
                    "description": "采购专员依据审查规则审查招标文件",
                }
            ],
            "pain_points": [
                {
                    "id": "pain-review",
                    "description": "审查依赖专家",
                    "severity": "high",
                    "affected_node_ids": ["review-bid-document"],
                }
            ],
            "constraints": [
                {
                    "id": "approval-rule",
                    "type": "approval",
                    "statement": "超过 50 万元必须人工审批",
                    "hard": True,
                }
            ],
            "target_metrics": ["审查周期"],
            "missing_information": [],
            "clarification_questions": [],
            "readiness_score": 80,
        }
    )


def test_gene_builder_is_deterministic_with_stable_ids() -> None:
    builder = GeneBuilder()

    first = builder.build_from_process(_process())
    second = builder.build_from_process(_process())

    assert [gene.model_dump() for gene in first] == [gene.model_dump() for gene in second]
    assert [gene.gene_id for gene in first] == ["gene-builder-test:review-bid-document"]


def test_gene_builder_uses_only_process_facts_for_node_gene() -> None:
    gene = GeneBuilder().build_from_process(_process())[0]

    assert gene.action_id == "review-bid-document"
    assert gene.action_name == "招标文件审查"
    assert gene.role == ["采购专员"]
    assert gene.data_and_knowledge == ["历史招标文件", "企业采购制度", "审查规则"]
    assert gene.tools == ["OA", "采购系统"]
    assert gene.standards_and_rules == ["超过 50 万元必须人工审批"]
    assert gene.object == []
    assert gene.technology == []


def test_gene_builder_maps_node_type_to_execution_mode() -> None:
    process = _process().model_copy(
        update={
            "as_is_nodes": [
                _process().as_is_nodes[0].model_copy(update={"node_type": "human"}),
                _process().as_is_nodes[0].model_copy(
                    update={"id": "system-node", "node_type": "system"}
                ),
                _process().as_is_nodes[0].model_copy(
                    update={"id": "ai-node", "node_type": "ai"}
                ),
            ]
        }
    )

    genes = GeneBuilder().build_from_process(process)

    assert [gene.execution_mode for gene in genes] == ["human", "system", "ai_assisted"]


def test_gene_builder_carries_global_context_as_retrieval_context_for_each_node() -> None:
    base_process = _process()
    process = base_process.model_copy(
        update={
            "as_is_nodes": [
                base_process.as_is_nodes[0],
                base_process.as_is_nodes[0].model_copy(
                    update={"id": "second-node", "name": "合同归档", "actor": "法务"}
                ),
            ]
        }
    )

    genes = GeneBuilder().build_from_process(process)

    assert [gene.data_and_knowledge for gene in genes] == [
        process.available_data,
        process.available_data,
    ]
    assert [gene.tools for gene in genes] == [process.existing_systems, process.existing_systems]
    assert [gene.standards_and_rules for gene in genes] == [
        [constraint.statement for constraint in process.constraints],
        [constraint.statement for constraint in process.constraints],
    ]
    assert all(gene.object == [] and gene.technology == [] for gene in genes)
