"""
AI-QMS Phase 1 - Markdown Store Service
Singleton service for cross-agent access to Markdown storage.

v2.4.8 - New file for shared storage access
"""

import os
import threading
from pathlib import Path
from typing import Optional, List

# Import the storage manager
from src.storage.markdown_storage import MarkdownStorageManager


# ============================================================
# Singleton Instance
# ============================================================

_instance: Optional[MarkdownStorageManager] = None
_lock = threading.Lock()


def get_markdown_store() -> MarkdownStorageManager:
    """
    Get the singleton MarkdownStorageManager instance.
    Thread-safe initialization.

    The storage root can be configured via environment variable:
    - AIQMS_MARKDOWN_STORAGE_ROOT: Path to markdown storage directory

    Returns:
        MarkdownStorageManager singleton instance
    """
    global _instance

    if _instance is None:
        with _lock:
            # Double-check locking pattern
            if _instance is None:
                storage_root = os.environ.get(
                    "AIQMS_MARKDOWN_STORAGE_ROOT", _get_default_storage_root()
                )
                _instance = MarkdownStorageManager(base_path=storage_root)

    return _instance


def _get_default_storage_root() -> str:
    """
    Get the default storage root path.
    Tries to find the project root and use markdown_storage directory.
    """
    # Try to find project root by looking for known files
    current = Path(__file__).resolve()

    # Walk up to find project root (contains README.md or src/)
    for parent in current.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return str(parent / "markdown_storage")

    # Fallback to current working directory
    return str(Path.cwd() / "markdown_storage")


# ============================================================
# Service Class (for dependency injection patterns)
# ============================================================


class MarkdownStoreService:
    """
    Service wrapper for MarkdownStorageManager.
    Provides a clean interface for agents and tools.
    """

    def __init__(self, storage_manager: Optional[MarkdownStorageManager] = None):
        """
        Initialize the service.

        Args:
            storage_manager: Optional custom storage manager.
                           Uses singleton if not provided.
        """
        self._manager = storage_manager or get_markdown_store()

    @property
    def manager(self) -> MarkdownStorageManager:
        """Get the underlying storage manager."""
        return self._manager

    # ============================================================
    # Document Operations
    # ============================================================

    def save_ocr_result(
        self,
        markdown_content: str,
        source_filename: str,
        source_file_path: Optional[str] = None,
        doc_id: Optional[str] = None,
        title: Optional[str] = None,
        doc_type: str = "OTHER",
        tags: Optional[List[str]] = None,
        ocr_provider: str = "unknown",
        ocr_confidence: float = 0.0,
        detected_version: Optional[str] = None,
    ) -> dict:
        """
        Save OCR result to Markdown storage.

        Args:
            markdown_content: OCR result in Markdown format
            source_filename: Original filename
            source_file_path: Path to source file (for SHA256 calculation)
            doc_id: Document ID extracted from filename (e.g., "QM-001").
                If provided, used as the registry doc_id instead of auto-generating.
            title: Document title extracted from filename (e.g., "ISO 13485 Quality Manual").
                If provided, overrides auto-extraction from markdown content.
            doc_type: Document type (SOP, WI, FORM, DHF, OTHER)
            tags: Optional tags for categorization
            ocr_provider: OCR provider used
            ocr_confidence: OCR confidence score
            detected_version: OCR-detected version (e.g., "1", "2", "1.1").
                If provided, used as initial version instead of default "1.0".

        Returns:
            Dict with success status and document info
        """
        # Calculate source file hash if path provided
        source_sha256 = None
        if source_file_path and Path(source_file_path).exists():
            source_sha256 = MarkdownStorageManager.compute_sha256(source_file_path)

        return self._manager.save_ocr_document(
            markdown_content=markdown_content,
            source_filename=source_filename,
            source_sha256=source_sha256,
            title=title,
            doc_id=doc_id,
            doc_type=doc_type,
            tags=tags,
            ocr_provider=ocr_provider,
            ocr_confidence=ocr_confidence,
            source_file_path=source_file_path,
            detected_version=detected_version,
        )

    def search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Search documents by content.

        Args:
            query: Search query string
            doc_type: Filter by document type
            limit: Maximum results

        Returns:
            List of matching documents with snippets
        """
        return self._manager.search_documents(
            query=query,
            doc_type=doc_type,
            latest_only=True,
            limit=limit,
        )

    def get_document(self, doc_id: str, version: Optional[str] = None) -> dict:
        """
        Get document content by ID.

        Args:
            doc_id: Document identifier
            version: Specific version (latest if not specified)

        Returns:
            Dict with content and metadata
        """
        return self._manager.get_document(doc_id, version)

    def list_documents(self, doc_type: Optional[str] = None) -> List[dict]:
        """
        List all documents.

        Args:
            doc_type: Filter by document type

        Returns:
            List of document summaries
        """
        return self._manager.list_documents(doc_type)

    def get_stats(self) -> dict:
        """Get storage statistics."""
        return self._manager.get_storage_stats()

    def obsolete_document(
        self,
        doc_id: str,
        reason: str = "",
        user_id: str = "system",
    ) -> dict:
        """
        v2.7.0: Mark a document as obsolete (作廢).
        Deletes files but keeps registry record for audit trail.

        Args:
            doc_id: Document identifier
            reason: Reason for obsoleting
            user_id: User who performed the action

        Returns:
            Dict with success status and details
        """
        return self._manager.obsolete_document(
            doc_id=doc_id,
            reason=reason,
            user_id=user_id,
        )

    def check_duplicate(self, file_path: str) -> Optional[dict]:
        """
        Check if a file has already been uploaded.

        Args:
            file_path: Path to the file to check

        Returns:
            Existing document info if duplicate, None otherwise
        """
        if not Path(file_path).exists():
            return None

        source_sha256 = MarkdownStorageManager.compute_sha256(file_path)
        return self._manager.get_document_by_source_hash(source_sha256)


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("Markdown Store Service Test")
    print("=" * 50)

    # Test singleton
    store1 = get_markdown_store()
    store2 = get_markdown_store()
    print(f"Singleton test: {store1 is store2}")  # Should be True

    # Test service
    service = MarkdownStoreService()
    stats = service.get_stats()
    print(f"Total documents: {stats['total_documents']}")
    print(f"Remaining slots: {stats['remaining_slots']}")

    # Test search
    results = service.search("test")
    print(f"Search 'test': {len(results)} results")
