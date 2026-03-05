"""
AI-QMS — Cross-Examination History Store
==========================================

Persistent JSON-based storage for cross-examination session records.
Each pipeline run's Phase 5 results are saved as a record, enabling:
  - Historical review of all cross-exam sessions
  - Per-record download (Word/Excel)
  - Meta-analysis when ≥10 records exist
  - Quality trend tracking over time

Storage pattern follows document_store.py:
  - JSON file at data/crossexam_history/crossexam_store.json
  - Thread-safe via atomic writes (safe_io)
  - CRUD operations with filtering
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

__all__ = ["CrossExamStore", "CrossExamRecord"]


# ============================================================
# Data structures
# ============================================================


class CrossExamRecord:
    """One cross-examination session record (one pipeline run's Phase 5)."""

    def __init__(
        self,
        *,
        record_id: str = "",
        run_id: str = "",
        timestamp: str = "",
        # Regulation context
        selected_regulations: list[str] | None = None,
        countries: list[str] | None = None,
        # Clause-level results
        clauses: list[dict] | None = None,
        # Aggregate stats
        total_clauses: int = 0,
        total_agreed: int = 0,
        total_flagged: int = 0,
        total_rounds: int = 0,
        # Cross-exam questions used
        questions_used: list[dict] | None = None,
        # LLM usage
        llm_usage: dict | None = None,
        llm_model: str = "",
        duration_seconds: float = 0.0,
        # Pipeline context
        assessment_mode: str = "",
        lang: str = "zh-TW",
    ):
        self.record_id = record_id or str(uuid.uuid4())[:12]
        self.run_id = run_id
        self.timestamp = timestamp or datetime.now().isoformat()
        self.selected_regulations = selected_regulations or []
        self.countries = countries or []
        self.clauses = clauses or []
        self.total_clauses = total_clauses
        self.total_agreed = total_agreed
        self.total_flagged = total_flagged
        self.total_rounds = total_rounds
        self.questions_used = questions_used or []
        self.llm_usage = llm_usage or {}
        self.llm_model = llm_model
        self.duration_seconds = duration_seconds
        self.assessment_mode = assessment_mode
        self.lang = lang

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "selected_regulations": self.selected_regulations,
            "countries": self.countries,
            "clauses": self.clauses,
            "total_clauses": self.total_clauses,
            "total_agreed": self.total_agreed,
            "total_flagged": self.total_flagged,
            "total_rounds": self.total_rounds,
            "questions_used": self.questions_used,
            "llm_usage": self.llm_usage,
            "llm_model": self.llm_model,
            "duration_seconds": self.duration_seconds,
            "assessment_mode": self.assessment_mode,
            "lang": self.lang,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrossExamRecord":
        import inspect

        valid_params = set(inspect.signature(cls.__init__).parameters.keys()) - {"self"}
        return cls(**{k: v for k, v in data.items() if k in valid_params})

    def summary_text(self, lang_key: str = "zh") -> str:
        """Generate a human-readable summary for display."""
        if lang_key == "zh":
            return (
                f"交叉詰問記錄 {self.record_id}\n"
                f"分析 ID: {self.run_id}\n"
                f"時間: {self.timestamp}\n"
                f"法規: {', '.join(self.selected_regulations) or '無'}\n"
                f"國家: {', '.join(self.countries) or '無'}\n"
                f"條款數: {self.total_clauses}  |  "
                f"同意: {self.total_agreed}  |  "
                f"標記 RA: {self.total_flagged}  |  "
                f"總輪次: {self.total_rounds}\n"
                f"模型: {self.llm_model}  |  "
                f"耗時: {self.duration_seconds:.1f}s"
            )
        return (
            f"Cross-Exam Record {self.record_id}\n"
            f"Run ID: {self.run_id}\n"
            f"Time: {self.timestamp}\n"
            f"Regulations: {', '.join(self.selected_regulations) or 'None'}\n"
            f"Countries: {', '.join(self.countries) or 'None'}\n"
            f"Clauses: {self.total_clauses}  |  "
            f"Agreed: {self.total_agreed}  |  "
            f"Flagged RA: {self.total_flagged}  |  "
            f"Total Rounds: {self.total_rounds}\n"
            f"Model: {self.llm_model}  |  "
            f"Duration: {self.duration_seconds:.1f}s"
        )


# ============================================================
# Store class
# ============================================================


class CrossExamStore:
    """JSON-backed cross-examination history store.

    Thread-safe via lock on write operations.
    File: data/crossexam_history/crossexam_store.json
    """

    DEFAULT_PATH = "./data/crossexam_history/crossexam_store.json"

    def __init__(self, store_file: str = DEFAULT_PATH):
        self.store_file = Path(store_file)
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        if not self.store_file.exists():
            self._init_store()

    def _init_store(self) -> None:
        """Initialize empty store file."""
        atomic_write_json(
            self.store_file,
            {
                "records": [],
                "meta": {"created_at": datetime.now().isoformat(), "version": 1},
            },
        )

    def _load_store(self) -> dict:
        """Load store data from disk."""
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {
                "records": [],
                "meta": {"created_at": datetime.now().isoformat(), "version": 1},
            }

    def _save_store(self, data: dict) -> None:
        """Save store data atomically."""
        atomic_write_json(self.store_file, data)

    # ── CRUD ──

    def save_record(self, record: CrossExamRecord) -> CrossExamRecord:
        """Save a cross-exam record. Returns the saved record."""
        with self._lock:
            store = self._load_store()
            # Check for duplicate run_id — update if exists
            existing_idx = next(
                (
                    i
                    for i, r in enumerate(store["records"])
                    if r.get("run_id") == record.run_id
                ),
                None,
            )
            if existing_idx is not None:
                store["records"][existing_idx] = record.to_dict()
                logger.info(f"Updated cross-exam record for run {record.run_id}")
            else:
                store["records"].append(record.to_dict())
                logger.info(
                    f"Saved new cross-exam record {record.record_id} (run {record.run_id})"
                )
            self._save_store(store)
        return record

    def get_record(self, record_id: str) -> Optional[CrossExamRecord]:
        """Get a single record by record_id."""
        store = self._load_store()
        for r in store["records"]:
            if r.get("record_id") == record_id:
                return CrossExamRecord.from_dict(r)
        return None

    def get_record_by_run_id(self, run_id: str) -> Optional[CrossExamRecord]:
        """Get a single record by run_id."""
        store = self._load_store()
        for r in store["records"]:
            if r.get("run_id") == run_id:
                return CrossExamRecord.from_dict(r)
        return None

    def get_all_records(self) -> list[CrossExamRecord]:
        """Get all records, newest first."""
        store = self._load_store()
        records = [CrossExamRecord.from_dict(r) for r in store.get("records", [])]
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    def get_record_count(self) -> int:
        """Get total number of records."""
        store = self._load_store()
        return len(store.get("records", []))

    def get_recent_records(self, limit: int = 10) -> list[CrossExamRecord]:
        """Get the N most recent records."""
        all_records = self.get_all_records()
        return all_records[:limit]

    def delete_record(self, record_id: str) -> bool:
        """Delete a record by record_id. Returns True if deleted."""
        with self._lock:
            store = self._load_store()
            original_count = len(store["records"])
            store["records"] = [
                r for r in store["records"] if r.get("record_id") != record_id
            ]
            if len(store["records"]) < original_count:
                self._save_store(store)
                return True
        return False

    # ── Aggregation helpers ──

    def get_country_distribution(self) -> dict[str, int]:
        """Get count of cross-exam sessions per country across all records."""
        dist: dict[str, int] = {}
        for record in self.get_all_records():
            for country in record.countries:
                dist[country] = dist.get(country, 0) + 1
        return dist

    def get_agreement_trend(self) -> list[dict]:
        """Get agreement rate trend over time (oldest to newest)."""
        records = self.get_all_records()
        records.reverse()  # oldest first
        trend = []
        for r in records:
            rate = r.total_agreed / max(r.total_clauses, 1)
            trend.append(
                {
                    "record_id": r.record_id,
                    "timestamp": r.timestamp,
                    "agreement_rate": round(rate, 3),
                    "total_clauses": r.total_clauses,
                    "total_flagged": r.total_flagged,
                }
            )
        return trend

    def get_question_type_distribution(self) -> dict[str, int]:
        """Get distribution of question types (delta/exceeds/overlap) across all records."""
        dist: dict[str, int] = {}
        for record in self.get_all_records():
            for q in record.questions_used:
                qtype = q.get("question_type", "unknown")
                dist[qtype] = dist.get(qtype, 0) + 1
        return dist

    def needs_meta_analysis(self) -> bool:
        """Check if ≥10 records exist, triggering meta-analysis."""
        return self.get_record_count() >= 10


# ============================================================
# Module-level singleton
# ============================================================

_store_instance: Optional[CrossExamStore] = None


def get_crossexam_store() -> CrossExamStore:
    """Get or create the singleton CrossExamStore instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = CrossExamStore()
    return _store_instance
