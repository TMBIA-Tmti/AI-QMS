"""
AI-QMS — Comparison Table Storage
==================================

The "one big comparison table" — each row is one {regulation clause × document section}
match result. Different views (by standard, by document, by verdict) are just filters.

Storage: JSON file in data/analysis_pipeline/ directory.
Each pipeline run gets its own comparison table file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from src.analysis.state import (
    PipelineState,
    RowState,
    Phase,
    PhaseStatus,
)
from src.analysis.compliance_rules import get_checklist, list_clauses
from src.analysis.risk_matrix import VERDICT_DISPLAY, RISK_LEVEL_DISPLAY


__all__ = [
    "ComparisonTable",
    "build_initial_rows",
]

# Default storage directory
_DEFAULT_DIR = Path("data/analysis_pipeline")


class ComparisonTable:
    """Manages the comparison table for a pipeline run.

    The table is essentially the PipelineState.rows dict with
    convenience methods for filtering, querying, and exporting.
    """

    def __init__(self, state: PipelineState, storage_dir: Path = _DEFAULT_DIR):
        self._state = state
        self._storage_dir = storage_dir
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state(self) -> PipelineState:
        return self._state

    # ── Row population ──

    def populate_from_scan(
        self,
        scan_result: dict,
        standard: str = "ISO_13485",
    ) -> int:
        """Build initial rows from scan_regulatory_references() output + checklist.

        For each document that references the given standard, create one row
        per clause in the checklist.

        Args:
            scan_result: Output of MarkdownStoreService.scan_regulatory_references()
            standard: Standard identifier to analyze against

        Returns:
            Number of rows created
        """
        checklist = get_checklist(standard)
        clause_ids = list_clauses(standard)
        by_doc = scan_result.get("by_document", [])

        # Find documents that reference this standard
        relevant_docs: list[dict] = []
        for doc in by_doc:
            doc_standards = doc.get("standards", [])
            # Check if any referenced standard matches (fuzzy: "ISO 13485" matches "ISO_13485")
            standard_normalized = standard.replace("_", " ").lower()
            for ds in doc_standards:
                if standard_normalized in ds.lower().replace("_", " "):
                    relevant_docs.append(doc)
                    break

        row_count = 0
        for doc in relevant_docs:
            doc_id = doc.get("doc_id", "")
            doc_title = doc.get("title", "")

            for clause_id in clause_ids:
                clause_info = checklist.get(clause_id, {})
                row = RowState(
                    clause_id=clause_id,
                    standard=standard,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    clause_title=clause_info.get("title", ""),
                    audit_impact=clause_info.get("audit_impact", "minor"),
                    audit_question=clause_info.get("audit_question", ""),
                    expected_evidence=clause_info.get("expected_evidence", []),
                )
                self._state.add_row(row)
                row_count += 1

        return row_count

    # ── Querying ──

    def get_rows_for_document(self, doc_id: str) -> list[RowState]:
        """Get all rows for a specific document."""
        return [r for r in self._state.get_all_rows() if r.doc_id == doc_id]

    def get_rows_for_clause(self, clause_id: str) -> list[RowState]:
        """Get all rows for a specific clause (across all documents)."""
        return [r for r in self._state.get_all_rows() if r.clause_id == clause_id]

    def get_rows_by_verdict(self, verdict: str) -> list[RowState]:
        """Get rows filtered by verdict."""
        return self._state.get_rows_by_verdict(verdict)

    def get_rows_by_risk_level(self, risk_level: str) -> list[RowState]:
        """Get rows filtered by risk level."""
        return [r for r in self._state.get_all_rows() if r.risk_level == risk_level]

    def get_flagged_rows(self) -> list[RowState]:
        """Get rows flagged for RA review (cross-examination disagreement)."""
        return [r for r in self._state.get_all_rows() if r.flagged_for_ra]

    def get_incomplete_rows(self) -> list[RowState]:
        """Get rows that haven't completed all phases."""
        return [
            r
            for r in self._state.get_all_rows()
            if r.overall_status != PhaseStatus.COMPLETED.value
        ]

    # ── Statistics ──

    def summary(self) -> dict:
        """Generate a summary of the comparison table."""
        all_rows = self._state.get_all_rows()
        total = len(all_rows)

        verdict_counts: dict[str, int] = {}
        risk_counts: dict[str, int] = {}
        doc_counts: dict[str, int] = {}
        flagged_count = 0

        for r in all_rows:
            if r.verdict:
                verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
            if r.risk_level:
                risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1
            doc_counts[r.doc_id] = doc_counts.get(r.doc_id, 0) + 1
            if r.flagged_for_ra:
                flagged_count += 1

        return {
            "total_rows": total,
            "documents_analyzed": len(doc_counts),
            "verdict_distribution": verdict_counts,
            "risk_distribution": risk_counts,
            "flagged_for_ra": flagged_count,
            "rows_per_document": doc_counts,
            "completion": self._state.progress_summary(),
        }

    # ── Single-row re-run support ──

    def reset_row_for_rerun(
        self,
        row_id: str,
        from_phase: Phase = Phase.GAP_SCAN,
    ) -> Optional[RowState]:
        """Reset a single row to re-run from a specific phase.

        Used for single-row re-run after RA correction.
        Preserves Phase 0 and 0.5 results, clears Phase 1+ results.

        Args:
            row_id: Row to reset
            from_phase: Phase to restart from (default: Phase 1 / GAP_SCAN)

        Returns:
            The reset RowState, or None if row not found
        """
        from src.analysis.state import PHASE_ORDER

        row = self._state.get_row(row_id)
        if row is None:
            return None

        # Clear phase results from the specified phase onwards
        phase_idx = PHASE_ORDER.index(from_phase)
        for p in PHASE_ORDER[phase_idx:]:
            row.phase_results.pop(p.value, None)

        # Reset row state
        row.current_phase = from_phase.value
        row.overall_status = PhaseStatus.PENDING.value

        # Clear downstream computed values if resetting from Phase 1+
        if from_phase.value <= Phase.GAP_SCAN.value:
            row.evidence_items = []
            row.gap_severity = None
            row.risk_level = None
            row.verdict = None
            row.verification_rounds = []
            row.verification_agreed = None
            row.flagged_for_ra = False
            row.remediation_suggestion = None
            row.remediation_regulation_cite = None

        row.updated_at = time.time()
        self._state.update_row(row)

        return row

    # ── RA modifications ──

    def override_verdict(
        self,
        row_id: str,
        new_verdict: str,
        reason: str,
        user_id: str = "ra_user",
    ) -> Optional[RowState]:
        """RA manually overrides a row's verdict.

        Risk auto-recalculates based on the new verdict (table lookup, no LLM).
        Previous values are saved in version_history.

        Args:
            row_id: Row to modify
            new_verdict: New verdict (from Verdict class)
            reason: Why the RA is overriding
            user_id: Who made the change
        """
        row = self._state.get_row(row_id)
        if row is None:
            return None

        # Save current state to version history
        row.version_history.append(
            {
                "action": "override_verdict",
                "previous_verdict": row.verdict,
                "previous_risk_level": row.risk_level,
                "previous_gap_severity": row.gap_severity,
                "new_verdict": new_verdict,
                "reason": reason,
                "by": user_id,
                "at": time.time(),
            }
        )

        # Apply override
        row.ra_override = {
            "verdict": new_verdict,
            "reason": reason,
            "by": user_id,
            "at": time.time(),
        }
        row.verdict = new_verdict
        row.updated_at = time.time()

        self._state.update_row(row)
        return row

    def add_clause_note(
        self,
        row_id: str,
        note: str,
        user_id: str = "ra_user",
    ) -> Optional[RowState]:
        """Add a permanent note to a clause (always included in every analysis)."""
        row = self._state.get_row(row_id)
        if row is None:
            return None

        row.version_history.append(
            {
                "action": "add_note",
                "previous_note": row.ra_notes,
                "new_note": note,
                "by": user_id,
                "at": time.time(),
            }
        )

        row.ra_notes = note
        row.updated_at = time.time()
        self._state.update_row(row)
        return row

    def restore_llm_original(self, row_id: str) -> Optional[RowState]:
        """Restore the LLM's original verdict (undo RA override).

        All versions are preserved in version_history.
        """
        row = self._state.get_row(row_id)
        if row is None:
            return None

        if row.ra_override is None:
            return row  # Nothing to restore

        # Find the original LLM verdict from version history
        original_verdict = None
        for entry in row.version_history:
            if entry.get("action") == "override_verdict":
                original_verdict = entry.get("previous_verdict")
                break

        if original_verdict is None:
            return row

        row.version_history.append(
            {
                "action": "restore_original",
                "overridden_verdict": row.verdict,
                "restored_verdict": original_verdict,
                "at": time.time(),
            }
        )

        row.verdict = original_verdict
        row.ra_override = None
        row.updated_at = time.time()

        self._state.update_row(row)
        return row

    # ── Persistence ──

    def save(self) -> Path:
        """Save the comparison table (via PipelineState) to disk."""
        filepath = self._storage_dir / f"{self._state.run_id}.json"
        self._state.save(filepath)
        return filepath

    @classmethod
    def load(cls, run_id: str, storage_dir: Path = _DEFAULT_DIR) -> "ComparisonTable":
        """Load a comparison table from disk."""
        filepath = storage_dir / f"{run_id}.json"
        state = PipelineState.load(filepath)
        return cls(state, storage_dir)

    @classmethod
    def list_runs(cls, storage_dir: Path = _DEFAULT_DIR) -> list[dict]:
        """List all saved pipeline runs."""
        if not storage_dir.exists():
            return []

        runs = []
        for f in sorted(storage_dir.glob("run_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                runs.append(
                    {
                        "run_id": data.get("run_id", f.stem),
                        "created_at": data.get("created_at"),
                        "status": data.get("status"),
                        "total_rows": len(data.get("rows", {})),
                        "standard": data.get("standard"),
                        "mode": data.get("mode"),
                    }
                )
            except Exception:
                continue

        return runs

    # ── Export helpers ──

    def to_flat_rows(self) -> list[dict]:
        """Export comparison table as flat dicts (for Word/Excel export).

        Each dict has all relevant fields flattened for easy rendering.
        """
        rows = []
        for r in self._state.get_all_rows():
            verdict_disp = VERDICT_DISPLAY.get(r.verdict or "", {})
            risk_disp = RISK_LEVEL_DISPLAY.get(r.risk_level or "", {})

            # Count evidence found/total
            evidence_found = sum(1 for e in r.evidence_items if e.get("found", False))
            evidence_total = len(r.expected_evidence)

            rows.append(
                {
                    "row_id": r.row_id,
                    "clause_id": r.clause_id,
                    "clause_title": r.clause_title,
                    "doc_id": r.doc_id,
                    "doc_title": r.doc_title,
                    "audit_impact": r.audit_impact,
                    "audit_question": r.audit_question,
                    "expected_evidence": r.expected_evidence,
                    "evidence_found": evidence_found,
                    "evidence_total": evidence_total,
                    "gap_severity": r.gap_severity,
                    "risk_level": r.risk_level,
                    "risk_icon": risk_disp.get("icon", ""),
                    "risk_label": risk_disp.get("label_zh", ""),
                    "verdict": r.verdict,
                    "verdict_icon": verdict_disp.get("icon", ""),
                    "verdict_label": verdict_disp.get("label_zh", ""),
                    "remediation": r.remediation_suggestion,
                    "flagged_for_ra": r.flagged_for_ra,
                    "ra_override": r.ra_override,
                    "ra_notes": r.ra_notes,
                    "verification_agreed": r.verification_agreed,
                    "verification_rounds": len(r.verification_rounds),
                }
            )

        # Sort by clause_id for consistent ordering
        rows.sort(key=lambda x: [int(n) for n in x["clause_id"].split(".")])
        return rows


def build_initial_rows(
    scan_result: dict,
    standard: str = "ISO_13485",
    storage_dir: Path = _DEFAULT_DIR,
) -> ComparisonTable:
    """Convenience: create a new PipelineState + ComparisonTable and populate rows.

    Args:
        scan_result: Output of scan_regulatory_references()
        standard: Standard to analyze against
        storage_dir: Where to save pipeline state

    Returns:
        ComparisonTable ready for pipeline execution
    """
    state = PipelineState(standard=standard)
    table = ComparisonTable(state, storage_dir)
    table.populate_from_scan(scan_result, standard)
    return table
