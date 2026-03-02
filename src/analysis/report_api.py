"""
AI-QMS — Report API (Phase D)
==============================

REST API endpoints for the interactive compliance report page.
Mounted on the Chainlit FastAPI app at /api/report/...

Endpoints:
  GET  /api/report/runs                        — List all pipeline runs
  GET  /api/report/{run_id}                    — Get full report data
  GET  /api/report/{run_id}/summary            — Get summary statistics
  GET  /api/report/{run_id}/rows               — Get rows with filters
  GET  /api/report/{run_id}/row/{row_id}       — Get single row detail
  POST /api/report/{run_id}/row/{row_id}/override  — RA override verdict
  POST /api/report/{run_id}/row/{row_id}/note      — Add clause note
  POST /api/report/{run_id}/row/{row_id}/restore   — Restore LLM original
  POST /api/report/{run_id}/row/{row_id}/rerun     — Reset row for re-run
  GET  /api/report/{run_id}/row/{row_id}/history   — Get version history
  GET  /api/report/{run_id}/export/{format}        — Export Word/Excel
  GET  /api/report/crossref/regulations            — List available regulations
  GET  /api/report/crossref/table                  — Cross-reference table
  GET  /api/report/crossref/questions              — Cross-exam questions
  GET  /api/report/standards/list                  — List supplemental standards
  POST /api/report/standards/applicable            — Determine applicable standards
  POST /api/report/standards/adjust                — Adjust standard-to-clause mapping
  GET  /api/report/{run_id}/stream                 — SSE cross-examination events
  POST /api/report/{run_id}/inject                 — Human message injection
  POST /api/report/{run_id}/pause                  — Pause cross-examination
  POST /api/report/{run_id}/resume                 — Resume cross-examination
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse

from src.analysis.state import Phase
from src.analysis.comparison_table import ComparisonTable
from src.analysis.risk_matrix import (
    RISK_LEVEL_DISPLAY,
    VERDICT_DISPLAY,
    Verdict,
    RiskLevel,
    assess_risk,
)

logger = logging.getLogger(__name__)

__all__ = ["report_router", "REPORT_STATIC_DIR"]

# Static files directory for report HTML/JS/CSS
REPORT_STATIC_DIR = Path(__file__).parent.parent.parent / "report_ui"

# Pipeline state storage directory
_PIPELINE_DIR = Path("data/analysis_pipeline")

# FastAPI router
report_router = APIRouter(prefix="/api/report", tags=["report"])


# ============================================================
# Helpers
# ============================================================


def _load_table(run_id: str) -> ComparisonTable:
    """Load a comparison table by run_id. Raises 404 if not found."""
    filepath = _PIPELINE_DIR / f"{run_id}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    try:
        return ComparisonTable.load(run_id, _PIPELINE_DIR)
    except Exception as e:
        logger.error(f"Failed to load pipeline state {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load run: {e}")


def _save_table(table: ComparisonTable) -> None:
    """Save the comparison table back to disk."""
    try:
        table.save()
    except Exception as e:
        logger.error(f"Failed to save pipeline state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save changes: {e}")


def _row_to_api(row_dict: dict) -> dict:
    """Enrich a flat row dict with display labels for the frontend."""
    verdict = row_dict.get("verdict")
    risk = row_dict.get("risk_level")

    v_disp = VERDICT_DISPLAY.get(verdict or "", {})
    r_disp = RISK_LEVEL_DISPLAY.get(risk or "", {})

    row_dict["verdict_icon"] = v_disp.get("icon", "")
    row_dict["verdict_label_zh"] = v_disp.get("label_zh", verdict or "")
    row_dict["verdict_label_en"] = v_disp.get("label_en", verdict or "")
    row_dict["risk_icon"] = r_disp.get("icon", "")
    row_dict["risk_label_zh"] = r_disp.get("label_zh", risk or "")
    row_dict["risk_label_en"] = r_disp.get("label_en", risk or "")
    row_dict["risk_action_zh"] = r_disp.get("action_zh", "")

    return row_dict


# ============================================================
# Report page serving
# ============================================================


@report_router.get("/page/{run_id}", response_class=HTMLResponse)
async def serve_report_page(run_id: str):
    """Serve the report HTML page for a specific run."""
    html_path = REPORT_STATIC_DIR / "report.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Report page not found")

    # Verify run exists
    filepath = _PIPELINE_DIR / f"{run_id}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # Read and inject run_id into the HTML template
    html_content = html_path.read_text(encoding="utf-8")
    html_content = html_content.replace("{{RUN_ID}}", run_id)
    return HTMLResponse(content=html_content)


@report_router.get("/static/{filename}")
async def serve_report_static(filename: str):
    """Serve static files (JS, CSS) for the report page."""
    allowed_extensions = {".js", ".css", ".svg", ".png", ".ico"}
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=403, detail="File type not allowed")

    filepath = REPORT_STATIC_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    content_types = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }
    return FileResponse(
        filepath, media_type=content_types.get(ext, "application/octet-stream")
    )


# ============================================================
# API Endpoints — Read
# ============================================================


@report_router.get("/runs")
async def list_runs():
    """List all saved pipeline runs."""
    runs = ComparisonTable.list_runs(_PIPELINE_DIR)
    return JSONResponse(content={"runs": runs})


@report_router.get("/{run_id}")
async def get_report(run_id: str):
    """Get full report data for a specific run."""
    table = _load_table(run_id)
    state = table.state

    # Build enriched row list
    flat_rows = table.to_flat_rows()
    enriched = [_row_to_api(r) for r in flat_rows]

    # Summary
    summary = table.summary()
    progress = state.progress_summary()

    # Data quality info
    dq = state.data_quality_summary

    # Source check info
    sc = state.source_check_summary

    # LLM budget
    budget = state.get_budget().to_dict()

    return JSONResponse(
        content={
            "run_id": state.run_id,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "completed_at": state.completed_at,
            "status": state.status,
            "mode": state.mode,
            "standard": state.standard,
            "current_phase": state.current_phase,
            "rows": enriched,
            "summary": summary,
            "progress": progress,
            "data_quality": dq,
            "source_check": sc,
            "llm_budget": budget,
            "verdict_options": [
                {"value": v, **VERDICT_DISPLAY.get(v, {})} for v in Verdict.ALL
            ],
            "risk_options": [
                {"value": r, **RISK_LEVEL_DISPLAY.get(r, {})} for r in RiskLevel.ALL
            ],
        }
    )


@report_router.get("/{run_id}/summary")
async def get_summary(run_id: str):
    """Get summary statistics only."""
    table = _load_table(run_id)
    summary = table.summary()
    progress = table.state.progress_summary()
    budget = table.state.get_budget().to_dict()
    return JSONResponse(
        content={
            "summary": summary,
            "progress": progress,
            "llm_budget": budget,
        }
    )


@report_router.get("/{run_id}/rows")
async def get_rows(
    run_id: str,
    doc_id: Optional[str] = Query(None, description="Filter by document ID"),
    clause_id: Optional[str] = Query(None, description="Filter by clause ID"),
    verdict: Optional[str] = Query(None, description="Filter by verdict"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    flagged: Optional[bool] = Query(None, description="Filter flagged rows only"),
    search: Optional[str] = Query(None, description="Search in clause/doc titles"),
):
    """Get rows with optional filters."""
    table = _load_table(run_id)
    flat_rows = table.to_flat_rows()

    # Apply filters
    if doc_id:
        flat_rows = [r for r in flat_rows if r["doc_id"] == doc_id]
    if clause_id:
        flat_rows = [r for r in flat_rows if r["clause_id"] == clause_id]
    if verdict:
        flat_rows = [r for r in flat_rows if r["verdict"] == verdict]
    if risk_level:
        flat_rows = [r for r in flat_rows if r.get("risk_level") == risk_level]
    if flagged is True:
        flat_rows = [r for r in flat_rows if r.get("flagged_for_ra")]
    if search:
        search_lower = search.lower()
        flat_rows = [
            r
            for r in flat_rows
            if search_lower
            in (r.get("clause_title", "") + r.get("doc_title", "")).lower()
            or search_lower in r.get("clause_id", "").lower()
            or search_lower in r.get("doc_id", "").lower()
        ]

    enriched = [_row_to_api(r) for r in flat_rows]

    return JSONResponse(
        content={
            "total": len(enriched),
            "rows": enriched,
        }
    )


@report_router.get("/{run_id}/row/{row_id}")
async def get_row_detail(run_id: str, row_id: str):
    """Get detailed data for a single row, including all phase results."""
    table = _load_table(run_id)
    row = table.state.get_row(row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    row_dict = row.to_dict()
    row_dict = _row_to_api(row_dict)

    return JSONResponse(content={"row": row_dict})


@report_router.get("/{run_id}/row/{row_id}/history")
async def get_row_history(run_id: str, row_id: str):
    """Get version history for a specific row."""
    table = _load_table(run_id)
    row = table.state.get_row(row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    return JSONResponse(
        content={
            "row_id": row_id,
            "version_history": row.version_history,
            "ra_override": row.ra_override,
            "ra_notes": row.ra_notes,
        }
    )


# ============================================================
# API Endpoints — Write (RA Modifications)
# ============================================================


@report_router.post("/{run_id}/row/{row_id}/override")
async def override_verdict(run_id: str, row_id: str, body: dict):
    """RA overrides a row's verdict.

    Body:
        {"verdict": "full_compliance", "reason": "已確認文件內容符合要求"}
    """
    new_verdict = body.get("verdict")
    reason = body.get("reason", "")
    user_id = body.get("user_id", "ra_user")

    if not new_verdict:
        raise HTTPException(status_code=400, detail="Missing 'verdict' field")
    if new_verdict not in Verdict.ALL:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verdict: {new_verdict}. Must be one of {Verdict.ALL}",
        )
    if not reason:
        raise HTTPException(status_code=400, detail="Missing 'reason' field")

    table = _load_table(run_id)
    updated = table.override_verdict(row_id, new_verdict, reason, user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    # Auto-recalculate risk based on new verdict
    # Verdict → gap_severity reverse mapping, then risk matrix lookup
    if updated.audit_impact and new_verdict:
        new_risk = _verdict_to_risk(new_verdict, updated.audit_impact)
        if new_risk:
            updated.risk_level = new_risk
            table.state.update_row(updated)

    _save_table(table)

    row_dict = _row_to_api(updated.to_dict())
    return JSONResponse(content={"success": True, "row": row_dict})


@report_router.post("/{run_id}/row/{row_id}/note")
async def add_note(run_id: str, row_id: str, body: dict):
    """Add a permanent note to a clause.

    Body:
        {"note": "此條款在本公司不適用，因為..."}
    """
    note = body.get("note", "")
    user_id = body.get("user_id", "ra_user")

    if not note:
        raise HTTPException(status_code=400, detail="Missing 'note' field")

    table = _load_table(run_id)
    updated = table.add_clause_note(row_id, note, user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    _save_table(table)

    row_dict = _row_to_api(updated.to_dict())
    return JSONResponse(content={"success": True, "row": row_dict})


@report_router.post("/{run_id}/row/{row_id}/restore")
async def restore_original(run_id: str, row_id: str):
    """Restore the LLM's original verdict (undo RA override)."""
    table = _load_table(run_id)
    updated = table.restore_llm_original(row_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    _save_table(table)

    row_dict = _row_to_api(updated.to_dict())
    return JSONResponse(content={"success": True, "row": row_dict})


@report_router.post("/{run_id}/row/{row_id}/rerun")
async def reset_for_rerun(run_id: str, row_id: str, body: dict = None):
    """Reset a row to re-run from Phase 1 (Gap Scan).

    Body (optional):
        {"from_phase": "phase_1"}  (default: phase_1)
    """
    from_phase_str = (body or {}).get("from_phase", Phase.GAP_SCAN.value)
    try:
        from_phase = Phase(from_phase_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase: {from_phase_str}",
        )

    table = _load_table(run_id)
    updated = table.reset_row_for_rerun(row_id, from_phase)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    _save_table(table)

    row_dict = _row_to_api(updated.to_dict())
    return JSONResponse(
        content={
            "success": True,
            "row": row_dict,
            "message": f"Row reset to {from_phase.display_name}. "
            f"Re-run the pipeline from Chainlit to execute the pending phases.",
        }
    )


# ============================================================
# API Endpoints — Export
# ============================================================


@report_router.get("/{run_id}/export/{fmt}")
async def export_report(run_id: str, fmt: str):
    """Export the report as Word or Excel.

    fmt: "word" or "excel"
    """
    if fmt not in ("word", "excel"):
        raise HTTPException(status_code=400, detail="Format must be 'word' or 'excel'")

    table = _load_table(run_id)
    flat_rows = table.to_flat_rows()
    summary = table.summary()

    # Use existing export utilities
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        if fmt == "word":
            from docx import Document
            from docx.shared import Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            filepath = export_dir / f"compliance_report_{run_id}.docx"
            assessment = _build_export_assessment(flat_rows, summary)

            doc = Document()
            title = doc.add_heading("AI-QMS 合規性分析報告", level=1)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

            from datetime import datetime
            meta = doc.add_paragraph()
            meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = meta.add_run(f"分析 ID: {run_id}  |  匯出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(128, 128, 128)

            # Summary section
            doc.add_heading("摘要", level=2)
            doc.add_paragraph(assessment)

            # Detail table
            doc.add_heading("詳細分析結果", level=2)
            if flat_rows:
                headers = ["條款", "文件", "稽核影響", "判定", "風險", "差距", "RA 標記"]
                tbl = doc.add_table(rows=1 + len(flat_rows), cols=len(headers))
                tbl.style = "Table Grid"
                for i, h in enumerate(headers):
                    tbl.rows[0].cells[i].text = h
                for ri, row in enumerate(flat_rows, 1):
                    tbl.rows[ri].cells[0].text = f"{row.get('clause_id', '')} {row.get('clause_title', '')}"
                    tbl.rows[ri].cells[1].text = f"{row.get('doc_id', '')}"
                    tbl.rows[ri].cells[2].text = row.get('audit_impact', '')
                    tbl.rows[ri].cells[3].text = f"{row.get('verdict_icon', '')} {row.get('verdict_label', '')}"
                    tbl.rows[ri].cells[4].text = f"{row.get('risk_icon', '')} {row.get('risk_label', '')}"
                    tbl.rows[ri].cells[5].text = row.get('gap_severity', '') or ''
                    tbl.rows[ri].cells[6].text = '⚠️' if row.get('flagged_for_ra') else ''

            doc.save(str(filepath))

        else:  # excel
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill

            filepath = export_dir / f"compliance_report_{run_id}.xlsx"
            assessment = _build_export_assessment(flat_rows, summary)

            wb = Workbook()
            ws = wb.active
            ws.title = "合規分析"

            # Headers
            headers = ["條款 ID", "條款名稱", "文件 ID", "文件標題", "稽核影響",
                       "稽核問題", "判定", "風險等級", "差距嚴重度",
                       "證據 (找到/總計)", "RA 標記", "RA 覆寫", "RA 備註"]
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=10)
            for ci, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=ci, value=h)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")

            for ri, row in enumerate(flat_rows, 2):
                ws.cell(row=ri, column=1, value=row.get('clause_id', ''))
                ws.cell(row=ri, column=2, value=row.get('clause_title', ''))
                ws.cell(row=ri, column=3, value=row.get('doc_id', ''))
                ws.cell(row=ri, column=4, value=row.get('doc_title', ''))
                ws.cell(row=ri, column=5, value=row.get('audit_impact', ''))
                ws.cell(row=ri, column=6, value=row.get('audit_question', ''))
                ws.cell(row=ri, column=7, value=f"{row.get('verdict_icon', '')} {row.get('verdict_label', '')}")
                ws.cell(row=ri, column=8, value=f"{row.get('risk_icon', '')} {row.get('risk_label', '')}")
                ws.cell(row=ri, column=9, value=row.get('gap_severity', '') or '')
                ws.cell(row=ri, column=10, value=f"{row.get('evidence_found', 0)}/{row.get('evidence_total', 0)}")
                ws.cell(row=ri, column=11, value='Y' if row.get('flagged_for_ra') else '')
                override = row.get('ra_override')
                ws.cell(row=ri, column=12, value=override.get('reason', '') if isinstance(override, dict) else '')
                ws.cell(row=ri, column=13, value=row.get('ra_notes', '') or '')

            # Auto-width
            for col in ws.columns:
                max_len = max((len(str(c.value or '')) for c in col), default=8)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

            wb.save(str(filepath))
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Export utilities not available. Check regulatory_export module.",
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    if not filepath.exists():
        raise HTTPException(status_code=500, detail="Export file was not created")

    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if fmt == "word"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(
        filepath,
        media_type=content_type,
        filename=filepath.name,
    )


