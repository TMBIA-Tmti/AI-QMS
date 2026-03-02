"""
AI-QMS — Analysis Pipeline Module
==================================

Multi-step, verifiable, traceable compliance analysis pipeline.
Replaces the one-shot LLM black-box with a structured Phase 0→6 pipeline.

Modules:
  - state:              Core data structures (PipelineState, RowState, etc.)
  - compliance_rules:   Predefined audit checklist (71 ISO 13485 clauses)
  - risk_matrix:        Deterministic risk engine (audit_impact × gap_severity)
  - comparison_table:   One big comparison table storage + querying
  - data_quality:       Phase 0 — Data Quality Gate
  - reference_mapper:   Phase 0.5 — Reference Mapping
  - gap_scanner:        Phase 1 — Gap Scan (LLM #1)
  - checklist_verifier: Phase 2 — Checklist Verification (LLM #2)
  - remediation:        Phase 4 — Remediation Suggestions (LLM #3)
  - verifier:           Phase 5 — Cross-Examination (LLM #4)
  - source_checker:     Phase 6 — Source Verification (HTTP)
  - pipeline:           Orchestrator (mode switching, pause/resume, budget)
"""

# State & types
from src.analysis.state import (
    Phase,
    PhaseStatus,
    ExecutionMode,
    PauseReason,
    PhaseResult,
    EvidenceItem,
    RowState,
    PipelineState,
    LLMBudget,
    PHASE_ORDER,
)

# Rules & risk
from src.analysis.compliance_rules import get_checklist, list_clauses
from src.analysis.risk_matrix import (
    RiskLevel,
    GapSeverity,
    AuditImpact,
    Verdict,
    assess_risk,
    determine_gap_severity,
    risk_to_verdict,
    RISK_MATRIX,
    RISK_LEVEL_DISPLAY,
    VERDICT_DISPLAY,
)

# Comparison table
from src.analysis.comparison_table import ComparisonTable, build_initial_rows

# Phase modules
from src.analysis.data_quality import run_data_quality_gate, DataQualityResult
from src.analysis.reference_mapper import run_reference_mapping
from src.analysis.gap_scanner import run_gap_scan_row
from src.analysis.checklist_verifier import run_checklist_verify_row
from src.analysis.remediation import run_remediation_row
from src.analysis.verifier import run_verification_row, MAX_VERIFICATION_ROUNDS
from src.analysis.source_checker import run_source_check, verify_url

# Pipeline orchestrator
from src.analysis.pipeline import AnalysisPipeline
from src.analysis.pipeline_runner import run_pipeline_analysis, PipelineRunResult

# Report API (Phase D)
from src.analysis.report_api import report_router

__all__ = [
    # State & types
    "Phase",
    "PhaseStatus",
    "ExecutionMode",
    "PauseReason",
    "PhaseResult",
    "EvidenceItem",
    "RowState",
    "PipelineState",
    "LLMBudget",
    "PHASE_ORDER",
    # Rules & risk
    "get_checklist",
    "list_clauses",
    "RiskLevel",
    "GapSeverity",
    "AuditImpact",
    "Verdict",
    "assess_risk",
    "determine_gap_severity",
    "risk_to_verdict",
    "RISK_MATRIX",
    "RISK_LEVEL_DISPLAY",
    "VERDICT_DISPLAY",
    # Comparison table
    "ComparisonTable",
    "build_initial_rows",
    # Phase modules
    "run_data_quality_gate",
    "DataQualityResult",
    "run_reference_mapping",
    "run_gap_scan_row",
    "run_checklist_verify_row",
    "run_remediation_row",
    "run_verification_row",
    "MAX_VERIFICATION_ROUNDS",
    "run_source_check",
    "verify_url",
    # Pipeline
    "AnalysisPipeline",
    "run_pipeline_analysis",
    "PipelineRunResult",
    # Report API
    "report_router",
]
