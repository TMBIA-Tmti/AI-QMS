from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

__all__ = ["DailyCrossExamStore", "DailySamplingRecord", "get_daily_crossexam_store"]


class DailySamplingRecord:
    """One daily sampling cross-examination session.

    Stores results from an independent Phase 5 re-run on a 20% sample
    of the latest comparison table rows.  Separate from the pipeline's
    CrossExamRecord which records full pipeline Phase 5 results.
    """

    def __init__(
        self,
        *,
        record_id: str = "",
        date: str = "",
        timestamp: str = "",
        source_run_id: str = "",
        selected_regulations: list[str] | None = None,
        countries: list[str] | None = None,
        mdsap_enabled: bool = False,
        sample_rate: float = 0.2,
        total_rows_available: int = 0,
        sampled_row_ids: list[str] | None = None,
        clauses: list[dict] | None = None,
        total_clauses: int = 0,
        total_agreed: int = 0,
        total_flagged: int = 0,
        total_rounds: int = 0,
        questions_used: list[dict] | None = None,
        llm_usage: dict | None = None,
        llm_model: str = "",
        duration_seconds: float = 0.0,
        lang: str = "zh-TW",
        dim_a_score: float = 0.0,
        dim_a_summary: str = "",
        dim_b_score: float = 0.0,
        dim_b_summary: str = "",
        overall_score: float = 0.0,
        cross_validation: dict | None = None,
        deviation_detected: bool = False,
        deviation_details: str = "",
    ):
        self.record_id = record_id or str(uuid.uuid4())[:12]
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.timestamp = timestamp or datetime.now().isoformat()
        self.source_run_id = source_run_id
        self.selected_regulations = selected_regulations or []
        self.countries = countries or []
        self.mdsap_enabled = mdsap_enabled
        self.sample_rate = sample_rate
        self.total_rows_available = total_rows_available
        self.sampled_row_ids = sampled_row_ids or []
        self.clauses = clauses or []
        self.total_clauses = total_clauses
        self.total_agreed = total_agreed
        self.total_flagged = total_flagged
        self.total_rounds = total_rounds
        self.questions_used = questions_used or []
        self.llm_usage = llm_usage or {}
        self.llm_model = llm_model
        self.duration_seconds = duration_seconds
        self.lang = lang
        self.dim_a_score = dim_a_score
        self.dim_a_summary = dim_a_summary
        self.dim_b_score = dim_b_score
        self.dim_b_summary = dim_b_summary
        self.overall_score = overall_score
        self.cross_validation = cross_validation or {}
        self.deviation_detected = deviation_detected
        self.deviation_details = deviation_details

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "date": self.date,
            "timestamp": self.timestamp,
            "source_run_id": self.source_run_id,
            "selected_regulations": self.selected_regulations,
            "countries": self.countries,
            "mdsap_enabled": self.mdsap_enabled,
            "sample_rate": self.sample_rate,
            "total_rows_available": self.total_rows_available,
            "sampled_row_ids": self.sampled_row_ids,
            "clauses": self.clauses,
            "total_clauses": self.total_clauses,
            "total_agreed": self.total_agreed,
            "total_flagged": self.total_flagged,
            "total_rounds": self.total_rounds,
            "questions_used": self.questions_used,
            "llm_usage": self.llm_usage,
            "llm_model": self.llm_model,
            "duration_seconds": self.duration_seconds,
            "lang": self.lang,
            "dim_a_score": self.dim_a_score,
            "dim_a_summary": self.dim_a_summary,
            "dim_b_score": self.dim_b_score,
            "dim_b_summary": self.dim_b_summary,
            "overall_score": self.overall_score,
            "cross_validation": self.cross_validation,
            "deviation_detected": self.deviation_detected,
            "deviation_details": self.deviation_details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailySamplingRecord":
        import inspect

        valid_params = set(inspect.signature(cls.__init__).parameters.keys()) - {"self"}
        return cls(**{k: v for k, v in data.items() if k in valid_params})

    def summary_text(self, lang_key: str = "zh") -> str:
        if lang_key == "zh":
            mode = "7國+5國MDSAP" if self.mdsap_enabled else "2國(TFDA+EU_MDR)"
            return (
                f"每日抽樣詰問 {self.record_id}\n"
                f"日期: {self.date}\n"
                f"來源分析: {self.source_run_id}\n"
                f"模式: {mode}\n"
                f"抽樣: {len(self.sampled_row_ids)}/{self.total_rows_available} "
                f"({self.sample_rate:.0%})\n"
                f"條款數: {self.total_clauses}  |  "
                f"同意: {self.total_agreed}  |  "
                f"標記 RA: {self.total_flagged}\n"
                f"Dim A: {self.dim_a_score:.0f}  |  "
                f"Dim B: {self.dim_b_score:.0f}  |  "
                f"總分: {self.overall_score:.0f}\n"
                f"模型: {self.llm_model}  |  "
                f"耗時: {self.duration_seconds:.1f}s"
            )
        mode = (
            "7-country+5-country MDSAP"
            if self.mdsap_enabled
            else "2-country(TFDA+EU_MDR)"
        )
        return (
            f"Daily Sampling Cross-Exam {self.record_id}\n"
            f"Date: {self.date}\n"
            f"Source run: {self.source_run_id}\n"
            f"Mode: {mode}\n"
            f"Sampled: {len(self.sampled_row_ids)}/{self.total_rows_available} "
            f"({self.sample_rate:.0%})\n"
            f"Clauses: {self.total_clauses}  |  "
            f"Agreed: {self.total_agreed}  |  "
            f"Flagged RA: {self.total_flagged}\n"
            f"Dim A: {self.dim_a_score:.0f}  |  "
            f"Dim B: {self.dim_b_score:.0f}  |  "
            f"Overall: {self.overall_score:.0f}\n"
            f"Model: {self.llm_model}  |  "
            f"Duration: {self.duration_seconds:.1f}s"
        )


