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


def to_local(ts) -> str:
    """Phoenix stores naive UTC timestamps; return them as local-time ISO text
    (with UTC offset) so they line up with every other log under logs/."""
    from datetime import timezone

    if not ts:
        return ""
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone().isoformat(sep=" ", timespec="milliseconds")
    except Exception:
        return ""


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


def _model(attrs) -> str:
    try:
        a = json.loads(attrs) if isinstance(attrs, str) else attrs
        return str((a.get("llm") or {}).get("model_name") or "-")
    except Exception:
        return "-"


def _latency(start, end) -> str:
    try:
        f = "%Y-%m-%d %H:%M:%S.%f"
        s = datetime.strptime(str(start)[:26], f if "." in str(start) else f.replace(".%f", ""))
        e = datetime.strptime(str(end)[:26], f if "." in str(end) else f.replace(".%f", ""))
        return f"{(e - s).total_seconds():.2f}"
    except Exception:
        return "-"


def write_session_md(rows, sessions_dir: Path) -> None:
    """Append a readable per-day table (logs/sessions/phoenix/<date>_phoenix.md)."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    handles: dict[Path, object] = {}
    try:
        for r in rows:
            loc = to_local(r["start_time"]) or str(r["start_time"])
            day = loc[:10]
            fp = sessions_dir / f"{day}_phoenix.md"
            if fp not in handles:
                new = not fp.exists()
                handles[fp] = open(fp, "a", encoding="utf-8")
                if new:
                    handles[fp].write(
                        f"# Phoenix LLM Traces - {day}\n\n"
                        f"Times are LOCAL time (UTC{datetime.now().astimezone().strftime('%z')}); "
                        "raw database values are UTC.\n\n"
                        "| Time | Project | Name | Model | Status | Latency(s) | Tokens | Trace |\n"
                        "|------|---------|------|-------|--------|------------|--------|-------|\n"
                    )
            tokens = (r["tokens_prompt"] or 0) + (r["tokens_completion"] or 0)
            handles[fp].write(
                f"| {loc[11:19]} | {r['project']} | {r['name']} | {_model(r['attributes'])} "
                f"| {r['status_code']} | {_latency(r['start_time'], r['end_time'])} | {tokens} | {str(r['trace_id'])[:8]} |\n"
            )
    finally:
        for h in handles.values():
            h.close()


def rebuild_sessions(db: Path, sessions_dir: Path) -> int:
    """Regenerate every daily summary from the whole database."""
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        if sessions_dir.exists():
            for f in sessions_dir.glob("*_phoenix.md"):
                f.unlink()
        last, n = 0, 0
        while True:
            rows = con.execute(
                """select s.id, p.name project, t.trace_id, s.name, s.start_time, s.end_time, s.status_code,
                          s.attributes, s.cumulative_llm_token_count_prompt tokens_prompt,
                          s.cumulative_llm_token_count_completion tokens_completion
                   from spans s join traces t on s.trace_rowid = t.id join projects p on t.project_rowid = p.id
                   where s.id > ? order by s.id limit ?""", (last, BATCH)).fetchall()
            if not rows:
                break
            write_session_md(rows, sessions_dir)
            last, n = rows[-1]["id"], n + len(rows)
        print(f"[phoenix-export] rebuilt session summaries from {n} span(s) -> {sessions_dir}")
        return n
    finally:
        con.close()


def export(db: Path, out: Path, mark_current: bool = False, sessions: Path | None = None) -> tuple[int, int]:
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
            batch_dicts = []
            try:
                for r in rows:
                    d = dict(r)
                    for k in ("attributes", "events"):
                        if isinstance(d[k], str):
                            try:
                                d[k] = json.loads(d[k])
                            except Exception:
                                pass
                    d["start_time_local"] = to_local(d["start_time"])
                    d["end_time_local"] = to_local(d["end_time"])
                    day = (d["start_time_local"] or str(d["start_time"]))[:10]
                    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in d["project"])
                    fp = out / f"spans_{safe}_{day}.jsonl"
                    if fp not in handles:
                        handles[fp] = open(fp, "a", encoding="utf-8")
                    handles[fp].write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
                    batch_dicts.append(d)
            finally:
                for h in handles.values():
                    h.close()
            try:
                write_txt(batch_dicts, out.parent / "export_txt")
            except Exception as exc:
                print(f"[phoenix-export] txt export failed: {exc!r}", file=sys.stderr)
            if sessions is not None:
                try:
                    write_session_md(rows, sessions)
                except Exception as exc:
                    print(f"[phoenix-export] session summary failed: {exc!r}", file=sys.stderr)
            mark["span_id"] = rows[-1]["id"]
            n_spans += len(rows)
            save_mark(mark_file, mark)  # persist progress per batch

        n_traces = 0
        new_traces = con.execute(
            """select t.id, p.name, t.trace_id, t.start_time, t.end_time,
                      (select count(*) from spans s where s.trace_rowid = t.id),
                      (select sum(cumulative_llm_token_count_prompt + cumulative_llm_token_count_completion)
                         from spans s where s.trace_rowid = t.id and s.parent_id is null)
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
                    w.writerow(["project", "trace_id", "start_time", "end_time", "spans", "tokens",
                                "start_time_local", "end_time_local"])
                for r in new_traces:
                    w.writerow(list(r)[1:] + [to_local(r[3]), to_local(r[4])])
            mark["trace_id"] = new_traces[-1][0]
            n_traces = len(new_traces)
            save_mark(mark_file, mark)
        print(f"[phoenix-export] exported {n_spans} span(s), {n_traces} trace(s) -> {out}")
        return n_spans, n_traces
    finally:
        con.close()


