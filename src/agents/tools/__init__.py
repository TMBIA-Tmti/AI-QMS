"""
AI-QMS Phase 1 - Agent Tools Module
Tools for cross-agent document access and operations.
"""

from .documents import (
    tool_search_docs,
    tool_get_doc,
    tool_list_docs,
    DocumentSearchTool,
)

__all__ = [
    "tool_search_docs",
    "tool_get_doc",
    "tool_list_docs",
    "DocumentSearchTool",
]
