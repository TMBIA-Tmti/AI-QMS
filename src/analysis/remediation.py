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
# Prompt construction
# ============================================================

_SYSTEM_PROMPT = """你是品質管理系統改善建議助手。你的任務是根據差距分析結果，提供具體的品質文件改善建議。

嚴格規則：
1. 每項建議必須引用對應的法規條文原文作為依據。
2. 建議必須具體可執行，包含「修改哪份文件」「修改哪個段落」「建議修改方向」。
3. 不提供模糊的方向性建議（如「應加強管理」），每項都要可操作。
4. 如果法規條文不可用，以稽核問題本身作為改善依據。
5. 回答必須使用指定的 JSON 格式。"""

_USER_PROMPT_TEMPLATE = """## 改善建議任務

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

請以 JSON 格式回答：

```json
{{
  "remediation": {{
    "summary": "改善方向總述（一句話）",
    "priority": "high" | "medium" | "low",
    "suggestions": [
      {{
        "action": "具體修改動作",
        "target_section": "建議修改的文件段落/章節",
        "regulation_basis": "法規依據（引用條文原文）",
        "example_content": "建議新增或修改的內容範例"
      }}
    ],
    "regulation_citation": "最相關的法規條文完整引用"
  }}
}}
```"""


def _build_gap_analysis_section(
    evidence_items: list[EvidenceItem],
    verdict: str,
) -> str:
    """Format gap analysis results for the remediation prompt."""
    parts = []

    # Group by status
    not_found = [e for e in evidence_items if not e.found]
    inadequate = [e for e in evidence_items if e.found and e.is_inadequate]
    outdated = [e for e in evidence_items if e.found and e.is_outdated]

    if not_found:
        parts.append("### 未找到的證據項目")
        for item in not_found:
            parts.append(
                f"- **{item.evidence_name}**\n  原因: {item.llm_reasoning or '未說明'}"
            )

    if inadequate:
        parts.append("\n### 內容不充分的證據項目")
        for item in inadequate:
            parts.append(
                f"- **{item.evidence_name}**\n"
                f"  現有內容: {item.source_quote or '無引用'}\n"
                f"  不足原因: {item.llm_reasoning or '未說明'}"
            )

    if outdated:
        parts.append("\n### 版本過期的項目")
        for item in outdated:
            parts.append(
                f"- **{item.evidence_name}**\n  出處: {item.source_section or '未知'}"
            )

    if not parts:
        parts.append("（無具體差距項目，但整體判定為非完全符合）")

    return "\n".join(parts)


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
                        # Extract ~800 chars around the match for remediation context
                        start = max(0, match.start() - 50)
                        end = min(len(content), match.end() + 800)
                        return content[start:end]

        return "（系統中無此法規條文原文，請以稽核問題本身作為改善依據）"
    except Exception:
        return "（無法取得法規條文）"


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
    max_tokens: int = 4096,
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

    Returns:
        PhaseResult with remediation suggestions
    """
    phase_result = PhaseResult(
        phase=Phase.REMEDIATION.value,
        started_at=time.time(),
    )

    try:
        # Skip if fully compliant — no remediation needed
        if row_state.verdict == "full_compliance":
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "完全符合，無需改善建議"}
            phase_result.completed_at = time.time()
            return phase_result

        # Reconstruct evidence items
        evidence_items = [EvidenceItem.from_dict(e) for e in row_state.evidence_items]

        if not evidence_items:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No evidence items from earlier phases"}
            phase_result.completed_at = time.time()
            return phase_result

        # Build gap analysis section
        gap_section = _build_gap_analysis_section(
            evidence_items, row_state.verdict or ""
        )

        # Get regulation text for citation
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

        # Import risk display for context
        from src.analysis.risk_matrix import RISK_LEVEL_DISPLAY

        risk_display = RISK_LEVEL_DISPLAY.get(row_state.risk_level or "", {})
        risk_label = risk_display.get("label_zh", row_state.risk_level or "未評估")

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            risk_level=risk_label,
            gap_severity=row_state.gap_severity or "未評估",
            gap_analysis_section=gap_section,
            regulation_text=regulation_text,
            doc_id=row_state.doc_id,
            doc_title=row_state.doc_title,
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
                "parse_warning": "LLM 回應格式無法解析，但已完成呼叫",
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

_DOC_REMEDIATION_SYSTEM_PROMPT = """你是品質管理系統改善建議助手。你的任務是根據差距分析結果，針對一份文件的多個法規條款提供具體的改善建議。

