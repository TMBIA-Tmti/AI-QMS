"""
AI-QMS — Pipeline State Management
===================================

Defines the core data structures for the multi-step analysis pipeline:

- PhaseResult: Output of a single phase for a single row
- RowState: Tracks one {clause_id × doc_id} pair through all phases
- PipelineState: Top-level state for the entire pipeline run

All structures are JSON-serializable for persistence and crash recovery.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


__all__ = [
    "Phase",
    "PhaseStatus",
    "ExecutionMode",
    "PauseReason",
    "PhaseResult",
    "EvidenceItem",
    "RowState",
    "PipelineState",
    "LLMBudget",
]


# ============================================================
# Enums
# ============================================================


class Phase(str, Enum):
    """Pipeline phases in execution order."""

    DATA_QUALITY = "phase_0"
    REFERENCE_MAPPING = "phase_0_5"
    GAP_SCAN = "phase_1"
    CHECKLIST_VERIFY = "phase_2"
    RISK_ASSESSMENT = "phase_3"
    REMEDIATION = "phase_4"
    VERIFICATION = "phase_5"
    SOURCE_CHECK = "phase_6"

    @property
    def display_name(self) -> str:
        _names = {
            "phase_0": "資料品質檢查",
            "phase_0_5": "法規參照對應",
            "phase_1": "差距掃描",
            "phase_2": "查核表驗證",
            "phase_3": "風險評估",
            "phase_4": "改善建議",
            "phase_5": "獨立驗證",
            "phase_6": "來源驗證",
        }
        return _names.get(self.value, self.value)

    @property
    def display_name_en(self) -> str:
        _names = {
            "phase_0": "Data Quality Gate",
            "phase_0_5": "Reference Mapping",
            "phase_1": "Gap Scan",
            "phase_2": "Checklist Verification",
            "phase_3": "Risk Assessment",
            "phase_4": "Remediation Suggestions",
            "phase_5": "Independent Verification",
            "phase_6": "Source Verification",
        }
        return _names.get(self.value, self.value)

    @property
    def uses_llm(self) -> bool:
        """Whether this phase requires an LLM call."""
        return self in (
            Phase.GAP_SCAN,
            Phase.CHECKLIST_VERIFY,
            Phase.REMEDIATION,
            Phase.VERIFICATION,
        )


# Ordered list for iteration
PHASE_ORDER: list[Phase] = [
    Phase.DATA_QUALITY,
    Phase.REFERENCE_MAPPING,
    Phase.GAP_SCAN,
    Phase.CHECKLIST_VERIFY,
    Phase.RISK_ASSESSMENT,
    Phase.REMEDIATION,
    Phase.VERIFICATION,
    Phase.SOURCE_CHECK,
]


class PhaseStatus(str, Enum):
    """Status of a phase for a specific row."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"  # e.g. Phase 4 skipped when no gaps
    FAILED = "failed"
    PAUSED = "paused"


class ExecutionMode(str, Enum):
    """Pipeline execution mode — switchable at any time."""

    STEP_BY_STEP = "step_by_step"  # 🔍 Manual: pause after each phase
    AUTO_RUN = "auto_run"  # 🚀 Auto: run all, pause on critical only
    RISK_ONLY = "risk_only"  # ⚡ Fast: Phase 0 + 0.5 + 1 + 3 only


class PauseReason(str, Enum):
    """Reasons for auto-pause in auto mode."""

    CRITICAL_GAP = "critical_gap"  # 🔴 Critical risk gap found
    EVIDENCE_CONFLICT = "evidence_conflict"  # Analyzer/Verifier disagree after 3 rounds
    LLM_BUDGET_EXCEEDED = "llm_budget_exceeded"  # Token budget hit
    USER_REQUESTED = "user_requested"  # Manual pause
    STEP_MODE_COMPLETE = "step_mode_complete"  # Step-by-step phase done
    ALL_EVIDENCE_MISSING = "all_evidence_missing"  # Phase 1 found zero evidence across all rows


# ============================================================
# Data structures
# ============================================================


