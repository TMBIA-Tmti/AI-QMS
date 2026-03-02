"""
AI-QMS — Phase 1: Gap Scan
============================

LLM call #1 — For each row (clause × doc), ask the LLM to search the
company document for evidence of each expected_evidence item.

The LLM is a SEARCH ASSISTANT only — it finds relevant paragraphs and
quotes them. It does NOT make compliance judgments.

Output: EvidenceItem list per row (found/not found, source quote, section).
"""

from __future__ import annotations

import json
import time
from typing import Optional

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    EvidenceItem,
    RowState,
    PipelineState,
)


__all__ = [
    "run_gap_scan_row",
    "build_gap_scan_prompt",
]


# ============================================================
# Prompt construction
# ============================================================

_SYSTEM_PROMPT = """你是品質管理系統文件搜尋助手。你的任務是在公司品質文件中搜尋特定的證據項目。

嚴格規則：
1. 你只負責「搜尋」和「引用」，不做合規性判斷。
2. 找到相關段落時，必須精確引用原文（quote），標明出處段落位置。
3. 找不到時，明確標示 found=false，不得編造或推測內容。
4. 如果找到的內容不足以涵蓋要求，標示 is_inadequate=true 並說明原因。
5. 回答必須使用指定的 JSON 格式。"""

_USER_PROMPT_TEMPLATE = """## 搜尋任務

**法規條款**: {clause_id} — {clause_title}
**稽核問題**: {audit_question}

**待搜尋的證據項目** (共 {evidence_count} 項):
{evidence_list}

## 公司文件內容

**文件編號**: {doc_id}
**文件標題**: {doc_title}

{doc_content}

## 回答格式

請以 JSON 格式回答，每個證據項目一個物件：

```json
{{
  "evidence_results": [
    {{
      "evidence_name": "證據項目名稱（與上方列表完全一致）",
      "found": true/false,
      "source_section": "找到的段落所在章節標題",
      "source_quote": "精確引用原文（最多200字）",
      "relevance_score": 0.0-1.0,
      "is_inadequate": true/false,
      "is_outdated": true/false,
      "reasoning": "簡述為何判定找到/未找到"
    }}
  ]
}}
```"""


def build_gap_scan_prompt(
    row: RowState,
    doc_content: str,
    candidate_sections: Optional[list[dict]] = None,
    max_content_chars: int = 15000,
) -> list[dict]:
    """Build the LLM prompt for gap scanning a single row.

    If candidate_sections from Phase 0.5 exist, prioritize those sections
    in the document content to stay within token limits.

    Args:
        row: The row being scanned
        doc_content: Full document content
        candidate_sections: From Phase 0.5 reference mapping
        max_content_chars: Maximum chars of doc content to include

    Returns:
        List of message dicts for LLM completion
    """

    # Build evidence list
    evidence_lines = []
    for i, ev in enumerate(row.expected_evidence, 1):
        evidence_lines.append(f"{i}. {ev}")
    evidence_list = "\n".join(evidence_lines)

    # Prepare document content — prioritize candidate sections
    if candidate_sections and len(doc_content) > max_content_chars:
        # Include candidate sections first, then fill remaining with context
        prioritized_parts = []
        remaining_budget = max_content_chars

        for cs in candidate_sections:
            preview = cs.get("text_preview", "")
            if preview and remaining_budget > 0:
                chunk = preview[:remaining_budget]
                prioritized_parts.append(
                    f"### {cs.get('heading', '未知章節')}\n{chunk}"
                )
                remaining_budget -= len(chunk)

        # Fill remaining budget with document head/tail
        if remaining_budget > 500:
            remaining_content = doc_content[:remaining_budget]
            prioritized_parts.append(f"\n### 其他文件內容\n{remaining_content}")

        final_content = "\n\n".join(prioritized_parts)
    else:
        final_content = doc_content[:max_content_chars]

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        clause_id=row.clause_id,
        clause_title=row.clause_title,
        audit_question=row.audit_question,
        evidence_count=len(row.expected_evidence),
        evidence_list=evidence_list,
        doc_id=row.doc_id,
        doc_title=row.doc_title,
        doc_content=final_content,
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_gap_scan_response(
    response_text: str,
    expected_evidence: list[str],
) -> list[EvidenceItem]:
    """Parse the LLM's JSON response into EvidenceItem objects.

    Handles partial/malformed JSON gracefully.
    """
    evidence_items: list[EvidenceItem] = []

    # Try to extract JSON from response
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
        results = data.get("evidence_results", [])

        for r in results:
            item = EvidenceItem(
                evidence_name=r.get("evidence_name", ""),
                found=bool(r.get("found", False)),
                source_section=r.get("source_section"),
                source_quote=r.get("source_quote"),
                relevance_score=r.get("relevance_score"),
                is_inadequate=bool(r.get("is_inadequate", False)),
                is_outdated=bool(r.get("is_outdated", False)),
                llm_reasoning=r.get("reasoning"),
            )
            evidence_items.append(item)

    except (json.JSONDecodeError, KeyError, TypeError):
        # If JSON parsing fails, create "not found" items for all evidence
        for ev_name in expected_evidence:
            evidence_items.append(
                EvidenceItem(
                    evidence_name=ev_name,
                    found=False,
                    llm_reasoning="LLM 回應格式錯誤，無法解析",
                )
            )

    # Ensure all expected evidence items are accounted for
    found_names = {item.evidence_name for item in evidence_items}
    for ev_name in expected_evidence:
        if ev_name not in found_names:
            evidence_items.append(
                EvidenceItem(
                    evidence_name=ev_name,
                    found=False,
                    llm_reasoning="LLM 回應中未包含此項目",
                )
            )

    return evidence_items


