"""
AI-QMS — Phase 2: Cross-Country ISO 13485 Comparison Table (Deterministic Render)
===================================================================================

Loads all RegulationProfile JSONs from data/regulations/ and renders a self-contained
HTML file with:
  - Rows  = ISO 13485:2016 clauses (71 rows)
  - Cols  = Countries/regulations (up to 32)
  - Cells = MappingStatus badge  ✅ full | ⚠️ partial | ❌ na | ➕ exceeds | 🔲 not_analyzed
  - Frozen left column (clause #) + frozen top header row
  - Horizontal scroll for 32 columns
  - Click-to-expand tooltip with rationale + unique_requirements
  - content_quality warning banner for low-quality profiles
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES_DIR = Path("data/regulations")
_DEFAULT_OUTPUT_PATH = Path("data/cross_country_comparison.html")

# Status → display badge
_STATUS_BADGE = {
    "full":         '<span class="badge badge-full"         title="Full coverage">✅ Full</span>',
    "partial":      '<span class="badge badge-partial"      title="Partial coverage">⚠️ Partial</span>',
    "na":           '<span class="badge badge-na"           title="Not addressed / Not found">❌ N/A</span>',
    "exceeds":      '<span class="badge badge-exceeds"      title="Exceeds ISO 13485 requirements">➕ Exceeds</span>',
    "not_analyzed": '<span class="badge badge-not-analyzed" title="Analysis attempted but did not complete">🔲 N/A*</span>',
}

_QUALITY_BADGE = {
    "ok":           "",
    "low":          '<span class="quality-warn">⚠️ Low-quality crawl — many clauses may be incorrect</span>',
    "fallback_used": '<span class="quality-info">ℹ️ Based on pre-written regulatory summary</span>',
}


def _profile_to_dict(profile: object) -> dict:
    """Convert an in-memory RegulationProfile dataclass to the JSON-compatible dict format."""
    from src.analysis.compliance_rules import MappingStatus, MappingMethod
    iso_mapped = {}
    for cid, m in getattr(profile, "iso_mapped", {}).items():
        iso_mapped[cid] = {
            "iso_clause": m.iso_clause,
            "status": m.status.value if hasattr(m.status, "value") else str(m.status),
            "regulation_ref": m.regulation_ref,
            "rationale_en": m.rationale_en,
            "rationale_zh": m.rationale_zh,
            "method": m.method.value if hasattr(m.method, "value") else str(m.method),
            "confidence": m.confidence,
            "notes": m.notes,
            "within_clause_deltas": [
                {
                    "delta_id": d.delta_id,
                    "iso_clause": d.iso_clause,
                    "title_en": d.title_en,
                    "title_zh": d.title_zh,
                    "country_specific_en": d.country_specific_en,
                    "country_specific_zh": d.country_specific_zh,
                    "regulation_ref": d.regulation_ref,
                    "delta_type": d.delta_type,
                    "audit_impact": d.audit_impact,
                    "confidence": d.confidence,
                }
                for d in getattr(m, "within_clause_deltas", [])
            ],
        }
    unique_reqs = []
    for r in getattr(profile, "unique_requirements", []):
        unique_reqs.append({
            "req_id": r.req_id,
            "title_en": r.title_en,
            "title_zh": r.title_zh,
            "requirement_en": r.requirement_en,
            "requirement_zh": r.requirement_zh,
            "related_iso_clauses": r.related_iso_clauses,
            "audit_impact": r.audit_impact,
            "audit_question_en": r.audit_question_en,
            "audit_question_zh": r.audit_question_zh,
            "is_within_clause_delta": r.is_within_clause_delta,
        })
    return {
        "regulation_id": profile.regulation_id,
        "name_en": profile.name_en,
        "name_zh": profile.name_zh,
        "country": profile.country,
        "country_name_en": profile.country_name_en,
        "country_name_zh": profile.country_name_zh,
        "source": profile.source,
        "source_url": profile.source_url,
        "last_updated": profile.last_updated,
        "iso_mapped": iso_mapped,
        "unique_requirements": unique_reqs,
        "content_quality": getattr(profile, "content_quality", "ok"),
        "needs_reanalysis": getattr(profile, "needs_reanalysis", False),
    }


def _count_non_na(profile_dict: dict) -> int:
    """Count non-na clauses in a profile dict."""
    return sum(
        1 for m in profile_dict.get("iso_mapped", {}).values()
        if m.get("status") != "na"
    )


def _merge_country_profiles_for_display(primary: dict, secondary: dict) -> dict:
    """Merge two profiles for the same country into an enriched display profile.

    primary   = the higher-quality profile (keeps its clause mappings)
    secondary = the lower-quality profile (contributes source_url, unique_requirements)

    This bypasses the quality_threshold in merge_profiles() because we always
    want to preserve supplementary content (URLs, requirements) regardless of
    clause-level quality of the secondary source.
    """
    import copy
    merged = copy.deepcopy(primary)

    # Merge source_url: combine both into a multi-source string (de-duplicated)
    primary_url = primary.get("source_url", "") or ""
    secondary_url = secondary.get("source_url", "") or ""
    if secondary_url and secondary_url not in primary_url:
        if primary_url:
            merged["source_url"] = f"{primary_url} | {secondary_url}"
        else:
            merged["source_url"] = secondary_url

    # Merge unique_requirements: union deduped by first 40 chars of title_en
    existing_reqs = {
        r.get("title_en", "")[:40].lower().strip()
        for r in merged.get("unique_requirements", [])
    }
    for req in secondary.get("unique_requirements", []):
        key = req.get("title_en", "")[:40].lower().strip()
        if key and key not in existing_reqs:
            existing_reqs.add(key)
            merged.setdefault("unique_requirements", []).append(req)

    # For clauses: if primary has "na" but secondary has a real mapping, use secondary's
    secondary_iso = secondary.get("iso_mapped", {})
    merged_iso = dict(merged.get("iso_mapped", {}))
    for clause_id, sec_mapping in secondary_iso.items():
        existing = merged_iso.get(clause_id)
        sec_status = sec_mapping.get("status") if sec_mapping else None
        if existing is None:
            if sec_mapping is not None:
                merged_iso[clause_id] = sec_mapping
        elif existing.get("status") == "na" and sec_status not in ("na", None):
            merged_iso[clause_id] = sec_mapping
    merged["iso_mapped"] = merged_iso

    # Mark as merged + record which regulation IDs contributed
    merged["source"] = "merged"
    merged_ids: list[str] = []
    for rid in (primary.get("regulation_id", ""), secondary.get("regulation_id", "")):
        if rid and rid not in merged_ids:
            merged_ids.append(rid)
    # Preserve any pre-existing merged IDs (in case of >2-way merges)
    for rid in primary.get("merged_regulation_ids", []) or []:
        if rid and rid not in merged_ids:
            merged_ids.append(rid)
    for rid in secondary.get("merged_regulation_ids", []) or []:
        if rid and rid not in merged_ids:
            merged_ids.append(rid)
    merged["merged_regulation_ids"] = merged_ids

    return merged


def load_all_profiles(profiles_dir: Path = _DEFAULT_PROFILES_DIR) -> list[dict]:
    """Load RegulationProfile data for HTML rendering.

    Strategy (P-03/P-04):
    1. Load all JSON files from disk (data/regulations/ AND src/regulations/).
    2. Also load predefined in-memory profiles (TFDA, QMSR, EU_MDR, etc.)
       that are NOT already on disk — these are the high-quality hand-crafted versions.
    3. When multiple profiles exist for the same country (e.g., TFDA and TAIWAN),
       MERGE them (preserving URLs, unique requirements, and clause-level data
       from all sources) rather than picking only one.
    4. Sort by country_name_en.
    """
    profiles: list[dict] = []
    loaded_ids: set[str] = set()

    # Step 1: load from disk — check both data/regulations/ and src/regulations/
    _additional_dir = Path("src/regulations")
    dirs_to_check: list[Path] = [profiles_dir]
    if _additional_dir.exists() and _additional_dir.resolve() != profiles_dir.resolve():
        dirs_to_check.append(_additional_dir)

    for pdir in dirs_to_check:
        if not pdir.exists():
            continue
        for p in sorted(pdir.glob("*.json")):
            if p.parent.name == "backups":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                reg_id = data.get("regulation_id", "")
                if reg_id and reg_id in loaded_ids:
                    continue  # avoid double-loading the same regulation_id
                profiles.append(data)
                if reg_id:
                    loaded_ids.add(reg_id)
            except Exception as exc:
                logger.warning(f"Failed to load {p.name}: {exc}")

    # Step 2: add predefined profiles not yet on disk
    try:
        from src.analysis.compliance_rules import PREDEFINED_REGULATIONS, load_all_crawled_regulations
        load_all_crawled_regulations()
        for reg_id, prof in PREDEFINED_REGULATIONS.items():
            if reg_id not in loaded_ids and getattr(prof, "source", "") in ("predefined", "merged"):
                profiles.append(_profile_to_dict(prof))
                loaded_ids.add(reg_id)
    except Exception as exc:
        logger.warning(f"Could not load predefined profiles: {exc}")

    # Step 3: deduplicate — MERGE all profiles for the same country rather than pick one.
    # Prefer the ISO country code (e.g., "US", "EU", "TW") as the dedup key so that
    # variants like "USA" vs "United States" or "EU" vs "European Union" collapse
    # to a single merged entry.
    by_country: dict[str, dict] = {}
    for p in profiles:
        country_key = (
            p.get("country")
            or p.get("country_name_en")
            or p.get("regulation_id", "")
        )
        existing = by_country.get(country_key)
        if existing is None:
            by_country[country_key] = p
        else:
            # Merge both — primary is the one with more non-na clauses
            if _count_non_na(p) >= _count_non_na(existing):
                primary, secondary = p, existing
            else:
                primary, secondary = existing, p
            by_country[country_key] = _merge_country_profiles_for_display(primary, secondary)

    result = sorted(by_country.values(), key=lambda d: d.get("country_name_en", ""))
    return result


def _get_iso_clauses() -> list[tuple[str, str]]:
    """Return ordered list of (clause_id, description) from compliance_rules."""
    try:
        from src.analysis.compliance_rules import ISO_13485_CHECKLIST
        return [(cid, info.get("title", cid)) for cid, info in ISO_13485_CHECKLIST.items()]
    except Exception:
        return []


def _cell_html(profile: dict, clause_id: str) -> str:
    """Generate HTML for one table cell (one country × one clause)."""
    iso_mapped = profile.get("iso_mapped", {})
    mapping = iso_mapped.get(clause_id)
    if not mapping:
        return '<td class="cell-na">❌</td>'

    status = mapping.get("status", "na")
    badge_key = status if status in _STATUS_BADGE else "na"
    badge = _STATUS_BADGE[badge_key]

    # Tooltip content
    rationale = mapping.get("rationale_en", "") or mapping.get("rationale_zh", "")
    reg_ref = mapping.get("regulation_ref", "")
    confidence = mapping.get("confidence", 0)
    within_deltas = mapping.get("within_clause_deltas", [])

    tooltip_parts = []
    if reg_ref and reg_ref not in ("N/A", ""):
        tooltip_parts.append(f"<b>Ref:</b> {_esc(reg_ref)}")
    if rationale:
        tooltip_parts.append(f"<b>Rationale:</b> {_esc(rationale[:300])}")
    if confidence:
        tooltip_parts.append(f"<b>Confidence:</b> {confidence:.0%}")
    if within_deltas:
        delta_titles = ", ".join(d.get("title_en", "") for d in within_deltas[:3])
        tooltip_parts.append(f"<b>Deltas:</b> {_esc(delta_titles)}")

    tooltip = "<br>".join(tooltip_parts)

    css_class = f"cell-{badge_key}"
    if tooltip:
        return (
            f'<td class="{css_class}">'
            f'<div class="has-tooltip">{badge}'
            f'<div class="tooltip-box">{tooltip}</div>'
            f'</div></td>'
        )
    return f'<td class="{css_class}">{badge}</td>'


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _unique_reqs_html(profile: dict) -> str:
    """Generate collapsed list of unique requirements for a profile.

    Shows ALL merged requirements (no [:10] limit) so that content from every
    contributing source (predefined + crawled + semi-official) is visible.
    """
    reqs = [r for r in profile.get("unique_requirements", [])
            if not r.get("is_within_clause_delta", False)]
    if not reqs:
        return ""
    items = "".join(
        f'<li><b>{_esc(r.get("title_en", ""))}</b>: {_esc(r.get("requirement_en", "")[:200])}</li>'
        for r in reqs  # No [:10] limit — show all merged requirements
    )
    return (
        f'<details class="unique-reqs">'
        f'<summary>🔆 {len(reqs)} unique requirement(s) beyond ISO 13485</summary>'
        f'<ul>{items}</ul>'
        f'</details>'
    )


def generate_html(
    profiles: Optional[list[dict]] = None,
    profiles_dir: Path = _DEFAULT_PROFILES_DIR,
    output_path: Optional[Path] = None,
    title: str = "ISO 13485 Cross-Country Compliance Matrix",
) -> str:
    """Generate the HTML comparison table.

    Args:
        profiles: Pre-loaded list of profile dicts. If None, loads from profiles_dir.
        profiles_dir: Directory containing RegulationProfile JSON files.
        output_path: If set, writes HTML to this file.
        title: Page title.

    Returns:
        HTML string.
    """
    if profiles is None:
        profiles = load_all_profiles(profiles_dir)

    if not profiles:
        return "<html><body><p>No regulation profiles found.</p></body></html>"

    clauses = _get_iso_clauses()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── CSS ─────────────────────────────────────────────────────────────────
    css = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           font-size: 12px; background: #f5f5f5; color: #222; }
    h1  { padding: 12px 16px; font-size: 18px; background: #1a1a2e; color: #fff; }
    .meta { padding: 6px 16px; background: #e8eaf6; font-size: 11px; color: #555; }
    .profile-warnings { padding: 8px 16px; }
    .quality-warn { background: #fff3cd; border: 1px solid #ffc107;
                    padding: 3px 8px; border-radius: 4px; font-size: 11px; margin: 2px 0; display: block; }
    .quality-info { background: #d1ecf1; border: 1px solid #bee5eb;
                    padding: 3px 8px; border-radius: 4px; font-size: 11px; margin: 2px 0; display: block; }
    .table-wrap { overflow-x: auto; margin: 8px 16px 24px; border: 1px solid #ccc; border-radius: 6px; }
    table { border-collapse: collapse; min-width: 100%; background: #fff; }
    th, td { border: 1px solid #e0e0e0; padding: 5px 7px; white-space: nowrap; vertical-align: middle; }
    /* Frozen first column */
    th:first-child, td:first-child {
        position: sticky; left: 0; z-index: 2; background: #fff;
        border-right: 2px solid #999; min-width: 120px; max-width: 200px;
        white-space: normal; word-break: break-word;
    }
    /* Frozen header row */
    thead th { position: sticky; top: 0; z-index: 3; background: #1a1a2e; color: #fff;
               text-align: center; font-size: 11px; }
    thead th:first-child { z-index: 4; }
    /* Country name column header */
    th.country-header { min-width: 90px; max-width: 120px; white-space: normal;
                        word-break: break-word; line-height: 1.3; }
    /* Row striping */
    tbody tr:nth-child(even) td { background: #fafafa; }
    tbody tr:nth-child(even) td:first-child { background: #f0f0f0; }
    tbody tr:hover td { background: #e8f0fe !important; }
    /* Clause cell */
    .clause-cell { font-family: monospace; font-size: 11px; }
    .clause-id { font-weight: bold; color: #1a1a2e; }
    .clause-title { color: #555; font-size: 10px; }
    /* Status badges */
    .badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
    .badge-full    { background: #d4edda; color: #155724; }
    .badge-partial { background: #fff3cd; color: #856404; }
    .badge-na      { background: #f8d7da; color: #721c24; }
    .badge-exceeds      { background: #d1ecf1; color: #0c5460; }
    .badge-not-analyzed { background: #e9ecef; color: #495057; }
    .cell-full         { background: #f0fff4; text-align: center; }
    .cell-partial      { background: #fffbf0; text-align: center; }
    .cell-na      { background: #fff5f5; text-align: center; color: #ccc; font-size: 16px; }
    .cell-exceeds { background: #f0fbff; text-align: center; }
    /* Tooltip */
    .has-tooltip { position: relative; cursor: help; }
    .tooltip-box  { display: none; position: absolute; left: 50%; transform: translateX(-50%);
                    top: 100%; z-index: 100; background: #333; color: #fff; padding: 8px 10px;
                    border-radius: 5px; font-size: 11px; line-height: 1.5; width: 280px;
                    white-space: normal; word-break: break-word; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .has-tooltip:hover .tooltip-box { display: block; }
    /* Unique requirements */
    .unique-reqs { margin: 8px 16px; }
    .unique-reqs summary { cursor: pointer; color: #1a1a2e; font-weight: 600; padding: 4px 0; }
    .unique-reqs ul { margin: 4px 0 4px 20px; line-height: 1.6; }
    /* Legend */
    .legend { padding: 8px 16px; display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px;
              background: #fff; border-top: 1px solid #eee; margin-top: 8px; }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    /* Stats bar */
    .stats-bar { padding: 6px 16px; font-size: 11px; color: #555;
                 background: #f0f0f0; border-bottom: 1px solid #ddd; }
    """

    # ── Build profile warning banners ───────────────────────────────────────
    warning_html = ""
    for p in profiles:
        q = p.get("content_quality", "ok")
        badge = _QUALITY_BADGE.get(q, "")
        if badge:
            name = p.get("country_name_en", p.get("regulation_id", ""))
            warning_html += f'<div>{name}: {badge}</div>'

    # ── Compute stats ────────────────────────────────────────────────────────
    total_cells = len(profiles) * len(clauses)
    full_cells = sum(
        1 for p in profiles
        for c in clauses
        if p.get("iso_mapped", {}).get(c[0], {}).get("status") == "full"
    )
    partial_cells = sum(
        1 for p in profiles
        for c in clauses
        if p.get("iso_mapped", {}).get(c[0], {}).get("status") == "partial"
    )
    exceeds_cells = sum(
        1 for p in profiles
        for c in clauses
        if p.get("iso_mapped", {}).get(c[0], {}).get("status") == "exceeds"
    )
    na_cells = total_cells - full_cells - partial_cells - exceeds_cells
    coverage_pct = (full_cells + partial_cells) / max(total_cells, 1) * 100

    stats_html = (
        f"<b>{len(profiles)}</b> regulations × <b>{len(clauses)}</b> ISO 13485 clauses = "
        f"<b>{total_cells}</b> cells | "
        f"✅ Full: {full_cells} ({full_cells/max(total_cells,1):.1%}) | "
        f"⚠️ Partial: {partial_cells} ({partial_cells/max(total_cells,1):.1%}) | "
        f"➕ Exceeds: {exceeds_cells} | "
        f"❌ N/A: {na_cells} | "
        f"Overall coverage: <b>{coverage_pct:.1f}%</b>"
    )

    # ── Table header ─────────────────────────────────────────────────────────
    country_headers = "".join(
        f'<th class="country-header">'
        f'{_esc(p.get("country_name_zh") or p.get("country_name_en", ""))} '
        f'({_esc(p.get("country_name_en", p.get("regulation_id", "")))})<br>'
        f'<span style="font-weight:normal;font-size:10px">'
        f'{_esc("/".join(filter(None, p.get("merged_regulation_ids", [p.get("regulation_id","")]))))}'
        f'</span>'
        f'</th>'
        for p in profiles
    )
    thead = f"""
    <thead>
      <tr>
        <th>ISO 13485 Clause</th>
        {country_headers}
      </tr>
    </thead>"""

    # ── Table body ────────────────────────────────────────────────────────────
    rows = []
    for clause_id, clause_title in clauses:
        cells = "".join(_cell_html(p, clause_id) for p in profiles)
        rows.append(
            f'<tr>'
            f'<td class="clause-cell">'
            f'<span class="clause-id">{_esc(clause_id)}</span><br>'
            f'<span class="clause-title">{_esc(clause_title[:60])}</span>'
            f'</td>'
            f'{cells}'
            f'</tr>'
        )
    tbody = f"<tbody>{''.join(rows)}</tbody>"

    # ── Unique requirements section ───────────────────────────────────────────
    unique_sections = "".join(
        f'<div style="margin:4px 0"><b>{_esc(p.get("country_name_en",""))} ({p.get("regulation_id","")}):</b>'
        f'{_unique_reqs_html(p)}</div>'
        for p in profiles
        if p.get("unique_requirements")
    )
    if unique_sections:
        unique_section_html = (
            f'<div style="padding:8px 16px"><h2 style="font-size:14px;margin-bottom:8px">'
            f'Country-Specific Requirements Beyond ISO 13485</h2>'
            f'{unique_sections}</div>'
        )
    else:
        unique_section_html = ""

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_html = """
    <div class="legend">
      <b>Legend:</b>
      <div class="legend-item"><span class="badge badge-full">✅ Full</span> — Clause fully covered by national regulation</div>
      <div class="legend-item"><span class="badge badge-partial">⚠️ Partial</span> — Clause partially covered or referenced</div>
      <div class="legend-item"><span class="badge badge-na">❌ N/A</span> — Clause not addressed or not found</div>
      <div class="legend-item"><span class="badge badge-exceeds">➕ Exceeds</span> — National regulation exceeds ISO 13485 requirements</div>
      <div class="legend-item"><span class="badge badge-not-analyzed">🔲 N/A*</span> — Analysis was attempted but LLM batch did not complete</div>
    </div>"""

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>{css}</style>
</head>
<body>
<h1>📋 {_esc(title)}</h1>
<div class="meta">Generated: {generated_at} | Source: data/regulations/ | {len(profiles)} regulations loaded</div>
<div class="stats-bar">{stats_html}</div>
{'<div class="profile-warnings">' + warning_html + '</div>' if warning_html else ''}
{legend_html}
<div class="table-wrap">
<table>
{thead}
{tbody}
</table>
</div>
{unique_section_html}
</body>
</html>"""

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"Cross-country comparison HTML written to {output_path}")

    return html


def generate_to_file(
    profiles_dir: Path = _DEFAULT_PROFILES_DIR,
    output_path: Path = _DEFAULT_OUTPUT_PATH,
    title: str = "ISO 13485 Cross-Country Compliance Matrix",
) -> Path:
    """Convenience wrapper: load profiles, generate HTML, save file. Returns output path."""
    profiles = load_all_profiles(profiles_dir)
    generate_html(profiles=profiles, output_path=output_path, title=title)
    return output_path


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT_PATH
    path = generate_to_file(output_path=out)
    print(f"Generated: {path}")
