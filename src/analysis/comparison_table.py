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
import logging
import re
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

logger = logging.getLogger(__name__)

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
        llm_completion_fn=None,
        model: str = "default",
    ) -> int:
        """Build initial rows from scan_regulatory_references() output + checklist.

        Smart matching: instead of creating one row per {document × clause}
        (which yields ~8875 rows for 125 docs × 71 clauses), we match each
        document to only the clauses it is designed to cover.

        Multi-strategy matching (all strategies used, results merged):
          1. Title clause extraction — "(ISO 13485 Clause 4.2.3)" in title
          2. Title keyword mapping — domain keywords → clause family (bonus, not relied upon)
          3. Tags / metadata clause hints
          4. Document body scanning — extract clause refs from doc content (NEW)
          5. LLM classification fallback — if no strategy matches, LLM determines clauses (NEW)

        Args:
            scan_result: Output of MarkdownStoreService.scan_regulatory_references()
            standard: Standard identifier to analyze against
            llm_completion_fn: LLM completion function for fallback classification
            model: LLM model name for fallback classification

        Returns:
            Number of rows created
        """
        checklist = get_checklist(standard)
        clause_ids = list_clauses(standard)
        by_doc = scan_result.get("by_document", [])

        # Load doc content service for body scanning
        try:
            from src.services.markdown_store_service import MarkdownStoreService
            doc_service = MarkdownStoreService()
        except Exception:
            doc_service = None

        # Find documents that reference this standard
        relevant_docs: list[dict] = []
        for doc in by_doc:
            doc_standards = doc.get("standards", [])
            standard_normalized = standard.replace("_", " ").lower()
            for ds in doc_standards:
                if standard_normalized in ds.lower().replace("_", " "):
                    relevant_docs.append(doc)
                    break

        # ── Filter out external standard/regulation documents ──
        # Documents that ARE the standard itself (e.g., "ISO 13485_2016.PDF")
        # should be used as reference material, NOT analyzed as QMS documents.
        relevant_docs = [
            doc for doc in relevant_docs
            if not self._is_external_standard_doc(doc, standard)
        ]
        # Pre-load doc content for body scanning (batch read, more efficient)
        doc_contents: dict[str, str] = {}
        if doc_service:
            for doc in relevant_docs:
                doc_id = doc.get("doc_id", "")
                if doc_id:
                    try:
                        result = doc_service.get_document(doc_id)
                        if result and result.get("success"):
                            doc_contents[doc_id] = result.get("content", "")
                    except Exception:
                        pass

        # Track docs that need LLM fallback
        llm_fallback_docs: list[dict] = []

        row_count = 0
        for doc in relevant_docs:
            doc_id = doc.get("doc_id", "")
            doc_title = doc.get("title", "")
            doc_tags = doc.get("tags", [])
            doc_body = doc_contents.get(doc_id, "")

            # Determine which clauses this document covers
            matched_clauses = self._match_doc_to_clauses(
                doc_id, doc_title, doc_tags, clause_ids, doc_body
            )

            if matched_clauses is None:
                # No strategy matched — queue for LLM fallback
                llm_fallback_docs.append(doc)
                continue

            for clause_id in matched_clauses:
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

        # Process LLM fallback docs
        if llm_fallback_docs and llm_completion_fn:
            logger.info(
                f"LLM fallback: classifying {len(llm_fallback_docs)} docs "
                f"that no strategy could match"
            )
            for doc in llm_fallback_docs:
                doc_id = doc.get("doc_id", "")
                doc_title = doc.get("title", "")
                doc_body = doc_contents.get(doc_id, "")
                matched_clauses = self._llm_classify_doc(
                    doc_id, doc_title, doc_body,
                    clause_ids, checklist,
                    llm_completion_fn, model,
                )
                for clause_id in matched_clauses:
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
        elif llm_fallback_docs:
            # No LLM available — log warning, skip these docs
            logger.warning(
                f"No LLM available for fallback classification. "
                f"Skipping {len(llm_fallback_docs)} unmatched docs: "
                f"{[d.get('doc_id', '?') for d in llm_fallback_docs]}"
            )

        return row_count

    @staticmethod
    def _is_external_standard_doc(doc: dict, standard: str) -> bool:
        """Detect if a document IS an external standard/regulation file.

        External standard documents (e.g., 'ISO 13485_2016.PDF', 'FDA 21 CFR 820.pdf')
        should be used as reference material, not analyzed as internal QMS documents.

        Heuristics:
          1. doc_id or title looks like a standard name (ISO, IEC, FDA, EN, etc.)
          2. doc_id or title contains the standard being analyzed
          3. Filename patterns typical of downloaded standard PDFs

        Returns:
            True if the document appears to be an external standard file
        """
        doc_id = (doc.get("doc_id") or "").strip()
        title = (doc.get("title") or "").strip()
        doc_type = (doc.get("doc_type") or "").strip().lower()

        # Combine for pattern matching
        id_lower = doc_id.lower().replace("_", " ").replace("-", " ")
        title_lower = title.lower().replace("_", " ").replace("-", " ")
        std_lower = standard.lower().replace("_", " ")

        # Known external standard prefixes
        # These are international/national standard body identifiers
        external_prefixes = (
            "iso ", "iso/", "iec ", "iec/", "en ",
            "astm ", "ansi ", "ansi/",
            "fda ", "21 cfr", "cfr ",
            "mdr ", "eu mdr", "ivdr",
            "gmp ", "qsr ", "qmsr",
            "jis ", "gb ", "gb/t", "cnt ", "cns ",
        )

        # 1. doc_id starts with a standard prefix
        if any(id_lower.startswith(p) for p in external_prefixes):
            logger.info(
                f"Excluding external standard doc: {doc_id} "
                f"(doc_id matches standard prefix)"
            )
            return True

        # 2. Title starts with a standard prefix
        if any(title_lower.startswith(p) for p in external_prefixes):
            logger.info(
                f"Excluding external standard doc: {doc_id} "
                f"(title matches standard prefix: '{title}')"
            )
            return True

        # 3. doc_id or title closely matches the standard being analyzed
        #    e.g., standard='ISO_13485', doc_id='ISO 13485_2016'
        if std_lower in id_lower or std_lower in title_lower:
            logger.info(
                f"Excluding external standard doc: {doc_id} "
                f"(matches analyzed standard '{standard}')"
            )
            return True

        # 4. Filename pattern: ends with version/year indicators typical of
        #    downloaded standard PDFs (e.g., 'ISO_13485_2016', 'IEC_62304_2015')
        import re
        if re.match(
            r'^(iso|iec|en|astm|ansi|fda|cfr|mdr|ivdr|jis|gb|cns)'
            r'[\s_./-]'
            r'.*\d{4}',
            id_lower,
        ):
            logger.info(
                f"Excluding external standard doc: {doc_id} "
                f"(filename pattern matches external standard)"
            )
            return True

        # 5. doc_type explicitly marked as external/reference
        if doc_type in ("external", "reference", "standard", "regulation"):
            logger.info(
                f"Excluding external standard doc: {doc_id} "
                f"(doc_type='{doc_type}')"
            )
            return True

        return False

    @staticmethod
    def _match_doc_to_clauses(
        doc_id: str,
        doc_title: str,
        doc_tags: list[str],
        all_clause_ids: list[str],
        doc_body: str = "",
    ) -> list[str] | None:
        """Determine which ISO 13485 clauses a document covers.

        Uses multiple strategies (all applied, results merged):
          1. Title clause reference — "ISO 13485 Clause X.Y.Z" or "條款 X.Y"
          2. Title keyword mapping — domain keywords → known clause families (bonus)
          3. Tags with clause references
          4. Document body scanning — extract clause refs from first ~2000 chars

        doc_id is NOT used for clause inference because the encoding
        convention varies across companies (some use clause-based numbering,
        some use sequential numbering, some use mixed approaches).

        Returns:
            List of clause IDs this document should be analyzed against,
            or None if no strategy could match (needs LLM fallback).
        """

        found_clauses: set[str] = set()

        # Normalize title: underscores → spaces (common OCR artifact)
        title_normalized = doc_title.replace("_", " ")

        # ---- Strategy 1: Extract clause from title ----
        clause_patterns = [
            r"[Cc]lause\s+(\d+(?:\.\d+)*)",       # "Clause 4.2.3"
            r"條款\s*(\d+(?:\.\d+)*)",              # "條款 4.2.3"
            r"\bISO\s*13485[^)]*?(\d+\.\d+(?:\.\d+)*)",  # "ISO 13485 Clause 4.2.3"
            r"^\s*(\d+\.\d+(?:\.\d+)*)\s*[-—\s]+",  # "4.2.3 - Title" at start
        ]
        for pattern in clause_patterns:
            for m in re.finditer(pattern, title_normalized):
                found_clauses.add(m.group(1))

        # (Strategy 2: keyword mapping REMOVED — fragile, breaks when
        #  company uses different title conventions. Body scan is reliable.)
        # ---- Strategy 3: Tags with clause references ----
        for tag in doc_tags:
            tag_clause = re.search(r"(\d+\.\d+(?:\.\d+)*)", tag)
            if tag_clause:
                found_clauses.add(tag_clause.group(1))

        # ---- Strategy 4: Scan document body for clause references ----
        # Look for patterns like "ISO 13485 Clause 7.5" or "條款 7.5"
        # in the first ~3000 chars of the document body.
        if doc_body:
            body_preview = doc_body[:3000]
            body_patterns = [
                r"[Cc]lause\s+(\d+(?:\.\d+)*)",
                r"條款\s*(\d+(?:\.\d+)*)",
                r"\bISO\s*13485[^\n]*?(\d+\.\d+(?:\.\d+)*)",
                # "Baseline domain focus: ... (ISO 13485 Clause X.Y)" pattern
                r"[Bb]aseline\s+domain[^\n]*?(\d+\.\d+(?:\.\d+)*)",
            ]
            for pattern in body_patterns:
                for m in re.finditer(pattern, body_preview):
                    clause_ref = m.group(1)
                    # Normalize X.0 → X (e.g., 8.0 → 8)
                    if clause_ref.endswith(".0"):
                        clause_ref = clause_ref[:-2]
                    # Validate it looks like an ISO 13485 clause (4.x - 8.x)
                    first_digit = clause_ref.split(".")[0]
                    if first_digit in ("4", "5", "6", "7", "8"):
                        found_clauses.add(clause_ref)

        # ---- Expand matched clauses to include sub-clauses ----
        expanded: set[str] = set()
        for clause in found_clauses:
            if clause in all_clause_ids:
                expanded.add(clause)
            prefix = clause + "."
            for cid in all_clause_ids:
                if cid.startswith(prefix):
                    expanded.add(cid)

        # ---- No fallback to all 71 clauses ----
        # If no strategy matched, return None to signal LLM fallback needed
        if not expanded:
            return None

        return sorted(expanded)

    @staticmethod
    def _llm_classify_doc(
        doc_id: str,
        doc_title: str,
        doc_body: str,
        all_clause_ids: list[str],
        checklist: dict,
        llm_completion_fn,
        model: str,
    ) -> list[str]:
        """Use LLM to determine which ISO 13485 clauses a document covers.

        This is the fallback when no regex/keyword strategy could match.
        Sends the doc title + first ~1500 chars of body to LLM with the
        full clause list, and asks the LLM to return matching clause IDs.

        Returns:
            List of matched clause IDs (may be empty if LLM fails).
        """
        # Build clause reference for prompt
        clause_ref_lines = []
        for cid in sorted(all_clause_ids, key=lambda x: [int(n) for n in x.split(".")]):
            info = checklist.get(cid, {})
            clause_ref_lines.append(f"  {cid}: {info.get('title', '')}")
        clause_ref_text = "\n".join(clause_ref_lines)

        body_preview = doc_body[:1500] if doc_body else "(no content available)"
        title_clean = doc_title.replace("_", " ")

        prompt = (
            f"You are an ISO 13485 QMS expert. Given a quality document, determine which "
            f"ISO 13485 clauses it is designed to cover.\n\n"
            f"Document ID: {doc_id}\n"
            f"Document Title: {title_clean}\n\n"
            f"Document Content (first ~1500 chars):\n{body_preview}\n\n"
            f"Available ISO 13485 clauses:\n{clause_ref_text}\n\n"
            f"Return ONLY a JSON array of clause IDs that this document covers. "
            f"For example: [\"7.5.1\", \"7.5.2\", \"7.5.6\"]\n"
            f"Be specific — only include clauses the document is actually about. "
            f"Do NOT include all clauses. Typical documents cover 1-15 clauses.\n"
            f"Return ONLY the JSON array, no other text."
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            response = llm_completion_fn(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=500,
            )
            content = response.get("content", "").strip()

            # Parse JSON array from response
            # Handle cases where LLM wraps in ```json ... ```
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            import json as _json
            clause_list = _json.loads(content)

            if not isinstance(clause_list, list):
                logger.warning(f"LLM returned non-list for {doc_id}: {content}")
                return []

            # Validate and expand
            expanded: set[str] = set()
            for clause in clause_list:
                clause = str(clause).strip()
                if clause in all_clause_ids:
                    expanded.add(clause)
                # Also expand sub-clauses
                prefix = clause + "."
                for cid in all_clause_ids:
                    if cid.startswith(prefix):
                        expanded.add(cid)

            logger.info(
                f"LLM classified {doc_id} ({title_clean[:40]}) -> "
                f"{len(expanded)} clauses: {sorted(expanded)[:5]}..."
            )
            return sorted(expanded)

        except Exception as e:
            logger.warning(f"LLM classification failed for {doc_id}: {e}")
            return []

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
    llm_completion_fn=None,
    model: str = "default",
) -> ComparisonTable:
    """Convenience: create a new PipelineState + ComparisonTable and populate rows.

    Args:
        scan_result: Output of scan_regulatory_references()
        standard: Standard to analyze against
        storage_dir: Where to save pipeline state
        llm_completion_fn: LLM function for fallback doc classification
        model: LLM model name

    Returns:
        ComparisonTable ready for pipeline execution
    """
    state = PipelineState(standard=standard)
    table = ComparisonTable(state, storage_dir)
    table.populate_from_scan(scan_result, standard, llm_completion_fn, model)
    return table
