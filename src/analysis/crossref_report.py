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

    # Header
    reg_count = meta.get('total_regulations', 0)
    lines.append(f"# {reg_count}國 × ISO 13485 交叉比對驗證報告")
    if language_mode != "zh-only":
        lines.append(f"# {reg_count}-Country × ISO 13485 Cross-Reference Validation Report")
    lines.append("")
    lines.append(f"**產生時間**: {meta.get('generated_at', '')[:19]}  ")
    lines.append(f"**基準標準**: {meta.get('iso_standard', '')}  ")
    lines.append(f"**比對國家數**: {meta.get('total_regulations', 0)}  ")
    lines.append(f"**總條款數**: {summary.get('total_clauses', 0)}  ")
    lines.append(f"**生成耗時**: {meta.get('generation_time_ms', 0)}ms  ")
    lines.append("")

    # Summary table
    lines.append("## 總覽" if language_mode == "zh-only" else "## 總覽 Summary")
    lines.append("")
    lines.append(
        "| 國家 | 完全對應 | 部分對應 | 超出ISO | 不適用 | 未映射 | 獨有需求 | 平均信心度 |"
    )
    lines.append(
        "|------|---------|---------|---------|--------|--------|---------|-----------|"
    )
    for reg_id, stats in country_stats.items():
        name = stats.get("country_name_zh", reg_id)
        if language_mode != "zh-only":
            name += f" ({stats.get('country_name_en', '')})"
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
    lines.append(
        "## 逐條比對明細"
        if language_mode == "zh-only"
        else "## 逐條比對明細 Clause-by-Clause Detail"
    )
    lines.append("")

    # Build header row dynamically based on countries
    reg_ids = list(country_stats.keys())
    header = "| 條款 | 標題 | 影響 |"
    separator = "|------|------|------|"
    for reg_id in reg_ids:
        stats = country_stats[reg_id]
        col_name = stats.get("country_name_zh", reg_id)
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
    lines.append("")

    # Delta items (country-unique requirements)
    if delta_items:
        lines.append(
            "## 國家獨有需求 (Delta)"
            if language_mode == "zh-only"
            else "## 國家獨有需求 (Delta Items)"
        )
        lines.append("")

        for reg_id, items in delta_items.items():
            stats = country_stats.get(reg_id, {})
            country_name = stats.get("country_name_zh", reg_id)
            if language_mode != "zh-only":
                country_name += f" ({stats.get('country_name_en', '')})"
            lines.append(f"### {country_name}")
            lines.append("")

            for item in items:
                impact_icon = _IMPACT_LABELS.get(item.get("audit_impact", ""), "")
                lines.append(f"#### {impact_icon} {item['req_id']}: {item['title_zh']}")
                if language_mode != "zh-only":
                    lines.append(f"*{item['title_en']}*")
                lines.append("")
                lines.append(f"- **法規引用**: {item['regulation_ref']}")
                lines.append(
                    f"- **相關ISO條款**: {', '.join(item.get('related_iso_clauses', []))}"
                )
                lines.append(f"- **需求說明**: {item['requirement_zh']}")
                if language_mode != "zh-only":
                    lines.append(f"- **Requirement**: {item['requirement_en']}")

                # Local language original text
                if language_mode == "local" and item.get("original_text"):
                    lang = item.get("original_lang", "")
                    lines.append(f"- **法規原文** [{lang}]: {item['original_text']}")
                    if item.get("english_translation"):
                        lines.append(
                            f"- **English Translation**: {item['english_translation']}"
                        )

                if item.get("semantic_note"):
                    lines.append(f"- **跨國比較**: {item['semantic_note']}")

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
