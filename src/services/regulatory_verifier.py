"""
AI-QMS — Regulatory Data Verification Module
=============================================

Validates crawled regulatory data for integrity, content quality,
and pipeline consistency. Provides verification reports for UI display
and Word/Excel export.

Checks performed:
  Content Quality (per document):
    - content_not_empty: Markdown content exists and len > 50
    - content_not_placeholder: Not a placeholder/error string
    - content_not_error_page: Not an anti-scraping/block page
    - content_has_structure: Has headings or multiple paragraphs
    - content_min_length: Content > 200 chars (real regulation pages are long)

  Integrity (per stored file):
    - hash_valid: SHA-256 matches registry
    - file_exists: Markdown file exists on disk

  Cross-Comparison (aggregate):
    - pipeline_consistency: crawl JSON matches storage registry
    - no_orphan_files: All files have registry entries
    - no_missing_files: All registry entries have files
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Anti-scraping / error page detection patterns
_BLOCK_PATTERNS = [
    # Cloudflare
    r"enable\s+javascript",
    r"checking\s+your\s+browser",
    r"cf-browser-verification",
    r"cloudflare",
    r"ray\s+id",
    # CAPTCHA
    r"captcha",
    r"recaptcha",
    r"hcaptcha",
    # Generic blocks
    r"access\s+denied",
    r"403\s+forbidden",
    r"sorry,?\s+you\s+have\s+been\s+blocked",
    r"automated\s+access",
    r"bot\s+detection",
    r"please\s+verify\s+you\s+are\s+a\s+human",
]
_BLOCK_RE = re.compile("|".join(_BLOCK_PATTERNS), re.IGNORECASE)

# Placeholder strings from the crawler
_PLACEHOLDER_PREFIXES = [
    "(No extractable content",
    "(HTML parsing failed",
    "HTTP 304 Not Modified but no previous content",
    "(JSON parsing failed",
]


class VerificationItem:
    """Single verification check result."""

    def __init__(
        self,
        check_name: str,
        passed: bool,
        severity: str = "info",
        message: str = "",
        details: Optional[dict] = None,
    ):
        self.check_name = check_name
        self.passed = passed
        self.severity = severity  # "critical", "warning", "info"
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
        }


class DocumentVerification:
    """Verification result for a single document."""

    def __init__(
        self,
        doc_id: str,
        region: str = "",
        agency: str = "",
        url: str = "",
    ):
        self.doc_id = doc_id
        self.region = region
        self.agency = agency
        self.url = url
        self.checks: list[VerificationItem] = []
        self.overall_status: str = "pass"  # "pass", "warning", "fail"
        self.verified_at: str = datetime.now(timezone.utc).isoformat()

    def add_check(self, item: VerificationItem) -> None:
        self.checks.append(item)
        # Update overall status based on worst severity
        if not item.passed:
            if item.severity == "critical":
                self.overall_status = "fail"
            elif item.severity == "warning" and self.overall_status != "fail":
                self.overall_status = "warning"

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "region": self.region,
            "agency": self.agency,
            "url": self.url,
            "checks": [c.to_dict() for c in self.checks],
            "overall_status": self.overall_status,
            "verified_at": self.verified_at,
        }


class VerificationReport:
    """Full verification report across all documents."""

    def __init__(self):
        self.verified_at: str = datetime.now(timezone.utc).isoformat()
        self.total_documents: int = 0
        self.passed_count: int = 0
        self.warning_count: int = 0
        self.failed_count: int = 0
        self.documents: list[DocumentVerification] = []
        self.cross_checks: list[VerificationItem] = []
        self.has_data: bool = False
        self.no_data_message: str = ""

    def to_dict(self) -> dict:
        return {
            "verified_at": self.verified_at,
            "total_documents": self.total_documents,
            "passed_count": self.passed_count,
            "warning_count": self.warning_count,
            "failed_count": self.failed_count,
            "documents": [d.to_dict() for d in self.documents],
            "cross_checks": [c.to_dict() for c in self.cross_checks],
            "has_data": self.has_data,
            "no_data_message": self.no_data_message,
        }


# ============================================================
# Content Quality Checks
# ============================================================


def _check_content_not_empty(content: str) -> VerificationItem:
    """Check that content is not empty and has meaningful length."""
    content_len = len(content.strip()) if content else 0
    passed = content_len > 50
    return VerificationItem(
        check_name="content_not_empty",
        passed=passed,
        severity="critical" if not passed else "info",
        message="內容不為空" if passed else f"內容為空或過短（{content_len} 字元）",
        details={"content_length": content_len},
    )


def _check_content_not_placeholder(content: str) -> VerificationItem:
    """Check that content is not a placeholder/error string."""
    if not content:
        return VerificationItem(
            check_name="content_not_placeholder",
            passed=False,
            severity="critical",
            message="內容為空",
        )

    stripped = content.strip()
    for prefix in _PLACEHOLDER_PREFIXES:
        if stripped.startswith(prefix):
            return VerificationItem(
                check_name="content_not_placeholder",
                passed=False,
                severity="critical",
                message=f"內容為佔位符文字: {prefix[:50]}...",
                details={"matched_prefix": prefix},
            )

    return VerificationItem(
        check_name="content_not_placeholder",
        passed=True,
        severity="info",
        message="內容非佔位符文字",
    )


def _check_content_not_error_page(content: str) -> VerificationItem:
    """Check that content is not an anti-scraping or error page."""
    if not content:
        return VerificationItem(
            check_name="content_not_error_page",
            passed=True,  # Empty handled by other checks
            severity="info",
            message="無內容可檢查",
        )

    # Check for block patterns
    match = _BLOCK_RE.search(content[:2000])  # Only check first 2KB
    if match:
        return VerificationItem(
            check_name="content_not_error_page",
            passed=False,
            severity="warning",
            message=f"內容可能為反爬蟲/封鎖頁面（偵測到: {match.group()[:30]}）",
            details={"matched_pattern": match.group()[:50]},
        )

    return VerificationItem(
        check_name="content_not_error_page",
        passed=True,
        severity="info",
        message="內容非反爬蟲/封鎖頁面",
    )


def _check_content_has_structure(content: str) -> VerificationItem:
    """Check that content has markdown structure (headings, paragraphs)."""
    if not content or len(content.strip()) < 50:
        return VerificationItem(
            check_name="content_has_structure",
            passed=False,
            severity="warning",
            message="內容過短，無法判斷結構",
        )

    # Count headings
    headings = len(re.findall(r"^#{1,6}\s+", content, re.MULTILINE))
    # Count paragraphs (non-empty lines separated by blank lines)
    paragraphs = len(
        [p for p in content.split("\n\n") if p.strip() and len(p.strip()) > 20]
    )

    has_structure = headings >= 2 or paragraphs >= 3
    return VerificationItem(
        check_name="content_has_structure",
        passed=has_structure,
        severity="warning" if not has_structure else "info",
        message=(
            f"內容具有結構（{headings} 個標題，{paragraphs} 個段落）"
            if has_structure
            else f"內容缺乏結構（{headings} 個標題，{paragraphs} 個段落）"
        ),
        details={"heading_count": headings, "paragraph_count": paragraphs},
    )


def _check_content_min_length(content: str) -> VerificationItem:
    """Check that content exceeds minimum length for a real regulation page."""
    # Strip markdown formatting for a cleaner length check
    if not content:
        text_len = 0
    else:
        text = re.sub(r"#{1,6}\s+", "", content)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[-*+]\s+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        text_len = len(text)

    passed = text_len >= 200
    return VerificationItem(
        check_name="content_min_length",
        passed=passed,
        severity="warning" if not passed else "info",
        message=(
            f"內容長度足夠（{text_len} 字元）"
            if passed
            else f"內容過短（{text_len} 字元），真實法規頁面通常超過 200 字元"
        ),
        details={"text_length": text_len},
    )


# ============================================================
# Integrity Checks
# ============================================================


def _check_file_exists(base_path: Path, md_path: str) -> VerificationItem:
    """Check that the markdown file exists on disk."""
    if not md_path:
        return VerificationItem(
            check_name="file_exists",
            passed=False,
            severity="critical",
            message="未記錄檔案路徑",
        )

    full_path = base_path / md_path
    exists = full_path.exists()
    return VerificationItem(
        check_name="file_exists",
        passed=exists,
        severity="critical" if not exists else "info",
        message="檔案存在" if exists else f"檔案不存在: {md_path}",
        details={"path": md_path},
    )


def _check_hash_valid(
    base_path: Path, md_path: str, expected_hash: str
) -> VerificationItem:
    """Verify SHA-256 hash of stored file matches registry."""
    if not md_path or not expected_hash:
        return VerificationItem(
            check_name="hash_valid",
            passed=False,
            severity="warning",
            message="缺少路徑或雜湊值，無法驗證",
        )

    full_path = base_path / md_path
    if not full_path.exists():
        return VerificationItem(
            check_name="hash_valid",
            passed=False,
            severity="critical",
            message="檔案不存在，無法驗證雜湊",
        )

    try:
        content = full_path.read_text(encoding="utf-8")
        actual_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
        matched = actual_hash == expected_hash
        return VerificationItem(
            check_name="hash_valid",
            passed=matched,
            severity="critical" if not matched else "info",
            message="SHA-256 雜湊驗證通過"
            if matched
            else "SHA-256 雜湊不一致（檔案可能已被修改）",
            details={
                "expected": expected_hash[:20] + "...",
                "actual": actual_hash[:20] + "...",
            },
        )
    except Exception as e:
        return VerificationItem(
            check_name="hash_valid",
            passed=False,
            severity="warning",
            message=f"雜湊驗證時發生錯誤: {e}",
        )


# ============================================================
# Cross-Comparison Checks
# ============================================================


def _check_pipeline_consistency(
    crawl_results: Optional[dict], registry_docs: list
) -> VerificationItem:
    """Check that crawl results JSON matches storage registry."""
    if not crawl_results:
        return VerificationItem(
            check_name="pipeline_consistency",
            passed=True,
            severity="info",
            message="無爬取結果可比對",
        )

    crawl_success = [
        r
        for r in crawl_results.get("results", [])
        if r.get("crawl_status") == "success"
    ]
    active_docs = [d for d in registry_docs if d.get("status") == "active"]

    crawl_count = len(crawl_success)
    storage_count = len(active_docs)

    # They should be roughly equal (storage may have slightly fewer
    # if some were filtered during save)
    diff = abs(crawl_count - storage_count)
    passed = diff <= 2  # Allow small tolerance

    return VerificationItem(
        check_name="pipeline_consistency",
        passed=passed,
        severity="warning" if not passed else "info",
        message=(
            f"管線一致性通過（爬取成功: {crawl_count}, 儲存: {storage_count}）"
            if passed
            else f"管線不一致（爬取成功: {crawl_count}, 儲存: {storage_count}, 差異: {diff}）"
        ),
        details={
            "crawl_success_count": crawl_count,
            "storage_active_count": storage_count,
            "difference": diff,
        },
    )


def _check_orphan_files(base_path: Path, registry_docs: list) -> VerificationItem:
    """Check for markdown files with no registry entry."""
    docs_dir = base_path / "documents"
    if not docs_dir.exists():
        return VerificationItem(
            check_name="no_orphan_files",
            passed=True,
            severity="info",
            message="文件目錄不存在，無孤立檔案",
        )

    # Collect all registry paths
    registry_paths = set()
    for doc in registry_docs:
        md_path = doc.get("markdown_path", "")
        if md_path:
            registry_paths.add(md_path)

    # Find all .md files in documents/
    orphans = []
    for md_file in docs_dir.rglob("*.md"):
        rel = str(md_file.relative_to(base_path))
        # Normalize path separators
        rel_normalized = rel.replace("\\", "/")
        found = False
        for rp in registry_paths:
            if rp.replace("\\", "/") == rel_normalized:
                found = True
                break
        if not found:
            orphans.append(rel)

    passed = len(orphans) == 0
    return VerificationItem(
        check_name="no_orphan_files",
        passed=passed,
        severity="warning" if not passed else "info",
        message=(
            "無孤立檔案"
            if passed
            else f"發現 {len(orphans)} 個孤立檔案（無對應的註冊表條目）"
        ),
        details={"orphan_files": orphans[:10]},  # Cap at 10
    )


def _check_missing_files(base_path: Path, registry_docs: list) -> VerificationItem:
    """Check for registry entries with no file on disk."""
    active_docs = [d for d in registry_docs if d.get("status") == "active"]
    missing = []
    for doc in active_docs:
        md_path = doc.get("markdown_path", "")
        if md_path:
            full_path = base_path / md_path
            if not full_path.exists():
                missing.append(
                    {
                        "doc_id": doc.get("doc_id", ""),
                        "path": md_path,
                    }
                )

    passed = len(missing) == 0
    return VerificationItem(
        check_name="no_missing_files",
        passed=passed,
        severity="critical" if not passed else "info",
        message=(
            "所有註冊檔案皆存在"
            if passed
            else f"發現 {len(missing)} 個註冊條目缺少對應檔案"
        ),
        details={"missing_files": missing[:10]},
    )


# ============================================================
# Main Verification Functions
# ============================================================


def verify_document(doc_id: str) -> Optional[DocumentVerification]:
    """Verify a single document by doc_id.

    Returns DocumentVerification or None if document not found.
    """
    try:
        from src.storage.regulatory_markdown_storage import (
            get_regulatory_markdown_store,
        )

        store = get_regulatory_markdown_store()
        doc = store.get_document(doc_id)
        if not doc:
            return None

        dv = DocumentVerification(
            doc_id=doc_id,
            region=doc.get("region", ""),
            agency=doc.get("agency", ""),
            url=doc.get("url", ""),
        )

        content = doc.get("content", "")
        base_path = store.base_path

        # Content quality checks
        dv.add_check(_check_content_not_empty(content))
        dv.add_check(_check_content_not_placeholder(content))
        dv.add_check(_check_content_not_error_page(content))
        dv.add_check(_check_content_has_structure(content))
        dv.add_check(_check_content_min_length(content))

        # Integrity checks
        md_path = doc.get("markdown_path", "")
        expected_hash = doc.get("content_hash", "")
        dv.add_check(_check_file_exists(base_path, md_path))
        dv.add_check(_check_hash_valid(base_path, md_path, expected_hash))

        return dv
    except Exception as e:
        logger.error(f"Failed to verify document {doc_id}: {e}")
        return None


def verify_all() -> VerificationReport:
    """Run full verification across all crawled regulatory data.

    Returns a VerificationReport. If no data exists, returns
    a report with has_data=False and a friendly message.
    """
    report = VerificationReport()

    # Check if data exists
    try:
        from src.storage.regulatory_markdown_storage import (
            get_regulatory_markdown_store,
        )

        md_store = get_regulatory_markdown_store()
        all_docs = md_store.list_documents()
    except Exception:
        all_docs = []

    try:
        from src.storage.regulatory_storage import get_regulatory_store

        result_store = get_regulatory_store()
        crawl_results = result_store.load_last_results()
    except Exception:
        crawl_results = None

    if not all_docs and not crawl_results:
        report.has_data = False
        report.no_data_message = (
            "尚未執行法規清單更新。請先執行「法規清單更新」指令以爬取法規資料，"
            "完成後即可在此查看資料驗證結果。"
        )
        return report

    report.has_data = True

    # Get base path for file checks
    try:
        base_path = md_store.base_path
    except Exception:
        base_path = Path("regulatory_markdown_storage")

    # Verify each document
    for doc_entry in all_docs:
        doc_id = doc_entry.get("doc_id", "")
        if not doc_id:
            continue

        dv = DocumentVerification(
            doc_id=doc_id,
            region=doc_entry.get("region", ""),
            agency=doc_entry.get("agency", ""),
            url=doc_entry.get("url", ""),
        )

        # Read content
        try:
            doc_full = md_store.get_document(doc_id)
            content = doc_full.get("content", "") if doc_full else ""
        except Exception:
            content = ""

        # Content quality checks
        dv.add_check(_check_content_not_empty(content))
        dv.add_check(_check_content_not_placeholder(content))
        dv.add_check(_check_content_not_error_page(content))
        dv.add_check(_check_content_has_structure(content))
        dv.add_check(_check_content_min_length(content))

        # Integrity checks
        md_path = doc_entry.get("markdown_path", "")
        expected_hash = doc_entry.get("content_hash", "")
        dv.add_check(_check_file_exists(base_path, md_path))
        dv.add_check(_check_hash_valid(base_path, md_path, expected_hash))

        report.documents.append(dv)

    # Cross-comparison checks
    registry_docs = md_store.registry.get("documents", []) if md_store else []
    report.cross_checks.append(
        _check_pipeline_consistency(crawl_results, registry_docs)
    )
    report.cross_checks.append(_check_orphan_files(base_path, registry_docs))
    report.cross_checks.append(_check_missing_files(base_path, registry_docs))

    # Compute summary counts
    report.total_documents = len(report.documents)
    for dv in report.documents:
        if dv.overall_status == "pass":
            report.passed_count += 1
        elif dv.overall_status == "warning":
            report.warning_count += 1
        else:
            report.failed_count += 1

    return report


def get_verification_summary() -> dict:
    """Quick verification summary for API responses.

    Returns a dict with counts and has_data flag.
    """
    report = verify_all()
    return {
        "has_data": report.has_data,
        "no_data_message": report.no_data_message,
        "verified_at": report.verified_at,
        "total_documents": report.total_documents,
        "passed_count": report.passed_count,
        "warning_count": report.warning_count,
        "failed_count": report.failed_count,
        "cross_checks_passed": sum(1 for c in report.cross_checks if c.passed),
        "cross_checks_total": len(report.cross_checks),
    }


# ============================================================
# Markdown Format (for Chainlit chat display)
# ============================================================


def format_verification_markdown(report: Optional[VerificationReport] = None) -> str:
    """Format verification report as Markdown for Chainlit chat display."""
    if report is None:
        report = verify_all()

    if not report.has_data:
        return f"🔍 **資料驗證結果**\n\n{report.no_data_message}"

    lines = [
        f"🔍 **資料驗證結果** （{report.verified_at[:19]}）\n",
        f"文件總數: **{report.total_documents}**\n",
        "### 驗證摘要\n",
        f"- 🟢 通過: {report.passed_count}",
        f"- 🟡 警告: {report.warning_count}",
        f"- 🔴 失敗: {report.failed_count}",
        "",
    ]

    # Cross checks
    if report.cross_checks:
        lines.append("### 交叉比對結果\n")
        for cc in report.cross_checks:
            icon = "✅" if cc.passed else "❌"
            lines.append(f"- {icon} {cc.message}")
        lines.append("")

    # Per-document results
    if report.documents:
        lines.append("### 各文件驗證詳情\n")
        lines.append("| 地區 | 機構 | 狀態 | 問題 |")
        lines.append("|------|------|------|------|")
        for dv in report.documents:
            status_icon = {"pass": "🟢", "warning": "🟡", "fail": "🔴"}.get(
                dv.overall_status, "⚪"
            )
            issues = [c.message for c in dv.checks if not c.passed]
            issue_text = "; ".join(issues[:2]) if issues else "—"
            lines.append(
                f"| {dv.region} | {dv.agency} | {status_icon} | {issue_text} |"
            )

    return "\n".join(lines)