# ============================================================
# Metadata endpoints
# ============================================================


@report_router.get("/{run_id}/filters")
async def get_filter_options(run_id: str):
    """Get available filter options for the report (documents, clauses, verdicts, risks)."""
    table = _load_table(run_id)
    flat_rows = table.to_flat_rows()

    # Unique documents
    docs = {}
    clauses = {}
    verdicts_seen = set()
    risks_seen = set()

    for r in flat_rows:
        did = r.get("doc_id", "")
        if did and did not in docs:
            docs[did] = r.get("doc_title", did)

        cid = r.get("clause_id", "")
        if cid and cid not in clauses:
            clauses[cid] = r.get("clause_title", cid)

        v = r.get("verdict")
        if v:
            verdicts_seen.add(v)

        rl = r.get("risk_level")
        if rl:
            risks_seen.add(rl)

    return JSONResponse(
        content={
            "documents": [{"id": k, "title": v} for k, v in sorted(docs.items())],
            "clauses": [
                {"id": k, "title": v}
                for k, v in sorted(
                    clauses.items(),
                    key=lambda x: [int(n) for n in x[0].split(".") if n.isdigit()],
                )
            ],
            "verdicts": [
                {"value": v, **VERDICT_DISPLAY.get(v, {})}
                for v in Verdict.ALL
                if v in verdicts_seen
            ],
            "risk_levels": [
                {"value": r, **RISK_LEVEL_DISPLAY.get(r, {})}
                for r in RiskLevel.ALL
                if r in risks_seen
            ],
        }
    )


