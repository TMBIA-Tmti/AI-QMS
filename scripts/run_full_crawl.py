"""Standalone script: crawl all 32 regions, annotate QMS sections, save to markdown storage.

Usage:
    python scripts/run_full_crawl.py               # standard full crawl
    python scripts/run_full_crawl.py --check-updates  # M7: also detect version updates via DDG
"""
import asyncio
import sys
import os
import json
import logging
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_full_crawl")


async def main():
    from src.services.regulatory_crawler import get_regulatory_crawler, REGION_SITES
    from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

    total_sites = sum(len(v) for v in REGION_SITES.values())
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting full crawl: {len(REGION_SITES)} regions, {total_sites} sites")

    crawler = get_regulatory_crawler()
    store = get_regulatory_markdown_store()

    try:
        results = await crawler.crawl_all_regions()
    finally:
        await crawler.close()

    summary = results.get("summary", {})
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Crawl done: "
          f"{summary.get('success_count',0)} success, "
          f"{summary.get('failed_count',0)} failed, "
          f"{summary.get('crawl_duration_seconds',0):.1f}s")

    save = store.save_from_crawl_results(results)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {save.get('saved_count',0)}, "
          f"Skipped: {save.get('skipped_count',0)}, "
          f"Replaced: {save.get('replaced_count',0)} old docs")

    # Write detailed report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "last_crawl_report.json")
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": summary,
        "save_result": save,
        "per_site": [
            {
                "region": r.get("region", ""),
                "agency": r.get("agency", ""),
                "status": r.get("crawl_status", ""),
                "source": r.get("content_source", ""),
                "lines": len(r.get("content_markdown", "").splitlines()),
                "chars": len(r.get("content_markdown", "")),
                "failure": r.get("failure_reason", ""),
                "duration_s": r.get("crawl_duration_seconds", 0),
            }
            for r in results.get("results", [])
        ],
    }
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report: {os.path.abspath(report_path)}")

    # Quick per-country table
    print("\n--- Per-site results ---")
    print(f"{'REGION':<24} {'AGENCY':<26} {'STATUS':<8} {'SRC':<12} {'LINES':>6}  FAILURE")
    print("-" * 100)
    for r in report["per_site"]:
        region = r["region"][:23]
        agency = r["agency"][:25]
        status = r["status"][:7]
        src = r["source"][:11] if r["source"] else "-"
        lines = r["lines"]
        failure = (r["failure"] or "")[:50]
        print(f"{region:<24} {agency:<26} {status:<8} {src:<12} {lines:>6}  {failure}")

    return report


async def _check_regulatory_updates(results: dict) -> None:
    """M7: DDG news scan — detect if any regulation has been updated since the note was written."""
    from src.services.regulatory_crawler import _ddgs_search
    import re

    year_re = re.compile(r"\b20(2[3-9]|3\d)\b")
    current_year = datetime.utcnow().year
    flagged = 0

    print("\n[UPDATE CHECK] Scanning for regulatory version changes via DuckDuckGo…")
    for r in results.get("results", []):
        if r.get("crawl_status") != "success":
            continue
        agency = r.get("agency", "")
        region = r.get("region", "")
        note = r.get("note", "") or ""

        query = f"{region} {agency} regulation update amendment 2025 2026"
        try:
            hits = await asyncio.to_thread(_ddgs_search, query, 3)
        except Exception:
            continue

        for hit in hits:
            body = hit.get("body", "") + hit.get("title", "")
            years_found = [int(y) for y in year_re.findall(body)]
            if any(y > current_year - 1 for y in years_found):
                # Check if note already mentions this year
                if not any(str(y) in note for y in years_found):
                    print(
                        f"  [UPDATE_DETECTED] {region}/{agency} — "
                        f"DDG snippet mentions {max(years_found)}: "
                        f"{body[:120]}"
                    )
                    flagged += 1
                    break

    if flagged == 0:
        print("[UPDATE CHECK] No new updates detected.")
    else:
        print(f"[UPDATE CHECK] {flagged} potential update(s) found — review notes above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-QMS full regulatory crawl")
    parser.add_argument(
        "--check-updates",
        action="store_true",
        default=False,
        help="M7: after crawl, scan DDG for regulation version updates",
    )
    args = parser.parse_args()

    async def _run():
        report = await main()
        if args.check_updates and report:
            await _check_regulatory_updates(report)

    asyncio.run(_run())
