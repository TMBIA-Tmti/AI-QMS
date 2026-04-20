"""
AI-QMS — Phase 4: Remediation Suggestions
==========================================

LLM call #3 — Only invoked when gaps are found (verdict != full_compliance).

The LLM receives:
  - The gap analysis results (what's missing/inadequate)
  - The regulation clause text (from crawled data)
  - The audit question and expected evidence

Output: Specific remediation suggestions citing regulation text,
        with priority and actionable steps.

SKIPPED when verdict == full_compliance (no gaps to fix).
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
    "run_remediation_row",
    "run_remediation_document",
]


# ============================================================
# Prompt construction (bilingual: zh / en / ja)
# ============================================================


def _lang_key(lang: str) -> str:
    """Normalize a UI language code to a prompt dict key (zh / en / ja).

    Falls back to 'en' for anything other than zh/ja.
    """
    if not lang:
        return "zh"
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("ja"):
        return "ja"
    if lang.startswith("en"):
        return "en"
    return "en"


_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統改善建議助手。你的任務是根據差距分析結果，提供具體的品質文件改善建議。

嚴格規則：
1. 每項建議必須引用對應的法規條文原文作為依據。
2. 建議必須具體可執行，包含「修改哪份文件」「修改哪個段落」「建議修改方向」。
3. 不提供模糊的方向性建議（如「應加強管理」），每項都要可操作。
4. 如果法規條文不可用，以稽核問題本身作為改善依據。
5. 回答必須使用指定的 JSON 格式。
6. 【內容完整性】每條建議（suggestions[]）的 action 及 example_content 字段最多 2000 字，詳細說明修改步驟與具體範例內容；summary 最多 500 字；每條輸出上限 10000 字（中文）或 10000 words（英文），確保建議內容完整不截斷。""",
    "en": """You are a Quality Management System improvement recommendation assistant. Your task is to provide specific, actionable document improvement recommendations based on gap analysis results.

Strict Rules:
1. Each recommendation must cite the corresponding regulatory text as its basis.
2. Recommendations must be specific and actionable: include "which document to modify", "which section to modify", "recommended direction of change".
3. Do not provide vague directional recommendations (e.g., "strengthen management") — every item must be operable.
4. If regulatory text is unavailable, use the audit question itself as the improvement basis.
5. Respond in the specified JSON format.
6. [Content Completeness] Each recommendation's action and example_content fields up to 2000 words each; summary up to 500 words; each item output limit 10000 words. Do not truncate.""",
    "ja": """あなたは品質マネジメントシステム改善提案アシスタントです。ギャップ分析結果に基づき、具体的で実行可能な文書改善提案を提供することが任務です。

厳格なルール：
1. 各提案は対応する規制条文を根拠として引用しなければならない。
2. 提案は具体的で実行可能であること：「どの文書を修正するか」「どのセクションを修正するか」「推奨変更方向」を含む。
3. 曖昧な方向性の提案（例：「管理を強化する」）は提供しない。各項目は実行可能でなければならない。
4. 規制テキストが利用できない場合、監査質問自体を改善の根拠として使用する。
5. 指定されたJSON形式で回答する。
6. 【コンテンツの完全性】各提案のactionとexample_contentフィールドはそれぞれ最大2000語；summaryは最大500語；各項目の出力上限は10000語。切り捨てないこと。""",
}

# Backward-compatible alias removed — language is routed via _SYSTEM_PROMPTS[lk] at call site.
# _SYSTEM_PROMPT = _SYSTEM_PROMPTS["zh"]