# ============================================================
# Internal helpers
# ============================================================


def _verdict_to_risk(verdict: str, audit_impact: str) -> Optional[str]:
    """Reverse-map verdict to risk level using the risk matrix.

    When RA overrides verdict, we recalculate risk deterministically.
    """
    # Verdict → gap_severity mapping (simplified)
    verdict_gap_map = {
        Verdict.FULL_COMPLIANCE: "none",
        Verdict.PARTIAL_COMPLIANCE: "incomplete",
        Verdict.NON_COMPLIANCE: "missing",
        Verdict.INSUFFICIENT_DATA: "missing",
    }

    gap_severity = verdict_gap_map.get(verdict)
    if gap_severity is None:
        return None

    result = assess_risk(audit_impact, gap_severity)
    return result  # assess_risk returns risk level string directly


def _build_export_assessment(flat_rows: list[dict], summary: dict) -> str:
    """Build a markdown assessment text from flat rows for Word/Excel export."""
    lines = [
        "# 合規性分析報告",
        "",
        f"**分析項目數**: {summary.get('total_rows', 0)}",
        f"**文件數**: {summary.get('documents_analyzed', 0)}",
        f"**需 RA 審查**: {summary.get('flagged_for_ra', 0)} 項",
        "",
        "## 判定結果分布",
        "",
    ]

    vd = summary.get("verdict_distribution", {})
    for v, count in vd.items():
        disp = VERDICT_DISPLAY.get(v, {})
        lines.append(f"- {disp.get('icon', '')} {disp.get('label_zh', v)}: {count} 項")

    lines.append("")
    lines.append("## 風險等級分布")
    lines.append("")

    rd = summary.get("risk_distribution", {})
    for r, count in rd.items():
        disp = RISK_LEVEL_DISPLAY.get(r, {})
        lines.append(f"- {disp.get('icon', '')} {disp.get('label_zh', r)}: {count} 項")

    lines.append("")
    lines.append("## 詳細結果")
    lines.append("")

    for row in flat_rows:
        lines.append(f"### {row.get('clause_id', '')} — {row.get('clause_title', '')}")
        lines.append(
            f"- **文件**: {row.get('doc_title', '')} ({row.get('doc_id', '')})"
        )
        lines.append(
            f"- **判定**: {row.get('verdict_icon', '')} {row.get('verdict_label', '')}"
        )
        lines.append(
            f"- **風險**: {row.get('risk_icon', '')} {row.get('risk_label', '')}"
        )
        lines.append(f"- **稽核影響**: {row.get('audit_impact', '')}")
        ev_found = row.get("evidence_found", 0)
        ev_total = row.get("evidence_total", 0)
        lines.append(f"- **證據**: {ev_found}/{ev_total} 項找到")

        if row.get("remediation"):
            lines.append(f"- **改善建議**: {row['remediation']}")

        if row.get("ra_override"):
            override = row["ra_override"]
            lines.append(
                f"- **RA 覆寫**: {override.get('verdict', '')} — {override.get('reason', '')}"
            )

        if row.get("ra_notes"):
            lines.append(f"- **RA 備註**: {row['ra_notes']}")

        lines.append("")

    return "\n".join(lines)


