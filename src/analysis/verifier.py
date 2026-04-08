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
        temperature: Analyzer LLM temperature (default 0.2 for creative reasoning)
        verifier_temperature: Verifier LLM temperature (default 0.0 for deterministic challenges)
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
                delta_items = [
                    q for q in reg_questions if q["question_type"] == "delta"
                ]
                exceeds_items = [
                    q for q in reg_questions if q["question_type"] == "exceeds"
                ]
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
                    "\n\n## Human RA Intervention\n"
                    + "\n".join(f"- {msg}" for msg in injected)
                    + "\n\n請在你的分析中考慮以上人工介入的意見。\n"
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

        analyzer_prompt = _ANALYZER_INITIAL_TEMPLATE.format(
            clause_id=row_state.clause_id,
            clause_title=row_state.clause_title,
            audit_question=row_state.audit_question,
            current_verdict=verdict_label,
            gap_severity=row_state.gap_severity or "未評估",
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
        verifier_prompt = _VERIFIER_CHALLENGE_TEMPLATE.format(
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
            _VERIFIER_SYSTEM_PROMPT,
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
                        "\n\n## Human RA Intervention\n"
                        + "\n".join(f"- {msg}" for msg in injected)
                        + "\n\n請在你的分析中考慮以上人工介入的意見。\n"
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
            analyzer_followup = _ANALYZER_RESPONSE_TEMPLATE.format(
                verifier_challenge=json.dumps(
                    verifier_response, ensure_ascii=False, indent=2
                ),
            )
            if round_injection_block:
                analyzer_followup += round_injection_block

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
            verifier_followup = _VERIFIER_FOLLOWUP_TEMPLATE.format(
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
                _VERIFIER_SYSTEM_PROMPT,
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
    phase_result = PhaseResult(
        phase=Phase.VERIFICATION.value,
        started_at=time.time(),
    )

    try:
        rows_with_evidence = [r for r in rows if r.evidence_items]

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
            evidence_summary = _build_evidence_summary(evidence_items)
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
            analyzer_prompt = _ANALYZER_INITIAL_TEMPLATE.format(
                clause_id=row.clause_id,
                clause_title=row.clause_title,
                audit_question=row.audit_question,
                current_verdict=verdict_label,
                gap_severity=row.gap_severity or "未評估",
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
                _ANALYZER_SYSTEM_PROMPT,
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
                llm_completion_fn,
                _VERIFIER_SYSTEM_PROMPT,
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

_QA_AUDITOR_SYSTEM_PROMPT = """你是品質管理系統的「第三方交叉詰問品質稽核員」。你的任務是獨立審查分析者（Analyzer）和驗證者（Verifier）之間的對話紀錄，判斷對話品質。

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
}"""

_QA_AUDITOR_USER_TEMPLATE = """## 第三方品質稽核任務

請審查以下 {clause_count} 筆交叉詰問對話紀錄：

**文件**: {doc_id} — {doc_title}
**涉及法規**: {regulations}

### 對話紀錄

{debate_transcripts}

請對每一筆對話給出品質評分和具體問題。"""


def _build_debate_transcript(
    clause_id: str,
    clause_title: str,
    audit_question: str,
    verdict: str,
    rounds: list[dict],
    agreed: bool,
) -> str:
    parts = [
        f"--- 條款 {clause_id}: {clause_title} ---",
        f"稽核問題: {audit_question}",
        f"判定結果: {verdict}",
        f"最終結論: {'同意' if agreed else '不同意（標記 RA 覆審）'}",
        "",
    ]
    for rd in rounds:
        round_num = rd.get("round", "?")
        analyzer = rd.get("analyzer", {})
        verifier = rd.get("verifier", {})

        a_position = str(analyzer.get("position", analyzer.get("response", "")))[:400]
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
        v_assessment = verifier.get("overall_assessment", "")[:300]

        parts.append(f"  輪次 {round_num}:")
        parts.append(f"    分析者: confidence={a_confidence}")
        parts.append(f"    立場: {a_position}")
        if a_evidence:
            parts.append(f"    證據: {', '.join(str(e)[:80] for e in a_evidence[:3])}")
        parts.append(f"    驗證者: agreement={v_agreement}")
        if isinstance(v_challenges, list) and v_challenges:
            for ch in v_challenges[:2]:
                if isinstance(ch, dict):
                    parts.append(f"    質疑: {ch.get('point', str(ch))[:150]}")
                else:
                    parts.append(f"    質疑: {str(ch)[:150]}")
        if v_assessment:
            parts.append(f"    評語: {v_assessment}")
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
) -> dict:
    from src.analysis.risk_matrix import VERDICT_DISPLAY

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
        verdict_label = verdict_info.get("label_zh", row.verdict or "未判定")
        transcript = _build_debate_transcript(
            clause_id=row.clause_id,
            clause_title=row.clause_title,
            audit_question=row.audit_question,
            verdict=verdict_label,
            rounds=row.verification_rounds,
            agreed=row.verification_agreed or False,
        )
        transcripts.append(transcript)

    combined_transcripts = "\n\n".join(transcripts)
    if len(combined_transcripts) > 12000:
        combined_transcripts = combined_transcripts[:12000] + "\n\n...（已截斷）"

    doc_title = rows[0].doc_title if rows else doc_id
    regulations_str = (
        ", ".join(selected_regulations) if selected_regulations else "ISO 13485"
    )

    user_prompt = _QA_AUDITOR_USER_TEMPLATE.format(
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
            _QA_AUDITOR_SYSTEM_PROMPT,
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