_USER_PROMPT_TEMPLATES: dict[str, str] = {
    "zh": """## 改善建議任務

**法規條款**: {clause_id} — {clause_title}
**稽核問題**: {audit_question}
**風險等級**: {risk_level}
**差距類型**: {gap_severity}

## 差距分析結果

{gap_analysis_section}

## 法規參考資料（如有）

{regulation_text}

## 公司文件資訊

**文件編號**: {doc_id}
**文件標題**: {doc_title}

## 回答格式

請以 JSON 格式回答（每條建議的 action 和 example_content 上限 2000 字，summary 上限 500 字，確保內容完整）：

```json
{{
  "remediation": {{
    "summary": "改善方向總述（上限 500 字）：概述本文件的整體合規落差及改善優先序",
    "priority": "high" | "medium" | "low",
    "suggestions": [
      {{
        "action": "具體修改動作（上限 2000 字）：詳述（1）需修改的確切段落或新增的章節，（2）修改的具體步驟及負責角色，（3）修改後應達到的合規標準，（4）驗證改善成效的方法。不得截斷。",
        "target_section": "建議修改的文件段落/章節（含文件編號、章節號碼及現有標題）",
        "regulation_basis": "法規依據（引用 ISO 13485:2016 條款編號、條文原文及所有適用子條款）",
        "example_content": "建議新增或修改的內容範例（上限 2000 字）：提供可直接複製使用的完整文字範本，包含必要的欄位、記錄格式或程序步驟，反映法規實質要求，不得截斷。"
      }}
    ],
    "regulation_citation": "最相關的法規條文完整引用（含所有子條款原文）"
  }}
}}
```""",
    "en": """## Improvement Recommendation Task

**Regulatory Clause**: {clause_id} — {clause_title}
**Audit Question**: {audit_question}
**Risk Level**: {risk_level}
**Gap Type**: {gap_severity}

## Gap Analysis Results

{gap_analysis_section}

## Regulatory Reference (if available)

{regulation_text}

## Company Document Information

**Document ID**: {doc_id}
**Document Title**: {doc_title}

## Response Format

Please respond in JSON format (action and example_content up to 2000 words each, summary up to 500 words):

```json
{{
  "remediation": {{
    "summary": "Overall improvement direction (up to 500 words): summarize compliance gaps and improvement priorities",
    "priority": "high" | "medium" | "low",
    "suggestions": [
      {{
        "action": "Specific modification action (up to 2000 words): detail (1) exact paragraph or section to modify/add, (2) specific steps and responsible roles, (3) compliance standard to achieve, (4) method to verify improvement. Do not truncate.",
        "target_section": "Recommended section to modify (include document ID, section number, current title)",
        "regulation_basis": "Regulatory basis (cite ISO 13485:2016 clause number, text, and all applicable sub-clauses)",
        "example_content": "Recommended content example (up to 2000 words): complete text template ready to use, including necessary fields, record formats, or procedure steps. Do not truncate."
      }}
    ],
    "regulation_citation": "Most relevant regulatory text complete citation (including all sub-clause text)"
  }}
}}
```""",
    "ja": """## 改善提案タスク

**規制条項**: {clause_id} — {clause_title}
**監査質問**: {audit_question}
**リスクレベル**: {risk_level}
**ギャップタイプ**: {gap_severity}

## ギャップ分析結果

{gap_analysis_section}

## 規制参照資料（利用可能な場合）

{regulation_text}

## 会社文書情報

**文書番号**: {doc_id}
**文書タイトル**: {doc_title}

## 回答形式

JSON形式で回答してください（actionとexample_contentは各最大2000語、summaryは最大500語）：

```json
{{
  "remediation": {{
    "summary": "改善方向の概要（最大500語）：文書の全体的なコンプライアンスギャップと改善優先順位",
    "priority": "high" | "medium" | "low",
    "suggestions": [
      {{
        "action": "具体的な修正アクション（最大2000語）：（1）修正または追加する正確な段落またはセクション、（2）具体的な手順と責任者、（3）達成すべきコンプライアンス基準、（4）改善効果の検証方法。切り捨てないこと。",
        "target_section": "修正推奨セクション（文書番号、セクション番号、現在のタイトルを含む）",
        "regulation_basis": "規制根拠（ISO 13485:2016条項番号、テキスト、適用されるすべてのサブ条項を引用）",
        "example_content": "推奨コンテンツ例（最大2000語）：直接使用可能な完全なテキストテンプレート（必要なフィールド、記録形式、または手順ステップを含む）。切り捨てないこと。"
      }}
    ],
    "regulation_citation": "最も関連性の高い規制テキストの完全引用（すべてのサブ条項テキストを含む）"
  }}
}}
```""",
}

