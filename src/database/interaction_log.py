"""
AI-QMS — LLM Interaction Log
==============================

Captures and persists ALL LLM interactions from every pipeline phase,
enabling the deep analysis report to include full prompt/response data.

Each pipeline run gets its own interaction log file:
  data/interaction_logs/{run_id}_interactions.json

Unlike SSE events (which truncate responses to 2000 chars and are ephemeral),
this log captures FULL prompts and responses for offline review.

Phases captured:
  - Phase 1: Gap Scan (evidence search)
  - Phase 2: Checklist Verification
  - Phase 4: Remediation Suggestions
  - Phase 5: Cross-Examination (all rounds per clause)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

__all__ = ["InteractionLog", "get_interaction_log"]


# ============================================================
# Interaction Log
# ============================================================


class InteractionLog:
    """Per-run LLM interaction log.

    Captures full prompt/response data for all pipeline phases.
    Thread-safe via lock.
    """

    LOG_DIR = Path("./data/interaction_logs")

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._lock = threading.Lock()
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._file = self.LOG_DIR / f"{run_id}_interactions.json"
        self._interactions: list[dict] = []
        self._created_at = datetime.now().isoformat()

        # Load existing if resuming
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._interactions = data.get("interactions", [])
                self._created_at = data.get("created_at", self._created_at)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        """Save log to disk atomically."""
        data = {
            "run_id": self.run_id,
            "created_at": self._created_at,
            "updated_at": datetime.now().isoformat(),
            "interaction_count": len(self._interactions),
            "interactions": self._interactions,
        }
        atomic_write_json(self._file, data)

    def log_interaction(
        self,
        *,
        phase: str,
        phase_label: str,
        doc_id: str = "",
        doc_title: str = "",
        clause_id: str = "",
        clause_title: str = "",
        # LLM call details
        system_prompt: str = "",
        user_prompt: str = "",
        llm_response: str = "",
        parsed_response: dict | list | None = None,
        # Metadata
        model: str = "",
        usage: dict | None = None,
        duration_seconds: float = 0.0,
        # Context
        round_number: int = 0,
        role: str = "",  # "analyzer" | "verifier" | ""
        extra: dict | None = None,
    ) -> None:
        """Log a single LLM interaction.

        Args:
            phase: Phase enum value (e.g., "gap_scan", "verification")
            phase_label: Human-readable phase name (e.g., "Phase 1 - Gap Scan")
            doc_id: Document ID
            doc_title: Document title
            clause_id: Clause ID (for per-clause phases)
            clause_title: Clause title
            system_prompt: Full system prompt sent to LLM
            user_prompt: Full user prompt sent to LLM
            llm_response: Full raw LLM response text
            parsed_response: Parsed structured response (dict/list)
            model: LLM model name
            usage: Token usage dict
            duration_seconds: LLM call duration
            round_number: Round number (for cross-examination)
            role: Role in cross-examination (analyzer/verifier)
            extra: Additional context data
        """
        entry = {
            "interaction_id": f"{self.run_id}_{len(self._interactions):04d}",
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "phase_label": phase_label,
            "doc_id": doc_id,
            "doc_title": doc_title,
            "clause_id": clause_id,
            "clause_title": clause_title,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "llm_response": llm_response,
            "parsed_response": parsed_response,
            "model": model,
            "usage": usage or {},
            "duration_seconds": duration_seconds,
            "round_number": round_number,
            "role": role,
            "extra": extra or {},
        }

        with self._lock:
            self._interactions.append(entry)
            # Save after each interaction for crash resilience
            try:
                self._save()
            except Exception as e:
                logger.warning(f"Failed to save interaction log: {e}")

    def get_interactions(self, phase: str = "") -> list[dict]:
        """Get all interactions, optionally filtered by phase."""
        if not phase:
            return list(self._interactions)
        return [i for i in self._interactions if i.get("phase") == phase]

    def get_interactions_by_clause(self, clause_id: str) -> list[dict]:
        """Get all interactions for a specific clause."""
        return [i for i in self._interactions if i.get("clause_id") == clause_id]

    def get_phase_summary(self) -> dict:
        """Get summary counts per phase."""
        summary: dict[str, dict] = {}
        for i in self._interactions:
            phase = i.get("phase", "unknown")
            if phase not in summary:
                summary[phase] = {
                    "count": 0,
                    "total_tokens": 0,
                    "phase_label": i.get("phase_label", phase),
                }
            summary[phase]["count"] += 1
            usage = i.get("usage", {})
            summary[phase]["total_tokens"] += usage.get("total_tokens", 0)
        return summary

    def to_dict(self) -> dict:
        """Full log as dict (for API responses)."""
        return {
            "run_id": self.run_id,
            "created_at": self._created_at,
            "interaction_count": len(self._interactions),
            "phase_summary": self.get_phase_summary(),
            "interactions": self._interactions,
        }

    @property
    def interaction_count(self) -> int:
        return len(self._interactions)


# ============================================================
# Module-level cache of active logs
# ============================================================

_active_logs: dict[str, InteractionLog] = {}
_logs_lock = threading.Lock()


def get_interaction_log(run_id: str) -> InteractionLog:
    """Get or create an InteractionLog for a run_id."""
    with _logs_lock:
        if run_id not in _active_logs:
            _active_logs[run_id] = InteractionLog(run_id)
        return _active_logs[run_id]


def load_interaction_log(run_id: str) -> Optional[InteractionLog]:
    """Load an existing interaction log from disk (read-only).

    Returns None if no log file exists for the run_id.
    """
    log_file = InteractionLog.LOG_DIR / f"{run_id}_interactions.json"
    if log_file.exists():
        return InteractionLog(run_id)
    return None
