"""
AI-QMS — Phase 5: Independent Verification (Cross-Examination)
===============================================================

LLM call #4 — Two LLM roles: Analyzer and Verifier.

Cross-examination (交叉詰問):
  1. Analyzer presents its evidence assessment
  2. Verifier challenges the assessment with counter-questions
     (including multi-regulation delta/exceeds items if countries selected)
  3. Analyzer responds to challenges
  4. Max 3 rounds. All rounds recorded in backend + Phoenix.
  5. If still disagreeing after 3 rounds → flagged_for_ra = True
  6. All exchanges emitted via SSE for real-time HTML viewing.

Questions come from compliance_rules.py audit questions.
Multi-regulation questions come from generate_cross_exam_questions().
The Verifier role uses the regulation text as ground truth.
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
    "run_verification_row",
    "run_verification_document",
    "run_qa_audit_document",
    "MAX_VERIFICATION_ROUNDS",
    "emit_verification_event",
]

MAX_VERIFICATION_ROUNDS = 3


# ============================================================
# Language helper (bilingual prompt routing)
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


def emit_verification_event(run_id: str, event: dict) -> None:
    """Emit a cross-examination event to SSE listeners.

    This is the bridge between verifier.py and report_api.py SSE streaming.
    Events are forwarded to the HTML real-time viewer.
    """
    try:
        from src.analysis.report_api import emit_cross_exam_event

        emit_cross_exam_event(run_id, event)
    except ImportError:
        pass  # SSE not available (e.g., running tests without FastAPI)


# ============================================================
# Analyzer role — defends the evidence assessment
# ============================================================

_ANALYZER_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統「分析者」角色，具備 ISO 13485:2016 稽核實務經驗。你在差距分析中已對品質文件進行系統性評估。

你的任務：
1. 根據實際找到的客觀證據（Objective Evidence），說明為何你認為當前的合規判定是正確的。
2. 區分「文件提及某要求」與「文件具體說明如何執行該要求」的差異——稽核只接受後者。
3. 當驗證者質疑時，你必須用具體的原文引用（非推測）來回應。
4. 如果驗證者的質疑揭露了實質的法規落差，你必須誠實承認判定可能需要修正。
5. 回答使用指定的 JSON 格式。
6. 【內容完整性】每個欄位的內容必須詳盡完整，切勿截斷：「position」欄位詳細論述最多 2000 字；「response」欄位針對每項質疑逐條回應，每條最多 1000 字；全部輸出每條上限 10000 字（中文）或 10000 words（英文），確保分析內容完整不被截斷。""",
    "en": """You are the "Analyzer" role in a Quality Management System, with practical ISO 13485:2016 audit experience. You have systematically assessed quality documents in gap analysis.

Your tasks:
1. Based on actual Objective Evidence found, explain why the current compliance verdict is correct.
2. Distinguish between "document mentions a requirement" vs. "document specifically describes how to execute the requirement" — auditors only accept the latter.
3. When the Verifier challenges you, respond with specific verbatim quotations (not speculation).
4. If the Verifier's challenge reveals a substantive regulatory gap, honestly acknowledge the assessment may need revision.
5. Respond in the specified JSON format.
6. [Content Completeness] Each field must be detailed and complete without truncation: "position" field up to 2000 words; "response" field responds to each challenge individually, up to 1000 words each; each item output limit 10000 words.""",
    "ja": """あなたは品質マネジメントシステムの「分析者」役割で、ISO 13485:2016の監査実務経験を持ちます。ギャップ分析において品質文書を系統的に評価しました。

あなたのタスク：
1. 実際に見つかった客観的証拠（Objective Evidence）に基づき、現在のコンプライアンス判定が正しい理由を説明する。
2. 「文書が要件に言及している」と「文書が要件の実行方法を具体的に説明している」の違いを区別する——監査員は後者のみを受け入れる。
3. 検証者が異議を唱えた場合、具体的な逐語引用（推測ではなく）で応答する。
4. 検証者の異議が実質的な規制上のギャップを明らかにした場合、判定の修正が必要な可能性を正直に認める。
5. 指定されたJSON形式で回答する。
6. 【コンテンツの完全性】各フィールドは切り捨てなしで詳細かつ完全であること：「position」フィールドは最大2000語；「response」フィールドは各異議に個別に応答し、各最大1000語；各項目出力上限10000語。""",
}
_ANALYZER_SYSTEM_PROMPT = _ANALYZER_SYSTEM_PROMPTS["zh"]

_ANALYZER_INITIAL_TEMPLATES: dict[str, str] = {
    "zh": """## 你的評估摘要

**法規條款**: {clause_id} — {clause_title}
**稽核問題**: {audit_question}
**當前判定**: {current_verdict}
**差距類型**: {gap_severity}

### 證據項目
{evidence_summary}

請以 JSON 格式說明你的評估立場（「position」字段詳細論述，上限 2000 字，確保內容完整）：

```json
{{
  "position": "支持當前判定的完整論述，需詳細闡明每一項證據如何對應法規要求，不得截斷，上限 2000 字",
  "key_evidence": ["關鍵證據引用1（含文件段落或頁碼）", "關鍵證據引用2"],
  "confidence": 0.0-1.0,
  "acknowledged_weaknesses": ["已知的弱點（如有），需說明具體落差所在"]
}}
```""",
    "en": """## Your Assessment Summary

**Regulatory Clause**: {clause_id} — {clause_title}
**Audit Question**: {audit_question}
**Current Verdict**: {current_verdict}
**Gap Type**: {gap_severity}

### Evidence Items
{evidence_summary}

Please state your assessment position in JSON format ("position" field detailed argument, up to 2000 words):

```json
{{
  "position": "Complete argument supporting the current verdict, detailing how each piece of evidence corresponds to regulatory requirements. Do not truncate, up to 2000 words.",
  "key_evidence": ["Key evidence citation 1 (including document section or page number)", "Key evidence citation 2"],
  "confidence": 0.0-1.0,
  "acknowledged_weaknesses": ["Known weaknesses (if any), describing specific compliance gaps"]
}}
```""",
    "ja": """## あなたの評価サマリー

**規制条項**: {clause_id} — {clause_title}
**監査質問**: {audit_question}
**現在の判定**: {current_verdict}
**ギャップタイプ**: {gap_severity}

### 証拠項目
{evidence_summary}

JSON形式で評価立場を述べてください（「position」フィールドは詳細な論述、最大2000語）：

```json
{{
  "position": "現在の判定を支持する完全な論述。各証拠が規制要件にどのように対応するかを詳述すること。切り捨てないこと、最大2000語。",
  "key_evidence": ["重要証拠引用1（文書セクションまたはページ番号を含む）", "重要証拠引用2"],
  "confidence": 0.0-1.0,
  "acknowledged_weaknesses": ["既知の弱点（あれば）、具体的なコンプライアンスギャップを説明"]
}}
```""",
}
_ANALYZER_INITIAL_TEMPLATE = _ANALYZER_INITIAL_TEMPLATES["zh"]