# ============================================================
# Cross-Reference Comparison API
# ============================================================


def _get_cross_ref_modules():
    """Lazy import cross-reference modules to avoid circular imports."""
    from src.analysis.compliance_rules import (
        ISO_13485_CHECKLIST,
        get_all_regulations,
        get_regulation,
        get_overlap_analysis,
        generate_cross_exam_questions,
        MappingStatus,
    )
    return {
        "ISO_13485_CHECKLIST": ISO_13485_CHECKLIST,
        "get_all_regulations": get_all_regulations,
        "get_regulation": get_regulation,
        "get_overlap_analysis": get_overlap_analysis,
        "generate_cross_exam_questions": generate_cross_exam_questions,
        "MappingStatus": MappingStatus,
    }


@report_router.get("/crossref/regulations")
async def list_regulations():
    """List all available regulations (predefined + crawled) for country selector."""
    mods = _get_cross_ref_modules()
    all_regs = mods["get_all_regulations"]()

    regulations = []
    for reg_id, profile in all_regs.items():
        iso_mapped_count = len(profile.iso_mapped)
        unique_count = len(profile.unique_requirements)

        # Count statuses
        status_counts = defaultdict(int)
        for cm in profile.iso_mapped.values():
            status_counts[cm.status.value] += 1

        regulations.append({
            "regulation_id": reg_id,
            "name_en": profile.name_en,
            "name_zh": profile.name_zh,
            "country": profile.country,
            "country_name_en": profile.country_name_en,
            "country_name_zh": profile.country_name_zh,
            "source": profile.source,
            "source_url": profile.source_url,
            "last_updated": profile.last_updated,
            "effective_date": profile.effective_date,
            "iso_mapped_count": iso_mapped_count,
            "unique_requirements_count": unique_count,
            "status_counts": dict(status_counts),
        })

    return JSONResponse(content={"regulations": regulations})