嚴格規則：
1. 每項建議必須引用對應的法規條文原文作為依據。
2. 建議必須具體可執行，包含「修改哪個段落」「建議修改方向」。
3. 不提供模糊的方向性建議。
4. 如果法規條文不可用，以稽核問題本身作為改善依據。
5. 回答必須使用指定的 JSON 格式，按條款編號分組。"""

_DOC_REMEDIATION_USER_TEMPLATE = """## 改善建議任務

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
```"""


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
    max_tokens: int = 8192,
    run_id: str = "",
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
    phase_result = PhaseResult(
        phase=Phase.REMEDIATION.value,
        started_at=time.time(),
    )

    try:
        # Filter rows that need remediation (not fully compliant)
        rows_needing_remediation = [
            r for r in rows if r.verdict != "full_compliance"
        ]

        if not rows_needing_remediation:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "所有條款完全符合，無需改善建議"}
            phase_result.completed_at = time.time()
            return phase_result

        # Import risk display for context
        from src.analysis.risk_matrix import RISK_LEVEL_DISPLAY

        # Build per-clause gap sections
        clauses_parts = []
        for i, row in enumerate(rows_needing_remediation, 1):
            evidence_items = [EvidenceItem.from_dict(e) for e in row.evidence_items]
            gap_section = _build_gap_analysis_section(
                evidence_items, row.verdict or ""
            )
            regulation_text = _get_regulation_text(row.clause_id, row.standard)
            risk_display = RISK_LEVEL_DISPLAY.get(row.risk_level or "", {})
            risk_label = risk_display.get("label_zh", row.risk_level or "未評估")

            clauses_parts.append(
                f"### {i}. 條款 {row.clause_id} — {row.clause_title}\n"
                f"**稽核問題**: {row.audit_question}\n"
                f"**風險等級**: {risk_label}\n"
                f"**差距類型**: {row.gap_severity or '未評估'}\n\n"
                f"**差距分析**:\n{gap_section}\n\n"
                f"**法規參考**: {regulation_text[:400]}"
            )

        clauses_gap_section = "\n\n".join(clauses_parts)
        doc_title = rows[0].doc_title if rows else doc_id

        user_prompt = _DOC_REMEDIATION_USER_TEMPLATE.format(
            clause_count=len(rows_needing_remediation),
            doc_id=doc_id,
            doc_title=doc_title,
            clauses_gap_section=clauses_gap_section,
        )

        messages = [
            {"role": "system", "content": _DOC_REMEDIATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = "LLM token 預算已用盡"
            phase_result.completed_at = time.time()
            return phase_result

        # SSE: emit before LLM call
        _emit_pipeline_event(run_id, {
            "type": "phase_4_start",
            "phase": "remediation",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "clause_ids": [r.clause_id for r in rows_needing_remediation],
            "clause_count": len(rows_needing_remediation),
            "prompt_preview": user_prompt[:500],
        })

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
        _emit_pipeline_event(run_id, {
            "type": "phase_4_result",
            "phase": "remediation",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "clause_ids": [r.clause_id for r in rows_needing_remediation],
            "llm_response": response_text[:2000],
            "total_suggestions": total_suggestions,
            "usage": usage,
        })

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(run_id, {
            "type": "phase_4_error",
            "phase": "remediation",
            "doc_id": doc_id,
            "error": str(e)[:500],
        })

    phase_result.completed_at = time.time()
    return phase_result
