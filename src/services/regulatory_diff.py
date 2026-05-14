"""
AI-QMS — Regulatory Content Diff Utilities
===========================================

Detects changes between crawl runs for regulatory documents stored in
regulatory_markdown_storage.  Provides:

  - Article-level diff for EU MDR core law (EU-MDR-2017-745-PDF, EUR-Lex-MDR-HTML)
  - MDCG guidance change count
  - Per-country X/N-sites-changed summary for all other regions
"""

import re
import difflib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Agencies whose content should be diffed at article level
EU_MDR_CORE_AGENCIES: frozenset = frozenset(
    {"EUR-Lex-MDR-CELLAR", "EUR-Lex-MDR-UK", "EU-MDR-2017-745-PDF", "EUR-Lex-MDR-HTML"}
)

# Agency prefix that identifies MDCG guidance documents
_MDCG_AGENCY_PREFIX = "MDCG"

# Regex that matches a standalone article heading line, e.g. "Article 10"
# Annex headings like "ANNEX I" are also captured.
_ARTICLE_RE = re.compile(
    r"^(Article\s+\d+|ANNEX\s+[IVXLC]+)\b",
    re.IGNORECASE,
)


def _split_by_articles(content: str) -> dict[str, str]:
    """Split Markdown content into a dict keyed by article/annex heading.

    Content before the first heading is stored under key '__preamble__'.
    The body starts after the first '---' separator (skips the auto-header).
    """
    # Skip the auto-generated file header (everything up to the first blank
    # line after the '---' separator that ends the header block).
    body_start = content.find("\n---\n\n")
    body = content[body_start + 6:] if body_start != -1 else content

    sections: dict[str, str] = {}
    current_key = "__preamble__"
    current_lines: list[str] = []

    for line in body.splitlines():
        m = _ARTICLE_RE.match(line.strip())
        if m:
            sections[current_key] = "\n".join(current_lines)
            # Normalise key: "Article  10" → "Article 10"
            current_key = re.sub(r"\s+", " ", line.strip().split("—")[0].strip())
            current_lines = [line]
        else:
            current_lines.append(line)

    sections[current_key] = "\n".join(current_lines)
    return sections


def compute_article_diff(old_content: str, new_content: str) -> list[str]:
    """Return a list of article/annex names whose text changed between two versions.

    Args:
        old_content: Full Markdown text from the previous crawl (including header).
        new_content: Full Markdown text from the new crawl (including header).

    Returns:
        List of changed article names, e.g. ["Article 10", "ANNEX IX"].
        Empty list means no meaningful content change was detected.
    """
    if not old_content or not new_content:
        return []

    old_sections = _split_by_articles(old_content)
    new_sections = _split_by_articles(new_content)

    changed: list[str] = []
    all_keys = set(old_sections) | set(new_sections)

    for key in sorted(all_keys):
        if key == "__preamble__":
            continue
        old_text = old_sections.get(key, "")
        new_text = new_sections.get(key, "")
        if old_text != new_text:
            # Use SequenceMatcher ratio to suppress near-identical noise
            ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()
            if ratio < 0.995:  # >0.5% difference required
                changed.append(key)

    return changed


def build_change_summary(save_result: dict, crawl_results: dict) -> dict:
    """Build a structured change summary from save_result and crawl_results.

    Separates EU into MDR-core vs MDCG, aggregates other regions as X/N.

    Args:
        save_result:   dict returned by RegulatoryMarkdownStorage.save_from_crawl_results()
                       Must contain 'per_doc_changes' list added by the modified save method.
        crawl_results: dict returned by crawler.crawl_all/selected_regions().

    Returns:
        {
            'eu': {
                'mdr_core': [{'agency': str, 'changed': bool, 'articles': [str], 'first_baseline': bool}],
                'mdcg': {'changed_count': int, 'total': int, 'first_baseline_count': int},
            },
            'countries': {
                '<region>': {'changed': int, 'total': int, 'first_baseline': int}
            },
            'has_any_change': bool,
        }
    """
    per_doc = save_result.get("per_doc_changes", [])

    eu_mdr_core: list[dict] = []
    eu_mdcg_changed = 0
    eu_mdcg_total = 0
    eu_mdcg_first_baseline = 0
    countries: dict[str, dict] = {}

    for entry in per_doc:
        region: str = entry.get("region", "")
        agency: str = entry.get("agency", "")
        changed: bool = entry.get("content_changed", False)
        first_baseline: bool = entry.get("first_baseline", False)

        if region == "歐盟 (EU)":
            if agency in EU_MDR_CORE_AGENCIES:
                eu_mdr_core.append({
                    "agency": agency,
                    "changed": changed,
                    "articles": entry.get("changed_articles", []),
                    "first_baseline": first_baseline,
                })
            elif agency.startswith(_MDCG_AGENCY_PREFIX):
                eu_mdcg_total += 1
                if changed:
                    eu_mdcg_changed += 1
                if first_baseline:
                    eu_mdcg_first_baseline += 1
        else:
            if region not in countries:
                countries[region] = {"changed": 0, "total": 0, "first_baseline": 0}
            countries[region]["total"] += 1
            if changed:
                countries[region]["changed"] += 1
            if first_baseline:
                countries[region]["first_baseline"] += 1

    has_any_change = (
        any(e["changed"] for e in eu_mdr_core)
        or eu_mdcg_changed > 0
        or any(v["changed"] > 0 for v in countries.values())
    )

    return {
        "eu": {
            "mdr_core": eu_mdr_core,
            "mdcg": {
                "changed_count": eu_mdcg_changed,
                "total": eu_mdcg_total,
                "first_baseline_count": eu_mdcg_first_baseline,
            },
        },
        "countries": countries,
        "has_any_change": has_any_change,
    }
