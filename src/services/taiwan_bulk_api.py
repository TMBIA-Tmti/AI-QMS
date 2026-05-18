"""
Taiwan MOJ Open API — Bulk Law Downloader
==========================================

Downloads the complete Taiwan medical device regulatory corpus from the
Ministry of Justice Open API (https://law.moj.gov.tw/api) in a single
ZIP download, filters the QMS-relevant laws, and converts each law to
structured Markdown.

API endpoints:
  ChOrder: https://law.moj.gov.tw/api/ch/order/json  (~25 MB ZIP, 10 416 orders)
  ChLaw:   https://law.moj.gov.tw/api/ch/law/json   (~6 MB ZIP,  1 344 laws)

Filter criteria (active laws only):
  - ChOrder: LawCategory contains '衛生福利部＞食品藥物管理目'
             AND '醫療器材' in LawName
             AND LawAbandonNote != '廢'
  - ChLaw:   '醫療器材' in LawName
             AND LawAbandonNote != '廢'

Result schema (compatible with regulatory_crawler crawled_texts):
  {
    "region":                 "台灣 (Taiwan)",
    "agency":                 "TFDA-L0030116",
    "name":                   "醫療器材品質管理系統準則",
    "url":                    "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0030116",
    "crawl_status":           "success",
    "content_source":         "bulk_api",
    "content_markdown":       "...",
    "title":                  "醫療器材品質管理系統準則",
    "note":                   "...",
    "crawl_duration_seconds": 0.0,
    "crawl_timestamp":        "...",
    "doc_type":               "primary",
    "_law_metadata": {
        "pcode":           "L0030116",
        "law_level":       "命令",
        "modified_date":   "20210414",
        "abandon_note":    "",
        "has_eng_version": "Y",
        "eng_name":        "Medical Device Quality Management System Regulations",
        "attachments":     [...],
        "zip_source":      "ChOrder",
    },
  }
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────────
_ORDER_URL = "https://law.moj.gov.tw/api/ch/order/json"
_LAW_URL   = "https://law.moj.gov.tw/api/ch/law/json"

# ── Cache configuration ───────────────────────────────────────────────────────
_CACHE_DIR        = Path("data/taiwan_bulk_cache")
_CACHE_TTL_DAYS   = 7          # re-download after 7 days (API updates weekly on Fridays)
_ORDER_CACHE_FILE = _CACHE_DIR / "ChOrder.json.zip"
_LAW_CACHE_FILE   = _CACHE_DIR / "ChLaw.json.zip"

# ── Filter criteria ───────────────────────────────────────────────────────────
_TFDA_CATEGORY    = "衛生福利部＞食品藥物管理目"
_MD_KEYWORD       = "醫療器材"
_ABANDON_FLAG     = "廢"

# Laws with these pcodes get doc_type="primary" (core QMS regulations)
_QMS_PRIMARY_PCODES: frozenset[str] = frozenset({
    "L0030116",  # 醫療器材品質管理系統準則         (ISO 13485 equivalent, 86 art.)
    "L0030112",  # 醫療器材品質管理系統檢查及製造許可核發辦法 (13 art.)
    "L0030106",  # 醫療器材管理法                   (parent law, 94 art.)
    "L0030110",  # 醫療器材製造業者設置標準          (10 art.)
})


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_taiwan_laws_bulk(
    use_cache: bool = True,
    save_individual_files: bool = False,
    output_dir: Optional[str | Path] = None,
) -> list[dict]:
    """Download Taiwan medical device laws and return as crawled_text dicts.

    Args:
        use_cache:              Use locally cached ZIP if < _CACHE_TTL_DAYS old.
        save_individual_files:  If True, also write one .md per law to output_dir.
        output_dir:             Directory for individual .md files (required when
                                save_individual_files=True).

    Returns:
        List of dicts compatible with regulatory_crawler crawled_texts schema.
    """
    t0 = time.time()
    laws: list[dict] = []

    # Download / load both ZIPs
    order_laws = _load_laws_from_zip(_ORDER_URL, _ORDER_CACHE_FILE, "ChOrder", use_cache)
    law_laws   = _load_laws_from_zip(_LAW_URL,   _LAW_CACHE_FILE,   "ChLaw",   use_cache)

    # Filter relevant laws
    filtered_order = _filter_laws(order_laws, zip_source="ChOrder")
    filtered_law   = _filter_laws(law_laws,   zip_source="ChLaw")

    all_laws = filtered_order + filtered_law
    logger.info(
        f"taiwan_bulk_api: {len(filtered_order)} orders + {len(filtered_law)} laws "
        f"= {len(all_laws)} total active medical device regulations"
    )

    if save_individual_files and output_dir:
        _save_individual_markdowns(all_laws, Path(output_dir))

    # Build crawled_text result list
    for law in all_laws:
        result = _law_to_crawled_result(law)
        laws.append(result)

    elapsed = round(time.time() - t0, 2)
    logger.info(f"taiwan_bulk_api: completed in {elapsed}s, {len(laws)} results")
    return laws


def get_law_metadata_index(results: list[dict]) -> dict[str, dict]:
    """Build pcode → metadata dict from fetch_taiwan_laws_bulk results.

    Used by merge_profiles() to detect amendments and deprecations.
    """
    index: dict[str, dict] = {}
    for r in results:
        meta = r.get("_law_metadata", {})
        pcode = meta.get("pcode", "")
        if pcode:
            index[pcode] = meta
    return index


def law_to_markdown(law: dict, zip_source: str = "") -> str:
    """Convert a single law JSON record to structured Markdown."""
    return _law_to_markdown(law, zip_source)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cache_is_fresh(cache_file: Path) -> bool:
    if not cache_file.exists():
        return False
    age_days = (time.time() - cache_file.stat().st_mtime) / 86400
    return age_days < _CACHE_TTL_DAYS


def _download_zip(url: str, dest: Path) -> None:
    """Download a ZIP from url to dest.

    SSL verification is disabled for law.moj.gov.tw because the site uses
    a certificate that lacks a Subject Key Identifier extension, which causes
    verification failures on some platforms (Windows + Python 3.12+).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        import httpx
        with httpx.Client(timeout=180, follow_redirects=True, verify=False) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
    except ImportError:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=180) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())

    logger.info(f"taiwan_bulk_api: downloaded {dest.name} ({dest.stat().st_size // 1024} KB)")