@report_router.get("/crossref/table")
async def get_crossref_table(
    regulations: str = Query(..., description="Comma-separated regulation IDs, e.g. QMSR,EU_MDR,TFDA"),
):
    """Get the full cross-reference comparison table.

    Returns ISO 13485 clauses as rows, with each selected regulation's
    mapping status, rationale, method, and confidence.
    Also returns unique requirements (delta items) per regulation.
    """
    mods = _get_cross_ref_modules()
    reg_ids = [r.strip() for r in regulations.split(",") if r.strip()]

    if not reg_ids:
        raise HTTPException(status_code=400, detail="No regulations specified")

    # Validate regulation IDs
    all_regs = mods["get_all_regulations"]()
    for rid in reg_ids:
        if rid not in all_regs:
            raise HTTPException(status_code=404, detail=f"Regulation '{rid}' not found")

    # Build cross-reference rows from ISO 13485 checklist
    checklist = mods["ISO_13485_CHECKLIST"]
    rows = []

    for clause in checklist:
        clause_id = clause["clause_id"]
        row = {
            "clause_id": clause_id,
            "clause_title": clause.get("title", ""),
            "audit_impact": clause.get("audit_impact", ""),
            "regulations": {},
        }

        for rid in reg_ids:
            analysis = mods["get_overlap_analysis"](rid, clause_id)
            profile = all_regs[rid]

            reg_data = {
                "status": analysis.get("status", "na"),
                "is_delta": analysis.get("is_delta", False),
                "regulation_ref": analysis.get("regulation_ref", ""),
                "rationale_en": analysis.get("rationale_en", ""),
                "rationale_zh": analysis.get("rationale_zh", ""),
                "method": analysis.get("method", ""),
                "confidence": analysis.get("confidence", 0.0),
                "notes": analysis.get("notes", ""),
                "delta_items": analysis.get("delta_items", []),
            }
            row["regulations"][rid] = reg_data

        rows.append(row)

    # Collect unique requirements (delta) per regulation
    unique_reqs = {}
    for rid in reg_ids:
        profile = all_regs[rid]
        reqs = []
        for req in profile.unique_requirements:
            reqs.append({
                "req_id": req.req_id,
                "regulation_ref": req.regulation_ref,
                "title_en": req.title_en,
                "title_zh": req.title_zh,
                "requirement_en": req.requirement_en,
                "requirement_zh": req.requirement_zh,
                "related_iso_clauses": req.related_iso_clauses,
                "audit_impact": req.audit_impact,
                "audit_question_en": req.audit_question_en,
                "audit_question_zh": req.audit_question_zh,
                "expected_evidence": req.expected_evidence,
                "rationale_en": req.rationale_en,
                "rationale_zh": req.rationale_zh,
                "method": req.method.value if hasattr(req.method, 'value') else str(req.method),
                "confidence": req.confidence,
            })
        unique_reqs[rid] = reqs

    # Regulation metadata for the header
    reg_meta = {}
    for rid in reg_ids:
        p = all_regs[rid]
        reg_meta[rid] = {
            "name_en": p.name_en,
            "name_zh": p.name_zh,
            "country": p.country,
            "country_name_zh": p.country_name_zh,
            "source": p.source,
            "effective_date": p.effective_date,
        }

    return JSONResponse(content={
        "regulation_ids": reg_ids,
        "regulation_meta": reg_meta,
        "iso_clause_count": len(checklist),
        "rows": rows,
        "unique_requirements": unique_reqs,
    })


