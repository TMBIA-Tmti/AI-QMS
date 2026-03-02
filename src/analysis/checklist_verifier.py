"""
AI-QMS — Phase 2: Checklist Verification
==========================================

LLM call #2 — Verify the evidence found in Phase 1 against the
audit question from compliance_rules.py.

L1 (keyword cross-match) is done in code first.
L2 (semantic comparison) is done by the LLM.

The LLM receives:
  - The audit question
  - The evidence items found in Phase 1 (with quotes)
  - The regulation text (if available from crawl data)

Output: Refined evidence items with semantic verification scores.
"""

from __future__ import annotations

import json
import re
import time

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    EvidenceItem,
    RowState,
    PipelineState,
)


__all__ = [
    "run_checklist_verify_row",
    "run_keyword_crossmatch",
]


# ============================================================
# L1: Keyword Cross-Match (code-based, no LLM)
# ============================================================


def _extract_keywords_from_audit_question(audit_question: str) -> list[str]:
    """Extract meaningful keywords from the audit question."""
    keywords: list[str] = []

    # Chinese keywords (2+ chars)
    cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", audit_question)
    keywords.extend(cn_words)

    # English keywords (3+ chars, skip common words)
    stop_words = {
        "the",
        "and",
        "for",
        "are",
        "was",
        "has",
        "have",
        "been",
        "with",
        "that",
        "this",
        "from",
        "does",
        "not",
        "all",
    }
    en_words = re.findall(r"[a-zA-Z]{3,}", audit_question)
    keywords.extend(w.lower() for w in en_words if w.lower() not in stop_words)

    return keywords


def run_keyword_crossmatch(
    evidence_items: list[EvidenceItem],
    audit_question: str,
) -> list[dict]:
    """L1 verification: Check if regulation keywords appear in cited evidence.

    Returns list of {evidence_name, keyword_matches, match_ratio}.
    """
    keywords = _extract_keywords_from_audit_question(audit_question)
    if not keywords:
        return []

    results = []
    for item in evidence_items:
        if not item.found or not item.source_quote:
            results.append(
                {
                    "evidence_name": item.evidence_name,
                    "keyword_matches": [],
                    "match_ratio": 0.0,
                }
            )
            continue

        quote_lower = item.source_quote.lower()
        matches = [kw for kw in keywords if kw.lower() in quote_lower]

        results.append(
            {
                "evidence_name": item.evidence_name,
                "keyword_matches": matches,
                "match_ratio": round(len(matches) / len(keywords), 3)
                if keywords
                else 0.0,
            }
        )

    return results


# ============================================================
# L2: Semantic Verification (LLM-based)
# ============================================================

_SYSTEM_PROMPT = """你是品質管理系統稽核驗證助手。你的任務是驗證已找到的證據是否真正回答了稽核問題。

嚴格規則：
1. 你只做「語意比對驗證」，不做合規性最終判定。
2. 針對每個證據項目，判斷引用的原文是否真正涵蓋該稽核要求。
3. 如果原文只是「提到」但沒有「具體說明如何執行」，標示 adequacy="partial"。
4. 如果原文完全沒有相關內容（錯誤引用），標示 adequacy="irrelevant"。
5. 回答必須使用指定的 JSON 格式。"""

_USER_PROMPT_TEMPLATE = """## 驗證任務

**法規條款**: {clause_id} — {clause_title}
**稽核問題**: {audit_question}

## 已找到的證據

{evidence_section}

## 法規參考資料（如有）

{regulation_text}

## 回答格式

請以 JSON 格式回答：

```json
{{
  "verification_results": [
    {{
      "evidence_name": "證據名稱",
      "adequacy": "full" | "partial" | "irrelevant" | "not_found",
      "semantic_score": 0.0-1.0,
      "explanation": "說明為何判定此等級"
    }}
  ]
}}
```"""


def _build_evidence_section(evidence_items: list[EvidenceItem]) -> str:
    """Format evidence items for the verification prompt."""
    parts = []
    for i, item in enumerate(evidence_items, 1):
        if item.found:
            parts.append(
                f"### 證據 {i}: {item.evidence_name}\n"
                f"- **出處**: {item.source_section or '未標明'}\n"
                f"- **引用原文**: {item.source_quote or '無引用'}\n"
                f"- **搜尋階段評分**: {item.relevance_score or 'N/A'}"
            )
        else:
            parts.append(
                f"### 證據 {i}: {item.evidence_name}\n"
                f"- **狀態**: 未找到\n"
                f"- **原因**: {item.llm_reasoning or '未說明'}"
            )
    return "\n\n".join(parts) if parts else "（無證據項目）"


