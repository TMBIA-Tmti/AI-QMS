"""
AI-QMS — Regulatory Markdown Storage
=====================================

Independent Markdown DB for crawled regulatory data.
Completely separate from the QMS document DB (markdown_storage/).

Directory structure:
    regulatory_markdown_storage/
    ├── metadata/
    │   └── regulatory_registry.json
    └── documents/
        ├── Taiwan/
        │   ├── TFDA_20260227_143000.md
        │   └── MOHW_20260227_143005.md
        ├── USA/
        │   ├── FDA_20260227_143010.md
        │   └── ...
        └── ...
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PATH = "regulatory_markdown_storage"


class RegulatoryMarkdownStorage:
    """
    Independent Markdown DB for crawled regulatory documents.
    Mirrors the pattern of MarkdownStorageManager but is fully standalone.
    """

    def __init__(self, base_path: str = _DEFAULT_BASE_PATH):
        self.base_path = Path(base_path)
        self.documents_path = self.base_path / "documents"
        self.metadata_path = self.base_path / "metadata"
        self.registry_file = self.metadata_path / "regulatory_registry.json"

        self._ensure_directories()
        self._load_registry()

    # ============================================================
    # Internal helpers
    # ============================================================

    def _ensure_directories(self) -> None:
        """Create directory structure if not exists."""
        self.documents_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> None:
        """Load regulatory registry from file."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self.registry: dict = json.load(f)
            except Exception:
                logger.warning("Failed to load regulatory registry, creating new one.")
                self._init_empty_registry()
        else:
            self._init_empty_registry()

    def _init_empty_registry(self) -> None:
        """Create an empty registry."""
        self.registry = {
            "registry_version": "1.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "document_count": 0,
            "next_id": 1,
            "documents": [],
        }
        self._save_registry()

    def _save_registry(self) -> None:
        """Save registry to file with atomic write."""
        self.registry["last_updated"] = datetime.now(timezone.utc).isoformat()
        active_docs = [
            d for d in self.registry["documents"] if d.get("status") != "deleted"
        ]
        self.registry["document_count"] = len(active_docs)
        self._atomic_write_json(self.registry_file, self.registry)

    def _atomic_write_json(self, file_path: Path, data: dict) -> None:
        """Atomic write for JSON files."""
        temp_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e

    def _atomic_write_text(self, file_path: Path, content: str) -> None:
        """Atomic write for text/markdown files."""
        temp_path = file_path.with_suffix(".md.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(temp_path, file_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e

    def _calculate_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content."""
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use as directory/file name."""
        return re.sub(r"[^\w\-]", "_", name)

    def _next_doc_id(self) -> str:
        """Generate next sequential doc_id."""
        next_id = self.registry.get("next_id", 1)
        doc_id = f"reg_{next_id:04d}"
        self.registry["next_id"] = next_id + 1
        return doc_id

    # ============================================================
    # Save operations
    # ============================================================

    def save_regulatory_document(
        self,
        region: str,
        agency: str,
        agency_name: str,
        title: str,
        url: str,
        markdown_content: str,
        crawl_status: str = "success",
        has_pdf: bool = False,
        pdf_urls: Optional[list] = None,
        note: str = "",
        failure_reason: Optional[str] = None,
    ) -> dict:
        """Save a single crawled regulatory document.

        Args:
            region: Region name (e.g., "台灣 (Taiwan)")
            agency: Agency code (e.g., "TFDA")
            agency_name: Full agency name
            title: Document/page title
            url: Source URL
            markdown_content: Crawled markdown content
            crawl_status: "success" or "failed"
            has_pdf: Whether PDFs were found
            pdf_urls: List of PDF download URLs
            note: Additional notes

        Returns:
            dict with 'success', 'doc_id', 'path' keys
        """
        doc_id = self._next_doc_id()
        timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")

        # Create region subdirectory
        safe_region = self._sanitize_name(region)
        safe_agency = self._sanitize_name(agency)
        region_dir = self.documents_path / safe_region
        region_dir.mkdir(parents=True, exist_ok=True)

        # Build markdown file
        filename = f"{safe_agency}_{ts_str}.md"
        filepath = region_dir / filename
        relative_path = str(filepath.relative_to(self.base_path))

        # Write markdown with header
        header = (
            f"# {region} — {agency} ({agency_name})\n"
            f"來源: {url}\n"
            f"爬取時間: {timestamp.isoformat()}\n"
            f"狀態: {crawl_status}\n\n---\n\n"
        )
        full_content = header + markdown_content
        self._atomic_write_text(filepath, full_content)
        content_hash = self._calculate_hash(full_content)

        # Create registry entry
        entry = {
            "doc_id": doc_id,
            "region": region,
            "agency": agency,
            "agency_name": agency_name,
            "title": title,
            "url": url,
            "crawl_timestamp": timestamp.isoformat(),
            "crawl_status": crawl_status,
            "failure_reason": failure_reason,
            "markdown_path": relative_path,
            "content_hash": content_hash,
            "has_pdf": has_pdf,
            "pdf_urls": pdf_urls or [],
            "status": "active",
            "deleted_at": None,
            "note": note,
        }
        self.registry["documents"].append(entry)
        self._save_registry()

        logger.info(
            f"Saved regulatory doc {doc_id}: {region}/{agency} -> {relative_path}"
        )
        return {"success": True, "doc_id": doc_id, "path": str(filepath)}

    def save_from_crawl_results(self, crawl_results: dict) -> dict:
        """Batch save from crawler output. Only saves successful crawls with content.

        Before saving, soft-deletes all existing active documents from the same
        regions that appear in the crawl results, so old versions are replaced.

        Args:
            crawl_results: dict with 'results' list and 'summary' dict
                Each result item has keys:
                    region, agency, agency_name, url, title, content_markdown,
                    crawl_status, failure_reason, has_pdf, pdf_urls,
                    crawl_timestamp, crawl_duration_seconds, note

        Returns:
            dict with 'saved_count', 'skipped_count', 'doc_ids', 'replaced_count'
        """
        results = crawl_results.get("results", [])
        saved_count = 0
        skipped_count = 0
        replaced_count = 0
        doc_ids = []

        # Collect regions from successful crawl results
        crawled_regions = set()
        for r in results:
            if r.get("crawl_status") == "success" and r.get("content_markdown"):
                region = r.get("region", "")
                if region:
                    crawled_regions.add(region)

        # Soft-delete old documents from these regions before saving new ones
        for region in crawled_regions:
            old_docs = self.delete_by_region(region)
            replaced_count += old_docs.get("deleted_count", 0)

        if replaced_count > 0:
            # Purge deleted files immediately to free disk space
            self.purge_deleted()
            logger.info(
                f"Replaced {replaced_count} old docs from regions: {crawled_regions}"
            )

        for r in results:
            status = r.get("crawl_status", "")
            content = r.get("content_markdown", "")

            if status != "success" or not content:
                skipped_count += 1
                continue

            result = self.save_regulatory_document(
                region=r.get("region", "Unknown"),
                agency=r.get("agency", "Unknown"),
                agency_name=r.get("agency_name", ""),
                title=r.get("title", ""),
                url=r.get("url", ""),
                markdown_content=content,
                crawl_status=status,
                has_pdf=r.get("has_pdf", False),
                pdf_urls=r.get("pdf_urls", []),
                note=r.get("note", ""),
                failure_reason=r.get("failure_reason"),
            )

            if result.get("success"):
                saved_count += 1
                doc_ids.append(result["doc_id"])
            else:
                skipped_count += 1

        logger.info(
            f"Batch save complete: {saved_count} saved, {skipped_count} skipped, {replaced_count} old docs replaced"
        )
        return {
            "saved_count": saved_count,
            "skipped_count": skipped_count,
            "replaced_count": replaced_count,
            "doc_ids": doc_ids,
        }

    # ============================================================
    # Query operations
    # ============================================================

    def list_documents(
        self, region: Optional[str] = None, status: str = "active"
    ) -> list:
        """List documents, optionally filtered by region and status.

        Args:
            region: Filter by region name (None = all regions)
            status: Filter by status ("active", "deleted", "all")

        Returns:
            list of document entry dicts (with added 'index' field)
        """
        docs = self.registry.get("documents", [])
        result = []
        for i, doc in enumerate(docs):
            if status != "all" and doc.get("status", "active") != status:
                continue
            if region and doc.get("region", "") != region:
                continue
            entry = dict(doc)
            entry["index"] = i
            result.append(entry)
        return result

    def get_document(self, doc_id: str) -> Optional[dict]:
        """Get full document content + metadata by doc_id.

        Returns:
            dict with all metadata fields + 'content' key, or None
        """
        for doc in self.registry.get("documents", []):
            if doc.get("doc_id") == doc_id:
                entry = dict(doc)
                # Read markdown content
                md_path = doc.get("markdown_path", "")
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

    def get_document_by_url(self, url: str, status: str = "active") -> Optional[dict]:
        """Get the most recent document matching a URL.

        Used by the crawler to retrieve previous content on HTTP 304 Not Modified,
        so the actual content can be preserved instead of a placeholder string.

        Args:
            url: Source URL to match
            status: Filter by status ("active", "deleted", "all")

        Returns:
            dict with all metadata fields + 'content' key, or None
        """
        best_match: Optional[dict] = None
        for doc in self.registry.get("documents", []):
            if status != "all" and doc.get("status", "active") != status:
                continue
            if doc.get("url", "") != url:
                continue
            # Pick the most recent one by crawl_timestamp
            if best_match is None or doc.get("crawl_timestamp", "") > best_match.get(
                "crawl_timestamp", ""
            ):
                best_match = doc

        if best_match is None:
            return None

        entry = dict(best_match)
        md_path = best_match.get("markdown_path", "")
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

    def search_documents(self, keyword: str, status: str = "active") -> list:
        """Search documents by keyword across region, agency, agency_name, title fields.

        Args:
            keyword: Search keyword (case-insensitive)
            status: Filter by status ("active", "deleted", "all")

        Returns:
            list of matching document entry dicts (with 'index' field)
        """
        kw_lower = keyword.lower().strip()
        docs = self.registry.get("documents", [])
        result = []
        for i, doc in enumerate(docs):
            if status != "all" and doc.get("status", "active") != status:
                continue
            searchable = (
                f"{doc.get('region', '')} {doc.get('agency', '')} "
                f"{doc.get('agency_name', '')} {doc.get('title', '')}"
            ).lower()
            if kw_lower in searchable:
                entry = dict(doc)
                entry["index"] = i
                result.append(entry)
        return result

    # ============================================================
    # Delete operations
    # ============================================================

    def delete_document(self, doc_id: str) -> dict:
        """Soft-delete a document by doc_id.

        Returns:
            dict with 'success', 'doc_id', 'region', 'agency', 'title'
        """
        for doc in self.registry.get("documents", []):
            if doc.get("doc_id") == doc_id and doc.get("status") != "deleted":
                doc["status"] = "deleted"
                doc["deleted_at"] = datetime.now(timezone.utc).isoformat()
                self._save_registry()
                logger.info(f"Soft-deleted regulatory doc {doc_id}")
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "region": doc.get("region", ""),
                    "agency": doc.get("agency", ""),
                    "title": doc.get("title", ""),
                }
        return {
            "success": False,
            "error": f"Document {doc_id} not found or already deleted.",
        }

    def delete_by_keyword(self, keyword: str) -> dict:
        """Soft-delete all active documents matching a keyword.

        Args:
            keyword: Search keyword (case-insensitive)

        Returns:
            dict with 'deleted_count', 'deleted_items'
        """
        kw_lower = keyword.lower().strip()
        deleted_items = []
        now = datetime.now(timezone.utc).isoformat()

        for doc in self.registry.get("documents", []):
            if doc.get("status") == "deleted":
                continue
            searchable = (
                f"{doc.get('region', '')} {doc.get('agency', '')} "
                f"{doc.get('agency_name', '')} {doc.get('title', '')}"
            ).lower()
            if kw_lower in searchable:
                doc["status"] = "deleted"
                doc["deleted_at"] = now
                deleted_items.append(
                    {
                        "doc_id": doc.get("doc_id", ""),
                        "region": doc.get("region", ""),
                        "agency": doc.get("agency", ""),
                        "title": doc.get("title", ""),
                    }
                )

        if deleted_items:
            self._save_registry()
            logger.info(f"Soft-deleted {len(deleted_items)} docs matching '{keyword}'")

        return {
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
        }

    def delete_by_indices(self, indices: list) -> dict:
        """Soft-delete documents by their index positions in the full registry.

        Args:
            indices: list of integer indices (0-based, from list_documents output)

        Returns:
            dict with 'deleted_count', 'deleted_items'
        """
        indices_set = set(indices)
        deleted_items = []
        now = datetime.now(timezone.utc).isoformat()
        docs = self.registry.get("documents", [])

        for i in indices_set:
            if 0 <= i < len(docs):
                doc = docs[i]
                if doc.get("status") != "deleted":
                    doc["status"] = "deleted"
                    doc["deleted_at"] = now
                    deleted_items.append(
                        {
                            "doc_id": doc.get("doc_id", ""),
                            "region": doc.get("region", ""),
                            "agency": doc.get("agency", ""),
                            "title": doc.get("title", ""),
                        }
                    )

        if deleted_items:
            self._save_registry()
            logger.info(f"Soft-deleted {len(deleted_items)} docs by indices")

        return {
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
        }

    def delete_by_region(self, region: str) -> dict:
        """Soft-delete all active documents from a specific region.

        Args:
            region: Region name (e.g., "台灣 (Taiwan)")

        Returns:
            dict with 'deleted_count', 'deleted_items'
        """
        deleted_items = []
        now = datetime.now(timezone.utc).isoformat()

        for doc in self.registry.get("documents", []):
            if doc.get("status") == "deleted":
                continue
            if doc.get("region", "") == region:
                doc["status"] = "deleted"
                doc["deleted_at"] = now
                deleted_items.append(
                    {
                        "doc_id": doc.get("doc_id", ""),
                        "region": doc.get("region", ""),
                        "agency": doc.get("agency", ""),
                        "title": doc.get("title", ""),
                    }
                )

        if deleted_items:
            self._save_registry()
            logger.info(
                f"Soft-deleted {len(deleted_items)} docs from region '{region}'"
            )

        return {
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
        }

    def cleanup_non_selected_regions(self, selected_regions: list) -> dict:
        """Soft-delete all active documents from regions NOT in the selected list.

        Args:
            selected_regions: List of region names to KEEP

        Returns:
            dict with 'deleted_count', 'deleted_items', 'kept_regions'
        """
        selected_set = set(selected_regions)
        deleted_items = []
        now = datetime.now(timezone.utc).isoformat()

        for doc in self.registry.get("documents", []):
            if doc.get("status") == "deleted":
                continue
            if doc.get("region", "") not in selected_set:
                doc["status"] = "deleted"
                doc["deleted_at"] = now
                deleted_items.append(
                    {
                        "doc_id": doc.get("doc_id", ""),
                        "region": doc.get("region", ""),
                        "agency": doc.get("agency", ""),
                        "title": doc.get("title", ""),
                    }
                )

        if deleted_items:
            self._save_registry()
            removed_regions = set(item["region"] for item in deleted_items)
            logger.info(
                f"Cleanup: soft-deleted {len(deleted_items)} docs from non-selected regions: {removed_regions}"
            )

        return {
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
            "kept_regions": list(selected_set),
        }

    def restore_document(self, doc_id: str) -> dict:
        """Restore a soft-deleted document.

        Returns:
            dict with 'success', 'doc_id'
        """
        for doc in self.registry.get("documents", []):
            if doc.get("doc_id") == doc_id and doc.get("status") == "deleted":
                doc["status"] = "active"
                doc["deleted_at"] = None
                self._save_registry()
                logger.info(f"Restored regulatory doc {doc_id}")
                return {"success": True, "doc_id": doc_id}
        return {
            "success": False,
            "error": f"Document {doc_id} not found or not deleted.",
        }

    def purge_deleted(self) -> dict:
        """Permanently remove all soft-deleted documents and their markdown files.

        Returns:
            dict with 'purged_count', 'purged_items'
        """
        docs = self.registry.get("documents", [])
        remaining = []
        purged_items = []

        for doc in docs:
            if doc.get("status") == "deleted":
                # Delete markdown file
                md_path = doc.get("markdown_path", "")
                if md_path:
                    full_path = self.base_path / md_path
                    if full_path.exists():
                        try:
                            full_path.unlink()
                            logger.info(f"Purged file: {md_path}")
                        except Exception as e:
                            logger.warning(f"Failed to purge file {md_path}: {e}")
                purged_items.append(
                    {
                        "doc_id": doc.get("doc_id", ""),
                        "region": doc.get("region", ""),
                        "agency": doc.get("agency", ""),
                    }
                )
            else:
                remaining.append(doc)

        self.registry["documents"] = remaining
        self._save_registry()

        # Clean up empty region directories
        if self.documents_path.exists():
            for region_dir in self.documents_path.iterdir():
                if region_dir.is_dir() and not any(region_dir.iterdir()):
                    try:
                        region_dir.rmdir()
                        logger.info(f"Removed empty region dir: {region_dir.name}")
                    except Exception:
                        pass

        logger.info(f"Purged {len(purged_items)} deleted documents")
        return {
            "purged_count": len(purged_items),
            "purged_items": purged_items,
        }

    # ============================================================
    # Stats & utility
    # ============================================================

    def get_stats(self) -> dict:
        """Return counts by region, total active, total deleted.

        Returns:
            dict with 'total_active', 'total_deleted', 'by_region'
        """
        docs = self.registry.get("documents", [])
        active = 0
        deleted = 0
        by_region: dict = {}

        for doc in docs:
            region = doc.get("region", "Unknown")
            status = doc.get("status", "active")

            if status == "deleted":
                deleted += 1
                continue

            active += 1
            if region not in by_region:
                by_region[region] = 0
            by_region[region] += 1

        return {
            "total_active": active,
            "total_deleted": deleted,
            "by_region": by_region,
        }

    def get_all_regions(self) -> list:
        """Return sorted list of unique regions from active documents."""
        docs = self.registry.get("documents", [])
        regions = set()
        for doc in docs:
            if doc.get("status", "active") == "active":
                regions.add(doc.get("region", ""))
        return sorted(regions)

    def get_document_count(self) -> int:
        """Get total number of active documents."""
        return sum(
            1
            for d in self.registry.get("documents", [])
            if d.get("status", "active") == "active"
        )

    # ============================================================
    # Upload reminders & regulation listing (for MdsapMarkdownStorage)
    # ============================================================

    # Mapping: cross-examination profile → region folder + display label
    _EXPECTED_REGULATIONS = {
        "QMSR": {
            "region": "USA",
            "name_en": "USA (FDA QMSR)",
            "name_zh": "美國 (FDA QMSR)",
        },
        "EU_MDR": {
            "region": "EU",
            "name_en": "EU (MDR 2017/745)",
            "name_zh": "歐盟 (MDR 2017/745)",
        },
        "TFDA": {
            "region": "Taiwan",
            "name_en": "Taiwan (TFDA)",
            "name_zh": "台灣 (TFDA)",
        },
        "HC": {
            "region": "Canada",
            "name_en": "Canada (HC/MDSAP)",
            "name_zh": "加拿大 (HC/MDSAP)",
        },
        "PMDA": {
            "region": "Japan",
            "name_en": "Japan (PMDA)",
            "name_zh": "日本 (PMDA)",
        },
        "ANVISA": {
            "region": "Brazil",
            "name_en": "Brazil (ANVISA)",
            "name_zh": "巴西 (ANVISA)",
        },
        "TGA": {
            "region": "Australia",
            "name_en": "Australia (TGA)",
            "name_zh": "澳洲 (TGA)",
        },
        "ISO_13485": {
            "region": "ISO_Standards",
            "name_en": "ISO 13485:2016",
            "name_zh": "ISO 13485:2016",
        },
        "MDSAP": {
            "region": "MDSAP",
            "name_en": "MDSAP (Single Audit Program)",
            "name_zh": "MDSAP（醫療器材單一稽核方案）",
        },
    }

    def get_upload_reminders(self) -> list[dict]:
        """Get list of regulations that still need user-uploaded full text.

        Checks each of the 7+1 expected regulations. If no uploaded document
        exists under {region}/uploads/, it's added to the reminders list.

        Returns:
            List of dicts: [{"regulation_id", "name_en", "name_zh", "region", "has_uploaded": False}]
        """
        reminders = []
        for reg_id, info in self._EXPECTED_REGULATIONS.items():
            region_dir = self.documents_path / info["region"] / "uploads"
            has_uploaded = False
            if region_dir.exists():
                # Any non-empty file counts as uploaded
                for f in region_dir.iterdir():
                    if f.is_file() and f.stat().st_size > 0:
                        has_uploaded = True
                        break
            if not has_uploaded:
                reminders.append(
                    {
                        "regulation_id": reg_id,
                        "name_en": info["name_en"],
                        "name_zh": info["name_zh"],
                        "region": info["region"],
                        "has_uploaded": False,
                    }
                )
        return reminders

    def list_all_regulations(self) -> list[dict]:
        """List all 7+1 regulations with their availability status.

        Returns:
            List of dicts with regulation_id, name, region, status fields.
        """
        result = []
        for reg_id, info in self._EXPECTED_REGULATIONS.items():
            region_dir = self.documents_path / info["region"]
            has_predefined = (
                (region_dir / "predefined").exists()
                and any((region_dir / "predefined").iterdir())
                if (region_dir / "predefined").exists()
                else False
            )
            has_uploaded = False
            upload_dir = region_dir / "uploads"
            if upload_dir.exists():
                has_uploaded = any(
                    f.is_file() and f.stat().st_size > 0 for f in upload_dir.iterdir()
                )
            has_crawled = any(
                doc.get("region", "").endswith(f"({info['region']})")
                or doc.get("region", "") == info["region"]
                for doc in self.registry.get("documents", [])
                if doc.get("status") != "deleted"
            )
            result.append(
                {
                    "regulation_id": reg_id,
                    "name_en": info["name_en"],
                    "name_zh": info["name_zh"],
                    "region": info["region"],
                    "has_predefined": has_predefined,
                    "has_uploaded": has_uploaded,
                    "has_crawled": has_crawled,
                    "status": "complete"
                    if (has_uploaded or has_crawled)
                    else "needs_upload",
                }
            )
        return result

    def save_uploaded_regulation(
        self, regulation_id: str, filename: str, content: str
    ) -> dict:
        """Save a user-uploaded regulation document.

        The file is placed under ``{region}/uploads/`` inside the unified
        ``regulatory_markdown_storage/`` directory.

        Args:
            regulation_id: Profile ID (e.g. 'QMSR', 'EU_MDR', 'TFDA')
            filename: Original filename
            content: Markdown content

        Returns:
            dict with 'success', 'path', 'regulation_id'
        """
        info = self._EXPECTED_REGULATIONS.get(regulation_id)
        if not info:
            return {
                "success": False,
                "error": f"Unknown regulation_id: {regulation_id}",
            }

        upload_dir = self.documents_path / info["region"] / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_name = self._sanitize_name(Path(filename).stem)
        ts = datetime.now().strftime("%Y%m%d")
        dest = upload_dir / f"{regulation_id}_uploaded_{ts}_{safe_name}.md"

        self._atomic_write_text(dest, content)
        logger.info(f"Saved uploaded regulation: {dest}")

        return {
            "success": True,
            "path": str(dest),
            "regulation_id": regulation_id,
        }

    def export_predefined_profiles(self) -> dict:
        """Export all predefined regulation profiles as Markdown files.

        Creates ``{country}/predefined/{REG_ID}_profile.md`` for each
        profile registered in ``compliance_rules.PREDEFINED_REGULATIONS``.

        Returns:
            dict with 'exported_count', 'profiles' list
        """
        try:
            from src.analysis.compliance_rules import get_all_profiles

            profiles = get_all_profiles()
        except ImportError:
            return {
                "exported_count": 0,
                "profiles": [],
                "error": "compliance_rules not available",
            }

        exported = []
        for reg_id, profile in profiles.items():
            info = self._EXPECTED_REGULATIONS.get(reg_id)
            if not info:
                continue
            pred_dir = self.documents_path / info["region"] / "predefined"
            pred_dir.mkdir(parents=True, exist_ok=True)
            dest = pred_dir / f"{reg_id}_profile.md"

            # Build markdown from profile
            lines = [
                f"# {profile.regulation_name}",
                f"**Regulation ID**: {profile.regulation_id}",
                f"**Country/Region**: {profile.country}",
                "",
                "## ISO 13485 Clause Mapping",
                "",
            ]
            for clause_id, mapping in profile.clause_mappings.items():
                lines.append(f"### {clause_id}")
                lines.append(f"- **Local Requirement**: {mapping.local_requirement}")
                lines.append(f"- **Mandatory**: {mapping.mandatory}")
                if mapping.guidance_notes:
                    lines.append(f"- **Notes**: {mapping.guidance_notes}")
                lines.append("")

            if profile.unique_requirements:
                lines.append("## Unique Requirements")
                lines.append("")
                for req in profile.unique_requirements:
                    lines.append(f"- {req}")
                lines.append("")

            self._atomic_write_text(dest, "\n".join(lines))
            exported.append({"regulation_id": reg_id, "path": str(dest)})

        return {"exported_count": len(exported), "profiles": exported}


# ============================================================
# Singleton accessor
# ============================================================

_reg_md_store_instance: Optional[RegulatoryMarkdownStorage] = None


def get_regulatory_markdown_store() -> RegulatoryMarkdownStorage:
    """Get or create singleton RegulatoryMarkdownStorage instance."""
    global _reg_md_store_instance
    if _reg_md_store_instance is None:
        _reg_md_store_instance = RegulatoryMarkdownStorage()
    return _reg_md_store_instance
