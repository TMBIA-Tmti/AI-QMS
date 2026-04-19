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
    "run_checklist_verify_document",
    "run_keyword_crossmatch",
]


# ============================================================
# i18n helpers
# ============================================================

from src.chainlit_app.lang_config import lang_key as _lang_key  # noqa: E402


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

_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統稽核驗證助手。你的任務是驗證已找到的證據是否真正回答了稽核問題。

嚴格規則：
1. 你只做「語意比對驗證」，不做合規性最終判定。
2. 針對每個證據項目，判斷引用的原文是否真正涵蓋該稽核要求。
3. 如果原文只是「提到」但沒有「具體說明如何執行」，標示 adequacy="partial"。
4. 如果原文完全沒有相關內容（錯誤引用），標示 adequacy="irrelevant"。
5. 回答必須使用指定的 JSON 格式。""",
    "en": """You are a Quality Management System audit verification assistant. Your task is to verify whether the evidence already found truly answers the audit question.

Strict rules:
1. You perform "semantic comparison verification" only — do not make final compliance judgments.
2. For each evidence item, judge whether the quoted passage truly covers the audit requirement.
3. If the passage merely "mentions" the requirement without "specifying how it is executed", mark adequacy="partial".
4. If the passage is unrelated (wrong citation), mark adequacy="irrelevant".
5. Respond strictly in the specified JSON format.""",
    "ja": """あなたは品質マネジメントシステムの監査検証アシスタントです。あなたの役割は、見つかった証拠が監査質問に真に回答しているかを検証することです。

