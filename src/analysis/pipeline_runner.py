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
]


# ============================================================
# Result container
# ============================================================


class PipelineRunResult:
    """Result of a pipeline analysis run, ready for report rendering."""

    def __init__(self):
        self.success: bool = False
        self.run_id: str = ""
        self.state: Optional[PipelineState] = None
        self.table: Optional[ComparisonTable] = None
        self.error: Optional[str] = None
        self.total_rows: int = 0
        self.completed_rows: int = 0
        self.duration_seconds: float = 0.0
        self.state_file_path: Optional[str] = None

        # Summary data for the report
        self.verdict_distribution: dict[str, int] = {}
        self.risk_distribution: dict[str, int] = {}
        self.flagged_for_ra: int = 0
        self.llm_budget_used: dict = {}

    def to_summary_markdown(self) -> str:
        """Generate a summary markdown for inline Chainlit display."""
        if not self.success:
            return f"⚠️ 分析管線執行失敗: {self.error or '未知錯誤'}"

        lines = [
            "## 📊 合規性分析管線結果",
            "",
            f"**分析 ID**: `{self.run_id}`",
            f"**總分析項目**: {self.total_rows} 項",
            f"**完成項目**: {self.completed_rows} 項",
            f"**耗時**: {self.duration_seconds:.1f} 秒",
            "",
            "### 判定結果分布",
        ]

        # Verdict distribution
        for verdict, count in self.verdict_distribution.items():
            display = VERDICT_DISPLAY.get(verdict, {})
            icon = display.get("icon", "❓")
            label = display.get("label_zh", verdict)
            lines.append(f"- {icon} **{label}**: {count} 項")

        if not self.verdict_distribution:
            lines.append("- （尚無判定結果）")

        lines.append("")
        lines.append("### 風險等級分布")

        # Risk distribution
        for risk, count in self.risk_distribution.items():
            display = RISK_LEVEL_DISPLAY.get(risk, {})
            icon = display.get("icon", "❓")
            label = display.get("label_zh", risk)
            lines.append(f"- {icon} **{label}**: {count} 項")

        if not self.risk_distribution:
            lines.append("- （尚無風險評估）")

        # Flagged
        if self.flagged_for_ra > 0:
            lines.append("")
            lines.append(f"### ⚠️ 需 RA 審查: {self.flagged_for_ra} 項")
            lines.append("（交叉詰問 3 輪後仍有分歧，已標記待人工審查）")

        # LLM usage
        if self.llm_budget_used:
            lines.append("")
            lines.append("### 📈 LLM Token 用量")
            lines.append(
                f"- 總用量: {self.llm_budget_used.get('total_tokens_used', 0):,} tokens "
                f"({self.llm_budget_used.get('usage_percent', 0)}%)"
            )
            lines.append(f"- 呼叫次數: {self.llm_budget_used.get('calls_made', 0)} 次")

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