class DailyCrossExamStore:
    """JSON-backed store for daily sampling cross-examination records.

    Completely independent from CrossExamStore (pipeline full cross-exam).
    File: data/daily_crossexam/daily_crossexam_store.json
    """

    DEFAULT_PATH = "./data/daily_crossexam/daily_crossexam_store.json"

    def __init__(self, store_file: str = DEFAULT_PATH):
        self.store_file = Path(store_file)
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        if not self.store_file.exists():
            self._init_store()

    def _init_store(self) -> None:
        atomic_write_json(
            self.store_file,
            {
                "records": [],
                "meta": {"created_at": datetime.now().isoformat(), "version": 1},
            },
        )

    def _load_store(self) -> dict:
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {
                "records": [],
                "meta": {"created_at": datetime.now().isoformat(), "version": 1},
            }

    def _save_store(self, data: dict) -> None:
        atomic_write_json(self.store_file, data)

    def save_record(self, record: DailySamplingRecord) -> DailySamplingRecord:
        with self._lock:
            store = self._load_store()
            existing_idx = next(
                (
                    i
                    for i, r in enumerate(store["records"])
                    if r.get("record_id") == record.record_id
                ),
                None,
            )
            if existing_idx is not None:
                store["records"][existing_idx] = record.to_dict()
                logger.info(f"Updated daily sampling record {record.record_id} ({record.date})")
            else:
                store["records"].append(record.to_dict())
                logger.info(
                    f"Saved new daily sampling record {record.record_id} ({record.date})"
                )
            self._save_store(store)
        return record

    def get_record(self, record_id: str) -> Optional[DailySamplingRecord]:
        store = self._load_store()
        for r in store["records"]:
            if r.get("record_id") == record_id:
                return DailySamplingRecord.from_dict(r)
        return None

    def get_record_by_date(self, date: str) -> Optional[DailySamplingRecord]:
        store = self._load_store()
        matches = [r for r in store["records"] if r.get("date") == date]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return DailySamplingRecord.from_dict(matches[0])

    def get_all_records(self) -> list[DailySamplingRecord]:
        store = self._load_store()
        records = [DailySamplingRecord.from_dict(r) for r in store.get("records", [])]
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    def get_record_count(self) -> int:
        store = self._load_store()
        return len(store.get("records", []))

    def get_recent_records(self, limit: int = 10) -> list[DailySamplingRecord]:
        return self.get_all_records()[:limit]

    def delete_record(self, record_id: str) -> bool:
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

    def get_country_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for record in self.get_all_records():
            for country in record.countries:
                dist[country] = dist.get(country, 0) + 1
        return dist

    def get_agreement_trend(self) -> list[dict]:
        records = self.get_all_records()
        records.reverse()
        trend = []
        for r in records:
            rate = r.total_agreed / max(r.total_clauses, 1)
            trend.append(
                {
                    "record_id": r.record_id,
                    "date": r.date,
                    "timestamp": r.timestamp,
                    "agreement_rate": round(rate, 3),
                    "total_clauses": r.total_clauses,
                    "total_flagged": r.total_flagged,
                    "dim_a_score": r.dim_a_score,
                    "dim_b_score": r.dim_b_score,
                    "overall_score": r.overall_score,
                }
            )
        return trend

    def get_question_type_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for record in self.get_all_records():
            for q in record.questions_used:
                qtype = q.get("question_type", "unknown")
                dist[qtype] = dist.get(qtype, 0) + 1
        return dist

    def needs_meta_review(self) -> bool:
        return self.get_record_count() >= 10


_daily_store_instance: Optional[DailyCrossExamStore] = None


def get_daily_crossexam_store() -> DailyCrossExamStore:
    global _daily_store_instance
    if _daily_store_instance is None:
        _daily_store_instance = DailyCrossExamStore()
    return _daily_store_instance