厳格なルール：
1. 「意味的な照合検証」のみを行い、最終的な適合性判定は行わないこと。
2. 各証拠項目について、引用された原文が監査要件を真にカバーしているかを判断すること。
3. 原文が要件に「言及している」だけで「実施方法を具体的に記述していない」場合、adequacy="partial" と表示すること。
4. 原文が全く関係ない内容（誤った引用）の場合、adequacy="irrelevant" と表示すること。
5. 回答は必ず指定の JSON 形式で行うこと。""",
}

_USER_PROMPT_TEMPLATES: dict[str, str] = {
    "zh": """## 驗證任務

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
```""",
    "en": """## Verification Task

**Regulatory Clause**: {clause_id} — {clause_title}
**Audit Question**: {audit_question}

## Evidence Already Found

{evidence_section}

## Regulatory Reference (if any)

{regulation_text}

## Response Format

Respond in JSON:

```json
{{
  "verification_results": [
    {{
      "evidence_name": "Evidence name",
      "adequacy": "full" | "partial" | "irrelevant" | "not_found",
      "semantic_score": 0.0-1.0,
      "explanation": "Reason for the chosen level"
    }}
  ]
}}
```""",
    "ja": """## 検証タスク

**規制条項**: {clause_id} — {clause_title}
**監査質問**: {audit_question}

## 既に見つかった証拠

{evidence_section}

## 規制参照資料（ある場合）

{regulation_text}

## 回答形式

JSON 形式で回答してください：

```json
{{
  "verification_results": [
    {{
      "evidence_name": "証拠名",
      "adequacy": "full" | "partial" | "irrelevant" | "not_found",
      "semantic_score": 0.0-1.0,
      "explanation": "この等級と判断した理由"
    }}
  ]
}}
```""",
}

# Back-compat aliases
_SYSTEM_PROMPT = _SYSTEM_PROMPTS["zh"]
_USER_PROMPT_TEMPLATE = _USER_PROMPT_TEMPLATES["zh"]


# Localized labels for evidence section building
_EVIDENCE_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "evidence": "證據",
        "source": "出處",
        "unmarked": "未標明",
        "quote": "引用原文",
        "no_quote": "無引用",
        "phase1_score": "搜尋階段評分",
        "status": "狀態",
        "not_found": "未找到",
        "reason": "原因",
        "no_reason": "未說明",
        "no_evidence": "（無證據項目）",
    },
    "en": {
        "evidence": "Evidence",
        "source": "Source",
        "unmarked": "Not labeled",
        "quote": "Quoted text",
        "no_quote": "No quote",
        "phase1_score": "Phase 1 score",
        "status": "Status",
        "not_found": "Not found",
        "reason": "Reason",
        "no_reason": "Not stated",
        "no_evidence": "(No evidence items)",
    },
    "ja": {
        "evidence": "証拠",
        "source": "出典",
        "unmarked": "未記載",
        "quote": "引用原文",
        "no_quote": "引用なし",
        "phase1_score": "第1段階スコア",
        "status": "ステータス",
        "not_found": "未発見",
        "reason": "理由",
        "no_reason": "未記載",
        "no_evidence": "（証拠項目なし）",
    },
}


def _build_evidence_section(
    evidence_items: list[EvidenceItem],
    lang: str = "zh-TW",
) -> str:
    """Format evidence items for the verification prompt."""
    lk = _lang_key(lang)
    L = _EVIDENCE_LABELS[lk]
    parts = []
    for i, item in enumerate(evidence_items, 1):
        if item.found:
            parts.append(
                f"### {L['evidence']} {i}: {item.evidence_name}\n"
                f"- **{L['source']}**: {item.source_section or L['unmarked']}\n"
                f"- **{L['quote']}**: {item.source_quote or L['no_quote']}\n"
                f"- **{L['phase1_score']}**: {item.relevance_score or 'N/A'}"
            )
        else:
            parts.append(
                f"### {L['evidence']} {i}: {item.evidence_name}\n"
                f"- **{L['status']}**: {L['not_found']}\n"
                f"- **{L['reason']}**: {item.llm_reasoning or L['no_reason']}"
            )
    return "\n\n".join(parts) if parts else L["no_evidence"]


def _get_regulation_text(clause_id: str, standard: str) -> str:
    from src.analysis import get_regulation_text

    return get_regulation_text(clause_id, standard, context_chars=500)


# Localized error / status strings
_ERR_MSGS: dict[str, dict[str, str]] = {
    "zh": {
        "budget_exhausted": "LLM token 預算已用盡",
        "empty_response": "LLM 回應為空",
        "call_failed": "LLM 呼叫失敗",
        "no_evidence_phase1": "Phase 1 沒有產生證據項目",
    },
    "en": {
        "budget_exhausted": "LLM token budget exhausted",
        "empty_response": "LLM response was empty",
        "call_failed": "LLM call failed",
        "no_evidence_phase1": "No evidence items from Phase 1",
    },
    "ja": {
        "budget_exhausted": "LLM トークン予算を使い切りました",
        "empty_response": "LLM の応答が空です",
        "call_failed": "LLM 呼び出しに失敗しました",
        "no_evidence_phase1": "第1段階で証拠項目が生成されませんでした",
    },
}


def run_checklist_verify_row(
    row_state: RowState,
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 8192,
    lang: str = "zh-TW",
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

    lk = _lang_key(lang)
    E = _ERR_MSGS[lk]

    try:
        # Reconstruct evidence items from row state
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        if not evidence_items:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": E["no_evidence_phase1"]}
            phase_result.completed_at = time.time()
            return phase_result

        # L1: Keyword cross-match
        l1_results = run_keyword_crossmatch(evidence_items, row_state.audit_question)

        # L2: Semantic verification (LLM)
        evidence_section = _build_evidence_section(evidence_items, lang=lang)
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

        user_prompt = _USER_PROMPT_TEMPLATES[lk].format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            evidence_section=evidence_section,
            regulation_text=regulation_text,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPTS[lk]},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = E["budget_exhausted"]
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

        # LLM error detection
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or response.get("all_failed")
        ):
            error_detail = response_text[:200] if response_text else E["empty_response"]
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"{E['call_failed']}: {error_detail}"
            phase_result.completed_at = time.time()
            return phase_result

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


# ============================================================
# SSE event emission
# ============================================================


def _emit_pipeline_event(run_id: str, event: dict) -> None:
    """Emit pipeline event to SSE listeners for real-time HTML viewing."""
    if not run_id:
        return
    try:
        from src.analysis.report_api import emit_cross_exam_event

        emit_cross_exam_event(run_id, event)
    except ImportError:
        pass


# ============================================================
# Per-document prompt construction
# ============================================================

_DOC_VERIFY_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統稽核驗證助手。你的任務是驗證已找到的證據是否真正回答了各個稽核問題。

嚴格規則：
1. 你只做「語意比對驗證」，不做合規性最終判定。
2. 針對每個證據項目，判斷引用的原文是否真正涵蓋該稽核要求。
3. 如果原文只是「提到」但沒有「具體說明如何執行」，標示 adequacy="partial"。
4. 如果原文完全沒有相關內容（錯誤引用），標示 adequacy="irrelevant"。
5. 回答必須使用指定的 JSON 格式，按條款編號分組。""",
    "en": """You are a Quality Management System audit verification assistant. Your task is to verify whether the evidence already found truly answers each audit question.

Strict rules:
1. You perform "semantic comparison verification" only — do not make final compliance judgments.
2. For each evidence item, judge whether the quoted passage truly covers the audit requirement.
3. If the passage merely "mentions" the requirement without "specifying how it is executed", mark adequacy="partial".
4. If the passage is unrelated (wrong citation), mark adequacy="irrelevant".
5. Respond in the specified JSON format, grouped by clause ID.""",
    "ja": """あなたは品質マネジメントシステムの監査検証アシスタントです。あなたの役割は、見つかった証拠が各監査質問に真に回答しているかを検証することです。

厳格なルール：
1. 「意味的な照合検証」のみを行い、最終的な適合性判定は行わないこと。
2. 各証拠項目について、引用された原文が監査要件を真にカバーしているかを判断すること。
3. 原文が要件に「言及している」だけで「実施方法を具体的に記述していない」場合、adequacy="partial" と表示すること。
4. 原文が全く関係ない内容（誤った引用）の場合、adequacy="irrelevant" と表示すること。
5. 回答は必ず指定の JSON 形式で、条項 ID ごとにグループ化して行うこと。""",
}

_DOC_VERIFY_USER_TEMPLATES: dict[str, str] = {
    "zh": """## 驗證任務

你需要驗證以下 {clause_count} 個法規條款的已找到證據是否充分。

### 各條款的證據

{clauses_evidence_section}

## 回答格式

請以 JSON 格式回答，按**條款的原始編號**（如 "4.1"、"7.1.2"）分組，key 必須與上方「條款 X.X」完全一致：

```json
{{
  "clause_results": {{
    "{example_clause_id}": {{
      "verification_results": [
        {{
          "evidence_name": "證據名稱",
          "adequacy": "full" | "partial" | "irrelevant" | "not_found",
          "semantic_score": 0.0-1.0,
          "explanation": "說明為何判定此等級"
        }}
      ]
    }}
  }}
}}
```""",
    "en": """## Verification Task

Verify whether the evidence already found for the following {clause_count} regulatory clauses is sufficient.

### Evidence Per Clause

{clauses_evidence_section}

## Response Format

Respond in JSON, grouped by the **original clause ID** (e.g. "4.1", "7.1.2"); the key must match the "Clause X.X" labels above exactly:

```json
{{
  "clause_results": {{
    "{example_clause_id}": {{
      "verification_results": [
        {{
          "evidence_name": "Evidence name",
          "adequacy": "full" | "partial" | "irrelevant" | "not_found",
          "semantic_score": 0.0-1.0,
          "explanation": "Reason for the chosen level"
        }}
      ]
    }}
  }}
}}
```""",
    "ja": """## 検証タスク

以下の {clause_count} 個の規制条項について、既に見つかった証拠が十分であるかを検証してください。

### 条項ごとの証拠

{clauses_evidence_section}

## 回答形式

JSON 形式で、**元の条項 ID**（例："4.1"、"7.1.2"）ごとにグループ化して回答してください。キーは上記「条項 X.X」の表記と完全に一致する必要があります：

```json
{{
  "clause_results": {{
    "{example_clause_id}": {{
      "verification_results": [
        {{
          "evidence_name": "証拠名",
          "adequacy": "full" | "partial" | "irrelevant" | "not_found",
          "semantic_score": 0.0-1.0,
          "explanation": "この等級と判断した理由"
        }}
      ]
    }}
  }}
}}
```""",
}

# Back-compat aliases
_DOC_VERIFY_SYSTEM_PROMPT = _DOC_VERIFY_SYSTEM_PROMPTS["zh"]
_DOC_VERIFY_USER_TEMPLATE = _DOC_VERIFY_USER_TEMPLATES["zh"]


# Localized labels for clauses_evidence_section header
_DOC_HEADER_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "clause": "條款",
        "audit_question": "稽核問題",
        "regulation_ref": "法規參考",
        "found_evidence": "已找到證據",
    },
    "en": {
        "clause": "Clause",
        "audit_question": "Audit Question",
        "regulation_ref": "Regulatory Reference",
        "found_evidence": "Evidence Already Found",
    },
    "ja": {
        "clause": "条項",
        "audit_question": "監査質問",
        "regulation_ref": "規制参照",
        "found_evidence": "既に見つかった証拠",
    },
}


def _normalize_clause_id(clause_id: str) -> str:
    """Normalize a clause ID for fuzzy matching (strip spaces, dashes, titles)."""
    # Take only the first token that looks like a clause number (digits and dots)
    m = re.match(r"[\d]+(?:\.[\d]+)*", clause_id.strip())
    return m.group(0) if m else clause_id.strip().lower()


def _parse_doc_verify_response(
    response_text: str,
    rows: list,
) -> dict[str, list[dict]]:
    """Parse per-document verification LLM response into per-clause results.

    Uses fuzzy matching so LLM keys like "4.1 — 組織背景" still map to
    row.clause_id == "4.1".

    Returns:
        Dict mapping clause_id -> list of verification result dicts
    """
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

    # Build normalized lookup: norm_key -> row.clause_id
    row_norm_map: dict[str, str] = {
        _normalize_clause_id(row.clause_id): row.clause_id for row in rows
    }

    result: dict[str, list[dict]] = {}

    try:
        data = json.loads(json_str)
        clause_results = data.get("clause_results", {})

        for llm_key, clause_data in clause_results.items():
            verification_results = clause_data.get("verification_results", [])

            # Try exact match first, then normalized fuzzy match
            if llm_key in row_norm_map.values():
                result[llm_key] = verification_results
            else:
                norm_key = _normalize_clause_id(llm_key)
                canonical = row_norm_map.get(norm_key)
                if canonical:
                    result[canonical] = verification_results
                else:
                    # Keep as-is (may be matched later or discarded)
                    result[llm_key] = verification_results

    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Ensure all row clause_ids have entries (empty list if LLM missed them)
    for row in rows:
        if row.clause_id not in result:
            result[row.clause_id] = []

    return result


# ============================================================
# Per-document Phase execution (PRIMARY)
# ============================================================


def run_checklist_verify_document(
    doc_id: str,
    rows: list[RowState],
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 8192,
    run_id: str = "",
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 2 checklist verification for ALL clauses of one document.

    ONE LLM call covers all clauses this document maps to.

    Args:
        doc_id: Document ID
        rows: All RowState objects for this document (with Phase 1 evidence)
        state: Pipeline state (for budget tracking)
        llm_completion_fn: LLM completion function (returns dict)
        model: LLM model name
        temperature: LLM temperature
        max_tokens: Max tokens for response
        run_id: Pipeline run ID for SSE emission
        lang: UI language code (zh-TW / en-US / ja-JP); falls back to en for others.

    Returns:
        PhaseResult with per-clause verification breakdown
    """
    phase_result = PhaseResult(
        phase=Phase.CHECKLIST_VERIFY.value,
        started_at=time.time(),
    )

    lk = _lang_key(lang)
    E = _ERR_MSGS[lk]
    H = _DOC_HEADER_LABELS[lk]

    try:
        # Build per-clause evidence sections
        clauses_parts = []
        has_evidence = False
        for i, row in enumerate(rows, 1):
            evidence_items = [EvidenceItem.from_dict(e) for e in row.evidence_items]
            if not evidence_items:
                continue
            has_evidence = True

            # L1: keyword cross-match per clause
            run_keyword_crossmatch(evidence_items, row.audit_question)

            evidence_section = _build_evidence_section(evidence_items, lang=lang)
            regulation_text = _get_regulation_text(row.clause_id, row.standard)

            clauses_parts.append(
                f"### {i}. {H['clause']} {row.clause_id} — {row.clause_title}\n"
                f"**{H['audit_question']}**: {row.audit_question}\n\n"
                f"**{H['regulation_ref']}**: {regulation_text[:300]}\n\n"
                f"**{H['found_evidence']}**:\n{evidence_section}"
            )

        if not has_evidence:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": E["no_evidence_phase1"]}
            phase_result.completed_at = time.time()
            return phase_result

        clauses_evidence_section = "\n\n".join(clauses_parts)

        # Use first row's clause_id as example in the JSON template
        example_clause_id = rows[0].clause_id if rows else "4.1"

        user_prompt = _DOC_VERIFY_USER_TEMPLATES[lk].format(
            clause_count=len(rows),
            clauses_evidence_section=clauses_evidence_section,
            example_clause_id=example_clause_id,
        )

        messages = [
            {"role": "system", "content": _DOC_VERIFY_SYSTEM_PROMPTS[lk]},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = E["budget_exhausted"]
            phase_result.completed_at = time.time()
            return phase_result

        doc_title = rows[0].doc_title if rows else doc_id

        # SSE: emit before LLM call
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_2_start",
                "phase": "checklist_verify",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows],
                "clause_count": len(rows),
                "prompt_preview": user_prompt[:500],
            },
        )

        # Call LLM with retry (handles transient network errors like incomplete chunked read)
        response = None
        last_error = ""
        for _attempt in range(3):
            response = llm_completion_fn(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            response_text_attempt = response.get("content", "")
            if (
                response_text_attempt
                and not response_text_attempt.startswith("[ERROR]")
                and not response.get("all_failed")
            ):
                break
            last_error = response_text_attempt[:200] if response_text_attempt else E["empty_response"]
            import time as _time
            _time.sleep(2 * (_attempt + 1))  # back-off: 2s, 4s

        response_text = response.get("content", "") if response else ""
        usage = response.get("usage", {}) if response else {}

        # LLM error detection (all retries failed)
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or (response and response.get("all_failed"))
        ):
            error_detail = last_error or (response_text[:200] if response_text else E["empty_response"])
            # Localized "after 3 retries" suffix
            _retry_suffix = {
                "zh": "（3次重試後）",
                "en": "(after 3 retries)",
                "ja": "（3回再試行後）",
            }[lk]
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"{E['call_failed']}: {error_detail}"
            phase_result.completed_at = time.time()
            _emit_pipeline_event(
                run_id,
                {
                    "type": "phase_2_error",
                    "phase": "checklist_verify",
                    "doc_id": doc_id,
                    "error": f"{E['call_failed']} {_retry_suffix}: {error_detail}",
                },
            )
            return phase_result

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse per-clause verification results
        clause_verify = _parse_doc_verify_response(response_text, rows)

        # Distribute verification results back to individual rows
        for row in rows:
            l2_results = clause_verify.get(row.clause_id, [])
            evidence_items = [EvidenceItem.from_dict(e) for e in row.evidence_items]

            for item in evidence_items:
                l2_match = next(
                    (
                        r
                        for r in l2_results
                        if r.get("evidence_name") == item.evidence_name
                    ),
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

            row.evidence_items = [item.to_dict() for item in evidence_items]

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "doc_id": doc_id,
            "clause_count": len(rows),
            "evidence_updated": True,
        }
        phase_result.llm_usage = usage
        phase_result.llm_model = response.get("model", model)

        # SSE: emit after LLM call
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_2_result",
                "phase": "checklist_verify",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows],
                "llm_response": response_text[:2000],
                "usage": usage,
            },
        )

        # SSE: conversation-style event
        _v_details = []
        for row in rows:
            l2_results = clause_verify.get(row.clause_id, [])
            for vr in l2_results:
                _v_details.append(
                    {
                        "clause_id": row.clause_id,
                        "evidence_name": vr.get("evidence_name", ""),
                        "adequacy": vr.get("adequacy", ""),
                        "explanation": vr.get("explanation", "")[:200],
                    }
                )
        _full_count = sum(1 for d in _v_details if d["adequacy"] == "full")
        _partial_count = sum(1 for d in _v_details if d["adequacy"] == "partial")
        _irrelevant_count = sum(1 for d in _v_details if d["adequacy"] == "irrelevant")

        # Localized question/answer summary
        if lk == "ja":
            _question_summary = (
                f"文書「{doc_title}」({doc_id}) 内の {len(rows)} 個の条項の証拠の十分性を検証してください。"
                f"各証拠項目について、十分(full)、部分的(partial)、無関係(irrelevant) のいずれかを判定します。"
            )
            _answer_summary = (
                f"検証完了：合計 {len(_v_details)} 件の証拠、"
                f"十分 {_full_count} ✅、部分的 {_partial_count} ⚠️、無関係 {_irrelevant_count} ❌。"
            )
        elif lk == "en":
            _question_summary = (
                f"Verify the adequacy of evidence for {len(rows)} clauses in document \"{doc_title}\" ({doc_id}). "
                f"For each evidence item, judge whether it is full, partial, or irrelevant."
            )
            _answer_summary = (
                f"Verification complete: {len(_v_details)} evidence items in total — "
                f"full: {_full_count} ✅, partial: {_partial_count} ⚠️, irrelevant: {_irrelevant_count} ❌."
            )
        else:
            _question_summary = (
                f"請驗證文件「{doc_title}」({doc_id}) 中 {len(rows)} 個條款"
                f"的證據充分性。逐一檢查每項證據是否充分(full)、部分(partial)或不相關(irrelevant)。"
            )
            _answer_summary = (
                f"驗證完成：共 {len(_v_details)} 項證據，"
                f"充分 {_full_count} ✅、部分 {_partial_count} ⚠️、不相關 {_irrelevant_count} ❌。"
            )

        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_2_conversation",
                "doc_id": doc_id,
                "clause_ids": [r.clause_id for r in rows],
                "question_summary": _question_summary,
                "answer_summary": _answer_summary,
                "details": {"clauses": _v_details},
            },
        )

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_2_error",
                "phase": "checklist_verify",
                "doc_id": doc_id,
                "error": str(e)[:500],
            },
        )

    phase_result.completed_at = time.time()
    return phase_result
