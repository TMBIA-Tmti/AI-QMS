"""
AI-QMS — Cross-Reference Validation Report Generator
=====================================================

Generates a static 3-country × ISO 13485 cross-reference report
using ONLY predefined regulation data (no LLM calls).

This report serves as:
1. Validation evidence that cross-examination data is correct
2. A reference table showing overlap/delta/exceeds per clause per country
3. Input for LLM cross-examination during Phase 5

Language modes:
- "zh-en" (default): Chinese + English bilingual
- "local": zh-en + original regulatory text in native language
- "zh-only": Chinese only
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "generate_crossref_validation_report",
    "format_crossref_report_markdown",
]


def generate_crossref_validation_report(
    regulation_ids: list[str],
) -> dict:
    """Generate a static cross-reference validation report.

    For each regulation × each ISO 13485 clause, calls get_overlap_analysis()
    to determine mapping status, overlap, and delta items.

    No LLM calls — pure Python dictionary assembly.

    Args:
        regulation_ids: e.g., ["QMSR", "EU_MDR", "TFDA"]

    Returns:
        dict with keys:
        - metadata: timestamp, regulation_ids, generation_time_ms
        - summary: total_clauses, per-country stats
        - clauses: list of per-clause cross-reference data
        - delta_items: all unique requirements grouped by country
    """
    from src.analysis.compliance_rules import (
        ISO_13485_CHECKLIST,
        get_regulation,
        get_overlap_analysis,
    )

    start = time.time()

    # Validate regulation IDs
    valid_regs = []
    for reg_id in regulation_ids:
        reg = get_regulation(reg_id)
        if reg is not None:
            valid_regs.append(reg_id)
        else:
            logger.warning(f"[CrossRef] Regulation {reg_id!r} not found, skipping")

    # Per-country summary counters
    country_stats: dict[str, dict] = {}
    for reg_id in valid_regs:
        reg = get_regulation(reg_id)
        country_stats[reg_id] = {
            "regulation_id": reg_id,
            "name_zh": reg.name_zh,
            "name_en": reg.name_en,
            "country_name_zh": reg.country_name_zh,
            "country_name_en": reg.country_name_en,
            "full_count": 0,
            "partial_count": 0,
            "exceeds_count": 0,
            "na_count": 0,
            "not_mapped_count": 0,
            "delta_count": 0,
            "total_confidence": 0.0,
            "mapped_count": 0,
        }

    # Build per-clause cross-reference
    clauses = []
    clause_keys = sorted(
        ISO_13485_CHECKLIST.keys(),
        key=lambda x: [int(p) for p in x.split(".")],
    )

    for clause_id in clause_keys:
        clause_info = ISO_13485_CHECKLIST[clause_id]
        clause_entry = {
            "clause_id": clause_id,
            "title": clause_info.get("title", ""),
            "audit_impact": clause_info.get("audit_impact", ""),
            "audit_question": clause_info.get("audit_question", ""),
            "countries": {},
        }

        for reg_id in valid_regs:
            analysis = get_overlap_analysis(reg_id, clause_id)
            status = analysis.get("status", "not_mapped")
            mapping = analysis.get("mapping")
            delta_items = analysis.get("delta_items", [])

            country_data = {
                "status": status,
                "is_overlap": analysis.get("is_overlap", False),
                "is_delta": analysis.get("is_delta", False),
                "delta_count": len(delta_items),
            }

            if mapping:
                country_data.update(
                    {
                        "regulation_ref": mapping.get("regulation_ref", ""),
                        "confidence": mapping.get("confidence", 0.0),
                        "rationale_zh": mapping.get("rationale_zh", ""),
                        "rationale_en": mapping.get("rationale_en", ""),
                        "original_text": mapping.get("original_text", ""),
                        "original_lang": mapping.get("original_lang", ""),
                        "english_translation": mapping.get("english_translation", ""),
                        "semantic_note": mapping.get("semantic_note", ""),
                        "method": mapping.get("method", ""),
                        "within_clause_deltas": mapping.get("within_clause_deltas", []),
                    }
                )
                # Update stats
                stats = country_stats[reg_id]
                stats["mapped_count"] += 1
                stats["total_confidence"] += mapping.get("confidence", 0.0)
            else:
                country_data.update(
                    {
                        "regulation_ref": "",
                        "confidence": 0.0,
                        "rationale_zh": "",
                        "rationale_en": "",
                        "original_text": "",
                        "original_lang": "",
                        "english_translation": "",
                        "semantic_note": "",
                        "method": "",
                    }
                )

            # Update counters
            stats = country_stats[reg_id]
            if status == "full":
                stats["full_count"] += 1
            elif status == "partial":
                stats["partial_count"] += 1
            elif status == "exceeds":
                stats["exceeds_count"] += 1
            elif status == "not_applicable":
                stats["na_count"] += 1
            else:
                stats["not_mapped_count"] += 1

            if delta_items:
                stats["delta_count"] += len(delta_items)

            clause_entry["countries"][reg_id] = country_data

        clauses.append(clause_entry)

    # Compute average confidence
    for reg_id, stats in country_stats.items():
        if stats["mapped_count"] > 0:
            stats["avg_confidence"] = round(
                stats["total_confidence"] / stats["mapped_count"], 3
            )
        else:
            stats["avg_confidence"] = 0.0

    # Collect all delta items grouped by country
    delta_items_by_country: dict[str, list[dict]] = {}
    for reg_id in valid_regs:
        reg = get_regulation(reg_id)
        if reg and reg.unique_requirements:
            items = []
            for req in reg.unique_requirements:
                items.append(
                    {
                        "req_id": req.req_id,
                        "regulation_ref": req.regulation_ref,
                        "title_zh": req.title_zh,
                        "title_en": req.title_en,
                        "requirement_zh": req.requirement_zh,
                        "requirement_en": req.requirement_en,
                        "related_iso_clauses": req.related_iso_clauses,
                        "audit_impact": req.audit_impact,
                        "audit_question_zh": req.audit_question_zh,
                        "audit_question_en": req.audit_question_en,
                        "expected_evidence": req.expected_evidence,
                        "confidence": req.confidence,
                        "method": req.method.value if hasattr(req.method, "value") else str(req.method),
                        "is_within_clause_delta": req.is_within_clause_delta,
                        "within_clause_delta_vs_iso": req.within_clause_delta_vs_iso,
                        "original_text": req.original_text,
                        "original_lang": req.original_lang,
                        "english_translation": req.english_translation,
                        "semantic_note": req.semantic_note,
                    }
                )
            delta_items_by_country[reg_id] = items

    elapsed_ms = round((time.time() - start) * 1000, 1)

    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regulation_ids": valid_regs,
            "generation_time_ms": elapsed_ms,
            "iso_standard": "ISO 13485:2016",
            "total_regulations": len(valid_regs),
        },
        "summary": {
            "total_clauses": len(clause_keys),
            "country_stats": country_stats,
        },
        "clauses": clauses,
        "delta_items": delta_items_by_country,
    }

    logger.info(
        f"[CrossRef] Report generated: {len(valid_regs)} regulations × "
        f"{len(clause_keys)} clauses in {elapsed_ms}ms"
    )

    return report


# ============================================================
# Status display helpers
# ============================================================

_STATUS_LABELS = {
    "full": {"zh": "✅ 完全對應", "en": "Full", "icon": "✅"},
    "partial": {"zh": "🔶 部分對應", "en": "Partial", "icon": "🔶"},
    "exceeds": {"zh": "⬆️ 超出 ISO", "en": "Exceeds", "icon": "⬆️"},
    "not_applicable": {"zh": "⬜ 不適用", "en": "N/A", "icon": "⬜"},
    "not_mapped": {"zh": "❓ 未映射", "en": "Not Mapped", "icon": "❓"},
}

_IMPACT_LABELS = {
    "critical": "🔴",
    "major": "🟡",
    "minor": "🟢",
}


def format_crossref_report_markdown(
    report: dict,
    language_mode: str = "zh-en",
) -> str:
    """Format cross-reference report as Markdown.

    Args:
        report: Output of generate_crossref_validation_report()
        language_mode:
            "zh-en" — Chinese + English bilingual (default)
            "local" — zh-en + original regulatory text in native language
            "zh-only" — Chinese only

    Returns:
        Formatted Markdown string
    """
    meta = report.get("metadata", {})
    summary = report.get("summary", {})
    clauses = report.get("clauses", [])
    delta_items = report.get("delta_items", {})
    country_stats = summary.get("country_stats", {})

    lines: list[str] = []

    # Determine if we should show Chinese
    # language_mode: "zh-only", "zh-en", "local" (legacy)
    # Also supports lang codes: "en-US", "ja-JP", "zh-TW", etc.
    _show_zh = language_mode in ("zh-only", "zh-en", "local")
    _show_en = language_mode != "zh-only"
    # If language_mode looks like a lang code, adapt accordingly
    # e.g. lang.startswith("zh") → show Chinese, lang.startswith("en") → English only
    lang = language_mode  # alias for pattern compatibility
    if lang.startswith("en") or lang.startswith("ja"):
        _show_zh = False
        _show_en = True
    elif lang.startswith("zh"):
        _show_zh = True
        _show_en = True

    # Header
    reg_count = meta.get('total_regulations', 0)
    if _show_zh:
        lines.append(f"# {reg_count}國 × ISO 13485 交叉比對驗證報告")
    if _show_en:
        lines.append(f"# {reg_count}-Country × ISO 13485 Cross-Reference Validation Report")
    lines.append("")
    if _show_zh:
        lines.append(f"**產生時間**: {meta.get('generated_at', '')[:19]}  ")
        lines.append(f"**基準標準**: {meta.get('iso_standard', '')}  ")
        lines.append(f"**比對國家數**: {meta.get('total_regulations', 0)}  ")
        lines.append(f"**總條款數**: {summary.get('total_clauses', 0)}  ")
        lines.append(f"**生成耗時**: {meta.get('generation_time_ms', 0)}ms  ")
    else:
        lines.append(f"**Generated at**: {meta.get('generated_at', '')[:19]}  ")
        lines.append(f"**Base standard**: {meta.get('iso_standard', '')}  ")
        lines.append(f"**Countries compared**: {meta.get('total_regulations', 0)}  ")
        lines.append(f"**Total clauses**: {summary.get('total_clauses', 0)}  ")
        lines.append(f"**Generation time**: {meta.get('generation_time_ms', 0)}ms  ")
    lines.append("")

    # Summary table
    if _show_zh:
        lines.append("## 總覽" if not _show_en else "## 總覽 Summary")
    else:
        lines.append("## Summary")
    lines.append("")
    if _show_zh:
        lines.append(
            "| 國家 | 完全對應 | 部分對應 | 超出ISO | 不適用 | 未映射 | 獨有需求 | 平均信心度 |"
        )
    else:
        lines.append(
            "| Country | Full | Partial | Exceeds | N/A | Not Mapped | Unique Reqs | Avg Confidence |"
        )
    lines.append(
        "|------|---------|---------|---------|--------|--------|---------|-----------|"
    )
    for reg_id, stats in country_stats.items():
        if _show_zh:
            name = stats.get("country_name_zh", reg_id)
            if _show_en:
                name += f" ({stats.get('country_name_en', '')})"
        else:
            name = stats.get("country_name_en", reg_id)
        lines.append(
            f"| {name} "
            f"| {stats.get('full_count', 0)} "
            f"| {stats.get('partial_count', 0)} "
            f"| {stats.get('exceeds_count', 0)} "
            f"| {stats.get('na_count', 0)} "
            f"| {stats.get('not_mapped_count', 0)} "
            f"| {stats.get('delta_count', 0)} "
            f"| {stats.get('avg_confidence', 0):.1%} |"
        )
    lines.append("")

    # Per-clause detail table
    if _show_zh:
        lines.append(
            "## 逐條比對明細"
            if not _show_en
            else "## 逐條比對明細 Clause-by-Clause Detail"
        )
    else:
        lines.append("## Clause-by-Clause Detail")
    lines.append("")

    # Build header row dynamically based on countries
    reg_ids = list(country_stats.keys())
    if _show_zh:
        header = "| 條款 | 標題 | 影響 |"
    else:
        header = "| Clause | Title | Impact |"
    separator = "|------|------|------|"
    for reg_id in reg_ids:
        stats = country_stats[reg_id]
        col_name = stats.get("country_name_zh", reg_id) if _show_zh else stats.get("country_name_en", reg_id)
        header += f" {col_name} |"
        separator += "------|"
    lines.append(header)
    lines.append(separator)

    for clause in clauses:
        impact_icon = _IMPACT_LABELS.get(clause.get("audit_impact", ""), "")
        row = f"| {clause['clause_id']} | {clause['title']} | {impact_icon} |"
        for reg_id in reg_ids:
            country_data = clause.get("countries", {}).get(reg_id, {})
            status = country_data.get("status", "not_mapped")
            status_info = _STATUS_LABELS.get(status, _STATUS_LABELS["not_mapped"])
            ref = country_data.get("regulation_ref", "")
            conf = country_data.get("confidence", 0)

            cell = f"{status_info['icon']}"
            if ref:
                cell += f" {ref}"
            if conf > 0:
                cell += f" ({conf:.0%})"
            row += f" {cell} |"
        lines.append(row)

        # Render within-clause deltas for exceeds clauses
        for reg_id in reg_ids:
            country_data = clause.get("countries", {}).get(reg_id, {})
            wcd_list = country_data.get("within_clause_deltas", [])
            if country_data.get("status") == "exceeds" and wcd_list:
                stats = country_stats.get(reg_id, {})
                if _show_zh:
                    c_name = stats.get("country_name_zh", reg_id)
                    if _show_en:
                        c_name += f" ({stats.get('country_name_en', '')})"
                else:
                    c_name = stats.get("country_name_en", reg_id)
                delta_count = len(wcd_list)
                lines.append("")
                lines.append(
                    f"> **{c_name}** — "
                    f"{'⬆️ EXCEEDS' if _show_en else '⬆️ 超出 ISO'} — "
                    f"{delta_count} within-clause delta{'s' if delta_count != 1 else ''}:"
                )
                for didx, wcd in enumerate(wcd_list, 1):
                    impact_icon = _IMPACT_LABELS.get(wcd.get("audit_impact", ""), "")
                    # Trilingual title
                    if _show_zh and _show_en:
                        title_line = (
                            f"{wcd.get('title_zh', '')} / "
                            f"{wcd.get('title_en', '')} / "
                            f"{wcd.get('title_ja', '')}"
                        )
                    elif _show_zh:
                        title_line = wcd.get("title_zh", "")
                    else:
                        # English or Japanese mode
                        if lang.startswith("ja"):
                            title_line = (
                                f"{wcd.get('title_ja', '')} / "
                                f"{wcd.get('title_en', '')}"
                            )
                        else:
                            title_line = wcd.get("title_en", "")
                    lines.append(f">   {didx}. {impact_icon} {title_line}")

                    # ISO baseline vs country-specific
                    if _show_zh and _show_en:
                        iso_line = (
                            f"{wcd.get('iso_baseline_zh', '')} / "
                            f"{wcd.get('iso_baseline_en', '')} / "
                            f"{wcd.get('iso_baseline_ja', '')}"
                        )
                        country_line = (
                            f"{wcd.get('country_specific_zh', '')} / "
                            f"{wcd.get('country_specific_en', '')} / "
                            f"{wcd.get('country_specific_ja', '')}"
                        )
                    elif _show_zh:
                        iso_line = wcd.get("iso_baseline_zh", "")
                        country_line = wcd.get("country_specific_zh", "")
                    else:
                        if lang.startswith("ja"):
                            iso_line = (
                                f"{wcd.get('iso_baseline_ja', '')} / "
                                f"{wcd.get('iso_baseline_en', '')}"
                            )
                            country_line = (
                                f"{wcd.get('country_specific_ja', '')} / "
                                f"{wcd.get('country_specific_en', '')}"
                            )
                        else:
                            iso_line = wcd.get("iso_baseline_en", "")
                            country_line = wcd.get("country_specific_en", "")

                    _iso_label = "ISO" if _show_en else "ISO"
                    _country_label = "Country" if _show_en else "該國"
                    lines.append(f">      {_iso_label}: {iso_line}")
                    lines.append(f">      {_country_label}: {country_line}")

                    # Ref and evidence
                    ref = wcd.get("regulation_ref", "")
                    evidence = wcd.get("expected_evidence", [])
                    if ref or evidence:
                        evidence_str = ", ".join(evidence) if evidence else ""
                        parts = []
                        if ref:
                            parts.append(f"Ref: {ref}")
                        if evidence_str:
                            parts.append(f"Evidence: [{evidence_str}]")
                        lines.append(f">      {' | '.join(parts)}")
                lines.append("")

    lines.append("")

    # Delta items (country-unique requirements)
    if delta_items:
        if _show_zh:
            lines.append(
                "## 國家獨有需求 (Delta)"
                if not _show_en
                else "## 國家獨有需求 (Delta Items)"
            )
        else:
            lines.append("## Country-Unique Requirements (Delta Items)")
        lines.append("")

        for reg_id, items in delta_items.items():
            stats = country_stats.get(reg_id, {})
            if _show_zh:
                country_name = stats.get("country_name_zh", reg_id)
                if _show_en:
                    country_name += f" ({stats.get('country_name_en', '')})"
            else:
                country_name = stats.get("country_name_en", reg_id)
            lines.append(f"### {country_name}")
            lines.append("")

            for item in items:
                impact_icon = _IMPACT_LABELS.get(item.get("audit_impact", ""), "")
                if _show_zh:
                    lines.append(f"#### {impact_icon} {item['req_id']}: {item['title_zh']}")
                    if _show_en:
                        lines.append(f"*{item['title_en']}*")
                else:
                    lines.append(f"#### {impact_icon} {item['req_id']}: {item['title_en']}")
                lines.append("")
                _reg_ref = "法規引用" if _show_zh else "Regulation Ref"
                lines.append(f"- **{_reg_ref}**: {item['regulation_ref']}")
                _iso_ref = "相關ISO條款" if _show_zh else "Related ISO Clauses"
                lines.append(
                    f"- **{_iso_ref}**: {', '.join(item.get('related_iso_clauses', []))}"
                )
                if _show_zh:
                    lines.append(f"- **需求說明**: {item['requirement_zh']}")
                    if _show_en:
                        lines.append(f"- **Requirement**: {item['requirement_en']}")
                else:
                    lines.append(f"- **Requirement**: {item['requirement_en']}")

                # Local language original text
                if language_mode == "local" and item.get("original_text"):
                    lang = item.get("original_lang", "")
                    _orig_label = "法規原文" if _show_zh else "Original Text"
                    lines.append(f"- **{_orig_label}** [{lang}]: {item['original_text']}")
                    if item.get("english_translation"):
                        lines.append(
                            f"- **English Translation**: {item['english_translation']}"
                        )

                if item.get("semantic_note"):
                    _compare_label = "跨國比較" if _show_zh else "Cross-Country Comparison"
                    lines.append(f"- **{_compare_label}**: {item['semantic_note']}")

                lines.append("")

    # Detailed clause mappings with original text (only in "local" mode)
    if language_mode == "local":
        lines.append("## 法規原文對照 Original Regulatory Text")
        lines.append("")
        for clause in clauses:
            has_original = any(
                clause.get("countries", {}).get(r, {}).get("original_text")
                for r in reg_ids
            )
            if not has_original:
                continue

            lines.append(f"### {clause['clause_id']} — {clause['title']}")
            lines.append("")
            for reg_id in reg_ids:
                country_data = clause.get("countries", {}).get(reg_id, {})
                original = country_data.get("original_text", "")
                if not original:
                    continue
                stats = country_stats.get(reg_id, {})
                country_name = stats.get("country_name_zh", reg_id)
                lang = country_data.get("original_lang", "")
                lines.append(f"**{country_name}** [{lang}]:")
                lines.append(f"> {original}")
                translation = country_data.get("english_translation", "")
                if translation:
                    lines.append(f"> *{translation}*")
                semantic = country_data.get("semantic_note", "")
                if semantic:
                    lines.append(f"> 📝 {semantic}")
                lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*本報告由 AI-QMS 系統自動產生，基於預定義法規映射資料。*  ")
    lines.append(f"*不涉及 LLM 呼叫，所有映射均為人工預定義。*")

    return "\n".join(lines)
