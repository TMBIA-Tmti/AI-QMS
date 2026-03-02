"""
AI-QMS — Phase 0: Data Quality Gate
=====================================

Evaluate data availability BEFORE any LLM work.
Checks:
  - Company QMS documents exist and have content
  - Regulatory data has been crawled (or local docs uploaded)
  - Each expected evidence item has a potential source document
  - No obsolete documents in the analysis set

If data quality is insufficient, the pipeline can skip or flag
individual rows rather than wasting LLM tokens on empty data.
"""

from __future__ import annotations

import time

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    PipelineState,
)


__all__ = [
    "run_data_quality_gate",
    "DataQualityResult",
]


class DataQualityResult:
    """Summary of data quality assessment for the entire pipeline."""

    def __init__(self):
        self.total_rows: int = 0
        self.rows_with_doc_content: int = 0
        self.rows_without_doc_content: int = 0
        self.rows_with_regulatory_data: int = 0
        self.rows_without_regulatory_data: int = 0
        self.documents_checked: dict[str, dict] = {}
        # doc_id -> {exists, has_content, content_length, is_obsolete}
        self.regulatory_data_available: bool = False
        self.issues: list[str] = []
        self.overall_pass: bool = True

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "rows_with_doc_content": self.rows_with_doc_content,
            "rows_without_doc_content": self.rows_without_doc_content,
            "rows_with_regulatory_data": self.rows_with_regulatory_data,
            "rows_without_regulatory_data": self.rows_without_regulatory_data,
            "documents_checked": self.documents_checked,
            "regulatory_data_available": self.regulatory_data_available,
            "issues": self.issues,
            "overall_pass": self.overall_pass,
        }


def _check_document_availability(doc_id: str) -> dict:
    """Check if a QMS document exists and has content.

    Returns dict with: exists, has_content, content_length, is_obsolete, title
    """
    try:
        from src.storage.markdown_storage import MarkdownStoreService

        service = MarkdownStoreService()
        result = service.get_document(doc_id)

        if not result or not result.get("success"):
            return {
                "exists": False,
                "has_content": False,
                "content_length": 0,
                "is_obsolete": False,
                "title": "",
            }

        content = result.get("content", "")
        # Check if document is obsolete
        # The storage service only returns active docs via get_document,
        # but we double-check status if available
        is_obsolete = result.get("status", "active") == "obsolete"

        return {
            "exists": True,
            "has_content": len(content.strip()) > 50,
            "content_length": len(content),
            "is_obsolete": is_obsolete,
            "title": result.get("title", ""),
        }
    except Exception:
        return {
            "exists": False,
            "has_content": False,
            "content_length": 0,
            "is_obsolete": False,
            "title": "",
        }


def _check_regulatory_data_available() -> bool:
    """Check if regulatory crawl data exists."""
    try:
        from src.storage.regulatory_storage import get_regulatory_store

        store = get_regulatory_store()
        last_crawl = store.get_last_crawl_results()
        if not last_crawl:
            return False

        results = last_crawl.get("results", [])
        success_count = sum(1 for r in results if r.get("crawl_status") == "success")
        return success_count > 0
    except Exception:
        return False


def run_data_quality_gate(state: PipelineState) -> DataQualityResult:
    """Execute Phase 0: Data Quality Gate.

    Checks every row's document availability and marks rows that
    cannot proceed (missing/obsolete docs) with appropriate status.

    Args:
        state: Current pipeline state with populated rows

    Returns:
        DataQualityResult with assessment details
    """
    dq = DataQualityResult()
    all_rows = state.get_all_rows()
    dq.total_rows = len(all_rows)

    # Check regulatory data once (shared across all rows)
    dq.regulatory_data_available = _check_regulatory_data_available()
    if not dq.regulatory_data_available:
        dq.issues.append(
            "尚未執行法規爬取，無法取得最新法規資料。建議先執行「法規清單更新」。"
        )

    # Check each unique document
    unique_doc_ids = {r.doc_id for r in all_rows}
    for doc_id in unique_doc_ids:
        doc_info = _check_document_availability(doc_id)
        dq.documents_checked[doc_id] = doc_info

        if not doc_info["exists"]:
            dq.issues.append(f"文件 {doc_id} 不存在於系統中。")
        elif doc_info["is_obsolete"]:
            dq.issues.append(f"文件 {doc_id} 已作廢，不應納入分析。")
        elif not doc_info["has_content"]:
            dq.issues.append(f"文件 {doc_id} 內容為空或過短。")

    # Process each row
    for row in all_rows:
        doc_info = dq.documents_checked.get(row.doc_id, {})

        # Create phase result
        phase_result = PhaseResult(
            phase=Phase.DATA_QUALITY.value,
            started_at=time.time(),
        )

        has_doc = (
            doc_info.get("exists", False)
            and doc_info.get("has_content", False)
            and not doc_info.get("is_obsolete", False)
        )

        if has_doc:
            dq.rows_with_doc_content += 1
        else:
            dq.rows_without_doc_content += 1

        if dq.regulatory_data_available:
            dq.rows_with_regulatory_data += 1
        else:
            dq.rows_without_regulatory_data += 1

        # Determine row-level data quality
        if not has_doc:
            phase_result.status = PhaseStatus.FAILED.value
            phase_result.error = (
                f"文件 {row.doc_id} 不可用"
                f"{'（已作廢）' if doc_info.get('is_obsolete') else ''}"
                f"{'（不存在）' if not doc_info.get('exists') else ''}"
                f"{'（內容為空）' if doc_info.get('exists') and not doc_info.get('has_content') else ''}"
            )
            phase_result.output = {
                "data_available": False,
                "reason": phase_result.error,
                "doc_content_length": doc_info.get("content_length", 0),
            }
            row.overall_status = PhaseStatus.SKIPPED.value
        else:
            phase_result.status = PhaseStatus.COMPLETED.value
            phase_result.output = {
                "data_available": True,
                "doc_content_length": doc_info.get("content_length", 0),
                "regulatory_data_available": dq.regulatory_data_available,
            }

        phase_result.completed_at = time.time()
        row.set_phase_result(Phase.DATA_QUALITY, phase_result)

        # Advance to next phase if passed
        if phase_result.status == PhaseStatus.COMPLETED.value:
            row.advance_to_next_phase()

        state.update_row(row)

    # Overall assessment
    if dq.rows_without_doc_content == dq.total_rows:
        dq.overall_pass = False
        dq.issues.append("所有文件均不可用，無法執行分析。")
    elif dq.rows_without_doc_content > 0:
        # Partial — some rows will be skipped
        dq.issues.append(
            f"{dq.rows_without_doc_content}/{dq.total_rows} 個分析項目"
            f"因文件不可用將被跳過。"
        )

    # Store summary in pipeline state
    state.data_quality_summary = dq.to_dict()

    return dq
