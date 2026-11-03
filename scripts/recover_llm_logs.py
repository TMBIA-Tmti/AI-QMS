"""Rebuild historical LLM call logs from the Phoenix database.

Before ``src/utils/llm_call_log.py`` existed, full prompts/responses were kept
only in Phoenix (``~/.phoenix/phoenix.db``).  This tool converts every Phoenix
span into the same JSONL record format the live call log uses, so old and new
history live side by side:

  logs/llm_calls/recovered_phoenix_<YYYY-MM-DD>.jsonl   every span, by local day
  data/llm_calls/<run_id>.recovered.jsonl               LLM calls inside that
                                                        pipeline run's time window

Phoenix spans carry no run id, so a call is attributed to a run by TIME WINDOW
(run created_at .. completed_at/updated_at, +/- 60 s).  Such records are marked
``"approximate": true``; if several runs overlap the call is written to each
candidate run and ``candidate_run_ids`` lists them all.

Safe to re-run: only the ``recovered`` files are (re)written; live call-log
files and ``data/interaction_logs`` are never touched.

Usage:  python scripts/recover_llm_logs.py [--db PATH]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAD = 60  # seconds around a run window


def default_db() -> Path:
    base = os.environ.get("PHOENIX_WORKING_DIR") or str(Path.home() / ".phoenix")
    return Path(base) / "phoenix.db"


def _epoch(utc_text: str) -> float:
    t = datetime.fromisoformat(str(utc_text).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.timestamp()


def _local_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="milliseconds")


def _messages(v) -> list:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return [{"role": "?", "content": v}]
    out = []
    for m in v if isinstance(v, list) else []:
        m = m.get("message", m) if isinstance(m, dict) else {"role": "?", "content": str(m)}
        out.append({"role": m.get("role", "?"), "content": m.get("content")})
    return out


def load_runs(data_dir: Path) -> list[dict]:
    runs = []
    for f in sorted((data_dir / "analysis_pipeline").glob("run_*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        a = j.get("created_at")
        if not a:
            continue
        b = j.get("completed_at") or j.get("updated_at") or a
        runs.append({"run_id": f.stem, "start": a - PAD, "end": max(a, b) + PAD})
    return runs


def span_to_record(row: sqlite3.Row) -> dict:
    a = json.loads(row["attributes"]) if isinstance(row["attributes"], str) else (row["attributes"] or {})
    llm = a.get("llm") or {}
    t0 = _epoch(row["start_time"])
    t1 = _epoch(row["end_time"]) if row["end_time"] else t0
    model = llm.get("model_name")
    is_llm = bool(llm) or (a.get("openinference") or {}).get("span", {}).get("kind") == "LLM"
    tc = llm.get("token_count") or {}
    rec = {
        "ts": _local_iso(t0),
        "ts_epoch": t0,
        "source": "phoenix",
        "kind": "llm" if is_llm else "span",
        "span_name": row["name"],
        "provider": (model or "").split("/")[0] if model else None,
        "model": model,
        "status": "ok" if row["status_code"] in ("OK", "UNSET") else "error",
        "duration_s": round(t1 - t0, 3),
        "error": row["status_message"] or None,
        "trace_id": row["trace_id"],
        "span_id": row["span_id"],
        "project": row["project"],
    }
    if is_llm:
        out_msgs = _messages(llm.get("output_messages"))
        rec.update(
            messages=_messages(llm.get("input_messages")) or [{"role": "?", "content": (a.get("input") or {}).get("value")}],
            response=(out_msgs[-1]["content"] if out_msgs else (a.get("output") or {}).get("value")),
            usage={
                "prompt_tokens": tc.get("prompt"),
                "completion_tokens": tc.get("completion"),
                "total_tokens": tc.get("total"),
            },
            invocation_parameters=llm.get("invocation_parameters"),
        )
    else:
        rec["attributes"] = {k: v for k, v in a.items() if k != "openinference"}
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    db = a.db or default_db()
    if not db.exists():
        print(f"[recover] Phoenix db not found: {db}")
        return 0
    root = a.root
    logs_dir = root / "logs" / "llm_calls"
    runs_dir = root / "data" / "llm_calls"
    logs_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    for f in logs_dir.glob("recovered_phoenix_*.jsonl"):
        f.unlink()
    for f in runs_dir.glob("*.recovered.jsonl"):
        f.unlink()

    runs = load_runs(root / "data")
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    day_fh: dict[str, object] = {}
    run_fh: dict[str, object] = {}
    n = n_llm = n_assigned = n_ambiguous = 0
    try:
        q = """select s.id, s.name, s.start_time, s.end_time, s.status_code, s.status_message,
                      s.attributes, t.trace_id, s.span_id, p.name project
               from spans s join traces t on s.trace_rowid = t.id
               join projects p on t.project_rowid = p.id order by s.start_time"""
        for row in con.execute(q):
            rec = span_to_record(row)
            day = rec["ts"][:10]
            if day not in day_fh:
                day_fh[day] = open(logs_dir / f"recovered_phoenix_{day}.jsonl", "a", encoding="utf-8")
            n += 1
            cands = []
            if rec["kind"] == "llm":
                n_llm += 1
                cands = [r["run_id"] for r in runs if r["start"] <= rec["ts_epoch"] <= r["end"]]
                if cands:
                    rec["candidate_run_ids"] = cands
                    rec["approximate"] = True
                    n_assigned += 1
                    n_ambiguous += len(cands) > 1
            day_fh[day].write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            for rid in cands:
                if rid not in run_fh:
                    run_fh[rid] = open(runs_dir / f"{rid}.recovered.jsonl", "a", encoding="utf-8")
                run_fh[rid].write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    finally:
        con.close()
        for h in list(day_fh.values()) + list(run_fh.values()):
            h.close()
    print(
        f"[recover] {n} Phoenix span(s) ({n_llm} LLM calls) -> {len(day_fh)} daily file(s); "
        f"{n_assigned} LLM call(s) attributed to {len(run_fh)} run(s) "
        f"({n_ambiguous} fall in overlapping run windows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