# Backward-compatible alias
_USER_PROMPT_TEMPLATE = _USER_PROMPT_TEMPLATES["zh"]


# ============================================================
# Gap analysis section headers (bilingual)
# ============================================================

_GAP_SECTION_HEADERS: dict[str, dict[str, str]] = {
    "zh": {
        "not_found": "### 未找到的證據項目",
        "inadequate": "\n### 內容不充分的證據項目",
        "outdated": "\n### 版本過期的項目",
        "reason": "原因",
        "current_content": "現有內容",
        "no_quote": "無引用",
        "inadequate_reason": "不足原因",
        "source": "出處",
        "unknown": "未知",
        "none_explained": "未說明",
        "empty_notice": "（無具體差距項目，但整體判定為非完全符合）",
    },
    "en": {
        "not_found": "### Evidence Items Not Found",
        "inadequate": "\n### Evidence Items with Insufficient Content",
        "outdated": "\n### Outdated Version Items",
        "reason": "Reason",
        "current_content": "Current content",
        "no_quote": "No quote",
        "inadequate_reason": "Inadequacy reason",
        "source": "Source",
        "unknown": "Unknown",
        "none_explained": "Not explained",
        "empty_notice": "(No specific gap items, but overall verdict is not full compliance)",
    },
    "ja": {
        "not_found": "### 見つからなかった証拠項目",
        "inadequate": "\n### 内容が不十分な証拠項目",
        "outdated": "\n### バージョンが古い項目",
        "reason": "理由",
        "current_content": "現在の内容",
        "no_quote": "引用なし",
        "inadequate_reason": "不十分な理由",
        "source": "出典",
        "unknown": "不明",
        "none_explained": "説明なし",
        "empty_notice": "（具体的なギャップ項目はないが、全体判定は完全適合ではない）",
    },
}


def _build_gap_analysis_section(
    evidence_items: list[EvidenceItem],
    verdict: str,
    lang: str = "zh-TW",
) -> str:
    """Format gap analysis results for the remediation prompt."""
    lk = _lang_key(lang)
    h = _GAP_SECTION_HEADERS[lk]
    parts = []

    # Group by status
    not_found = [e for e in evidence_items if not e.found]
    inadequate = [e for e in evidence_items if e.found and e.is_inadequate]
    outdated = [e for e in evidence_items if e.found and e.is_outdated]

    if not_found:
        parts.append(h["not_found"])
        for item in not_found:
            parts.append(
                f"- **{item.evidence_name}**\n  {h['reason']}: {item.llm_reasoning or h['none_explained']}"
            )

    if inadequate:
        parts.append(h["inadequate"])
        for item in inadequate:
            parts.append(
                f"- **{item.evidence_name}**\n"
                f"  {h['current_content']}: {item.source_quote or h['no_quote']}\n"
                f"  {h['inadequate_reason']}: {item.llm_reasoning or h['none_explained']}"
            )

    if outdated:
        parts.append(h["outdated"])
        for item in outdated:
            parts.append(
                f"- **{item.evidence_name}**\n  {h['source']}: {item.source_section or h['unknown']}"
            )

    if not parts:
        parts.append(h["empty_notice"])

    return "\n".join(parts)


def _get_regulation_text(clause_id: str, standard: str) -> str:
    from src.analysis import get_regulation_text

    return get_regulation_text(clause_id, standard, context_chars=800)


def _parse_remediation_response(response_text: str) -> dict:
    """Parse LLM remediation response JSON."""
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
        return data.get("remediation", {})
    except (json.JSONDecodeError, KeyError):
        return {}


# ============================================================
# Phase execution
# ============================================================


