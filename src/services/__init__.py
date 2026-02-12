"""
AI-QMS Phase 1 - Services Module
Shared services for cross-agent access.
"""

from .markdown_store_service import get_markdown_store, MarkdownStoreService

__all__ = ["get_markdown_store", "MarkdownStoreService"]