_ANALYZER_RESPONSE_TEMPLATES: dict[str, str] = {
    "zh": """## 驗證者的質疑

{verifier_challenge}

請針對以上質疑進行回應，使用 JSON 格式（「response」字段逐條回應每項質疑，每條上限 1000 字）：

```json
{{
  "response": "針對每項質疑的完整回應，需逐條引用法規原文及文件實際內容，不得截斷，上限 3000 字",
  "additional_evidence": ["補充證據（含具體文件引用或段落）"],
  "concession": "承認質疑有理的部分（如有），需具體說明哪個子要求確實未被涵蓋",
  "revised_confidence": 0.0-1.0
}}
```""",
    "en": """## Verifier's Challenge

{verifier_challenge}

Please respond to the above challenges in JSON format ("response" field responds to each challenge individually, up to 1000 words each):

```json
{{
  "response": "Complete response to each challenge, citing regulatory text and actual document content for each point. Do not truncate, up to 3000 words.",
  "additional_evidence": ["Supplementary evidence (including specific document citations)"],
  "concession": "Acknowledged valid points from the challenge (if any), specifically identifying which sub-requirements are genuinely not covered",
  "revised_confidence": 0.0-1.0
}}
```""",
    "ja": """## 検証者の異議

{verifier_challenge}

JSON形式で上記の異議に応答してください（「response」フィールドは各異議に個別に応答、各最大1000語）：

```json
{{
  "response": "各異議への完全な応答、各ポイントについて規制テキストと実際の文書内容を引用する。切り捨てないこと、最大3000語。",
  "additional_evidence": ["補足証拠（具体的な文書引用を含む）"],
  "concession": "異議の有効な点の承認（あれば）、どのサブ要件が実際にカバーされていないかを具体的に特定する",
  "revised_confidence": 0.0-1.0
}}
```""",
}
_ANALYZER_RESPONSE_TEMPLATE = _ANALYZER_RESPONSE_TEMPLATES["zh"]


# ============================================================
# Verifier role — challenges the assessment
# ============================================================

_VERIFIER_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統「驗證者」角色，具備 MDSAP（醫療器材單一稽核程序）多國稽核主導員資格。你的任務是從 ISO 13485:2016 法規合規的角度，嚴格質疑分析者的評估。

你的職責：
1. 檢查分析者是否遺漏了 ISO 13485:2016 條款的重要子要求（sub-requirements）。
2. 質疑「語言符合性」vs「法規正確性」——文件使用相似術語不等於實質涵蓋法規要求。
3. 指出「提到要求」vs「具體描述如何執行、由誰執行、多久一次」的關鍵差異。
4. 從 ISO 14971 風險管理角度思考：此合規落差在最壞情況下會帶來什麼不良後果？
5. 如果有多國法規要求（delta items），特別檢查分析者是否充分考量各國獨有要求。
6. 如果分析者的評估確實以客觀證據支撐且覆蓋所有子要求，你應當同意——不要為質疑而質疑。
7. 回答使用指定的 JSON 格式。
8. 【內容完整性】每條質疑（challenges[].point）最多 2000 字，包含：具體法規引用、應有的客觀證據描述、以及 ISO 14971 最壞情況風險說明；overall_assessment 最多 1000 字；每條輸出上限 10000 字（中文）或 10000 words（英文），確保分析完整不截斷。""",
    "en": """You are the "Verifier" role in a Quality Management System, holding MDSAP (Medical Device Single Audit Program) multi-country lead auditor qualifications. Your task is to rigorously challenge the Analyzer's assessment from an ISO 13485:2016 regulatory compliance perspective.

Your responsibilities:
1. Check whether the Analyzer missed important sub-requirements of ISO 13485:2016 clauses.
2. Challenge "linguistic compliance" vs. "regulatory correctness" — the document using similar terminology does not mean it substantively covers regulatory requirements.
3. Point out the critical difference between "mentioning a requirement" vs. "specifically describing how to execute it, by whom, how often".
4. Think from ISO 14971 risk management perspective: what is the worst-case outcome of this compliance gap?
5. If there are multi-country regulatory requirements (delta items), specifically check whether the Analyzer adequately considered each country's unique requirements.
6. If the Analyzer's assessment is genuinely supported by objective evidence covering all sub-requirements, you should agree — do not challenge for the sake of challenging.
7. Respond in the specified JSON format.
8. [Content Completeness] Each challenge (challenges[].point) up to 2000 words, covering: specific regulatory citation, description of required objective evidence, ISO 14971 worst-case risk analysis; overall_assessment up to 1000 words; each item output limit 10000 words.""",
    "ja": """あなたは品質マネジメントシステムの「検証者」役割で、MDSAP（医療機器単一監査プログラム）多国籍主席監査人資格を持ちます。ISO 13485:2016の規制コンプライアンスの観点から分析者の評価を厳格に異議申し立てることが任務です。

責任：
1. 分析者がISO 13485:2016条項の重要なサブ要件を見逃していないか確認する。
2. 「言語的適合性」vs「規制の正確性」に異議を唱える——文書が類似用語を使用していても規制要件を実質的にカバーしていることにはならない。
3. 「要件に言及する」vs「誰が、どのように、どのくらいの頻度で実行するかを具体的に説明する」の重要な違いを指摘する。
4. ISO 14971リスク管理の観点から考える：このコンプライアンスギャップの最悪のシナリオは何か？
5. 多国籍規制要件（デルタ項目）がある場合、各国固有の要件を分析者が十分に考慮したかを確認する。
6. 分析者の評価が客観的証拠によって真に裏付けられ、すべてのサブ要件をカバーしている場合は同意すること——異議のための異議は不要。
7. 指定されたJSON形式で回答する。
8. 【コンテンツの完全性】各異議（challenges[].point）は最大2000語；overall_assessmentは最大1000語；各項目出力上限10000語。""",
}
_VERIFIER_SYSTEM_PROMPT = _VERIFIER_SYSTEM_PROMPTS["zh"]

_VERIFIER_CHALLENGE_TEMPLATES: dict[str, str] = {
    "zh": """## 分析者的評估

{analyzer_position}

## 法規原文參考

{regulation_text}

## 稽核問題

{audit_question}

請以 JSON 格式提出你的驗證意見（每條 challenges[].point 上限 2000 字，overall_assessment 上限 1000 字）：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "challenges": [
    {{
      "point": "詳細質疑要點（上限 2000 字）：需包含（1）分析者的具體遺漏說明，（2）完整法規原文引用，（3）稽核時應佐證的文件或記錄清單，（4）若未改善的最壞情況後果，不得截斷。",
      "regulation_basis": "法規依據（引用 ISO 13485:2016 條款編號及原文，包含所有適用子條款）",
      "expected_evidence": "應有的客觀證據詳述（具體文件名稱、記錄格式、程序步驟、負責人角色及執行頻率）",
      "worst_case_impact": "ISO 14971 視角下的最壞情況風險分析（包含危害情境、發生可能性、嚴重度及潛在的法規不符合後果）"
    }}
  ],
  "overall_assessment": "整體評語（300-1000 字）：需涵蓋本次稽核問題的整體合規狀況評估、重點落差摘要、及後續 RA 建議方向"
}}
```""",
    "en": """## Analyzer's Assessment

{analyzer_position}

## Regulatory Text Reference

{regulation_text}

## Audit Question

{audit_question}

Please state your verification opinion in JSON format (each challenges[].point up to 2000 words, overall_assessment up to 1000 words):

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "challenges": [
    {{
      "point": "Detailed challenge point (up to 2000 words): must include (1) specific omissions by the Analyzer, (2) complete regulatory text citation, (3) list of documents/records that should be evidenced in audit, (4) worst-case consequences if not addressed. Do not truncate.",
      "regulation_basis": "Regulatory basis (cite ISO 13485:2016 clause number and text, including all applicable sub-clauses)",
      "expected_evidence": "Detailed description of required objective evidence (specific document names, record formats, procedure steps, responsible roles, and execution frequency)",
      "worst_case_impact": "Worst-case risk analysis from ISO 14971 perspective (including hazard scenario, probability, severity, and potential regulatory non-conformance consequences)"
    }}
  ],
  "overall_assessment": "Overall assessment (up to 1000 words): covers the overall compliance status for this audit question, key gap summary, and recommended RA action direction"
}}
```""",
    "ja": """## 分析者の評価

{analyzer_position}

## 規制テキスト参照

{regulation_text}

## 監査質問

{audit_question}

