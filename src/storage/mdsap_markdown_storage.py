"""
AI-QMS — MDSAP Markdown Storage (Unified Wrapper)
===================================================

Thin wrapper over RegulatoryMarkdownStorage that provides the API expected
by report_api.py endpoints for 7-country regulation management.

All 7 countries' regulation Markdown files are stored TOGETHER under the
unified ``regulatory_markdown_storage/`` directory with this structure::

    regulatory_markdown_storage/
    └── documents/
        ├── USA/
        │   ├── predefined/          ← System-generated profile summaries
        │   │   └── QMSR_profile.md
        │   ├── uploads/             ← User-uploaded full regulation text
        │   │   └── QMSR_uploaded_20260304.md
        │   └── FDA_20260227_*.md    ← Crawler-fetched documents
        ├── EU/
        │   ├── predefined/
        │   └── uploads/
        ├── Taiwan/
        ├── Canada/
        ├── Japan/
        ├── Brazil/
        ├── Australia/
        └── ISO_Standards/
            ├── predefined/
            └── uploads/

This module re-exports the methods from RegulatoryMarkdownStorage so that
``report_api.py`` imports like ``from src.storage.mdsap_markdown_storage
import get_mdsap_markdown_store`` work without modification.

MDSAP, ISO 13485, and all 7 countries' regulations are treated as
**external documents (外來文件)** and share the same storage layer.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.storage.regulatory_markdown_storage import (
    RegulatoryMarkdownStorage,
    get_regulatory_markdown_store,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MdsapMarkdownStorage",
    "get_mdsap_markdown_store",
]


class MdsapMarkdownStorage:
    """Facade over RegulatoryMarkdownStorage for 7-country regulation management.

    Delegates all operations to the unified regulatory markdown storage.
    Provides the interface expected by ``report_api.py`` endpoints:

    - ``get_upload_reminders()``  → regulations needing user upload
    - ``list_all_regulations()``  → status of all 7+1 regulations
    - ``save_uploaded_regulation()`` → save user-uploaded regulation text
    - ``export_predefined_profiles()`` → generate profile Markdown from
      compliance_rules PREDEFINED_REGULATIONS
    """

    def __init__(self, store: Optional[RegulatoryMarkdownStorage] = None):
        self._store = store or get_regulatory_markdown_store()

    # ------ Delegated methods ------

    def get_upload_reminders(self) -> list[dict]:
        """Get list of regulations that still need user-uploaded full text."""
        return self._store.get_upload_reminders()

    def list_all_regulations(self) -> list[dict]:
        """List all 7+1 regulations with their availability status."""
        return self._store.list_all_regulations()

    def save_uploaded_regulation(
        self, regulation_id: str, filename: str, content: str
    ) -> dict:
        """Save a user-uploaded regulation document.

        The file is placed under ``{country}/uploads/`` inside the unified
        ``regulatory_markdown_storage/`` directory.
        """
        return self._store.save_uploaded_regulation(regulation_id, filename, content)

    def export_predefined_profiles(self) -> dict:
        """Export all predefined regulation profiles as Markdown files.

        Creates ``{country}/predefined/{REG_ID}_profile.md`` for each
        profile registered in ``compliance_rules.PREDEFINED_REGULATIONS``.
        """
        return self._store.export_predefined_profiles()

    # ------ Convenience accessors ------

    def get_document(self, doc_id: str):
        """Get a document by its ID."""
        return self._store.get_document(doc_id)

    def list_documents(self, region: Optional[str] = None, status: str = "active"):
        """List documents, optionally filtered by region."""
        return self._store.list_documents(region=region, status=status)

    def get_stats(self) -> dict:
        """Return storage statistics."""
        return self._store.get_stats()


# ============================================================
# Singleton accessor
# ============================================================

_mdsap_store_instance: Optional[MdsapMarkdownStorage] = None


def get_mdsap_markdown_store() -> MdsapMarkdownStorage:
    """Get or create singleton MdsapMarkdownStorage instance.

    This is the primary entry point imported by ``report_api.py``.
    """
    global _mdsap_store_instance
    if _mdsap_store_instance is None:
        _mdsap_store_instance = MdsapMarkdownStorage()
    return _mdsap_store_instance