@report_router.get("/crossref/questions")
async def get_crossref_questions(
    doc_id: str = Query(..., description="Document ID, e.g. QP-852"),
    doc_title: str = Query("", description="Document title"),
    baseline_clause: str = Query("", description="Primary ISO 13485 clause, e.g. 8.5.2"),
    regulations: str = Query(..., description="Comma-separated regulation IDs"),
    doc_content_summary: str = Query("", description="Brief document content summary"),
):
    """Generate cross-examination questions for a specific document.

    Returns prioritized questions: delta (highest) > exceeds > overlap.
    """
    mods = _get_cross_ref_modules()
    reg_ids = [r.strip() for r in regulations.split(",") if r.strip()]

    if not reg_ids:
        raise HTTPException(status_code=400, detail="No regulations specified")

    questions = mods["generate_cross_exam_questions"](
        doc_id=doc_id,
        doc_title=doc_title,
        baseline_clause=baseline_clause,
        selected_regulations=reg_ids,
        doc_content_summary=doc_content_summary,
    )

    return JSONResponse(content={
        "doc_id": doc_id,
        "baseline_clause": baseline_clause,
        "selected_regulations": reg_ids,
        "total_questions": len(questions),
        "questions": questions,
    })


# ============================================================
# Supplemental Standards API Endpoints
# ============================================================


def _get_standards_modules():
    """Lazy import supplemental standards to avoid circular imports."""
    from src.analysis.compliance_rules import (
        get_all_standards,
        get_standard,
        get_applicable_standards,
        adjust_standard_clause_mapping,
        ProductProfile,
        StandardCategory,
    )
    return {
        "get_all_standards": get_all_standards,
        "get_standard": get_standard,
        "get_applicable_standards": get_applicable_standards,
        "adjust_standard_clause_mapping": adjust_standard_clause_mapping,
        "ProductProfile": ProductProfile,
        "StandardCategory": StandardCategory,
    }


