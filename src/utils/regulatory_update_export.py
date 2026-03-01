"""
AI-QMS — Regulatory Update Report Export Module
================================================

Export regulatory crawl update results to Word (.docx) and Excel (.xlsx) formats.
Follows the same patterns as regulatory_export.py for consistency.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


# Output directory for generated files
EXPORT_DIR = Path("data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Shared styles (same as regulatory_export.py)
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(name="Microsoft JhengHei", size=10, bold=True, color="FFFFFF")
CELL_FONT = Font(name="Microsoft JhengHei", size=9)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Status colors for Excel
SUCCESS_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
FAIL_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")


# ============================================================
# Helper Functions
# ============================================================


def _strip_markdown(text: str) -> str:
    """Strip markdown formatting for plain text preview."""
    text = re.sub(r"#{1,6}\s+", "", text)  # headers
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # italic
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"[-*+]\s+", "", text)  # list markers
    text = re.sub(r"\n+", " ", text)  # newlines
    return text.strip()


def _get_qms_mapping(agency: str, region: str = "") -> str:
    """Map agency/region to related QMS standards/regulations."""
    mapping = {
        "FDA": "21 CFR 820 (QSR/QMSR), FDA Guidance",
        "eCFR": "21 CFR Part 820, Part 11",
        "TFDA": "醫療器材管理法, GMP",
        "PMDA": "QMS省令 (MHLW Ordinance 169), JIS T 2304",
        "NMPA": "醫療器械生產質量管理規範",
        "TGA": "Australian Medical Device Standards",
        "MFDS": "KGMP (Korean GMP)",
        "HSA": "Singapore Medical Device GMP",
        "CDSCO": "India MDR 2017",
        "ANVISA": "Brazil RDC 665/2022",
        "Health_Canada": "CMDR (SOR/98-282), ISO 13485",
        "Swissmedic": "MepV (Swiss Medical Devices Ordinance)",
        "COFEPRIS": "Mexico NOM Standards",
        "EMA": "EU MDR 2017/745, EU IVDR 2017/746",
        "MDCG": "EU MDR Guidance Documents",
        "BSI": "EU MDR, UKCA Marking",
        "ISO": "ISO 13485, ISO 14971, IEC 62304",
        "EUR-Lex": "EU MDR/IVDR Regulations",
    }
    for key, val in mapping.items():
        if key.upper() in agency.upper():
            return val
    # Generic fallback based on region
    if any(kw in region.upper() for kw in ["EU", "歐盟", "欧盟", "EUROPE"]):
        return "EU MDR 2017/745"
    return "ISO 13485"


# ============================================================
# Markdown Format (for Chainlit chat display)
# ============================================================


def format_regulatory_update_markdown(
    crawl_results: dict, assessment: Optional[str] = None
) -> str:
    """Format crawl results as Markdown for Chainlit chat display."""
    results = crawl_results.get("results", [])
    summary = crawl_results.get("summary", {})

    total = summary.get("total_sites", 0)
    success = summary.get("success_count", 0)

    duration = summary.get("crawl_duration_seconds", 0)
    regions = summary.get("regions_covered", [])

    lines = [
        f"📋 **法規清單更新結果** (成功 {success}/{total} 個網站，耗時 {duration:.1f} 秒)\n",
        f"涵蓋地區: {', '.join(regions)}\n",
        "### 爬取結果摘要\n",
        "| 地區 | 機構 | 狀態 | 內容摘要 | QMS 對應 |",
        "|------|------|------|----------|----------|",
    ]

    for r in results:
        region = r.get("region", "")
        agency = r.get("agency", "")
        status = "✅" if r.get("crawl_status") == "success" else "❌"
        qms = _get_qms_mapping(agency, region)

        if r.get("crawl_status") == "success":
            content = r.get("content_markdown", "")
            preview = _strip_markdown(content)[:50] if content else ""
        elif r.get("crawl_status") == "failed":
            reason = r.get("failure_reason", "未知原因")
            preview = reason[:50] + "..." if len(reason) > 50 else reason
        else:
            preview = r.get("note", "")[:50]

        lines.append(f"| {region} | {agency} | {status} | {preview} | {qms[:30]} |")

    # Failed sites section
    failed_results = [r for r in results if r.get("crawl_status") == "failed"]
    if failed_results:
        lines.append("\n### ⚠️ 無法爬取的網站\n")
        for r in failed_results:
            reason = r.get("failure_reason", "未知原因")
            lines.append(f"- **{r['region']} — {r['agency']}**: {reason}")
        lines.append("")

    # Assessment section
    if assessment:
        lines.append("\n---\n")
        lines.append("### 📊 QMS 評估報告\n")
        lines.append(assessment)

    return "\n".join(lines)


# ============================================================
# Word Export
# ============================================================


def export_regulatory_update_to_word(
    crawl_results: dict, assessment: Optional[str] = None
) -> str:
    """Export regulatory update results to Word (.docx).

    Returns:
        Path to the generated .docx file.
    """
    results = crawl_results.get("results", [])
    summary = crawl_results.get("summary", {})

    total = summary.get("total_sites", 0)
    success = summary.get("success_count", 0)
    failed = summary.get("failed_count", 0)
    duration = summary.get("crawl_duration_seconds", 0)

    doc = Document()

    # Title
    title = doc.add_heading("AI-QMS 法規清單更新報告", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    meta2 = doc.add_paragraph()
    meta2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run2 = meta2.add_run(
        f"掃描網站: {total} | 成功: {success} | 失敗: {failed} | 耗時: {duration:.1f}秒"
    )
    run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    # Section 1: Summary Table (enhanced with structured columns)
    doc.add_heading("一、法規更新摘要", level=2)

    table1 = doc.add_table(rows=1, cols=7)
    table1.style = "Table Grid"
    table1.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["地區", "機構", "URL", "狀態", "內容摘要", "儲存路徑", "QMS 對應"]
    for i, header in enumerate(headers):
        cell = table1.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(9)

    for r in results:
        row = table1.add_row()
        region = r.get("region", "")
        agency = r.get("agency", "")
        status_text = "成功" if r.get("crawl_status") == "success" else "失敗"

        # Content summary
        content = r.get("content_markdown", "")
        content_summary = (
            _strip_markdown(content)[:100]
            if content
            else (r.get("failure_reason", "")[:100])
        )

        # Storage path
        storage_path = (
            f"regulatory_markdown_storage/documents/{region}/{agency}_*.md"
            if r.get("crawl_status") == "success"
            else ""
        )

        # QMS mapping
        qms = _get_qms_mapping(agency, region)

        values = [
            region,
            agency,
            r.get("url", "")[:80],
            status_text,
            content_summary,
            storage_path,
            qms,
        ]
        for i, val in enumerate(values):
            cell = row.cells[i]
            cell.text = val
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)

    widths = [Cm(2), Cm(2), Cm(3.5), Cm(1.2), Cm(3.5), Cm(2.5), Cm(3)]
    for row in table1.rows:
        for i, width in enumerate(widths):
            row.cells[i].width = width

    doc.add_paragraph()

    # Section 2: Content Details
    success_results = [r for r in results if r.get("crawl_status") == "success"]
    if success_results:
        doc.add_heading("二、各地區法規詳情", level=2)

        for r in success_results:
            doc.add_heading(
                f"{r.get('region', '')} — {r.get('agency', '')}",
                level=3,
            )
            content = r.get("content_markdown", "")
            preview = content[:1000] if len(content) > 1000 else content
            p = doc.add_paragraph(preview)
            for run in p.runs:
                run.font.size = Pt(8)
            if len(content) > 1000:
                trunc = doc.add_paragraph(
                    "... (內容已截斷，完整內容請參閱 Markdown 檔案)"
                )
                for run in trunc.runs:
                    run.font.size = Pt(8)
                    run.font.italic = True
            doc.add_paragraph()

    # Section 3: Assessment Report
    if assessment:
        doc.add_heading("三、QMS 評估報告", level=2)
        # Split assessment into paragraphs
        for para_text in assessment.split("\n"):
            stripped = para_text.strip()
            if not stripped:
                doc.add_paragraph()
                continue
            if stripped.startswith("###"):
                doc.add_heading(stripped.lstrip("#").strip(), level=4)
            elif stripped.startswith("##"):
                doc.add_heading(stripped.lstrip("#").strip(), level=3)
            elif stripped.startswith("#"):
                doc.add_heading(stripped.lstrip("#").strip(), level=2)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                p = doc.add_paragraph(stripped[2:], style="List Bullet")
                for run in p.runs:
                    run.font.size = Pt(9)
            elif stripped.startswith(tuple(f"{i}." for i in range(1, 20))):
                p = doc.add_paragraph(stripped, style="List Number")
                for run in p.runs:
                    run.font.size = Pt(9)
            else:
                p = doc.add_paragraph(stripped)
                for run in p.runs:
                    run.font.size = Pt(9)

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    run = footer.add_run(
        "本報告由 AI-QMS 品質管理系統自動產生。"
        "法規資訊透過網路爬取取得，僅供參考，請以各國官方網站公告為準。"
    )
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(128, 128, 128)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"regulatory_update_{timestamp}.docx"
    filepath = EXPORT_DIR / filename
    doc.save(str(filepath))
    return str(filepath)


# ============================================================
# Excel Export
# ============================================================


def export_regulatory_update_to_excel(
    crawl_results: dict, assessment: Optional[str] = None
) -> str:
    """Export regulatory update results to Excel (.xlsx).

    Returns:
        Path to the generated .xlsx file.
    """
    results = crawl_results.get("results", [])
    summary = crawl_results.get("summary", {})

    total = summary.get("total_sites", 0)
    success = summary.get("success_count", 0)
    failed = summary.get("failed_count", 0)
    duration = summary.get("crawl_duration_seconds", 0)

    wb = Workbook()

    # Sheet 1: Summary (enhanced with structured columns)
    ws1 = wb.active
    ws1.title = "更新摘要"

    # Title
    ws1.merge_cells("A1:G1")
    title_cell = ws1.cell(row=1, column=1)
    title_cell.value = "AI-QMS 法規清單更新報告"
    title_cell.font = Font(name="Microsoft JhengHei", size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    # Metadata
    ws1.merge_cells("A2:G2")
    meta_cell = ws1.cell(row=2, column=1)
    meta_cell.value = (
        f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"掃描網站: {total} | 成功: {success} | 失敗: {failed} | 耗時: {duration:.1f}秒"
    )
    meta_cell.font = Font(
        name="Microsoft JhengHei", size=9, italic=True, color="808080"
    )

    # Headers (enhanced)
    headers = ["地區", "機構", "URL", "狀態", "內容摘要", "儲存路徑", "QMS 對應"]
    for col, header in enumerate(headers, 1):
        cell = ws1.cell(row=4, column=col)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    # Data
    for row_idx, r in enumerate(results, 5):
        region = r.get("region", "")
        agency = r.get("agency", "")
        status_text = "成功" if r.get("crawl_status") == "success" else "失敗"

        # Content summary
        content = r.get("content_markdown", "")
        content_summary = (
            _strip_markdown(content)[:150]
            if content
            else (r.get("failure_reason", "")[:150])
        )

        # Storage path
        storage_path = (
            f"regulatory_markdown_storage/documents/{region}/{agency}_*.md"
            if r.get("crawl_status") == "success"
            else ""
        )

        # QMS mapping
        qms = _get_qms_mapping(agency, region)

        values = [
            region,
            agency,
            r.get("url", ""),
            status_text,
            content_summary,
            storage_path,
            qms,
        ]
        for col, val in enumerate(values, 1):
            cell = ws1.cell(row=row_idx, column=col)
            cell.value = val
            cell.font = CELL_FONT
            cell.border = THIN_BORDER

        # Color status cell
        status_cell = ws1.cell(row=row_idx, column=4)
        if status_text == "成功":
            status_cell.fill = SUCCESS_FILL
        else:
            status_cell.fill = FAIL_FILL

    ws1.column_dimensions["A"].width = 15
    ws1.column_dimensions["B"].width = 15
    ws1.column_dimensions["C"].width = 40
    ws1.column_dimensions["D"].width = 8
    ws1.column_dimensions["E"].width = 40
    ws1.column_dimensions["F"].width = 25
    ws1.column_dimensions["G"].width = 30
    ws1.freeze_panes = "A5"

    # Sheet 2: Assessment Report (if provided)
    if assessment:
        ws3 = wb.create_sheet("評估報告")

        ws3.merge_cells("A1:B1")
        title_cell3 = ws3.cell(row=1, column=1)
        title_cell3.value = "QMS 評估報告"
        title_cell3.font = Font(name="Microsoft JhengHei", size=14, bold=True)
        title_cell3.alignment = Alignment(horizontal="center")

        # Write assessment as rows
        assessment_lines = assessment.split("\n")
        for row_idx, line in enumerate(assessment_lines, 3):
            cell = ws3.cell(row=row_idx, column=1)
            cell.value = line
            if line.strip().startswith("#"):
                cell.font = Font(name="Microsoft JhengHei", size=11, bold=True)
            else:
                cell.font = CELL_FONT

        ws3.column_dimensions["A"].width = 100

    # Footer note
    note_row = len(results) + 6
    ws1.merge_cells(f"A{note_row}:G{note_row}")
    note_cell = ws1.cell(row=note_row, column=1)
    note_cell.value = (
        "本報告由 AI-QMS 品質管理系統自動產生。"
        "法規資訊透過網路爬取取得，僅供參考，請以各國官方網站公告為準。"
    )
    note_cell.font = Font(
        name="Microsoft JhengHei", size=8, italic=True, color="808080"
    )

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"regulatory_update_{timestamp}.xlsx"
    filepath = EXPORT_DIR / filename
    wb.save(str(filepath))
    return str(filepath)
