"""
AI-QMS — Phase 6: Source Verification
======================================

Batch URL re-verification at the end of the pipeline.

After Phase 5 completes, this phase re-fetches all URLs referenced
in the regulatory data used during analysis and verifies:
  1. URL is still accessible (HTTP 200)
  2. Content hasn't changed significantly since crawl time
  3. Flags any broken or significantly changed sources

No LLM involved — pure HTTP verification.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from src.analysis.state import (
    Phase,
    PhaseStatus,
    PhaseResult,
    PipelineState,
)


__all__ = [
    "run_source_check",
    "verify_url",
]


# ============================================================
# URL verification
# ============================================================


def verify_url(
    url: str,
    expected_hash: Optional[str] = None,
    timeout: int = 15,
) -> dict:
    """Verify a single URL is accessible and content hasn't changed.

    Args:
        url: URL to verify
        expected_hash: SHA-256 hash of previously crawled content (optional)
        timeout: HTTP request timeout in seconds

    Returns:
        dict with verification results
    """
    import urllib.request
    import urllib.error

    result = {
        "url": url,
        "accessible": False,
        "status_code": None,
        "content_changed": None,
        "error": None,
        "checked_at": time.time(),
    }

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )
        # Use HEAD first for speed, fall back to GET if needed
        req.method = "HEAD"

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status_code"] = resp.status
            result["accessible"] = resp.status == 200

        # If we have an expected hash and URL is accessible, do a GET to verify content
        if expected_hash and result["accessible"]:
            req.method = "GET"
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content = resp.read()
                    current_hash = hashlib.sha256(content).hexdigest()
                    result["content_changed"] = current_hash != expected_hash
                    result["current_hash"] = current_hash
            except Exception:
                # Can't verify content, but URL is accessible
                result["content_changed"] = None

    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["accessible"] = False
        result["error"] = f"HTTP {e.code}: {e.reason}"

    except urllib.error.URLError as e:
        result["accessible"] = False
        result["error"] = f"URL Error: {str(e.reason)}"

    except Exception as e:
        result["accessible"] = False
        result["error"] = str(e)

    return result


def _collect_urls_from_pipeline(state: PipelineState) -> list[dict]:
    """Collect all unique URLs referenced in the pipeline's regulatory data.

    Returns:
        List of {url, doc_id, content_hash} dicts
    """
    try:
        from src.storage.regulatory_markdown_storage import (
            get_regulatory_markdown_store,
        )

        store = get_regulatory_markdown_store()
        all_docs = store.list_documents(status="active")

        # Collect unique URLs with their metadata
        seen_urls: set[str] = set()
        url_entries: list[dict] = []

        for doc in all_docs:
            url = doc.get("url", "")
            if url and url.startswith("http") and url not in seen_urls:
                seen_urls.add(url)
                url_entries.append(
                    {
                        "url": url,
                        "doc_id": doc.get("doc_id", ""),
                        "content_hash": doc.get("content_hash", ""),
                        "region": doc.get("region", ""),
                        "agency": doc.get("agency", ""),
                    }
                )

        return url_entries

    except Exception:
        return []


# ============================================================
# Phase execution
# ============================================================


def _lang_key(lang: str) -> str:
    """Normalize a UI language code to a key (zh / en / ja)."""
    if not lang:
        return "zh"
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("ja"):
        return "ja"
    if lang.startswith("en"):
        return "en"
    return "en"


def run_source_check(
    state: PipelineState,
    max_urls: int = 50,
    timeout_per_url: int = 15,
    skip_content_verify: bool = False,
    lang: str = "zh-TW",
) -> PhaseResult:
    """Execute Phase 6 source verification — batch URL re-check.

    Runs after all other phases complete. Verifies that the crawled
    regulatory data sources are still accessible.

    Args:
        state: Pipeline state
        max_urls: Maximum number of URLs to verify (to avoid excessive requests)
        timeout_per_url: HTTP timeout per URL in seconds
        skip_content_verify: If True, only check accessibility (HEAD), skip content hash
        lang: UI language code (e.g., 'zh-TW', 'en', 'ja')

    Returns:
        PhaseResult with verification summary
    """
    lk = _lang_key(lang)
    _no_urls_msg = {
        "zh": "No regulatory URLs found to verify",
        "en": "No regulatory URLs found to verify",
        "ja": "検証対象の規制URLが見つかりませんでした",
    }[lk]

    phase_result = PhaseResult(
        phase=Phase.SOURCE_CHECK.value,
        started_at=time.time(),
    )

    try:
        # Collect URLs
        url_entries = _collect_urls_from_pipeline(state)

        if not url_entries:
            phase_result.status = PhaseStatus.SKIPPED.value
            phase_result.output = {"reason": _no_urls_msg}
            phase_result.completed_at = time.time()
            return phase_result

        # Limit to max_urls
        if len(url_entries) > max_urls:
            url_entries = url_entries[:max_urls]

        # Verify each URL
        results: list[dict] = []
        accessible_count = 0
        broken_count = 0
        changed_count = 0

        for entry in url_entries:
            expected_hash = (
                entry.get("content_hash") if not skip_content_verify else None
            )
            verification = verify_url(
                url=entry["url"],
                expected_hash=expected_hash,
                timeout=timeout_per_url,
            )
            verification["doc_id"] = entry.get("doc_id", "")
            verification["region"] = entry.get("region", "")
            verification["agency"] = entry.get("agency", "")
            results.append(verification)

            if verification["accessible"]:
                accessible_count += 1
                if verification.get("content_changed") is True:
                    changed_count += 1
            else:
                broken_count += 1

        # Build summary
        summary = {
            "total_urls": len(results),
            "accessible": accessible_count,
            "broken": broken_count,
            "content_changed": changed_count,
            "verification_results": results,
        }

        # Store summary in pipeline state
        state.source_check_summary = summary

        phase_result.status = PhaseStatus.COMPLETED.value
        phase_result.output = summary

    except Exception as e:
        phase_result.status = PhaseStatus.FAILED.value
        phase_result.error = str(e)

    phase_result.completed_at = time.time()
    return phase_result
