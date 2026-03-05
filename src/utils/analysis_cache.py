"""Analysis cache for resilient regulatory report generation.

Provides persistent caching for long-running regulatory analysis tasks.
When LLM analysis is running, intermediate results are periodically saved
so that Word/Excel reports can be generated even if:
- WebSocket disconnects (browser closes/crashes)
- LLM provider times out or errors
- Any other interruption occurs

Cache files are stored in data/analysis_cache/ as JSON.
"""

import json
import threading

from datetime import datetime
from pathlib import Path

from src.utils.safe_io import atomic_write_json

_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "analysis_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_cache_lock = threading.Lock()


def _make_cache_id(command: str) -> str:
    """Generate a cache ID based on command and timestamp."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{command}_{ts}"


def save_analysis_cache(
    cache_id: str,
    command: str,
    scan_result: dict = None,
    crawl_results: dict = None,
    assessment: str = "",
    status: str = "in_progress",
    baseline_word_path: str = "",
    baseline_excel_path: str = "",
    final_word_path: str = "",
    final_excel_path: str = "",
    provider_id: str = "",
    model_name: str = "",
):
    """Save or update analysis cache.

    Args:
        cache_id: Unique identifier for this analysis run
        command: "regulatory_list" or "regulatory_update"
        scan_result: Local document scan results
        crawl_results: Web crawl results (for regulatory_update)
        assessment: Current LLM assessment text (may be partial)
        status: "in_progress", "completed", "failed", "baseline_ready"
        baseline_word_path: Path to baseline (no-LLM) Word report
        baseline_excel_path: Path to baseline (no-LLM) Excel report
        final_word_path: Path to final (with-LLM) Word report
        final_excel_path: Path to final (with-LLM) Excel report
        provider_id: LLM provider used
        model_name: LLM model used
    """
    cache_path = _CACHE_DIR / f"{cache_id}.json"

    # Load existing cache if updating
    existing = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    # Merge: only update non-empty fields
    data = {
        "cache_id": cache_id,
        "command": command,
        "status": status,
        "updated_at": datetime.now().isoformat(),
        "created_at": existing.get("created_at", datetime.now().isoformat()),
        "provider_id": provider_id or existing.get("provider_id", ""),
        "model_name": model_name or existing.get("model_name", ""),
        "assessment": assessment if assessment else existing.get("assessment", ""),
        "assessment_length": len(assessment)
        if assessment
        else existing.get("assessment_length", 0),
        "baseline_word_path": baseline_word_path
        or existing.get("baseline_word_path", ""),
        "baseline_excel_path": baseline_excel_path
        or existing.get("baseline_excel_path", ""),
        "final_word_path": final_word_path or existing.get("final_word_path", ""),
        "final_excel_path": final_excel_path or existing.get("final_excel_path", ""),
    }

    # Store scan_result and crawl_results only on first save (they're large)
    if scan_result is not None:
        data["scan_result"] = scan_result
    elif "scan_result" in existing:
        data["scan_result"] = existing["scan_result"]

    if crawl_results is not None:
        data["crawl_results"] = crawl_results
    elif "crawl_results" in existing:
        data["crawl_results"] = existing["crawl_results"]

    atomic_write_json(cache_path, data)


def load_latest_cache(command: str = None) -> dict:
    """Load the most recent analysis cache, optionally filtered by command.

    Returns empty dict if no cache found.
    """
    if not _CACHE_DIR.exists():
        return {}

    cache_files = sorted(_CACHE_DIR.glob("*.json"), reverse=True)

    for cache_path in cache_files:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if command and data.get("command") != command:
                continue
            return data
        except Exception:
            continue

    return {}


def load_cache_by_id(cache_id: str) -> dict:
    """Load a specific analysis cache by ID."""
    cache_path = _CACHE_DIR / f"{cache_id}.json"
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_pending_reports() -> list:
    """Find analysis caches that have completed reports but user hasn't seen them.

    Returns list of cache entries where:
    - status is "completed"
    - final Word/Excel paths exist
    """
    if not _CACHE_DIR.exists():
        return []

    pending = []
    for cache_path in sorted(_CACHE_DIR.glob("*.json"), reverse=True):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            status = data.get("status", "")
            if status == "completed":
                # Check if report files actually exist
                has_final = (
                    data.get("final_word_path")
                    and Path(data["final_word_path"]).exists()
                )
                has_baseline = (
                    data.get("baseline_word_path")
                    and Path(data["baseline_word_path"]).exists()
                )
                if has_final or has_baseline:
                    pending.append(data)
        except Exception:
            continue

    return pending


def mark_cache_delivered(cache_id: str):
    """Mark a cache entry as delivered to the user (so it won't show again)."""
    cache_path = _CACHE_DIR / f"{cache_id}.json"
    if not cache_path.exists():
        return
    with _cache_lock:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "delivered"
            data["delivered_at"] = datetime.now().isoformat()
            atomic_write_json(cache_path, data)
        except Exception:
            pass


def cleanup_old_caches(keep_count: int = 10):
    """Remove old cache files, keeping only the most recent ones."""
    if not _CACHE_DIR.exists():
        return
    cache_files = sorted(_CACHE_DIR.glob("*.json"), reverse=True)
    for old_file in cache_files[keep_count:]:
        try:
            old_file.unlink()
        except Exception:
            pass
