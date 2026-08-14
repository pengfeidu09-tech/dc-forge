"""企业客户全过程知识包的内容质量、追溯性和去重测试。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "企业客户需求全过程知识管理系统_FINAL_COMPLETE"
KM_PROJECT = PACKAGE / "03_客户项目全过程库" / "华东新程汽车项目"
PLACEHOLDERS = (
    "汽车采购项目模拟业务资料",
    "客户希望AI理解业务背景并关联历史项目",
    "推进当前阶段",
    "整理资料并跟踪事项",
    "针对第",
    "确认下一步行动",
    "采购全过程知识片段，包含需求、会议、文档和经验",
)


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_all_markdown_files_have_substantive_content_without_placeholders() -> None:
    markdown_files = list(PACKAGE.rglob("*.md"))
    assert markdown_files

    for path in markdown_files:
        text = path.read_text(encoding="utf-8").strip()
        assert len(text) >= 400, f"{path.relative_to(PACKAGE)} 内容过短"
        assert text.startswith("# "), f"{path.relative_to(PACKAGE)} 缺少一级标题"
        assert not any(placeholder in text for placeholder in PLACEHOLDERS), path


def test_project_master_and_requirements_form_a_traceable_baseline() -> None:
    master = read_json(KM_PROJECT / "project_master.json")
    requirements = read_json(KM_PROJECT / "02_需求阶段" / "requirements.json")

    assert master["project_id"] == "PRJ-KM-001"
    assert master["data_classification"] == "synthetic_demo"
    assert master["timeline_classification"] == "simulated_future_scenario"
    assert len(master["milestones"]) == 12

    requirement_items = requirements["requirements"]
    assert {item["requirement_id"] for item in requirement_items} == {
        "REQ-001",
        "REQ-002",
        "REQ-003",
    }
    for item in requirement_items:
        assert len(item["versions"]) >= 2
        assert len([v for v in item["versions"] if v["confirmed_baseline"]]) == 1
        assert item["acceptance_criteria"]
        assert item["source_ids"]


def test_meetings_are_detailed_distinct_and_actionable() -> None:
    meeting_paths = sorted((KM_PROJECT / "03_会议记录").glob("MTG-*.md"))
    assert len(meeting_paths) == 12

    bodies = []
    for path in meeting_paths:
        text = path.read_text(encoding="utf-8")
        assert len(text) >= 900, path.name
        for heading in ("## 会议元数据", "## 讨论纪要", "## 决策", "## 行动项", "## 风险与待确认项", "## 关联对象"):
            assert heading in text, f"{path.name} 缺少 {heading}"
        assert "负责人" in text and "截止日期" in text
        bodies.append(re.sub(r"# .*\n", "", text).strip())

    assert len(set(bodies)) == len(bodies)


def test_business_documents_have_metadata_and_requirement_links() -> None:
    document_paths = sorted((KM_PROJECT / "05_业务文档").glob("*.md"))
    assert len(document_paths) >= 8

    for path in document_paths:
        text = path.read_text(encoding="utf-8")
        assert len(text) >= 1200, path.name
        assert "## 文档元数据" in text, path.name
        assert "PRJ-KM-001" in text, path.name
        assert re.search(r"REQ-00[123]", text), path.name
        assert "模拟" in text, path.name


def test_communication_records_are_semantic_and_source_linked() -> None:
    duplicate_dir = KM_PROJECT / "05_沟通记录"
    assert not duplicate_dir.exists()

    records = read_json(KM_PROJECT / "04_沟通记录" / "企业微信项目群.json")
    assert 10 <= len(records) <= 20
    assert len({record["id"] for record in records}) == len(records)

    combined_contents = []
    for record in records:
        assert record["summary"]
        assert record["decision"]
        assert record["actions"]
        assert record["related"]
        content = " ".join(message["content"] for message in record["messages"])
        assert not re.search(r"针对第\d+阶段", content)
        combined_contents.append(content)
    assert len(set(combined_contents)) == len(combined_contents)

    timeline = read_json(KM_PROJECT / "04_沟通记录" / "沟通时间线.json")
    assert len(timeline) >= 12
    assert all(event["source_ids"] and event["related"] for event in timeline)


def test_rag_indexes_are_unique_substantive_and_traceable() -> None:
    knowledge = read_jsonl(PACKAGE / "04_RAG知识库" / "knowledge_chunks.jsonl")
    communications = read_jsonl(PACKAGE / "04_RAG知识库" / "communication_chunks.jsonl")

    assert 25 <= len(knowledge) <= 100
    assert len({chunk["chunk_id"] for chunk in knowledge}) == len(knowledge)
    assert len({chunk["content"] for chunk in knowledge}) == len(knowledge)
    for chunk in knowledge:
        assert chunk["data_classification"] == "synthetic_demo"
        assert chunk["project_id"] == "PRJ-KM-001"
        assert chunk["source_id"]
        assert chunk["source_path"]
        assert chunk["related"]
        assert len(chunk["content"]) >= 80

    assert len(communications) >= 12
    assert len({chunk["content"] for chunk in communications}) == len(communications)
    assert {chunk["source"] for chunk in communications} >= {"wechat", "email"}
    assert all(chunk["source_id"] and chunk["related"] for chunk in communications)


def test_skills_and_mcp_tools_define_executable_contracts() -> None:
    for path in (PACKAGE / "07_Skill技能库").glob("*.yaml"):
        skill = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert skill["version"]
        assert skill["description"]
        assert skill["applicable_scenarios"]
        assert skill["inputs"]
        assert len(skill["workflow"]) >= 4
        assert skill["evidence_requirements"]
        assert skill["guardrails"]
        assert skill["outputs"]

    mcp = read_json(PACKAGE / "05_AI_Agent" / "MCP_tools.json")
    assert len(mcp["tools"]) >= 5
    for tool in mcp["tools"]:
        assert tool["description"]
        assert tool["input_schema"]["properties"]
        assert tool["output_schema"]["properties"]
        assert tool["permission"]
        assert tool["audit"]


def test_image_only_presentation_is_searchable_but_not_authoritative() -> None:
    source_pdf = PACKAGE / "智能招采一体化平台主打PPT.pdf"
    governance_note = PACKAGE / "08_工程说明" / "图片版PPT资料治理说明.md"
    ocr_chunks = read_jsonl(PACKAGE / "04_RAG知识库" / "presentation_ocr_chunks.jsonl")
    metadata = read_json(PACKAGE / "04_RAG知识库" / "metadata.json")

    assert source_pdf.exists()
    assert len(governance_note.read_text(encoding="utf-8")) >= 1000
    assert len(ocr_chunks) == 24
    assert {chunk["page"] for chunk in ocr_chunks} == set(range(1, 25))
    assert all(chunk["ocr_status"] == "completed" for chunk in ocr_chunks)
    assert all(chunk["authority"] == "reference_only" for chunk in ocr_chunks)
    assert all(
        chunk["claim_status"] == "unverified_marketing_claim" for chunk in ocr_chunks
    )
    assert all(chunk["source_path"] == "智能招采一体化平台主打PPT.pdf" for chunk in ocr_chunks)
    assert any("6倍" in chunk["content"] for chunk in ocr_chunks)
    assert any("86%" in chunk["content"] for chunk in ocr_chunks)
    assert any("95%" in chunk["content"] for chunk in ocr_chunks)

    index = next(
        item for item in metadata["indexes"] if item["name"] == "presentation_ocr_chunks.jsonl"
    )
    assert index["authority"] == "reference_only"
    assert index["claim_status"] == "unverified_marketing_claim"
