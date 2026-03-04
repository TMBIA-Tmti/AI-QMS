"""
AI-QMS — Regulatory Update Report Export Module
================================================

Export regulatory crawl update results to Word (.docx) and Excel (.xlsx) formats.
Follows the same patterns as regulatory_export.py for consistency.
"""

import json
import os
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


# ── i18n helpers ──


def _t(key: str, lang: str = "zh-TW", **kwargs) -> str:
    """Translate a key using locale JSON files."""
    _cache = getattr(_t, "_cache", {})
    if lang not in _cache:
        locale_path = os.path.join(
            os.path.dirname(__file__), "..", "chainlit_app", "locales", f"{lang}.json"
        )
        try:
            with open(locale_path, "r", encoding="utf-8") as f:
                _cache[lang] = json.load(f)
        except Exception:
            _cache[lang] = {}
        _t._cache = _cache
    text = _cache.get(lang, {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def _tl(key: str, lang: str = "zh-TW") -> list:
    """Translate a key that returns a list (e.g. table headers)."""
    _cache = getattr(_t, "_cache", {})
    if lang not in _cache:
        _t(key, lang)  # populate cache
        _cache = getattr(_t, "_cache", {})
    val = _cache.get(lang, {}).get(key)
    return val if isinstance(val, list) else [key]


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
    crawl_results: dict,
    assessment: Optional[str] = None,
    lang: str = "zh-TW",
) -> str:
    """Format crawl results as Markdown for Chainlit chat display."""
    results = crawl_results.get("results", [])
    summary = crawl_results.get("summary", {})

    total = summary.get("total_sites", 0)
    success = summary.get("success_count", 0)

    duration = summary.get("crawl_duration_seconds", 0)
    regions = summary.get("regions_covered", [])

    md_headers = _tl("regulatory_update_export.table_headers_md", lang)

    lines = [
        _t(
            "regulatory_update_export.result_title",
            lang,
            success=success,
            total=total,
            duration=f"{duration:.1f}",
        )
        + "\n",
        _t("regulatory_update_export.regions_covered", lang, regions=", ".join(regions))
        + "\n",
        f"### {_t('regulatory_update_export.summary_table', lang)}\n",
        f"| {' | '.join(md_headers)} |",
        f"|{'|'.join(['------' for _ in md_headers])}|",
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
            reason = r.get(
                "failure_reason", _t("regulatory_update_export.unknown_reason", lang)
            )
            preview = reason[:50] + "..." if len(reason) > 50 else reason
        else:
            preview = r.get("note", "")[:50]

        lines.append(f"| {region} | {agency} | {status} | {preview} | {qms[:30]} |")

    # Failed sites section
    failed_results = [r for r in results if r.get("crawl_status") == "failed"]
    if failed_results:
        lines.append(f"\n### {_t('regulatory_update_export.failed_sites', lang)}\n")
        for r in failed_results:
            reason = r.get(
                "failure_reason", _t("regulatory_update_export.unknown_reason", lang)
            )
            lines.append(f"- **{r['region']} — {r['agency']}**: {reason}")
        lines.append("")

    # Assessment section
    if assessment:
        lines.append("\n---\n")
        lines.append(f"### {_t('regulatory_export.assessment_report', lang)}\n")
        lines.append(assessment)

    return "\n".join(lines)


# ============================================================
# Word Export
# ============================================================


def _source_label(source_command: str, lang: str = "zh-TW") -> str:
    labels = {
        "regulatory_list": _t("source_label.regulatory_list", lang),
        "regulatory_update": _t("source_label.regulatory_update", lang),
    }
    return labels.get(source_command, source_command)


def export_regulatory_update_to_word(
    crawl_results: dict,
    assessment: Optional[str] = None,
    verification_report: Optional[dict] = None,
    lang: str = "zh-TW",
    source_command: str = "regulatory_update",
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

    src_label = _source_label(source_command, lang)
    doc = Document()

    # Title
    title = doc.add_heading(
        f"{_t('regulatory_update_export.title', lang)}（{src_label}）", level=1
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(
        f"{_t('regulatory_export.export_time', lang)}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"{_t('source_label.source', lang)}: {src_label}"
    )
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    meta2 = doc.add_paragraph()
    meta2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run2 = meta2.add_run(
        _t(
            "regulatory_update_export.meta_stats",
            lang,
            total=total,
            success=success,
            failed=failed,
            duration=f"{duration:.1f}",
        )
    )
    run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    # Section 1: Summary Table (enhanced with structured columns)
    doc.add_heading(_t("regulatory_update_export.summary_heading", lang), level=2)

    table1 = doc.add_table(rows=1, cols=7)
    table1.style = "Table Grid"
    table1.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = _tl("regulatory_update_export.table_headers", lang)
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
        status_text = (
            _t("regulatory_update_export.crawl_status_success", lang)
            if r.get("crawl_status") == "success"
            else _t("regulatory_update_export.crawl_status_fail", lang)
        )

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
        doc.add_heading(
            _t("regulatory_update_export.content_detail_heading", lang), level=2
        )

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
                    _t("regulatory_export.content_truncated", lang)
                )
                for run in trunc.runs:
                    run.font.size = Pt(8)
                    run.font.italic = True
            doc.add_paragraph()

    # Section 3: Assessment Report
    if assessment:
        doc.add_heading(_t("regulatory_export.assessment_heading", lang), level=2)
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

    # Section: Verification Report (if provided)
    if verification_report and verification_report.get("has_data"):
        # Reuse the shared verification renderer from regulatory_export
        from src.utils.regulatory_export import _render_verification_to_word

        _render_verification_to_word(doc, verification_report, lang)

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    run = footer.add_run(
        f"{_t('regulatory_update_export.footer', lang)} | "
        f"{_t('source_label.source', lang)}: {src_label}"
    )
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(128, 128, 128)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cmd_tag = "list" if source_command == "regulatory_list" else "update"
    filename = f"regulatory_update_{cmd_tag}_{timestamp}.docx"
    filepath = EXPORT_DIR / filename
    doc.save(str(filepath))
    return str(filepath)


# ============================================================
# Excel Export
# ============================================================


def export_regulatory_update_to_excel(
    crawl_results: dict,
    assessment: Optional[str] = None,
    verification_report: Optional[dict] = None,
    lang: str = "zh-TW",
    source_command: str = "regulatory_update",
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

    src_label = _source_label(source_command, lang)
    wb = Workbook()

    # Sheet 1: Summary (enhanced with structured columns)
    ws1 = wb.active
    ws1.title = _t("regulatory_update_export.summary_sheet", lang)

    # Title
    ws1.merge_cells("A1:G1")
    title_cell = ws1.cell(row=1, column=1)
    title_cell.value = f"{_t('regulatory_update_export.title', lang)}（{src_label}）"
    title_cell.font = Font(name="Microsoft JhengHei", size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    # Metadata
    ws1.merge_cells("A2:G2")
    meta_cell = ws1.cell(row=2, column=1)
    meta_cell.value = (
        f"{_t('regulatory_export.export_time', lang)}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"{_t('source_label.source', lang)}: {src_label} | "
        + _t(
            "regulatory_update_export.meta_stats",
            lang,
            total=total,
            success=success,
            failed=failed,
            duration=f"{duration:.1f}",
        )
    )
    meta_cell.font = Font(
        name="Microsoft JhengHei", size=9, italic=True, color="808080"
    )

    # Headers (enhanced)
    headers = _tl("regulatory_update_export.table_headers", lang)
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
        status_text = (
            _t("regulatory_update_export.crawl_status_success", lang)
            if r.get("crawl_status") == "success"
            else _t("regulatory_update_export.crawl_status_fail", lang)
        )

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
        if status_text == _t("regulatory_update_export.crawl_status_success", lang):
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
        from src.utils.regulatory_export import _render_assessment_to_excel

        _render_assessment_to_excel(wb, assessment, lang)

    # Sheet: Verification Report (if provided)
    if verification_report and verification_report.get("has_data"):
        from src.utils.regulatory_export import _render_verification_to_excel

        _render_verification_to_excel(wb, verification_report, lang)

    # Footer note
    note_row = len(results) + 6
    ws1.merge_cells(f"A{note_row}:G{note_row}")
    note_cell = ws1.cell(row=note_row, column=1)
    note_cell.value = (
        f"{_t('regulatory_update_export.footer', lang)} | "
        f"{_t('source_label.source', lang)}: {src_label}"
    )
    note_cell.font = Font(
        name="Microsoft JhengHei", size=8, italic=True, color="808080"
    )

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cmd_tag = "list" if source_command == "regulatory_list" else "update"
    filename = f"regulatory_update_{cmd_tag}_{timestamp}.xlsx"
    filepath = EXPORT_DIR / filename
    wb.save(str(filepath))
    return str(filepath)