JSON形式で検証意見を述べてください（各challenges[].pointは最大2000語、overall_assessmentは最大1000語）：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "challenges": [
    {{
      "point": "詳細な異議ポイント（最大2000語）：（1）分析者の具体的な見落とし、（2）完全な規制テキスト引用、（3）監査で証拠として必要な文書/記録リスト、（4）対処しない場合の最悪のシナリオ。切り捨てないこと。",
      "regulation_basis": "規制根拠（ISO 13485:2016条項番号とテキスト、適用されるすべてのサブ条項を含む）",
      "expected_evidence": "必要な客観的証拠の詳細説明（具体的な文書名、記録形式、手順ステップ、責任者、実行頻度）",
      "worst_case_impact": "ISO 14971の観点からの最悪ケースリスク分析（危害シナリオ、確率、重篤度、潜在的な規制不適合の結果を含む）"
    }}
  ],
  "overall_assessment": "全体評価（最大1000語）：この監査質問の全体的なコンプライアンス状況、主要ギャップのサマリー、推奨RAアクション方向"
}}
```""",
}
_VERIFIER_CHALLENGE_TEMPLATE = _VERIFIER_CHALLENGE_TEMPLATES["zh"]

_VERIFIER_FOLLOWUP_TEMPLATES: dict[str, str] = {
    "zh": """## 分析者的回應

{analyzer_response}

## 前一輪你的質疑

{previous_challenge}

請根據分析者的回應更新你的評估，使用 JSON 格式（每項 remaining_concerns 上限 500 字，overall_assessment 上限 1000 字）：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "remaining_concerns": ["仍未解決的疑慮（每條上限 500 字，需詳述：（1）分析者回應的不足之處，（2）法規原文中仍未被涵蓋的子要求，（3）建議後續應補充的客觀證據）"],
  "resolved_concerns": ["已被合理回應的疑慮（說明分析者如何以客觀證據消弭疑慮）"],
  "overall_assessment": "更新後的整體評語（300-1000 字）：評估本輪交流後整體合規信心的變化、仍存在的重大落差及建議行動"
}}
```""",
    "en": """## Analyzer's Response

{analyzer_response}

## Your Previous Round Challenge

{previous_challenge}

