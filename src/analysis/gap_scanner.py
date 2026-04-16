"""
AI-QMS — Phase 1: Gap Scan
============================

LLM call #1 — For each DOCUMENT, ask the LLM to search for evidence
of all expected_evidence items across all clauses the document covers.

Per-document mode (primary): ONE LLM call per document, covers all clauses.
Per-row mode (legacy): ONE LLM call per clause×doc pair, for single-row re-run.

The LLM is a SEARCH ASSISTANT only — it finds relevant paragraphs and
quotes them. It does NOT make compliance judgments.

Output: EvidenceItem list per row (found/not found, source quote, section).
All LLM interactions are emitted via SSE for real-time HTML viewing.
"""

from __future__ import annotations

import json
import time
from typing import Optional, Callable

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    EvidenceItem,
    RowState,
    PipelineState,
)


import logging

logger = logging.getLogger(__name__)

__all__ = [
    "run_gap_scan_row",
    "run_gap_scan_document",
    "build_gap_scan_prompt",
    "filter_relevant_clauses",
]


# ============================================================
# Prompt construction
# ============================================================

_SYSTEM_PROMPT = """你是 ISO 13485:2016 稽核支援文件搜尋助手，專精於依照客觀證據原則（Objective Evidence）在品質文件中定位合規依據。

嚴格規則：
1. 你只負責「搜尋」和「精確引用」，不做合規性判斷。
2. 找到相關段落時，必須精確引用原文（quote），標明出處章節標題與段落位置。
3. 找不到時，明確標示 found=false，絕不編造、推測或補充未出現於文件的內容。
4. 區分三種結果（根據 ISO 13485 稽核實務）：
   - 充分 (found=true, is_inadequate=false)：文件明確描述「如何執行」而非僅「提及」該要求，包含程序、責任人及可量測標準。
   - 不充分 (found=true, is_inadequate=true)：文件提到此要求但缺乏具體程序、責任人、頻率或可量測標準。
   - 缺失 (found=false)：文件中完全找不到相關內容。
5. 語言符合性 ≠ 法規正確性：文件使用相似術語不等於實質涵蓋法規要求，需確認實質程序內容。
6. 如發現文件版本日期或引用標準已過期（如引用 ISO 13485:2003 而非 2016 版），標示 is_outdated=true。
7. 回答必須使用指定的 JSON 格式。"""

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
    max_tokens: int = 8192,
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
        from src.services.markdown_store_service import MarkdownStoreService

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

        # 檢測 LLM 錯誤回應
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or response.get("all_failed")
        ):
            error_detail = response_text[:200] if response_text else "LLM 回應為空"
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"LLM 呼叫失敗: {error_detail}"
            phase_result.completed_at = time.time()
            return phase_result

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
# Clause relevance pre-filter (Phase 0.5)
# ============================================================

import re as _re