# ============================================================
# Phase execution
# ============================================================


def run_gap_scan_row(
    row_state: RowState,
    state: PipelineState,
    llm_completion_fn: callable,
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> PhaseResult:
    """Execute Phase 1 gap scan for a single row.

    Args:
        row_state: The row to scan
        state: Pipeline state (for budget tracking)
        llm_completion_fn: Function matching LLMProviderManager.completion() signature
        model: LLM model name
        temperature: LLM temperature (low for precision)
        max_tokens: Max tokens for response

    Returns:
        PhaseResult with evidence items in output
    """
    phase_result = PhaseResult(
        phase=Phase.GAP_SCAN.value,
        started_at=time.time(),
    )

    try:
        # Get document content
        from src.storage.markdown_storage import MarkdownStoreService

        service = MarkdownStoreService()
        doc_result = service.get_document(row_state.doc_id)

        if not doc_result or not doc_result.get("success"):
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"無法讀取文件 {row_state.doc_id}"
            phase_result.completed_at = time.time()
            return phase_result

        doc_content = doc_result.get("content", "")

        # Get candidate sections from Phase 0.5
        ref_result = row_state.get_phase_result(Phase.REFERENCE_MAPPING)
        candidate_sections = None
        if ref_result and ref_result.output:
            candidate_sections = ref_result.output.get("candidate_sections")

        # Build prompt
        messages = build_gap_scan_prompt(
            row_state,
            doc_content,
            candidate_sections,
        )

        # Check budget
        budget = state.get_budget()
        if budget.exceeded:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = "LLM token 預算已用盡"
            phase_result.completed_at = time.time()
            return phase_result

        # Call LLM (non-streaming)
        response = llm_completion_fn(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        # Extract response
        response_text = response.get("content", "")
        usage = response.get("usage", {})
        llm_model = response.get("model", model)

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse evidence items
        evidence_items = _parse_gap_scan_response(
            response_text,
            row_state.expected_evidence,
        )

        # Store results
        row_state.evidence_items = [item.to_dict() for item in evidence_items]

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "evidence_count": len(evidence_items),
            "found_count": sum(1 for e in evidence_items if e.found),
            "not_found_count": sum(1 for e in evidence_items if not e.found),
            "inadequate_count": sum(1 for e in evidence_items if e.is_inadequate),
            "raw_response_length": len(response_text),
        }
        phase_result.llm_usage = usage
        phase_result.llm_model = llm_model

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    return phase_result