Please update your assessment based on the Analyzer's response in JSON format (each remaining_concerns up to 500 words, overall_assessment up to 1000 words):

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "remaining_concerns": ["Unresolved concerns (each up to 500 words, detailing: (1) inadequacy in Analyzer's response, (2) sub-requirements in regulatory text still not covered, (3) recommended objective evidence to supplement)"],
  "resolved_concerns": ["Concerns adequately addressed (explaining how Analyzer resolved them with objective evidence)"],
  "overall_assessment": "Updated overall assessment (up to 1000 words): evaluate changes in overall compliance confidence after this exchange, remaining major gaps and recommended actions"
}}
```""",
    "ja": """## 分析者の応答

{analyzer_response}

## 前ラウンドのあなたの異議

{previous_challenge}

分析者の応答に基づいてJSON形式で評価を更新してください（各remaining_concernsは最大500語、overall_assessmentは最大1000語）：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "remaining_concerns": ["未解決の懸念（各最大500語、詳述：（1）分析者の応答の不十分な点、（2）規制テキストでまだカバーされていないサブ要件、（3）補足すべき客観的証拠の推奨）"],
  "resolved_concerns": ["適切に対処された懸念（分析者がどのように客観的証拠で解決したかを説明）"],
  "overall_assessment": "更新された全体評価（最大1000語）：この交換後の全体的なコンプライアンス信頼度の変化、残存する主要ギャップと推奨アクション"
}}
```""",
}
_VERIFIER_FOLLOWUP_TEMPLATE = _VERIFIER_FOLLOWUP_TEMPLATES["zh"]


# ============================================================
# Multi-regulation context headers & evidence summary labels
# ============================================================

_MULTI_REG_HEADERS: dict[str, str] = {
    "zh": "## 多國法規特殊要求（需額外驗證）\n",
    "en": "## Multi-Country Regulatory Requirements (Require Additional Verification)\n",
    "ja": "## 多国籍規制要件（追加検証が必要）\n",
}

_EVIDENCE_STATUS_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "found": "✅ 找到",
        "not_found": "❌ 未找到",
        "inadequate": "⚠️ 不充分",
        "outdated": "📅 版本過期",
        "empty": "（無證據項目）",
        "quote": "引用",
        "reason": "原因",
    },
    "en": {
        "found": "✅ Found",
        "not_found": "❌ Not found",
        "inadequate": "⚠️ Inadequate",
        "outdated": "📅 Outdated",
        "empty": "(No evidence items)",
        "quote": "Quote",
        "reason": "Reason",
    },
    "ja": {
        "found": "✅ 見つかった",
        "not_found": "❌ 見つからず",
        "inadequate": "⚠️ 不十分",
        "outdated": "📅 バージョン古い",
        "empty": "（証拠項目なし）",
        "quote": "引用",
        "reason": "理由",
    },
}

_NOT_ASSESSED: dict[str, str] = {
    "zh": "未評估",
    "en": "Not assessed",
    "ja": "未評価",
}

_NOT_VERDICTED: dict[str, str] = {
    "zh": "未判定",
    "en": "Not determined",
    "ja": "未判定",
}

_BUDGET_EXCEEDED_MSG: dict[str, str] = {
    "zh": "LLM token 預算已用盡",
    "en": "LLM token budget exhausted",
    "ja": "LLMトークン予算を使い果たしました",
}

_HUMAN_INJECTION_HEADER: dict[str, str] = {
    "zh": (
        "\n\n## Human RA Intervention\n"
    ),
    "en": (
        "\n\n## Human RA Intervention\n"
    ),
    "ja": (
        "\n\n## Human RA Intervention\n"
    ),
}

_HUMAN_INJECTION_NOTE: dict[str, str] = {
    "zh": "\n\n請在你的分析中考慮以上人工介入的意見。\n",
    "en": "\n\nPlease take the above human intervention comments into account in your analysis.\n",
    "ja": "\n\n上記の人間による介入コメントを分析に考慮してください。\n",
}


# ============================================================
# Helper functions
# ============================================================


def _build_evidence_summary(
    evidence_items: list[EvidenceItem],
    lang: str = "zh-TW",
) -> str:
    """Build a summary of evidence for the analyzer."""
    lk = _lang_key(lang)
    labels = _EVIDENCE_STATUS_LABELS[lk]
    parts = []
    for i, item in enumerate(evidence_items, 1):
        status = labels["found"] if item.found else labels["not_found"]
        if item.is_inadequate:
            status = labels["inadequate"]
        if item.is_outdated:
            status = labels["outdated"]

        line = f"{i}. [{status}] {item.evidence_name}"
        if item.source_quote:
            quote = item.source_quote[:100] + (
                "..." if len(item.source_quote) > 100 else ""
            )
            line += f"\n   {labels['quote']}: 「{quote}」"
        if item.llm_reasoning:
            line += f"\n   {labels['reason']}: {item.llm_reasoning}"
        parts.append(line)

    return "\n".join(parts) if parts else labels["empty"]


def _get_regulation_text(clause_id: str, standard: str) -> str:
    from src.analysis import get_regulation_text

    return get_regulation_text(clause_id, standard, context_chars=800)


def _parse_json_response(response_text: str) -> dict:
    """Parse LLM JSON response with code block handling."""
    json_str = response_text.strip()

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
        return json.loads(json_str)
    except (json.JSONDecodeError, KeyError):
        return {}


def _call_llm(
    llm_completion_fn: callable,
    system_prompt: str,
    user_prompt: str,
    state: PipelineState,
    model: str,
    temperature: float,
    max_tokens: int,
) -> tuple[dict, dict]:
    """Call LLM and return (parsed_response, usage). Checks budget first.

    Returns:
        (parsed_json, usage_dict)
    Raises:
        RuntimeError if budget exceeded.
    """
    budget = state.get_budget()
    if budget.exceeded:
        raise RuntimeError("LLM token 預算已用盡")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = llm_completion_fn(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )

    response_text = response.get("content", "")
    usage = response.get("usage", {})

    budget.record_usage(usage)
    state.update_budget(budget)

    parsed = _parse_json_response(response_text)
    return parsed, usage


# ============================================================
# Phase execution
# ============================================================


def run_verification_row(
    row_state: RowState,
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.2,
    verifier_temperature: float = 0.0,
    max_tokens: int = 16384,
    selected_regulations: list[str] | None = None,
    run_id: str = "",
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 5 cross-examination for a single row.

    Process:
        Round 1: Analyzer states position → Verifier challenges
        Round 2: Analyzer responds → Verifier re-evaluates
        Round 3: (if needed) Analyzer final → Verifier final
        If still disagreeing after 3 rounds → flagged_for_ra
        All rounds emitted via SSE for real-time HTML viewing.

    Args:
        row_state: Row with Phase 1-4 results
        state: Pipeline state
        llm_completion_fn: LLM completion function
        model: Model name
        temperature: Analyzer LLM temperature (default 0.2 for creative reasoning)
        verifier_temperature: Verifier LLM temperature (default 0.0 for deterministic challenges)
        max_tokens: Max response tokens
        selected_regulations: Country regulation IDs (e.g., ['QMSR', 'EU_MDR', 'TFDA'])
        run_id: Pipeline run ID for SSE event emission

    Returns:
        PhaseResult with verification rounds and agreement status
    """
    lk = _lang_key(lang)
    phase_result = PhaseResult(
        phase=Phase.VERIFICATION.value,
        started_at=time.time(),
    )

    try:
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        if not evidence_items:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No evidence items to verify"}
            phase_result.completed_at = time.time()
            return phase_result

        evidence_summary = _build_evidence_summary(evidence_items, lang=lang)
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

        # Language-aware title/question keys for multi-reg questions
        title_key = (
            "title_en" if lk == "en" else "title_ja" if lk == "ja" else "title_zh"
        )
        question_key = (
            "question_en"
            if lk == "en"
            else "question_ja"
            if lk == "ja"
            else "question_zh"
        )

        # ── Multi-regulation context (delta / exceeds items) ──
        multi_reg_context = ""
        if selected_regulations:
            try:
                from src.analysis.compliance_rules import generate_cross_exam_questions

                reg_questions = generate_cross_exam_questions(
                    doc_id=row_state.doc_id or "",
                    doc_title=row_state.doc_title or "",
                    baseline_clause=row_state.clause_id,
                    selected_regulations=selected_regulations,
                )
                delta_items = [
                    q for q in reg_questions if q["question_type"] == "delta"
                ]
                exceeds_items = [
                    q for q in reg_questions if q["question_type"] == "exceeds"
                ]
                if delta_items or exceeds_items:
                    parts = [_MULTI_REG_HEADERS[lk]]
                    for q in delta_items:
                        title = q.get(title_key) or q.get("title_zh", "")
                        question = q.get(question_key) or q.get("question_zh", "")
                        parts.append(f"⚠️ [{q['country']}] {title}: {question}")
                    for q in exceeds_items:
                        title = q.get(title_key) or q.get("title_zh", "")
                        question = q.get(question_key) or q.get("question_zh", "")
                        parts.append(f"📋 [{q['country']}] {title}: {question}")
                    multi_reg_context = "\n".join(parts)
            except Exception:
                pass  # Non-critical — proceed without multi-reg context

        # Import verdict display
        from src.analysis.risk_matrix import VERDICT_DISPLAY

        verdict_info = VERDICT_DISPLAY.get(row_state.verdict or "", {})
        label_key = "label_en" if lk == "en" else "label_ja" if lk == "ja" else "label_zh"
        verdict_label = verdict_info.get(
            label_key, verdict_info.get("label_zh", row_state.verdict or _NOT_VERDICTED[lk])
        )

        rounds: list[dict] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        agreed = False

        # Emit SSE: verification start
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "verification_start",
                    "clause_id": row_state.clause_id,
                    "clause_title": row_state.clause_title,
                    "doc_id": row_state.doc_id or "",
                    "selected_regulations": selected_regulations or [],
                    "has_multi_reg_context": bool(multi_reg_context),
                },
            )

        # ---- Round 1: Analyzer initial position ----

        # Drain any pending human-injected messages (lazy import to avoid circular)
        human_injection_block = ""
        if run_id:
            from src.analysis.report_api import get_injected_messages

            injected = get_injected_messages(run_id)
            if injected:
                human_injection_block = (
                    _HUMAN_INJECTION_HEADER[lk]
                    + "\n".join(f"- {msg}" for msg in injected)
                    + _HUMAN_INJECTION_NOTE[lk]
                )
                emit_verification_event(
                    run_id,
                    {
                        "type": "human_injection_applied",
                        "run_id": run_id,
                        "clause_id": row_state.clause_id,
                        "messages": injected,
                    },
                )

        analyzer_prompt = _ANALYZER_INITIAL_TEMPLATES[lk].format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            current_verdict=verdict_label,
            gap_severity=row_state.gap_severity or _NOT_ASSESSED[lk],
            evidence_summary=evidence_summary,
        )
        if human_injection_block:
            analyzer_prompt += human_injection_block

        # Emit SSE: round start
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "round_start",
                    "round": 1,
                    "clause_id": row_state.clause_id,
                },
            )

        analyzer_response, usage = _call_llm(
            llm_completion_fn,
            _ANALYZER_SYSTEM_PROMPTS[lk],
            analyzer_prompt,
            state,
            model,
            temperature,
            max_tokens,
        )
        _merge_usage(total_usage, usage)

        # Emit SSE: analyzer response
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "analyzer",
                    "round": 1,
                    "clause_id": row_state.clause_id,
                    "content": json.dumps(analyzer_response, ensure_ascii=False),
                },
            )

        # Verifier challenges — append multi-regulation context if available
        verifier_prompt = _VERIFIER_CHALLENGE_TEMPLATES[lk].format(
            analyzer_position=json.dumps(
                analyzer_response, ensure_ascii=False, indent=2
            ),
            regulation_text=regulation_text,
            audit_question=row_state.audit_question,
        )
        if multi_reg_context:
            verifier_prompt += f"\n\n{multi_reg_context}"
        if human_injection_block:
            verifier_prompt += human_injection_block

        verifier_response, usage = _call_llm(
            llm_completion_fn,
            _VERIFIER_SYSTEM_PROMPTS[lk],
            verifier_prompt,
            state,
            model,
            verifier_temperature,
            max_tokens,
        )
        _merge_usage(total_usage, usage)

        # Emit SSE: verifier response
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "verifier",
                    "round": 1,
                    "clause_id": row_state.clause_id,
                    "content": json.dumps(verifier_response, ensure_ascii=False),
                },
            )

        rounds.append(
            {
                "round": 1,
                "analyzer": analyzer_response,
                "verifier": verifier_response,
            }
        )

        agreement = verifier_response.get("agreement_level", "")
        if agreement == "agree":
            agreed = True

        # Emit SSE: round end
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "round_end",
                    "round": 1,
                    "clause_id": row_state.clause_id,
                    "agreement_level": agreement,
                    "agreed": agreed,
                },
            )

        # ---- Rounds 2-3: Follow-up if not agreed ----
        for round_num in range(2, MAX_VERIFICATION_ROUNDS + 1):
            if agreed:
                break

            # Emit SSE: round start
            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "round_start",
                        "round": round_num,
                        "clause_id": row_state.clause_id,
                    },
                )

            # Drain any pending human-injected messages for this round
            round_injection_block = ""
            if run_id:
                from src.analysis.report_api import get_injected_messages

                injected = get_injected_messages(run_id)
                if injected:
                    round_injection_block = (
                        _HUMAN_INJECTION_HEADER[lk]
                        + "\n".join(f"- {msg}" for msg in injected)
                        + _HUMAN_INJECTION_NOTE[lk]
                    )
                    emit_verification_event(
                        run_id,
                        {
                            "type": "human_injection_applied",
                            "run_id": run_id,
                            "clause_id": row_state.clause_id,
                            "messages": injected,
                        },
                    )

            # Analyzer responds to verifier's challenge
            analyzer_followup = _ANALYZER_RESPONSE_TEMPLATES[lk].format(
                verifier_challenge=json.dumps(
                    verifier_response, ensure_ascii=False, indent=2
                ),
            )
            if round_injection_block:
                analyzer_followup += round_injection_block

            analyzer_response, usage = _call_llm(
                llm_completion_fn,
                _ANALYZER_SYSTEM_PROMPTS[lk],
                analyzer_followup,
                state,
                model,
                temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            # Emit SSE: analyzer response
            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "analyzer",
                        "round": round_num,
                        "clause_id": row_state.clause_id,
                        "content": json.dumps(analyzer_response, ensure_ascii=False),
                    },
                )

            # Verifier re-evaluates
            verifier_followup = _VERIFIER_FOLLOWUP_TEMPLATES[lk].format(
                analyzer_response=json.dumps(
                    analyzer_response, ensure_ascii=False, indent=2
                ),
                previous_challenge=json.dumps(
                    verifier_response, ensure_ascii=False, indent=2
                ),
            )
            if round_injection_block:
                verifier_followup += round_injection_block

            verifier_response, usage = _call_llm(
                llm_completion_fn,
                _VERIFIER_SYSTEM_PROMPTS[lk],
                verifier_followup,
                state,
                model,
                verifier_temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            # Emit SSE: verifier response
            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "verifier",
                        "round": round_num,
                        "clause_id": row_state.clause_id,
                        "content": json.dumps(verifier_response, ensure_ascii=False),
                    },
                )

            rounds.append(
                {
                    "round": round_num,
                    "analyzer": analyzer_response,
                    "verifier": verifier_response,
                }
            )

            agreement = verifier_response.get("agreement_level", "")
            if agreement == "agree":
                agreed = True

            # Emit SSE: round end
            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "round_end",
                        "round": round_num,
                        "clause_id": row_state.clause_id,
                        "agreement_level": agreement,
                        "agreed": agreed,
                    },
                )
        # ---- Store results ----
        row_state.verification_rounds = rounds
        row_state.verification_agreed = agreed
        row_state.flagged_for_ra = not agreed

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "total_rounds": len(rounds),
            "agreed": agreed,
            "flagged_for_ra": not agreed,
            "final_agreement_level": agreement,
            "rounds": rounds,
            "multi_regulation": bool(multi_reg_context),
            "selected_regulations": selected_regulations or [],
        }
        phase_result.llm_usage = total_usage
        phase_result.llm_model = model

        # Emit SSE: verification complete
        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "verification_complete",
                    "clause_id": row_state.clause_id,
                    "total_rounds": len(rounds),
                    "agreed": agreed,
                    "flagged_for_ra": not agreed,
                    "final_agreement_level": agreement,
                },
            )

    except RuntimeError as e:
        # Budget exceeded mid-verification
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        # Still save partial rounds
        if rounds:
            row_state.verification_rounds = rounds
            phase_result.output = {
                "total_rounds": len(rounds),
                "partial": True,
                "rounds": rounds,
            }

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    return phase_result