def run_remediation_row(
    row_state: RowState,
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.3,
    max_tokens: int = 0,
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 4 remediation suggestions for a single row.

    SKIPPED when:
    - verdict == "full_compliance" (no gaps)
    - No evidence items from earlier phases

    Args:
        row_state: Row with Phase 1-3 results
        state: Pipeline state
        llm_completion_fn: LLM completion function
        model: Model name
        temperature: LLM temperature (slightly higher for creative suggestions)
        max_tokens: Max response tokens
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja')

    Returns:
        PhaseResult with remediation suggestions
    """
    lk = _lang_key(lang)
    phase_result = PhaseResult(
        phase=Phase.REMEDIATION.value,
        started_at=time.time(),
    )

    # Localized static strings
    _reason_full_compliance = {
        "zh": "完全符合，無需改善建議",
        "en": "Full compliance — no remediation needed",
        "ja": "完全適合——改善提案は不要",
    }[lk]
    _not_assessed = {"zh": "未評估", "en": "Not assessed", "ja": "未評価"}[lk]
    _budget_exceeded_msg = {
        "zh": "LLM token 預算已用盡",
        "en": "LLM token budget exhausted",
        "ja": "LLMトークン予算を使い果たしました",
    }[lk]
    _llm_empty_msg = {
        "zh": "LLM 回應為空",
        "en": "LLM response was empty",
        "ja": "LLM応答が空でした",
    }[lk]
    _llm_call_failed = {
        "zh": "LLM 呼叫失敗",
        "en": "LLM call failed",
        "ja": "LLM呼び出し失敗",
    }[lk]
    _parse_warning = {
        "zh": "LLM 回應格式無法解析，但已完成呼叫",
        "en": "LLM response format could not be parsed, but call completed",
        "ja": "LLM応答形式を解析できませんでしたが、呼び出しは完了しました",
    }[lk]

    try:
        # Skip if fully compliant — no remediation needed
        if row_state.verdict == "full_compliance":
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": _reason_full_compliance}
            phase_result.completed_at = time.time()
            return phase_result

        # Reconstruct evidence items
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        if not evidence_items:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No evidence items from earlier phases"}
            phase_result.completed_at = time.time()
            return phase_result

        # Auto-size max_tokens based on gap count: more gaps → longer suggestions needed.
        # Floor at 8192 to guarantee complete output; ceiling at 16384 for very large gaps.
        if max_tokens == 0:
            gap_count = sum(
                1 for e in evidence_items
                if not e.found or e.is_inadequate or e.is_outdated
            )
            max_tokens = max(8192, min(16384, gap_count * 2000 + 4096))

        # Build gap analysis section
        gap_section = _build_gap_analysis_section(
            evidence_items, row_state.verdict or "", lang=lang
        )

        # Get regulation text for citation
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

        # Import risk display for context
        from src.analysis.risk_matrix import RISK_LEVEL_DISPLAY

        risk_display = RISK_LEVEL_DISPLAY.get(row_state.risk_level or "", {})
        label_key = "label_en" if lk == "en" else "label_ja" if lk == "ja" else "label_zh"
        risk_label = risk_display.get(
            label_key, risk_display.get("label_zh", row_state.risk_level or _not_assessed)
        )

        user_prompt = _USER_PROMPT_TEMPLATES[lk].format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            risk_level=risk_label,
            gap_severity=row_state.gap_severity or _not_assessed,
            gap_analysis_section=gap_section,
            regulation_text=regulation_text,
            doc_id=row_state.doc_id,
            doc_title=row_state.doc_title,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPTS[lk]},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = _budget_exceeded_msg
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

        # Detect LLM error responses
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or response.get("all_failed")
        ):
            error_detail = response_text[:200] if response_text else _llm_empty_msg
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"{_llm_call_failed}: {error_detail}"
            phase_result.completed_at = time.time()
            return phase_result

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse remediation
        remediation = _parse_remediation_response(response_text)

        if remediation:
            # Store key results in row state
            row_state.remediation_suggestion = remediation.get("summary", "")
            row_state.remediation_regulation_cite = remediation.get(
                "regulation_citation", ""
            )

            phase_result.status = PhaseStatus.COMPLETED.value
            phase_result.output = {
                "remediation": remediation,
                "suggestion_count": len(remediation.get("suggestions", [])),
                "priority": remediation.get("priority", "medium"),
            }
        else:
            phase_result.status = PhaseStatus.COMPLETED.value
            phase_result.output = {
                "remediation": {},
                "suggestion_count": 0,
                "parse_warning": _parse_warning,
            }

        phase_result.llm_usage = usage
        phase_result.llm_model = response.get("model", model)

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    return phase_result


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

_DOC_REMEDIATION_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統改善建議助手。你的任務是根據差距分析結果，針對一份文件的多個法規條款提供具體的改善建議。

嚴格規則：
1. 每項建議必須引用對應的法規條文原文作為依據。
2. 建議必須具體可執行，包含「修改哪個段落」「建議修改方向」。
3. 不提供模糊的方向性建議。
4. 如果法規條文不可用，以稽核問題本身作為改善依據。
5. 回答必須使用指定的 JSON 格式，按條款編號分組。""",
    "en": """You are a Quality Management System improvement recommendation assistant. Your task is to provide specific improvement recommendations for multiple regulatory clauses of a single document based on gap analysis results.

Strict Rules:
1. Each recommendation must cite the corresponding regulatory text as its basis.
2. Recommendations must be specific and actionable — include "which section to modify" and "recommended direction".
3. Do not provide vague directional recommendations.
4. If regulatory text is unavailable, use the audit question itself as the improvement basis.
5. Respond in the specified JSON format, grouped by clause ID.""",
    "ja": """あなたは品質マネジメントシステム改善提案アシスタントです。ギャップ分析結果に基づき、1つの文書の複数の規制条項に対して具体的な改善提案を提供することが任務です。

厳格なルール：
1. 各提案は対応する規制条文を根拠として引用しなければならない。
2. 提案は具体的で実行可能であること：「どのセクションを修正するか」「推奨変更方向」を含む。
3. 曖昧な方向性の提案は提供しない。
4. 規制テキストが利用できない場合、監査質問自体を改善の根拠として使用する。
5. 指定されたJSON形式で、条項番号ごとにグループ化して回答する。""",
}

