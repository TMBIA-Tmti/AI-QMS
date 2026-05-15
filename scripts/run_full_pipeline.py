"""
AI-QMS — Full Regulatory Pipeline Runner
=========================================

Executes the complete two-phase pipeline:
  Phase 1a: Crawl all (or selected) regions → raw Markdown
  Phase 1b: LLM analysis → RegulationProfile JSON (parallel, up to 4 concurrent)
  Phase 2:  Generate ISO 13485 cross-country HTML comparison table

Usage:
  python scripts/run_full_pipeline.py
  python scripts/run_full_pipeline.py --regions "台灣 (Taiwan)" "美國 (USA)"
  python scripts/run_full_pipeline.py --skip-crawl          # use existing crawl cache
  python scripts/run_full_pipeline.py --skip-analysis       # skip LLM, only gen HTML
  python scripts/run_full_pipeline.py --only-html           # Phase 2 only
  python scripts/run_full_pipeline.py --provider anthropic --model claude-sonnet-4-6

Environment variables:
  ANTHROPIC_API_KEY / OPENAI_API_KEY — set before running for cloud providers
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


async def _run_pipeline(args: argparse.Namespace) -> None:
    t_start = time.time()

    # ── Import project modules ────────────────────────────────────────────────
    from src.services.regulatory_crawler import (
        AsyncRegulatoryUpdateCrawler,
        REGION_SITES,
    )
    from src.analysis.regulation_analyzer import analyze_regulation_with_llm
    from src.analysis.compliance_rules import save_crawled_regulation, load_all_crawled_regulations
    from src.analysis.cross_country_html import generate_to_file
    from pathlib import Path as _Path

    # Determine regions to process
    all_regions = list(REGION_SITES.keys())
    regions = args.regions if args.regions else all_regions
    invalid = [r for r in regions if r not in REGION_SITES]
    if invalid:
        logger.error(f"Unknown region(s): {invalid}")
        logger.info(f"Available: {all_regions}")
        sys.exit(1)

    logger.info(f"Pipeline: {len(regions)} region(s), provider={args.provider}, model={args.model}")

    crawl_results: dict[str, list[dict]] = {}

    # ── Phase 1a: Crawl ───────────────────────────────────────────────────────
    if not args.skip_crawl and not args.only_html:
        logger.info("=" * 60)
        logger.info("PHASE 1a: Crawling regulatory websites")
        logger.info("=" * 60)
        t_crawl = time.time()

        crawler = AsyncRegulatoryUpdateCrawler()
        try:
            raw_results = await crawler.crawl_regions(regions)
        finally:
            await crawler.close()

        # Group by region
        for r in raw_results:
            region = r.get("region", "")
            if region not in crawl_results:
                crawl_results[region] = []
            if r.get("crawl_status") == "success" and r.get("content_markdown"):
                crawl_results[region].append(r)

        success_total = sum(len(v) for v in crawl_results.values())
        elapsed_crawl = time.time() - t_crawl
        logger.info(
            f"Crawl complete: {success_total} successful site(s) across "
            f"{len([r for r,v in crawl_results.items() if v])} region(s) "
            f"in {elapsed_crawl:.1f}s"
        )
    else:
        logger.info("Skipping crawl phase (--skip-crawl or --only-html)")

    # ── Phase 1b: LLM Analysis ────────────────────────────────────────────────
    if not args.skip_analysis and not args.only_html and crawl_results:
        logger.info("=" * 60)
        logger.info("PHASE 1b: LLM analysis → RegulationProfile JSON")
        logger.info("=" * 60)
        t_analysis = time.time()

        # Set up LLM
        try:
            from src.llm_providers import create_provider_manager, setup_api_key
            setup_api_key(args.provider, args.api_key or "")
            manager = create_provider_manager(args.provider)
            is_local = manager.current_provider.get("is_local", False)
        except Exception as exc:
            logger.error(f"Failed to initialise LLM provider '{args.provider}': {exc}")
            sys.exit(1)

        # Parallel analysis: 4 concurrent for cloud, 1 for local
        concurrency = 1 if is_local else 4
        sem = asyncio.Semaphore(concurrency)
        logger.info(f"Analysis concurrency: {concurrency} (is_local={is_local})")

        async def _analyse_region(region: str) -> tuple[str, bool]:
            texts = crawl_results.get(region, [])
            if not texts:
                logger.warning(f"  [{region}] No crawl data — skipping analysis")
                return region, False

            async with sem:
                logger.info(f"  [{region}] Starting LLM analysis ({len(texts)} source(s))...")
                t0 = time.time()
                try:
                    profile = await analyze_regulation_with_llm(
                        region_name=region,
                        crawled_texts=texts,
                        llm_completion_fn=manager.completion,
                        model=args.model,
                        send_progress_fn=None,
                        provider_id=args.provider,
                        is_local_override=is_local,
                    )
                    elapsed = time.time() - t0
                    if profile:
                        non_na = sum(1 for m in profile.iso_mapped.values() if m.status.value != "na")
                        logger.info(
                            f"  [{region}] ✅ Done in {elapsed:.1f}s — "
                            f"{non_na}/{len(profile.iso_mapped)} clauses mapped, "
                            f"quality={profile.content_quality}"
                        )
                        return region, True
                    else:
                        logger.warning(f"  [{region}] ⚠️ Analysis returned None ({elapsed:.1f}s)")
                        return region, False
                except Exception as exc:
                    logger.error(f"  [{region}] ❌ Error: {exc}")
                    return region, False

        analysis_regions = [r for r in regions if r in crawl_results]
        results = await asyncio.gather(*[_analyse_region(r) for r in analysis_regions])

        ok_count = sum(1 for _, ok in results if ok)
        elapsed_analysis = time.time() - t_analysis
        logger.info(
            f"Analysis complete: {ok_count}/{len(analysis_regions)} profiles saved "
            f"in {elapsed_analysis:.1f}s"
        )

    # ── Phase 2: HTML Table ───────────────────────────────────────────────────
    if not args.skip_html:
        logger.info("=" * 60)
        logger.info("PHASE 2: Generating cross-country HTML comparison table")
        logger.info("=" * 60)

        # Load all available profiles (including ones not re-analysed this run)
        try:
            load_all_crawled_regulations()
        except Exception:
            pass

        output_path = _Path(args.output)
        path = generate_to_file(output_path=output_path)
        logger.info(f"HTML table written → {path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    total_elapsed = time.time() - t_start
    logger.info("=" * 60)
    logger.info(f"Pipeline complete in {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    logger.info("=" * 60)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-QMS Full Regulatory Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--regions", nargs="+", metavar="REGION",
        help='Region names to process (e.g. "台灣 (Taiwan)" "美國 (USA)"). Default: all.'
    )
    parser.add_argument(
        "--provider", default="ollama",
        help="LLM provider ID: ollama | anthropic | openai | lmstudio (default: ollama)"
    )
    parser.add_argument(
        "--model", default="default",
        help='LLM model name (default: "default" — uses provider default)'
    )
    parser.add_argument(
        "--api-key", default="", metavar="KEY",
        help="API key for cloud provider (or set via environment variable)"
    )
    parser.add_argument(
        "--skip-crawl", action="store_true",
        help="Skip Phase 1a (crawl) — use existing crawl cache"
    )
    parser.add_argument(
        "--skip-analysis", action="store_true",
        help="Skip Phase 1b (LLM analysis)"
    )
    parser.add_argument(
        "--skip-html", action="store_true",
        help="Skip Phase 2 (HTML table generation)"
    )
    parser.add_argument(
        "--only-html", action="store_true",
        help="Run Phase 2 only (load existing profiles → generate HTML)"
    )
    parser.add_argument(
        "--output", default="data/cross_country_comparison.html", metavar="PATH",
        help="Output path for HTML table (default: data/cross_country_comparison.html)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_run_pipeline(args))
