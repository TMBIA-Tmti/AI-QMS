"""
Taiwan Bulk Law Downloader — Standalone Verification Script
===========================================================

Downloads all active Taiwan medical device regulations from the
MOJ Open API, converts each to Markdown, saves them to docs/taiwan_laws/,
and prints a verification table.

Usage:
    python scripts/download_taiwan_bulk_laws.py
    python scripts/download_taiwan_bulk_laws.py --no-cache   # force fresh download
    python scripts/download_taiwan_bulk_laws.py --output docs/custom_dir
"""

import sys
import os
import io
import argparse
import time
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp950 encoding errors
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _verify_markdown(filepath: Path) -> dict:
    """Read a markdown file and return verification stats."""
    content = filepath.read_text(encoding="utf-8")
    lines   = content.splitlines()

    # Count actual article lines (lines starting with **第)
    article_lines = [l for l in lines if l.startswith("**第") and "條**" in l]
    chapter_lines = [l for l in lines if l.startswith("### 第")]
    has_history   = "## 沿革" in content
    has_articles  = "## 條文內容" in content
    char_count    = len(content)

    return {
        "articles":   len(article_lines),
        "chapters":   len(chapter_lines),
        "has_history": has_history,
        "has_articles": has_articles,
        "chars":      char_count,
        "ok":         char_count > 200 and has_articles,
    }


def main():
    parser = argparse.ArgumentParser(description="Download Taiwan medical device laws as Markdown")
    parser.add_argument("--no-cache",  action="store_true", help="Force fresh download (ignore cache)")
    parser.add_argument("--output",    default="docs/taiwan_laws", help="Output directory (default: docs/taiwan_laws)")
    args = parser.parse_args()

    use_cache  = not args.no_cache
    output_dir = Path(args.output)

    print("=" * 70)
    print("Taiwan Medical Device Law Bulk Downloader")
    print("Source: https://law.moj.gov.tw/api (MOJ Open API)")
    print("=" * 70)
    print(f"Output directory : {output_dir.resolve()}")
    print(f"Cache            : {'enabled' if use_cache else 'disabled (fresh download)'}")
    print()

    t_start = time.time()

    from src.services.taiwan_bulk_api import fetch_taiwan_laws_bulk

    print("Fetching laws from MOJ Bulk API …")
    results = fetch_taiwan_laws_bulk(
        use_cache=use_cache,
        save_individual_files=True,
        output_dir=output_dir,
    )

    elapsed = time.time() - t_start
    print(f"Download complete: {len(results)} laws in {elapsed:.1f}s")
    print()

    # ── Verification table ───────────────────────────────────────────────────
    print(f"{'pcode':<12} {'法規名稱':<35} {'條數':>5} {'字數':>7} {'狀態'}")
    print("-" * 70)

    all_ok = True
    md_files = sorted(output_dir.glob("*.md"))

    if not md_files:
        print("  ⚠️  No markdown files found in output directory!")
        sys.exit(1)

    for r in results:
        meta     = r.get("_law_metadata", {})
        pcode    = meta.get("pcode", "?")
        name     = r.get("name", "")[:33]
        md_path  = None

        # Find corresponding markdown file
        for f in md_files:
            if pcode in f.name:
                md_path = f
                break

        if md_path is None:
            print(f"  {pcode:<12} {name:<35} {'?':>5} {'?':>7}  ❌ 檔案未找到")
            all_ok = False
            continue

        stats = _verify_markdown(md_path)
        status = "✅" if stats["ok"] else "❌"
        if not stats["ok"]:
            all_ok = False

        print(
            f"  {pcode:<12} {name:<35} {stats['articles']:>5} "
            f"{stats['chars']:>7,}  {status}"
        )

    print("-" * 70)
    print(f"Total: {len(results)} files")
    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    if all_ok:
        print("✅ All markdown files verified — content is complete.")
    else:
        print("❌ Some files failed verification — check output above.")
        sys.exit(1)

    # Print file listing
    print()
    print(f"Files in {output_dir}:")
    for f in sorted(output_dir.glob("*.md")):
        size_kb = f.stat().st_size // 1024
        print(f"  {f.name}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
