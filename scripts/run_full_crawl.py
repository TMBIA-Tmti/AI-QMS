"""Standalone script: crawl all 32 regions, annotate QMS sections, save to markdown storage."""
import asyncio
import sys
import os
import json
import logging
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


if __name__ == "__main__":
    asyncio.run(main())