def _get_regulation_text(
    clause_id: str,
    standard: str,
) -> str:
    """Try to retrieve regulation text from crawled data."""
    try:
        from src.storage.regulatory_markdown_storage import (
            get_regulatory_markdown_store,
        )

        store = get_regulatory_markdown_store()
        # Search for documents matching the standard
        all_docs = store.list_documents(status="active")

        for doc in all_docs:
            title = doc.get("title", "").lower()
            standard_name = standard.replace("_", " ").lower()
            if standard_name in title or standard_name.replace(" ", "") in title:
                full_doc = store.get_document(doc.get("doc_id", ""))
                if full_doc and full_doc.get("content"):
                    content = full_doc["content"]
                    # Try to find the specific clause section
                    clause_pattern = re.compile(
                        rf"(?:^|\n)(?:#+\s*)?{re.escape(clause_id)}[\s.、]",
                        re.MULTILINE,
                    )
                    match = clause_pattern.search(content)
                    if match:
                        # Extract ~500 chars around the match
                        start = max(0, match.start() - 50)
                        end = min(len(content), match.end() + 500)
                        return content[start:end]

        return "（系統中無此法規條文原文，以下驗證基於稽核問題本身）"
    except Exception:
        return "（無法取得法規條文）"


def run_checklist_verify_row(
    row_state: RowState,
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> PhaseResult:
    """Execute Phase 2 checklist verification for a single row.

    Steps:
    1. Run L1 keyword cross-match (code)
    2. Run L2 semantic verification (LLM)
    3. Update evidence items with verification results

    Args:
        row_state: Row with Phase 1 evidence items
        state: Pipeline state
        llm_completion_fn: LLM completion function
        model: Model name
        temperature: LLM temperature
        max_tokens: Max response tokens

    Returns:
        PhaseResult with verification details
    """
    phase_result = PhaseResult(
        phase=Phase.CHECKLIST_VERIFY.value,
        started_at=time.time(),
    )

    try:
        # Reconstruct evidence items from row state
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        if not evidence_items:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No evidence items from Phase 1"}
            phase_result.completed_at = time.time()
            return phase_result

        # L1: Keyword cross-match
        l1_results = run_keyword_crossmatch(evidence_items, row_state.audit_question)

        # L2: Semantic verification (LLM)
        evidence_section = _build_evidence_section(evidence_items)
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            evidence_section=evidence_section,
            regulation_text=regulation_text,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = "LLM token 預算已用盡"
            phase_result.completed_at = time.time()
            return phase_result

        # Call LLM
        response = llm_completion_fn(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        response_text = response.get("content", "")
        usage = response.get("usage", {})

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse L2 results
        l2_results = _parse_verification_response(response_text)

        # Merge L1 + L2 results into evidence items
        for item in evidence_items:
            # Find matching L2 result
            l2_match = next(
                (r for r in l2_results if r.get("evidence_name") == item.evidence_name),
                None,
            )
            if l2_match:
                adequacy = l2_match.get("adequacy", "")
                if adequacy == "irrelevant":
                    item.found = False
                    item.llm_reasoning = l2_match.get("explanation", "")
                elif adequacy == "partial":
                    item.is_inadequate = True
                    item.relevance_score = l2_match.get("semantic_score", 0.5)
                    item.llm_reasoning = l2_match.get("explanation", "")
                elif adequacy == "full":
                    item.relevance_score = l2_match.get("semantic_score", 1.0)

        # Update row evidence items
        row_state.evidence_items = [item.to_dict() for item in evidence_items]

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "l1_keyword_results": l1_results,
            "l2_verification_results": l2_results,
            "evidence_updated": True,
        }
        phase_result.llm_usage = usage
        phase_result.llm_model = response.get("model", model)

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    return phase_result


def _parse_verification_response(response_text: str) -> list[dict]:
    """Parse LLM verification response JSON."""
    json_str = response_text.strip()

    # Handle markdown code blocks
    if "```json" in json_str:
        start = json_str.index("```json") + 7
        end = (
            json_str.index("```", start) if "```" in json_str[start:] else len(json_str)
        )
        json_str = json_str[start:end].strip()
    elif "```" in json_str:
        start = json_str.index("```") + 3
        end = (
            json_str.index("```", start) if "```" in json_str[start:] else len(json_str)
        )
        json_str = json_str[start:end].strip()

    try:
        data = json.loads(json_str)
        return data.get("verification_results", [])
    except (json.JSONDecodeError, KeyError):
        return []