# ---------------------------------------------------------------------------
# Static keyword → clause mapping (zero tokens, instant)
# Keys are regex patterns matched against "<doc_id> <doc_title>" (lowercase).
# Each entry is a tuple of (pattern, [clause_ids]).
# Multiple patterns can match; results are unioned.
# ---------------------------------------------------------------------------
_KEYWORD_CLAUSE_RULES: list[tuple[str, list[str]]] = [
    # ── Document / Record Control ──────────────────────────────────────────
    (r"document.control|document.review|document.numbering|external.document"
     r"|文件管制|文件控制|文件編號|numbering.system",
     ["4.2.1", "4.2.3", "4.2.4", "4.2.5"]),
    (r"record.control|record.retention|electronic.record|記錄管制|記錄控制",
     ["4.2.4", "4.2.5"]),
    (r"quality.manual|品質手冊|qm-",
     ["4.1", "4.2.1", "4.2.2", "5.1", "5.3"]),

    # ── QMS General Requirements ──────────────────────────────────────────
    (r"general.require|general.document|documentation.require|general_require",
     ["4.1", "4.2.1", "4.2.2", "4.2.3", "4.2.4", "4.2.5"]),

    # ── Management ────────────────────────────────────────────────────────
    (r"management.review|管理審查|管理評審",
     ["5.1", "5.2", "5.6.1", "5.6.2", "5.6.3", "8.4", "8.5.1"]),
    (r"management.responsib|management.commit|management_responsib|management_commit",
     ["5.1", "5.2", "5.3", "5.4.1", "5.4.2", "5.5.1", "5.5.2", "5.5.3",
      "5.6.1", "5.6.2", "5.6.3"]),
    (r"quality.policy|品質政策|quality.objective|品質目標",
     ["5.1", "5.2", "5.3", "5.4.1", "5.4.2"]),
    (r"planning(?!.of.product)|計畫|規劃",
     ["5.4.1", "5.4.2"]),
    (r"responsibility.authority|responsibility_authority|¾responsibility",
     ["5.5.1", "5.5.2", "5.5.3"]),
    (r"organization|組織|organ.chart|組織圖",
     ["5.5.1", "5.5.2", "5.5.3", "6.1"]),
    (r"customer.focus|customer_focus",
     ["5.2", "7.2.1"]),

    # ── Human Resources / Infrastructure ──────────────────────────────────
    (r"resource.management|resource_management|provision.of.resource|provision_of_resource",
     ["6.1", "6.2", "6.3", "6.4.1", "6.4.2"]),
    (r"training|訓練|培訓|教育訓練|competenc|onboard|human.resource|human_resource",
     ["6.2"]),
    (r"infrastruct|基礎設施|facility|設施|環境|work.environment|equipment.mainten"
     r"|backup|pest.control|temperature.monitor|waste.disposal|cleanroom|gown",
     ["6.3", "6.4.1", "6.4.2"]),

    # ── Product Realization Planning ──────────────────────────────────────
    (r"product.realiz|產品實現|realiz.planning",
     ["7.1"]),
    (r"customer.require|顧客要求|customer.review|合約審查|order.review"
     r"|order.entry|order_entry|customer.related|customer_related",
     ["7.2.1", "7.2.2", "7.2.3"]),
    (r"customer.communicat|顧客溝通|customer.feedback",
     ["7.2.3", "8.2.1"]),

    # ── Design & Development ──────────────────────────────────────────────
    (r"design.develop|design.and.develop|設計開發|design.control|design.plan"
     r"|design.verif|design.histor|clinical.eval",
     ["7.3.1", "7.3.2", "7.3.3", "7.3.4", "7.3.5",
      "7.3.6", "7.3.7", "7.3.8", "7.3.9", "7.3.10",
      "4.2.3", "4.2.4"]),

    # ── Purchasing / Supplier ─────────────────────────────────────────────
    (r"purchas|採購|procure|supplier.eval|供應商評估|vendor",
     ["7.4.1", "7.4.2", "7.4.3", "4.2.3", "4.2.4"]),

    # ── Production & Service ──────────────────────────────────────────────
    (r"production.control|production.and.service|production.setup|production_setup"
     r"|service.provision|生產管制|manufactur|製造|process.control|製程"
     r"|line.clearance|line_clearance|rework",
     ["7.5.1", "7.5.2", "7.5.3", "7.5.4", "4.2.3", "4.2.4"]),
    (r"packaging",
     ["7.5.1", "7.5.3", "4.2.4"]),
    (r"clean.room|cleanroom|潔淨室|contamination|污染控制",
     ["6.4.1", "7.5.1", "7.5.2"]),
    (r"steril|滅菌|灭菌",
     ["7.5.2", "7.5.5", "4.2.3", "4.2.4"]),
    (r"label|標示|標籤|marking",
     ["7.5.6", "7.5.7"]),
    (r"product.identif|product_identif|identification|traceab|可追溯|追溯|lot.control|批號管制",
     ["7.5.8", "7.5.9", "7.5.9.1", "7.5.9.2"]),
    (r"implant|植入|active.implant",
     ["7.5.10", "7.5.11"]),
    (r"customer.property|顧客財產|customer.supplied",
     ["7.5.4"]),

    # ── Calibration / Measurement Equipment ──────────────────────────────
    (r"calibrat|校準|校正|instrument.control|caliper|thermometer|scale"
     r"|measuring.equipment|monitoring.and.measuring.equipment"
     r"|control.of.monitoring|量測設備",
     ["7.6", "4.2.4"]),

    # ── Monitoring & Measurement ──────────────────────────────────────────
    (r"internal.audit|內部稽核|audit.checklist|auditor.qualif|audit.procedure",
     ["8.2.1", "8.2.2", "4.2.3", "4.2.4"]),
    (r"customer.satisf|顧客滿意|satisfaction.survey|customer.survey",
     ["8.2.1"]),
    (r"monitoring.and.measurement.of.process|monitoring.measurement.of.process"
     r"|process.monitor|製程監控|statistical|sampling",
     ["8.2.3", "8.2.4"]),
    (r"monitoring.and.measurement.of.product|monitoring.measurement.of.product"
     r"|product.inspect|產品檢驗|incoming.inspect|進料检验|ipqc|oqc|iqc",
     ["8.2.4", "8.2.4.1", "8.2.4.2", "4.2.4"]),

    # ── Nonconforming Product ─────────────────────────────────────────────
    (r"nonconform|不合格|不符合|ncr|deviation|偏差",
     ["8.3", "8.3.1", "8.3.2", "8.3.3", "8.3.4", "8.5.2", "4.2.4"]),
    (r"advisory.notice|安全通報|field.safety|recall|回收",
     ["8.3.3", "8.3.4"]),

    # ── Data Analysis / Improvement ───────────────────────────────────────
    (r"data.analysis|data.trend|data_trend|數據分析|資料分析|statistical|general.measurement|general_measurement",
     ["8.4"]),
    (r"improvement|改進|改善|continual.improv|持續改善",
     ["8.5.1"]),
    (r"corrective.action|矯正措施|capa|root.cause|root_cause",
     ["8.5.1", "8.5.2", "8.3", "8.2.2", "4.2.4"]),
    (r"preventive.action|預防措施|preventive|fmea",
     ["8.5.1", "8.5.3", "4.2.4"]),
    (r"risk.manag|risk.analysis|risk_analysis|風險管理|風險分析|risk.assessment|風險評估",
     ["7.1"]),
    (r"technical.file|technical_file",
     ["4.2.3", "4.2.4", "7.3.10", "8.2.6"]),

    # ── Complaint Handling ────────────────────────────────────────────────
    (r"complaint|客訴|抱怨|customer.complaint",
     ["8.2.1", "8.2.2", "8.5.1", "8.5.2", "4.2.4"]),

    # ── Regulatory / MDR / UDI ───────────────────────────────────────────
    (r"regulatory|法規|mdr|fda|post.market|上市後",
     ["8.2.1", "8.2.6", "8.3.4"]),
    (r"vigilance|警戒|adverse.event|不良事件",
     ["8.2.3", "8.2.6", "8.3.3", "8.3.4"]),
]

