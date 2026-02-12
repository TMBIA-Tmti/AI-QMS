"""
AI-QMS Phase 1 - 法規清單與引用清單匯出模組
Export regulatory standards list and document reference list to Word/Excel formats.
"""

from datetime import datetime
from pathlib import Path
from typing import List

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


# Output directory for generated files
EXPORT_DIR = Path("data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Shared styles
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(name="Microsoft JhengHei", size=10, bold=True, color="FFFFFF")
CELL_FONT = Font(name="Microsoft JhengHei", size=9)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


# ============================================================
# 法規清單 (Regulatory Standards List)
# ============================================================


def format_regulatory_table_markdown(scan_result: dict) -> str:
    """Format regulatory scan result as Markdown for chat display."""
    by_doc = scan_result.get("by_document", [])
    aggregate = scan_result.get("aggregate", [])

    if not aggregate:
        return "📋 資料庫中的文件未引用任何法規或標準。"

    lines = [
        f"📋 **法規清單** (共 {len(aggregate)} 項標準，涵蓋 {len(by_doc)} 份文件)\n",
        "### 標準彙總\n",
        "| 標準 | 引用文件數 | 引用文件 |",
        "|------|-----------|---------|",
    ]

    for entry in aggregate:
        std = entry["standard"]
        refs = entry["referenced_by"]
        ref_str = ", ".join(refs[:5])
        if len(refs) > 5:
            ref_str += f" ...等 {len(refs)} 份"
        lines.append(f"| {std} | {len(refs)} | {ref_str} |")

    lines.append(f"\n### 各文件引用明細\n")
    lines.append("| 文件編號 | 文件名稱 | 版本 | 引用標準 |")
    lines.append("|---------|---------|------|---------|")

    for doc in by_doc:
        stds = ", ".join(doc["standards"][:5])
        if len(doc["standards"]) > 5:
            stds += f" ...等 {len(doc['standards'])} 項"
        lines.append(
            f"| {doc['doc_id']} | {doc['title'][:30]} | v{doc['current_version']} | {stds} |"
        )

    lines.append(f"\n💡 輸入「下載法規清單 word」或「下載法規清單 excel」可匯出檔案")
    return "\n".join(lines)


def export_regulatory_to_word(scan_result: dict) -> str:
    """
    Export regulatory standards list to Word (.docx).

    Returns:
        Path to the generated .docx file.
    """
    by_doc = scan_result.get("by_document", [])
    aggregate = scan_result.get("aggregate", [])

    doc = Document()

    # Title
    title = doc.add_heading("AI-QMS 法規標準引用清單", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    meta2 = doc.add_paragraph()
    meta2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run2 = meta2.add_run(f"標準總數: {len(aggregate)} 項 | 涵蓋文件: {len(by_doc)} 份")
    run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    if not aggregate:
        doc.add_paragraph("資料庫中的文件未引用任何法規或標準。")
    else:
        # Section 1: Aggregate standards
        doc.add_heading("一、標準彙總", level=2)

        table1 = doc.add_table(rows=1, cols=3)
        table1.style = "Table Grid"
        table1.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers = ["標準", "引用文件數", "引用文件"]
        for i, header in enumerate(headers):
            cell = table1.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(9)

        for entry in aggregate:
            row = table1.add_row()
            values = [
                entry["standard"],
                str(len(entry["referenced_by"])),
                ", ".join(entry["referenced_by"]),
            ]
            for i, val in enumerate(values):
                cell = row.cells[i]
                cell.text = val
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)

        widths = [Cm(5), Cm(2.5), Cm(10)]
        for row in table1.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = width

        doc.add_paragraph()

        # Section 2: Per-document detail
        doc.add_heading("二、各文件引用明細", level=2)

        table2 = doc.add_table(rows=1, cols=5)
        table2.style = "Table Grid"
        table2.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers2 = ["文件編號", "文件名稱", "類型", "版本", "引用標準"]
        for i, header in enumerate(headers2):
            cell = table2.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(9)

        for d in by_doc:
            row = table2.add_row()
            values = [
                d["doc_id"],
                d["title"],
                d["doc_type"],
                f"v{d['current_version']}",
                ", ".join(d["standards"]),
            ]
            for i, val in enumerate(values):
                cell = row.cells[i]
                cell.text = val
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)

        widths2 = [Cm(2.5), Cm(5), Cm(1.5), Cm(1.5), Cm(7)]
        for row in table2.rows:
            for i, width in enumerate(widths2):
                row.cells[i].width = width

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    run = footer.add_run(
        "本報告由 AI-QMS 品質管理系統自動產生。法規標準資訊擷取自文件 OCR 內容，僅供參考。"
    )
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(128, 128, 128)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"regulatory_standards_{timestamp}.docx"
    filepath = EXPORT_DIR / filename
    doc.save(str(filepath))
    return str(filepath)


