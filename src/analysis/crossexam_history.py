"""Persist a run's cross-examination (Phase 5, LLM-vs-LLM) summary in the
cross-exam history store (data/crossexam_history/crossexam_store.json).

Nothing used to write to that store, so the history/trend views were always
empty.  This module builds a ``CrossExamRecord`` from a saved pipeline run
(data/analysis_pipeline/<run_id>.json) and upserts it by ``run_id``.  It is used
both by ``AnalysisPipeline.run()`` (after every run, including paused or
interrupted ones, so the record always reflects the latest state) and by
``scripts/backfill_crossexam_history.py`` for old runs.

Never raises: failures are logged and ``False`` is returned.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PIPELINE_DIR = "data/analysis_pipeline"


def build_record(run: dict):
    """Build a CrossExamRecord from a pipeline-run dict, or None if the run has
    no cross-examination rounds."""
    from src.database.crossexam_store import CrossExamRecord

    rows = run.get("rows") or {}
    if isinstance(rows, list):
        rows = {str(i): r for i, r in enumerate(rows)}
    clauses, tot_rounds, agreed, flagged = [], 0, 0, 0
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    duration = 0.0
    model = ""
    for r in rows.values():
        rounds = r.get("verification_rounds") or []
        p5 = (r.get("phase_results") or {}).get("phase_5") or {}
        if not rounds and p5.get("status") != "completed":
            continue
        n = len(rounds)
        tot_rounds += n
        ok = bool(r.get("verification_agreed"))
        fl = bool(r.get("flagged_for_ra"))
        agreed += ok
        flagged += fl
        clauses.append(
            {
                "row_id": r.get("row_id"),
                "clause_id": r.get("clause_id"),
                "doc_id": r.get("doc_id"),
                "standard": r.get("standard"),
                "agreed": ok,
                "flagged_for_ra": fl,
                "rounds": n,
                "verdict": r.get("verdict"),
            }
        )
        u = p5.get("llm_usage") or {}
        for k in usage:
            usage[k] += int(u.get(k) or 0)
        duration += float(p5.get("duration_seconds") or 0)
        model = model or p5.get("llm_model") or ""
    if not clauses or tot_rounds == 0:
        return None
    meta = run.get("run_metadata") or {}
    ts = run.get("completed_at") or run.get("updated_at") or run.get("created_at")
    try:
        stamp = datetime.fromtimestamp(float(ts)).isoformat()
    except Exception:
        stamp = datetime.now().isoformat()
    regs = list(run.get("selected_regulations") or [])
    return CrossExamRecord(
        record_id=f"run-{str(run.get('run_id', ''))[4:16]}",
        run_id=run.get("run_id", ""),
        timestamp=stamp,
        selected_regulations=regs,
        countries=regs,
        clauses=clauses,
        total_clauses=len(clauses),
        total_agreed=agreed,
        total_flagged=flagged,
        total_rounds=tot_rounds,
        llm_usage=usage,
        llm_model=model or str(meta.get("model") or ""),
        duration_seconds=round(duration, 2),
        assessment_mode=str(run.get("mode") or ""),
        lang=str(meta.get("language") or "zh-TW"),
    )


def save_run_record(run_id: str, base: Optional[str] = None) -> bool:
    """Upsert the cross-exam history record for ``run_id``. Never raises."""
    try:
        from src.database.crossexam_store import get_crossexam_store

        path = Path(base or PIPELINE_DIR) / f"{run_id}.json"
        run = json.loads(path.read_text(encoding="utf-8"))
        rec = build_record(run)
        if rec is None:
            return False
        store = get_crossexam_store()
        old = store.get_record_by_run_id(run_id)
        if old is not None:
            store.delete_record(old.record_id)
        store.save_record(rec)
        return True
    except Exception as exc:
        logger.warning("cross-exam history save failed for %s: %r", run_id, exc)
        return False
