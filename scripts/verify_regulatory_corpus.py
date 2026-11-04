"""Verify the crawled regulatory corpus: provenance, completeness, LightRAG recall.

Usage (project root):
    python scripts/verify_regulatory_corpus.py                  # all regions, no LLM
    python scripts/verify_regulatory_corpus.py --region "歐盟 (EU)"
    python scripts/verify_regulatory_corpus.py --recall 8       # also probe LightRAG

The report is written to data/regulations_verification/verification.{md,json}.
Exit code 1 when any document FAILS (so it can gate CI or a re-crawl).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", action="append", help="REGION_SITES name, repeatable (default: all)")
    ap.add_argument("--recall", type=int, default=0, metavar="N",
                    help="probe each indexed region's LightRAG graph with N passages (uses the LLM)")
    ap.add_argument("--out", default="data/regulations_verification")
    args = ap.parse_args()

    from src.services.regulatory_source_check import verify_region, write_report
    from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

    store = get_regulatory_markdown_store()
    regions = args.region or store.get_all_regions()
    results = {r: verify_region(r, store) for r in regions}

    recall: dict = {}
    if args.recall:
        from src.services.lightrag_regulatory import has_region_index, measure_recall

        async def _run() -> None:
            for r in regions:
                if has_region_index(r):
                    recall[r] = await measure_recall(r, sample=args.recall)
                    print(f"recall {r}: {recall[r]['hits']}/{recall[r]['probes']}")

        asyncio.run(_run())

    md = write_report(results, Path(args.out), recall)
    n_fail = sum(1 for cs in results.values() for c in cs if c.status == "fail")
    n_warn = sum(1 for cs in results.values() for c in cs if c.status == "warn")
    n = sum(len(cs) for cs in results.values())
    print(f"{n} documents: {n - n_fail - n_warn} ok, {n_warn} warn, {n_fail} FAIL -> {md}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
