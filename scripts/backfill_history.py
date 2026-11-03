"""Backfill history files that older versions never wrote.

  1. data/crossexam_history/crossexam_store.json  <- every saved pipeline run
     that contains cross-examination rounds (via src.analysis.crossexam_history)
  2. data/crawl_history.jsonl                     <- scheduled regulatory crawls
     reconstructed from the "[Scheduler] ..." lines in logs/chainlit/*.log

Run from the project folder whose data should be filled (the working directory
is used for ``data/`` and ``logs/``):

    python <path-to>/scripts/backfill_history.py

Safe to re-run: runs already in the cross-exam store are refreshed in place and
reconstructed crawl entries (marked "backfilled") are regenerated; entries
written by the live application are never touched.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def backfill_crossexam() -> int:
    from src.analysis.crossexam_history import save_run_record

    n = 0
    for f in sorted(glob.glob("data/analysis_pipeline/run_*.json")):
        rid = os.path.basename(f)[:-5]
        if save_run_record(rid):
            n += 1
    print(f"[backfill] cross-exam history: {n} run(s) written to data/crossexam_history/crossexam_store.json")
    return n


_TS = r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})"


def backfill_crawls() -> int:
    starts, entries = {}, []
    for f in sorted(glob.glob("logs/chainlit/*_chainlit.log")):
        last_start, changes = None, False
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "[Scheduler]" not in line:
                    continue
                m = re.match(_TS, line)
                if not m:
                    continue
                ts = f"{m.group(1)}T{m.group(2)}"
                if "Starting scheduled regulatory crawl" in line:
                    last_start, changes = ts, False
                elif "Regulatory changes detected" in line:
                    changes = True
                else:
                    c = re.search(r"Regulatory crawl complete: (\d+)/(\d+) succeeded", line)
                    if c:
                        entries.append(
                            {
                                "last_full_crawl_date": m.group(1),
                                "last_full_crawl_timestamp": ts,
                                "trigger_source": "scheduler",
                                "started_at": last_start,
                                "succeeded": int(c.group(1)),
                                "total": int(c.group(2)),
                                "changes_detected": changes,
                                "backfilled": True,
                                "source_log": os.path.basename(f),
                            }
                        )
                        last_start, changes = None, False
    path = Path("data/crawl_history.jsonl")
    live = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not d.get("backfilled"):
                live.append(d)
    allr = sorted(entries + live, key=lambda d: d.get("last_full_crawl_timestamp", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in allr), encoding="utf-8")
    tmp.replace(path)
    print(f"[backfill] crawl history: {len(entries)} reconstructed + {len(live)} live entr(ies) -> {path}")
    return len(entries)


if __name__ == "__main__":
    backfill_crossexam()
    backfill_crawls()
