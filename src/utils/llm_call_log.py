"""Central, append-only record of EVERY LLM call (success, failure, streaming).

Every call that goes through ``LLMProviderManager.completion()`` -- gap scan,
checklist verification, remediation, cross-examination, question generation,
regulation analysis, OCR/vision, LightRAG, chat -- is written here with its
full messages and full response, independent of Phoenix and independent of the
per-phase ``interaction_log``.

Files (JSON Lines, one call per line, UTF-8, never rewritten or truncated):
  logs/llm_calls/YYYY-MM-DD.jsonl     every call, chronological
  data/llm_calls/<run_id>.jsonl       copy of the calls made while a pipeline
                                      run was active on the calling thread

Logging must never break the application: all failures are swallowed (a single
warning is emitted to the normal log).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parent.parent.parent
_lock = threading.Lock()
_warned = False

# data:image/...;base64,AAAA...  ->  placeholder (keeps files small, text intact)
_DATA_URL = re.compile(r"data:(?:image|application)/[\w.+-]+;base64,[A-Za-z0-9+/=\s]{200,}")


def _redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return _DATA_URL.sub(lambda m: f"<binary data omitted, {len(m.group(0))} chars>", obj)
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    return obj


def log_dir() -> Path:
    return _ROOT / "logs" / "llm_calls"


def run_dir() -> Path:
    return _ROOT / "data" / "llm_calls"


def log_llm_call(record: dict, run_id: Optional[str] = None) -> None:
    """Append one call record. Never raises."""
    global _warned
    try:
        now = datetime.now().astimezone()
        record.setdefault("ts", now.isoformat(timespec="milliseconds"))
        record.setdefault("ts_epoch", now.timestamp())
        if run_id:
            record["run_id"] = run_id
        line = json.dumps(_redact(record), ensure_ascii=False, default=str) + "\n"
        targets = [log_dir() / f"{now:%Y-%m-%d}.jsonl"]
        if run_id:
            targets.append(run_dir() / f"{run_id}.jsonl")
        with _lock:
            for fp in targets:
                fp.parent.mkdir(parents=True, exist_ok=True)
                with open(fp, "a", encoding="utf-8") as fh:
                    fh.write(line)
    except Exception as exc:  # pragma: no cover - logging must not break callers
        if not _warned:
            _warned = True
            _logger.warning("LLM call log write failed (further failures silent): %r", exc)