@report_router.get("/standards/list")
async def list_supplemental_standards():
    """List all available supplemental standards.

    Returns all predefined standards with their categories,
    detection keywords, ISO 13485 clause links, and regulatory references.
    """
    mods = _get_standards_modules()
    all_stds = mods["get_all_standards"]()

    standards = []
    for std_id, std in all_stds.items():
        standards.append({
            "standard_id": std.standard_id,
            "name_en": std.name_en,
            "name_zh": std.name_zh,
            "category": std.category.value,
            "version": std.version,
            "is_universal": std.is_universal,
            "primary_iso_clauses": std.primary_iso_clauses,
            "clause_links": [
                {
                    "standard_clause": cl.standard_clause,
                    "iso_13485_clause": cl.iso_13485_clause,
                    "relationship": cl.relationship,
                    "description_en": cl.description_en,
                    "description_zh": cl.description_zh,
                }
                for cl in std.clause_links
            ],
            "regulatory_references": std.regulatory_references,
            "audit_questions": std.audit_questions,
            "detection_keywords_en": std.detection_keywords_en,
            "detection_keywords_zh": std.detection_keywords_zh,
        })

    return JSONResponse(content={"standards": standards})


@report_router.post("/standards/applicable")
async def get_applicable_standards_endpoint(request: Request):
    """Determine which supplemental standards apply based on product profile.

    Accepts a JSON body with product characteristics:
    {
        "has_software": true/false,
        "has_electrical": true/false,
        "is_implantable": true/false,
        "is_sterile": true/false,
        "sterilization_method": "eo"/"radiation"/"steam"/"",
        "has_biological_contact": true/false,
        "user_confirmed_standards": ["ISO_14971", ...],
        "user_rejected_standards": [...],
        "detected_standard_refs": ["ISO 14971", "IEC 62304", ...],
        "uploaded_standard_files": ["ISO_11135.pdf", ...]
    }

    Returns applicable standards list with ISO 13485 clause mappings.
    """
    mods = _get_standards_modules()
    body = await request.json()

    # Build ProductProfile from request body
    ProfileCls = mods["ProductProfile"]
    profile = ProfileCls(
        has_software=(
            body.get("has_software", False),
            body.get("has_software_confidence", 0.5),
            body.get("has_software_source", "user_manual"),
        ),
        has_electrical=(
            body.get("has_electrical", False),
            body.get("has_electrical_confidence", 0.5),
            body.get("has_electrical_source", "user_manual"),
        ),
        is_implantable=(
            body.get("is_implantable", False),
            body.get("is_implantable_confidence", 0.5),
            body.get("is_implantable_source", "user_manual"),
        ),
        is_sterile=(
            body.get("is_sterile", False),
            body.get("is_sterile_confidence", 0.5),
            body.get("is_sterile_source", "user_manual"),
        ),
        sterilization_method=body.get("sterilization_method", ""),
        has_biological_contact=(
            body.get("has_biological_contact", False),
            body.get("has_biological_contact_confidence", 0.5),
            body.get("has_biological_contact_source", "user_manual"),
        ),
        is_ivd=(
            body.get("is_ivd", False),
            body.get("is_ivd_confidence", 0.5),
            body.get("is_ivd_source", "user_manual"),
        ),
        has_clinical_investigation=(
            body.get("has_clinical_investigation", False),
            body.get("has_clinical_investigation_confidence", 0.5),
            body.get("has_clinical_investigation_source", "user_manual"),
        ),
        user_confirmed_standards=body.get("user_confirmed_standards", []),
        user_rejected_standards=body.get("user_rejected_standards", []),
        detected_standard_refs=body.get("detected_standard_refs", []),
        uploaded_standard_files=body.get("uploaded_standard_files", []),
    )

    applicable = mods["get_applicable_standards"](profile)

    results = []
    for std in applicable:
        results.append({
            "standard_id": std.standard_id,
            "name_en": std.name_en,
            "name_zh": std.name_zh,
            "category": std.category.value,
            "is_universal": std.is_universal,
            "primary_iso_clauses": std.primary_iso_clauses,
            "clause_links": [
                {
                    "standard_clause": cl.standard_clause,
                    "iso_13485_clause": cl.iso_13485_clause,
                    "relationship": cl.relationship,
                    "description_en": cl.description_en,
                    "description_zh": cl.description_zh,
                }
                for cl in std.clause_links
            ],
            "regulatory_references": std.regulatory_references,
            "audit_questions": std.audit_questions,
        })

    return JSONResponse(content={
        "product_profile": {
            "has_software": body.get("has_software", False),
            "has_electrical": body.get("has_electrical", False),
            "is_implantable": body.get("is_implantable", False),
            "is_sterile": body.get("is_sterile", False),
            "sterilization_method": body.get("sterilization_method", ""),
            "has_biological_contact": body.get("has_biological_contact", False),
        },
        "applicable_standards_count": len(results),
        "applicable_standards": results,
    })


