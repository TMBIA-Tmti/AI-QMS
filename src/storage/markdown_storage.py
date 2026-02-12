"""
AI-QMS Phase 1 Document Control - Markdown Storage Manager
Manages converted Markdown documents with version control and registry.

v2.4.8 Updates:
- Added atomic write operations (write to .tmp then os.replace)
- Added compute_sha256(file_path) for file hash calculation
- Added save_ocr_document() for auto-save after OCR
- Added search_documents() for full-text search across documents
"""

import os
import json
import hashlib
import tempfile
import re
import logging
from pathlib import Path
from typing import TypedDict, Optional, Literal, List
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# Type Definitions
# ============================================================


class VersionEntry(TypedDict):
    """Version entry for a document"""

    version: str
    markdown_path: str
    original_file: str
    created_at: str
    created_by: str
    ocr_provider: str
    ocr_confidence: float
    hash: str


class DocumentEntry(TypedDict):
    """Document entry in registry"""

    doc_id: str
    title: str
    current_version: str
    versions: list[VersionEntry]
    doc_type: Literal["SOP", "WI", "FORM", "DHF", "OTHER"]
    status: Literal["active", "obsolete", "draft"]
    related_documents: list[str]


class DocumentRegistry(TypedDict):
    """Document registry structure"""

    registry_version: str
    last_updated: str
    document_count: int
    documents: list[DocumentEntry]


# ============================================================
# Constants
# ============================================================

DOC_TYPES = ["SOP", "WI", "FORM", "DHF", "OTHER"]
POC_DOCUMENT_LIMIT = 9999  # v2.5.0: Removed 20-file limit per user request


# ============================================================
# Markdown Storage Manager
# ============================================================


