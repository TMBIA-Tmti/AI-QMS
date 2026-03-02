"""
AI-QMS — Phase 0.5: Reference Mapping
=======================================

Locate WHERE in company documents each regulation clause is referenced.
This is section-level mapping (not just "doc mentions ISO 13485" but
"section 3.2 of QP-001 addresses clause 4.2.3").

This phase is code-based (no LLM) — it uses keyword matching and
section header analysis to create a preliminary mapping before
the LLM does deep paragraph-level search in Phase 1.

Output: For each row (clause × doc), a list of candidate sections
where the regulation might be addressed.
"""

from __future__ import annotations

import re
import time

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    PipelineState,
)


__all__ = [
    "run_reference_mapping",
]


# ============================================================
# Section extraction
# ============================================================

# Patterns that identify section headers in Markdown documents
_SECTION_PATTERNS = [
    # Markdown headers: # Title, ## Title, ### Title
    re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE),
    # Numbered sections: 1. Title, 1.1 Title, 4.2.3 Title
    re.compile(r"^(\d+(?:\.\d+)*)\s*[.、]\s*(.+)$", re.MULTILINE),
]


def _extract_sections(content: str) -> list[dict]:
    """Extract sections from a Markdown document.

    Returns list of {heading, level, start_pos, end_pos, text}.
    Each section includes the text from its heading to the next heading.
    """
    sections: list[dict] = []

    # Find all section headers
    headers: list[tuple[int, str, int]] = []  # (position, heading_text, level)

    for pattern in _SECTION_PATTERNS:
        for match in pattern.finditer(content):
            level_marker = match.group(1)
            heading = match.group(2).strip()
            pos = match.start()

            # Determine level
            if level_marker.startswith("#"):
                level = len(level_marker)
            else:
                level = level_marker.count(".") + 1

            headers.append((pos, heading, level))

    # Sort by position
    headers.sort(key=lambda x: x[0])

    # Build sections with text content
    for i, (pos, heading, level) in enumerate(headers):
        # End position = start of next header, or end of document
        if i + 1 < len(headers):
            end_pos = headers[i + 1][0]
        else:
            end_pos = len(content)

        section_text = content[pos:end_pos].strip()

        sections.append(
            {
                "heading": heading,
                "level": level,
                "start_pos": pos,
                "end_pos": end_pos,
                "text": section_text,
                "text_length": len(section_text),
            }
        )

    # If no sections found, treat entire document as one section
    if not sections and content.strip():
        sections.append(
            {
                "heading": "(全文)",
                "level": 0,
                "start_pos": 0,
                "end_pos": len(content),
                "text": content.strip(),
                "text_length": len(content.strip()),
            }
        )

    return sections


# ============================================================
# Keyword matching
# ============================================================


def _build_clause_keywords(clause_id: str, clause_info: dict) -> list[str]:
    """Build a list of search keywords from a clause's metadata.

    Includes: clause number, title words, expected evidence keywords.
    """
    keywords: list[str] = []

    # Clause number itself (e.g., "4.2.3")
    keywords.append(clause_id)

    # Title keywords (split Chinese/English)
    title = clause_info.get("title", "")
    if title:
        # Chinese keywords: split on common delimiters
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", title)
        keywords.extend(cn_words)
        # English keywords
        en_words = re.findall(r"[a-zA-Z]{3,}", title)
        keywords.extend(w.lower() for w in en_words)

    # Expected evidence keywords
    for ev in clause_info.get("expected_evidence", []):
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", ev)
        keywords.extend(cn_words)
        en_words = re.findall(r"[a-zA-Z]{3,}", ev)
        keywords.extend(w.lower() for w in en_words)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    return unique


def _score_section_relevance(
    section: dict,
    keywords: list[str],
) -> float:
    """Score how relevant a section is to a clause based on keyword matches.

    Returns a score from 0.0 to 1.0.
    """
    if not keywords:
        return 0.0

    text_lower = section["text"].lower()
    matches = 0

    for kw in keywords:
        # Case-insensitive search
        if kw.lower() in text_lower:
            matches += 1

    if not keywords:
        return 0.0

    return min(1.0, matches / max(len(keywords) * 0.3, 1))


# ============================================================
# Main phase execution
# ============================================================


def run_reference_mapping(state: PipelineState) -> dict:
    """Execute Phase 0.5: Reference Mapping.

    For each row that passed Phase 0, find candidate sections in the
    company document where the clause might be addressed.

    Args:
        state: Pipeline state with rows that passed Phase 0

    Returns:
        Summary dict with mapping statistics
    """
    # Only process rows that are at Phase 0.5 (passed Phase 0)
    rows_to_process = state.get_rows_by_phase(Phase.REFERENCE_MAPPING)

    if not rows_to_process:
        return {"rows_processed": 0, "message": "No rows at Phase 0.5"}

    # Cache document content and sections (avoid re-reading same doc)
    doc_cache: dict[str, str] = {}
    section_cache: dict[str, list[dict]] = {}

    rows_mapped = 0
    total_candidates = 0

    for row in rows_to_process:
        phase_result = PhaseResult(
            phase=Phase.REFERENCE_MAPPING.value,
            started_at=time.time(),
        )

        try:
            # Get document content (cached)
            if row.doc_id not in doc_cache:
                try:
                    from src.storage.markdown_storage import MarkdownStoreService

                    service = MarkdownStoreService()
                    doc_result = service.get_document(row.doc_id)
                    doc_cache[row.doc_id] = (
                        doc_result.get("content", "")
                        if doc_result and doc_result.get("success")
                        else ""
                    )
                except Exception:
                    doc_cache[row.doc_id] = ""

            content = doc_cache[row.doc_id]

            # Extract sections (cached)
            if row.doc_id not in section_cache:
                section_cache[row.doc_id] = _extract_sections(content)

            sections = section_cache[row.doc_id]

            # Build keywords for this clause
            clause_info = {
                "title": row.clause_title,
                "expected_evidence": row.expected_evidence,
            }
            keywords = _build_clause_keywords(row.clause_id, clause_info)

            # Score each section
            candidates: list[dict] = []
            for section in sections:
                score = _score_section_relevance(section, keywords)
                if score > 0.1:  # Minimum relevance threshold
                    candidates.append(
                        {
                            "heading": section["heading"],
                            "level": section["level"],
                            "score": round(score, 3),
                            "text_preview": section["text"][:200],
                            "start_pos": section["start_pos"],
                            "text_length": section["text_length"],
                        }
                    )

            # Sort by relevance score descending
            candidates.sort(key=lambda x: x["score"], reverse=True)

            # Keep top 5 candidates
            candidates = candidates[:5]
            total_candidates += len(candidates)

            phase_result.status = PhaseStatus.COMPLETED.value
            phase_result.output = {
                "candidate_sections": candidates,
                "total_sections_in_doc": len(sections),
                "keywords_used": keywords[:10],  # Truncate for storage
                "doc_content_length": len(content),
            }

            rows_mapped += 1

        except Exception as e:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = str(e)
            phase_result.output = {"candidate_sections": []}

        phase_result.completed_at = time.time()
        row.set_phase_result(Phase.REFERENCE_MAPPING, phase_result)

        # Advance to next phase
        if phase_result.status == PhaseStatus.COMPLETED.value:
            row.advance_to_next_phase()

        state.update_row(row)

    return {
        "rows_processed": len(rows_to_process),
        "rows_mapped": rows_mapped,
        "total_candidate_sections": total_candidates,
        "avg_candidates_per_row": (
            round(total_candidates / rows_mapped, 1) if rows_mapped > 0 else 0
        ),
    }