# _DOC_REMEDIATION_SYSTEM_PROMPT alias removed — language routed via _DOC_REMEDIATION_SYSTEM_PROMPTS[lk] at call site.
# _DOC_REMEDIATION_SYSTEM_PROMPT = _DOC_REMEDIATION_SYSTEM_PROMPTS["zh"]

_DOC_REMEDIATION_USER_TEMPLATES: dict[str, str] = {
    "zh": """## 改善建議任務

你需要針對以下 {clause_count} 個法規條款的差距提供改善建議。

**文件編號**: {doc_id}
**文件標題**: {doc_title}

### 各條款的差距分析

{clauses_gap_section}

## 回答格式

請以 JSON 格式回答，按條款編號分組：

```json
{{
  "clause_results": {{
    "條款編號": {{
      "remediation": {{
        "summary": "改善方向總述（一句話）",
        "priority": "high" | "medium" | "low",
        "suggestions": [
          {{
            "action": "具體修改動作",
            "target_section": "建議修改的文件段落",
            "regulation_basis": "法規依據",
            "example_content": "建議內容範例"
          }}
        ],
        "regulation_citation": "最相關的法規條文完整引用"
      }}
    }}
  }}
}}
```""",
    "en": """## Improvement Recommendation Task

Provide improvement recommendations for the gaps in the following {clause_count} regulatory clauses.

**Document ID**: {doc_id}
**Document Title**: {doc_title}

### Gap Analysis for Each Clause

{clauses_gap_section}

## Response Format

Respond in JSON format, grouped by clause ID:

```json
{{
  "clause_results": {{
    "clause_id": {{
      "remediation": {{
        "summary": "Overall improvement direction (one sentence)",
        "priority": "high" | "medium" | "low",
        "suggestions": [
          {{
            "action": "Specific modification action",
            "target_section": "Recommended section to modify",
            "regulation_basis": "Regulatory basis",
            "example_content": "Recommended content example"
          }}
        ],
        "regulation_citation": "Most relevant regulatory text complete citation"
      }}
    }}
  }}
}}
```""",
    "ja": """## 改善提案タスク

以下の{clause_count}個の規制条項のギャップに対する改善提案を提供してください。

**文書番号**: {doc_id}
**文書タイトル**: {doc_title}

### 各条項のギャップ分析

{clauses_gap_section}

## 回答形式

条項番号ごとにグループ化してJSON形式で回答してください：

```json
{{
  "clause_results": {{
    "条項番号": {{
      "remediation": {{
        "summary": "改善方向の概要（一文）",
        "priority": "high" | "medium" | "low",
        "suggestions": [
          {{
            "action": "具体的な修正アクション",
            "target_section": "修正推奨セクション",
            "regulation_basis": "規制根拠",
            "example_content": "推奨コンテンツ例"
          }}
        ],
        "regulation_citation": "最も関連性の高い規制テキストの完全引用"
      }}
    }}
  }}
}}
```""",
}