class MarkdownStorageManager:
    """
    Manages Markdown document storage with version control.
    Enforces POC document limit of 20 documents.
    """

    def __init__(self, base_path: str = "markdown_storage"):
        """
        Initialize the Markdown Storage Manager.

        Args:
            base_path: Base directory for markdown storage
        """
        self.base_path = Path(base_path)
        self.documents_path = self.base_path / "documents"
        self.metadata_path = self.base_path / "metadata"
        self.ocr_artifacts_path = self.base_path / "ocr_artifacts"
        self.index_path = self.base_path / "index"

        self.registry_file = self.metadata_path / "document_registry.json"

        self._ensure_directories()
        self._load_registry()

    def _ensure_directories(self) -> None:
        """Create directory structure if not exists"""
        # Document type directories
        for doc_type in DOC_TYPES:
            (self.documents_path / doc_type).mkdir(parents=True, exist_ok=True)

        # Metadata directory
        self.metadata_path.mkdir(parents=True, exist_ok=True)

        # OCR artifacts directories
        (self.ocr_artifacts_path / "images").mkdir(parents=True, exist_ok=True)
        (self.ocr_artifacts_path / "tables").mkdir(parents=True, exist_ok=True)
        (self.ocr_artifacts_path / "stamps").mkdir(parents=True, exist_ok=True)

        # Index directory
        (self.index_path / "vector_embeddings").mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> None:
        """Load document registry from file"""
        if self.registry_file.exists():
            with open(self.registry_file, "r", encoding="utf-8") as f:
                self.registry: DocumentRegistry = json.load(f)
        else:
            self.registry = DocumentRegistry(
                registry_version="1.0",
                last_updated=datetime.now().isoformat(),
                document_count=0,
                documents=[],
            )
            self._save_registry()

    def _save_registry(self) -> None:
        """Save document registry to file with atomic write"""
        self.registry["last_updated"] = datetime.now().isoformat()
        self.registry["document_count"] = len(self.registry["documents"])

        # Atomic write: write to temp file then replace
        self._atomic_write_json(self.registry_file, self.registry)

    def _atomic_write_json(self, file_path: Path, data: dict) -> None:
        """
        Atomic write for JSON files.
        Writes to a temp file first, then replaces the target file.
        This prevents corruption if the process is interrupted.
        """
        temp_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Atomic replace (works on Windows and Unix)
            os.replace(temp_path, file_path)
        except Exception as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            raise e

    def _atomic_write_text(self, file_path: Path, content: str) -> None:
        """
        Atomic write for text files (Markdown).
        Writes to a temp file first, then replaces the target file.
        """
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
        """Calculate SHA-256 hash of content"""
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

    def _get_next_version(self, current_version: str) -> str:
        """
        Calculate next version number.

        Args:
            current_version: Current version string (e.g., "1.0", "2.1")

        Returns:
            Next version string
        """
        try:
            parts = current_version.replace("v", "").split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return f"{major}.{minor + 1}"
        except (ValueError, IndexError):
            return "1.1"

    def get_document_count(self) -> int:
        """Get total number of documents in registry"""
        return len(self.registry["documents"])

    def check_document_limit(self, limit: int = POC_DOCUMENT_LIMIT) -> bool:
        """
        Check if under document limit.

        Args:
            limit: Maximum document count (default: 20 for POC)

        Returns:
            True if under limit, False if at or over limit
        """
        return self.get_document_count() < limit

    def get_remaining_slots(self, limit: int = POC_DOCUMENT_LIMIT) -> int:
        """Get number of remaining document slots"""
        return max(0, limit - self.get_document_count())

    def document_exists(self, doc_id: str) -> bool:
        """Check if document exists in registry"""
        return any(doc["doc_id"] == doc_id for doc in self.registry["documents"])

    def save_document(
        self,
        doc_id: str,
        title: str,
        doc_type: str,
        markdown_content: str,
        original_file: str,
        ocr_provider: str = "unknown",
        ocr_confidence: float = 0.0,
        user_id: str = "system",
        initial_version: str = None,
    ) -> dict:
        """
        Save a new document to storage.

        Args:
            doc_id: Document identifier (e.g., "SOP-001")
            title: Document title
            doc_type: Document type (SOP, WI, FORM, DHF, OTHER)
            markdown_content: Markdown content to save
            original_file: Path to original uploaded file
            ocr_provider: OCR provider used
            ocr_confidence: OCR confidence score
            user_id: User who created the document
            initial_version: OCR-detected version (e.g., "1", "2", "1.1").
                If provided, used instead of default "1.0".

        Returns:
            Dict with 'success', 'path', 'version' keys
        """
        # Check document limit
        if not self.check_document_limit():
            return {
                "success": False,
                "error": f"Document limit reached ({POC_DOCUMENT_LIMIT}). Cannot add new documents.",
                "remaining_slots": 0,
            }

        # Check if document already exists
        if self.document_exists(doc_id):
            return {
                "success": False,
                "error": f"Document {doc_id} already exists.",
            }

        # Validate doc_type
        if doc_type not in DOC_TYPES:
            doc_type = "OTHER"

        # Create markdown file — use OCR-detected version if provided
        version = initial_version if initial_version else "1.0"
        filename = f"{doc_id}_v{version}.md"
        file_path = self.documents_path / doc_type / filename

        # Write markdown content with atomic write
        self._atomic_write_text(file_path, markdown_content)

        # Calculate hash
        content_hash = self._calculate_hash(markdown_content)

        # Create version entry
        version_entry = VersionEntry(
            version=version,
            markdown_path=str(file_path.relative_to(self.base_path)),
            original_file=original_file,
            created_at=datetime.now().isoformat(),
            created_by=user_id,
            ocr_provider=ocr_provider,
            ocr_confidence=ocr_confidence,
            hash=content_hash,
        )

        # Create document entry
        doc_entry = DocumentEntry(
            doc_id=doc_id,
            title=title,
            current_version=version,
            versions=[version_entry],
            doc_type=doc_type,
            status="active",
            related_documents=[],
        )

        # Add to registry
        self.registry["documents"].append(doc_entry)
        self._save_registry()

        return {
            "success": True,
            "path": str(file_path),
            "version": version,
            "hash": content_hash,
            "remaining_slots": self.get_remaining_slots(),
        }

    def update_document(
        self,
        doc_id: str,
        markdown_content: str,
        original_file: str,
        ocr_provider: str = "unknown",
        ocr_confidence: float = 0.0,
        user_id: str = "system",
        explicit_version: str = None,
    ) -> dict:
        """
        Add a new version to an existing document.

        Args:
            doc_id: Document identifier
            markdown_content: New markdown content
            original_file: Path to original uploaded file
            ocr_provider: OCR provider used
            ocr_confidence: OCR confidence score
            user_id: User who updated the document
            explicit_version: v2.5.2 - If provided, use this version instead of auto-incrementing
                              (from OCR-detected version number on the document)

        Returns:
            Dict with 'success', 'path', 'version', 'previous_version' keys
        """
        # Find document
        doc_entry = None
        doc_index = -1
        for i, doc in enumerate(self.registry["documents"]):
            if doc["doc_id"] == doc_id:
                doc_entry = doc
                doc_index = i
                break

        if doc_entry is None:
            return {
                "success": False,
                "error": f"Document {doc_id} not found. Use save_document() for new documents.",
            }

        # Calculate new version
        previous_version = doc_entry["current_version"]
        # v2.5.2: Use OCR-detected version if provided, otherwise auto-increment
        if explicit_version:
            new_version = explicit_version.replace("v", "").replace("V", "")
        else:
            new_version = self._get_next_version(previous_version)

        # Create markdown file
        doc_type = doc_entry["doc_type"]
        filename = f"{doc_id}_v{new_version}.md"
        file_path = self.documents_path / doc_type / filename

        # Write markdown content with atomic write
        self._atomic_write_text(file_path, markdown_content)

        # Calculate hash
        content_hash = self._calculate_hash(markdown_content)

        # Create version entry
        version_entry = VersionEntry(
            version=new_version,
            markdown_path=str(file_path.relative_to(self.base_path)),
            original_file=original_file,
            created_at=datetime.now().isoformat(),
            created_by=user_id,
            ocr_provider=ocr_provider,
            ocr_confidence=ocr_confidence,
            hash=content_hash,
        )

        # Update document entry
        doc_entry["versions"].append(version_entry)
        doc_entry["current_version"] = new_version
        self.registry["documents"][doc_index] = doc_entry
        self._save_registry()

        # v2.6.0: Clean up old version files after successful version update
        # Keep the version entry in registry for audit trail, but delete actual files
        for old_ver in doc_entry.get("versions", [])[
            :-1
        ]:  # All versions except the latest
            if old_ver.get("files_removed"):
                continue  # Already cleaned up

            # Delete old markdown file
            old_md_path = old_ver.get("markdown_path", "")
            if old_md_path:
                full_md_path = self.base_path / old_md_path
                if full_md_path.exists():
                    try:
                        full_md_path.unlink()
                        logger.info(
                            f"v2.6.0: Deleted old version markdown: {old_md_path}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete old markdown {old_md_path}: {e}"
                        )

            # Delete old original file
            old_orig = old_ver.get("original_file", "")
            if old_orig:
                old_orig_path = Path(old_orig)
                if not old_orig_path.is_absolute():
                    old_orig_path = Path.cwd() / old_orig
                if old_orig_path.exists():
                    try:
                        old_orig_path.unlink()
                        logger.info(f"v2.6.0: Deleted old version original: {old_orig}")
                    except Exception as e:
                        logger.warning(f"Failed to delete old original {old_orig}: {e}")

            # Mark as cleaned up (keep entry for audit)
            old_ver["files_removed"] = True
            old_ver["files_removed_at"] = datetime.now().isoformat()

        # Save registry again with files_removed flags
        self._save_registry()

        return {
            "success": True,
            "path": str(file_path),
            "version": new_version,
            "previous_version": previous_version,
            "hash": content_hash,
        }

    def get_document(self, doc_id: str, version: Optional[str] = None) -> dict:
        """
        Get document content.

        Args:
            doc_id: Document identifier
            version: Specific version (uses current if None)

        Returns:
            Dict with 'success', 'content', 'metadata' keys
        """
        # Find document
        doc_entry = None
        for doc in self.registry["documents"]:
            if doc["doc_id"] == doc_id:
                doc_entry = doc
                break

        if doc_entry is None:
            return {"success": False, "error": f"Document {doc_id} not found"}

        # Find version
        target_version = version or doc_entry["current_version"]
        version_entry = None
        for v in doc_entry["versions"]:
            if v["version"] == target_version:
                version_entry = v
                break

        if version_entry is None:
            return {
                "success": False,
                "error": f"Version {target_version} not found for {doc_id}",
            }

        # Read content
        file_path = self.base_path / version_entry["markdown_path"]
        if not file_path.exists():
            return {"success": False, "error": f"Markdown file not found: {file_path}"}

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "success": True,
            "content": content,
            "metadata": {
                "doc_id": doc_id,
                "title": doc_entry["title"],
                "version": target_version,
                "doc_type": doc_entry["doc_type"],
                "status": doc_entry["status"],
                "created_at": version_entry["created_at"],
                "created_by": version_entry["created_by"],
                "ocr_provider": version_entry["ocr_provider"],
                "ocr_confidence": version_entry["ocr_confidence"],
                "hash": version_entry["hash"],
            },
        }

    def list_documents(self, doc_type: Optional[str] = None) -> list[dict]:
        """
        List all documents in registry.

        Args:
            doc_type: Filter by document type (optional)

        Returns:
            List of document summaries
        """
        documents = []
        for doc in self.registry["documents"]:
            if doc_type is None or doc["doc_type"] == doc_type:
                documents.append(
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "doc_type": doc["doc_type"],
                        "current_version": doc["current_version"],
                        "status": doc["status"],
                        "version_count": len(doc["versions"]),
                    }
                )
        return documents

    def get_version_history(self, doc_id: str) -> list[dict]:
        """
        Get version history for a document.

        Args:
            doc_id: Document identifier

        Returns:
            List of version entries
        """
        for doc in self.registry["documents"]:
            if doc["doc_id"] == doc_id:
                return doc["versions"]
        return []

    def set_document_status(self, doc_id: str, status: str) -> bool:
        """
        Set document status.

        Args:
            doc_id: Document identifier
            status: New status (active, obsolete, draft)

        Returns:
            True if successful
        """
        if status not in ["active", "obsolete", "draft"]:
            return False

        for i, doc in enumerate(self.registry["documents"]):
            if doc["doc_id"] == doc_id:
                self.registry["documents"][i]["status"] = status
                self._save_registry()
                return True
        return False

    def obsolete_document(
        self,
        doc_id: str,
        reason: str = "",
        user_id: str = "system",
    ) -> dict:
        """
        v2.7.0: Mark a document as obsolete (作廢).
        - Sets status to 'obsolete'
        - Deletes all markdown files and original uploaded files
        - Keeps the registry entry as an audit record
        - Records obsolete metadata (reason, who, when)

        Args:
            doc_id: Document identifier (e.g., "OTHER-016")
            reason: Reason for obsoleting the document
            user_id: User who performed the action

        Returns:
            Dict with 'success', 'doc_id', 'title', 'files_deleted' keys
        """
        # Find document
        doc_entry = None
        doc_index = -1
        for i, doc in enumerate(self.registry["documents"]):
            if doc["doc_id"] == doc_id:
                doc_entry = doc
                doc_index = i
                break

        if doc_entry is None:
            return {"success": False, "error": f"文件 {doc_id} 不存在"}

        if doc_entry.get("status") == "obsolete":
            return {"success": False, "error": f"文件 {doc_id} 已經是作廢狀態"}

        # Collect info before deletion
        title = doc_entry.get("title", "")
        doc_type = doc_entry.get("doc_type", "OTHER")
        current_version = doc_entry.get("current_version", "")
        files_deleted = []

        # Delete all version files (markdown + original)
        for ver in doc_entry.get("versions", []):
            if ver.get("files_removed"):
                continue  # Already cleaned up by version update

            # Delete markdown file
            md_path_str = ver.get("markdown_path", "")
            if md_path_str:
                full_md_path = self.base_path / md_path_str
                if full_md_path.exists():
                    try:
                        full_md_path.unlink()
                        files_deleted.append(str(full_md_path))
                        logger.info(f"v2.7.0 obsolete: Deleted markdown: {md_path_str}")
                    except Exception as e:
                        logger.warning(f"Failed to delete markdown {md_path_str}: {e}")

            # Delete original uploaded file
            orig_file = ver.get("original_file", "")
            if orig_file:
                orig_path = Path(orig_file)
                if not orig_path.is_absolute():
                    orig_path = Path.cwd() / orig_file
                if orig_path.exists():
                    try:
                        orig_path.unlink()
                        files_deleted.append(str(orig_path))
                        logger.info(f"v2.7.0 obsolete: Deleted original: {orig_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete original {orig_file}: {e}")

            # Also try uploads/ directory
            if orig_file:
                uploads_path = Path("uploads") / Path(orig_file).name
                if uploads_path.exists():
                    try:
                        uploads_path.unlink()
                        files_deleted.append(str(uploads_path))
                        logger.info(f"v2.7.0 obsolete: Deleted upload: {uploads_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete upload {uploads_path}: {e}")

            # Mark version as files removed
            ver["files_removed"] = True
            ver["files_removed_at"] = datetime.now().isoformat()

        # Update document status to obsolete
        doc_entry["status"] = "obsolete"
        doc_entry["obsoleted_at"] = datetime.now().isoformat()
        doc_entry["obsoleted_by"] = user_id
        doc_entry["obsolete_reason"] = reason
        self.registry["documents"][doc_index] = doc_entry
        self._save_registry()

        return {
            "success": True,
            "doc_id": doc_id,
            "title": title,
            "doc_type": doc_type,
            "version": current_version,
            "files_deleted": files_deleted,
            "files_deleted_count": len(files_deleted),
            "reason": reason,
        }

    def add_related_document(self, doc_id: str, related_doc_id: str) -> bool:
        """
        Add a related document reference.

        Args:
            doc_id: Document identifier
            related_doc_id: Related document identifier

        Returns:
            True if successful
        """
        for i, doc in enumerate(self.registry["documents"]):
            if doc["doc_id"] == doc_id:
                if related_doc_id not in doc["related_documents"]:
                    self.registry["documents"][i]["related_documents"].append(
                        related_doc_id
                    )
                    self._save_registry()
                return True
        return False

    def get_storage_stats(self) -> dict:
        """Get storage statistics"""
        total_versions = sum(len(doc["versions"]) for doc in self.registry["documents"])

        type_counts = {}
        for doc_type in DOC_TYPES:
            type_counts[doc_type] = sum(
                1 for doc in self.registry["documents"] if doc["doc_type"] == doc_type
            )

        return {
            "total_documents": self.get_document_count(),
            "total_versions": total_versions,
            "remaining_slots": self.get_remaining_slots(),
            "limit": POC_DOCUMENT_LIMIT,
            "by_type": type_counts,
            "registry_version": self.registry["registry_version"],
            "last_updated": self.registry["last_updated"],
        }

    # ============================================================
    # v2.4.8 New Methods - OCR Auto-Save & Search
    # ============================================================

    @staticmethod
    def compute_sha256(file_path: str) -> str:
        """
        Compute SHA-256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA-256 hash string with 'sha256:' prefix
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return f"sha256:{sha256_hash.hexdigest()}"

    def save_ocr_document(
        self,
        markdown_content: str,
        source_filename: str,
        source_sha256: Optional[str] = None,
        title: Optional[str] = None,
        doc_id: Optional[str] = None,
        doc_type: str = "OTHER",
        tags: Optional[List[str]] = None,
        ocr_provider: str = "unknown",
        ocr_confidence: float = 0.0,
        user_id: str = "system",
        source_file_path: Optional[str] = None,
        detected_version: Optional[str] = None,
    ) -> dict:
        """
        Save OCR-processed document to Markdown storage.

        Args:
            markdown_content: OCR result in Markdown format
            source_filename: Original filename that was OCR'd
            source_sha256: SHA-256 hash of source file (optional)
            title: Document title (extracted from content if not provided)
            doc_id: Document ID extracted from filename (e.g., "QM-001").
                If provided, used instead of auto-generating a sequential ID.
            doc_type: Document type (SOP, WI, FORM, DHF, OTHER)
            tags: Optional list of tags for categorization
            ocr_provider: OCR provider used (e.g., "gpt-4o", "claude-3")
            ocr_confidence: OCR confidence score (0.0-1.0)
            user_id: User who uploaded the document
            source_file_path: Full path to the uploaded file (with timestamp prefix).
                If provided, stored as original_file for reliable retrieval.
            detected_version: OCR-detected version string (e.g., "1", "2", "1.1").
                If provided, used as initial version instead of default "1.0".

        Returns:
            Dict with 'success', 'doc_id', 'path', 'version' keys
        """
        # Check document limit
        if not self.check_document_limit():
            return {
                "success": False,
                "error": f"Document limit reached ({POC_DOCUMENT_LIMIT}). Cannot add new documents.",
                "remaining_slots": 0,
            }

        # Validate doc_type
        if doc_type not in DOC_TYPES:
            doc_type = "OTHER"

        # v3.1.0: Use provided doc_id (extracted from filename) if available,
        # otherwise fall back to auto-generated sequential ID
        if not doc_id:
            doc_id = self._generate_doc_id(doc_type)

        # Extract title from content if not provided
        if not title:
            title = self._extract_title_from_markdown(markdown_content, source_filename)

        # Add metadata header to markdown content
        metadata_header = self._create_metadata_header(
            doc_id=doc_id,
            title=title,
            source_filename=source_filename,
            source_sha256=source_sha256,
            doc_type=doc_type,
            tags=tags or [],
            ocr_provider=ocr_provider,
            ocr_confidence=ocr_confidence,
        )
        full_content = metadata_header + markdown_content

        # Save using existing method
        # v3.1.0: Use source_file_path (full path with timestamp) if provided,
        # so get_original_file_path() can reliably find the uploaded file.
        original_file_value = source_file_path if source_file_path else source_filename
        result = self.save_document(
            doc_id=doc_id,
            title=title,
            doc_type=doc_type,
            markdown_content=full_content,
            original_file=original_file_value,
            ocr_provider=ocr_provider,
            ocr_confidence=ocr_confidence,
            user_id=user_id,
            initial_version=detected_version,
        )

        if result.get("success"):
            result["doc_id"] = doc_id
            result["title"] = title
            result["source_sha256"] = source_sha256

        return result

    def _generate_doc_id(self, doc_type: str) -> str:
        """
        Generate a unique document ID based on doc_type.
        Format: {DOC_TYPE}-{SEQUENCE:03d}
        """
        # Count existing documents of this type
        existing_count = sum(
            1 for doc in self.registry["documents"] if doc["doc_type"] == doc_type
        )
        sequence = existing_count + 1
        return f"{doc_type}-{sequence:03d}"

    def _extract_title_from_markdown(self, content: str, fallback: str) -> str:
        """
        Extract title from Markdown content.
        Looks for first H1 heading or uses fallback.
        """
        # Look for # Title pattern
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Look for first non-empty line
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("---"):
                return line[:100]  # Limit title length

        # Use filename without extension as fallback
        return Path(fallback).stem

    def _create_metadata_header(
        self,
        doc_id: str,
        title: str,
        source_filename: str,
        source_sha256: Optional[str],
        doc_type: str,
        tags: List[str],
        ocr_provider: str,
        ocr_confidence: float,
    ) -> str:
        """Create YAML frontmatter metadata header for Markdown document."""
        tags_str = ", ".join(tags) if tags else ""
        return f"""---
