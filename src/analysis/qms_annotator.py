"""
QMS Section Annotator
=====================
Post-processes crawled regulatory markdown to annotate which sections are
QMS-relevant (ISO 13485 mapped) vs. non-QMS administrative text.

Adds HTML comment markers readable by downstream LLM analysis and the UI:
  <!-- QMS_RELEVANT: clauses=[4.1, 7.5.1], score=3 -->
  <!-- NON_QMS -->

Also prepends a "QMS Relevant Sections" index block listing all matched
sections with their ISO 13485 clause mappings.

Usage:
    from src.analysis.qms_annotator import annotate_qms_sections
    annotated_md = annotate_qms_sections(raw_markdown)
"""

from __future__ import annotations
import re


def _build_clause_map() -> dict[str, frozenset[str]]:
    """Build clause_id → frozenset(lowercase keywords) from regulation_analyzer."""
    try:
        from src.analysis.regulation_analyzer import _CLAUSE_KEYWORDS
        return {k: frozenset(kw.lower() for kw in v) for k, v in _CLAUSE_KEYWORDS.items()}
    except ImportError:
        return {}


_CLAUSE_MAP: dict[str, frozenset[str]] = _build_clause_map()

# Broad QMS terms that count for scoring even if not in clause map
_BROAD_QMS_TERMS: frozenset[str] = frozenset({
    # English
    "quality management", "qms", "quality system", "iso 13485", "iso13485",
    "quality manual", "quality policy", "quality objective",
    "management review", "management responsibility", "management representative",
    "document control", "record control", "records management",
    "internal audit", "corrective action", "preventive action", "capa",
    "nonconforming", "non-conforming", "nonconformance",
    "design control", "design and development", "design history file",
    "purchasing control", "supplier evaluation", "approved supplier",
    "process validation", "special process",
    "calibration", "measuring equipment", "monitoring equipment",
    "complaint handling", "adverse event", "vigilance",
    "post-market surveillance", "pmcf", "psur",
    "risk management", "iso 14971",
    "sterile", "sterilisation", "sterilization",
    "traceability", "udi", "unique device identifier",
    "continual improvement", "continuous improvement",
    "product realization", "infrastructure", "work environment",
    "customer satisfaction", "customer focus",
    # Chinese (Traditional & Simplified)
    "品質管理", "品管系統", "品质管理", "文件管制", "记录控制",
    "管理審查", "内部审核", "矯正措施", "纠正措施", "預防措施", "预防措施",
    "不符合品", "不合格品", "设计控制", "採購管制", "采购控制", "過程確認", "过程确认",
    "量測設備", "测量设备", "校正", "校准", "顧客抱怨", "客户投诉", "警戒",
    "供應商評估", "供应商评估", "風險管理", "风险管理",
    # Japanese
    "品質管理", "品質マネジメント", "内部監査", "是正処置", "予防処置",
    "文書管理", "記録管理", "設計管理", "購買管理", "工程管理",
    # Korean
    "품질관리", "품질경영", "내부감사", "시정조치", "예방조치",
})


def _score_section(text: str) -> tuple[int, list[str]]:
    """Return (total_score, matched_clause_ids) for a markdown text block."""
    lower = text.lower()
    matched_clauses: list[str] = []
    score = 0

    for clause_id, keywords in _CLAUSE_MAP.items():
        if any(kw in lower for kw in keywords):
            matched_clauses.append(clause_id)
            score += 1

    # Broad terms add 1 collectively (prevents over-counting)
    if any(term in lower for term in _BROAD_QMS_TERMS):
        score += 1

    return score, matched_clauses


def _split_by_headers(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (header_line, body_text) pairs.

    The first tuple may have an empty header (preamble before first heading).
    """
    header_re = re.compile(r"^(#{1,4} .+)$", re.MULTILINE)
    sections: list[tuple[str, str]] = []
    positions = [(m.start(), m.end(), m.group(0)) for m in header_re.finditer(markdown)]

    if not positions:
        return [("", markdown.strip())]

    # Preamble (text before first header)
    preamble = markdown[: positions[0][0]].strip()
    if preamble:
        sections.append(("", preamble))

    for i, (start, end, header) in enumerate(positions):
        body_start = end + 1
        body_end = positions[i + 1][0] if i + 1 < len(positions) else len(markdown)
        body = markdown[body_start:body_end].strip()
        sections.append((header, body))

    return sections


def annotate_qms_sections(
    markdown: str,
    *,
    min_score: int = 1,
) -> str:
    """Annotate a regulatory markdown document with QMS relevance markers.

    Inserts HTML comment markers before each section:
      <!-- QMS_RELEVANT: clauses=[4.1, 7.5.1], score=3 -->
      <!-- NON_QMS -->

    Prepends a "QMS Relevant Sections" index block listing matched sections
    with their ISO 13485 clause mappings.

    Args:
        markdown: Full regulatory markdown text (may include file header).
        min_score: Minimum score to be considered QMS-relevant (default 1).

    Returns:
        Annotated markdown string. Returns original markdown unchanged on error.
    """
    if not markdown or not markdown.strip():
        return markdown

    try:
        sections = _split_by_headers(markdown)
    except Exception:
        return markdown

    if not sections:
        return markdown

    qms_index_entries: list[str] = []
    annotated_parts: list[str] = []

    for header, body in sections:
        combined = f"{header}\n{body}"
        score, clauses = _score_section(combined)
        is_qms = score >= min_score

        if is_qms:
            clause_str = ", ".join(sorted(set(clauses))) if clauses else "general"
            annotation = f"<!-- QMS_RELEVANT: clauses=[{clause_str}], score={score} -->"
            if header:
                display = header.lstrip("#").strip()
                qms_index_entries.append(
                    f"- **{display}** — ISO 13485: {clause_str}"
                )
        else:
            annotation = "<!-- NON_QMS -->"

        if header:
            part = f"{annotation}\n{header}\n\n{body}".strip()
        else:
            # Preamble (no header) — only annotate if it has content
            part = f"{annotation}\n{body}".strip() if body else ""

        if part:
            annotated_parts.append(part)

    body_md = "\n\n".join(annotated_parts)

    # Build QMS index block
    if qms_index_entries:
        index_block = (
            "## QMS Relevant Sections (ISO 13485 Mapped)\n\n"
            + "\n".join(qms_index_entries)
            + "\n\n---\n\n"
        )
    else:
        index_block = ""

    # Insert index after the file header block (ends at first "\n---\n")
    sep = "\n---\n"
    sep_pos = markdown.find(sep)
    if sep_pos != -1:
        file_header = markdown[: sep_pos + len(sep)]
        return file_header + "\n" + index_block + body_md
    else:
        return index_block + body_md