def export_regulatory_to_excel(scan_result: dict) -> str:
    """
    Export regulatory standards list to Excel (.xlsx).

    Returns:
        Path to the generated .xlsx file.
    """
    by_doc = scan_result.get("by_document", [])
    aggregate = scan_result.get("aggregate", [])

    wb = Workbook()

    # Sheet 1: Aggregate
    ws1 = wb.active
    ws1.title = "標準彙總"

    # Title
    ws1.merge_cells("A1:C1")
    title_cell = ws1.cell(row=1, column=1)
    title_cell.value = "AI-QMS 法規標準引用清單"
    title_cell.font = Font(name="Microsoft JhengHei", size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    # Metadata
    ws1.merge_cells("A2:C2")
    meta_cell = ws1.cell(row=2, column=1)
    meta_cell.value = (
        f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"標準總數: {len(aggregate)} 項 | 涵蓋文件: {len(by_doc)} 份"
    )
    meta_cell.font = Font(
        name="Microsoft JhengHei", size=9, italic=True, color="808080"
    )

    # Headers
    headers = ["標準", "引用文件數", "引用文件"]
    for col, header in enumerate(headers, 1):
        cell = ws1.cell(row=4, column=col)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    # Data
    for row_idx, entry in enumerate(aggregate, 5):
        values = [
            entry["standard"],
            len(entry["referenced_by"]),
            ", ".join(entry["referenced_by"]),
        ]
        for col, val in enumerate(values, 1):
            cell = ws1.cell(row=row_idx, column=col)
            cell.value = val
            cell.font = CELL_FONT
            cell.border = THIN_BORDER

    ws1.column_dimensions["A"].width = 30
    ws1.column_dimensions["B"].width = 15
    ws1.column_dimensions["C"].width = 50
    ws1.freeze_panes = "A5"

    # Sheet 2: Per-document detail
    ws2 = wb.create_sheet("文件引用明細")

    # Title
    ws2.merge_cells("A1:E1")
    title_cell2 = ws2.cell(row=1, column=1)
    title_cell2.value = "各文件引用法規標準明細"
    title_cell2.font = Font(name="Microsoft JhengHei", size=14, bold=True)
    title_cell2.alignment = Alignment(horizontal="center")

    # Headers
    headers2 = ["文件編號", "文件名稱", "類型", "版本", "引用標準"]
    for col, header in enumerate(headers2, 1):
        cell = ws2.cell(row=3, column=col)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    for row_idx, d in enumerate(by_doc, 4):
        values = [
            d["doc_id"],
            d["title"],
            d["doc_type"],
            f"v{d['current_version']}",
            ", ".join(d["standards"]),
        ]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=row_idx, column=col)
            cell.value = val
            cell.font = CELL_FONT
            cell.border = THIN_BORDER

    ws2.column_dimensions["A"].width = 15
    ws2.column_dimensions["B"].width = 35
    ws2.column_dimensions["C"].width = 10
    ws2.column_dimensions["D"].width = 10
    ws2.column_dimensions["E"].width = 60
    ws2.freeze_panes = "A4"

    # Footer note
    note_row = len(by_doc) + 5
    ws2.merge_cells(f"A{note_row}:E{note_row}")
    note_cell = ws2.cell(row=note_row, column=1)
    note_cell.value = "本報告由 AI-QMS 品質管理系統自動產生。法規標準資訊擷取自文件 OCR 內容，僅供參考。"
    note_cell.font = Font(
        name="Microsoft JhengHei", size=8, italic=True, color="808080"
    )

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"regulatory_standards_{timestamp}.xlsx"
    filepath = EXPORT_DIR / filename
    wb.save(str(filepath))
    return str(filepath)


# ============================================================
# 引用清單 (Document Reference List after version update)
# ============================================================


