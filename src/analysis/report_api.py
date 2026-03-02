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
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

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
            from src.utils.regulatory_export import export_regulatory_list_to_word

            filepath = export_dir / f"compliance_report_{run_id}.docx"
            # Build assessment text from flat rows
            assessment = _build_export_assessment(flat_rows, summary)
            export_regulatory_list_to_word(
                assessment=assessment,
                output_path=str(filepath),
            )
        else:  # excel
            from src.utils.regulatory_export import export_regulatory_list_to_excel

            filepath = export_dir / f"compliance_report_{run_id}.xlsx"
            assessment = _build_export_assessment(flat_rows, summary)
            export_regulatory_list_to_excel(
                assessment=assessment,
                output_path=str(filepath),
            )
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