def _msgs(v) -> str:
    """Render llm.input_messages / llm.output_messages as readable text."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return v
    parts = []
    for m in v if isinstance(v, list) else []:
        m = m.get("message", m) if isinstance(m, dict) else m
        if isinstance(m, dict):
            c = m.get("content")
            if c is None and m.get("contents"):
                c = "\n".join(str(x.get("message_content", {}).get("text", x)) for x in m["contents"])
            parts.append(f"[{m.get('role', '?')}]\n{c}")
        else:
            parts.append(str(m))
    return "\n\n".join(parts)


def format_span_txt(d: dict) -> str:
    a = d.get("attributes") or {}
    llm = a.get("llm") or {}
    inp = _msgs(llm.get("input_messages")) if llm.get("input_messages") else str((a.get("input") or {}).get("value", ""))
    outp = _msgs(llm.get("output_messages")) if llm.get("output_messages") else str((a.get("output") or {}).get("value", ""))
    tc = llm.get("token_count") or {}
    lat = _latency(d.get("start_time"), d.get("end_time"))
    return (
        "=" * 100 + "\n"
        f"{(d.get('start_time_local') or d.get('start_time') or '')[:23]} | {d.get('project')} | {d.get('name')} | "
        f"{llm.get('model_name', '-')} | {d.get('status_code')} | {lat}s | tokens {tc.get('total', '-')}\n"
        f"trace {d.get('trace_id')}  span {d.get('span_id')}\n" + "-" * 100 + "\n"
        f"INPUT:\n{inp}\n\nOUTPUT:\n{outp}\n"
        + (f"\nSTATUS MESSAGE: {d['status_message']}\n" if d.get("status_message") else "")
        + "\n"
    )


def write_txt(spans, txt_dir: Path) -> None:
    """Append spans (dicts with *_local fields) to per-day readable .txt files."""
    txt_dir.mkdir(parents=True, exist_ok=True)
    handles: dict[Path, object] = {}
    try:
        for d in spans:
            day = (d.get("start_time_local") or str(d.get("start_time")))[:10]
            fp = txt_dir / f"{day}_phoenix.txt"
            if fp not in handles:
                new = not fp.exists()
                handles[fp] = open(fp, "a", encoding="utf-8-sig" if new else "utf-8")
                if new:
                    handles[fp].write(f"Phoenix LLM traces - {day} (local time, UTC{datetime.now().astimezone().strftime('%z')})\n\n")
            handles[fp].write(format_span_txt(d))
    finally:
        for h in handles.values():
            h.close()


def rebuild_txt(out: Path, txt_dir: Path) -> int:
    """Regenerate every per-day .txt from the exported JSONL files (time-ordered)."""
    if txt_dir.exists():
        for f in txt_dir.glob("*_phoenix.txt"):
            f.unlink()
    n = 0
    for f in sorted(out.glob("spans_*.jsonl")):
        buf = []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                buf.append(json.loads(line))
                if len(buf) >= 2000:
                    write_txt(buf, txt_dir); n += len(buf); buf = []
        if buf:
            write_txt(buf, txt_dir); n += len(buf)
    print(f"[phoenix-export] wrote {n} span(s) as readable text -> {txt_dir}")
    return n


def add_local_fields(out: Path) -> None:
    """One-off: add start_time_local/end_time_local to files exported earlier."""
    for f in sorted(out.glob("spans_*.jsonl")):
        tmp = f.with_suffix(".tmp")
        n = 0
        with open(f, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
            for line in src:
                d = json.loads(line)
                if "start_time_local" not in d:
                    d["start_time_local"] = to_local(d.get("start_time"))
                    d["end_time_local"] = to_local(d.get("end_time"))
                dst.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
                n += 1
        tmp.replace(f)
        print(f"[phoenix-export] {f.name}: {n} line(s) updated")
    csv_path = out / "traces_summary.csv"
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        if rows and "start_time_local" not in rows[0]:
            rows[0] += ["start_time_local", "end_time_local"]
            for r in rows[1:]:
                r += [to_local(r[2]), to_local(r[3])]
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh).writerows(rows)
            print(f"[phoenix-export] traces_summary.csv: {len(rows) - 1} row(s) updated")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "logs" / "phoenix" / "export")
    ap.add_argument("--sessions", type=Path, default=ROOT / "logs" / "sessions" / "phoenix")
    ap.add_argument("--rebuild-sessions", action="store_true",
                    help="regenerate all daily summaries in --sessions from the whole database")
    ap.add_argument("--mark-current", action="store_true")
    ap.add_argument("--add-local-time", action="store_true",
                    help="one-off: add local-time fields to previously exported files")
    ap.add_argument("--txt", type=Path, default=ROOT / "logs" / "phoenix" / "export_txt")
    ap.add_argument("--make-txt", action="store_true",
                    help="regenerate readable per-day .txt files from the exported JSONL")
    a = ap.parse_args()
    try:
        if a.make_txt:
            rebuild_txt(a.out, a.txt)
        elif a.add_local_time:
            add_local_fields(a.out)
        elif a.rebuild_sessions:
            rebuild_sessions(a.db or default_db(), a.sessions)
        else:
            export(a.db or default_db(), a.out, a.mark_current, a.sessions)
    except Exception as exc:  # never break a launcher
        print(f"[phoenix-export] failed: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