def format_reference_table_markdown(doc_id: str, ref_docs: List[dict]) -> str:
    """Format document reference list as Markdown for chat display."""
    if not ref_docs:
        return f"📋 沒有其他文件引用 {doc_id}。"

    lines = [
        f"📋 **文件引用清單** — {doc_id} 被以下 {len(ref_docs)} 份文件引用\n",
        "| 文件編號 | 文件名稱 | 類型 | 版本 | 引用方式 |",
        "|---------|---------|------|------|---------|",
    ]

    for r in ref_docs:
        ref_type = "明確引用" if r.get("reference_type") == "explicit" else "內容引用"
        lines.append(
            f"| {r['doc_id']} | {r['title'][:30]} | {r['doc_type']} | v{r['current_version']} | {ref_type} |"
        )

    lines.append(f"\n💡 輸入「下載引用清單 word」或「下載引用清單 excel」可匯出檔案")
    return "\n".join(lines)


def export_reference_to_word(doc_id: str, ref_docs: List[dict]) -> str:
    """
    Export document reference list to Word (.docx).

    Returns:
        Path to the generated .docx file.
    """
    doc = Document()

    # Title
    title = doc.add_heading(f"AI-QMS 文件引用清單 — {doc_id}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = meta.add_run(f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(128, 128, 128)

    meta2 = doc.add_paragraph()
    meta2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run2 = meta2.add_run(f"引用 {doc_id} 的文件共 {len(ref_docs)} 份")
    run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    if not ref_docs:
        doc.add_paragraph(f"沒有其他文件引用 {doc_id}。")
    else:
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers = ["#", "文件編號", "文件名稱", "版本", "引用方式"]
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(9)

        for idx, r in enumerate(ref_docs, 1):
            row = table.add_row()
            ref_type = (
                "明確引用" if r.get("reference_type") == "explicit" else "內容引用"
            )
            values = [
                str(idx),
                r["doc_id"],
                r["title"],
                f"v{r['current_version']}",
                ref_type,
            ]
            for i, val in enumerate(values):
                cell = row.cells[i]
                cell.text = val
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)

        widths = [Cm(1), Cm(3), Cm(6), Cm(2), Cm(2.5)]
        for row in table.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = width

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    run = footer.add_run(
        f"本報告由 AI-QMS 品質管理系統自動產生。列出所有引用 {doc_id} 的文件，建議確認是否需要同步更新。"
    )
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(128, 128, 128)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reference_list_{doc_id}_{timestamp}.docx"
    filepath = EXPORT_DIR / filename
    doc.save(str(filepath))
    return str(filepath)


def export_reference_to_excel(doc_id: str, ref_docs: List[dict]) -> str:
    """
    Export document reference list to Excel (.xlsx).

    Returns:
        Path to the generated .xlsx file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "引用清單"

    # Title
    ws.merge_cells("A1:E1")
    title_cell = ws.cell(row=1, column=1)
    title_cell.value = f"AI-QMS 文件引用清單 — {doc_id}"
    title_cell.font = Font(name="Microsoft JhengHei", size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    # Metadata
    ws.merge_cells("A2:E2")
    meta_cell = ws.cell(row=2, column=1)
    meta_cell.value = (
        f"匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"引用 {doc_id} 的文件共 {len(ref_docs)} 份"
    )
    meta_cell.font = Font(
        name="Microsoft JhengHei", size=9, italic=True, color="808080"
    )

    # Headers
    headers = ["#", "文件編號", "文件名稱", "版本", "引用方式"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER

    # Data
    for row_idx, r in enumerate(ref_docs, 5):
        ref_type = "明確引用" if r.get("reference_type") == "explicit" else "內容引用"
        values = [
            row_idx - 4,
            r["doc_id"],
            r["title"],
            f"v{r['current_version']}",
            ref_type,
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.value = val
            cell.font = CELL_FONT
            cell.border = THIN_BORDER

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 12
    ws.freeze_panes = "A5"

    # Footer
    note_row = len(ref_docs) + 6
    ws.merge_cells(f"A{note_row}:E{note_row}")
    note_cell = ws.cell(row=note_row, column=1)
    note_cell.value = f"本報告由 AI-QMS 品質管理系統自動產生。列出所有引用 {doc_id} 的文件，建議確認是否需要同步更新。"
    note_cell.font = Font(
        name="Microsoft JhengHei", size=8, italic=True, color="808080"
    )

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reference_list_{doc_id}_{timestamp}.xlsx"
    filepath = EXPORT_DIR / filename
    wb.save(str(filepath))
    return str(filepath)
