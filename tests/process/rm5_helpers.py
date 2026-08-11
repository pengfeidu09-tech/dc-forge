from __future__ import annotations

from pathlib import Path

from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementItem,
    RequirementSourceRef,
    RequirementState,
)
from backend.app.process.conflict_detector import ConflictDetector
from backend.app.process.gap_detector import GapDetector
from backend.app.process.readiness import ReadinessEvaluator
from backend.app.process.requirement_baseline import RequirementBaselineBuilder
from backend.app.process.requirement_skill import RequirementSkillLoader


SKILL_ROOT = Path(__file__).parents[2] / "data" / "requirement_skills"
PROJECT_ID = "synthetic-automotive-procurement-rm5"


def skill():
    return RequirementSkillLoader(SKILL_ROOT).resolve("automotive-procurement-v1")


def item(
    requirement_id: str,
    category: str,
    subject: str,
    value: str,
    *,
    parameters: dict | None = None,
    process_detail: dict | None = None,
    pain_point_detail: dict | None = None,
    status: str = "confirmed",
    confirmation_level: str = "customer",
    supersedes: list[str] | None = None,
) -> RequirementItem:
    return RequirementItem(
        requirement_id=requirement_id,
        category=category,
        subject=subject,
        value=value,
        parameters=parameters or {},
        provenance="customer_raw",
        status=status,
        confirmation_level=confirmation_level,
        confidence=1,
        source_refs=[RequirementSourceRef(source_id="customer-1", excerpt=value)],
        process_detail=process_detail,
        pain_point_detail=pain_point_detail,
        supersedes_requirement_ids=supersedes or [],
    )


def base_items(*, approval: int = 500000, goal: str = "缩短招标文件编制与审查周期，降低合规风险"):
    return [
        item("req-industry", "industry", "industry", "制造"),
        item("req-department", "department", "department", "采购中心"),
        item("req-goal", "business_goal", "goal", goal),
        item("req-role", "role", "buyer", "采购专员"),
        item(
            "req-process-1", "current_process", "document intake", "接收招标文件",
            process_detail={
                "process_node_id": "intake", "name": "招标文件接收", "actor": "采购专员",
                "node_type": "human", "description": "接收招标文件",
                "next_node_ids": ["review"],
            },
        ),
        item(
            "req-process-2", "current_process", "document review", "审查招标文件并定位风险",
            process_detail={
                "process_node_id": "review", "name": "招标文件审查", "actor": "采购专员",
                "node_type": "human", "description": "采购专员依据审查规则审查招标文件并定位风险",
                "next_node_ids": [],
            },
        ),
        item(
            "req-pain", "pain_point", "manual review", "人工审查周期长且合规风险定位慢",
            pain_point_detail={
                "pain_point_id": "manual-review", "description": "人工审查周期长且合规风险定位慢",
                "severity": "high", "affected_process_node_ids": ["review"],
            },
        ),
        item("req-data-1", "available_data", "historical documents", "历史招标文件"),
        item("req-data-2", "available_data", "rules", "企业采购制度"),
        item("req-data-3", "available_data", "review rules", "审查规则"),
        item("req-system", "existing_system", "OA", "OA"),
        item("req-security", "security", "deployment boundary", "数据不得出企业私域"),
        item(
            f"req-approval-{approval}", "approval", "procurement approval threshold",
            f"超过{approval}必须人工审批",
            parameters={"threshold": approval},
        ),
        item("req-metric-1", "target_metric", "processing time", "processing_time"),
        item("req-metric-2", "target_metric", "risk findings", "risk_findings"),
    ]


def state_and_baseline(
    *,
    state_version: int = 1,
    baseline_version: int = 1,
    approval: int = 500000,
    goal: str = "缩短招标文件编制与审查周期，降低合规风险",
    extra_items: list[RequirementItem] | None = None,
) -> tuple[RequirementState, RequirementBaseline]:
    state = RequirementState(
        project_id=PROJECT_ID,
        state_version=state_version,
        source_ids=["customer-1"],
        selected_skill_id="automotive-procurement-v1",
        items=base_items(approval=approval, goal=goal) + (extra_items or []),
    )
    resolved = skill()
    conflicts = ConflictDetector().detect(state, resolved)
    gaps = GapDetector().detect(state, resolved, conflicts)
    state = state.model_copy(update={"gaps": gaps, "conflicts": conflicts})
    readiness = ReadinessEvaluator().evaluate(
        state, resolved, gaps, conflicts, customer_confirmation_complete=True
    )
    baseline = RequirementBaselineBuilder(resolved).build(
        state,
        readiness,
        baseline_version=baseline_version,
        confirmed_by="synthetic-customer-owner",
        confirmation_summary="Synthetic/de-identified customer confirmation.",
    )
    return state, baseline
