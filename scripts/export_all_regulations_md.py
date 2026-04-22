"""
一次性腳本：爬取所有地區 QMS 法條並輸出為 Markdown 檔案。
用途：讓使用者確認每個國家爬到的是正確的法條內容，而非新聞/公告/入口頁。

輸出：
  - docs/regulations_check/<地區>.md  （每個地區一個檔案）
  - docs/regulations_check/_SUMMARY.md  （彙總表：地區 / agency / URL / 爬取狀態 / 內容來源）

執行方式：
  python scripts/export_all_regulations_md.py

可選：只跑特定地區：
  python scripts/export_all_regulations_md.py "中國 (China)" "印度 (India)"
"""

import asyncio
import sys
import os
import re
from pathlib import Path
from datetime import datetime

# 確保 src 在 import 路徑裡
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.regulatory_crawler import (
    AsyncRegulatoryUpdateCrawler,
    REGION_SITES,
)

OUT_DIR = Path(__file__).parent.parent / "docs" / "regulations_check"


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w一-鿿\-]", "_", name)[:60]


async def main(selected: list[str] | None = None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    regions = selected or list(REGION_SITES.keys())

    print(f"[export] 開始爬取 {len(regions)} 個地區，輸出到 {OUT_DIR}")
    crawler = AsyncRegulatoryUpdateCrawler()
    try:
        result = await crawler.crawl_selected_regions(regions)
    finally:
        await crawler.close()

    results: list[dict] = result.get("results", [])
    summary_rows = []

    # 把結果按地區分組，每地區一個 .md 檔
    by_region: dict[str, list[dict]] = {}
    for r in results:
        region = r.get("region", "Unknown")
        by_region.setdefault(region, []).append(r)

    for region, entries in by_region.items():
        fname = OUT_DIR / f"{_safe_filename(region)}.md"
        lines = [f"# {region}\n\n"]
        lines.append(f"爬取時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n")

        for e in entries:
            agency = e.get("agency", "")
            url = e.get("url", "")
            status = e.get("crawl_status", "unknown")
            source = e.get("content_source", "")
            content = e.get("content_markdown", "").strip()
            note = e.get("note", "")
            failure = e.get("failure_reason", "")

            lines.append(f"## {agency}\n\n")
            lines.append(f"**URL**: {url}  \n")
            lines.append(f"**爬取狀態**: `{status}`  \n")
            lines.append(f"**內容來源**: `{source}`  \n")
            if note:
                lines.append(f"**備註**: {note}  \n")
            if failure:
                lines.append(f"**失敗原因**: {failure}  \n")
            lines.append("\n")

            if content:
                lines.append(content)
            else:
                lines.append("_（無法取得內容）_")
            lines.append("\n\n---\n\n")

            # 彙總表一行
            status_icon = "✅" if status == "success" else "❌"
            source_tag = f"[{source}]" if source else ""
            summary_rows.append(
                f"| {status_icon} | {region} | {agency} | `{source_tag}` | {url} |"
            )

        fname.write_text("".join(lines), encoding="utf-8")
        print(f"  已寫入: {fname.name}")

    # 彙總表
    summary_lines = [
        "# 全球 QMS 法條爬取結果彙總\n\n",
        f"爬取時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
        f"地區數: {len(by_region)} | Agency 數: {len(results)}\n\n",
        "| 狀態 | 地區 | Agency | 來源 | URL |\n",
        "|------|------|--------|------|-----|\n",
    ]
    summary_lines += [r + "\n" for r in summary_rows]

    summary_file = OUT_DIR / "_SUMMARY.md"
    summary_file.write_text("".join(summary_lines), encoding="utf-8")
    print(f"\n[export] 彙總: {summary_file}")

    # 統計
    success = sum(1 for r in results if r.get("crawl_status") == "success")
    prewritten = sum(1 for r in results if r.get("content_source") == "pre-written")
    live = sum(1 for r in results if r.get("content_source") == "live")
    failed = len(results) - success
    print(f"\n結果: 成功 {success}/{len(results)}  |  live={live}  pre-written={prewritten}  失敗={failed}")


if __name__ == "__main__":
    selected = sys.argv[1:] or None
    asyncio.run(main(selected))