@dataclass
class EvidenceItem:
    """One piece of evidence found (or not found) for an expected_evidence entry.

    Each expected_evidence item in compliance_rules.py produces one EvidenceItem.
    """

    evidence_name: str  # From compliance_rules expected_evidence list
    found: bool = False
    source_doc_id: Optional[str] = None  # Which QMS document
    source_section: Optional[str] = None  # Section heading in the document
    source_quote: Optional[str] = None  # Exact quoted text (for traceability)
    relevance_score: Optional[float] = None  # 0.0-1.0, from LLM structured output
    is_inadequate: bool = False  # Content exists but doesn't cover the requirement
    is_outdated: bool = False  # Document version is outdated
    llm_reasoning: Optional[str] = None  # LLM's explanation (for transparency)

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PhaseResult:
    """Output of a single phase for a single row.

    Stored incrementally — each phase appends its result to the row.
    """

    phase: str  # Phase.value
    status: str = PhaseStatus.PENDING.value
    started_at: Optional[float] = None  # time.time()
    completed_at: Optional[float] = None
    error: Optional[str] = None

    # Phase-specific output (varies by phase)
    output: dict = field(default_factory=dict)

    # LLM usage tracking (only for LLM phases)
    llm_usage: Optional[dict] = (
        None  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    )
    llm_model: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return round(self.completed_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_seconds"] = self.duration_seconds
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PhaseResult":
        data.pop("duration_seconds", None)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RowState:
    """State for one comparison row: {clause_id × doc_id}.

    Each row goes through Phase 0→6 independently.
    Phase results are accumulated as the pipeline progresses.
    """

    # Identity
    row_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    clause_id: str = ""  # e.g. "4.2.3"
    standard: str = ""  # e.g. "ISO_13485"
    doc_id: str = ""  # e.g. "QP-001"
    doc_title: str = ""

    # Clause info (copied from compliance_rules for convenience)
    clause_title: str = ""
    audit_impact: str = ""  # "critical" | "major" | "minor"
    audit_question: str = ""
    expected_evidence: list[str] = field(default_factory=list)

    # Current phase tracking
    current_phase: str = Phase.DATA_QUALITY.value
    overall_status: str = PhaseStatus.PENDING.value

    # Phase results (accumulated)
    phase_results: dict[str, dict] = field(default_factory=dict)
    # key = Phase.value, value = PhaseResult.to_dict()

    # Evidence items (populated in Phase 1, refined in Phase 2)
    evidence_items: list[dict] = field(default_factory=list)

    # Risk assessment results (populated in Phase 3)
    gap_severity: Optional[str] = None
    risk_level: Optional[str] = None
    verdict: Optional[str] = None

    # Cross-examination (Phase 5)
    verification_rounds: list[dict] = field(default_factory=list)
    verification_agreed: Optional[bool] = None  # None = not yet verified
    flagged_for_ra: bool = False  # True if 3 rounds and still disagreeing

    # Remediation (Phase 4)
    remediation_suggestion: Optional[str] = None
    remediation_regulation_cite: Optional[str] = None

    # RA modifications (post-hoc)
    ra_override: Optional[dict] = None  # {verdict, reason, by, at}
    ra_notes: Optional[str] = None  # Permanent clause notes
    version_history: list[dict] = field(default_factory=list)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def set_phase_result(self, phase: Phase, result: PhaseResult) -> None:
        """Store a phase result and advance current_phase."""
        self.phase_results[phase.value] = result.to_dict()
        self.updated_at = time.time()

    def get_phase_result(self, phase: Phase) -> Optional[PhaseResult]:
        """Retrieve a stored phase result."""
        data = self.phase_results.get(phase.value)
        if data is None:
            return None
        return PhaseResult.from_dict(data)

    def advance_to_next_phase(self) -> Optional[Phase]:
        """Move current_phase to the next in order. Returns the new phase or None if done."""
        try:
            current = Phase(self.current_phase)
            idx = PHASE_ORDER.index(current)
            if idx + 1 < len(PHASE_ORDER):
                next_phase = PHASE_ORDER[idx + 1]
                self.current_phase = next_phase.value
                self.updated_at = time.time()
                return next_phase
            else:
                self.overall_status = PhaseStatus.COMPLETED.value
                self.updated_at = time.time()
                return None
        except (ValueError, IndexError):
            return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RowState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LLMBudget:
    """Tracks LLM token usage against a configurable upper limit."""

    max_total_tokens: int = 500_000  # Default upper limit
    max_time_seconds: int = 600  # Default 10 minute time limit
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    calls_made: int = 0
    start_time: float = 0.0  # Set when pipeline starts

    def __post_init__(self):
        import time
        if self.start_time == 0.0:
            self.start_time = time.time()

    def start_timer(self):
        """Reset the start time for time-based budget tracking."""
        import time
        self.start_time = time.time()

    @property
    def total_tokens_used(self) -> int:
        return self.prompt_tokens_used + self.completion_tokens_used

    @property
    def remaining(self) -> int:
        return max(0, self.max_total_tokens - self.total_tokens_used)

    @property
    def exceeded(self) -> bool:
        import time
        token_exceeded = self.total_tokens_used >= self.max_total_tokens
        time_exceeded = (time.time() - self.start_time) >= self.max_time_seconds if self.start_time > 0 else False
        return token_exceeded or time_exceeded

    @property
    def usage_percent(self) -> float:
        if self.max_total_tokens <= 0:
            return 100.0
        return round((self.total_tokens_used / self.max_total_tokens) * 100, 1)

    def record_usage(self, usage: dict) -> None:
        """Record LLM usage from a completion response."""
        self.prompt_tokens_used += usage.get("prompt_tokens", 0)
        self.completion_tokens_used += usage.get("completion_tokens", 0)
        self.calls_made += 1

    def to_dict(self) -> dict:
        return {
            "max_total_tokens": self.max_total_tokens,
            "max_time_seconds": self.max_time_seconds,
            "prompt_tokens_used": self.prompt_tokens_used,
            "completion_tokens_used": self.completion_tokens_used,
            "total_tokens_used": self.total_tokens_used,
            "remaining": self.remaining,
            "exceeded": self.exceeded,
            "usage_percent": self.usage_percent,
            "calls_made": self.calls_made,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LLMBudget":
        return cls(
            max_total_tokens=data.get("max_total_tokens", 500_000),
            max_time_seconds=data.get("max_time_seconds", 600),
            prompt_tokens_used=data.get("prompt_tokens_used", 0),
            completion_tokens_used=data.get("completion_tokens_used", 0),
            calls_made=data.get("calls_made", 0),
        )


@dataclass
class PipelineState:
    """Top-level state for an entire pipeline run.

    Serializable to JSON for crash recovery and persistence.
    """

    # Identity
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Configuration
    mode: str = ExecutionMode.AUTO_RUN.value
    standard: str = "ISO_13485"  # Which standard is being analyzed
    source_command: str = "regulatory_list"  # "regulatory_list" or "regulatory_update"

    # Status
    status: str = PhaseStatus.PENDING.value  # Overall pipeline status
    current_phase: str = Phase.DATA_QUALITY.value  # Current global phase
    pause_reason: Optional[str] = None
    error: Optional[str] = None

    # Rows
    rows: dict[str, dict] = field(default_factory=dict)
    # key = row_id, value = RowState.to_dict()

    # LLM Budget
    llm_budget: dict = field(default_factory=lambda: LLMBudget().to_dict())

    # Data quality summary (Phase 0 output)
    data_quality_summary: Optional[dict] = None

    # Source verification summary (Phase 6 output)
    source_check_summary: Optional[dict] = None

    # Product docs paths (temporary, deleted after report)
    product_doc_paths: list[str] = field(default_factory=list)

    # Custom phase skip configuration (user-selected phases to skip)
    skipped_phases: list[str] = field(default_factory=list)

    # Selected regulations for multi-regulation cross-exam (persisted for restart recovery)
    selected_regulations: list[str] = field(default_factory=list)

    # Completion
    completed_at: Optional[float] = None

    # ---- Row management ----

    def add_row(self, row: RowState) -> None:
        """Add a row to the pipeline."""
        self.rows[row.row_id] = row.to_dict()
        self.updated_at = time.time()

    def get_row(self, row_id: str) -> Optional[RowState]:
        """Retrieve a row by ID."""
        data = self.rows.get(row_id)
        if data is None:
            return None
        return RowState.from_dict(data)

    def update_row(self, row: RowState) -> None:
        """Update a row in the pipeline (replace)."""
        self.rows[row.row_id] = row.to_dict()
        self.updated_at = time.time()

    def get_all_rows(self) -> list[RowState]:
        """Return all rows as RowState objects."""
        return [RowState.from_dict(d) for d in self.rows.values()]

    def get_rows_by_phase(self, phase: Phase) -> list[RowState]:
        """Return rows currently at a specific phase."""
        return [
            RowState.from_dict(d)
            for d in self.rows.values()
            if d.get("current_phase") == phase.value
        ]

    def get_rows_by_verdict(self, verdict: str) -> list[RowState]:
        """Return rows with a specific verdict."""
        return [
            RowState.from_dict(d)
            for d in self.rows.values()
            if d.get("verdict") == verdict
        ]

    def get_rows_by_doc(self, doc_id: str) -> list[RowState]:
        """Return all rows for a specific document."""
        return [
            RowState.from_dict(d)
            for d in self.rows.values()
            if d.get("doc_id") == doc_id
        ]

    def get_unique_doc_ids(self) -> list[str]:
        """Return unique doc_ids from all rows, preserving insertion order."""
        seen: set[str] = set()
        result: list[str] = []
        for d in self.rows.values():
            did = d.get("doc_id", "")
            if did and did not in seen:
                seen.add(did)
                result.append(did)
        return result

    def group_rows_by_doc(self, phase: Phase) -> dict[str, list[RowState]]:
        """Group rows at a specific phase by their doc_id."""
        groups: dict[str, list[RowState]] = {}
        for row in self.get_rows_by_phase(phase):
            groups.setdefault(row.doc_id, []).append(row)
        return groups

    # ---- Budget ----

    def get_budget(self) -> LLMBudget:
        return LLMBudget.from_dict(self.llm_budget)

    def update_budget(self, budget: LLMBudget) -> None:
        self.llm_budget = budget.to_dict()
        self.updated_at = time.time()

    # ---- Mode switching ----

    def set_mode(self, mode: ExecutionMode) -> None:
        """Switch execution mode (allowed at any time)."""
        self.mode = mode.value
        self.updated_at = time.time()

    # ---- Pause/Resume ----

    def pause(self, reason: PauseReason) -> None:
        """Pause the pipeline."""
        self.status = PhaseStatus.PAUSED.value
        self.pause_reason = reason.value
        self.updated_at = time.time()

    def resume(self) -> None:
        """Resume the pipeline."""
        self.status = PhaseStatus.RUNNING.value
        self.pause_reason = None
        self.updated_at = time.time()

    # ---- Progress ----

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def completed_rows(self) -> int:
        return sum(
            1
            for d in self.rows.values()
            if d.get("overall_status") == PhaseStatus.COMPLETED.value
        )

    @property
    def progress_percent(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round((self.completed_rows / self.total_rows) * 100, 1)

    def progress_summary(self) -> dict:
        """Return a summary of pipeline progress."""
        budget = self.get_budget()
        phase_counts: dict[str, int] = {}
        verdict_counts: dict[str, int] = {}
        for d in self.rows.values():
            cp = d.get("current_phase", "unknown")
            phase_counts[cp] = phase_counts.get(cp, 0) + 1
            v = d.get("verdict")
            if v:
                verdict_counts[v] = verdict_counts.get(v, 0) + 1

        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "status": self.status,
            "total_rows": self.total_rows,
            "completed_rows": self.completed_rows,
            "progress_percent": self.progress_percent,
            "current_phase": self.current_phase,
            "phase_distribution": phase_counts,
            "verdict_distribution": verdict_counts,
            "llm_budget": budget.to_dict(),
            "pause_reason": self.pause_reason,
        }

    # ---- Serialization ----

    def to_dict(self) -> dict:
        d = asdict(self)
        # Include @property values that asdict() doesn't serialize
        d["total_rows"] = self.total_rows
        d["completed_rows"] = self.completed_rows
        d["progress_percent"] = self.progress_percent
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "PipelineState":
        return cls.from_dict(json.loads(json_str))

    def save(self, path: Path) -> None:
        """Persist pipeline state to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)  # Atomic write

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        """Load pipeline state from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)