async def _send_progress(
    msg_fn: Optional[Callable],
    phase: Phase,
    status: str,
    detail: str = "",
) -> None:
    """Send a progress message via Chainlit (or any async callback)."""
    if msg_fn is None:
        return

    icon = _PHASE_ICONS.get(phase, "📋")
    phase_name = phase.display_name

    if status == "start":
        text = f"{icon} **{phase_name}** 執行中..."
    elif status == "done":
        text = f"{icon} **{phase_name}** ✅ 完成"
        if detail:
            text += f" — {detail}"
    elif status == "skip":
        text = f"{icon} **{phase_name}** ⏭️ 跳過"
        if detail:
            text += f" — {detail}"
    elif status == "fail":
        text = f"{icon} **{phase_name}** ❌ 失敗"
        if detail:
            text += f" — {detail}"
    else:
        text = f"{icon} **{phase_name}** {detail}"

    try:
        await msg_fn(text)
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
    max_tokens_budget: int = 500_000,
    source_command: str = "regulatory_list",
    send_message_fn: Optional[Callable] = None,
    phoenix_trace_ctx: Optional[Callable] = None,
    selected_regulations: list[str] | None = None,
    on_run_id_ready: Optional[Callable] = None,
    custom_skip_phases: list[str] | None = None,
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
        max_tokens_budget: Max LLM token budget
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
    result = PipelineRunResult()
    start_time = time.time()

    try:
        pipeline = AnalysisPipeline(
            llm_completion_fn=llm_completion_fn,
            model=model,
            mode=mode,
            max_tokens_budget=max_tokens_budget,
            standard=standard,
            selected_regulations=selected_regulations,
        )

        pipeline.state.source_command = source_command

        if custom_skip_phases:
            pipeline.state.skipped_phases = list(custom_skip_phases)
        if selected_regulations:
            pipeline.state.selected_regulations = list(selected_regulations)

        # Set up callbacks for progress reporting
        async def on_phase_complete(phase: Phase, state: PipelineState) -> None:
            rows = state.get_all_rows()
            if phase == Phase.DATA_QUALITY:
                dq = state.data_quality_summary or {}
                detail = (
                    f"{dq.get('rows_with_doc_content', 0)}/{dq.get('total_rows', 0)} "
                    f"項資料可用"
                )
                await _send_progress(send_message_fn, phase, "done", detail)
            elif phase == Phase.REFERENCE_MAPPING:
                await _send_progress(send_message_fn, phase, "done")
            elif phase == Phase.GAP_SCAN:
                found = sum(
                    1
                    for r in rows
                    if r.phase_results.get(Phase.GAP_SCAN.value, {}).get("status")
                    == "completed"
                )
                await _send_progress(
                    send_message_fn, phase, "done", f"{found} 項完成證據搜尋"
                )
            elif phase == Phase.CHECKLIST_VERIFY:
                await _send_progress(send_message_fn, phase, "done")
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
                await _send_progress(send_message_fn, phase, "done", detail)
            elif phase == Phase.REMEDIATION:
                await _send_progress(send_message_fn, phase, "done")
            elif phase == Phase.VERIFICATION:
                flagged = sum(1 for r in rows if r.flagged_for_ra)
                detail = f"{flagged} 項需 RA 審查" if flagged else "所有項目驗證通過"
                await _send_progress(send_message_fn, phase, "done", detail)
            elif phase == Phase.SOURCE_CHECK:
                sc = state.source_check_summary or {}
                detail = (
                    f"{sc.get('accessible', 0)} 可存取 / {sc.get('broken', 0)} 失效"
                )
                await _send_progress(send_message_fn, phase, "done", detail)

        # Sync callback wrapper for the pipeline (pipeline is sync, callbacks are async)
        # We need to bridge sync → async
        _phase_complete_events: list[tuple[Phase, PipelineState]] = []

        def sync_on_phase_complete(phase: Phase, state: PipelineState) -> None:
            """Sync callback — stores events for async processing."""
            _phase_complete_events.append((phase, state))

        # Populate rows
        await _send_progress(
            send_message_fn, Phase.DATA_QUALITY, "start", "初始化分析管線..."
        )
        row_count = pipeline.initialize(scan_result)

        # Notify run_id is ready — send report URL BEFORE pipeline runs
        if on_run_id_ready:
            try:
                await on_run_id_ready(pipeline.state.run_id)
            except Exception as e:
                logger.warning(f"on_run_id_ready callback failed: {e}")

        if row_count == 0:
            result.error = "無可分析的項目（未找到引用法規標準的品質文件）"
            result.duration_seconds = time.time() - start_time
            return result

        await _send_progress(
            send_message_fn,
            Phase.DATA_QUALITY,
            "start",
            f"已建立 {row_count} 個分析項目",
        )

        # Override pipeline callbacks with our sync wrapper
        pipeline._on_phase_complete = sync_on_phase_complete

        # Run pipeline in a thread (it's synchronous, uses blocking LLM calls)
        loop = asyncio.get_event_loop()

        # We run the pipeline in chunks so we can send async progress between phases
        # Instead of running the full pipeline.run(), we step through phases manually

        pipeline._state.status = PhaseStatus.RUNNING.value

        for phase in PHASE_ORDER:
            if pipeline.is_paused or pipeline.is_completed:
                break

            # Check if this phase should be skipped in current mode
            if pipeline._skip_phase_in_mode(phase):
                await _send_progress(
                    send_message_fn, phase, "skip", "當前模式不執行此階段"
                )
                continue

            if pipeline._phase_already_done(phase):
                continue

            # Budget check for LLM phases
            if phase.uses_llm and pipeline._budget_exceeded():
                await _send_progress(send_message_fn, phase, "fail", "Token 預算已用盡")
                pipeline.pause(
                    __import__(
                        "src.analysis.state", fromlist=["PauseReason"]
                    ).PauseReason.LLM_BUDGET_EXCEEDED
                )
                break

            # Send start message
            await _send_progress(send_message_fn, phase, "start")

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
                    await loop.run_in_executor(None, executor)
                except Exception as e:
                    logger.error(f"Phase {phase.value} failed: {e}")
                    await _send_progress(send_message_fn, phase, "fail", str(e)[:100])
                    continue

            # Process any queued phase complete events
            while _phase_complete_events:
                p, s = _phase_complete_events.pop(0)
                await on_phase_complete(p, s)

            # Check auto-pause conditions after risk assessment
            if phase == Phase.RISK_ASSESSMENT:
                if pipeline._check_critical_gaps():
                    await _send_progress(
                        send_message_fn, phase, "done", "🔴 發現嚴重差距，管線已暫停"
                    )
                    # In auto mode we can resume and continue
                    pipeline.resume()

            if phase == Phase.VERIFICATION:
                if pipeline._check_evidence_conflicts():
                    await _send_progress(
                        send_message_fn, phase, "done", "⚠️ 交叉驗證有分歧，管線已暫停"
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

    except Exception as e:
        result.success = False
        result.error = str(e)
        logger.error(f"Pipeline runner failed: {e}", exc_info=True)

    result.duration_seconds = time.time() - start_time
    return result
