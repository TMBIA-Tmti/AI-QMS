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
import os

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

# ── i18n helper ──

def _t(key: str, lang: str = "zh-TW", **kwargs) -> str:
    """Translate a key using locale JSON files."""
    _cache = getattr(_t, '_cache', {})
    if lang not in _cache:
        locale_path = os.path.join(
            os.path.dirname(__file__), '..', 'chainlit_app', 'locales', f'{lang}.json'
        )
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
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
async def serve_report_page(run_id: str, lang: str = Query(default="zh-TW")):
    """Serve the report HTML page for a specific run.

    Args:
        run_id: Pipeline run identifier.
        lang: UI language code (e.g. zh-TW, en-US, ja-JP). Injected into JS.
    """
    html_path = REPORT_STATIC_DIR / "report.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Report page not found")

    # Verify run exists
    filepath = _PIPELINE_DIR / f"{run_id}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # Read and inject run_id + language into the HTML template
    html_content = html_path.read_text(encoding="utf-8")
    html_content = html_content.replace("{{RUN_ID}}", run_id)
    html_content = html_content.replace("{{LANG}}", lang)
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


@report_router.get("/locales/{lang_code}.json")
async def serve_report_locale(lang_code: str):
    """Serve locale JSON for the report UI.

    Falls back to zh-TW if requested language file is not found.
    """
    locales_dir = REPORT_STATIC_DIR / "locales"
    filepath = locales_dir / f"{lang_code}.json"
    if not filepath.exists():
        # Fallback to zh-TW
        filepath = locales_dir / "zh-TW.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Locale file not found")
    return FileResponse(filepath, media_type="application/json; charset=utf-8")

# ============================================================
# API Endpoints — Read
# ============================================================


@report_router.get("/runs")
async def list_runs():
    """List all saved pipeline runs."""
    runs = ComparisonTable.list_runs(_PIPELINE_DIR)
    return JSONResponse(content={"runs": runs})


