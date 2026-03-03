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
    "MAX_VERIFICATION_ROUNDS",
    "emit_verification_event",
]

MAX_VERIFICATION_ROUNDS = 3


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

_ANALYZER_SYSTEM_PROMPT = """你是品質管理系統「分析者」角色。你在差距分析中已對品質文件進行評估。

你的任務：
1. 根據已找到的證據，說明為何你認為當前的合規判定是正確的。
2. 當驗證者質疑時，你必須用具體的證據引用來回應。
3. 如果驗證者的質疑有道理，你必須誠實承認可能的判定錯誤。
4. 回答使用指定的 JSON 格式。"""

_ANALYZER_INITIAL_TEMPLATE = """## 你的評估摘要

**法規條款**: {clause_id} — {clause_title}
**稽核問題**: {audit_question}
**當前判定**: {current_verdict}
**差距類型**: {gap_severity}

### 證據項目
{evidence_summary}

請以 JSON 格式說明你的評估立場：

```json
{{
  "position": "支持當前判定的完整論述",
  "key_evidence": ["關鍵證據引用1", "關鍵證據引用2"],
  "confidence": 0.0-1.0,
  "acknowledged_weaknesses": ["已知的弱點（如有）"]
}}
```"""

_ANALYZER_RESPONSE_TEMPLATE = """## 驗證者的質疑

{verifier_challenge}

請針對以上質疑進行回應，使用 JSON 格式：

```json
{{
  "response": "針對質疑的回應",
  "additional_evidence": ["補充證據（如有）"],
  "concession": "承認質疑有理的部分（如有）",
  "revised_confidence": 0.0-1.0
}}
```"""


# ============================================================
# Verifier role — challenges the assessment
# ============================================================

_VERIFIER_SYSTEM_PROMPT = """你是品質管理系統「驗證者」角色。你的任務是從法規合規的角度質疑分析者的評估。

你的職責：
1. 檢查分析者是否遺漏了重要的法規要求。
2. 質疑證據引用是否真正涵蓋了稽核問題的所有面向。
3. 指出「提到」vs「具體說明如何執行」的差異。
4. 如果有多國法規要求，特別注意各國「獨有要求」(delta items)。
5. 如果分析者的評估確實合理且有充足證據，你應當同意。
6. 不要為了質疑而質疑 — 只提出有實質意義的挑戰。
7. 回答使用指定的 JSON 格式。"""

_VERIFIER_CHALLENGE_TEMPLATE = """## 分析者的評估

{analyzer_position}

## 法規原文參考

{regulation_text}

## 稽核問題

{audit_question}

請以 JSON 格式提出你的驗證意見：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "challenges": [
    {{
      "point": "質疑要點",
      "regulation_basis": "法規依據",
      "expected_evidence": "你認為應該有的證據"
    }}
  ],
  "overall_assessment": "整體評語"
}}
```"""

_VERIFIER_FOLLOWUP_TEMPLATE = """## 分析者的回應

{analyzer_response}

## 前一輪你的質疑

{previous_challenge}

請根據分析者的回應更新你的評估，使用 JSON 格式：

```json
{{
  "agreement_level": "agree" | "partial_agree" | "disagree",
  "remaining_concerns": ["仍未解決的疑慮"],
  "resolved_concerns": ["已被合理回應的疑慮"],
  "overall_assessment": "更新後的整體評語"
}}
```"""


# ============================================================
# Helper functions
# ============================================================


def _build_evidence_summary(evidence_items: list[EvidenceItem]) -> str:
    """Build a summary of evidence for the analyzer."""
    parts = []
    for i, item in enumerate(evidence_items, 1):
        status = "✅ 找到" if item.found else "❌ 未找到"
        if item.is_inadequate:
            status = "⚠️ 不充分"
        if item.is_outdated:
            status = "📅 版本過期"

        line = f"{i}. [{status}] {item.evidence_name}"
        if item.source_quote:
            quote = item.source_quote[:100] + (
                "..." if len(item.source_quote) > 100 else ""
            )
            line += f"\n   引用: 「{quote}」"
        if item.llm_reasoning:
            line += f"\n   原因: {item.llm_reasoning}"
        parts.append(line)

    return "\n".join(parts) if parts else "（無證據項目）"