def _load_laws_from_zip(url: str, cache_file: Path, json_name: str, use_cache: bool) -> list[dict]:
    """Download (or restore from cache) and parse a MOJ bulk ZIP."""
    if use_cache and _cache_is_fresh(cache_file):
        logger.info(f"taiwan_bulk_api: using cached {cache_file.name}")
    else:
        logger.info(f"taiwan_bulk_api: downloading {url} …")
        _download_zip(url, cache_file)

    try:
        with zipfile.ZipFile(cache_file) as zf:
            json_filename = f"{json_name}.json"
            with zf.open(json_filename) as jf:
                raw = jf.read()
                # Strip UTF-8 BOM if present
                if raw[:3] == b"\xef\xbb\xbf":
                    raw = raw[3:]
                data = json.loads(raw.decode("utf-8"))
        laws = data.get("Laws", [])
        logger.info(f"taiwan_bulk_api: {json_name} contains {len(laws)} records")
        return laws
    except Exception as e:
        logger.error(f"taiwan_bulk_api: failed to parse {cache_file.name}: {e}")
        return []


def _filter_laws(laws: list[dict], zip_source: str) -> list[dict]:
    """Filter to active medical device laws from TFDA."""
    result = []
    for law in laws:
        name    = law.get("LawName", "")
        cat     = law.get("LawCategory", "")
        abandon = law.get("LawAbandonNote", "")

        if abandon == _ABANDON_FLAG:
            continue
        if _MD_KEYWORD not in name:
            continue
        if zip_source == "ChOrder" and _TFDA_CATEGORY not in cat:
            continue

        law["_zip_source"] = zip_source
        result.append(law)

    return result


def _extract_pcode(url: str) -> str:
    """Extract pcode from a law URL like ...?pcode=L0030116."""
    if "pcode=" in url:
        return url.split("pcode=")[-1].strip()
    return ""


