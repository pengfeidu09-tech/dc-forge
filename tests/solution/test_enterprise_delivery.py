"""DELIVERY-M1 enterprise handoff package tests."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZipFile

from backend.app.solution.enterprise_delivery import (
    EnterpriseDeliveryBrief,
    EnterpriseDeliveryPackageBuilder,
)


EXPECTED_FILES = {
    "01_DCFORGE_大型汽车制造企业智能招采与采购合规解决方案.pptx",
    "02_DCFORGE_解决方案建议书.pdf",
    "03_DCFORGE_解决方案建议书.html",
    "04_DCFORGE_实施与验收计划.xlsx",
    "05_DCFORGE_部署安全与集成边界.md",
    "06_DCFORGE_演示与操作手册.md",
    "README_交付说明.md",
    "manifest.json",
}


def _pptx_text(path: Path) -> tuple[int, str]:
    with ZipFile(path) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
        text = "\n".join(
            archive.read(name).decode("utf-8") for name in slide_names
        )
    return len(slide_names), text


def test_default_brief_uses_only_safe_automotive_presales_facts() -> None:
    brief = EnterpriseDeliveryBrief.default_automotive_procurement()
    serialized = json.dumps(brief.to_dict(), ensure_ascii=False)

    assert "大型汽车制造企业" in serialized
    assert "供应商准入" in serialized
    assert "询比价" in serialized
    assert "采购合规审查" in serialized
    assert "待双方确认" in serialized
    assert "华东师范大学" not in serialized
    assert "教育" not in serialized
    assert "小米" not in serialized
    assert "SU7" not in serialized
    assert "10台" not in serialized
    assert "已实现" not in serialized


def test_enterprise_delivery_package_is_complete_editable_and_customer_safe(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "enterprise-delivery"
    builder = EnterpriseDeliveryPackageBuilder(
        EnterpriseDeliveryBrief.default_automotive_procurement()
    )

    result = builder.build(output_dir)

    assert set(path.name for path in output_dir.iterdir()) == EXPECTED_FILES
    assert result.archive_path.name == "DCFORGE_企业智能招采解决方案交付包_v1.0.zip"
    assert result.archive_path.is_file()

    pptx_path = output_dir / next(name for name in EXPECTED_FILES if name.endswith(".pptx"))
    pdf_path = output_dir / next(name for name in EXPECTED_FILES if name.endswith(".pdf"))
    html_path = output_dir / next(name for name in EXPECTED_FILES if name.endswith(".html"))
    xlsx_path = output_dir / next(name for name in EXPECTED_FILES if name.endswith(".xlsx"))

    assert pptx_path.read_bytes().startswith(b"PK")
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert xlsx_path.read_bytes().startswith(b"PK")
    assert min(path.stat().st_size for path in output_dir.iterdir()) > 100

    slide_count, pptx_xml = _pptx_text(pptx_path)
    assert slide_count >= 18
    assert "Requirement Intelligence" in pptx_xml
    assert "MCP" in pptx_xml
    assert "人工审批" in pptx_xml

    html = html_path.read_text(encoding="utf-8")
    assert "大型汽车制造企业智能招采与采购合规解决方案" in html
    assert "供应商准入" in html
    assert "建议验收口径" in html
    assert "待双方确认" in html
    assert "review_score" not in html
    assert "asset_id" not in html
    assert "open_id" not in html
    assert "tenant_key" not in html
    assert "chat_id" not in html
    assert "华东师范大学" not in html
    assert "小米" not in html

    with ZipFile(xlsx_path) as archive:
        workbook_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xml")
        )
    assert "实施计划" in workbook_xml
    assert "验收指标" in workbook_xml
    assert "接口清单" in workbook_xml
    assert "双方待办" in workbook_xml

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["package_version"] == "1.0"
    assert manifest["document_status"] == "客户交流与试点立项建议稿"
    assert manifest["business_results_status"] == "未验证"
    assert {item["name"] for item in manifest["files"]} == EXPECTED_FILES - {
        "manifest.json"
    }
    for item in manifest["files"]:
        path = output_dir / item["name"]
        assert item["sha256"] == sha256(path.read_bytes()).hexdigest()

    with ZipFile(result.archive_path) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
