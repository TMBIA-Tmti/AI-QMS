"""
AI-QMS — Dynamic Audit Question Generator (Side B)
===================================================

Generates LLM-based audit questions for critical-impact clauses.
Used in the hybrid A/B question strategy:

  Side A (70%): Static questions from ISO_13485_CHECKLIST (major/minor clauses)
  Side B (30%): LLM-generated questions (critical clauses only)

Routing logic (get_audit_question_hybrid):
  - audit_impact == "critical"  → try B first, fallback to A on validation failure
  - audit_impact == "major"     → always A
  - audit_impact == "minor"     → always A

Quality gate: generated questions must satisfy ALL of:
  1. question_zh is 50–300 characters
  2. Contains ISO 13485 clause number pattern (e.g. §7.5.3) or "ISO 13485"
  3. regulation_refs list is non-empty

If any condition fails → automatic fallback to Side A.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.analysis.compliance_rules import ISO_13485_CHECKLIST, get_audit_question

logger = logging.getLogger(__name__)

__all__ = [
    "generate_question_b",
    "validate_question_b",
    "get_audit_question_hybrid",
    "SIDE_B_SYSTEM_PROMPT",
]

# ============================================================
# Side B — LLM system prompt
# ============================================================

SIDE_B_SYSTEM_PROMPT = """你是 ISO 13485:2016 醫療器材品質管理系統的資深稽核員，具備 MDSAP 主導員資格。

你的任務：根據提供的條款資訊與文件摘要，生成一個**高品質、可驗證**的稽核問題。

問題必須滿足以下所有條件：
1. **引用具體法規條號**：必須包含 ISO 13485:2016 條款編號（如「依 ISO 13485:2016 §7.5.3」）
2. **可驗證性**：問題必須能透過查看實際文件、記錄或程序來回答（不能是概念性問題）
3. **針對文件內容**：根據提供的文件摘要，聚焦於該文件最可能存在合規落差的面向
4. **具體查核點**：問題應指明「由誰執行、頻率、紀錄方式」等其中至少一項
5. **長度**：50–200 字之間
6. **避免重複**：不得與「現有標準問題」完全相同