def _law_to_markdown(law: dict, zip_source: str = "") -> str:
    """Convert a law JSON record to structured Markdown."""
    name         = law.get("LawName", "")
    level        = law.get("LawLevel", "")
    url          = law.get("LawURL", "")
    category     = law.get("LawCategory", "")
    modified     = law.get("LawModifiedDate", "")
    effective    = law.get("LawEffectiveDate", "")
    effective_note = law.get("LawEffectiveNote", "")
    has_eng      = law.get("LawHasEngVersion", "")
    eng_name     = law.get("EngLawName", "")
    histories    = law.get("LawHistories", "") or ""
    foreword     = law.get("LawForeword", "") or ""
    attachments  = law.get("LawAttachements") or []
    articles     = law.get("LawArticles") or []
    pcode        = _extract_pcode(url)

    # Format date
    def fmt_date(d: str) -> str:
        if len(d) == 8:
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return d

    lines: list[str] = []

    # ── Header block ─────────────────────────────────────────────────────────
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"**法規位階**: {level}  ")
    lines.append(f"**pcode**: {pcode}  ")
    lines.append(f"**法規類別**: {category}  ")
    lines.append(f"**最後異動**: {fmt_date(modified)}  ")
    if effective:
        lines.append(f"**生效日期**: {fmt_date(effective)}  ")
    if effective_note:
        lines.append(f"**生效說明**: {effective_note}  ")
    if eng_name:
        lines.append(f"**英文名稱**: {eng_name}  ")
    if has_eng == "Y":
        lines.append(f"**英文版**: https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode={pcode}  ")
    lines.append(f"**法規網址**: {url}  ")
    if attachments:
        for att in attachments:
            fname = att.get("FileName", "")
            furl  = att.get("FileURL", "")
            if fname and furl:
                lines.append(f"**附件**: [{fname}]({furl})  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Histories ─────────────────────────────────────────────────────────────
    if histories.strip():
        lines.append("## 沿革")
        lines.append("")
        lines.append(histories.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Foreword ─────────────────────────────────────────────────────────────
    if foreword.strip():
        lines.append("## 前言")
        lines.append("")
        lines.append(foreword.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Articles ─────────────────────────────────────────────────────────────
    lines.append("## 條文內容")
    lines.append("")

    for art in articles:
        art_type    = art.get("ArticleType", "A")
        art_no      = art.get("ArticleNo", "")
        art_content = art.get("ArticleContent", "")

        if art_type == "C":
            # Chapter/section heading
            heading = art_content.strip()
            lines.append(f"### {heading}")
            lines.append("")
        else:
            # Regular article
            no_clean = art_no.strip()
            content  = art_content.strip()
            if no_clean:
                lines.append(f"**{no_clean}**")
                lines.append("")
            if content:
                lines.append(content)
                lines.append("")

    return "\n".join(lines)


def _law_to_crawled_result(law: dict) -> dict:
    """Convert a filtered law dict to a regulatory_crawler compatible result dict."""
    name         = law.get("LawName", "")
    url          = law.get("LawURL", "")
    pcode        = _extract_pcode(url)
    level        = law.get("LawLevel", "")
    modified     = law.get("LawModifiedDate", "")
    abandon      = law.get("LawAbandonNote", "")
    has_eng      = law.get("LawHasEngVersion", "")
    eng_name     = law.get("EngLawName", "")
    attachments  = law.get("LawAttachements") or []
    zip_source   = law.get("_zip_source", "")

    agency   = f"TFDA-{pcode}" if pcode else "TFDA-Unknown"
    doc_type = "primary" if pcode in _QMS_PRIMARY_PCODES else "qms_guidance"

    content_md = _law_to_markdown(law, zip_source)

    note_parts = [f"pcode={pcode}", f"level={level}", f"modified={modified}"]
    if has_eng == "Y":
        note_parts.append(f"eng={eng_name}")
    if attachments:
        note_parts.append(f"attachments={len(attachments)}")

    return {
        "region":                 "台灣 (Taiwan)",
        "agency":                 agency,
        "agency_name":            name,
        "name":                   name,
        "url":                    url,
        "crawl_status":           "success",
        "content_source":         "bulk_api",
        "content_markdown":       content_md,
        "title":                  name,
        "note":                   "MOJ Bulk API — " + ", ".join(note_parts),
        "crawl_duration_seconds": 0.0,
        "crawl_timestamp":        datetime.now(timezone.utc).isoformat(),
        "doc_type":               doc_type,
        "failure_reason":         None,
        "_law_metadata": {
            "pcode":           pcode,
            "law_level":       level,
            "modified_date":   modified,
            "abandon_note":    abandon,
            "has_eng_version": has_eng,
            "eng_name":        eng_name,
            "attachments":     attachments,
            "zip_source":      zip_source,
        },
    }


def _safe_filename(name: str) -> str:
    """Convert a law name to a safe filesystem filename."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789一-鿿-_")
    result = []
    for ch in name:
        if ch.isalnum() or '一' <= ch <= '鿿' or ch in ('-', '_'):
            result.append(ch)
        else:
            result.append('_')
    cleaned = ''.join(result).strip('_')
    return cleaned[:80] if cleaned else "law"


def _save_individual_markdowns(laws: list[dict], output_dir: Path) -> None:
    """Write one .md file per law into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for law in laws:
        name     = law.get("LawName", "unknown")
        url      = law.get("LawURL", "")
        pcode    = _extract_pcode(url)
        zip_src  = law.get("_zip_source", "")
        content  = _law_to_markdown(law, zip_src)
        articles = law.get("LawArticles") or []

        safe_name = _safe_filename(name)
        filename  = f"{pcode}-{safe_name}.md" if pcode else f"{safe_name}.md"
        filepath  = output_dir / filename

        filepath.write_text(content, encoding="utf-8")
        saved += 1
        logger.info(
            f"  Saved: {filename}  ({len(articles)} articles, {len(content)} chars)"
        )

    logger.info(f"taiwan_bulk_api: saved {saved} markdown files → {output_dir}")