@report_router.post("/standards/adjust")
async def adjust_standard_mapping(request: Request):
    """Adjust a supplemental standard's clause-to-ISO-13485 mapping.

    Accepts a JSON body:
    {
        "standard_id": "ISO_14971",
        "standard_clause": "ISO 14971 Clause 4",
        "old_iso_clause": "7.1",
        "new_iso_clause": "7.3.3"
    }

    The old_iso_clause is optional but recommended for safety verification.
    Changes persist for the server session duration.
    """
    mods = _get_standards_modules()
    body = await request.json()

    standard_id = body.get("standard_id", "")
    standard_clause = body.get("standard_clause", "")
    old_iso_clause = body.get("old_iso_clause", "")
    new_iso_clause = body.get("new_iso_clause", "")

    if not standard_id or not standard_clause or not new_iso_clause:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Required fields: standard_id, standard_clause, new_iso_clause",
            },
        )

    result = mods["adjust_standard_clause_mapping"](
        standard_id=standard_id,
        standard_clause=standard_clause,
        old_iso_clause=old_iso_clause,
        new_iso_clause=new_iso_clause,
    )

    status_code = 200 if result["success"] else 400
    return JSONResponse(status_code=status_code, content=result)


# ============================================================
# SSE Event Streaming for Real-Time Cross-Examination
# ============================================================
# SSE Event Streaming for Real-Time Cross-Examination
# ============================================================


# Global event bus: run_id → asyncio.Queue
# Each queue holds dicts like {"type": "analyzer", "content": "...", ...}
_event_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


def emit_cross_exam_event(run_id: str, event: dict) -> None:
    """Emit an event to all SSE listeners for a given run.

    Call this from the pipeline/verifier when cross-examination
    messages are generated.

    Event types:
        - round_start: {"type": "round_start", "round": 1}
        - analyzer:    {"type": "analyzer", "round": 1, "content": "...", "regulation": "..."}
        - verifier:    {"type": "verifier", "round": 1, "content": "...", "regulation": "..."}
        - round_end:   {"type": "round_end", "round": 1, "agreed": true/false}
        - complete:    {"type": "complete", "verdict": "...", "flagged": true/false}
        - error:       {"type": "error", "message": "..."}
        - human_ack:   {"type": "human_ack", "message": "..."}
    """
    event["timestamp"] = time.time()
    for queue in _event_queues.get(run_id, []):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"SSE queue full for run {run_id}, dropping event")


async def _sse_generator(run_id: str, queue: asyncio.Queue):
    """Async generator that yields SSE events from the queue."""
    try:
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id, 'timestamp': time.time()})}\n\n"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # If complete or error, end the stream
                if event.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
    finally:
        # Cleanup: remove this queue from the listeners
        if run_id in _event_queues:
            try:
                _event_queues[run_id].remove(queue)
            except ValueError:
                pass
            if not _event_queues[run_id]:
                del _event_queues[run_id]


@report_router.get("/{run_id}/stream")
async def stream_cross_examination(run_id: str):
    """SSE endpoint for real-time cross-examination events.

    Client connects with EventSource and receives events as they happen.
    Events include analyzer/verifier messages, round results, and final verdict.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_queues[run_id].append(queue)

    return StreamingResponse(
        _sse_generator(run_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@report_router.post("/{run_id}/inject")
async def inject_human_message(run_id: str, body: dict):
    """Inject a human message into the cross-examination.

    Body:
        {"message": "你問錯了，應該問...", "user_id": "ra_user"}
    """
    message = body.get("message", "").strip()
    user_id = body.get("user_id", "human")

    if not message:
        raise HTTPException(status_code=400, detail="Missing 'message' field")

    # Broadcast the human injection event to all SSE listeners
    event = {
        "type": "human_injection",
        "message": message,
        "user_id": user_id,
        "run_id": run_id,
    }
    emit_cross_exam_event(run_id, event)

    return JSONResponse(content={
        "success": True,
        "message": "Human injection sent to cross-examination",
    })


@report_router.post("/{run_id}/pause")
async def pause_cross_examination(run_id: str):
    """Pause the cross-examination for this run."""
    emit_cross_exam_event(run_id, {"type": "pause", "run_id": run_id})
    return JSONResponse(content={"success": True, "message": "Pause signal sent"})


@report_router.post("/{run_id}/resume")
async def resume_cross_examination(run_id: str):
    """Resume the cross-examination for this run."""
    emit_cross_exam_event(run_id, {"type": "resume", "run_id": run_id})
    return JSONResponse(content={"success": True, "message": "Resume signal sent"})