回答**只能**使用以下 JSON 格式，不要包含任何其他文字：
{
  "question_zh": "稽核問題（繁體中文）",
  "question_en": "Audit question (English)",
  "regulation_refs": ["ISO 13485:2016 §X.X.X"],
  "focus_area": "此問題聚焦的合規面向（一句話）",
  "verifiable_by": "可透過哪類文件/記錄驗證（一句話）"
}"""


# ============================================================
# Core: generate & validate
# ============================================================


def generate_question_b(
    clause_id: str,
    clause_info: dict,
    doc_id: str,
    doc_title: str,
    doc_content_summary: str,
    llm_completion_fn: callable,
    model: str = "default",
) -> Optional[dict]:
    """Call LLM to generate a dynamic audit question for a critical clause.

    Returns a parsed dict with question fields, or None if generation/parsing fails.
    """
    existing_question = clause_info.get("audit_question", "")
    user_prompt = (
        f"條款資訊：\n"
        f"- 條款 ID：{clause_id}\n"
        f"- 條款標題：{clause_info.get('title', '')}\n"
        f"- 重要性：{clause_info.get('audit_impact', 'critical')}\n"
        f"- 現有標準問題（請勿重複）：{existing_question[:200]}\n\n"
        f"文件資訊：\n"
        f"- 文件 ID：{doc_id}\n"
        f"- 文件標題：{doc_title}\n"
        f"- 文件摘要：{doc_content_summary[:800] if doc_content_summary else '（無摘要）'}\n\n"
        f"請生成一個針對此文件與此條款的高品質稽核問題。"
    )

    try:
        response_text, _usage = llm_completion_fn(
            system=SIDE_B_SYSTEM_PROMPT,
            user=user_prompt,
            model=model,
            temperature=0.7,
            max_tokens=512,
        )
        return _parse_json_response(response_text)
    except Exception as exc:
        logger.warning(
            "Side B question generation failed for clause=%s doc=%s: %s",
            clause_id,
            doc_id,
            exc,
        )
        return None


def validate_question_b(q: dict) -> bool:
    """Quality gate for LLM-generated questions.

    Returns True only when ALL of the following pass:
      1. question_zh exists and is 50–300 chars
      2. Contains ISO 13485 clause reference (§X.X or "ISO 13485")
      3. regulation_refs list is non-empty
    """
    if not q or not isinstance(q, dict):
        return False

    question_zh = q.get("question_zh", "")
    if not question_zh or not (50 <= len(question_zh) <= 300):
        logger.debug(
            "Side B validation fail: question_zh length=%d", len(question_zh)
        )
        return False

    has_ref = bool(
        re.search(r"[§§]\s*\d+\.\d+", question_zh)
        or re.search(r"ISO\s*13485", question_zh, re.IGNORECASE)
        or q.get("regulation_refs")
    )
    if not has_ref:
        logger.debug("Side B validation fail: no regulation reference found")
        return False

    return True


# ============================================================
# Public API: hybrid selector
# ============================================================


def get_audit_question_hybrid(
    clause_id: str,
    doc_id: str = "",
    doc_title: str = "",
    doc_content_summary: str = "",
    llm_completion_fn: Optional[callable] = None,
    model: str = "default",
    seed: Optional[int] = None,
) -> dict:
    """Hybrid A/B question selector.

    Routing:
      critical + llm_completion_fn available → try Side B, fallback to A
      major / minor, or no LLM fn provided   → Side A always

    Returns:
        {
            "question":          str,       # selected question text (zh)
            "question_en":       str,       # English version (B only, else "")
            "source":            "A"|"B",   # which side was used
            "clause_id":         str,
            "audit_impact":      str,
            "regulation_refs":   list,      # from B; [] for A
            "focus_area":        str,       # from B; "" for A
            "verifiable_by":     str,       # from B; "" for A
            "expected_evidence": list,      # static list from checklist (always)
        }
    """
    clause_info = ISO_13485_CHECKLIST.get(clause_id, {})
    audit_impact = clause_info.get("audit_impact", "major")
    static_expected_evidence = clause_info.get("expected_evidence", [])

    # ── Side B: critical clauses with LLM available ──────────────────────────
    if audit_impact == "critical" and llm_completion_fn is not None:
        q_b = generate_question_b(
            clause_id=clause_id,
            clause_info=clause_info,
            doc_id=doc_id,
            doc_title=doc_title,
            doc_content_summary=doc_content_summary,
            llm_completion_fn=llm_completion_fn,
            model=model,
        )
        if q_b and validate_question_b(q_b):
            logger.info(
                "Side B question accepted for clause=%s doc=%s", clause_id, doc_id
            )
            return {
                "question": q_b["question_zh"],
                "question_en": q_b.get("question_en", ""),
                "source": "B",
                "clause_id": clause_id,
                "audit_impact": audit_impact,
                "regulation_refs": q_b.get("regulation_refs", []),
                "focus_area": q_b.get("focus_area", ""),
                "verifiable_by": q_b.get("verifiable_by", ""),
                "expected_evidence": static_expected_evidence,
            }
        logger.info(
            "Side B fallback to A for clause=%s (validation failed or error)", clause_id
        )

    # ── Side A: static pool with date + doc_id hash ──────────────────────────
    question_a = get_audit_question(clause_info, seed=seed, doc_id=doc_id)
    return {
        "question": question_a,
        "question_en": "",
        "source": "A",
        "clause_id": clause_id,
        "audit_impact": audit_impact,
        "regulation_refs": [],
        "focus_area": "",
        "verifiable_by": "",
        "expected_evidence": static_expected_evidence,
    }


# ============================================================
# Internal helpers
# ============================================================


def _parse_json_response(text: str) -> Optional[dict]:
    """Extract and parse the first JSON object found in LLM response text."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None