@report_router.get("/latest")
async def redirect_to_latest_run():
    """Redirect to the most recent pipeline run's report page.

    Finds the newest run_*.json file and redirects to /api/report/page/{run_id}.
    Returns 404 if no runs exist.
    """
    runs = ComparisonTable.list_runs(_PIPELINE_DIR)
    if not runs:
        raise HTTPException(status_code=404, detail="No pipeline runs found")

    # Runs are sorted by modified time (newest first) by list_runs()
    latest_run_id = runs[0].get("run_id", "")
    if not latest_run_id:
        raise HTTPException(status_code=404, detail="No valid run_id found")

    from starlette.responses import RedirectResponse
    return RedirectResponse(url=f"/api/report/page/{latest_run_id}")


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
    run_id: Optional[str] = Query(None, description="Pipeline run ID to attach document evidence"),
):
    """Get the full cross-reference comparison table.

    Returns ISO 13485 clauses as rows, with each selected regulation's
    mapping status, rationale, method, and confidence.
    Also returns unique requirements (delta items) per regulation.
    If run_id is provided, attaches document evidence from the pipeline run.
    If run_id is not provided, auto-selects the latest run (if any).
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

    for clause_id, clause_info in checklist.items():
        row = {
            "clause_id": clause_id,
            "clause_title": clause_info.get("title", ""),
            "audit_impact": clause_info.get("audit_impact", ""),
            "regulations": {},
            "doc_evidence": [],  # populated from pipeline run
        }

        for rid in reg_ids:
            analysis = mods["get_overlap_analysis"](rid, clause_id)
            profile = all_regs[rid]

            mapping = analysis.get("mapping") or {}
            reg_data = {
                "status": analysis.get("status", "na"),
                "is_delta": analysis.get("is_delta", False),
                "regulation_ref": mapping.get("regulation_ref", ""),
                "rationale_en": mapping.get("rationale_en", ""),
                "rationale_zh": mapping.get("rationale_zh", ""),
                "method": mapping.get("method", ""),
                "confidence": mapping.get("confidence", 0.0),
                "notes": mapping.get("notes", ""),
                "delta_items": analysis.get("delta_items", []),
            }
            row["regulations"][rid] = reg_data

        rows.append(row)

    # ── Attach document evidence from pipeline run ──
    # Group pipeline rows by clause_id to find which docs match each clause
    _attached_run_id = None
    try:
        # Auto-select latest run if not specified
        if not run_id:
            available_runs = ComparisonTable.list_runs(_PIPELINE_DIR)
            if available_runs:
                run_id = available_runs[0].get("run_id", "")

        if run_id:
            run_file = _PIPELINE_DIR / f"{run_id}.json"
            if run_file.exists():
                import json as _json
                with open(run_file, "r", encoding="utf-8") as _f:
                    run_data = _json.load(_f)

                # Build clause_id → list of doc evidence
                clause_evidence: dict[str, list[dict]] = {}
                for _row_id, _row_data in run_data.get("rows", {}).items():
                    _cid = _row_data.get("clause_id", "")
                    _did = _row_data.get("doc_id", "")
                    _dtitle = _row_data.get("doc_title", "")
                    _evidence_items = _row_data.get("evidence_items", [])

                    if not _cid or not _did:
                        continue

                    # Summarize evidence for this doc-clause pair
                    found_items = []
                    missing_items = []
                    inadequate_items = []
                    for ei in _evidence_items:
                        name = ei.get("evidence_name", "")
                        if ei.get("found"):
                            item = {
                                "name": name,
                                "section": ei.get("source_section", ""),
                                "quote": (ei.get("source_quote", "") or "")[:200],
                                "relevance": ei.get("relevance_score", 0),
                                "inadequate": ei.get("is_inadequate", False),
                            }
                            if ei.get("is_inadequate"):
                                inadequate_items.append(item)
                            else:
                                found_items.append(item)
                        else:
                            missing_items.append(name)

                    doc_entry = {
                        "doc_id": _did,
                        "doc_title": _dtitle,
                        "found_count": len(found_items),
                        "missing_count": len(missing_items),
                        "inadequate_count": len(inadequate_items),
                        "found": found_items,
                        "inadequate": inadequate_items,
                        "missing": missing_items,
                    }

                    if _cid not in clause_evidence:
                        clause_evidence[_cid] = []
                    clause_evidence[_cid].append(doc_entry)

                # Attach evidence to rows
                for row in rows:
                    cid = row["clause_id"]
                    row["doc_evidence"] = clause_evidence.get(cid, [])

                _attached_run_id = run_id
    except Exception as e:
        logger.warning(f"Failed to attach doc evidence from pipeline run: {e}")

    # ── Supplement: scan ALL quality docs to fill gaps ──
    # Pipeline only matches docs to their "primary" clauses. Here we also
    # include docs matched by regex / body scan that weren't in the pipeline.
    try:
        from src.services.markdown_store_service import MarkdownStoreService
        _doc_svc = MarkdownStoreService()
        _all_docs = _doc_svc.list_documents()  # all active docs

        # Load clause IDs for matching
        from src.analysis.compliance_rules import list_clauses
        _clause_ids = list_clauses("ISO_13485")

        # Collect doc_ids already present per clause from pipeline
        _pipeline_doc_ids: dict[str, set[str]] = {}
        for row in rows:
            cid = row["clause_id"]
            _pipeline_doc_ids[cid] = {
                de["doc_id"] for de in row.get("doc_evidence", [])
            }

        # For each doc, determine which clauses it covers
        for _doc_summary in _all_docs:
            _did = _doc_summary.get("doc_id", "")
            _dtitle = _doc_summary.get("title", "")
            _doc_type = _doc_summary.get("doc_type", "")
            _status = _doc_summary.get("status", "active")

            # Skip non-active docs
            if _status != "active":
                continue

            # Skip external standard / regulation documents
            _doc_dict = {"doc_id": _did, "title": _dtitle, "doc_type": _doc_type}
            if ComparisonTable._is_external_standard_doc(_doc_dict, "ISO_13485"):
                continue

            # Get doc content for body scanning
            _doc_detail = _doc_svc.get_document(_did)
            _doc_body = ""
            if _doc_detail and isinstance(_doc_detail, dict):
                _doc_body = _doc_detail.get("content", "")

            _doc_tags = []
            if isinstance(_doc_detail, dict):
                _doc_tags = _doc_detail.get("tags", [])

            # Match doc to clauses using regex strategies (no LLM here)
            _matched = ComparisonTable._match_doc_to_clauses(
                _did, _dtitle, _doc_tags, _clause_ids, _doc_body
            )
            if _matched is None:
                # No regex match — skip (LLM fallback too expensive for API call)
                continue

            # Add to doc_evidence for each matched clause if not already present
            for _cid in _matched:
                existing_ids = _pipeline_doc_ids.get(_cid, set())
                if _did in existing_ids:
                    continue  # already from pipeline

                # Create a supplemental doc entry (no evidence details,
                # just shows which doc is mapped to this clause)
                _supp_entry = {
                    "doc_id": _did,
                    "doc_title": _dtitle,
                    "found_count": -1,  # -1 = not scanned by pipeline
                    "missing_count": -1,
                    "inadequate_count": -1,
                    "found": [],
                    "inadequate": [],
                    "missing": [],
                    "source": "regex_supplement",
                }

                # Find the row for this clause and append
                for row in rows:
                    if row["clause_id"] == _cid:
                        row["doc_evidence"].append(_supp_entry)
                        break

    except Exception as e:
        logger.warning(f"Failed to supplement doc evidence via scan: {e}")
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
        "pipeline_run_id": _attached_run_id,
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
# Verification API Endpoints
# ============================================================


@report_router.get("/verification/summary")
async def get_verification_summary_endpoint():
    """Quick verification summary (pass/warn/fail counts)."""
    try:
        from src.services.regulatory_verifier import get_verification_summary as _get_ver_summary
        summary = _get_ver_summary()
        return JSONResponse(content=summary)
    except Exception as e:
        logger.error(f"Verification summary failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Verification failed: {e}"},
        )


@report_router.get("/verification/full")
async def get_full_verification():
    """Full verification report with all document details."""
    try:
        from src.services.regulatory_verifier import verify_all
        report = verify_all()
        return JSONResponse(content=report.to_dict())
    except Exception as e:
        logger.error(f"Full verification failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Verification failed: {e}"},
        )


@report_router.get("/verification/document/{doc_id}")
async def get_document_verification(doc_id: str):
    """Verify a single document by doc_id."""
    try:
        from src.services.regulatory_verifier import verify_document
        result = verify_document(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
        return JSONResponse(content=result.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document verification failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Verification failed: {e}"},
        )


# ============================================================
# API Endpoints — Read (path-parameter routes MUST come AFTER
# all static-path routes to avoid /{run_id} catching /crossref etc.)
# ============================================================

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
async def reset_for_rerun(run_id: str, row_id: str, body: dict = None, lang: str = Query("zh-TW")):
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

    # Emit SSE event so the cross-exam viewer shows the reset
    emit_cross_exam_event(run_id, {
        "type": "row_reset",
        "row_id": row_id,
        "clause_id": updated.clause_id if hasattr(updated, 'clause_id') else row_id,
        "from_phase": from_phase.value,
        "message": _t("report_api.rerun_sse_msg", lang, row_id=row_id, phase=from_phase.display_name),
    })

    return JSONResponse(
        content={
            "success": True,
            "row": row_dict,
            "message": _t("report_api.rerun_success_msg", lang),
        }
    )


# ============================================================
# API Endpoints — Export
# ============================================================


@report_router.get("/{run_id}/export/{fmt}")
async def export_report(run_id: str, fmt: str, lang: str = Query("zh-TW")):
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
            assessment = _build_export_assessment(flat_rows, summary, lang)

            doc = Document()
            title = doc.add_heading(_t("report_api.title", lang), level=1)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

            from datetime import datetime
            meta = doc.add_paragraph()
            meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = meta.add_run(_t("report_api.meta", lang, run_id=run_id, time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(128, 128, 128)

            # Summary section
            doc.add_heading(_t("report_api.summary_heading", lang), level=2)
            doc.add_paragraph(assessment)

            # Detail table
            doc.add_heading(_t("report_api.detail_heading", lang), level=2)
            if flat_rows:
                headers = [_t("report_api.col_clause", lang), _t("report_api.col_doc", lang), _t("report_api.col_audit_impact", lang), _t("report_api.col_verdict", lang), _t("report_api.col_risk", lang), _t("report_api.col_gap", lang), _t("report_api.col_ra_flag", lang)]
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
            assessment = _build_export_assessment(flat_rows, summary, lang)

            wb = Workbook()
            ws = wb.active
            ws.title = _t("report_api.sheet_name", lang)

            # Headers
            headers = [_t("report_api.col_clause_id", lang), _t("report_api.col_clause_name", lang), _t("report_api.col_doc_id", lang), _t("report_api.col_doc_title", lang), _t("report_api.col_audit_impact", lang),
                       _t("report_api.col_audit_question", lang), _t("report_api.col_verdict", lang), _t("report_api.col_risk_level", lang), _t("report_api.col_gap_severity", lang),
                       _t("report_api.col_evidence", lang), _t("report_api.col_ra_flag", lang), _t("report_api.col_ra_override", lang), _t("report_api.col_ra_notes", lang)]
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


def _build_export_assessment(flat_rows: list[dict], summary: dict, lang: str = "zh-TW") -> str:
    """Build a markdown assessment text from flat rows for Word/Excel export."""
    lines = [
        f"# {_t('report_api.md_title', lang)}",
        "",
        f"**{_t('report_api.md_total_items', lang)}**: {summary.get('total_rows', 0)}",
        f"**{_t('report_api.md_total_docs', lang)}**: {summary.get('documents_analyzed', 0)}",
        f"**{_t('report_api.md_ra_review', lang)}**: {summary.get('flagged_for_ra', 0)} {_t('report_api.md_items', lang)}",
        "",
        f"## {_t('report_api.md_verdict_dist', lang)}",
        "",
    ]

    vd = summary.get("verdict_distribution", {})
    for v, count in vd.items():
        disp = VERDICT_DISPLAY.get(v, {})
        lines.append(f"- {disp.get('icon', '')} {disp.get('label_zh', v)}: {count} {_t('report_api.md_items', lang)}")

    lines.append("")
    lines.append(f"## {_t('report_api.md_risk_dist', lang)}")
    lines.append("")

    rd = summary.get("risk_distribution", {})
    for r, count in rd.items():
        disp = RISK_LEVEL_DISPLAY.get(r, {})
        lines.append(f"- {disp.get('icon', '')} {disp.get('label_zh', r)}: {count} {_t('report_api.md_items', lang)}")

    lines.append("")
    lines.append(f"## {_t('report_api.md_detail', lang)}")
    lines.append("")

    for row in flat_rows:
        lines.append(f"### {row.get('clause_id', '')} — {row.get('clause_title', '')}")
        lines.append(
            f"- **{_t('report_api.md_doc_label', lang)}**: {row.get('doc_title', '')} ({row.get('doc_id', '')})"
        )
        lines.append(
            f"- **{_t('report_api.md_verdict_label', lang)}**: {row.get('verdict_icon', '')} {row.get('verdict_label', '')}"
        )
        lines.append(
            f"- **{_t('report_api.md_risk_label', lang)}**: {row.get('risk_icon', '')} {row.get('risk_label', '')}"
        )
        lines.append(f"- **{_t('report_api.md_audit_impact_label', lang)}**: {row.get('audit_impact', '')}")
        ev_found = row.get("evidence_found", 0)
        ev_total = row.get("evidence_total", 0)
        lines.append(f"- **{_t('report_api.md_evidence_label', lang)}**: {_t('report_api.md_evidence_found', lang, found=ev_found, total=ev_total)}")

        if row.get("remediation"):
            lines.append(f"- **{_t('report_api.md_remediation_label', lang)}**: {row['remediation']}")

        if row.get("ra_override"):
            override = row["ra_override"]
            lines.append(
                f"- **{_t('report_api.md_ra_override_label', lang)}**: {override.get('verdict', '')} — {override.get('reason', '')}"
            )

        if row.get("ra_notes"):
            lines.append(f"- **{_t('report_api.md_ra_notes_label', lang)}**: {row['ra_notes']}")

        lines.append("")

    return "\n".join(lines)



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