_FILTER_LLM_SYSTEM_PROMPT = """你是 ISO 13485:2016 稽核範疇分析師，負責判斷哪些條款與指定文件「直接相關」。

直接相關的定義：稽核員審查此文件時，預期能在文件內容中找到該條款要求的程序、責任人或可量測標準。

排除條件（符合任一即排除）：
- 條款屬於完全不同的業務功能
- 文件只「引用」或「提及」該條款，但不負責描述其執行程序
- 條款的主責部門與此文件無直接關係

只回傳 JSON 陣列，不附加說明。每份文件預期涵蓋 3-15 個條款。"""

_FILTER_LLM_USER_TEMPLATE = """文件編號: {doc_id}
文件標題: {doc_title}

文件前 1500 字:
{doc_excerpt}

---
請從以下條款中，選出與此文件直接相關的條款編號：

{clause_list}

```json
["條款編號1", ...]
```"""


def filter_relevant_clauses(
    doc_id: str,
    doc_title: str,
    doc_content: str,
    rows: list[RowState],
    llm_completion_fn: Callable,
    model: str = "default",
) -> list[str]:
    """Pre-filter: return only clause IDs relevant to this document.

    Strategy (in order):
    1. Match doc_id + doc_title against static keyword rules (zero tokens).
       If ≥1 rule matches, union all matched clause sets and return.
    2. If no keyword match, fall back to a cheap LLM call (max_tokens=512).
    3. If LLM call fails, return all clause IDs (safe fallback).

    Returns:
        List of clause_ids that should be included in the full gap scan.
    """
    all_clause_ids = [row.clause_id for row in rows]
    valid_ids = set(all_clause_ids)
    search_text = f"{doc_id} {doc_title}".lower()

    # ── Step 1: static keyword matching ────────────────────────────────────
    matched: set[str] = set()
    for pattern, clause_ids in _KEYWORD_CLAUSE_RULES:
        if _re.search(pattern, search_text):
            matched.update(c for c in clause_ids if c in valid_ids)

    if matched:
        result = [cid for cid in all_clause_ids if cid in matched]
        logger.info(
            "filter_relevant_clauses [keyword]: %s → %d/%d clauses (patterns matched)",
            doc_id, len(result), len(all_clause_ids),
        )
        return result

    # ── Step 2: LLM fallback for unrecognised documents ────────────────────
    logger.info("filter_relevant_clauses [llm]: %s — no keyword match, calling LLM", doc_id)
    clause_lines = [f"{row.clause_id}: {row.clause_title}" for row in rows]
    clause_list = "\n".join(clause_lines)

    user_prompt = _FILTER_LLM_USER_TEMPLATE.format(
        doc_id=doc_id,
        doc_title=doc_title,
        doc_excerpt=doc_content[:1500],
        clause_list=clause_list,
    )

    try:
        response = llm_completion_fn(
            messages=[
                {"role": "system", "content": _FILTER_LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0.0,
            max_tokens=512,
            stream=False,
        )
        text = response.get("content", "") if response else ""
        if not text or text.startswith("[ERROR]"):
            logger.warning("filter_relevant_clauses [llm]: call failed, using all clauses")
            return all_clause_ids

        json_str = text.strip()
        if "```json" in json_str:
            start = json_str.index("```json") + 7
            end = json_str.index("```", start) if "```" in json_str[start:] else len(json_str)
            json_str = json_str[start:end].strip()
        elif "```" in json_str:
            start = json_str.index("```") + 3
            end = json_str.index("```", start) if "```" in json_str[start:] else len(json_str)
            json_str = json_str[start:end].strip()

        relevant = json.loads(json_str)
        if not isinstance(relevant, list) or not relevant:
            return all_clause_ids

        filtered = [cid for cid in all_clause_ids if cid in set(relevant) & valid_ids]
        if not filtered:
            return all_clause_ids

        logger.info(
            "filter_relevant_clauses [llm]: %s → %d/%d clauses retained",
            doc_id, len(filtered), len(all_clause_ids),
        )
        return filtered

    except Exception as exc:
        logger.warning("filter_relevant_clauses [llm] exception: %s — using all clauses", exc)
        return all_clause_ids


# ============================================================
# Per-document prompt construction
# ============================================================

_DOC_SYSTEM_PROMPT = """你是 ISO 13485:2016 稽核支援文件搜尋助手，專精於依照客觀證據原則（Objective Evidence）在品質文件中定位多個法規條款的合規依據。

嚴格規則：
1. 你只負責「搜尋」和「精確引用」，不做合規性判斷。
2. 找到相關段落時，必須精確引用原文（quote），標明出處章節標題與段落位置。
3. 找不到時，明確標示 found=false，絕不編造、推測或補充未出現於文件的內容。
4. 區分三種結果（根據 ISO 13485:2016 稽核實務）：
   - 充分 (found=true, is_inadequate=false)：文件明確描述「如何執行」而非僅「提及」該要求，包含程序、責任人及可量測標準。
   - 不充分 (found=true, is_inadequate=true)：文件提到此要求但缺乏具體程序、責任人、頻率或可量測標準。
   - 缺失 (found=false)：文件中完全找不到相關內容。
5. 語言符合性 ≠ 法規正確性：文件使用相似術語不等於實質涵蓋法規要求，需確認實質程序內容。
6. 如發現文件版本日期或引用標準已過期，標示 is_outdated=true。
7. 回答必須使用指定的 JSON 格式，按條款編號分組。"""

_DOC_USER_PROMPT_TEMPLATE = """## 搜尋任務

你需要在以下品質文件中，針對 {clause_count} 個法規條款搜尋對應的證據項目。

### 法規條款清單

{clauses_section}

## 公司文件內容

**文件編號**: {doc_id}
**文件標題**: {doc_title}

{doc_content}

## 回答格式

請以 JSON 格式回答，按條款編號分組：

```json
{{
  "clause_results": {{
    "條款編號": {{
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
  }}
}}
```"""


def _parse_doc_gap_scan_response(
    response_text: str,
    rows: list[RowState],
) -> dict[str, list[EvidenceItem]]:
    """Parse per-document LLM response into per-clause evidence items.

    Returns:
        Dict mapping clause_id -> list of EvidenceItem
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

    result: dict[str, list[EvidenceItem]] = {}

    # Build expected evidence map for fallback
    expected_map: dict[str, list[str]] = {}
    for row in rows:
        expected_map[row.clause_id] = row.expected_evidence

    try:
        data = json.loads(json_str)
        clause_results = data.get("clause_results", {})

        for clause_id, clause_data in clause_results.items():
            evidence_list = clause_data.get("evidence_results", [])
            items: list[EvidenceItem] = []
            for r in evidence_list:
                items.append(
                    EvidenceItem(
                        evidence_name=r.get("evidence_name", ""),
                        found=bool(r.get("found", False)),
                        source_section=r.get("source_section"),
                        source_quote=r.get("source_quote"),
                        relevance_score=r.get("relevance_score"),
                        is_inadequate=bool(r.get("is_inadequate", False)),
                        is_outdated=bool(r.get("is_outdated", False)),
                        llm_reasoning=r.get("reasoning"),
                    )
                )
            result[clause_id] = items

    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Per-document gap scan JSON parse failed")

    # Ensure all clauses have entries, fill missing with 'not found'
    for row in rows:
        if row.clause_id not in result:
            result[row.clause_id] = [
                EvidenceItem(
                    evidence_name=ev,
                    found=False,
                    llm_reasoning="LLM 回應中未包含此條款的結果",
                )
                for ev in row.expected_evidence
            ]
        else:
            # Ensure all expected evidence items are accounted for
            found_names = {item.evidence_name for item in result[row.clause_id]}
            for ev in row.expected_evidence:
                if ev not in found_names:
                    result[row.clause_id].append(
                        EvidenceItem(
                            evidence_name=ev,
                            found=False,
                            llm_reasoning="LLM 回應中未包含此項目",
                        )
                    )

    return result


# ============================================================
# Per-document Phase execution (PRIMARY)
# ============================================================


def run_gap_scan_document(
    doc_id: str,
    rows: list[RowState],
    state: PipelineState,
    llm_completion_fn: Callable,
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 8192,
    run_id: str = "",
) -> PhaseResult:
    """Execute Phase 1 gap scan for ALL clauses of one document in a single LLM call.

    Args:
        doc_id: Document ID
        rows: All RowState objects for this document
        state: Pipeline state (for budget tracking)
        llm_completion_fn: LLM completion function (returns dict)
        model: LLM model name
        temperature: LLM temperature
        max_tokens: Max tokens for response
        run_id: Pipeline run ID for SSE emission

    Returns:
        PhaseResult with per-clause evidence breakdown
    """
    phase_result = PhaseResult(
        phase=Phase.GAP_SCAN.value,
        started_at=time.time(),
    )

    try:
        # Get document content (once for all clauses)
        from src.services.markdown_store_service import MarkdownStoreService

        service = MarkdownStoreService()
        doc_result = service.get_document(doc_id)

        if not doc_result or not doc_result.get("success"):
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"無法讀取文件 {doc_id}"
            phase_result.completed_at = time.time()
            return phase_result

        doc_content = doc_result.get("content", "")
        doc_title = rows[0].doc_title if rows else doc_id
        max_content_chars = 15000
        final_content = doc_content[:max_content_chars]

        # --- Phase 0.5: clause relevance pre-filter ---
        # Cheap call (max_tokens=512) to drop clauses clearly outside this
        # document's scope before the expensive full-scan prompt is built.
        relevant_ids = filter_relevant_clauses(
            doc_id=doc_id,
            doc_title=doc_title,
            doc_content=doc_content,
            rows=rows,
            llm_completion_fn=llm_completion_fn,
            model=model,
        )
        relevant_id_set = set(relevant_ids)
        scan_rows = [r for r in rows if r.clause_id in relevant_id_set]
        skipped_rows = [r for r in rows if r.clause_id not in relevant_id_set]

        # Mark skipped clauses as out-of-scope immediately (no LLM cost)
        for row in skipped_rows:
            row.evidence_items = [
                EvidenceItem(
                    evidence_name=ev,
                    found=False,
                    relevance_score=0.0,
                    llm_reasoning="文件範疇不涵蓋此條款（預篩選排除）",
                ).to_dict()
                for ev in row.expected_evidence
            ]

        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_1_filter",
                "doc_id": doc_id,
                "total_clauses": len(rows),
                "scan_clauses": len(scan_rows),
                "skipped_clauses": len(skipped_rows),
                "skipped_ids": [r.clause_id for r in skipped_rows],
            },
        )

        if not scan_rows:
            # All clauses filtered out — mark phase complete with zero findings
            phase_result.status = PhaseStatus.COMPLETED.value
            phase_result.output = {
                "doc_id": doc_id,
                "clause_count": 0,
                "total_found": 0,
                "total_not_found": sum(len(r.expected_evidence) for r in rows),
                "total_inadequate": 0,
                "note": "全部條款均被預篩選排除",
            }
            phase_result.completed_at = time.time()
            return phase_result

        # Build clauses section (only relevant clauses)
        clauses_parts = []
        for i, row in enumerate(scan_rows, 1):
            evidence_lines = []
            for j, ev in enumerate(row.expected_evidence, 1):
                evidence_lines.append(f"   {j}. {ev}")
            ev_text = "\n".join(evidence_lines)
            clauses_parts.append(
                f"{i}. **{row.clause_id}** — {row.clause_title}\n"
                f"   稽核問題: {row.audit_question}\n"
                f"   待搜尋證據:\n{ev_text}"
            )
        clauses_section = "\n\n".join(clauses_parts)

        user_prompt = _DOC_USER_PROMPT_TEMPLATE.format(
            clause_count=len(scan_rows),
            clauses_section=clauses_section,
            doc_id=doc_id,
            doc_title=doc_title,
            doc_content=final_content,
        )

        messages = [
            {"role": "system", "content": _DOC_SYSTEM_PROMPT},
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
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_1_start",
                "phase": "gap_scan",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in scan_rows],
                "clause_count": len(scan_rows),
                "prompt_preview": user_prompt[:500],
            },
        )

        # Call LLM with retry for rate limit / transient errors
        response = None
        last_error = ""
        _retry_waits = [60, 90, 120]  # seconds to wait on rate limit
        for _attempt, _wait in enumerate([0] + _retry_waits):
            if _wait:
                time.sleep(_wait)
            response = llm_completion_fn(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            _rt = response.get("content", "")
            if _rt and not _rt.startswith("[ERROR]") and not response.get("all_failed"):
                break
            last_error = _rt[:300] if _rt else "LLM 回應為空"
            is_rate_limit = "rate_limit" in last_error.lower() or "429" in last_error
            if not is_rate_limit:
                break  # non-rate-limit error — no point retrying

        response_text = response.get("content", "") if response else ""
        usage = response.get("usage", {}) if response else {}
        llm_model = response.get("model", model) if response else model

        # 檢測 LLM 錯誤回應
        if (
            not response_text
            or response_text.startswith("[ERROR]")
            or (response and response.get("all_failed"))
        ):
            error_detail = last_error or (response_text[:200] if response_text else "LLM 回應為空")
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = f"LLM 呼叫失敗: {error_detail}"
            phase_result.completed_at = time.time()
            _emit_pipeline_event(
                run_id,
                {
                    "type": "phase_1_error",
                    "phase": "gap_scan",
                    "doc_id": doc_id,
                    "error": f"LLM 呼叫失敗: {error_detail}",
                },
            )
            return phase_result

        # Track budget
        budget.record_usage(usage)
        state.update_budget(budget)

        # Parse per-clause results (only scan_rows were sent to LLM)
        clause_evidence = _parse_doc_gap_scan_response(response_text, scan_rows)

        # Distribute results back to scanned rows
        total_found = 0
        total_not_found = 0
        total_inadequate = 0
        for row in scan_rows:
            items = clause_evidence.get(row.clause_id, [])
            row.evidence_items = [item.to_dict() for item in items]
            total_found += sum(1 for e in items if e.found)
            total_not_found += sum(1 for e in items if not e.found)
            total_inadequate += sum(1 for e in items if e.is_inadequate)

        # Count skipped rows as not-found in totals
        total_not_found += sum(len(r.expected_evidence) for r in skipped_rows)

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = {
            "doc_id": doc_id,
            "clause_count": len(rows),
            "scan_clause_count": len(scan_rows),
            "skipped_clause_count": len(skipped_rows),
            "total_found": total_found,
            "total_not_found": total_not_found,
            "total_inadequate": total_inadequate,
            "raw_response_length": len(response_text),
        }
        phase_result.llm_usage = usage
        phase_result.llm_model = llm_model

        # SSE: emit after LLM call
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_1_result",
                "phase": "gap_scan",
                "doc_id": doc_id,
                "doc_title": doc_title,
                "clause_ids": [r.clause_id for r in scan_rows],
                "llm_response": response_text[:2000],
                "evidence_summary": {
                    "found": total_found,
                    "not_found": total_not_found,
                    "inadequate": total_inadequate,
                },
                "usage": usage,
            },
        )

        # SSE: conversation-style event for human-readable display
        _clause_details = []
        for row in scan_rows:
            items = clause_evidence.get(row.clause_id, [])
            _clause_details.append(
                {
                    "clause_id": row.clause_id,
                    "found": sum(1 for e in items if e.found),
                    "not_found": sum(1 for e in items if not e.found),
                    "inadequate": sum(1 for e in items if e.is_inadequate),
                }
            )
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_1_conversation",
                "doc_id": doc_id,
                "clause_ids": [r.clause_id for r in scan_rows],
                "question_summary": (
                    f"請在文件「{doc_title}」({doc_id}) 中搜尋 {len(scan_rows)} 個相關 ISO 13485 條款"
                    f"的合規證據（共 {len(rows)} 條款，{len(skipped_rows)} 條預篩選排除）。"
                ),
                "answer_summary": (
                    f"文件掃描完成：掃描 {len(scan_rows)} 條款，"
                    f"找到 {total_found} 項 ✅、未找到 {total_not_found} 項 ❌"
                    + (f"、不充分 {total_inadequate} 項 ⚠️" if total_inadequate else "")
                    + f"（{len(skipped_rows)} 條款範疇外，略過）。"
                ),
                "details": {"clauses": _clause_details},
            },
        )

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(
            run_id,
            {
                "type": "phase_1_error",
                "phase": "gap_scan",
                "doc_id": doc_id,
                "error": str(e)[:500],
            },
        )

    phase_result.completed_at = time.time()
    return phase_result
