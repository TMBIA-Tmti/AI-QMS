"""
AI-QMS — Regulatory Analysis Storage
=====================================

Independent Markdown DB for LLM-generated regulatory analysis reports.
Stores assessment reports from 法規清單 and 法規清單更新 commands
for Phase 2 audit module consumption.

Directory structure:
    regulatory_analysis_storage/
    ├── metadata/
    │   └── analysis_registry.json
    └── reports/
        ├── analysis_20260227_143000.md
        ├── analysis_20260227_150000.md
        └── ...
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from src.utils.safe_io import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PATH = "regulatory_analysis_storage"


class RegulatoryAnalysisStorage:
    """
    Independent Markdown DB for LLM-generated regulatory analysis reports.
    Mirrors the pattern of RegulatoryMarkdownStorage but for analysis output.
    """

    def __init__(self, base_path: str = _DEFAULT_BASE_PATH):
        self.base_path = Path(base_path)
        self.reports_path = self.base_path / "reports"
        self.metadata_path = self.base_path / "metadata"
        self.registry_file = self.metadata_path / "analysis_registry.json"

        self._ensure_directories()
        self._load_registry()

    # ============================================================
    # Internal helpers
    # ============================================================

    def _ensure_directories(self) -> None:
        """Create directory structure if not exists."""
        self.reports_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> None:
        """Load analysis registry from file."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self.registry: dict = json.load(f)
            except Exception:
                logger.warning("Failed to load analysis registry, creating new one.")
                self._init_empty_registry()
        else:
            self._init_empty_registry()

    def _init_empty_registry(self) -> None:
        """Create an empty registry."""
        self.registry = {
            "registry_version": "1.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "report_count": 0,
            "next_id": 1,
            "reports": [],
        }
        self._save_registry()

    def _save_registry(self) -> None:
        """Save registry to file with atomic write."""
        self.registry["last_updated"] = datetime.now(timezone.utc).isoformat()
        active_reports = [
            r for r in self.registry["reports"] if r.get("status") != "deleted"
        ]
        self.registry["report_count"] = len(active_reports)
        atomic_write_json(self.registry_file, self.registry)

    def _calculate_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content."""
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

    def _next_report_id(self) -> str:
        """Generate next sequential report_id."""
        next_id = self.registry.get("next_id", 1)
        report_id = f"rpt_{next_id:04d}"
        self.registry["next_id"] = next_id + 1
        return report_id

    # ============================================================
    # Save operations
    # ============================================================

    def save_analysis_report(
        self,
        analysis_content: str,
        source_command: str = "regulatory_update",
        crawl_summary: Optional[dict] = None,
        analyzed_standards: Optional[list] = None,
        analyzed_documents: Optional[list] = None,
        provider: str = "",
        model: str = "",
        is_truncated: bool = False,
    ) -> dict:
        """Save an LLM-generated analysis report.

        Args:
            analysis_content: The LLM-generated assessment markdown
            source_command: "regulatory_list" or "regulatory_update"
            crawl_summary: Optional crawl summary (region counts, success/fail)
            analyzed_standards: List of standards analyzed
            analyzed_documents: List of QMS doc_ids analyzed
            provider: LLM provider used
            model: LLM model used
            is_truncated: Whether the report was truncated due to token exhaustion

        Returns:
            dict with 'success', 'report_id', 'path' keys
        """
        if not analysis_content or not analysis_content.strip():
            return {"success": False, "error": "Empty analysis content"}

        report_id = self._next_report_id()
        timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")

        # Build markdown file with header
        command_label = {
            "regulatory_list": "法規清單",
            "regulatory_update": "法規清單更新",
        }.get(source_command, source_command)

        standards_count = len(analyzed_standards) if analyzed_standards else 0
        docs_count = len(analyzed_documents) if analyzed_documents else 0
        truncation_note = "\n⚠️ 狀態: 報告因 Token 耗盡而截斷，內容可能不完整" if is_truncated else ""

        header = (
            f"# 法規合規性分析報告 ({report_id})\n"
            f"生成時間: {timestamp.isoformat()}\n"
            f"來源指令: {command_label}\n"
            f"LLM: {provider} / {model}\n"
            f"分析標準數: {standards_count}\n"
            f"分析文件數: {docs_count}{truncation_note}\n\n---\n\n"
        )
        full_content = header + analysis_content

        # Write markdown file
        filename = f"analysis_{ts_str}.md"
        filepath = self.reports_path / filename
        relative_path = str(filepath.relative_to(self.base_path))

        atomic_write_text(filepath, full_content)
        content_hash = self._calculate_hash(full_content)

        # Create registry entry
        entry = {
            "report_id": report_id,
            "source_command": source_command,
            "analysis_timestamp": timestamp.isoformat(),
            "markdown_path": relative_path,
            "content_hash": content_hash,
            "content_length": len(analysis_content),
            "provider": provider,
            "model": model,
            "is_truncated": is_truncated,
            "crawl_summary": crawl_summary or {},
            "analyzed_standards": analyzed_standards or [],
            "analyzed_documents": analyzed_documents or [],
            "status": "active",
            "deleted_at": None,
        }
        self.registry["reports"].append(entry)
        self._save_registry()

        logger.info(
            f"Saved analysis report {report_id}: {source_command} -> {relative_path} "
            f"({len(analysis_content)} chars, truncated={is_truncated})"
        )
        return {"success": True, "report_id": report_id, "path": str(filepath)}

    # ============================================================
    # Query operations
    # ============================================================

    def list_reports(self, status: str = "active") -> list:
        """List reports, optionally filtered by status.

        Args:
            status: Filter by status ("active", "deleted", "all")

        Returns:
            list of report entry dicts (with added 'index' field)
        """
        reports = self.registry.get("reports", [])
        result = []
        for i, rpt in enumerate(reports):
            if status != "all" and rpt.get("status", "active") != status:
                continue
            entry = dict(rpt)
            entry["index"] = i
            result.append(entry)
        return result

    def get_report(self, report_id: str) -> Optional[dict]:
        """Get full report content + metadata by report_id.

        Returns:
            dict with all metadata fields + 'content' key, or None
        """
        for rpt in self.registry.get("reports", []):
            if rpt.get("report_id") == report_id:
                entry = dict(rpt)
                md_path = rpt.get("markdown_path", "")
                if md_path:
                    full_path = self.base_path / md_path
                    if full_path.exists():
                        try:
                            entry["content"] = full_path.read_text(encoding="utf-8")
                        except Exception:
                            entry["content"] = ""
                    else:
                        entry["content"] = ""
                else:
                    entry["content"] = ""
                return entry
        return None

    def get_latest_report(self, source_command: Optional[str] = None) -> Optional[dict]:
        """Get the most recent active report, optionally filtered by source command.

        Args:
            source_command: Filter by "regulatory_list" or "regulatory_update" (None = any)

        Returns:
            dict with all metadata fields + 'content' key, or None
        """
        reports = self.registry.get("reports", [])
        # Iterate in reverse to find the latest active report
        for rpt in reversed(reports):
            if rpt.get("status", "active") != "active":
                continue
            if source_command and rpt.get("source_command") != source_command:
                continue
            return self.get_report(rpt.get("report_id", ""))
        return None

    def search_reports(self, keyword: str, status: str = "active") -> list:
        """Search reports by keyword across analyzed_standards, analyzed_documents,
        source_command, provider, model fields.

        Args:
            keyword: Search keyword (case-insensitive)
            status: Filter by status ("active", "deleted", "all")

        Returns:
            list of matching report entry dicts (with 'index' field)
        """
        kw_lower = keyword.lower().strip()
        reports = self.registry.get("reports", [])
        result = []
        for i, rpt in enumerate(reports):
            if status != "all" and rpt.get("status", "active") != status:
                continue
            searchable_parts = [
                rpt.get("source_command", ""),
                rpt.get("provider", ""),
                rpt.get("model", ""),
            ]
            searchable_parts.extend(rpt.get("analyzed_standards", []))
            searchable_parts.extend(rpt.get("analyzed_documents", []))
            searchable = " ".join(searchable_parts).lower()
            if kw_lower in searchable:
                entry = dict(rpt)
                entry["index"] = i
                result.append(entry)
        return result

    # ============================================================
    # Delete operations
    # ============================================================

    def delete_report(self, report_id: str) -> dict:
        """Soft-delete a report by report_id.

        Returns:
            dict with 'success', 'report_id'
        """
        for rpt in self.registry.get("reports", []):
            if rpt.get("report_id") == report_id and rpt.get("status") != "deleted":
                rpt["status"] = "deleted"
                rpt["deleted_at"] = datetime.now(timezone.utc).isoformat()
                self._save_registry()
                logger.info(f"Soft-deleted analysis report {report_id}")
                return {"success": True, "report_id": report_id}
        return {
            "success": False,
            "error": f"Report {report_id} not found or already deleted.",
        }

    # ============================================================
    # Stats & utility
    # ============================================================

    def get_stats(self) -> dict:
        """Return report counts and summary info.

        Returns:
            dict with 'total_active', 'total_deleted', 'by_source_command'
        """
        reports = self.registry.get("reports", [])
        active = 0
        deleted = 0
        by_source: dict = {}

        for rpt in reports:
            status = rpt.get("status", "active")
            if status == "deleted":
                deleted += 1
                continue
            active += 1
            src = rpt.get("source_command", "unknown")
            if src not in by_source:
                by_source[src] = 0
            by_source[src] += 1

        return {
            "total_active": active,
            "total_deleted": deleted,
            "by_source_command": by_source,
        }

    def get_report_count(self) -> int:
        """Get total number of active reports."""
        return sum(
            1
            for r in self.registry.get("reports", [])
            if r.get("status", "active") == "active"
        )


# ============================================================
# Singleton accessor
# ============================================================

_analysis_store_instance: Optional[RegulatoryAnalysisStorage] = None


def get_regulatory_analysis_store() -> RegulatoryAnalysisStorage:
    """Get or create singleton RegulatoryAnalysisStorage instance."""
    global _analysis_store_instance
    if _analysis_store_instance is None:
        _analysis_store_instance = RegulatoryAnalysisStorage()
    return _analysis_store_instance
