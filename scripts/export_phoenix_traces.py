"""Incrementally export Arize Phoenix traces to logs/phoenix/export/.

Reads phoenix.db directly (read-only), so it works whether or not the Phoenix
server is running and regardless of which HTTP port Phoenix picked.  Only spans
newer than the stored watermark are written, so it is cheap to call on every
launch / shutdown.

Output (under <project>/logs/phoenix/export/):
  spans_<project>_<YYYY-MM-DD>.jsonl   one full span per line
  traces_summary.csv                   one row per trace (appended)
  .watermark.json                      last exported span/trace row ids

Usage:
  python scripts/export_phoenix_traces.py [--db PATH] [--out DIR] [--mark-current]

--mark-current sets the watermark to the newest row without exporting anything
(use after a manual full export so history is not duplicated).
Never raises: failures are printed and the exit code is 0 so launchers are safe.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = 2000


def default_db() -> Path:
    base = os.environ.get("PHOENIX_WORKING_DIR") or str(Path.home() / ".phoenix")
    return Path(base) / "phoenix.db"


def load_mark(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"span_id": 0, "trace_id": 0}


def save_mark(path: Path, mark: dict) -> None:
    mark["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(mark), encoding="utf-8")
    tmp.replace(path)


def export(db: Path, out: Path, mark_current: bool = False) -> tuple[int, int]:
    if not db.exists():
        print(f"[phoenix-export] db not found: {db}")
        return 0, 0
    out.mkdir(parents=True, exist_ok=True)
    mark_file = out / ".watermark.json"
    mark = load_mark(mark_file)

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        if mark_current:
            mark["span_id"] = con.execute("select coalesce(max(id),0) from spans").fetchone()[0]
            mark["trace_id"] = con.execute("select coalesce(max(id),0) from traces").fetchone()[0]
            save_mark(mark_file, mark)
            print(f"[phoenix-export] watermark set to span {mark['span_id']} / trace {mark['trace_id']}")
            return 0, 0

        n_spans = 0
        while True:
            rows = con.execute(
                """select s.id, p.name project, t.trace_id, s.span_id, s.parent_id, s.name,
                          s.span_kind, s.start_time, s.end_time, s.status_code, s.status_message,
                          s.attributes, s.events,
                          s.cumulative_llm_token_count_prompt tokens_prompt,
                          s.cumulative_llm_token_count_completion tokens_completion
                   from spans s
                   join traces t on s.trace_rowid = t.id
                   join projects p on t.project_rowid = p.id
                   where s.id > ? order by s.id limit ?""",
                (mark["span_id"], BATCH),
            ).fetchall()
            if not rows:
                break
            handles: dict[Path, object] = {}
            try:
                for r in rows:
                    d = dict(r)
                    for k in ("attributes", "events"):
                        if isinstance(d[k], str):
                            try:
                                d[k] = json.loads(d[k])
                            except Exception:
                                pass
                    day = str(d["start_time"])[:10]
                    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in d["project"])
                    fp = out / f"spans_{safe}_{day}.jsonl"
                    if fp not in handles:
                        handles[fp] = open(fp, "a", encoding="utf-8")
                    handles[fp].write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
            finally:
                for h in handles.values():
                    h.close()
            mark["span_id"] = rows[-1]["id"]
            n_spans += len(rows)
            save_mark(mark_file, mark)  # persist progress per batch

        n_traces = 0
        new_traces = con.execute(
            """select t.id, p.name, t.trace_id, t.start_time, t.end_time,
                      (select count(*) from spans s where s.trace_rowid = t.id)
               from traces t join projects p on t.project_rowid = p.id
               where t.id > ? order by t.id""",
            (mark["trace_id"],),
        ).fetchall()
        if new_traces:
            csv_path = out / "traces_summary.csv"
            new_file = not csv_path.exists()
            with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["project", "trace_id", "start_time", "end_time", "spans"])
                for r in new_traces:
                    w.writerow(list(r)[1:])
            mark["trace_id"] = new_traces[-1][0]
            n_traces = len(new_traces)
            save_mark(mark_file, mark)
        print(f"[phoenix-export] exported {n_spans} span(s), {n_traces} trace(s) -> {out}")
        return n_spans, n_traces
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "logs" / "phoenix" / "export")
    ap.add_argument("--mark-current", action="store_true")
    a = ap.parse_args()
    try:
        export(a.db or default_db(), a.out, a.mark_current)
    except Exception as exc:  # never break a launcher
        print(f"[phoenix-export] failed: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
