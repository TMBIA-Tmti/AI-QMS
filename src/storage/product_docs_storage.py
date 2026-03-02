"""
AI-QMS — Product Documents Temporary Storage
=============================================

Temporary storage for product documents (IFU, spec sheets, product introductions)
uploaded by users before regulatory analysis. Documents are stored in an independent
directory, isolated from markdown_storage/ and regulatory_markdown_storage/.

Lifecycle:
    1. User triggers 法規清單 or 法規清單更新
    2. System asks if user wants to upload product docs
    3. User uploads files → OCR'd text saved here via save_document()
    4. LLM analysis uses get_session_content_for_prompt() as additional context
    5. After report generation, cleanup_session() deletes everything

Directory structure:
    data/product_docs_temp/
    ├── session_20260302_195800/
    │   ├── _metadata.json
    │   ├── IFU_ProductX.md
    │   └── Spec_Sheet_v2.md
    └── session_20260303_100000/
        ├── _metadata.json
        └── Product_Intro.md
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PATH = Path("data") / "product_docs_temp"


class ProductDocsStorage:
    """
    Temporary storage for product documents uploaded before regulatory analysis.

    Completely isolated from markdown_storage/ and regulatory_markdown_storage/.
    Each analysis session gets its own subdirectory, auto-deleted after report generation.
    """

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or _DEFAULT_BASE_PATH
        if isinstance(self.base_path, str):
            self.base_path = Path(self.base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Session management
    # ============================================================

    def create_session(self) -> str:
        """Create a new session directory.

        Returns:
            session_id (str): Unique session identifier, e.g. 'session_20260302_195800'
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        session_id = f"session_{ts}"
        session_dir = self.base_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Initialize metadata
        metadata = {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "documents": [],
        }
        self._save_metadata(session_id, metadata)

        logger.info(f"Created product docs session: {session_id}")
        return session_id

    # ============================================================
    # Document operations
    # ============================================================

    def save_document(
        self,
        session_id: str,
        filename: str,
        content: str,
        original_path: str = "",
    ) -> dict:
        """Save a processed document (OCR'd text content) to session.

        Args:
            session_id: Session identifier from create_session()
            filename: Original filename (e.g. 'IFU_ProductX.pdf')
            content: OCR'd text content (markdown)
            original_path: Original file path before OCR (for reference only)

        Returns:
            dict with keys: 'success', 'doc_id', 'path'
        """
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return {"success": False, "error": f"Session {session_id} not found"}

        if not content or not content.strip():
            return {"success": False, "error": "Empty document content"}

        # Save content as .md file (use filename stem to avoid .pdf.md etc.)
        stem = Path(filename).stem
        safe_stem = "".join(c if c.isalnum() or c in "-_. " else "_" for c in stem)
        md_filename = f"{safe_stem}.md"
        md_path = session_dir / md_filename

        # Handle duplicate filenames
        counter = 1
        while md_path.exists():
            md_filename = f"{safe_stem}_{counter}.md"
            md_path = session_dir / md_filename
            counter += 1

        # Atomic write
        self._atomic_write_text(md_path, content)

        doc_id = f"{session_id}/{Path(md_filename).stem}"

        # Update metadata
        metadata = self._load_metadata(session_id)
        metadata["documents"].append(
            {
                "doc_id": doc_id,
                "filename": filename,
                "md_filename": md_filename,
                "original_path": original_path,
                "content_length": len(content),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save_metadata(session_id, metadata)

        logger.info(f"Saved product doc: {doc_id} ({len(content)} chars)")
        return {"success": True, "doc_id": doc_id, "path": str(md_path)}

    def get_session_documents(self, session_id: str) -> list:
        """Get all documents in a session.

        Args:
            session_id: Session identifier

        Returns:
            List of dicts with keys: doc_id, filename, content, original_path, saved_at
        """
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return []

        metadata = self._load_metadata(session_id)
        results = []

        for doc_entry in metadata.get("documents", []):
            md_filename = doc_entry.get("md_filename", "")
            md_path = session_dir / md_filename
            content = ""
            if md_path.exists():
                try:
                    content = md_path.read_text(encoding="utf-8")
                except Exception:
                    logger.warning(f"Failed to read product doc: {md_path}")

            results.append(
                {
                    "doc_id": doc_entry.get("doc_id", ""),
                    "filename": doc_entry.get("filename", ""),
                    "content": content,
                    "original_path": doc_entry.get("original_path", ""),
                    "saved_at": doc_entry.get("saved_at", ""),
                }
            )

        return results

    def get_session_content_for_prompt(
        self, session_id: str, max_chars: int = 8000
    ) -> str:
        """Get combined content of all docs in session, formatted for LLM prompt.

        Distributes max_chars evenly across documents. Format:
            ### [來源: 📦 產品文件] {filename}
            {content}

        Args:
            session_id: Session identifier
            max_chars: Maximum total characters for all documents combined

        Returns:
            Formatted string for LLM prompt injection, or empty string if no documents.
        """
        docs = self.get_session_documents(session_id)
        if not docs:
            return ""

        per_doc_limit = max(500, max_chars // len(docs))
        parts = []

        for doc in docs:
            content = doc.get("content", "")
            if not content.strip():
                continue
            truncated = content[:per_doc_limit]
            if len(content) > per_doc_limit:
                truncated += "\n...(內容已截斷)"
            parts.append(f"### [來源: 📦 產品文件] {doc['filename']}\n{truncated}")

        if not parts:
            return ""

        header = (
            f"## 產品相關文件（使用者本次上傳，僅供本次分析參考）\n"
            f"共 {len(parts)} 份產品文件\n"
        )
        return header + "\n\n".join(parts)

    def has_documents(self, session_id: str) -> bool:
        """Check if session has any documents.

        Args:
            session_id: Session identifier

        Returns:
            True if session exists and contains at least one document.
        """
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return False
        metadata = self._load_metadata(session_id)
        return len(metadata.get("documents", [])) > 0

    # ============================================================
    # Cleanup operations
    # ============================================================

    def cleanup_session(self, session_id: str) -> dict:
        """Delete all files in a session directory.

        Args:
            session_id: Session identifier

        Returns:
            dict with keys: 'success', 'deleted_count'
        """
        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return {"success": True, "deleted_count": 0}

        metadata = self._load_metadata(session_id)
        doc_count = len(metadata.get("documents", []))

        try:
            shutil.rmtree(session_dir)
            logger.info(
                f"Cleaned up product docs session: {session_id} ({doc_count} docs)"
            )
            return {"success": True, "deleted_count": doc_count}
        except Exception as e:
            logger.warning(f"Failed to cleanup session {session_id}: {e}")
            return {"success": False, "deleted_count": 0, "error": str(e)}

    def cleanup_all(self) -> dict:
        """Delete ALL session directories (nuclear cleanup).

        Returns:
            dict with keys: 'success', 'deleted_count'
        """
        total_deleted = 0
        sessions = self.list_sessions()

        for session_info in sessions:
            result = self.cleanup_session(session_info["session_id"])
            total_deleted += result.get("deleted_count", 0)

        logger.info(f"Cleaned up all product docs sessions: {total_deleted} docs total")
        return {"success": True, "deleted_count": total_deleted}

    # ============================================================
    # Query operations
    # ============================================================

    def list_sessions(self) -> list:
        """List all existing sessions.

        Returns:
            List of dicts with keys: session_id, doc_count, created_at
        """
        if not self.base_path.exists():
            return []

        results = []
        for entry in sorted(self.base_path.iterdir()):
            if entry.is_dir() and entry.name.startswith("session_"):
                metadata = self._load_metadata(entry.name)
                results.append(
                    {
                        "session_id": entry.name,
                        "doc_count": len(metadata.get("documents", [])),
                        "created_at": metadata.get("created_at", ""),
                    }
                )
        return results

    # ============================================================
    # Internal helpers
    # ============================================================

    def _load_metadata(self, session_id: str) -> dict:
        """Load session metadata from _metadata.json."""
        metadata_path = self.base_path / session_id / "_metadata.json"
        if not metadata_path.exists():
            return {"session_id": session_id, "created_at": "", "documents": []}
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning(f"Failed to load metadata for session {session_id}")
            return {"session_id": session_id, "created_at": "", "documents": []}

    def _save_metadata(self, session_id: str, metadata: dict) -> None:
        """Save session metadata to _metadata.json with atomic write."""
        metadata_path = self.base_path / session_id / "_metadata.json"
        self._atomic_write_json(metadata_path, metadata)

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


# ============================================================
# Singleton accessor
# ============================================================

_product_docs_instance: Optional[ProductDocsStorage] = None


def get_product_docs_store() -> ProductDocsStorage:
    """Get or create singleton ProductDocsStorage instance."""
    global _product_docs_instance
    if _product_docs_instance is None:
        _product_docs_instance = ProductDocsStorage()
    return _product_docs_instance