_DOC_REMEDIATION_USER_TEMPLATE = _DOC_REMEDIATION_USER_TEMPLATES["zh"]


def _parse_doc_remediation_response(
    response_text: str,
    rows: list,
) -> dict[str, dict]:
    """Parse per-document remediation LLM response into per-clause results.

    Returns:
        Dict mapping clause_id -> remediation dict
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

    result: dict[str, dict] = {}

    try:
        data = json.loads(json_str)
        clause_results = data.get("clause_results", {})

        for clause_id, clause_data in clause_results.items():
            result[clause_id] = clause_data.get("remediation", {})

    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Ensure all clauses have entries
    for row in rows:
        if row.clause_id not in result:
            result[row.clause_id] = {}

    return result


# ============================================================
# Per-document Phase execution (PRIMARY)
# ============================================================


def run_remediation_document(
    doc_id: str,
    rows: list[RowState],
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.3,
    max_tokens: int = 0,
    run_id: str = "",
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 4 remediation for ALL clauses of one document.

    ONE LLM call covers all clauses this document maps to.
    SKIPPED for rows where verdict == 'full_compliance'.

    Args:
        doc_id: Document ID
        rows: All RowState objects for this document
        state: Pipeline state (for budget tracking)
        llm_completion_fn: LLM completion function (returns dict)
        model: LLM model name
        temperature: LLM temperature (slightly higher for creative suggestions)
        max_tokens: Max tokens for response
        run_id: Pipeline run ID for SSE emission

    Returns:
        PhaseResult with per-clause remediation breakdown
    """
    lk = _lang_key(lang)
    phase_result = PhaseResult(
        phase=Phase.REMEDIATION.value,
        started_at=time.time(),
    )

    _reason_all_compliant = {
        "zh": "所有條款完全符合，無需改善建議",
        "en": "All clauses fully compliant — no remediation needed",
        "ja": "すべての条項が完全適合のため改善提案は不要",
    }[lk]
    _not_assessed = {"zh": "未評估", "en": "Not assessed", "ja": "未評価"}[lk]
    _budget_exceeded_msg = {
        "zh": "LLM token 預算已用盡",
        "en": "LLM token budget exhausted",
        "ja": "LLMトークン予算を使い果たしました",
    }[lk]
    _llm_empty_msg = {
        "zh": "LLM 回應為空",
        "en": "LLM response was empty",
        "ja": "LLM応答が空でした",
    }[lk]
    _llm_call_failed = {
        "zh": "LLM 呼叫失敗",
        "en": "LLM call failed",
        "ja": "LLM呼び出し失敗",
    }[lk]
    _clause_header_tpl = {
        "zh": (
            "### {i}. 條款 {clause_id} — {clause_title}\n"
            "**稽核問題**: {audit_question}\n"
            "**風險等級**: {risk_label}\n"
            "**差距類型**: {gap_severity}\n\n"
            "**差距分析**:\n{gap_section}\n\n"
            "**法規參考**: {regulation_text}"
        ),
        "en": (
            "### {i}. Clause {clause_id} — {clause_title}\n"
            "**Audit Question**: {audit_question}\n"
            "**Risk Level**: {risk_label}\n"
            "**Gap Type**: {gap_severity}\n\n"
            "**Gap Analysis**:\n{gap_section}\n\n"
            "**Regulatory Reference**: {regulation_text}"
        ),
        "ja": (
            "### {i}. 条項 {clause_id} — {clause_title}\n"
            "**監査質問**: {audit_question}\n"
            "**リスクレベル**: {risk_label}\n"
            "**ギャップタイプ**: {gap_severity}\n\n"
            "**ギャップ分析**:\n{gap_section}\n\n"
            "**規制参照**: {regulation_text}"
        ),
    }[lk]

    try:
        # Filter rows that need remediation (not fully compliant)
        rows_needing_remediation = [r for r in rows if r.verdict != "full_compliance"]

        if not rows_needing_remediation:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": _reason_all_compliant}
            phase_result.completed_at = time.time()
            return phase_result

        # Auto-size max_tokens: base per clause + per gap item.
        # Floor at 8192; ceiling at 16384 to guarantee no truncation.
        if max_tokens == 0:
            total_gap_items = sum(
                sum(
                    1 for e in [EvidenceItem.from_dict(ei) for ei in row.evidence_items]
                    if not e.found or e.is_inadequate or e.is_outdated
                )
                for row in rows_needing_remediation
            )
            n_clauses = len(rows_needing_remediation)
            max_tokens = max(8192, min(16384, n_clauses * 1200 + total_gap_items * 400))

        # Import risk display for context
        from src.analysis.risk_matrix import RISK_LEVEL_DISPLAY

        label_key = "label_en" if lk == "en" else "label_ja" if lk == "ja" else "label_zh"

        # Build per-clause gap sections
        clauses_parts = []
        for i, row in enumerate(rows_needing_remediation, 1):
            evidence_items = [EvidenceItem.from_dict(e) for e in row.evidence_items]
            gap_section = _build_gap_analysis_section(
                evidence_items, row.verdict or "", lang=lang
            )
            regulation_text = _get_regulation_text(row.clause_id, row.standard)
            risk_display = RISK_LEVEL_DISPLAY.get(row.risk_level or "", {})
            risk_label = risk_display.get(
                label_key,
                risk_display.get("label_zh", row.risk_level or _not_assessed),
            )

            clauses_parts.append(
                _clause_header_tpl.format(
                    i=i,
                    clause_id=row.clause_id,
                    clause_title=row.clause_title,
                    audit_question=row.audit_question,
                    risk_label=risk_label,
                    gap_severity=row.gap_severity or _not_assessed,
                    gap_section=gap_section,
                    regulation_text=regulation_text[:400],
                )
            )

        clauses_gap_section = "\n\n".join(clauses_parts)
        doc_title = rows[0].doc_title if rows else doc_id

        user_prompt = _DOC_REMEDIATION_USER_TEMPLATES[lk].format(
            clause_count=len(rows_needing_remediation),
            doc_id=doc_id,
            doc_title=doc_title,
            clauses_gap_section=clauses_gap_section,
        )

        messages = [
            {"role": "system", "content": _DOC_REMEDIATION_SYSTEM_PROMPTS[lk]},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = _budget_exceeded_msg
            phase_result.completed_at = time.time()
            return phase_result

        # SSE: emit before LLM call
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_4_start",
                "phase": "remediation",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows_needing_remediation],
                "clause_count": len(rows_needing_remediation),
                "prompt_preview": user_prompt[:500],
            },
        )

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

        # Detect LLM error responses
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or response.get("all_failed")
        ):
            error_detail = response_text[:200] if response_text else _llm_empty_msg
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"{_llm_call_failed}: {error_detail}"
            phase_result.completed_at = time.time()
            _emit_pipeline_event(
                run_id,
                {
                    "type": "phase_4_error",
                    "phase": "remediation",
                    "doc_id": doc_id,
                    "error": f"{_llm_call_failed}: {error_detail}",
                },
            )
            return phase_result

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse per-clause remediation results
        clause_remediation = _parse_doc_remediation_response(
            response_text, rows_needing_remediation
        )

        # Distribute remediation results back to individual rows
        total_suggestions = 0
        for row in rows_needing_remediation:
            remediation = clause_remediation.get(row.clause_id, {})
            if remediation:
                row.remediation_suggestion = remediation.get("summary", "")
                row.remediation_regulation_cite = remediation.get(
                    "regulation_citation", ""
                )
                total_suggestions += len(remediation.get("suggestions", []))

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "doc_id": doc_id,
            "clause_count": len(rows_needing_remediation),
            "skipped_count": len(rows) - len(rows_needing_remediation),
            "total_suggestions": total_suggestions,
        }
        phase_result.llm_usage = usage
        phase_result.llm_model = response.get("model", model)

        # SSE: emit after LLM call
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_4_result",
                "phase": "remediation",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows_needing_remediation],
                "llm_response": response_text[:2000],
                "total_suggestions": total_suggestions,
                "usage": usage,
            },
        )

        # Interaction log: persist full LLM call for deep report export
        if run_id:
            try:
                from src.database.interaction_log import get_interaction_log
                get_interaction_log(run_id).log_interaction(
                    phase="remediation",
                    phase_label="Phase 4 - Remediation Suggestions",
                    doc_id=doc_id,
                    doc_title=doc_title,
                    system_prompt=_DOC_REMEDIATION_SYSTEM_PROMPTS[lk],
                    user_prompt=user_prompt,
                    llm_response=response_text,
                    model=response.get("model", model) if response else model,
                    usage=usage,
                    duration_seconds=round(time.time() - phase_result.started_at, 2),
                    extra={"clause_ids": [r.clause_id for r in rows_needing_remediation]},
                )
            except Exception:
                pass

        # SSE: conversation-style event
        _r_details = []
        for row in rows_needing_remediation:
            rem = clause_remediation.get(row.clause_id, {})
            _r_details.append(
                {
                    "clause_id": row.clause_id,
                    "suggestion": rem.get("summary", "")[:300],
                    "regulation": rem.get("regulation_citation", ""),
                }
            )
        _skipped = len(rows) - len(rows_needing_remediation)

        if lk == "en":
            _question_summary = (
                f"For document \"{doc_title}\" ({doc_id}), please provide specific "
                f"improvement recommendations and regulatory citations for the "
                f"{len(rows_needing_remediation)} non-fully-compliant clauses."
                + (f" ({_skipped} fully-compliant clauses skipped.)" if _skipped else "")
            )
            _answer_summary = (
                f"Generated {total_suggestions} improvement recommendations covering "
                f"{len(rows_needing_remediation)} clauses."
            )
        elif lk == "ja":
            _question_summary = (
                f"文書「{doc_title}」({doc_id}) 内の{len(rows_needing_remediation)}個の"
                "完全適合ではない条項について、具体的な改善提案と規制引用を提供してください。"
                + (f"（{_skipped}個の完全適合条項はスキップ）" if _skipped else "")
            )
            _answer_summary = (
                f"{len(rows_needing_remediation)}個の条項を対象に、"
                f"{total_suggestions}件の改善提案を生成しました。"
            )
        else:
            _question_summary = (
                f"針對文件「{doc_title}」({doc_id}) 中 {len(rows_needing_remediation)} 個"
                f"未完全符合的條款，請提供具體的改善建議與法規引用。"
                + (f"（{_skipped} 個已完全符合的條款已跳過）" if _skipped else "")
            )
            _answer_summary = (
                f"已產生 {total_suggestions} 條改善建議，涵蓋 {len(rows_needing_remediation)} 個條款。"
            )

        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_4_conversation",
                "doc_id": doc_id,
                "clause_ids": [r.clause_id for r in rows_needing_remediation],
                "question_summary": _question_summary,
                "answer_summary": _answer_summary,
                "details": {"clauses": _r_details},
            },
        )

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_4_error",
                "phase": "remediation",
                "doc_id": doc_id,
                "error": str(e)[:500],
            },
        )

    phase_result.completed_at = time.time()
    return phase_result
