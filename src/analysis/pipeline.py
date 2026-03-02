"""
AI-QMS — Pipeline Orchestrator
================================

Manages the execution of Phases 0→6 for the analysis pipeline.

Features:
  - Three execution modes: step-by-step / auto-run / risk-only
  - Mode switching at any time
  - Pause/resume support
  - Auto-pause on critical gaps or evidence conflicts
  - LLM budget tracking with upper limit
  - Crash recovery via JSON state persistence
  - Per-row progress tracking
  - Phase 3 (Risk Assessment) uses rule engine, no LLM

Pipeline flow:
  Phase 0:   Data Quality Gate (code) → skip bad rows
  Phase 0.5: Reference Mapping (code) → locate relevant sections
  Phase 1:   Gap Scan (LLM #1) → find evidence
  Phase 2:   Checklist Verification (LLM #2) → verify evidence
  Phase 3:   Risk Assessment (rule engine) → matrix lookup
  Phase 4:   Remediation Suggestions (LLM #3) → only for gaps
  Phase 5:   Independent Verification (LLM #4) → cross-examination
  Phase 6:   Source Verification (HTTP) → batch URL check
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

from src.analysis.state import (
    Phase,
    PhaseStatus,
    ExecutionMode,
    PauseReason,
    PipelineState,
    RowState,
    LLMBudget,
    PHASE_ORDER,
)

from src.analysis.comparison_table import ComparisonTable
from src.analysis.data_quality import run_data_quality_gate
from src.analysis.reference_mapper import run_reference_mapping
from src.analysis.gap_scanner import run_gap_scan_row
from src.analysis.checklist_verifier import run_checklist_verify_row
from src.analysis.remediation import run_remediation_row
from src.analysis.verifier import run_verification_row
from src.analysis.source_checker import run_source_check

logger = logging.getLogger(__name__)


__all__ = [
    "AnalysisPipeline",
]


# ============================================================
# Phase 3 — Risk Assessment (rule engine, no LLM)
# ============================================================


def _run_risk_assessment_row(row_state: RowState) -> None:
    """Execute Phase 3 for a single row using the rule engine.

    Reads evidence items from Phase 1/2 and applies risk_matrix.py
    to determine gap_severity, risk_level, and verdict.
    """
    from src.analysis.state import PhaseResult, EvidenceItem
    from src.analysis.risk_matrix import (
        determine_gap_severity,
        assess_risk,
        risk_to_verdict,
    )

    phase_result = PhaseResult(
        phase=Phase.RISK_ASSESSMENT.value,
        started_at=time.time(),
    )

    try:
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        # Determine gap severity from evidence items
        found_count = sum(1 for e in evidence_items if e.found and not e.is_inadequate)
        total_count = len(evidence_items)
        inadequate_count = sum(1 for e in evidence_items if e.is_inadequate)
        outdated_count = sum(1 for e in evidence_items if e.is_outdated)

        gap_severity = determine_gap_severity(
            total_expected=total_count,
            found_adequate=found_count,
            found_inadequate=inadequate_count,
            found_outdated=outdated_count,
        )

        # Lookup risk level from matrix
        risk_level = assess_risk(
            audit_impact=row_state.audit_impact,
            gap_severity=gap_severity,
        )

        # Derive verdict
        verdict = risk_to_verdict(risk_level)

        # Store results
        row_state.gap_severity = gap_severity
        row_state.risk_level = risk_level
        row_state.verdict = verdict

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "gap_severity": gap_severity,
            "risk_level": risk_level,
            "verdict": verdict,
            "evidence_stats": {
                "total": total_count,
                "found_adequate": found_count,
                "inadequate": inadequate_count,
                "outdated": outdated_count,
                "missing": total_count - found_count - inadequate_count,
            },
        }

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    row_state.set_phase_result(Phase.RISK_ASSESSMENT, phase_result)


# ============================================================
# Pipeline orchestrator
# ============================================================


class AnalysisPipeline:
    """Orchestrates the multi-step analysis pipeline.

    Usage:
        pipeline = AnalysisPipeline(
            llm_completion_fn=manager.completion,
            model="gpt-4o",
        )
        pipeline.initialize(scan_result)
        pipeline.run()  # or pipeline.step() for step-by-step
    """

    def __init__(
        self,
        llm_completion_fn: Callable,
        model: str = "default",
        mode: ExecutionMode = ExecutionMode.AUTO_RUN,
        max_tokens_budget: int = 500_000,
        standard: str = "ISO_13485",
        state_dir: Path = Path("data/analysis_pipeline"),
        on_phase_complete: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_row_complete: Optional[Callable] = None,
        selected_regulations: list[str] | None = None,
    ):
        """Initialize the pipeline.

        Args:
            llm_completion_fn: LLM completion function (matches LLMProviderManager.completion)
            model: LLM model name to use
            mode: Execution mode (step-by-step / auto-run / risk-only)
            max_tokens_budget: Maximum total LLM tokens allowed
            standard: Regulatory standard to analyze against
            state_dir: Directory for state persistence
            on_phase_complete: Callback(phase, state) after each phase completes
            on_pause: Callback(reason, state) when pipeline pauses
            on_row_complete: Callback(row_state, state) when a row finishes all phases
            selected_regulations: Country regulation IDs for multi-regulation cross-exam
                                   (e.g., ['QMSR', 'EU_MDR', 'TFDA'])
        """
        self._llm_fn = llm_completion_fn
        self._model = model
        self._standard = standard
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._selected_regulations = selected_regulations

        # Callbacks
        self._on_phase_complete = on_phase_complete
        self._on_pause = on_pause
        self._on_row_complete = on_row_complete

        # State
        self._state = PipelineState(
            mode=mode.value,
            standard=standard,
        )
        budget = LLMBudget(max_total_tokens=max_tokens_budget)
        self._state.update_budget(budget)

        # Comparison table wrapper
        self._table = ComparisonTable(self._state, state_dir)

    # ── Properties ──

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def table(self) -> ComparisonTable:
        return self._table

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode(self._state.mode)

    @property
    def is_paused(self) -> bool:
        return self._state.status == PhaseStatus.PAUSED.value

    @property
    def is_completed(self) -> bool:
        return self._state.status == PhaseStatus.COMPLETED.value

    # ── Initialization ──

    def initialize(self, scan_result: dict) -> int:
        """Initialize the pipeline with scan results.

        Creates comparison table rows from scan_regulatory_references() output.

        Args:
            scan_result: Output of MarkdownStoreService.scan_regulatory_references()

        Returns:
            Number of rows created
        """
        row_count = self._table.populate_from_scan(scan_result, self._standard)
        self._state.status = PhaseStatus.PENDING.value
        self._save_state()
        logger.info(f"Pipeline initialized: {row_count} rows for {self._standard}")
        return row_count

    def initialize_from_state(self, state: PipelineState) -> None:
        """Resume from a saved pipeline state (crash recovery).

        Args:
            state: Previously saved PipelineState
        """
        self._state = state
        self._table = ComparisonTable(self._state, self._state_dir)
        logger.info(
            f"Pipeline resumed from state: {state.run_id}, "
            f"progress={state.progress_percent}%"
        )

    # ── Mode switching ──

    def set_mode(self, mode: ExecutionMode) -> None:
        """Switch execution mode (allowed at any time)."""
        self._state.set_mode(mode)
        self._save_state()
        logger.info(f"Pipeline mode switched to: {mode.value}")

    # ── Pause / Resume ──

    def pause(self, reason: PauseReason = PauseReason.USER_REQUESTED) -> None:
        """Pause the pipeline."""
        self._state.pause(reason)
        self._save_state()
        if self._on_pause:
            self._on_pause(reason, self._state)
        logger.info(f"Pipeline paused: {reason.value}")

    def resume(self) -> None:
        """Resume the pipeline from paused state."""
        if not self.is_paused:
            return
        self._state.resume()
        self._save_state()
        logger.info("Pipeline resumed")

    # ── Execution ──

    def run(self) -> PipelineState:
        """Run the pipeline to completion (or until pause/budget).

        In AUTO_RUN mode: runs all phases, pauses only on critical gaps.
        In STEP_BY_STEP mode: runs one phase and pauses.
        In RISK_ONLY mode: runs Phase 0, 0.5, 1, 3 only.

        Returns:
            Final PipelineState
        """
        self._state.status = PhaseStatus.RUNNING.value
        self._save_state()

        try:
            # Phase 0: Data Quality Gate
            if not self._phase_already_done(Phase.DATA_QUALITY):
                self._execute_phase_0()
                if self._should_stop_after_phase():
                    return self._state

            # Phase 0.5: Reference Mapping
            if not self._phase_already_done(Phase.REFERENCE_MAPPING):
                self._execute_phase_05()
                if self._should_stop_after_phase():
                    return self._state

            # Phase 1: Gap Scan (LLM)
            if not self._phase_already_done(Phase.GAP_SCAN):
                self._execute_phase_1()
                if self._should_stop_after_phase():
                    return self._state

            # Phase 2: Checklist Verification (LLM)
            if not self._skip_phase_in_mode(Phase.CHECKLIST_VERIFY):
                if not self._phase_already_done(Phase.CHECKLIST_VERIFY):
                    self._execute_phase_2()
                    if self._should_stop_after_phase():
                        return self._state

            # Phase 3: Risk Assessment (rule engine)
            if not self._phase_already_done(Phase.RISK_ASSESSMENT):
                self._execute_phase_3()
                if self._should_stop_after_phase():
                    return self._state

            # Check for critical gaps — auto-pause in auto mode
            if self._check_critical_gaps():
                return self._state

            # Phase 4: Remediation (LLM, only for gaps)
            if not self._skip_phase_in_mode(Phase.REMEDIATION):
                if not self._phase_already_done(Phase.REMEDIATION):
                    self._execute_phase_4()
                    if self._should_stop_after_phase():
                        return self._state

            # Phase 5: Verification / Cross-examination (LLM)
            if not self._skip_phase_in_mode(Phase.VERIFICATION):
                if not self._phase_already_done(Phase.VERIFICATION):
                    self._execute_phase_5()
                    if self._should_stop_after_phase():
                        return self._state

            # Check for evidence conflicts — auto-pause
            if self._check_evidence_conflicts():
                return self._state

            # Phase 6: Source Check (HTTP)
            if not self._skip_phase_in_mode(Phase.SOURCE_CHECK):
                if not self._phase_already_done(Phase.SOURCE_CHECK):
                    self._execute_phase_6()

            # Complete
            self._state.status = PhaseStatus.COMPLETED.value
            self._state.completed_at = time.time()
            self._save_state()
            logger.info(
                f"Pipeline completed: {self._state.completed_rows}/{self._state.total_rows} rows"
            )

        except Exception as e:
            self._state.status = PhaseStatus.FAILED.value
            self._state.error = str(e)
            self._save_state()
            logger.error(f"Pipeline failed: {e}")

        return self._state

    def step(self) -> tuple[Phase, PipelineState]:
        """Execute one phase and return. For step-by-step mode.

        Returns:
            (phase_executed, state)
        """
        self._state.status = PhaseStatus.RUNNING.value

        # Find the next phase to execute
        current = Phase(self._state.current_phase)

        phase_executors = {
            Phase.DATA_QUALITY: self._execute_phase_0,
            Phase.REFERENCE_MAPPING: self._execute_phase_05,
            Phase.GAP_SCAN: self._execute_phase_1,
            Phase.CHECKLIST_VERIFY: self._execute_phase_2,
            Phase.RISK_ASSESSMENT: self._execute_phase_3,
            Phase.REMEDIATION: self._execute_phase_4,
            Phase.VERIFICATION: self._execute_phase_5,
            Phase.SOURCE_CHECK: self._execute_phase_6,
        }

        executor = phase_executors.get(current)
        if executor:
            executor()

        # Pause after step
        self._state.pause(PauseReason.STEP_MODE_COMPLETE)
        self._save_state()

        return current, self._state

    def run_single_row(
        self,
        row_id: str,
        from_phase: Phase = Phase.GAP_SCAN,
    ) -> Optional[RowState]:
        """Re-run a single row from a specific phase.

        Used for single-row re-run after RA correction.

        Args:
            row_id: Row to re-run
            from_phase: Phase to restart from

        Returns:
            Updated RowState or None if not found
        """
        row = self._table.reset_row_for_rerun(row_id, from_phase)
        if row is None:
            return None

        logger.info(f"Re-running row {row_id} from {from_phase.value}")

        # Execute phases from from_phase onwards
        phase_idx = PHASE_ORDER.index(from_phase)
        for phase in PHASE_ORDER[phase_idx:]:
            if self._skip_phase_in_mode(phase):
                continue
            self._execute_row_phase(row, phase)
            self._state.update_row(row)

        self._save_state()
        return row

    # ── Phase executors ──

    def _execute_phase_0(self) -> None:
        """Phase 0: Data Quality Gate."""
        logger.info("Executing Phase 0: Data Quality Gate")
        self._state.current_phase = Phase.DATA_QUALITY.value

        dq_result = run_data_quality_gate(self._state)

        self._notify_phase_complete(Phase.DATA_QUALITY)
        self._advance_global_phase(Phase.REFERENCE_MAPPING)
        self._save_state()

        logger.info(
            f"Phase 0 complete: {dq_result.rows_with_doc_content}/{dq_result.total_rows} rows have data"
        )

    def _execute_phase_05(self) -> None:
        """Phase 0.5: Reference Mapping."""
        logger.info("Executing Phase 0.5: Reference Mapping")
        self._state.current_phase = Phase.REFERENCE_MAPPING.value

        mapping_summary = run_reference_mapping(self._state)

        self._notify_phase_complete(Phase.REFERENCE_MAPPING)
        self._advance_global_phase(Phase.GAP_SCAN)
        self._save_state()

        logger.info(
            f"Phase 0.5 complete: {mapping_summary.get('rows_mapped', 0)} rows mapped"
        )

    def _execute_phase_1(self) -> None:
        """Phase 1: Gap Scan (LLM)."""
        logger.info("Executing Phase 1: Gap Scan")
        self._state.current_phase = Phase.GAP_SCAN.value

        rows = self._state.get_rows_by_phase(Phase.GAP_SCAN)
        for row in rows:
            if self._budget_exceeded():
                break
            result = run_gap_scan_row(
                row,
                self._state,
                self._llm_fn,
                self._model,
            )
            row.set_phase_result(Phase.GAP_SCAN, result)
            if result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()
            self._state.update_row(row)
            self._save_state()  # Save after each row for crash recovery

        self._notify_phase_complete(Phase.GAP_SCAN)
        self._advance_global_phase(Phase.CHECKLIST_VERIFY)

    def _execute_phase_2(self) -> None:
        """Phase 2: Checklist Verification (LLM)."""
        logger.info("Executing Phase 2: Checklist Verification")
        self._state.current_phase = Phase.CHECKLIST_VERIFY.value

        rows = self._state.get_rows_by_phase(Phase.CHECKLIST_VERIFY)
        for row in rows:
            if self._budget_exceeded():
                break
            result = run_checklist_verify_row(
                row,
                self._state,
                self._llm_fn,
                self._model,
            )
            row.set_phase_result(Phase.CHECKLIST_VERIFY, result)
            if result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()
            self._state.update_row(row)
            self._save_state()

        self._notify_phase_complete(Phase.CHECKLIST_VERIFY)
        self._advance_global_phase(Phase.RISK_ASSESSMENT)

    def _execute_phase_3(self) -> None:
        """Phase 3: Risk Assessment (rule engine, no LLM)."""
        logger.info("Executing Phase 3: Risk Assessment")
        self._state.current_phase = Phase.RISK_ASSESSMENT.value

        rows = self._state.get_rows_by_phase(Phase.RISK_ASSESSMENT)
        for row in rows:
            _run_risk_assessment_row(row)
            if row.get_phase_result(Phase.RISK_ASSESSMENT):
                result = row.get_phase_result(Phase.RISK_ASSESSMENT)
                if result and result.status == PhaseStatus.COMPLETED.value:
                    row.advance_to_next_phase()
            self._state.update_row(row)

        self._notify_phase_complete(Phase.RISK_ASSESSMENT)
        self._advance_global_phase(Phase.REMEDIATION)
        self._save_state()

    def _execute_phase_4(self) -> None:
        """Phase 4: Remediation Suggestions (LLM, only for gaps)."""
        logger.info("Executing Phase 4: Remediation Suggestions")
        self._state.current_phase = Phase.REMEDIATION.value

        rows = self._state.get_rows_by_phase(Phase.REMEDIATION)
        for row in rows:
            if self._budget_exceeded():
                break
            result = run_remediation_row(
                row,
                self._state,
                self._llm_fn,
                self._model,
            )
            row.set_phase_result(Phase.REMEDIATION, result)
            if result.status in (
                PhaseStatus.COMPLETED.value,
                PhaseStatus.SKIPPED.value,
            ):
                row.advance_to_next_phase()
            self._state.update_row(row)
            self._save_state()

        self._notify_phase_complete(Phase.REMEDIATION)
        self._advance_global_phase(Phase.VERIFICATION)

    def _execute_phase_5(self) -> None:
        """Phase 5: Independent Verification / Cross-examination (LLM)."""
        logger.info("Executing Phase 5: Independent Verification")
        self._state.current_phase = Phase.VERIFICATION.value

        rows = self._state.get_rows_by_phase(Phase.VERIFICATION)
        for row in rows:
            if self._budget_exceeded():
                break
            result = run_verification_row(
                row,
                self._state,
                self._llm_fn,
                self._model,
                selected_regulations=self._selected_regulations,
                run_id=self._state.run_id,
            )
            row.set_phase_result(Phase.VERIFICATION, result)
            if result.status in (
                PhaseStatus.COMPLETED.value,
                PhaseStatus.SKIPPED.value,
            ):
                row.advance_to_next_phase()
            self._state.update_row(row)
            self._save_state()

            # Notify per-row completion if callback set
            if (
                self._on_row_complete
                and row.overall_status == PhaseStatus.COMPLETED.value
            ):
                self._on_row_complete(row, self._state)

        self._notify_phase_complete(Phase.VERIFICATION)
        self._advance_global_phase(Phase.SOURCE_CHECK)

    def _execute_phase_6(self) -> None:
        """Phase 6: Source Verification (HTTP batch)."""
        logger.info("Executing Phase 6: Source Verification")
        self._state.current_phase = Phase.SOURCE_CHECK.value

        result = run_source_check(self._state)

        self._notify_phase_complete(Phase.SOURCE_CHECK)
        self._save_state()

        logger.info(
            f"Phase 6 complete: {result.output.get('accessible', 0)} accessible, "
            f"{result.output.get('broken', 0)} broken URLs"
        )

    def _execute_row_phase(self, row: RowState, phase: Phase) -> None:
        """Execute a specific phase for a single row (used in single-row re-run)."""
        if phase == Phase.DATA_QUALITY:
            # Skip — data quality is global, not re-run per row
            row.advance_to_next_phase()
        elif phase == Phase.REFERENCE_MAPPING:
            # Re-run reference mapping for this row only
            from src.analysis.reference_mapper import (
                _extract_sections,
                _build_clause_keywords,
                _score_section_relevance,
            )
            from src.analysis.state import PhaseResult

            phase_result = PhaseResult(
                phase=Phase.REFERENCE_MAPPING.value,
                started_at=time.time(),
            )
            try:
                from src.services.markdown_store_service import MarkdownStoreService

                service = MarkdownStoreService()
                doc_result = service.get_document(row.doc_id)
                content = (
                    doc_result.get("content", "")
                    if doc_result and doc_result.get("success")
                    else ""
                )
                sections = _extract_sections(content)
                clause_info = {
                    "title": row.clause_title,
                    "expected_evidence": row.expected_evidence,
                }
                keywords = _build_clause_keywords(row.clause_id, clause_info)
                candidates = []
                for section in sections:
                    score = _score_section_relevance(section, keywords)
                    if score > 0.1:
                        candidates.append(
                            {
                                "heading": section["heading"],
                                "level": section["level"],
                                "score": round(score, 3),
                                "text_preview": section["text"][:200],
                                "start_pos": section["start_pos"],
                                "text_length": section["text_length"],
                            }
                        )
                candidates.sort(key=lambda x: x["score"], reverse=True)
                candidates = candidates[:5]
                phase_result.status = PhaseStatus.COMPLETED.value
                phase_result.output = {
                    "candidate_sections": candidates,
                    "total_sections_in_doc": len(sections),
                }
            except Exception as e:
                phase_result.status = PhaseStatus.FAILED.value
                phase_result.error = str(e)
            phase_result.completed_at = time.time()
            row.set_phase_result(Phase.REFERENCE_MAPPING, phase_result)
            if phase_result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()

        elif phase == Phase.GAP_SCAN:
            result = run_gap_scan_row(row, self._state, self._llm_fn, self._model)
            row.set_phase_result(Phase.GAP_SCAN, result)
            if result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()

        elif phase == Phase.CHECKLIST_VERIFY:
            result = run_checklist_verify_row(
                row, self._state, self._llm_fn, self._model
            )
            row.set_phase_result(Phase.CHECKLIST_VERIFY, result)
            if result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()

        elif phase == Phase.RISK_ASSESSMENT:
            _run_risk_assessment_row(row)
            result = row.get_phase_result(Phase.RISK_ASSESSMENT)
            if result and result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()

        elif phase == Phase.REMEDIATION:
            result = run_remediation_row(row, self._state, self._llm_fn, self._model)
            row.set_phase_result(Phase.REMEDIATION, result)
            if result.status in (
                PhaseStatus.COMPLETED.value,
                PhaseStatus.SKIPPED.value,
            ):
                row.advance_to_next_phase()

        elif phase == Phase.VERIFICATION:
            result = run_verification_row(
                row,
                self._state,
                self._llm_fn,
                self._model,
                selected_regulations=self._selected_regulations,
                run_id=self._state.run_id,
            )
            row.set_phase_result(Phase.VERIFICATION, result)
            if result.status in (
                PhaseStatus.COMPLETED.value,
                PhaseStatus.SKIPPED.value,
            ):
                row.advance_to_next_phase()

        elif phase == Phase.SOURCE_CHECK:
            # Source check is global, not per-row
            row.advance_to_next_phase()

    # ── Control helpers ──

    def _should_stop_after_phase(self) -> bool:
        """Check if pipeline should stop after current phase."""
        if self.is_paused:
            return True

        if self._budget_exceeded():
            self.pause(PauseReason.LLM_BUDGET_EXCEEDED)
            return True

        if self.mode == ExecutionMode.STEP_BY_STEP:
            self.pause(PauseReason.STEP_MODE_COMPLETE)
            return True

        return False

    def _skip_phase_in_mode(self, phase: Phase) -> bool:
        """Check if a phase should be skipped in current mode.

        RISK_ONLY mode only runs: Phase 0, 0.5, 1, 3.
        """
        if self.mode != ExecutionMode.RISK_ONLY:
            return False
        return phase in (
            Phase.CHECKLIST_VERIFY,
            Phase.REMEDIATION,
            Phase.VERIFICATION,
            Phase.SOURCE_CHECK,
        )

    def _phase_already_done(self, phase: Phase) -> bool:
        """Check if a phase has already been completed globally."""
        try:
            current_idx = PHASE_ORDER.index(Phase(self._state.current_phase))
            phase_idx = PHASE_ORDER.index(phase)
            return phase_idx < current_idx
        except (ValueError, IndexError):
            return False

    def _budget_exceeded(self) -> bool:
        """Check if LLM budget has been exceeded."""
        budget = self._state.get_budget()
        return budget.exceeded

    def _check_critical_gaps(self) -> bool:
        """Check for critical gaps and auto-pause if in auto mode.

        Returns True if pipeline was paused.
        """
        if self.mode != ExecutionMode.AUTO_RUN:
            return False

        from src.analysis.risk_matrix import RiskLevel

        critical_rows = [
            r
            for r in self._state.get_all_rows()
            if r.risk_level == RiskLevel.IMMEDIATE_CORRECTION
        ]

        if critical_rows:
            logger.warning(f"Found {len(critical_rows)} critical gap(s) — auto-pausing")
            self.pause(PauseReason.CRITICAL_GAP)
            return True

        return False

    def _check_evidence_conflicts(self) -> bool:
        """Check for evidence conflicts and auto-pause if in auto mode.

        Returns True if pipeline was paused.
        """
        if self.mode != ExecutionMode.AUTO_RUN:
            return False

        flagged_rows = self._table.get_flagged_rows()

        if flagged_rows:
            logger.warning(
                f"Found {len(flagged_rows)} row(s) with evidence conflicts — auto-pausing"
            )
            self.pause(PauseReason.EVIDENCE_CONFLICT)
            return True

        return False

    def _advance_global_phase(self, next_phase: Phase) -> None:
        """Advance the global pipeline phase."""
        self._state.current_phase = next_phase.value
        self._state.updated_at = time.time()

    def _notify_phase_complete(self, phase: Phase) -> None:
        """Notify callback that a phase completed."""
        if self._on_phase_complete:
            self._on_phase_complete(phase, self._state)

    # ── State persistence ──

    def _save_state(self) -> None:
        """Save pipeline state to disk for crash recovery."""
        try:
            state_file = self._state_dir / f"{self._state.run_id}.json"
            self._state.save(state_file)
        except Exception as e:
            logger.error(f"Failed to save pipeline state: {e}")

    @classmethod
    def load_from_state(
        cls,
        state_path: Path,
        llm_completion_fn: Callable,
        model: str = "default",
        selected_regulations: list[str] | None = None,
    ) -> "AnalysisPipeline":
        """Load a pipeline from a saved state file.

        Args:
            state_path: Path to the saved JSON state file
            llm_completion_fn: LLM completion function
            model: LLM model name
            selected_regulations: Country regulation IDs for multi-regulation cross-exam

        Returns:
            Resumed AnalysisPipeline
        """
        state = PipelineState.load(state_path)
        pipeline = cls(
            llm_completion_fn=llm_completion_fn,
            model=model,
            mode=ExecutionMode(state.mode),
            standard=state.standard,
            state_dir=state_path.parent,
            selected_regulations=selected_regulations,
        )
        pipeline.initialize_from_state(state)
        return pipeline

    # ── Progress / reporting ──

    def progress(self) -> dict:
        """Get current pipeline progress summary."""
        return self._state.progress_summary()

    def get_comparison_table_summary(self) -> dict:
        """Get comparison table summary for reporting."""
        return self._table.summary()
