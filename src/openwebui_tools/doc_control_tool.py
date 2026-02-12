"""
Open WebUI Tool: Document Control Sub-Agent Integration
This tool allows the main agent in Open WebUI to interact with the
Gradio Document Control sub-agent for QMS document management.

To use in Open WebUI:
1. Go to Workspace > Tools
2. Create new tool
3. Copy this code into the tool editor
"""

import json
import requests
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    """
    AI-QMS Document Control Tools for Open WebUI
    Integrates with Gradio sub-agent on port 7860
    """

    class Valves(BaseModel):
        """Configuration for the Document Control tool"""

        GRADIO_URL: str = Field(
            default="http://localhost:7860",
            description="URL of the Gradio Document Control sub-agent",
        )
        TIMEOUT: int = Field(default=30, description="Request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

    def get_document_status(self) -> str:
        """
        Get the current document storage status from the QMS system.
        Returns the number of documents stored and remaining capacity.

        :return: JSON string with storage status
        """
        try:
            # Call Gradio API to get status
            response = requests.post(
                f"{self.valves.GRADIO_URL}/api/predict",
                json={
                    "fn_index": 0,  # This would need to be adjusted based on actual Gradio API
                    "data": ["狀態"],
                },
                timeout=self.valves.TIMEOUT,
            )

            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Document Control sub-agent is running",
                        "url": self.valves.GRADIO_URL,
                        "status": "Use the Gradio interface at http://localhost:7860 for document operations",
                    },
                    ensure_ascii=False,
                )
            else:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Gradio returned status {response.status_code}",
                    },
                    ensure_ascii=False,
                )

        except requests.exceptions.ConnectionError:
            return json.dumps(
                {
                    "success": False,
                    "error": "Cannot connect to Gradio sub-agent. Please ensure it's running on port 7860",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def open_document_control(self) -> str:
        """
        Provide instructions to access the Document Control sub-agent interface.
        The Gradio interface handles document upload, OCR, version control, and stamp confirmation.

        :return: Instructions for accessing the Document Control interface
        """
        return json.dumps(
            {
                "success": True,
                "message": "Document Control Sub-Agent",
                "interface_url": "http://localhost:7860",
                "features": [
                    "Document Upload (PDF, images)",
                    "Vision-First OCR Processing",
                    "Document Type Detection (New vs Version Update)",
                    "Stamp Confirmation Workflow",
                    "Tamper-Proof Audit Trail (SHA-256)",
                    "Markdown Storage with Version Control",
                ],
                "instructions": [
                    "1. Open http://localhost:7860 in your browser",
                    "2. Select LLM Provider (Ollama recommended for local)",
                    "3. Upload document file",
                    "4. Click 'Start Processing' for OCR",
                    "5. Confirm document type (New or Version Update)",
                    "6. For version updates, complete stamp confirmation",
                    "7. Document will be saved with audit trail",
                ],
                "poc_limit": "20 documents maximum",
            },
            ensure_ascii=False,
            indent=2,
        )

    def list_documents(self) -> str:
        """
        List all documents currently stored in the QMS system.

        :return: JSON string with list of documents
        """
        try:
            # Read from the document registry directly
            import os

            registry_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "markdown_storage",
                "metadata",
                "document_registry.json",
            )

            if os.path.exists(registry_path):
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)

                documents = registry.get("documents", [])
                return json.dumps(
                    {
                        "success": True,
                        "total_documents": len(documents),
                        "remaining_slots": 20 - len(documents),
                        "documents": [
                            {
                                "doc_id": doc.get("doc_id"),
                                "title": doc.get("title"),
                                "type": doc.get("doc_type"),
                                "version": doc.get("current_version"),
                                "status": doc.get("status"),
                            }
                            for doc in documents
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                return json.dumps(
                    {
                        "success": True,
                        "total_documents": 0,
                        "remaining_slots": 20,
                        "documents": [],
                        "message": "No documents stored yet",
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def get_audit_log(self, limit: int = 10) -> str:
        """
        Get recent audit log entries from the QMS system.
        The audit log uses SHA-256 hash chain for tamper-proof records.

        :param limit: Maximum number of records to return (default 10)
        :return: JSON string with audit log entries
        """
        try:
            import os

            audit_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
                "audit_log.json",
            )

            if os.path.exists(audit_path):
                with open(audit_path, "r", encoding="utf-8") as f:
                    audit_data = json.load(f)

                records = audit_data.get("records", [])
                recent_records = records[-limit:] if len(records) > limit else records

                return json.dumps(
                    {
                        "success": True,
                        "total_records": len(records),
                        "showing": len(recent_records),
                        "records": [
                            {
                                "timestamp": rec.get("timestamp"),
                                "action": rec.get("action"),
                                "document_id": rec.get("document_id"),
                                "user_id": rec.get("user_id"),
                                "hash": rec.get("current_hash", "")[:16] + "...",
                            }
                            for rec in recent_records
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                return json.dumps(
                    {
                        "success": True,
                        "total_records": 0,
                        "records": [],
                        "message": "No audit records yet",
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# For testing
if __name__ == "__main__":
    tools = Tools()
    print("=== Document Status ===")
    print(tools.get_document_status())
    print("\n=== Open Document Control ===")
    print(tools.open_document_control())
    print("\n=== List Documents ===")
    print(tools.list_documents())
    print("\n=== Audit Log ===")
    print(tools.get_audit_log())
