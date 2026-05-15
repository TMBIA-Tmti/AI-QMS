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
import threading
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
from src.analysis.gap_scanner import run_gap_scan_row, run_gap_scan_document
from src.analysis.checklist_verifier import (
    run_checklist_verify_row,
    run_checklist_verify_document,
)
from src.analysis.remediation import run_remediation_row, run_remediation_document
from src.analysis.verifier import run_verification_row, run_verification_document
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
            expected_count=total_count,
            found_count=found_count,
            has_inadequate=bool(inadequate_count),
            has_outdated=bool(outdated_count),
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
                "missing": sum(1 for e in evidence_items if not e.found and not getattr(e, 'is_inadequate', False) and not getattr(e, 'is_outdated', False)),
            },
        }

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    row_state.set_phase_result(Phase.RISK_ASSESSMENT, phase_result)


def _emit_phase3_event(run_id: str, event: dict) -> None:
    """Emit Phase 3 pipeline event to SSE listeners for real-time HTML viewing."""
    if not run_id:
        return
    try:
        from src.analysis.report_api import emit_cross_exam_event

        emit_cross_exam_event(run_id, event)
    except ImportError:
        pass


# ============================================================
# Runtime metadata collection
# ============================================================


def _collect_run_metadata(
    provider_info: Optional[dict] = None,
    provider_is_local: bool = False,
) -> dict:
    """Collect provider + hardware info at pipeline start for reports."""
    import platform
    meta: dict = {}

    # ── Provider ──────────────────────────────────────────────
    if provider_info:
        meta.update({
            "provider_name":  provider_info.get("provider_name", ""),
            "provider_type":  provider_info.get("provider_type", ""),
            "is_local":       provider_info.get("is_local", provider_is_local),
            "model":          provider_info.get("model", ""),
            "api_base_url":   provider_info.get("api_base_url", ""),
        })
    else:
        meta["is_local"] = provider_is_local
        meta["provider_name"] = "Local LLM" if provider_is_local else "Cloud API"
        meta["provider_type"] = "Local LLM" if provider_is_local else "Cloud API"

    meta["max_workers"] = 1 if provider_is_local else 8
    meta["workers_reason"] = "auto: local provider" if provider_is_local else "auto: cloud API"

    # ── GPU / hardware ────────────────────────────────────────
    try:
        import torch
        meta["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            meta["gpu_name"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            meta["vram_gb"] = round(props.total_memory / (1024 ** 3), 1)
            cap = torch.cuda.get_device_capability(0)
            meta["gpu_capability"] = f"sm_{cap[0]}{cap[1]}"
            meta["torch_cuda"] = torch.version.cuda or "N/A"
        else:
            meta["gpu_name"] = "No CUDA GPU"
            meta["torch_cuda"] = "N/A"
            meta["vram_gb"] = 0
    except ImportError:
        meta["gpu_name"] = "torch not installed"
        meta["torch_version"] = "N/A"
        meta["torch_cuda"] = "N/A"

    try:
        from src.ocr.gpu_check import _get_driver_cuda_version, check_gpu
        meta["driver_cuda"] = _get_driver_cuda_version() or "N/A"
        gpu_status = check_gpu()
        meta["gpu_compat_status"] = gpu_status.get("status", "unknown")
        meta["gpu_compat_warnings"] = gpu_status.get("warnings", [])
    except Exception:
        meta["driver_cuda"] = "N/A"
        meta["gpu_compat_status"] = "unknown"
        meta["gpu_compat_warnings"] = []

    meta["platform"] = platform.system()
    return meta


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
        max_time_seconds: int = 600,
        standard: str = "ISO_13485",
        state_dir: Path = Path("data/analysis_pipeline"),
        on_phase_complete: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_row_complete: Optional[Callable] = None,
        selected_regulations: list[str] | None = None,
        lang: str = "zh-TW",
        provider_is_local: bool = False,
        provider_info: Optional[dict] = None,
    ):
        """Initialize the pipeline.

        Args:
            llm_completion_fn: LLM completion function (matches LLMProviderManager.completion)
            model: LLM model name to use
            mode: Execution mode (step-by-step / auto-run / risk-only)
            max_tokens_budget: Maximum total LLM tokens allowed
            max_time_seconds: Maximum time in seconds for LLM phases (default 600 = 10 min)
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
        self._lang = lang
        self._provider_is_local = provider_is_local

        # Callbacks
        self._on_phase_complete = on_phase_complete
        self._on_pause = on_pause
        self._on_row_complete = on_row_complete
        # Per-document progress callback for Phase 1 (set by pipeline_runner)
        # Signature: (docs_done: int, total_docs: int, doc_id: str) -> None
        self._phase1_doc_callback: Optional[Callable] = None

        # State
        self._state = PipelineState(
            mode=mode.value,
            standard=standard,
        )
        budget = LLMBudget(
            max_total_tokens=max_tokens_budget, max_time_seconds=max_time_seconds
        )
        self._state.update_budget(budget)

        # Thread lock for Phase 5 parallel state updates
        self._state_lock = threading.Lock()

        # Collect runtime metadata (provider + hardware) once at init
        self._state.run_metadata = _collect_run_metadata(
            provider_info=provider_info,
            provider_is_local=provider_is_local,
        )

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
        row_count = self._table.populate_from_scan(
            scan_result,
            self._standard,
            llm_completion_fn=self._llm_fn,
            model=self._model,
            lang=self._lang,
        )
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

        # Emit pipeline start event for SSE
        try:
            from src.analysis.report_api import emit_cross_exam_event

            emit_cross_exam_event(
                self._state.run_id,
                {
                    "type": "pipeline_started",
                    "run_id": self._state.run_id,
                    "mode": self._state.mode,
                    "total_rows": self._state.total_rows,
                },
            )
        except ImportError:
            pass

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

            # Sanity check: all evidence missing after Phase 1?
            if self._check_all_evidence_missing():
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

            # Emit pipeline complete event for SSE
            try:
                from src.analysis.report_api import emit_cross_exam_event

                emit_cross_exam_event(
                    self._state.run_id,
                    {
                        "type": "pipeline_complete",
                        "run_id": self._state.run_id,
                        "completed_rows": self._state.completed_rows,
                        "total_rows": self._state.total_rows,
                    },
                )
            except ImportError:
                pass
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

        dq_result = run_data_quality_gate(self._state, lang=self._lang)

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

    def _compute_max_workers(self, cloud_cap: int) -> int:
        """Return max concurrent workers based on provider type.

        Local providers (LM Studio / Ollama) are single-instance — use 1.
        Cloud APIs support true concurrency — use cloud_cap.
        """
        return 1 if self._provider_is_local else cloud_cap

    def _execute_phase_1(self) -> None:
        """Phase 1: Gap Scan (LLM) — per-document grouping, parallelized."""
        logger.info("Executing Phase 1: Gap Scan (per-document, parallel)")
        self._state.current_phase = Phase.GAP_SCAN.value
        self._state.get_budget().start_timer()

        doc_groups = self._state.group_rows_by_doc(Phase.GAP_SCAN)
        if not doc_groups:
            self._notify_phase_complete(Phase.GAP_SCAN)
            self._advance_global_phase(Phase.CHECKLIST_VERIFY)
            return

        if self._budget_exceeded():
            self._notify_phase_complete(Phase.GAP_SCAN)
            self._advance_global_phase(Phase.CHECKLIST_VERIFY)
            return

        import concurrent.futures

        max_workers = min(self._compute_max_workers(8), len(doc_groups))
        total_docs = len(doc_groups)
        docs_completed = 0

        def _scan_single_doc(doc_id: str, rows: list) -> tuple:
            result = run_gap_scan_document(
                doc_id=doc_id,
                rows=rows,
                state=self._state,
                llm_completion_fn=self._llm_fn,
                model=self._model,
                run_id=self._state.run_id,
                lang=self._lang,
            )
            return (doc_id, rows, result)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_scan_single_doc, doc_id, rows): doc_id
                for doc_id, rows in doc_groups.items()
            }
            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    _, rows, result = future.result()
                    with self._state_lock:
                        docs_completed += 1
                        if self._phase1_doc_callback:
                            try:
                                self._phase1_doc_callback(docs_completed, total_docs, doc_id)
                            except Exception:
                                pass
                        for row in rows:
                            row.set_phase_result(Phase.GAP_SCAN, result)
                            if result.status in (
                                PhaseStatus.COMPLETED.value,
                                PhaseStatus.SKIPPED.value,
                            ):
                                row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()
                except Exception as e:
                    logger.error(f"Phase 1 failed for doc {doc_id}: {e}")

        # Retry once for docs that failed due to transient LLM errors
        self.retry_failed_phase1_docs()
        self._notify_phase_complete(Phase.GAP_SCAN)
        self._advance_global_phase(Phase.CHECKLIST_VERIFY)

    def retry_failed_phase1_docs(self) -> int:
        """Retry Phase 1 for docs that failed due to transient LLM errors.

        Finds rows where current_phase == gap_scan AND
        phase_results['gap_scan']['status'] == 'failed'.
        Re-runs run_gap_scan_document() once for each failed doc group.
        On success, advances rows to the next phase.

        Returns:
            Number of docs successfully recovered.
        """
        import concurrent.futures as _cf
        from src.analysis.gap_scanner import run_gap_scan_document

        all_rows = self._state.get_all_rows()
        failed_rows = [
            r for r in all_rows
            if r.current_phase == Phase.GAP_SCAN.value
            and r.phase_results.get(Phase.GAP_SCAN.value, {}).get("status")
            == PhaseStatus.FAILED.value
        ]
        if not failed_rows:
            return 0

        doc_groups: dict[str, list] = {}
        for row in failed_rows:
            doc_groups.setdefault(row.doc_id, []).append(row)

        logger.info(
            "retry_failed_phase1_docs: retrying %d docs (%d rows)",
            len(doc_groups), len(failed_rows),
        )

        max_workers = min(self._compute_max_workers(8), len(doc_groups))
        success_count = 0

        def _retry_single(doc_id: str, rows: list) -> tuple:
            result = run_gap_scan_document(
                doc_id=doc_id,
                rows=rows,
                state=self._state,
                llm_completion_fn=self._llm_fn,
                model=self._model,
                run_id=self._state.run_id,
                lang=self._lang,
            )
            return (doc_id, rows, result)

        with _cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_retry_single, doc_id, rows): doc_id
                for doc_id, rows in doc_groups.items()
            }
            for future in _cf.as_completed(futures):
                doc_id = futures[future]
                try:
                    _, rows, result = future.result()
                    with self._state_lock:
                        recovered = 0
                        for row in rows:
                            row.set_phase_result(Phase.GAP_SCAN, result)
                            if result.status in (
                                PhaseStatus.COMPLETED.value,
                                PhaseStatus.SKIPPED.value,
                            ):
                                row.advance_to_next_phase()
                                recovered += 1
                            self._state.update_row(row)
                        success_count += min(1, recovered)
                        self._save_state()
                except Exception as e:
                    logger.error(
                        "retry_failed_phase1_docs: doc %s failed again: %s", doc_id, e
                    )

        logger.info(
            "retry_failed_phase1_docs: %d/%d docs recovered",
            success_count, len(doc_groups),
        )
        return success_count

    def _execute_phase_2(self) -> None:
        """Phase 2: Checklist Verification (LLM) — per-document grouping, parallelized."""
        logger.info(
            "Executing Phase 2: Checklist Verification (per-document, parallel)"
        )
        self._state.current_phase = Phase.CHECKLIST_VERIFY.value

        doc_groups = self._state.group_rows_by_doc(Phase.CHECKLIST_VERIFY)
        if not doc_groups:
            self._notify_phase_complete(Phase.CHECKLIST_VERIFY)
            self._advance_global_phase(Phase.RISK_ASSESSMENT)
            return

        if self._budget_exceeded():
            self._notify_phase_complete(Phase.CHECKLIST_VERIFY)
            self._advance_global_phase(Phase.RISK_ASSESSMENT)
            return

        import concurrent.futures

        max_workers = min(self._compute_max_workers(4), len(doc_groups))

        def _verify_single_doc(doc_id: str, rows: list) -> tuple:
            result = run_checklist_verify_document(
                doc_id=doc_id,
                rows=rows,
                state=self._state,
                llm_completion_fn=self._llm_fn,
                model=self._model,
                run_id=self._state.run_id,
                lang=self._lang,
            )
            return (doc_id, rows, result)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_verify_single_doc, doc_id, rows): doc_id
                for doc_id, rows in doc_groups.items()
            }
            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    _, rows, result = future.result()
                    with self._state_lock:
                        for row in rows:
                            row.set_phase_result(Phase.CHECKLIST_VERIFY, result)
                            if result.status in (
                                PhaseStatus.COMPLETED.value,
                                PhaseStatus.SKIPPED.value,
                            ):
                                row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()
                except Exception as e:
                    logger.error(f"Phase 2 failed for doc {doc_id}: {e}")
                    with self._state_lock:
                        for row in doc_groups.get(doc_id, []):
                            failed = PhaseResult(phase=Phase.CHECKLIST_VERIFY.value, status=PhaseStatus.FAILED.value, error=str(e))
                            row.set_phase_result(Phase.CHECKLIST_VERIFY, failed)
                            row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()

        self._notify_phase_complete(Phase.CHECKLIST_VERIFY)
        self._advance_global_phase(Phase.RISK_ASSESSMENT)

    def _execute_phase_3(self) -> None:
        """Phase 3: Risk Assessment (rule engine, no LLM)."""
        logger.info("Executing Phase 3: Risk Assessment")
        self._state.current_phase = Phase.RISK_ASSESSMENT.value

        run_id = getattr(self._state, "run_id", None)

        # Group rows by document for SSE events (mirrors P4 pattern)
        doc_groups = self._state.group_rows_by_doc(Phase.RISK_ASSESSMENT)
        for doc_id, rows in doc_groups.items():
            doc_title = (
                rows[0].doc_title if rows and hasattr(rows[0], "doc_title") else ""
            )
            clause_ids = [r.clause_id for r in rows if hasattr(r, "clause_id")]

            # SSE: phase_3_start
            _emit_phase3_event(
                run_id,
                {
                    "type": "phase_3_start",
                    "phase": "risk_assessment",
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "clause_ids": clause_ids,
                    "clause_count": len(rows),
                },
            )

            try:
                for row in rows:
                    _run_risk_assessment_row(row)
                    if row.get_phase_result(Phase.RISK_ASSESSMENT):
                        result = row.get_phase_result(Phase.RISK_ASSESSMENT)
                        if result and result.status == PhaseStatus.COMPLETED.value:
                            row.advance_to_next_phase()
                    self._state.update_row(row)

                # Collect results for SSE emit
                completed_results = []
                for row in rows:
                    pr = row.get_phase_result(Phase.RISK_ASSESSMENT)
                    if pr and pr.output:
                        completed_results.append(
                            {
                                "clause_id": getattr(row, "clause_id", ""),
                                "gap_severity": pr.output.get("gap_severity", ""),
                                "risk_level": pr.output.get("risk_level", ""),
                                "verdict": pr.output.get("verdict", ""),
                                "evidence_stats": pr.output.get("evidence_stats", {}),
                            }
                        )

                # SSE: phase_3_result
                _emit_phase3_event(
                    run_id,
                    {
                        "type": "phase_3_result",
                        "phase": "risk_assessment",
                        "doc_id": doc_id,
                        "doc_title": doc_title,
                        "clause_ids": clause_ids,
                        "risk_details": completed_results,
                        "clause_count": len(rows),
                    },
                )

            except Exception as e:
                # SSE: phase_3_error
                _emit_phase3_event(
                    run_id,
                    {
                        "type": "phase_3_error",
                        "phase": "risk_assessment",
                        "doc_id": doc_id,
                        "error": str(e)[:500],
                    },
                )

            self._save_state()

        self._notify_phase_complete(Phase.RISK_ASSESSMENT)
        self._advance_global_phase(Phase.REMEDIATION)
        self._save_state()

    def _execute_phase_4(self) -> None:
        """Phase 4: Remediation Suggestions (LLM) — per-document grouping, parallelized."""
        logger.info(
            "Executing Phase 4: Remediation Suggestions (per-document, parallel)"
        )
        self._state.current_phase = Phase.REMEDIATION.value

        doc_groups = self._state.group_rows_by_doc(Phase.REMEDIATION)
        if not doc_groups:
            self._notify_phase_complete(Phase.REMEDIATION)
            self._advance_global_phase(Phase.VERIFICATION)
            return

        if self._budget_exceeded():
            self._notify_phase_complete(Phase.REMEDIATION)
            self._advance_global_phase(Phase.VERIFICATION)
            return

        import concurrent.futures

        max_workers = min(self._compute_max_workers(4), len(doc_groups))

        def _remediate_single_doc(doc_id: str, rows: list) -> tuple:
            result = run_remediation_document(
                doc_id=doc_id,
                rows=rows,
                state=self._state,
                llm_completion_fn=self._llm_fn,
                model=self._model,
                run_id=self._state.run_id,
                lang=self._lang,
            )
            return (doc_id, rows, result)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_remediate_single_doc, doc_id, rows): doc_id
                for doc_id, rows in doc_groups.items()
            }
            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    _, rows, result = future.result()
                    with self._state_lock:
                        for row in rows:
                            row.set_phase_result(Phase.REMEDIATION, result)
                            if result.status in (
                                PhaseStatus.COMPLETED.value,
                                PhaseStatus.SKIPPED.value,
                            ):
                                row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()
                except Exception as e:
                    logger.error(f"Phase 4 failed for doc {doc_id}: {e}")
                    with self._state_lock:
                        for row in doc_groups.get(doc_id, []):
                            failed = PhaseResult(phase=Phase.REMEDIATION.value, status=PhaseStatus.FAILED.value, error=str(e))
                            row.set_phase_result(Phase.REMEDIATION, failed)
                            row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()

        self._notify_phase_complete(Phase.REMEDIATION)
        self._advance_global_phase(Phase.VERIFICATION)

    def _execute_phase_5(self) -> None:
        """Phase 5: Independent Verification / Cross-examination (LLM) — per-document grouping.

        Parallelized: multiple document groups are processed concurrently via ThreadPoolExecutor.
        """
        logger.info(
            "Executing Phase 5: Independent Verification (per-document, parallel)"
        )
        self._state.current_phase = Phase.VERIFICATION.value

        doc_groups = self._state.group_rows_by_doc(Phase.VERIFICATION)

        if not doc_groups:
            self._notify_phase_complete(Phase.VERIFICATION)
            self._advance_global_phase(Phase.SOURCE_CHECK)
            return

        # Pre-flight budget check
        if self._budget_exceeded():
            logger.info("Phase 5 skipped: budget exceeded before start")
            self._notify_phase_complete(Phase.VERIFICATION)
            self._advance_global_phase(Phase.SOURCE_CHECK)
            return

        import concurrent.futures

        # Limit concurrency to avoid overwhelming LLM API
        max_workers = min(self._compute_max_workers(4), len(doc_groups))

        def _verify_single_doc(doc_id: str, rows: list) -> tuple:
            """Process one document group. Returns (doc_id, rows, result)."""
            result = run_verification_document(
                doc_id=doc_id,
                rows=rows,
                state=self._state,
                llm_completion_fn=self._llm_fn,
                model=self._model,
                selected_regulations=self._selected_regulations,
                run_id=self._state.run_id,
                lang=self._lang,
            )
            return (doc_id, rows, result)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_verify_single_doc, doc_id, rows): doc_id
                for doc_id, rows in doc_groups.items()
            }

            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    _, rows, result = future.result()
                    with self._state_lock:
                        for row in rows:
                            row.set_phase_result(Phase.VERIFICATION, result)
                            if result.status in (
                                PhaseStatus.COMPLETED.value,
                                PhaseStatus.SKIPPED.value,
                            ):
                                row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()

                    for row in rows:
                        if (
                            self._on_row_complete
                            and row.overall_status == PhaseStatus.COMPLETED.value
                        ):
                            self._on_row_complete(row, self._state)
                except Exception as e:
                    logger.error(f"Phase 5 failed for doc {doc_id}: {e}")
                    with self._state_lock:
                        for row in doc_groups.get(doc_id, []):
                            failed = PhaseResult(phase=Phase.VERIFICATION.value, status=PhaseStatus.FAILED.value, error=str(e))
                            row.set_phase_result(Phase.VERIFICATION, failed)
                            row.advance_to_next_phase()
                            self._state.update_row(row)
                        self._save_state()

        # ── Step 2: Third-party QA audit of all completed debates ──
        logger.info(
            "Phase 5 Step 2: Running third-party QA audit on debate transcripts"
        )
        try:
            from src.analysis.verifier import run_qa_audit_document

            qa_audit_results = {}
            verified_doc_groups = {}
            for doc_id, rows in doc_groups.items():
                refreshed_rows = []
                for row in rows:
                    updated = self._state.get_row(row.row_id)
                    if updated:
                        refreshed_rows.append(updated)
                    else:
                        refreshed_rows.append(row)
                if any(
                    getattr(r, "verification_rounds", None)
                    and len(r.verification_rounds) > 0
                    for r in refreshed_rows
                ):
                    verified_doc_groups[doc_id] = refreshed_rows

            if verified_doc_groups and not self._budget_exceeded():
                qa_max_workers = min(self._compute_max_workers(4), len(verified_doc_groups))
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=qa_max_workers
                ) as qa_executor:
                    qa_futures = {
                        qa_executor.submit(
                            run_qa_audit_document,
                            doc_id=did,
                            rows=drows,
                            state=self._state,
                            llm_completion_fn=self._llm_fn,
                            model=self._model,
                            selected_regulations=self._selected_regulations,
                            run_id=self._state.run_id,
                            lang=self._lang,
                        ): did
                        for did, drows in verified_doc_groups.items()
                    }
                    for future in concurrent.futures.as_completed(qa_futures):
                        did = qa_futures[future]
                        try:
                            qa_result = future.result()
                            qa_audit_results[did] = qa_result
                            with self._state_lock:
                                for drow in verified_doc_groups[did]:
                                    self._state.update_row(drow)
                                self._save_state()
                        except Exception as qa_e:
                            logger.error(
                                f"Phase 5 Step 2 QA audit failed for doc {did}: {qa_e}"
                            )

                with self._state_lock:
                    self._state.qa_audit_summary = {
                        "total_documents": len(qa_audit_results),
                        "document_scores": {
                            did: r.get("overall_score", 0)
                            for did, r in qa_audit_results.items()
                        },
                        "avg_score": (
                            sum(
                                r.get("overall_score", 0)
                                for r in qa_audit_results.values()
                            )
                            / max(1, len(qa_audit_results))
                        ),
                        "details": qa_audit_results,
                    }
                    self._save_state()

            logger.info(
                f"Phase 5 Step 2 complete: {len(qa_audit_results)} documents audited"
            )
        except Exception as qa_global_err:
            logger.error(f"Phase 5 Step 2 failed globally: {qa_global_err}")

        self._notify_phase_complete(Phase.VERIFICATION)
        self._advance_global_phase(Phase.SOURCE_CHECK)

    def _execute_phase_6(self) -> None:
        """Phase 6: Source Verification (HTTP batch)."""
        logger.info("Executing Phase 6: Source Verification")
        self._state.current_phase = Phase.SOURCE_CHECK.value

        result = run_source_check(self._state, lang=self._lang)

        # Phase 6 is global (not per-row), so advance all rows that are
        # still at SOURCE_CHECK — this marks them COMPLETED and makes
        # progress_percent reach 100%.
        with self._state_lock:
            for row in self._state.get_all_rows():
                if row.current_phase == Phase.SOURCE_CHECK.value:
                    row.advance_to_next_phase()
                    self._state.update_row(row)

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
            result = run_gap_scan_row(
                row, self._state, self._llm_fn, self._model, lang=self._lang
            )
            row.set_phase_result(Phase.GAP_SCAN, result)
            if result.status == PhaseStatus.COMPLETED.value:
                row.advance_to_next_phase()

        elif phase == Phase.CHECKLIST_VERIFY:
            result = run_checklist_verify_row(
                row, self._state, self._llm_fn, self._model, lang=self._lang
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
            result = run_remediation_row(
                row, self._state, self._llm_fn, self._model, lang=self._lang
            )
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
                lang=self._lang,
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
        """Check if a phase should be skipped in current mode or by custom config.

        RISK_ONLY mode only runs: Phase 0, 0.5, 1, 3.
        Custom skip: user-selected phases stored in state.skipped_phases.
        """
        if phase.value in self._state.skipped_phases:
            return True
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

    def _check_all_evidence_missing(self) -> bool:
        """Post-Phase 1 sanity check: if ALL evidence items are 'not found',
        something is likely wrong (bad model, empty docs, prompt failure).

        Auto-pauses the pipeline so the user can investigate rather than
        wasting LLM tokens on subsequent phases that will produce empty results.

        Returns True if pipeline was paused.
        """
        from src.analysis.state import EvidenceItem

        rows = self._state.get_all_rows()
        rows_with_evidence = [r for r in rows if r.evidence_items]

        if not rows_with_evidence:
            # No evidence items at all — Phase 1 may have been skipped entirely
            return False

        total_items = 0
        found_items = 0
        for r in rows_with_evidence:
            for e_dict in r.evidence_items:
                total_items += 1
                ei = EvidenceItem.from_dict(e_dict)
                if ei.found:
                    found_items += 1

        if total_items == 0:
            return False

        if found_items == 0:
            logger.warning(
                "Phase 1 sanity check FAILED: 0/%d evidence items found across "
                "%d rows — auto-pausing. Possible causes: wrong model, empty docs, "
                "LLM prompt failure.",
                total_items,
                len(rows_with_evidence),
            )
            self.pause(PauseReason.ALL_EVIDENCE_MISSING)
            return True

        # Also warn (but don't pause) if found ratio is extremely low (< 5%)
        found_ratio = found_items / total_items
        if found_ratio < 0.05:
            logger.warning(
                "Phase 1 sanity check WARNING: only %d/%d (%.1f%%) evidence items found. "
                "Results may be unreliable.",
                found_items,
                total_items,
                found_ratio * 100,
            )

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