doc_id: {doc_id}
title: {title}
source_file: {source_filename}
source_sha256: {source_sha256 or "N/A"}
doc_type: {doc_type}
tags: [{tags_str}]
ocr_provider: {ocr_provider}
ocr_confidence: {ocr_confidence:.2f}
created_at: {datetime.now().isoformat()}
---

"""

    def search_documents(
        self,
        query: str,
        doc_type: Optional[str] = None,
        latest_only: bool = True,
        limit: int = 10,
    ) -> List[dict]:
        """
        Full-text search across all Markdown documents.

        Args:
            query: Search query string (case-insensitive)
            doc_type: Filter by document type (optional)
            latest_only: Only search latest version of each document
            limit: Maximum number of results to return

        Returns:
            List of matching documents with snippets
        """
        import re as _re

        results = []
        query_lower = query.lower()

        # Improved tokenization: split on whitespace AND extract
        # alphanumeric tokens (e.g. "QP-423") separately from CJK text.
        # This handles Chinese queries like "QP-423文件的目的是什麼？"
        # by extracting ["qp-423", "文件的目的是什麼"] as search tokens.
        raw_words = query_lower.split()
        query_tokens = []
        for w in raw_words:
            # Split each word into alphanumeric parts and CJK parts
            parts = _re.findall(
                r"[a-z0-9][\w\-]*[a-z0-9]|[a-z0-9]+|[\u4e00-\u9fff\u3400-\u4dbf]+", w
            )
            if parts:
                query_tokens.extend(parts)
            else:
                query_tokens.append(w)
        # Remove very short CJK tokens (single chars that are likely particles)
        query_tokens = [
            t for t in query_tokens if len(t) > 1 or _re.match(r"[a-z0-9]", t)
        ]
        if not query_tokens:
            query_tokens = [query_lower]

        for doc in self.registry["documents"]:
            # Filter by doc_type if specified
            if doc_type and doc["doc_type"] != doc_type:
                continue

            # Get versions to search
            if latest_only:
                versions_to_search = [doc["versions"][-1]] if doc["versions"] else []
            else:
                versions_to_search = doc["versions"]

            for version_entry in versions_to_search:
                file_path = self.base_path / version_entry["markdown_path"]
                if not file_path.exists():
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue

                content_lower = content.lower()

                # Also search in doc_id and title (metadata match)
                meta_text = f"{doc.get('doc_id', '')} {doc.get('title', '')}".lower()
                searchable = content_lower + "\n" + meta_text

                # Check if any query token is present (OR-based for better recall)
                matched = any(token in searchable for token in query_tokens)
                if not matched:
                    continue

                # Find snippet around first match
                first_token = next(
                    (t for t in query_tokens if t in content_lower), query_tokens[0]
                )
                snippet = self._extract_snippet(content, first_token, context_chars=150)

                results.append(
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "doc_type": doc["doc_type"],
                        "version": version_entry["version"],
                        "status": doc["status"],
                        "snippet": snippet,
                        "path": str(file_path),
                        "created_at": version_entry["created_at"],
                    }
                )

                if len(results) >= limit:
                    return results

        return results

    def _extract_snippet(
        self, content: str, query_word: str, context_chars: int = 150
    ) -> str:
        """Extract a snippet of text around the first occurrence of query word."""
        content_lower = content.lower()
        pos = content_lower.find(query_word.lower())

        if pos == -1:
            # Return beginning of content if word not found
            return content[: context_chars * 2] + "..."

        # Calculate start and end positions
        start = max(0, pos - context_chars)
        end = min(len(content), pos + len(query_word) + context_chars)

        # Adjust to word boundaries
        if start > 0:
            # Find next space after start
            space_pos = content.find(" ", start)
            if space_pos != -1 and space_pos < pos:
                start = space_pos + 1

        if end < len(content):
            # Find last space before end
            space_pos = content.rfind(" ", pos, end)
            if space_pos != -1:
                end = space_pos

        snippet = content[start:end].strip()

        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def find_referencing_documents(self, doc_id: str) -> List[dict]:
        """
        Find all documents that reference the given doc_id in their content.
        Used after version updates to notify users of affected documents.

        Args:
            doc_id: Document identifier to search for references

        Returns:
            List of documents that reference this doc_id
        """
        referencing = []
        doc_id_lower = doc_id.lower()

        for doc in self.registry["documents"]:
            # Skip the document itself
            if doc["doc_id"] == doc_id:
                continue

            # Check related_documents field first
            if doc_id in doc.get("related_documents", []):
                referencing.append(
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "doc_type": doc["doc_type"],
                        "current_version": doc["current_version"],
                        "reference_type": "explicit",
                    }
                )
                continue

            # Search latest version content for references
            if doc["versions"]:
                latest_version = doc["versions"][-1]
                file_path = self.base_path / latest_version["markdown_path"]
                if file_path.exists():
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read().lower()
                        if doc_id_lower in content:
                            referencing.append(
                                {
                                    "doc_id": doc["doc_id"],
                                    "title": doc["title"],
                                    "doc_type": doc["doc_type"],
                                    "current_version": doc["current_version"],
                                    "reference_type": "content",
                                }
                            )
                    except Exception:
                        continue

        return referencing

    def get_document_by_source_hash(self, source_sha256: str) -> Optional[dict]:
        """
        Find a document by its source file SHA-256 hash.
        Useful for detecting duplicate uploads.

        Args:
            source_sha256: SHA-256 hash of the source file

        Returns:
            Document entry if found, None otherwise
        """
        for doc in self.registry["documents"]:
            for version in doc["versions"]:
                # Check if the version's markdown file contains this hash
                file_path = self.base_path / version["markdown_path"]
                if file_path.exists():
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read(500)  # Only read header
                            if source_sha256 in content:
                                return {
                                    "doc_id": doc["doc_id"],
                                    "title": doc["title"],
                                    "version": version["version"],
                                    "doc_type": doc["doc_type"],
                                }
                    except Exception:
                        continue
        return None

    def get_original_file_path(self, doc_id: str, version: str = None) -> Optional[str]:
        """
        v2.5.4: Resolve the original uploaded file path for a document.
        Searches multiple locations: direct path, uploads/, mock-data/.

        Args:
            doc_id: Document identifier
            version: Specific version (None = latest)

        Returns:
            Absolute path to the original file if found, None otherwise
        """
        doc_entry = None
        for doc in self.registry["documents"]:
            if doc["doc_id"] == doc_id:
                doc_entry = doc
                break

        if not doc_entry or not doc_entry["versions"]:
            return None

        # Find the requested version
        if version:
            ver_entry = None
            for v in doc_entry["versions"]:
                if v["version"] == version:
                    ver_entry = v
                    break
            if not ver_entry:
                return None
        else:
            # v2.6.0: Get latest version that hasn't been cleaned up
            ver_entry = doc_entry["versions"][-1]

        # v2.6.0: If files were removed (old version cleanup), return None
        if ver_entry.get("files_removed"):
            return None

        original_file = ver_entry.get("original_file", "")
        if not original_file:
            return None

        # Try multiple resolution strategies
        search_paths = [
            Path(
                original_file
            ),  # Direct path (v3.1.0: may be full path with timestamp)
            Path("uploads") / Path(original_file).name,  # uploads/ folder
            Path("mock-data") / Path(original_file).name,  # mock-data/ folder
        ]

        for p in search_paths:
            if p.exists():
                return str(p.resolve())

        # v3.1.0: Fallback — search uploads/ for timestamp-prefixed files
        # matching the bare filename (for old registry entries that stored
        # only the original filename without the timestamp prefix)
        bare_name = Path(original_file).name
        try:
            uploads_dir = Path("uploads")
            if uploads_dir.exists():
                for f in sorted(uploads_dir.iterdir(), reverse=True):
                    # Match files ending with _<bare_name> (timestamp prefix pattern)
                    if f.name.endswith(f"_{bare_name}") or f.name == bare_name:
                        return str(f.resolve())
        except Exception:
            pass

        return None

    def list_documents_with_files(self) -> list:
        """
        v2.5.4: List all documents with original file availability info.

        Returns:
            List of dicts with doc_id, title, doc_type, version, has_original_file
        """
        result = []
        for doc in self.registry["documents"]:
            doc_id = doc["doc_id"]
            file_path = self.get_original_file_path(doc_id)
            result.append(
                {
                    "doc_id": doc_id,
                    "title": doc["title"],
                    "doc_type": doc["doc_type"],
                    "current_version": doc["current_version"],
                    "has_original_file": file_path is not None,
                    "original_file_path": file_path,
                    "file_extension": Path(file_path).suffix if file_path else None,
                }
            )
        return result

    def scan_regulatory_references(self) -> dict:
        """
        v3.0.0: Scan all documents for regulatory standard references.
        Comprehensive coverage of global medical device regulatory standards
        across all major markets and standards bodies.

        Returns:
            Dict with:
                'by_document': list of {doc_id, title, doc_type, version, standards: [str]}
                'aggregate': list of {standard, version, referenced_by: [doc_id]}
        """
        import re as _re

        # Comprehensive regex patterns for global regulatory standards
        patterns = [
            # ==========================================
            # International Standards Organizations
            # ==========================================
            # ISO: ISO 13485:2016, ISO 14971:2019, ISO/IEC 27001, ISO/TR 80002-2
            r"ISO(?:/(?:IEC|TR|TS|PAS))?\s*\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # IEC: IEC 62304:2006, IEC 60601-1-2:2014, IEC/TR 80002-1
            r"IEC(?:/(?:TR|TS|PAS))?\s*\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # ASTM: ASTM F2761, ASTM D4169, ASTM E2500
            r"ASTM\s*[A-Z]\s*\d{3,5}(?:[-–]\d+)?(?:\s*:\s*\d{4})?",
            # IEEE: IEEE 11073, IEEE 802.11
            r"IEEE\s*\d{3,5}(?:\.\d+)?(?:[-–]\d+)?(?:\s*:\s*\d{4})?",
            # CLSI: CLSI EP05, CLSI M100
            r"CLSI\s*[A-Z]{1,3}\s*\d{2,3}(?:[-–][A-Z]?\d*)?",
            # ICH: ICH Q7, ICH E6(R2), ICH Q10
            r"ICH\s*[QESM]\d{1,2}(?:\s*\([Rr]\d\))?",
            # WHO: WHO TRS (Technical Report Series)
            r"WHO\s+TRS\s*\d{3,4}",
            # ==========================================
            # United States (FDA / AAMI)
            # ==========================================
            # FDA 21 CFR: 21 CFR Part 820, 21 CFR Part 11, 21 CFR 820.30
            r"(?:FDA\s+)?21\s*CFR\s*(?:Part\s*|§\s*)?\d+(?:\.\d+)?",
            # AAMI: AAMI TIR45, AAMI ST79, AAMI/IEC 62304
            r"AAMI(?:/(?:IEC|ISO|ANSI))?\s*(?:TIR|ST|HE|SW|BI|EQ)?\s*\d{2,5}(?:[-–]\d+)?(?:\s*:\s*\d{4})?",
            # ANSI/AAMI: ANSI/AAMI ST79, ANSI/AAMI/IEC 62304
            r"ANSI(?:/AAMI)?(?:/(?:IEC|ISO))?\s*(?:TIR|ST|HE|SW|BI|EQ)?\s*\d{2,5}(?:[-–]\d+)?(?:\s*:\s*\d{4})?",
            # FDA Guidance documents (keyword match)
            r"FDA\s+(?:Guidance|Draft\s+Guidance|Final\s+Guidance)",
            # UL standards: UL 60601-1, UL 2900
            r"UL\s*\d{3,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # NIST: NIST SP 800-series
            r"NIST\s*(?:SP|IR|FIPS)?\s*\d{3,4}(?:[-–]\d+)?",
            # USP: USP <71>, USP <85>
            r"USP\s*(?:<\d+>|\d+)",
            # QSR (Quality System Regulation)
            r"QSR",
            # QMSR (Quality Management System Regulation - FDA final rule 2024)
            r"QMSR",
            # ==========================================
            # European Union
            # ==========================================
            # EU MDR / IVDR: EU MDR 2017/745, IVDR 2017/746
            r"(?:EU\s+)?(?:MDR|IVDR)\s*\d{4}/\d{3,4}",
            # MDD (Medical Device Directive): MDD 93/42/EEC
            r"MDD\s*\d{2}/\d{2,3}/(?:EEC|EC)",
            # AIMD Directive: 90/385/EEC
            r"AIMD\s*\d{2}/\d{2,3}/(?:EEC|EC)",
            # IVDD: 98/79/EC
            r"IVDD\s*\d{2}/\d{2,3}/(?:EEC|EC)",
            # EN standards: EN 60601-1, EN ISO 13485:2016
            r"EN\s+(?:ISO\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # BS EN: BS EN ISO 13485, BS EN 60601-1
            r"BS\s+EN\s+(?:ISO\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # DIN EN: DIN EN ISO 13485, DIN EN 62304
            r"DIN\s+(?:EN\s+)?(?:ISO\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # NF: NF EN ISO 13485 (French)
            r"NF\s+(?:EN\s+)?(?:ISO\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # UNI: UNI EN ISO 13485 (Italian)
            r"UNI\s+(?:EN\s+)?(?:ISO\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # MDCG guidance: MDCG 2019-16, MDCG 2020-5
            r"MDCG\s*\d{4}[-–]\d{1,3}(?:\s*(?:rev|Rev|REV)\.?\s*\d+)?",
            # MEDDEV guidance: MEDDEV 2.7/1, MEDDEV 2.12-1
            r"MEDDEV\s*\d+\.?\d*(?:/\d+)?(?:[-–]\d+)?(?:\s*(?:rev|Rev|REV)\.?\s*\d+)?",
            # EU Directive numbers: 2017/745, 93/42/EEC
            r"\d{2,4}/\d{2,4}/(?:EU|EEC|EC)",
            # MDSAP
            r"MDSAP",
            # ==========================================
            # United Kingdom (post-Brexit)
            # ==========================================
            # UKCA marking / UK MDR
            r"UK(?:CA|\s+MDR)",
            # BS (British Standard): BS 5724, BS EN ISO 13485
            # (BS EN already covered above)
            # ==========================================
            # China (NMPA / CFDA / SFDA)
            # ==========================================
            # GB/T, GB: GB/T 42062, GB 9706.1
            r"GB(?:/T)?\s*\d{4,5}(?:\.\d+)?(?:[-–]\d{4})?",
            # YY/T, YY: YY/T 0287, YY 0505 (medical device industry standards)
            r"YY(?:/T)?\s*\d{4,5}(?:\.\d+)?(?:[-–]\d{4})?",
            # NMPA / CFDA / SFDA regulatory orders
            r"(?:NMPA|CFDA|SFDA)\s*(?:Order|令|公告)?\s*(?:No\.?\s*)?\d*",
            # ==========================================
            # Japan (PMDA / MHLW)
            # ==========================================
            # JIS: JIS T 0601-1, JIS Q 13485
            r"JIS\s*[A-Z]?\s*\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # JMDN (Japanese Medical Device Nomenclature)
            r"JMDN",
            # J-PAL / PMDA guidance
            r"PMDA\s+(?:Guidance|通知|通達)",
            # ==========================================
            # South Korea (MFDS / KFDA)
            # ==========================================
            # KS standards: KS P ISO 13485, KS C IEC 62304
            r"KS\s+[A-Z]\s+(?:ISO\s+|IEC\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # MFDS / KFDA
            r"(?:MFDS|KFDA)\s*(?:Notification|고시)?\s*(?:No\.?\s*)?\d*",
            # ==========================================
            # Taiwan (TFDA)
            # ==========================================
            # CNS: CNS 13485, CNS 14971
            r"CNS\s*\d{4,5}(?:\s*:\s*\d{4})?",
            # TFDA
            r"TFDA",
            # ==========================================
            # Australia / New Zealand (TGA)
            # ==========================================
            # AS/NZS: AS/NZS ISO 13485
            r"AS(?:/NZS)?\s+(?:ISO\s+|IEC\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # TGA
            r"TGA",
            # ==========================================
            # Canada (Health Canada)
            # ==========================================
            # CAN/CSA: CAN/CSA-ISO 13485, CSA C22.2 No. 60601
            r"(?:CAN/)?CSA[-–\s]+(?:ISO\s+|IEC\s+|C\d+\.\d+\s+(?:No\.\s*)?)?\d{3,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # SOR (Statutory Orders and Regulations)
            r"SOR/\d{2,4}[-–]\d+",
            # ==========================================
            # Brazil (ANVISA)
            # ==========================================
            # ANVISA RDC: RDC No. 185/2001
            r"(?:ANVISA\s+)?RDC\s*(?:No?\.?\s*)?\d+(?:/\d{4})?",
            # ABNT NBR: ABNT NBR ISO 13485
            r"ABNT\s+NBR\s+(?:ISO\s+|IEC\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # ==========================================
            # India (CDSCO)
            # ==========================================
            # IS (Indian Standard): IS 13485, IS/ISO 14971
            r"IS(?:/ISO)?\s*\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # BIS
            r"BIS\s*\d{4,5}(?:\s*:\s*\d{4})?",
            # CDSCO / MDR 2017 (India)
            r"CDSCO",
            # ==========================================
            # Russia / EAEU (Eurasian Economic Union)
            # ==========================================
            # GOST R: GOST R ISO 13485, GOST R 51609
            r"GOST\s*(?:R\s+)?(?:ISO\s+|IEC\s+)?\d{4,5}(?:[-–]\d+)*(?:\s*:\s*\d{4})?",
            # EAEU TR (Technical Regulation)
            r"(?:EAEU|EAC)\s+TR\s*\d{3}/\d{4}",
            # ==========================================
            # Other Regional / Specific Standards
            # ==========================================
            # IMDRF guidance
            r"IMDRF(?:/\w+)?\s*(?:N\d+)?",
            # GHTF (predecessor to IMDRF)
            r"GHTF(?:/SG\d)?\s*(?:N\d+)?",
            # MIL-STD (US Military): MIL-STD-810, MIL-STD-461
            r"MIL[-–]STD[-–]\d{3,4}[A-Z]?",
            # IPC standards (electronics): IPC-A-610, IPC J-STD-001
            r"IPC[-–]?(?:[A-Z][-–])?\d{3,4}(?:[-–]\d+)?",
            # SAE (aerospace/automotive): SAE AS9100
            r"SAE\s*(?:AS|AMS|ARP|J)\s*\d{3,5}(?:[A-Z])?",
            # SEMI standards (semiconductor)
            r"SEMI\s*[A-Z]\d{1,3}(?:[-–]\d+)?",
            # OIML (metrology)
            r"OIML\s*[A-Z]\s*\d{1,3}",
            # Pharmacopoeia: Ph. Eur. only (EP/BP/JP/CP removed — too many false positives)
            r"Ph\.\s*Eur\.(?:\s*\d+(?:\.\d+)?)?",
        ]
        combined_pattern = "|".join(f"({p})" for p in patterns)

        by_document = []
        aggregate_map = {}  # standard_normalized -> {standard, referenced_by: set}

        for doc in self.registry["documents"]:
            if doc["status"] != "active":
                continue
            if not doc["versions"]:
                continue

            latest_version = doc["versions"][-1]
            file_path = self.base_path / latest_version["markdown_path"]
            if not file_path.exists():
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            # Find all matches
            found_standards = set()
            for match in _re.finditer(combined_pattern, content, _re.IGNORECASE):
                raw = match.group(0).strip()
                # Normalize whitespace
                normalized = _re.sub(r"\s+", " ", raw).upper()
                found_standards.add(normalized)

            if found_standards:
                sorted_standards = sorted(found_standards)
                by_document.append(
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "doc_type": doc["doc_type"],
                        "current_version": doc["current_version"],
                        "standards": sorted_standards,
                    }
                )

                for std in sorted_standards:
                    if std not in aggregate_map:
                        aggregate_map[std] = {
                            "standard": std,
                            "referenced_by": set(),
                        }
                    aggregate_map[std]["referenced_by"].add(doc["doc_id"])

        # Convert sets to sorted lists for JSON serialization
        aggregate = []
        for std_key in sorted(aggregate_map.keys()):
            entry = aggregate_map[std_key]
            aggregate.append(
                {
                    "standard": entry["standard"],
                    "referenced_by": sorted(entry["referenced_by"]),
                }
            )

        return {
            "by_document": by_document,
            "aggregate": aggregate,
        }


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("Markdown Storage Manager Test")
    print("=" * 50)

    manager = MarkdownStorageManager()

    # Show stats
    stats = manager.get_storage_stats()
    print(f"Total documents: {stats['total_documents']}")
    print(f"Remaining slots: {stats['remaining_slots']}")
    print(f"Limit: {stats['limit']}")

    # Test save document
    if manager.check_document_limit():
        result = manager.save_document(
            doc_id="TEST-001",
            title="Test Document",
            doc_type="SOP",
            markdown_content="# Test Document\n\nThis is a test.",
            original_file="test.pdf",
            ocr_provider="test",
            ocr_confidence=0.95,
            user_id="test_user",
        )
        print(f"\nSave result: {result}")

    # List documents
    docs = manager.list_documents()
    print(f"\nDocuments: {docs}")