def _merge_usage(total: dict, usage: dict) -> None:
    """Accumulate LLM usage across multiple calls."""
    total["prompt_tokens"] += usage.get("prompt_tokens", 0)
    total["completion_tokens"] += usage.get("completion_tokens", 0)
    total["total_tokens"] += usage.get("total_tokens", 0)


# ============================================================
# SSE event emission (pipeline-level, all phases)
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
# Per-document Phase execution (PRIMARY)
# ============================================================


def run_verification_document(
    doc_id: str,
    rows: list[RowState],
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.2,
    verifier_temperature: float = 0.0,
    max_tokens: int = 8192,
    selected_regulations: list[str] | None = None,
    run_id: str = "",
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 5 cross-examination for ALL clauses of one document.

    For each clause, runs the Analyzer/Verifier debate (up to 3 rounds).
    All rounds emitted via SSE for real-time HTML viewing.

    NOTE: Phase 5 is inherently per-clause (debate is clause-specific),
    but we group by document for SSE emission and state management.

    Args:
        doc_id: Document ID
        rows: All RowState objects for this document
        state: Pipeline state
        llm_completion_fn: LLM completion function (returns dict)
        model: LLM model name
        temperature: Analyzer LLM temperature (default 0.2)
        verifier_temperature: Verifier LLM temperature (default 0.0)
        max_tokens: Max tokens per LLM call
        selected_regulations: Country regulation IDs
        run_id: Pipeline run ID for SSE emission

    Returns:
        PhaseResult with aggregated verification results
    """
    lk = _lang_key(lang)
    label_key = "label_en" if lk == "en" else "label_ja" if lk == "ja" else "label_zh"
    title_key = "title_en" if lk == "en" else "title_ja" if lk == "ja" else "title_zh"
    question_key = (
        "question_en" if lk == "en" else "question_ja" if lk == "ja" else "question_zh"
    )

    phase_result = PhaseResult(
        phase=Phase.VERIFICATION.value,
        started_at=time.time(),
    )

    try:
        # Skip rows with no evidence or already fully compliant (no gaps to cross-examine)
        rows_with_evidence = [
            r for r in rows
            if r.evidence_items and r.verdict not in ("full_compliance", "not_applicable")
        ]

        if not rows_with_evidence:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No gaps to verify (all compliant or no evidence)"}
            phase_result.completed_at = time.time()
            return phase_result

        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        total_agreed = 0
        total_flagged = 0
        doc_title = rows[0].doc_title if rows else doc_id

        # SSE: document-level start
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_5_start",
                "phase": "verification",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows_with_evidence],
                "clause_count": len(rows_with_evidence),
                "selected_regulations": selected_regulations or [],
            },
        )

        # Process each clause's debate (per-clause within document)
        for row in rows_with_evidence:
            # Check budget before each clause
            budget = state.get_budget()
            if budget.exceeded:
                row.verification_rounds = []
                row.verification_agreed = False
                row.flagged_for_ra = True
                total_flagged += 1
                continue

            evidence_items = [EvidenceItem.from_dict(e) for e in row.evidence_items]
            evidence_summary = _build_evidence_summary(evidence_items, lang=lang)
            regulation_text = _get_regulation_text(row.clause_id, row.standard)

            # Multi-regulation context
            multi_reg_context = ""
            if selected_regulations:
                try:
                    from src.analysis.compliance_rules import (
                        generate_cross_exam_questions,
                    )

                    reg_questions = generate_cross_exam_questions(
                        doc_id=row.doc_id or "",
                        doc_title=row.doc_title or "",
                        baseline_clause=row.clause_id,
                        selected_regulations=selected_regulations,
                    )
                    delta_items = [
                        q for q in reg_questions if q["question_type"] == "delta"
                    ]
                    exceeds_items = [
                        q for q in reg_questions if q["question_type"] == "exceeds"
                    ]
                    if delta_items or exceeds_items:
                        parts = [_MULTI_REG_HEADERS[lk]]
                        for q in delta_items:
                            title = q.get(title_key) or q.get("title_zh", "")
                            question = q.get(question_key) or q.get("question_zh", "")
                            parts.append(f"⚠️ [{q['country']}] {title}: {question}")
                        for q in exceeds_items:
                            title = q.get(title_key) or q.get("title_zh", "")
                            question = q.get(question_key) or q.get("question_zh", "")
                            parts.append(f"📋 [{q['country']}] {title}: {question}")
                        multi_reg_context = "\n".join(parts)
                except Exception:
                    pass

            from src.analysis.risk_matrix import VERDICT_DISPLAY

            verdict_info = VERDICT_DISPLAY.get(row.verdict or "", {})
            verdict_label = verdict_info.get(
                label_key, verdict_info.get("label_zh", row.verdict or _NOT_VERDICTED[lk])
            )

            rounds: list[dict] = []
            agreed = False

            # Emit SSE: verification start for this clause
            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "verification_start",
                        "clause_id": row.clause_id,
                        "clause_title": row.clause_title,
                        "doc_id": doc_id,
                        "selected_regulations": selected_regulations or [],
                        "has_multi_reg_context": bool(multi_reg_context),
                    },
                )

            # Round 1: Analyzer initial position
            analyzer_prompt = _ANALYZER_INITIAL_TEMPLATES[lk].format(
                clause_id=row.clause_id,
                clause_title=row.clause_title,
                audit_question=row.audit_question,
                current_verdict=verdict_label,
                gap_severity=row.gap_severity or _NOT_ASSESSED[lk],
                evidence_summary=evidence_summary,
            )

            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "round_start",
                        "round": 1,
                        "clause_id": row.clause_id,
                    },
                )

            analyzer_response, usage = _call_llm(
                llm_completion_fn,
                _ANALYZER_SYSTEM_PROMPTS[lk],
                analyzer_prompt,
                state,
                model,
                temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "analyzer",
                        "round": 1,
                        "clause_id": row.clause_id,
                        "content": json.dumps(analyzer_response, ensure_ascii=False),
                    },
                )

            # Verifier challenges
            verifier_prompt = _VERIFIER_CHALLENGE_TEMPLATES[lk].format(
                analyzer_position=json.dumps(
                    analyzer_response, ensure_ascii=False, indent=2
                ),
                regulation_text=regulation_text,
                audit_question=row.audit_question,
            )
            if multi_reg_context:
                verifier_prompt += f"\n\n{multi_reg_context}"

            verifier_response, usage = _call_llm(
                llm_completion_fn,
                _VERIFIER_SYSTEM_PROMPTS[lk],
                verifier_prompt,
                state,
                model,
                verifier_temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "verifier",
                        "round": 1,
                        "clause_id": row.clause_id,
                        "content": json.dumps(verifier_response, ensure_ascii=False),
                    },
                )

            rounds.append(
                {
                    "round": 1,
                    "analyzer": analyzer_response,
                    "verifier": verifier_response,
                }
            )

            agreement = verifier_response.get("agreement_level", "")
            if agreement == "agree":
                agreed = True

            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "round_end",
                        "round": 1,
                        "clause_id": row.clause_id,
                        "agreement_level": agreement,
                        "agreed": agreed,
                    },
                )

            # Rounds 2-3
            for round_num in range(2, MAX_VERIFICATION_ROUNDS + 1):
                if agreed:
                    break

                budget = state.get_budget()
                if budget.exceeded:
                    break

                if run_id:
                    emit_verification_event(
                        run_id,
                        {
                            "type": "round_start",
                            "round": round_num,
                            "clause_id": row.clause_id,
                        },
                    )

                analyzer_followup = _ANALYZER_RESPONSE_TEMPLATES[lk].format(
                    verifier_challenge=json.dumps(
                        verifier_response, ensure_ascii=False, indent=2
                    ),
                )

                analyzer_response, usage = _call_llm(
                    llm_completion_fn,
                    _ANALYZER_SYSTEM_PROMPTS[lk],
                    analyzer_followup,
                    state,
                    model,
                    temperature,
                    max_tokens,
                )
                _merge_usage(total_usage, usage)

                if run_id:
                    emit_verification_event(
                        run_id,
                        {
                            "type": "analyzer",
                            "round": round_num,
                            "clause_id": row.clause_id,
                            "content": json.dumps(
                                analyzer_response, ensure_ascii=False
                            ),
                        },
                    )

                verifier_followup = _VERIFIER_FOLLOWUP_TEMPLATES[lk].format(
                    analyzer_response=json.dumps(
                        analyzer_response, ensure_ascii=False, indent=2
                    ),
                    previous_challenge=json.dumps(
                        verifier_response, ensure_ascii=False, indent=2
                    ),
                )

                verifier_response, usage = _call_llm(
                    llm_completion_fn,
                    _VERIFIER_SYSTEM_PROMPTS[lk],
                    verifier_followup,
                    state,
                    model,
                    verifier_temperature,
                    max_tokens,
                )
                _merge_usage(total_usage, usage)

                if run_id:
                    emit_verification_event(
                        run_id,
                        {
                            "type": "verifier",
                            "round": round_num,
                            "clause_id": row.clause_id,
                            "content": json.dumps(
                                verifier_response, ensure_ascii=False
                            ),
                        },
                    )

                rounds.append(
                    {
                        "round": round_num,
                        "analyzer": analyzer_response,
                        "verifier": verifier_response,
                    }
                )

                agreement = verifier_response.get("agreement_level", "")
                if agreement == "agree":
                    agreed = True

                if run_id:
                    emit_verification_event(
                        run_id,
                        {
                            "type": "round_end",
                            "round": round_num,
                            "clause_id": row.clause_id,
                            "agreement_level": agreement,
                            "agreed": agreed,
                        },
                    )

            # Store results for this row
            row.verification_rounds = rounds
            row.verification_agreed = agreed
            row.flagged_for_ra = not agreed

            if agreed:
                total_agreed += 1
            else:
                total_flagged += 1

            if run_id:
                emit_verification_event(
                    run_id,
                    {
                        "type": "verification_complete",
                        "clause_id": row.clause_id,
                        "total_rounds": len(rounds),
                        "agreed": agreed,
                        "flagged_for_ra": not agreed,
                        "final_agreement_level": agreement,
                    },
                )

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "doc_id": doc_id,
            "clause_count": len(rows_with_evidence),
            "total_agreed": total_agreed,
            "total_flagged": total_flagged,
            "selected_regulations": selected_regulations or [],
        }
        phase_result.llm_usage = total_usage
        phase_result.llm_model = model

        # SSE: document-level complete
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_5_result",
                "phase": "verification",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in rows_with_evidence],
                "total_agreed": total_agreed,
                "total_flagged": total_flagged,
                "usage": total_usage,
            },
        )

    except RuntimeError as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_5_error",
                "phase": "verification",
                "doc_id": doc_id,
                "error": str(e)[:500],
            },
        )

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_5_error",
                "phase": "verification",
                "doc_id": doc_id,
                "error": str(e)[:500],
            },
        )

    phase_result.completed_at = time.time()
    return phase_result


# ============================================================
# Phase 5 Step 2: Third-Party QA Audit
# ============================================================

_QA_AUDITOR_SYSTEM_PROMPTS: dict[str, str] = {
    "zh": """你是品質管理系統的「第三方交叉詰問品質稽核員」。你的任務是獨立審查分析者（Analyzer）和驗證者（Verifier）之間的對話紀錄，判斷對話品質。

你不是分析者或驗證者的任何一方 — 你是獨立的第三方稽核員。

你需要檢查每一筆對話紀錄：
1. **問題合理性**: 分析者提出的立場和證據引用是否合理？有無捏造或不存在的證據？
2. **回答正確性**: 驗證者的質疑是否基於正確的法規內容？有無引用錯誤的條文或歪曲法規原意？
3. **邏輯一致性**: 整個辯論過程的邏輯是否連貫？有無自相矛盾？
4. **幻覺偵測**: 分析者或驗證者是否編造了不存在的文件、證據或法規條文？
5. **深度充分性**: 討論是否足夠深入，還是流於表面應付？
6. **最終結論合理性**: 最終的同意/不同意結論是否與辯論內容一致？

**評分標準（overall_score 與每條款 score，必須嚴格依照此表給分）：**

| 分數區間 | 條件說明 |
|---------|---------|
| 90–100 | 無幻覺，證據引用精確，邏輯完全連貫，質疑有深度，結論與辯論一致 |
| 70–89  | 輕微瑕疵（引用略有不精確或論述稍淺），但整體品質良好，無幻覺 |
| 50–69  | 有明顯問題（1–2 項邏輯跳躍或證據薄弱），或有疑似但未確認的幻覺 |
| 30–49  | 嚴重問題（多項矛盾、或確認幻覺、或結論與辯論不符） |
| 0–29   | 完全失效（大量捏造、無實質辯論內容、或結論完全錯誤） |

**各欄位說明：**
- `question_quality: good` = 問題具體有深度；`acceptable` = 可接受但稍淺；`poor` = 流於表面或錯誤
- `answer_accuracy: accurate` = 法規引用正確；`partially_accurate` = 部分正確；`inaccurate` = 引用錯誤
- `logic_consistency: consistent` = 全程邏輯連貫；`minor_issues` = 輕微不一致；`inconsistent` = 明顯矛盾

回答使用以下 JSON 格式：
{
  "overall_score": 0-100,
  "score_rationale": "說明 overall_score 依照上表選擇此分數區間的理由",
  "clause_audits": [
    {
      "clause_id": "條款編號",
      "score": 0-100,
      "score_rationale": "說明此條款評分依據",
      "question_quality": "good | acceptable | poor",
      "answer_accuracy": "accurate | partially_accurate | inaccurate",
      "hallucination_detected": false,
      "hallucination_details": "幻覺具體內容（若有）",
      "logic_consistency": "consistent | minor_issues | inconsistent",
      "depth_sufficient": true,
      "conclusion_reasonable": true,
      "issues": ["具體問題描述"]
    }
  ],
  "summary": "整體審查摘要（2-3 句話）",
  "recommendations": ["改善建議"]
}""",
    "en": """You are the "Third-Party Cross-Examination Quality Auditor" for a Quality Management System. Your task is to independently review the debate transcripts between the Analyzer and the Verifier and assess dialogue quality.

You are neither the Analyzer nor the Verifier — you are an independent third-party auditor.

Review each debate record for:
1. **Question reasonableness**: Are the Analyzer's position and evidence citations reasonable? Any fabricated or non-existent evidence?
2. **Answer correctness**: Are the Verifier's challenges based on accurate regulatory content? Any misquoted clauses or distorted regulatory intent?
3. **Logic consistency**: Is the reasoning throughout the debate coherent? Any self-contradictions?
4. **Hallucination detection**: Did either party fabricate non-existent documents, evidence, or regulatory clauses?
5. **Depth sufficiency**: Is the discussion substantive, or superficial?
6. **Conclusion reasonableness**: Does the final agree/disagree conclusion align with the debate content?

**Scoring criteria (overall_score and per-clause score — apply strictly):**

| Score range | Criteria |
|-------------|----------|
| 90–100 | No hallucinations, precise evidence citations, fully coherent logic, substantive challenges, conclusion matches debate |
| 70–89  | Minor flaws (slightly imprecise citations or shallow arguments), overall good quality, no hallucinations |
| 50–69  | Notable issues (1–2 logic jumps or weak evidence), or suspected but unconfirmed hallucinations |
| 30–49  | Serious issues (multiple contradictions, confirmed hallucinations, or conclusion inconsistent with debate) |
| 0–29   | Complete failure (extensive fabrication, no substantive debate, or entirely wrong conclusion) |

**Field definitions:**
- `question_quality: good` = specific and substantive; `acceptable` = adequate but shallow; `poor` = superficial or incorrect
- `answer_accuracy: accurate` = regulatory citations correct; `partially_accurate` = partially correct; `inaccurate` = citations wrong
- `logic_consistency: consistent` = fully coherent; `minor_issues` = slight inconsistencies; `inconsistent` = clear contradictions

Respond using the following JSON format:
{
  "overall_score": 0-100,
  "score_rationale": "Explain which score band was chosen and why",
  "clause_audits": [
    {
      "clause_id": "clause number",
      "score": 0-100,
      "score_rationale": "Explain scoring basis for this clause",
      "question_quality": "good | acceptable | poor",
      "answer_accuracy": "accurate | partially_accurate | inaccurate",
      "hallucination_detected": false,
      "hallucination_details": "Specific hallucination content (if any)",
      "logic_consistency": "consistent | minor_issues | inconsistent",
      "depth_sufficient": true,
      "conclusion_reasonable": true,
      "issues": ["Specific issue description"]
    }
  ],
  "summary": "Overall review summary (2-3 sentences)",
  "recommendations": ["Improvement suggestions"]
}""",
    "ja": """あなたは品質マネジメントシステムの「第三者相互尋問品質監査員」です。あなたの任務は、分析者（Analyzer）と検証者（Verifier）間の対話記録を独立して審査し、対話品質を判定することです。

あなたは分析者でも検証者でもありません — 独立した第三者監査員です。

各対話記録について以下を確認してください：
1. **質問の合理性**: 分析者の立場と証拠引用は合理的か？捏造または存在しない証拠はないか？
2. **回答の正確性**: 検証者の質疑は正確な規制内容に基づいているか？誤った条項引用や規制の歪曲はないか？
3. **論理の一貫性**: 議論全体の論理は一貫しているか？自己矛盾はないか？
4. **ハルシネーション検出**: いずれかの当事者が存在しない文書、証拠、規制条項を捏造していないか？
5. **議論の深さ**: 議論は十分に実質的か、表面的な対応に留まっていないか？
6. **結論の合理性**: 最終的な同意/不同意の結論は議論内容と一致しているか？

**採点基準（overall_scoreおよび各条項score — 厳密に適用）：**

| スコア範囲 | 基準 |
|-----------|------|
| 90–100 | ハルシネーションなし、証拠引用が正確、論理が完全に一貫、質疑が実質的、結論が議論と一致 |
| 70–89  | 軽微な欠点（引用がやや不正確または議論がやや浅い）、全体的に良質、ハルシネーションなし |
| 50–69  | 顕著な問題（1〜2箇所の論理的飛躍または証拠が薄弱）、または疑わしいが未確認のハルシネーション |
| 30–49  | 深刻な問題（複数の矛盾、確認されたハルシネーション、または結論と議論の不一致） |
| 0–29   | 完全な失敗（広範な捏造、実質的な議論なし、または結論が完全に誤り） |

**フィールド定義：**
- `question_quality: good` = 具体的で実質的；`acceptable` = 許容範囲だが浅い；`poor` = 表面的または誤り
- `answer_accuracy: accurate` = 規制引用が正確；`partially_accurate` = 部分的に正確；`inaccurate` = 引用が誤り
- `logic_consistency: consistent` = 完全に一貫；`minor_issues` = 軽微な不一致；`inconsistent` = 明らかな矛盾

以下のJSON形式で回答してください：
{
  "overall_score": 0-100,
  "score_rationale": "どのスコア帯を選択したか、その理由を説明",
  "clause_audits": [
    {
      "clause_id": "条項番号",
      "score": 0-100,
      "score_rationale": "この条項の採点根拠を説明",
      "question_quality": "good | acceptable | poor",
      "answer_accuracy": "accurate | partially_accurate | inaccurate",
      "hallucination_detected": false,
      "hallucination_details": "ハルシネーションの具体的な内容（ある場合）",
      "logic_consistency": "consistent | minor_issues | inconsistent",
      "depth_sufficient": true,
      "conclusion_reasonable": true,
      "issues": ["具体的な問題の説明"]
    }
  ],
  "summary": "全体的な審査サマリー（2〜3文）",
  "recommendations": ["改善提案"]
}""",
}

_QA_AUDITOR_USER_TEMPLATES: dict[str, str] = {
    "zh": """## 第三方品質稽核任務

請審查以下 {clause_count} 筆交叉詰問對話紀錄：

**文件**: {doc_id} — {doc_title}
**涉及法規**: {regulations}

### 對話紀錄

{debate_transcripts}

請對每一筆對話給出品質評分和具體問題。""",
    "en": """## Third-Party Quality Audit Task

Please review the following {clause_count} cross-examination debate transcripts:

**Document**: {doc_id} — {doc_title}
**Regulations involved**: {regulations}

### Debate Transcripts

{debate_transcripts}

Provide quality scores and specific issues for each debate.""",
    "ja": """## 第三者品質監査タスク

以下の {clause_count} 件の相互尋問対話記録を審査してください：

**文書**: {doc_id} — {doc_title}
**関連規制**: {regulations}

### 対話記録

{debate_transcripts}

各対話の品質スコアと具体的な問題点を提供してください。""",
}


_TRANSCRIPT_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "clause": "條款",
        "audit_question": "稽核問題",
        "verdict": "判定結果",
        "conclusion": "最終結論",
        "agreed": "同意",
        "disagreed": "不同意（標記 RA 覆審）",
        "round": "輪次",
        "analyzer": "分析者",
        "position": "立場",
        "evidence": "證據",
        "verifier": "驗證者",
        "challenge": "質疑",
        "assessment": "評語",
        "truncated": "...（已截斷）",
    },
    "en": {
        "clause": "Clause",
        "audit_question": "Audit Question",
        "verdict": "Verdict",
        "conclusion": "Final Conclusion",
        "agreed": "Agreed",
        "disagreed": "Disagreed (Flagged for RA Review)",
        "round": "Round",
        "analyzer": "Analyzer",
        "position": "Position",
        "evidence": "Evidence",
        "verifier": "Verifier",
        "challenge": "Challenge",
        "assessment": "Assessment",
        "truncated": "...(truncated)",
    },
    "ja": {
        "clause": "条項",
        "audit_question": "監査質問",
        "verdict": "判定結果",
        "conclusion": "最終結論",
        "agreed": "同意",
        "disagreed": "不同意（RA再審フラグ）",
        "round": "ラウンド",
        "analyzer": "分析者",
        "position": "立場",
        "evidence": "証拠",
        "verifier": "検証者",
        "challenge": "質疑",
        "assessment": "評価",
        "truncated": "...（省略）",
    },
}


def _build_debate_transcript(
    clause_id: str,
    clause_title: str,
    audit_question: str,
    verdict: str,
    rounds: list[dict],
    agreed: bool,
    lang: str = "zh-TW",
) -> str:
    lk = _lang_key(lang)
    lb = _TRANSCRIPT_LABELS[lk]
    parts = [
        f"--- {lb['clause']} {clause_id}: {clause_title} ---",
        f"{lb['audit_question']}: {audit_question}",
        f"{lb['verdict']}: {verdict}",
        f"{lb['conclusion']}: {lb['agreed'] if agreed else lb['disagreed']}",
        "",
    ]
    for rd in rounds:
        round_num = rd.get("round", "?")
        analyzer = rd.get("analyzer", {})
        verifier = rd.get("verifier", {})

        a_position = str(analyzer.get("position", analyzer.get("response", "")))[:800]
        a_confidence = analyzer.get(
            "confidence", analyzer.get("revised_confidence", "N/A")
        )
        a_evidence = analyzer.get(
            "key_evidence", analyzer.get("additional_evidence", [])
        )

        v_agreement = verifier.get("agreement_level", "N/A")
        v_challenges = verifier.get(
            "challenges", verifier.get("remaining_concerns", [])
        )
        v_assessment = verifier.get("overall_assessment", "")[:600]

        parts.append(f"  {lb['round']} {round_num}:")
        parts.append(f"    {lb['analyzer']}: confidence={a_confidence}")
        parts.append(f"    {lb['position']}: {a_position}")
        if a_evidence:
            parts.append(f"    {lb['evidence']}: {', '.join(str(e)[:80] for e in a_evidence[:3])}")
        parts.append(f"    {lb['verifier']}: agreement={v_agreement}")
        if isinstance(v_challenges, list) and v_challenges:
            for ch in v_challenges[:2]:
                if isinstance(ch, dict):
                    parts.append(f"    {lb['challenge']}: {ch.get('point', str(ch))[:150]}")
                else:
                    parts.append(f"    {lb['challenge']}: {str(ch)[:150]}")
        if v_assessment:
            parts.append(f"    {lb['assessment']}: {v_assessment}")
        parts.append("")

    return "\n".join(parts)


def run_qa_audit_document(
    doc_id: str,
    rows: list,
    state,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    selected_regulations: list[str] | None = None,
    run_id: str = "",
    lang: str = "zh-TW",
) -> dict:
    from src.analysis.risk_matrix import VERDICT_DISPLAY

    lk = _lang_key(lang)
    label_key = "label_en" if lk == "en" else "label_ja" if lk == "ja" else "label_zh"

    rows_with_debates = [
        r
        for r in rows
        if getattr(r, "verification_rounds", None) and len(r.verification_rounds) > 0
    ]

    if not rows_with_debates:
        return {
            "overall_score": 0,
            "clause_audits": [],
            "summary": "No debate transcripts to audit.",
            "recommendations": [],
            "skipped": True,
        }

    budget = state.get_budget()
    if budget.exceeded:
        return {
            "overall_score": 0,
            "clause_audits": [],
            "summary": "Budget exceeded, QA audit skipped.",
            "recommendations": [],
            "skipped": True,
        }

    transcripts = []
    for row in rows_with_debates:
        verdict_info = VERDICT_DISPLAY.get(row.verdict or "", {})
        verdict_label = verdict_info.get(
            label_key, verdict_info.get("label_zh", row.verdict or _NOT_VERDICTED[lk])
        )
        transcript = _build_debate_transcript(
            clause_id=row.clause_id,
            clause_title=row.clause_title,
            audit_question=row.audit_question,
            verdict=verdict_label,
            rounds=row.verification_rounds,
            agreed=row.verification_agreed or False,
            lang=lang,
        )
        transcripts.append(transcript)

    combined_transcripts = "\n\n".join(transcripts)
    if len(combined_transcripts) > 12000:
        combined_transcripts = (
            combined_transcripts[:12000]
            + "\n\n"
            + _TRANSCRIPT_LABELS[lk]["truncated"]
        )

    doc_title = rows[0].doc_title if rows else doc_id
    regulations_str = (
        ", ".join(selected_regulations) if selected_regulations else "ISO 13485"
    )

    user_prompt = _QA_AUDITOR_USER_TEMPLATES[lk].format(
        clause_count=len(rows_with_debates),
        doc_id=doc_id,
        doc_title=doc_title,
        regulations=regulations_str,
        debate_transcripts=combined_transcripts,
    )

    if run_id:
        emit_verification_event(
            run_id,
            {
                "type": "qa_audit_start",
                "doc_id": doc_id,
                "clause_count": len(rows_with_debates),
            },
        )

    try:
        response, usage = _call_llm(
            llm_completion_fn,
            _QA_AUDITOR_SYSTEM_PROMPTS[lk],
            user_prompt,
            state,
            model,
            temperature,
            max_tokens,
        )

        result = {
            "overall_score": response.get("overall_score", 0),
            "clause_audits": response.get("clause_audits", []),
            "summary": response.get("summary", ""),
            "recommendations": response.get("recommendations", []),
            "llm_usage": usage,
            "llm_model": model,
            "doc_id": doc_id,
            "clause_count": len(rows_with_debates),
            "skipped": False,
        }

        audit_by_clause = {
            a.get("clause_id", ""): a for a in response.get("clause_audits", [])
        }
        for row in rows_with_debates:
            clause_audit = audit_by_clause.get(row.clause_id)
            if clause_audit:
                row.qa_audit = clause_audit
            else:
                row.qa_audit = {
                    "clause_id": row.clause_id,
                    "score": 0,
                    "question_quality": "unknown",
                    "answer_accuracy": "unknown",
                    "hallucination_detected": False,
                    "issues": ["No audit data returned for this clause"],
                }

        if run_id:
            emit_verification_event(
                run_id,
                {
                    "type": "qa_audit_complete",
                    "doc_id": doc_id,
                    "overall_score": result["overall_score"],
                    "clause_count": len(rows_with_debates),
                    "summary": result["summary"][:200],
                },
            )

        return result

    except RuntimeError:
        return {
            "overall_score": 0,
            "clause_audits": [],
            "summary": "QA audit failed: budget exceeded.",
            "recommendations": [],
            "skipped": True,
        }
    except Exception as e:
        return {
            "overall_score": 0,
            "clause_audits": [],
            "summary": f"QA audit failed: {str(e)[:200]}",
            "recommendations": [],
            "skipped": True,
            "error": str(e)[:200],
        }
