"""
AI-QMS Phase 1 - Document Search Tools
Cross-agent tools for searching and retrieving documents from Markdown storage.

v2.4.8 - New file for cross-agent document access

These tools can be used by:
- Main Agent: For answering questions about stored documents
- Sub-Agents: For referencing related documents
- LangGraph workflows: For document-aware processing
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.services.markdown_store_service import get_markdown_store, MarkdownStoreService


# ============================================================
# Functional Tools (for direct use)
# ============================================================


def tool_search_docs(
    query: str,
    doc_type: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search documents in the Markdown storage by content.

    This tool searches across all OCR-processed documents stored in the
    Markdown database. It performs full-text search and returns matching
    documents with snippets.

    Args:
        query: Search query string (case-insensitive, supports multiple words)
        doc_type: Filter by document type (SOP, WI, FORM, DHF, OTHER)
        limit: Maximum number of results to return (default: 10)

    Returns:
        List of matching documents with:
        - doc_id: Document identifier
        - title: Document title
        - doc_type: Document type
        - version: Document version
        - snippet: Text snippet around the match
        - path: Path to the Markdown file

    Example:
        >>> results = tool_search_docs("品質手冊")
        >>> for doc in results:
        ...     print(f"{doc['doc_id']}: {doc['title']}")
    """
    service = MarkdownStoreService()
    return service.search(query=query, doc_type=doc_type, limit=limit)


def tool_get_doc(
    doc_id: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get a specific document by ID from the Markdown storage.

    Retrieves the full content and metadata of a document. If no version
    is specified, returns the latest version.

    Args:
        doc_id: Document identifier (e.g., "SOP-001", "WI-003")
        version: Specific version to retrieve (e.g., "1.0", "2.1")
                 If None, returns the latest version.

    Returns:
        Dict with:
        - success: Boolean indicating if document was found
        - content: Full Markdown content of the document
        - metadata: Document metadata including:
            - doc_id, title, version, doc_type, status
            - created_at, created_by
            - ocr_provider, ocr_confidence
            - hash

    Example:
        >>> doc = tool_get_doc("SOP-001")
        >>> if doc['success']:
        ...     print(doc['content'][:500])
    """
    service = MarkdownStoreService()
    return service.get_document(doc_id=doc_id, version=version)


def tool_list_docs(
    doc_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all documents in the Markdown storage.

    Returns a summary of all stored documents, optionally filtered by type.

    Args:
        doc_type: Filter by document type (SOP, WI, FORM, DHF, OTHER)
                  If None, returns all documents.

    Returns:
        List of document summaries with:
        - doc_id: Document identifier
        - title: Document title
        - doc_type: Document type
        - current_version: Latest version number
        - status: Document status (active, obsolete, draft)
        - version_count: Number of versions

    Example:
        >>> docs = tool_list_docs(doc_type="SOP")
        >>> print(f"Found {len(docs)} SOPs")
    """
    service = MarkdownStoreService()
    return service.list_documents(doc_type=doc_type)


def tool_get_stats() -> Dict[str, Any]:
    """
    Get storage statistics.

    Returns:
        Dict with:
        - total_documents: Total number of documents
        - total_versions: Total number of versions across all documents
        - remaining_slots: Remaining document slots (POC limit)
        - limit: Maximum document limit
        - by_type: Document count by type
    """
    service = MarkdownStoreService()
    return service.get_stats()


# ============================================================
# Class-based Tool (for LangGraph/LangChain integration)
# ============================================================


class DocumentSearchTool:
    """
    Document search tool for LangGraph/LangChain integration.

    This class provides a structured interface for document search
    that can be easily integrated with LangGraph workflows.

    Usage:
        tool = DocumentSearchTool()
        results = tool.search("品質手冊")
        doc = tool.get("SOP-001")
    """

    name = "document_search"
    description = """
    Search and retrieve documents from the QMS Markdown storage.
    Use this tool to find documents by content, get specific documents by ID,
    or list all available documents.
    """

    def __init__(self):
        self._service = MarkdownStoreService()

    def search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search documents by content."""
        return self._service.search(query=query, doc_type=doc_type, limit=limit)

    def get(
        self,
        doc_id: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a specific document by ID."""
        return self._service.get_document(doc_id=doc_id, version=version)

    def list(
        self,
        doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all documents."""
        return self._service.list_documents(doc_type=doc_type)

    def stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        return self._service.get_stats()

    def __call__(self, action: str, **kwargs) -> Any:
        """
        Callable interface for LangGraph tool use.

        Args:
            action: One of "search", "get", "list", "stats"
            **kwargs: Arguments for the action

        Returns:
            Result of the action
        """
        actions = {
            "search": self.search,
            "get": self.get,
            "list": self.list,
            "stats": self.stats,
        }

        if action not in actions:
            return {
                "error": f"Unknown action: {action}. Valid actions: {list(actions.keys())}"
            }

        try:
            return actions[action](**kwargs)
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# Tool Definitions for LLM Function Calling
# ============================================================

TOOL_DEFINITIONS = [
    {
        "name": "search_documents",
        "description": "Search QMS documents by content. Returns matching documents with snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "doc_type": {
                    "type": "string",
                    "enum": ["SOP", "WI", "FORM", "DHF", "OTHER"],
                    "description": "Filter by document type (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_document",
        "description": "Get a specific document by ID. Returns full content and metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "Document identifier (e.g., SOP-001)",
                },
                "version": {
                    "type": "string",
                    "description": "Specific version (optional, defaults to latest)",
                },
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List all documents in storage. Returns document summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": ["SOP", "WI", "FORM", "DHF", "OTHER"],
                    "description": "Filter by document type (optional)",
                }
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """
    Execute a tool by name with given arguments.
    For use with LLM function calling.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool execution result
    """
    tool_map = {
        "search_documents": tool_search_docs,
        "get_document": tool_get_doc,
        "list_documents": tool_list_docs,
        "get_stats": tool_get_stats,
    }

    if tool_name not in tool_map:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return tool_map[tool_name](**arguments)
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("Document Search Tools Test")
    print("=" * 50)

    # Test functional tools
    print("\n1. Testing tool_search_docs...")
    results = tool_search_docs("test")
    print(f"   Found {len(results)} documents")
    for r in results:
        print(f"   - {r['doc_id']}: {r['title']}")

    print("\n2. Testing tool_list_docs...")
    docs = tool_list_docs()
    print(f"   Total documents: {len(docs)}")

    print("\n3. Testing tool_get_stats...")
    stats = tool_get_stats()
    print(f"   Stats: {stats}")

    # Test class-based tool
    print("\n4. Testing DocumentSearchTool class...")
    tool = DocumentSearchTool()
    results = tool("search", query="test")
    print(f"   Search via __call__: {len(results)} results")

    print("\n5. Testing execute_tool...")
    result = execute_tool("search_documents", {"query": "test"})
    print(f"   Execute tool: {len(result)} results")

    print("\n" + "=" * 50)
    print("All tests passed!")
