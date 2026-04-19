"""
AI-QMS — Pipeline Runner (Async Bridge)
=========================================

Bridges the synchronous AnalysisPipeline with async Chainlit UI.
Provides progress updates via Chainlit messages and integrates
with Phoenix observability.

Usage in app.py:
    from src.analysis.pipeline_runner import run_pipeline_analysis

    pipeline_result = await run_pipeline_analysis(
        scan_result=scan_result,
        llm_completion_fn=manager.completion,
        model=model_name,
        source_command="regulatory_list",
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from src.analysis.state import (
    Phase,
    PhaseStatus,
    ExecutionMode,
    PauseReason,
    PipelineState,
    PHASE_ORDER,
)
from src.analysis.pipeline import AnalysisPipeline
from src.analysis.comparison_table import ComparisonTable
from src.analysis.risk_matrix import (
    RISK_LEVEL_DISPLAY,
    VERDICT_DISPLAY,
    Verdict,
)


logger = logging.getLogger(__name__)


__all__ = [
    "run_pipeline_analysis",
    "PipelineRunResult",
    "_pipeline_send_message_fn",
]


# ============================================================
# i18n strings for pipeline runner (progress + summary)
# ============================================================

_PIPELINE_I18N: dict[str, dict[str, str]] = {
    "zh-TW": {
        # to_summary_markdown
        "pipeline_failed": "分析管線執行失敗",
        "unknown_error": "未知錯誤",
        "pipeline_title": "📊 合規性分析管線結果",
        "analysis_id": "分析 ID",
        "total_items": "總分析項目",
        "completed_items": "完成項目",
        "duration": "耗時",
        "items_suffix": "項",
        "seconds": "秒",
        "verdicts_heading": "### 判定結果分布",
        "no_verdicts": "- （尚無判定結果）",
        "risk_heading": "### 風險等級分布",
        "no_risk": "- （尚無風險評估）",
        "ra_review_heading": "### ⚠️ 需 RA 審查",
        "ra_review_note": "（交叉詰問 3 輪後仍有分歧，已標記待人工審查）",
        "llm_usage_heading": "### 📈 LLM Token 用量",
        "total_usage": "總用量",
        "calls_made": "呼叫次數",
        "calls_suffix": "次",
        # progress messages
        "phase_running": "執行中...",
        "phase_done": "✅ 完成",
        "phase_skipped": "⏭️ 跳過",
        "phase_failed": "❌ 失敗",
        "skip_not_in_mode": "當前模式不執行此階段",
        "budget_exhausted": "Token 預算已用盡",
        "rows_available_suffix": "項資料可用",
        "evidence_done_suffix": "項完成證據搜尋",
        "ra_review_detail_suffix": "項需 RA 審查",
        "ra_review_all_pass": "所有項目驗證通過",
        "source_check_detail": "{accessible} 可存取 / {broken} 失效",
        "initializing": "初始化分析管線...",
        "created_rows": "已建立 {n} 個分析項目",
        "no_items_error": "無可分析的項目（未找到引用法規標準的品質文件）",
        "critical_gaps_pause": "🔴 發現嚴重差距，管線已暫停",
        "evidence_conflict_pause": "⚠️ 交叉驗證有分歧，管線已暫停",
        "gap_scan_doc_progress": "執行中... — {done}/{total} 份文件 [{pct}%]",
    },
    "en-US": {
        "pipeline_failed": "Pipeline analysis failed",
        "unknown_error": "Unknown error",
        "pipeline_title": "📊 Compliance Analysis Pipeline Results",
        "analysis_id": "Analysis ID",
        "total_items": "Total items",
        "completed_items": "Completed items",
        "duration": "Duration",
        "items_suffix": "items",
        "seconds": "seconds",
        "verdicts_heading": "### Verdict Distribution",
        "no_verdicts": "- (No verdict results yet)",
        "risk_heading": "### Risk Level Distribution",
        "no_risk": "- (No risk assessment yet)",
        "ra_review_heading": "### ⚠️ Require RA Review",
        "ra_review_note": "(Disagreement persisted after 3 cross-examination rounds — flagged for manual review)",
        "llm_usage_heading": "### 📈 LLM Token Usage",
        "total_usage": "Total usage",
        "calls_made": "Calls made",
        "calls_suffix": "calls",
        "phase_running": "running...",
        "phase_done": "✅ complete",
        "phase_skipped": "⏭️ skipped",
        "phase_failed": "❌ failed",
        "skip_not_in_mode": "Skipped in current mode",
        "budget_exhausted": "Token budget exhausted",
        "rows_available_suffix": "items available",
        "evidence_done_suffix": "evidence searches complete",
        "ra_review_detail_suffix": "items require RA review",
        "ra_review_all_pass": "All items verified",
        "source_check_detail": "{accessible} accessible / {broken} broken",
        "initializing": "Initializing analysis pipeline...",
        "created_rows": "Created {n} analysis items",
        "no_items_error": "No items to analyze (no QMS documents referencing the regulatory standard were found)",
        "critical_gaps_pause": "🔴 Critical gaps detected — pipeline paused",
        "evidence_conflict_pause": "⚠️ Cross-verification disagreement — pipeline paused",
        "gap_scan_doc_progress": "running... — {done}/{total} docs [{pct}%]",
    },
    "ja-JP": {
        "pipeline_failed": "分析パイプラインの実行に失敗しました",
        "unknown_error": "不明なエラー",
        "pipeline_title": "📊 コンプライアンス分析パイプライン結果",
        "analysis_id": "分析 ID",
        "total_items": "総分析項目",
        "completed_items": "完了項目",
        "duration": "所要時間",
        "items_suffix": "件",
        "seconds": "秒",
        "verdicts_heading": "### 判定結果の分布",
        "no_verdicts": "- （判定結果はまだありません）",
        "risk_heading": "### リスクレベルの分布",
        "no_risk": "- （リスク評価はまだありません）",
        "ra_review_heading": "### ⚠️ RA レビューが必要",
        "ra_review_note": "（交差尋問を3ラウンド行っても合意に至らず、手動レビュー対象としてフラグ設定）",
        "llm_usage_heading": "### 📈 LLM トークン使用量",
        "total_usage": "総使用量",
        "calls_made": "呼び出し回数",
        "calls_suffix": "回",
        "phase_running": "実行中...",
        "phase_done": "✅ 完了",
        "phase_skipped": "⏭️ スキップ",
        "phase_failed": "❌ 失敗",
        "skip_not_in_mode": "現在のモードではこのフェーズを実行しません",
        "budget_exhausted": "トークン予算を使い切りました",
        "rows_available_suffix": "件のデータが利用可能",
        "evidence_done_suffix": "件の証拠検索が完了",
        "ra_review_detail_suffix": "件 RA レビューが必要",
        "ra_review_all_pass": "すべての項目が検証済み",
        "source_check_detail": "{accessible} 件アクセス可能 / {broken} 件リンク切れ",
        "initializing": "分析パイプラインを初期化中...",
        "created_rows": "{n} 件の分析項目を作成しました",
        "no_items_error": "分析可能な項目がありません（規制基準を参照している QMS 文書が見つかりません）",
        "critical_gaps_pause": "🔴 重大なギャップを検出 — パイプラインを一時停止",
        "evidence_conflict_pause": "⚠️ 交差検証で意見の相違 — パイプラインを一時停止",
        "gap_scan_doc_progress": "実行中... — {done}/{total} 件のドキュメント [{pct}%]",
    },
}


from src.chainlit_app.lang_config import lang_key as _lang_key_short  # noqa: E402

_PIPELINE_LANG_MAP = {"zh": "zh-TW", "en": "en-US", "ja": "ja-JP"}


def _pipeline_lang_key(lang: str) -> str:
    """Normalize language code to a pipeline i18n dict key.

    Delegates short-form normalization to lang_config.lang_key, then maps
    to the full locale codes used in _PIPELINE_I18N.
    """
    return _PIPELINE_LANG_MAP.get(_lang_key_short(lang), "en-US")


def _t(lang: str, key: str, **fmt) -> str:
    """Look up a localized pipeline string by key, with optional format args."""
    lk = _pipeline_lang_key(lang)
    text = _PIPELINE_I18N.get(lk, _PIPELINE_I18N["en-US"]).get(key)
    if text is None:
        text = _PIPELINE_I18N["en-US"].get(key, key)
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text

# Module-level send function, set by run_pipeline_analysis() when active.
# Used by report_api.py for deviation/meta-review announcements via Chainlit.
_pipeline_send_message_fn: Optional[Callable] = None


# ============================================================
# Result container
# ============================================================


class PipelineRunResult:
    """Result of a pipeline analysis run, ready for report rendering."""

    def __init__(self, lang: str = "zh-TW"):
        self.success: bool = False
        self.run_id: str = ""
        self.state: Optional[PipelineState] = None
        self.table: Optional[ComparisonTable] = None
        self.error: Optional[str] = None
        self.total_rows: int = 0
        self.completed_rows: int = 0
        self.duration_seconds: float = 0.0
        self.state_file_path: Optional[str] = None
        self.lang: str = lang

        # Summary data for the report
        self.verdict_distribution: dict[str, int] = {}
        self.risk_distribution: dict[str, int] = {}
        self.flagged_for_ra: int = 0
        self.llm_budget_used: dict = {}
        self.verification_report: Optional[dict] = None

    def _label_for_display(self, display: dict, fallback: str) -> str:
        """Pick a localized label from a *_DISPLAY dict based on self.lang."""
        lk = _pipeline_lang_key(self.lang)
        if lk == "en-US":
            return display.get("label_en") or display.get("label_zh") or fallback
        if lk == "ja-JP":
            return (
                display.get("label_ja")
                or display.get("label_en")
                or display.get("label_zh")
                or fallback
            )
        return display.get("label_zh") or fallback

    def to_summary_markdown(self) -> str:
        """Generate a summary markdown for inline Chainlit display."""
        lang = self.lang
        if not self.success:
            return (
                f"⚠️ {_t(lang, 'pipeline_failed')}: "
                f"{self.error or _t(lang, 'unknown_error')}"
            )

        items = _t(lang, "items_suffix")
        lines = [
            f"## {_t(lang, 'pipeline_title')}",
            "",
            f"**{_t(lang, 'analysis_id')}**: `{self.run_id}`",
            f"**{_t(lang, 'total_items')}**: {self.total_rows} {items}",
            f"**{_t(lang, 'completed_items')}**: {self.completed_rows} {items}",
            f"**{_t(lang, 'duration')}**: {self.duration_seconds:.1f} {_t(lang, 'seconds')}",
            "",
            _t(lang, "verdicts_heading"),
        ]

        # Verdict distribution
        for verdict, count in self.verdict_distribution.items():
            display = VERDICT_DISPLAY.get(verdict, {})
            icon = display.get("icon", "❓")
            label = self._label_for_display(display, verdict)
            lines.append(f"- {icon} **{label}**: {count} {items}")

        if not self.verdict_distribution:
            lines.append(_t(lang, "no_verdicts"))

        lines.append("")
        lines.append(_t(lang, "risk_heading"))

        # Risk distribution
        for risk, count in self.risk_distribution.items():
            display = RISK_LEVEL_DISPLAY.get(risk, {})
            icon = display.get("icon", "❓")
            label = self._label_for_display(display, risk)
            lines.append(f"- {icon} **{label}**: {count} {items}")

        if not self.risk_distribution:
            lines.append(_t(lang, "no_risk"))

        # Flagged
        if self.flagged_for_ra > 0:
            lines.append("")
            lines.append(
                f"{_t(lang, 'ra_review_heading')}: {self.flagged_for_ra} {items}"
            )
            lines.append(_t(lang, "ra_review_note"))

        # LLM usage
        if self.llm_budget_used:
            lines.append("")
            lines.append(_t(lang, "llm_usage_heading"))
            lines.append(
                f"- {_t(lang, 'total_usage')}: "
                f"{self.llm_budget_used.get('total_tokens_used', 0):,} tokens "
                f"({self.llm_budget_used.get('usage_percent', 0)}%)"
            )
            lines.append(
                f"- {_t(lang, 'calls_made')}: "
                f"{self.llm_budget_used.get('calls_made', 0)} "
                f"{_t(lang, 'calls_suffix')}"
            )

        return "\n".join(lines)


# ============================================================
# Progress messaging
# ============================================================

_PHASE_ICONS = {
    Phase.DATA_QUALITY: "🔍",
    Phase.REFERENCE_MAPPING: "🗺️",
    Phase.GAP_SCAN: "🔎",
    Phase.CHECKLIST_VERIFY: "✅",
    Phase.RISK_ASSESSMENT: "⚖️",
    Phase.REMEDIATION: "🛠️",
    Phase.VERIFICATION: "🔄",
    Phase.SOURCE_CHECK: "🌐",
}


def _phase_display_name(phase: Phase, lang: str) -> str:
    """Return a localized display name for a phase.

    Uses the Phase.display_name attribute as Chinese fallback and provides
    simple English/Japanese equivalents.
    """
    lk = _pipeline_lang_key(lang)
    if lk == "zh-TW":
        return phase.display_name
    names = {
        Phase.DATA_QUALITY: {
            "en-US": "Phase 0: Data Quality Gate",
            "ja-JP": "フェーズ 0: データ品質ゲート",
        },
        Phase.REFERENCE_MAPPING: {
            "en-US": "Phase 0.5: Reference Mapping",
            "ja-JP": "フェーズ 0.5: 参照マッピング",
        },
        Phase.GAP_SCAN: {
            "en-US": "Phase 1: Gap Scan",
            "ja-JP": "フェーズ 1: ギャップスキャン",
        },
        Phase.CHECKLIST_VERIFY: {
            "en-US": "Phase 2: Checklist Verification",
            "ja-JP": "フェーズ 2: チェックリスト検証",
        },
        Phase.RISK_ASSESSMENT: {
            "en-US": "Phase 3: Risk Assessment",
            "ja-JP": "フェーズ 3: リスク評価",
        },
        Phase.REMEDIATION: {
            "en-US": "Phase 4: Remediation Suggestions",
            "ja-JP": "フェーズ 4: 是正提案",
        },
        Phase.VERIFICATION: {
            "en-US": "Phase 5: Cross-Examination",
            "ja-JP": "フェーズ 5: 交差検証",
        },
        Phase.SOURCE_CHECK: {
            "en-US": "Phase 6: Source Verification",
            "ja-JP": "フェーズ 6: ソース検証",
        },
    }
    return names.get(phase, {}).get(lk, phase.display_name)


async def _send_progress(
    msg_fn: Optional[Callable],
    phase: Phase,
    status: str,
    detail: str = "",
    progress_pct: float | None = None,
    lang: str = "zh-TW",
) -> None:
    """Send a progress message via Chainlit (or any async callback)."""
    if msg_fn is None:
        return

    icon = _PHASE_ICONS.get(phase, "📋")
    phase_name = _phase_display_name(phase, lang)
    pct_str = f" [{progress_pct:.0f}%]" if progress_pct is not None else ""

    if status == "start":
        text = f"{icon} **{phase_name}** {_t(lang, 'phase_running')}{pct_str}"
    elif status == "done":
        text = f"{icon} **{phase_name}** {_t(lang, 'phase_done')}{pct_str}"
        if detail:
            text += f" — {detail}"
    elif status == "skip":
        text = f"{icon} **{phase_name}** {_t(lang, 'phase_skipped')}{pct_str}"
        if detail:
            text += f" — {detail}"
    elif status == "fail":
        text = f"{icon} **{phase_name}** {_t(lang, 'phase_failed')}{pct_str}"
        if detail:
            text += f" — {detail}"
    else:
        text = f"{icon} **{phase_name}** {detail}{pct_str}"

    try:
        await asyncio.wait_for(msg_fn(text), timeout=10.0)
    except Exception:
        pass  # Best-effort UI update


# ============================================================
# Main runner
# ============================================================


async def run_pipeline_analysis(
    scan_result: dict,
    llm_completion_fn: Callable,
    model: str = "default",
    mode: ExecutionMode = ExecutionMode.AUTO_RUN,
    standard: str = "ISO_13485",
    max_tokens_budget: int = 10_000_000_000,
    max_time_seconds: int = 86400,
    source_command: str = "regulatory_list",
    send_message_fn: Optional[Callable] = None,
    phoenix_trace_ctx: Optional[Callable] = None,
    selected_regulations: list[str] | None = None,
    on_run_id_ready: Optional[Callable] = None,
    custom_skip_phases: list[str] | None = None,
    lang: str = "zh-TW",
) -> PipelineRunResult:
    """Run the full analysis pipeline with async progress reporting.

    This is the main entry point called from app.py's handle_regulatory_list()
    and handle_regulatory_update_rescan().

    Args:
        scan_result: Output of MarkdownStoreService.scan_regulatory_references()
        llm_completion_fn: LLM completion function (non-streaming)
        model: LLM model name
        mode: Execution mode
        standard: Regulatory standard to analyze
        max_tokens_budget: Max LLM token budget (default: no practical limit)
        max_time_seconds: Max wall-clock seconds for LLM phases (default: 24h)
        source_command: "regulatory_list" or "regulatory_update"
        send_message_fn: Async callback to send Chainlit messages (optional)
        phoenix_trace_ctx: Phoenix trace context manager (optional)
        selected_regulations: Country regulation IDs for multi-regulation cross-exam
                               (e.g., ['QMSR', 'EU_MDR', 'TFDA'])
        on_run_id_ready: Async callback(run_id) called as soon as run_id is available,
                          BEFORE pipeline starts. Used to send report URL early.

    Returns:
        PipelineRunResult with all analysis data
    """
    global _pipeline_send_message_fn

    result = PipelineRunResult(lang=lang)
    start_time = time.time()
    _pipeline_send_message_fn = send_message_fn

    try:
        pipeline = AnalysisPipeline(
            llm_completion_fn=llm_completion_fn,
            model=model,
            mode=mode,
            max_tokens_budget=max_tokens_budget,
            max_time_seconds=max_time_seconds,
            standard=standard,
            selected_regulations=selected_regulations,
            lang=lang,
        )

        pipeline.state.source_command = source_command

        if custom_skip_phases:
            pipeline.state.skipped_phases = list(custom_skip_phases)
        if selected_regulations:
            pipeline.state.selected_regulations = list(selected_regulations)

        # Set up callbacks for progress reporting
        async def on_phase_complete(phase: Phase, state: PipelineState) -> None:
            rows = state.get_all_rows()
            pct = state.progress_percent
            if phase == Phase.DATA_QUALITY:
                dq = state.data_quality_summary or {}
                detail = (
                    f"{dq.get('rows_with_doc_content', 0)}/{dq.get('total_rows', 0)} "
                    f"{_t(lang, 'rows_available_suffix')}"
                )
                await _send_progress(send_message_fn, phase, "done", detail, lang=lang)
            elif phase == Phase.REFERENCE_MAPPING:
                await _send_progress(send_message_fn, phase, "done", lang=lang)
            elif phase == Phase.GAP_SCAN:
                found = sum(
                    1
                    for r in rows
                    if r.phase_results.get(Phase.GAP_SCAN.value, {}).get("status")
                    == "completed"
                )
                await _send_progress(
                    send_message_fn,
                    phase,
                    "done",
                    f"{found} {_t(lang, 'evidence_done_suffix')}",
                    lang=lang,
                )
            elif phase == Phase.CHECKLIST_VERIFY:
                await _send_progress(send_message_fn, phase, "done", lang=lang)
            elif phase == Phase.RISK_ASSESSMENT:
                # Count verdicts
                verdicts: dict[str, int] = {}
                for r in rows:
                    if r.verdict:
                        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
                non_compliant = verdicts.get(Verdict.NON_COMPLIANCE, 0)
                partial = verdicts.get(Verdict.PARTIAL_COMPLIANCE, 0)
                full = verdicts.get(Verdict.FULL_COMPLIANCE, 0)
                detail = f"✅ {full} | ⚠️ {partial} | ❌ {non_compliant}"
                await _send_progress(send_message_fn, phase, "done", detail, lang=lang)
            elif phase == Phase.REMEDIATION:
                await _send_progress(send_message_fn, phase, "done", lang=lang)
            elif phase == Phase.VERIFICATION:
                flagged = sum(1 for r in rows if r.flagged_for_ra)
                detail = (
                    f"{flagged} {_t(lang, 'ra_review_detail_suffix')}"
                    if flagged
                    else _t(lang, "ra_review_all_pass")
                )
                await _send_progress(send_message_fn, phase, "done", detail, lang=lang)
            elif phase == Phase.SOURCE_CHECK:
                sc = state.source_check_summary or {}
                detail = _t(
                    lang,
                    "source_check_detail",
                    accessible=sc.get("accessible", 0),
                    broken=sc.get("broken", 0),
                )
                # pct is now meaningful here — pipeline.py marks all rows
                # COMPLETED at end of Phase 6, so this should read 100%.
                await _send_progress(send_message_fn, phase, "done", detail, pct, lang=lang)

        # Sync callback wrapper for the pipeline (pipeline is sync, callbacks are async)
        # We need to bridge sync → async
        _phase_complete_events: list[tuple[Phase, PipelineState]] = []

        def sync_on_phase_complete(phase: Phase, state: PipelineState) -> None:
            """Sync callback — stores events for async processing."""
            _phase_complete_events.append((phase, state))

        # Populate rows
        await _send_progress(
            send_message_fn,
            Phase.DATA_QUALITY,
            "start",
            _t(lang, "initializing"),
            lang=lang,
        )
        row_count = pipeline.initialize(scan_result)

        # Notify run_id is ready — send report URL BEFORE pipeline runs
        if on_run_id_ready:
            try:
                await on_run_id_ready(pipeline.state.run_id)
            except Exception as e:
                logger.warning(f"on_run_id_ready callback failed: {e}")

        if row_count == 0:
            result.error = _t(lang, "no_items_error")
            result.duration_seconds = time.time() - start_time
            return result

        await _send_progress(
            send_message_fn,
            Phase.DATA_QUALITY,
            "start",
            _t(lang, "created_rows", n=row_count),
            lang=lang,
        )

        # Override pipeline callbacks with our sync wrapper
        pipeline._on_phase_complete = sync_on_phase_complete

        # Run pipeline in a thread (it's synchronous, uses blocking LLM calls)
        loop = asyncio.get_running_loop()

        # We run the pipeline in chunks so we can send async progress between phases
        # Instead of running the full pipeline.run(), we step through phases manually

        pipeline._state.status = PhaseStatus.RUNNING.value

        for phase in PHASE_ORDER:
            if pipeline.is_paused or pipeline.is_completed:
                break

            # Check if this phase should be skipped in current mode
            if pipeline._skip_phase_in_mode(phase):
                await _send_progress(
                    send_message_fn, phase, "skip", _t(lang, "skip_not_in_mode"), lang=lang
                )
                continue

            if pipeline._phase_already_done(phase):
                continue

            # Budget check for LLM phases
            if phase.uses_llm and pipeline._budget_exceeded():
                await _send_progress(
                    send_message_fn, phase, "fail", _t(lang, "budget_exhausted"), lang=lang
                )
                pipeline.pause(PauseReason.LLM_BUDGET_EXCEEDED)
                break

            # Send start message
            await _send_progress(send_message_fn, phase, "start", lang=lang)

            # Execute the phase in a thread to not block the event loop
            phase_executors = {
                Phase.DATA_QUALITY: pipeline._execute_phase_0,
                Phase.REFERENCE_MAPPING: pipeline._execute_phase_05,
                Phase.GAP_SCAN: pipeline._execute_phase_1,
                Phase.CHECKLIST_VERIFY: pipeline._execute_phase_2,
                Phase.RISK_ASSESSMENT: pipeline._execute_phase_3,
                Phase.REMEDIATION: pipeline._execute_phase_4,
                Phase.VERIFICATION: pipeline._execute_phase_5,
                Phase.SOURCE_CHECK: pipeline._execute_phase_6,
            }

            executor = phase_executors.get(phase)
            if executor:
                try:
                    if phase == Phase.GAP_SCAN and send_message_fn is not None:
                        # Phase 1: run with per-document progress monitoring
                        import queue as _queue
                        _doc_q: _queue.Queue = _queue.Queue()

                        def _on_doc_done(done: int, total: int, doc_id: str) -> None:
                            _doc_q.put((done, total, doc_id))

                        pipeline._phase1_doc_callback = _on_doc_done
                        _phase_name = _phase_display_name(Phase.GAP_SCAN, lang)
                        _phase_icon = _PHASE_ICONS.get(Phase.GAP_SCAN, "🔎")

                        phase_task = asyncio.ensure_future(
                            loop.run_in_executor(None, executor)
                        )
                        _last_progress_time = asyncio.get_event_loop().time()
                        _last_done = 0
                        _last_total = 0
                        while not phase_task.done():
                            got_update = False
                            while True:
                                try:
                                    done, total, _doc_id = _doc_q.get_nowait()
                                    _last_done = done
                                    _last_total = total
                                    pct = round(done / total * 100) if total > 0 else 0
                                    progress_text = (
                                        f"{_phase_icon} **{_phase_name}** "
                                        + _t(lang, "gap_scan_doc_progress",
                                             done=done, total=total, pct=pct)
                                    )
                                    await asyncio.wait_for(send_message_fn(progress_text), timeout=10.0)
                                    _last_progress_time = asyncio.get_event_loop().time()
                                    got_update = True
                                except _queue.Empty:
                                    break
                            # Heartbeat every 15s when no new doc completes (LLM fallback running)
                            if not got_update and _last_total > 0:
                                elapsed_since = asyncio.get_event_loop().time() - _last_progress_time
                                if elapsed_since >= 15:
                                    pct = round(_last_done / _last_total * 100)
                                    heartbeat = (
                                        f"{_phase_icon} **{_phase_name}** "
                                        + _t(lang, "gap_scan_doc_progress",
                                             done=_last_done, total=_last_total, pct=pct)
                                        + f" ⏳ ({int(elapsed_since)}s)"
                                    )
                                    await asyncio.wait_for(send_message_fn(heartbeat), timeout=10.0)
                                    _last_progress_time = asyncio.get_event_loop().time()
                            await asyncio.sleep(0.3)
                        pipeline._phase1_doc_callback = None
                        # Drain any remaining queue items (docs that completed
                        # while the loop was sleeping or exiting)
                        while True:
                            try:
                                done, total, _doc_id = _doc_q.get_nowait()
                                pct = round(done / total * 100) if total > 0 else 0
                                progress_text = (
                                    f"{_phase_icon} **{_phase_name}** "
                                    + _t(lang, "gap_scan_doc_progress",
                                         done=done, total=total, pct=pct)
                                )
                                await asyncio.wait_for(send_message_fn(progress_text), timeout=10.0)
                            except _queue.Empty:
                                break
                            except Exception:
                                break
                        await phase_task  # propagate any exception
                    else:
                        await loop.run_in_executor(None, executor)
                except Exception as e:
                    logger.error(f"Phase {phase.value} failed: {e}")
                    await _send_progress(send_message_fn, phase, "fail", str(e)[:100], lang=lang)
                    continue

            # Process any queued phase complete events
            while _phase_complete_events:
                p, s = _phase_complete_events.pop(0)
                await on_phase_complete(p, s)

            # Check auto-pause conditions after risk assessment
            if phase == Phase.RISK_ASSESSMENT:
                if pipeline._check_critical_gaps():
                    await _send_progress(
                        send_message_fn,
                        phase,
                        "done",
                        _t(lang, "critical_gaps_pause"),
                        lang=lang,
                    )
                    # In auto mode we can resume and continue
                    pipeline.resume()

            if phase == Phase.VERIFICATION:
                if pipeline._check_evidence_conflicts():
                    await _send_progress(
                        send_message_fn,
                        phase,
                        "done",
                        _t(lang, "evidence_conflict_pause"),
                        lang=lang,
                    )
                    pipeline.resume()

        # Mark completed if we got through all phases
        if (
            not pipeline.is_paused
            and pipeline._state.status == PhaseStatus.RUNNING.value
        ):
            pipeline._state.status = PhaseStatus.COMPLETED.value
            pipeline._state.completed_at = time.time()
            pipeline._save_state()

        # Build result
        result.success = True
        result.run_id = pipeline.state.run_id
        result.state = pipeline.state
        result.table = pipeline.table
        result.total_rows = pipeline.state.total_rows
        result.completed_rows = pipeline.state.completed_rows
        result.state_file_path = str(
            pipeline._state_dir / f"{pipeline.state.run_id}.json"
        )

        # Summary data
        summary = pipeline.get_comparison_table_summary()
        result.verdict_distribution = summary.get("verdict_distribution", {})
        result.risk_distribution = summary.get("risk_distribution", {})
        result.flagged_for_ra = summary.get("flagged_for_ra", 0)
        result.llm_budget_used = pipeline.state.get_budget().to_dict()

        # Phase 5 verification report — build from flagged rows
        try:
            ver_rows = pipeline.state.rows
            flagged_items = [
                {
                    "clause_id": getattr(r, "clause_id", ""),
                    "doc_id": getattr(r, "doc_id", ""),
                    "verdict": getattr(r, "verdict", ""),
                    "flagged_for_ra": getattr(r, "flagged_for_ra", False),
                    "verification_rounds": len(getattr(r, "verification_rounds", []) or []),
                }
                for r in ver_rows
                if getattr(r, "flagged_for_ra", False)
            ]
            result.verification_report = {
                "has_data": True,
                "verified_at": pipeline.state.completed_at or time.time(),
                "total_rows": len(ver_rows),
                "flagged_count": len(flagged_items),
                "flagged_items": flagged_items,
            }
        except Exception as _ver_exc:
            logger.warning(f"Could not build verification_report: {_ver_exc}")

    except Exception as e:
        result.success = False
        result.error = str(e)
        logger.error(f"Pipeline runner failed: {e}", exc_info=True)
        # Save partial state so the report is still accessible
        try:
            pipeline._state.status = PhaseStatus.FAILED.value
            pipeline._save_state()
            result.run_id = pipeline.state.run_id
            result.state = pipeline.state
            result.table = pipeline.table
            result.total_rows = pipeline.state.total_rows
            result.completed_rows = pipeline.state.completed_rows
            result.state_file_path = str(
                pipeline._state_dir / f"{pipeline.state.run_id}.json"
            )
        except Exception as _save_err:
            logger.warning(f"Could not save partial state after failure: {_save_err}")

    result.duration_seconds = time.time() - start_time
    return result