def _get_regulation_text(clause_id: str, standard: str) -> str:
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
                    clause_pattern = re.compile(
                        rf"(?:^|\n)(?:#+\s*)?{re.escape(clause_id)}[\s.、]",
                        re.MULTILINE,
                    )
                    match = clause_pattern.search(content)
                    if match:
                        start = max(0, match.start() - 50)
                        end = min(len(content), match.end() + 800)
                        return content[start:end]

        return "（系統中無此法規條文原文）"
    except Exception:
        return "（無法取得法規條文）"


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
    max_tokens: int = 4096,
    selected_regulations: list[str] | None = None,
    run_id: str = "",
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
        temperature: LLM temperature
        max_tokens: Max response tokens
        selected_regulations: Country regulation IDs (e.g., ['QMSR', 'EU_MDR', 'TFDA'])
        run_id: Pipeline run ID for SSE event emission

    Returns:
        PhaseResult with verification rounds and agreement status
    """
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

        evidence_summary = _build_evidence_summary(evidence_items)
        regulation_text = _get_regulation_text(row_state.clause_id, row_state.standard)

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
                delta_items = [q for q in reg_questions if q["question_type"] == "delta"]
                exceeds_items = [q for q in reg_questions if q["question_type"] == "exceeds"]
                if delta_items or exceeds_items:
                    parts = ["## 多國法規特殊要求（需額外驗證）\n"]
                    for q in delta_items:
                        parts.append(
                            f"⚠️ [{q['country']}] {q['title_zh']}: {q['question_zh']}"
                        )
                    for q in exceeds_items:
                        parts.append(
                            f"📋 [{q['country']}] {q['title_zh']}: {q['question_zh']}"
                        )
                    multi_reg_context = "\n".join(parts)
            except Exception:
                pass  # Non-critical — proceed without multi-reg context

        # Import verdict display
        from src.analysis.risk_matrix import VERDICT_DISPLAY

        verdict_info = VERDICT_DISPLAY.get(row_state.verdict or "", {})
        verdict_label = verdict_info.get("label_zh", row_state.verdict or "未判定")

        rounds: list[dict] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        agreed = False

        # Emit SSE: verification start
        if run_id:
            emit_verification_event(run_id, {
                "type": "verification_start",
                "clause_id": row_state.clause_id,
                "clause_title": row_state.clause_title,
                "doc_id": row_state.doc_id or "",
                "selected_regulations": selected_regulations or [],
                "has_multi_reg_context": bool(multi_reg_context),
            })

        # ---- Round 1: Analyzer initial position ----
        analyzer_prompt = _ANALYZER_INITIAL_TEMPLATE.format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            current_verdict=verdict_label,
            gap_severity=row_state.gap_severity or "未評估",
            evidence_summary=evidence_summary,
        )

        # Emit SSE: round start
        if run_id:
            emit_verification_event(run_id, {
                "type": "round_start",
                "round": 1,
                "clause_id": row_state.clause_id,
            })

        analyzer_response, usage = _call_llm(
            llm_completion_fn,
            _ANALYZER_SYSTEM_PROMPT,
            analyzer_prompt,
            state,
            model,
            temperature,
            max_tokens,
        )
        _merge_usage(total_usage, usage)

        # Emit SSE: analyzer response
        if run_id:
            emit_verification_event(run_id, {
                "type": "analyzer",
                "round": 1,
                "clause_id": row_state.clause_id,
                "content": json.dumps(analyzer_response, ensure_ascii=False),
            })

        # Verifier challenges — append multi-regulation context if available
        verifier_prompt = _VERIFIER_CHALLENGE_TEMPLATE.format(
            analyzer_position=json.dumps(
                analyzer_response, ensure_ascii=False, indent=2
            ),
            regulation_text=regulation_text,
            audit_question=row_state.audit_question,
        )
        if multi_reg_context:
            verifier_prompt += f"\n\n{multi_reg_context}"

        verifier_response, usage = _call_llm(
            llm_completion_fn,
            _VERIFIER_SYSTEM_PROMPT,
            verifier_prompt,
            state,
            model,
            temperature,
            max_tokens,
        )
        _merge_usage(total_usage, usage)

        # Emit SSE: verifier response
        if run_id:
            emit_verification_event(run_id, {
                "type": "verifier",
                "round": 1,
                "clause_id": row_state.clause_id,
                "content": json.dumps(verifier_response, ensure_ascii=False),
            })

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
            emit_verification_event(run_id, {
                "type": "round_end",
                "round": 1,
                "clause_id": row_state.clause_id,
                "agreement_level": agreement,
                "agreed": agreed,
            })

        # ---- Rounds 2-3: Follow-up if not agreed ----
        for round_num in range(2, MAX_VERIFICATION_ROUNDS + 1):
            if agreed:
                break

            # Emit SSE: round start
            if run_id:
                emit_verification_event(run_id, {
                    "type": "round_start",
                    "round": round_num,
                    "clause_id": row_state.clause_id,
                })

            # Analyzer responds to verifier's challenge
            analyzer_followup = _ANALYZER_RESPONSE_TEMPLATE.format(
                verifier_challenge=json.dumps(
                    verifier_response, ensure_ascii=False, indent=2
                ),
            )

            analyzer_response, usage = _call_llm(
                llm_completion_fn,
                _ANALYZER_SYSTEM_PROMPT,
                analyzer_followup,
                state,
                model,
                temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            # Emit SSE: analyzer response
            if run_id:
                emit_verification_event(run_id, {
                    "type": "analyzer",
                    "round": round_num,
                    "clause_id": row_state.clause_id,
                    "content": json.dumps(analyzer_response, ensure_ascii=False),
                })

            # Verifier re-evaluates
            verifier_followup = _VERIFIER_FOLLOWUP_TEMPLATE.format(
                analyzer_response=json.dumps(
                    analyzer_response, ensure_ascii=False, indent=2
                ),
                previous_challenge=json.dumps(
                    verifier_response, ensure_ascii=False, indent=2
                ),
            )

            verifier_response, usage = _call_llm(
                llm_completion_fn,
                _VERIFIER_SYSTEM_PROMPT,
                verifier_followup,
                state,
                model,
                temperature,
                max_tokens,
            )
            _merge_usage(total_usage, usage)

            # Emit SSE: verifier response
            if run_id:
                emit_verification_event(run_id, {
                    "type": "verifier",
                    "round": round_num,
                    "clause_id": row_state.clause_id,
                    "content": json.dumps(verifier_response, ensure_ascii=False),
                })

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
                emit_verification_event(run_id, {
                    "type": "round_end",
                    "round": round_num,
                    "clause_id": row_state.clause_id,
                    "agreement_level": agreement,
                    "agreed": agreed,
                })
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
            emit_verification_event(run_id, {
                "type": "verification_complete",
                "clause_id": row_state.clause_id,
                "total_rounds": len(rounds),
                "agreed": agreed,
                "flagged_for_ra": not agreed,
                "final_agreement_level": agreement,
            })

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
    max_tokens: int = 8192,
    selected_regulations: list[str] | None = None,
    run_id: str = "",
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
        temperature: LLM temperature
        max_tokens: Max tokens per LLM call
        selected_regulations: Country regulation IDs
        run_id: Pipeline run ID for SSE emission

    Returns:
        PhaseResult with aggregated verification results
    """
    phase_result = PhaseResult(
        phase=Phase.VERIFICATION.value,
        started_at=time.time(),
    )

    try:
        rows_with_evidence = [
            r for r in rows if r.evidence_items
        ]

        if not rows_with_evidence:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": "No evidence items to verify"}
            phase_result.completed_at = time.time()
            return phase_result

        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        total_agreed = 0
        total_flagged = 0
        doc_title = rows[0].doc_title if rows else doc_id

        # SSE: document-level start
        _emit_pipeline_event(run_id, {
            "type": "phase_5_start",
            "phase": "verification",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "clause_ids": [r.clause_id for r in rows_with_evidence],
            "clause_count": len(rows_with_evidence),
            "selected_regulations": selected_regulations or [],
        })

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
            evidence_summary = _build_evidence_summary(evidence_items)
            regulation_text = _get_regulation_text(row.clause_id, row.standard)

            # Multi-regulation context
            multi_reg_context = ""
            if selected_regulations:
                try:
                    from src.analysis.compliance_rules import generate_cross_exam_questions
                    reg_questions = generate_cross_exam_questions(
                        doc_id=row.doc_id or "",
                        doc_title=row.doc_title or "",
                        baseline_clause=row.clause_id,
                        selected_regulations=selected_regulations,
                    )
                    delta_items = [q for q in reg_questions if q["question_type"] == "delta"]
                    exceeds_items = [q for q in reg_questions if q["question_type"] == "exceeds"]
                    if delta_items or exceeds_items:
                        parts = ["## 多國法規特殊要求（需額外驗證）\n"]
                        for q in delta_items:
                            parts.append(
                                f"⚠️ [{q['country']}] {q['title_zh']}: {q['question_zh']}"
                            )
                        for q in exceeds_items:
                            parts.append(
                                f"📋 [{q['country']}] {q['title_zh']}: {q['question_zh']}"
                            )
                        multi_reg_context = "\n".join(parts)
                except Exception:
                    pass

            from src.analysis.risk_matrix import VERDICT_DISPLAY
            verdict_info = VERDICT_DISPLAY.get(row.verdict or "", {})
            verdict_label = verdict_info.get("label_zh", row.verdict or "未判定")

            rounds: list[dict] = []
            agreed = False

            # Emit SSE: verification start for this clause
            if run_id:
                emit_verification_event(run_id, {
                    "type": "verification_start",
                    "clause_id": row.clause_id,
                    "clause_title": row.clause_title,
                    "doc_id": doc_id,
                    "selected_regulations": selected_regulations or [],
                    "has_multi_reg_context": bool(multi_reg_context),
                })

            # Round 1: Analyzer initial position
            analyzer_prompt = _ANALYZER_INITIAL_TEMPLATE.format(
                clause_id=row.clause_id,
                clause_title=row.clause_title,
                audit_question=row.audit_question,
                current_verdict=verdict_label,
                gap_severity=row.gap_severity or "未評估",
                evidence_summary=evidence_summary,
            )

            if run_id:
                emit_verification_event(run_id, {
                    "type": "round_start",
                    "round": 1,
                    "clause_id": row.clause_id,
                })

            analyzer_response, usage = _call_llm(
                llm_completion_fn, _ANALYZER_SYSTEM_PROMPT, analyzer_prompt,
                state, model, temperature, max_tokens,
            )
            _merge_usage(total_usage, usage)

            if run_id:
                emit_verification_event(run_id, {
                    "type": "analyzer",
                    "round": 1,
                    "clause_id": row.clause_id,
                    "content": json.dumps(analyzer_response, ensure_ascii=False),
                })

            # Verifier challenges
            verifier_prompt = _VERIFIER_CHALLENGE_TEMPLATE.format(
                analyzer_position=json.dumps(
                    analyzer_response, ensure_ascii=False, indent=2
                ),
                regulation_text=regulation_text,
                audit_question=row.audit_question,
            )
            if multi_reg_context:
                verifier_prompt += f"\n\n{multi_reg_context}"

            verifier_response, usage = _call_llm(
                llm_completion_fn, _VERIFIER_SYSTEM_PROMPT, verifier_prompt,
                state, model, temperature, max_tokens,
            )
            _merge_usage(total_usage, usage)

            if run_id:
                emit_verification_event(run_id, {
                    "type": "verifier",
                    "round": 1,
                    "clause_id": row.clause_id,
                    "content": json.dumps(verifier_response, ensure_ascii=False),
                })

            rounds.append({
                "round": 1,
                "analyzer": analyzer_response,
                "verifier": verifier_response,
            })

            agreement = verifier_response.get("agreement_level", "")
            if agreement == "agree":
                agreed = True

            if run_id:
                emit_verification_event(run_id, {
                    "type": "round_end",
                    "round": 1,
                    "clause_id": row.clause_id,
                    "agreement_level": agreement,
                    "agreed": agreed,
                })

            # Rounds 2-3
            for round_num in range(2, MAX_VERIFICATION_ROUNDS + 1):
                if agreed:
                    break

                budget = state.get_budget()
                if budget.exceeded:
                    break

                if run_id:
                    emit_verification_event(run_id, {
                        "type": "round_start",
                        "round": round_num,
                        "clause_id": row.clause_id,
                    })

                analyzer_followup = _ANALYZER_RESPONSE_TEMPLATE.format(
                    verifier_challenge=json.dumps(
                        verifier_response, ensure_ascii=False, indent=2
                    ),
                )

                analyzer_response, usage = _call_llm(
                    llm_completion_fn, _ANALYZER_SYSTEM_PROMPT, analyzer_followup,
                    state, model, temperature, max_tokens,
                )
                _merge_usage(total_usage, usage)

                if run_id:
                    emit_verification_event(run_id, {
                        "type": "analyzer",
                        "round": round_num,
                        "clause_id": row.clause_id,
                        "content": json.dumps(analyzer_response, ensure_ascii=False),
                    })

                verifier_followup = _VERIFIER_FOLLOWUP_TEMPLATE.format(
                    analyzer_response=json.dumps(
                        analyzer_response, ensure_ascii=False, indent=2
                    ),
                    previous_challenge=json.dumps(
                        verifier_response, ensure_ascii=False, indent=2
                    ),
                )

                verifier_response, usage = _call_llm(
                    llm_completion_fn, _VERIFIER_SYSTEM_PROMPT, verifier_followup,
                    state, model, temperature, max_tokens,
                )
                _merge_usage(total_usage, usage)

                if run_id:
                    emit_verification_event(run_id, {
                        "type": "verifier",
                        "round": round_num,
                        "clause_id": row.clause_id,
                        "content": json.dumps(verifier_response, ensure_ascii=False),
                    })

                rounds.append({
                    "round": round_num,
                    "analyzer": analyzer_response,
                    "verifier": verifier_response,
                })

                agreement = verifier_response.get("agreement_level", "")
                if agreement == "agree":
                    agreed = True

                if run_id:
                    emit_verification_event(run_id, {
                        "type": "round_end",
                        "round": round_num,
                        "clause_id": row.clause_id,
                        "agreement_level": agreement,
                        "agreed": agreed,
                    })

            # Store results for this row
            row.verification_rounds = rounds
            row.verification_agreed = agreed
            row.flagged_for_ra = not agreed

            if agreed:
                total_agreed += 1
            else:
                total_flagged += 1

            if run_id:
                emit_verification_event(run_id, {
                    "type": "verification_complete",
                    "clause_id": row.clause_id,
                    "total_rounds": len(rounds),
                    "agreed": agreed,
                    "flagged_for_ra": not agreed,
                    "final_agreement_level": agreement,
                })

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
        _emit_pipeline_event(run_id, {
            "type": "phase_5_result",
            "phase": "verification",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "clause_ids": [r.clause_id for r in rows_with_evidence],
            "total_agreed": total_agreed,
            "total_flagged": total_flagged,
            "usage": total_usage,
        })

    except RuntimeError as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(run_id, {
            "type": "phase_5_error",
            "phase": "verification",
            "doc_id": doc_id,
            "error": str(e)[:500],
        })

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)
        _emit_pipeline_event(run_id, {
            "type": "phase_5_error",
            "phase": "verification",
            "doc_id": doc_id,
            "error": str(e)[:500],
        })

    phase_result.completed_at = time.time()
    return phase_result
