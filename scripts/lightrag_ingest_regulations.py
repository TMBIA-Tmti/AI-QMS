"""Index crawled national regulations into per-country LightRAG graphs.

Usage (run from the project root):
    python scripts/lightrag_ingest_regulations.py --list
    python scripts/lightrag_ingest_regulations.py --region "新加坡 (Singapore)"
    python scripts/lightrag_ingest_regulations.py --all --max-docs 20

The run is resumable: documents already indexed (same content hash) are skipped.
Entity extraction is slow on local models (minutes per document); start with a
small region and check ``data/lightrag/regulatory/<ID>/`` before running --all.

Environment:
    LIGHTRAG_LLM_MODEL       extraction model (default: provider default)
    LIGHTRAG_LLM_MAX_TOKENS  per-call output cap (default 4096)
    LIGHTRAG_LLM_MAX_ASYNC   LLM concurrency (default 2; use 1 for local GPUs)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def _main(args: argparse.Namespace) -> int:
    from src.services.lightrag_regulatory import (
        ingest_region,
        list_region_documents,
        load_manifest,
    )
    from src.storage.regulatory_markdown_storage import get_regulatory_markdown_store

    store = get_regulatory_markdown_store()
    regions = args.region or (store.get_all_regions() if args.all else [])

    if args.list or not regions:
        print(f"{'region':<40}{'docs':>6}{'indexed':>9}")
        for r in store.get_all_regions():
            print(f"{r:<40}{len(list_region_documents(r)):>6}{len(load_manifest(r)):>9}")
        return 0

    exit_code = 0
    for region in regions:
        print(f"== {region}")
        stats = await ingest_region(
            region,
            max_docs=args.max_docs,
            progress=lambda i, n, d: print(f"   [{i}/{n}] {d}", flush=True),
        )
        print(f"   -> {stats}")
        if stats["errors"]:
            exit_code = 1
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", action="append", help="REGION_SITES name, repeatable")
    ap.add_argument("--all", action="store_true", help="every region in the registry")
    ap.add_argument("--list", action="store_true", help="show document / indexed counts and exit")
    ap.add_argument("--max-docs", type=int, default=None, help="max NEW documents per region this run")
    args = ap.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
