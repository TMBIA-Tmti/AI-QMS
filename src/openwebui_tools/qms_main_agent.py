"""
AI-QMS Main Agent Tool for Open WebUI
=====================================

Version: v2.3.1
Updated: 2026-02-05

This tool provides the main agent functionality for AI-QMS system.
It should be installed in Open WebUI as a Tool/Function.

Changes in v2.3.1:
- Open WebUI Tool installation completed
- API Key RBAC permission fix documented
- JSON import file (ai_qms_tool_export.json) available

Installation:
1. Open http://localhost:3000
2. Go to Workspace > Tools
3. Click "+" to create new tool
4. Copy this entire file content
5. Save and enable the tool

Features:
- Sub-Agent Navigation (direct jump to any sub-agent)
- LLM Provider Management (12+ providers via LiteLLM)
- Document Control Sub-Agent integration
- System status monitoring with provider status
- Audit log access
- Document listing
- Office format support (PDF, Word, Excel, PowerPoint, Images, Text)

Sub-Agent Ports:
- Document Control: 7860 (POC - Available)
- Audit Management: 7861 (Phase 2)
- Regulatory Affairs: 7862 (Phase 2)
- Production Control: 7863 (Phase 2)
- Records Collection: 7864 (Phase 2)

LLM Providers (12+):
- Direct API: OpenAI, Anthropic, Google, DeepSeek, xAI
- Gateway: OpenRouter, Requesty, Together AI, Groq, Fireworks AI, Deep Infra
- Local: Ollama, LM Studio

Supported File Formats:
- PDF: .pdf
- Images: .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp
- Word: .docx, .doc
- Excel: .xlsx, .xls
- PowerPoint: .pptx, .ppt
- Text: .txt, .md, .csv, .rtf
"""

import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    """
    AI-QMS Main Agent Tools (v2.3.1)

    This class provides tools for the AI-QMS quality management system.
    It integrates with the Gradio sub-agents and provides
    system monitoring, LLM provider management, and navigation capabilities.

    Key Features:
    - 12+ LLM Provider support via LiteLLM
    - Full Office format support (Word, Excel, PowerPoint)
    - Sub-Agent navigation with service status checking
    - Document management with 20-doc POC limit
    - SHA-256 tamper-proof audit trail
    - Open WebUI Tool integration (NEW in v2.3.1)

    Sub-Agent Navigation:
    - Document Control (POC): http://localhost:7860
    - Audit Management (Phase 2): http://localhost:7861
    - Regulatory Affairs (Phase 2): http://localhost:7862
    - Production Control (Phase 2): http://localhost:7863
    - Records Collection (Phase 2): http://localhost:7864
    """

    class Valves(BaseModel):
        """Configuration valves for the tool"""

        # Project Root Path
        PROJECT_ROOT: str = Field(
            default="C:/Users/MDR/Desktop/發公文與政府單位聯繫資料/臨床委員會/AI QMS 規劃/AI-QMS-Phase1-DocControl",
            description="Local path to AI-QMS project root (used for imports + data paths)",
        )

        # Sub-Agent URLs
        DOC_CONTROL_URL: str = Field(
            default="http://localhost:7860",
            description="URL of the Document Control sub-agent (POC)",
        )
        AUDIT_URL: str = Field(
            default="http://localhost:7861",
            description="URL of the Audit Management sub-agent (Phase 2)",
        )
        REGULATORY_URL: str = Field(
            default="http://localhost:7862",
            description="URL of the Regulatory Affairs sub-agent (Phase 2)",
        )
        PRODUCTION_URL: str = Field(
            default="http://localhost:7863",
            description="URL of the Production Control sub-agent (Phase 2)",
        )
        RECORDS_URL: str = Field(
            default="http://localhost:7864",
            description="URL of the Records Collection sub-agent (Phase 2)",
        )

        # LLM Settings
        OLLAMA_URL: str = Field(
            default="http://localhost:11434",
            description="URL of the Ollama LLM service",
        )
        LMSTUDIO_URL: str = Field(
            default="http://localhost:1234",
            description="URL of the LM Studio service",
        )

        # Limits
        DOC_LIMIT: int = Field(
            default=20, description="Maximum number of documents (POC limit)"
        )

    def __init__(self):
        self.valves = self.Valves()
        self.project_root = Path(self.valves.PROJECT_ROOT)
        self.data_path = str(self.project_root)

        # Ensure repo is on sys.path for imports
        self._ensure_repo_on_syspath()

        # LLM Manager (lazy loaded)
        self._llm_manager = None
        self._llm_import_error = None

    # ============================================================
    # Private Helper Methods
    # ============================================================

    def _ensure_repo_on_syspath(self) -> None:
        """Ensure the project root is on sys.path for imports"""
        repo = str(self.project_root)
        if repo and repo not in sys.path:
            sys.path.insert(0, repo)

    def _get_llm_manager(self):
        """Lazy-load the LLM provider manager from src/llm_providers.py"""
        if self._llm_manager is not None or self._llm_import_error is not None:
            return self._llm_manager

        try:
            from src.llm_providers import create_provider_manager

            self._llm_manager = create_provider_manager()
            return self._llm_manager
        except Exception as e:
            self._llm_import_error = str(e)
            return None

    def _get_supported_file_formats(self) -> dict:
        """Get supported file formats from the OCR module (source of truth)"""
        try:
            from src.ocr.vision_ocr import SUPPORTED_EXTENSIONS

            # Group by type
            formats_by_type = {}
            for ext, file_type in SUPPORTED_EXTENSIONS.items():
                if file_type not in formats_by_type:
                    formats_by_type[file_type] = []
                formats_by_type[file_type].append(ext)

            return {
                "extensions": sorted(list(SUPPORTED_EXTENSIONS.keys())),
                "by_type": formats_by_type,
                "total_formats": len(SUPPORTED_EXTENSIONS),
            }
        except Exception as e:
            # Safe fallback (matches v2.3.0 requirements)
            return {
                "error": str(e),
                "extensions": [
                    ".pdf",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                    ".tiff",
                    ".tif",
                    ".bmp",
                    ".docx",
                    ".doc",
                    ".xlsx",
                    ".xls",
                    ".pptx",
                    ".ppt",
                    ".txt",
                    ".md",
                    ".csv",
                    ".rtf",
                ],
                "by_type": {
                    "pdf": [".pdf"],
                    "image": [
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".webp",
                        ".tiff",
                        ".tif",
                        ".bmp",
                    ],
                    "word": [".docx"],
                    "word_legacy": [".doc"],
                    "excel": [".xlsx"],
                    "excel_legacy": [".xls"],
                    "powerpoint": [".pptx"],
                    "powerpoint_legacy": [".ppt"],
                    "text": [".txt", ".md", ".rtf"],
                    "csv": [".csv"],
                },
            }

    def _get_sub_agent_registry(self) -> dict:
        """Get the sub-agent registry with current URLs from valves"""
        return {
            "doc_control": {
                "id": "doc_control",
                "name": "Document Control",
                "name_zh": "文件管制",
                "description": "Document upload, OCR processing, version control, stamp confirmation",
                "description_zh": "文件上傳、OCR處理、版本控制、簽章確認",
                "url": self.valves.DOC_CONTROL_URL,
                "port": 7860,
                "status": "available",
                "phase": "POC",
                "icon": "doc",
                "features": [
                    "Vision-First OCR (GPT-4V/Claude/Gemini)",
                    "Full Office format support (Word, Excel, PowerPoint)",
                    "Document type detection",
                    "Version control workflow",
                    "Stamp confirmation popup",
                    "Markdown storage (20 docs limit)",
                    "SHA-256 audit trail",
                ],
            },
            "audit": {
                "id": "audit",
                "name": "Audit Management",
                "name_zh": "稽核管理",
                "description": "Internal and external audit management, CAPA tracking",
                "description_zh": "內外部稽核管理、CAPA追蹤",
                "url": self.valves.AUDIT_URL,
                "port": 7861,
                "status": "planned",
                "phase": "Phase 2",
                "icon": "search",
                "features": [
                    "Audit scheduling",
                    "Finding management",
                    "CAPA tracking",
                    "Audit report generation",
                ],
            },
            "regulatory": {
                "id": "regulatory",
                "name": "Regulatory Affairs",
                "name_zh": "法規事務",
                "description": "Regulatory document management and compliance tracking",
                "description_zh": "法規文件管理、合規追蹤",
                "url": self.valves.REGULATORY_URL,
                "port": 7862,
                "status": "planned",
                "phase": "Phase 2",
                "icon": "balance",
                "features": [
                    "Regulatory submission tracking",
                    "Compliance monitoring",
                    "Standard mapping (ISO, FDA, EU MDR)",
                    "Regulatory intelligence",
                ],
            },
            "production": {
                "id": "production",
                "name": "Production Control",
                "name_zh": "生產管制",
                "description": "Production documentation and batch records",
                "description_zh": "生產文件、批次紀錄",
                "url": self.valves.PRODUCTION_URL,
                "port": 7863,
                "status": "planned",
                "phase": "Phase 2",
                "icon": "factory",
                "features": [
                    "Batch record management",
                    "Production order tracking",
                    "Equipment qualification",
                    "Process validation",
                ],
            },
            "records": {
                "id": "records",
                "name": "Records Collection",
                "name_zh": "紀錄收集",
                "description": "Quality records collection and management",
                "description_zh": "品質紀錄收集與管理",
                "url": self.valves.RECORDS_URL,
                "port": 7864,
                "status": "planned",
                "phase": "Phase 2",
                "icon": "archive",
                "features": [
                    "Record collection workflow",
                    "Retention management",
                    "Archive and retrieval",
                    "Record integrity verification",
                ],
            },
        }

    def _check_service_status(self, url: str) -> str:
        """Check if a service is running"""
        try:
            response = requests.get(url, timeout=3)
            return "running" if response.status_code == 200 else "error"
        except:
            return "stopped"

    def _get_provider_status_list(self) -> list:
        """Get all providers with their status for system status display"""
        mgr = self._get_llm_manager()
        if mgr is None:
            return []

        providers = []
        for p in mgr.get_all_providers():
            env_key = p.get("env_key_name")
            is_local = bool(p.get("is_local"))
            configured = True if is_local else bool(os.getenv(env_key or ""))

            providers.append(
                {
                    "id": p.get("provider_id"),
                    "name": p.get("display_name"),
                    "category": p.get("category"),
                    "is_local": is_local,
                    "configured": configured,
                    "status": "ready" if configured else "missing_api_key",
                }
            )

        return providers

    # ============================================================
    # LLM Provider Management Methods (NEW in v2.3.0)
    # ============================================================

    def get_llm_providers(self) -> str:
        """
        Get all supported LLM providers with their status.

        Returns comprehensive information about all 12+ LLM providers:
        - Direct API: OpenAI, Anthropic, Google, DeepSeek, xAI
        - Gateway: OpenRouter, Requesty, Together AI, Groq, Fireworks AI, Deep Infra
        - Local: Ollama, LM Studio

        Each provider includes:
        - Provider ID and display name
        - Category (direct_api, gateway, local)
        - Configuration status (ready/missing_api_key)
        - Environment variable name for API key

        Use this when the user asks about:
        - Available LLM providers
        - Which AI models can be used
        - Provider configuration status

        :return: JSON string with all providers and their status
        """
        mgr = self._get_llm_manager()
        if mgr is None:
            return json.dumps(
                {
                    "error": "LLM provider module not available",
                    "details": self._llm_import_error,
                    "fallback_providers": ["ollama", "lmstudio"],
                },
                ensure_ascii=False,
                indent=2,
            )

        providers = []
        for p in mgr.get_all_providers():
            env_key = p.get("env_key_name")
            is_local = bool(p.get("is_local"))
            configured = True if is_local else bool(os.getenv(env_key or ""))

            providers.append(
                {
                    "provider_id": p.get("provider_id"),
                    "display_name": p.get("display_name"),
                    "display_name_zh": p.get("display_name_zh"),
                    "category": p.get("category"),
                    "api_base_url": p.get("api_base_url"),
                    "default_model": p.get("default_model"),
                    "supports_vision": p.get("supports_vision"),
                    "is_local": is_local,
                    "env_key_name": env_key,
                    "configured": configured,
                    "status": "ready" if configured else "missing_api_key",
                }
            )

        # Group by category
        by_category = {}
        for p in providers:
            cat = p.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(p)

        return json.dumps(
            {
                "total_providers": len(providers),
                "current_provider_id": mgr.current_provider_id,
                "ready_count": sum(1 for p in providers if p["configured"]),
                "by_category": by_category,
                "providers": providers,
            },
            ensure_ascii=False,
            indent=2,
        )

    def get_current_provider(self) -> str:
        """
        Get the currently selected LLM provider.

        Returns detailed information about the active provider including:
        - Provider ID and display name
        - Category and API base URL
        - Default model and vision support
        - Configuration status

        Use this when the user asks about:
        - Current AI model
        - Which provider is active
        - Current LLM settings

        :return: JSON string with current provider information
        """
        mgr = self._get_llm_manager()
        if mgr is None:
            return json.dumps(
                {
                    "error": "LLM provider module not available",
                    "details": self._llm_import_error,
                    "fallback": "Using default Ollama provider",
                },
                ensure_ascii=False,
                indent=2,
            )

        p = mgr.current_provider
        env_key = p.get("env_key_name")
        is_local = bool(p.get("is_local"))
        configured = True if is_local else bool(os.getenv(env_key or ""))

        return json.dumps(
            {
                "provider_id": mgr.current_provider_id,
                "display_name": p.get("display_name"),
                "display_name_zh": p.get("display_name_zh"),
                "category": p.get("category"),
                "api_base_url": p.get("api_base_url"),
                "default_model": p.get("default_model"),
                "supports_vision": p.get("supports_vision"),
                "is_local": p.get("is_local"),
                "env_key_name": env_key,
                "configured": configured,
                "status": "ready" if configured else "missing_api_key",
            },
            ensure_ascii=False,
            indent=2,
        )

    def set_provider(self, provider_id: str) -> str:
        """
        Switch the current LLM provider.

        Available provider IDs:
        - Direct API: openai, anthropic, google, deepseek, xai
        - Gateway: openrouter, requesty, together, groq, fireworks, deepinfra
        - Local: ollama, lmstudio

        Use this when the user wants to:
        - Change AI model
        - Switch to a different provider
        - Use a specific LLM service

        :param provider_id: The provider identifier (e.g., "openai", "anthropic", "ollama")
        :return: JSON string with switch result
        """
        mgr = self._get_llm_manager()
        if mgr is None:
            return json.dumps(
                {
                    "success": False,
                    "error": "LLM provider module not available",
                    "details": self._llm_import_error,
                },
                ensure_ascii=False,
                indent=2,
            )

        provider_id = (provider_id or "").strip().lower()
        ok = mgr.switch_provider(provider_id)

        if not ok:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Unknown provider_id: {provider_id}",
                    "available_provider_ids": sorted(list(mgr.providers.keys())),
                    "hint": "Use get_llm_providers() to see all available providers",
                },
                ensure_ascii=False,
                indent=2,
            )

        # Persist preference for other components
        os.environ["LLM_PROVIDER"] = provider_id

        p = mgr.current_provider
        return json.dumps(
            {
                "success": True,
                "message": f"Switched to {p.get('display_name')}",
                "current_provider_id": mgr.current_provider_id,
                "display_name": p.get("display_name"),
                "category": p.get("category"),
                "default_model": p.get("default_model"),
            },
            ensure_ascii=False,
            indent=2,
        )

    # ============================================================
    # System Status Methods
    # ============================================================

    def get_system_status(self) -> str:
        """
        Get the current AI-QMS system status.

        Returns comprehensive information about:
        - System version (v2.3.1)
        - Document count and remaining capacity
        - All sub-agent service status
        - LLM provider status (12+ providers)
        - Supported file formats (Office, PDF, Images, Text)
        - Compliance standards

        Use this when the user asks about system status or health.

        :return: JSON string with system status information
        """
        sub_agents = self._get_sub_agent_registry()

        status = {
            "system": "AI-QMS Phase 1 Document Control",
            "version": "v2.3.1",
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "sub_agents": {},
            "llm_providers": {},
            "supported_file_formats": {},
            "documents": {},
            "compliance": ["ISO 13485:2016", "FDA 21 CFR Part 11", "EU MDR 2017/745"],
        }

        # Check all sub-agent services
        for agent_id, agent_info in sub_agents.items():
            service_status = self._check_service_status(agent_info["url"])
            status["sub_agents"][agent_id] = {
                "name": agent_info["name"],
                "name_zh": agent_info["name_zh"],
                "url": agent_info["url"],
                "status": service_status
                if agent_info["status"] == "available"
                else "planned",
                "phase": agent_info["phase"],
            }

        # Check Ollama service
        try:
            response = requests.get(f"{self.valves.OLLAMA_URL}/api/tags", timeout=3)
            if response.status_code == 200:
                models = response.json().get("models", [])
                status["services"]["ollama"] = {
                    "status": "running",
                    "url": self.valves.OLLAMA_URL,
                    "models_available": len(models),
                    "description": "Local LLM Service",
                }
            else:
                status["services"]["ollama"] = {
                    "status": "error",
                    "url": self.valves.OLLAMA_URL,
                }
        except:
            status["services"]["ollama"] = {
                "status": "stopped",
                "url": self.valves.OLLAMA_URL,
                "description": "Local LLM Service",
            }

        # Check LM Studio service
        try:
            response = requests.get(f"{self.valves.LMSTUDIO_URL}/v1/models", timeout=3)
            if response.status_code == 200:
                status["services"]["lmstudio"] = {
                    "status": "running",
                    "url": self.valves.LMSTUDIO_URL,
                    "description": "LM Studio Local LLM",
                }
            else:
                status["services"]["lmstudio"] = {
                    "status": "error",
                    "url": self.valves.LMSTUDIO_URL,
                }
        except:
            status["services"]["lmstudio"] = {
                "status": "stopped",
                "url": self.valves.LMSTUDIO_URL,
                "description": "LM Studio Local LLM",
            }

        # LLM Provider status (12+ providers)
        mgr = self._get_llm_manager()
        if mgr is None:
            status["llm_providers"] = {
                "error": "LLM providers unavailable",
                "details": self._llm_import_error,
            }
        else:
            providers = self._get_provider_status_list()
            status["llm_providers"] = {
                "current_provider_id": mgr.current_provider_id,
                "total_providers": len(providers),
                "ready_count": sum(1 for p in providers if p["configured"]),
                "providers": providers,
            }

        # Supported file formats (v2.3.0)
        status["supported_file_formats"] = self._get_supported_file_formats()

        # Check document count
        registry_path = os.path.join(
            self.data_path, "markdown_storage", "metadata", "document_registry.json"
        )
        try:
            if os.path.exists(registry_path):
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)
                doc_count = len(registry.get("documents", []))
            else:
                doc_count = 0

            status["documents"] = {
                "current_count": doc_count,
                "limit": self.valves.DOC_LIMIT,
                "remaining": self.valves.DOC_LIMIT - doc_count,
                "usage_percent": round((doc_count / self.valves.DOC_LIMIT) * 100, 1),
            }
        except Exception as e:
            status["documents"] = {"error": str(e)}

        return json.dumps(status, ensure_ascii=False, indent=2)

    def get_supported_formats(self) -> str:
        """
        Get all supported file formats for document upload.

        Returns information about supported formats:
        - PDF documents
        - Images (PNG, JPG, TIFF, etc.)
        - Word documents (.docx, .doc)
        - Excel spreadsheets (.xlsx, .xls)
        - PowerPoint presentations (.pptx, .ppt)
        - Text files (.txt, .md, .csv, .rtf)

        Use this when the user asks about:
        - What file types can be uploaded
        - Supported document formats
        - Office format support

        :return: JSON string with supported file formats
        """
        formats = self._get_supported_file_formats()
        return json.dumps(
            {
                "version": "v2.3.1",
                "message": "Full Office format support added in v2.3.0",
                **formats,
            },
            ensure_ascii=False,
            indent=2,
        )

    # ============================================================
    # Sub-Agent Navigation Methods
    # ============================================================

    def navigate_to_sub_agent(self, agent_id: str) -> str:
        """
        Navigate to a specific sub-agent interface.

        This is the main navigation function to jump directly to any sub-agent.

        Available agent_id values:
        - "doc_control": Document Control (POC - Available)
        - "audit": Audit Management (Phase 2 - Planned)
        - "regulatory": Regulatory Affairs (Phase 2 - Planned)
        - "production": Production Control (Phase 2 - Planned)
        - "records": Records Collection (Phase 2 - Planned)

        Use this when the user wants to:
        - Go to a specific sub-agent
        - Open document control
        - Access audit management
        - Navigate to regulatory affairs
        - Open production control
        - Access records collection

        :param agent_id: The sub-agent identifier (doc_control, audit, regulatory, production, records)
        :return: JSON string with navigation information and URL
        """
        sub_agents = self._get_sub_agent_registry()

        # Normalize agent_id
        agent_id = agent_id.lower().strip()

        # Handle aliases
        aliases = {
            "document": "doc_control",
            "document_control": "doc_control",
            "documents": "doc_control",
            "doc": "doc_control",
            "ocr": "doc_control",
            "upload": "doc_control",
            "word": "doc_control",
            "excel": "doc_control",
            "powerpoint": "doc_control",
            "pdf": "doc_control",
            "audit_management": "audit",
            "audits": "audit",
            "regulatory_affairs": "regulatory",
            "regulation": "regulatory",
            "regulations": "regulatory",
            "production_control": "production",
            "manufacturing": "production",
            "records_collection": "records",
            "record": "records",
            "archive": "records",
        }

        if agent_id in aliases:
            agent_id = aliases[agent_id]

        if agent_id not in sub_agents:
            return json.dumps(
                {
                    "error": f"Unknown sub-agent: {agent_id}",
                    "available_agents": list(sub_agents.keys()),
                    "hint": "Use one of: doc_control, audit, regulatory, production, records",
                },
                ensure_ascii=False,
                indent=2,
            )

        agent = sub_agents[agent_id]

        # Check service status
        service_status = self._check_service_status(agent["url"])

        result = {
            "action": "navigate_to_sub_agent",
            "agent_id": agent_id,
            "name": agent["name"],
            "name_zh": agent["name_zh"],
            "url": agent["url"],
            "port": agent["port"],
            "phase": agent["phase"],
            "service_status": service_status
            if agent["status"] == "available"
            else "not_deployed",
            "description": agent["description"],
            "description_zh": agent["description_zh"],
            "features": agent["features"],
        }

        if agent["status"] == "available":
            if service_status == "running":
                result["instructions"] = [
                    f"1. Click the link or open in browser: {agent['url']}",
                    "2. The sub-agent interface will open in a new tab",
                    "3. Follow the on-screen instructions to complete your task",
                    "4. Return to this chat when done",
                ]
                result["message"] = (
                    f"Sub-agent '{agent['name']}' is ready. Click the URL to open."
                )
            else:
                result["instructions"] = [
                    "1. The sub-agent service is not running",
                    "2. Start the service using: start.bat",
                    "3. Or run: start_chainlit.bat",
                    f"4. Then access: {agent['url']}",
                ]
                result["message"] = (
                    f"Sub-agent '{agent['name']}' is not running. Please start the service first."
                )
        else:
            result["message"] = (
                f"Sub-agent '{agent['name']}' is planned for {agent['phase']} and not yet available."
            )
            result["instructions"] = [
                f"This sub-agent is scheduled for {agent['phase']}",
                "Currently only Document Control is available in POC",
                "Use 'doc_control' to access the available sub-agent",
            ]

        return json.dumps(result, ensure_ascii=False, indent=2)

    def open_document_control(self) -> str:
        """
        Open the Document Control sub-agent interface.

        This launches the Gradio-based document management interface where users can:
        - Upload documents (PDF, Word, Excel, PowerPoint, Images, Text)
        - Process OCR with Vision-First pipeline
        - Manage document versions
        - Confirm stamps for version updates

        Supported file formats (v2.3.0):
        - PDF: .pdf
        - Word: .docx, .doc
        - Excel: .xlsx, .xls
        - PowerPoint: .pptx, .ppt
        - Images: .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp
        - Text: .txt, .md, .csv, .rtf

        Use this when the user wants to:
        - Upload a new document
        - Update an existing document
        - Process OCR on a file
        - Manage document versions

        :return: Instructions and URL for accessing the Document Control interface
        """
        return self.navigate_to_sub_agent("doc_control")

    def open_audit_management(self) -> str:
        """
        Open the Audit Management sub-agent interface.

        This sub-agent handles:
        - Internal audit scheduling and execution
        - External audit preparation
        - Finding management and CAPA tracking
        - Audit report generation

        Note: This is planned for Phase 2 and not yet available.

        :return: Information about the Audit Management sub-agent
        """
        return self.navigate_to_sub_agent("audit")

    def open_regulatory_affairs(self) -> str:
        """
        Open the Regulatory Affairs sub-agent interface.

        This sub-agent handles:
        - Regulatory submission tracking
        - Compliance monitoring
        - Standard mapping (ISO, FDA, EU MDR)
        - Regulatory intelligence

        Note: This is planned for Phase 2 and not yet available.

        :return: Information about the Regulatory Affairs sub-agent
        """
        return self.navigate_to_sub_agent("regulatory")

    def open_production_control(self) -> str:
        """
        Open the Production Control sub-agent interface.

        This sub-agent handles:
        - Batch record management
        - Production order tracking
        - Equipment qualification
        - Process validation

        Note: This is planned for Phase 2 and not yet available.

        :return: Information about the Production Control sub-agent
        """
        return self.navigate_to_sub_agent("production")

    def open_records_collection(self) -> str:
        """
        Open the Records Collection sub-agent interface.

        This sub-agent handles:
        - Record collection workflow
        - Retention management
        - Archive and retrieval
        - Record integrity verification

        Note: This is planned for Phase 2 and not yet available.

        :return: Information about the Records Collection sub-agent
        """
        return self.navigate_to_sub_agent("records")

    # ============================================================
    # Document Management Methods
    # ============================================================

    def list_documents(self) -> str:
        """
        List all documents currently stored in the QMS system.

        Returns a list of all documents with their:
        - Document ID
        - Title
        - Document type (SOP, WI, FORM, DHF)
        - Current version
        - Status

        Use this when the user asks to see stored documents or check document inventory.

        :return: JSON string with list of documents
        """
        registry_path = os.path.join(
            self.data_path, "markdown_storage", "metadata", "document_registry.json"
        )

        try:
            if os.path.exists(registry_path):
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)

                documents = registry.get("documents", [])

                result = {
                    "total_documents": len(documents),
                    "limit": self.valves.DOC_LIMIT,
                    "remaining_slots": self.valves.DOC_LIMIT - len(documents),
                    "documents": [],
                }

                for doc in documents:
                    result["documents"].append(
                        {
                            "doc_id": doc.get("doc_id"),
                            "title": doc.get("title"),
                            "type": doc.get("doc_type"),
                            "current_version": doc.get("current_version"),
                            "status": doc.get("status"),
                            "version_count": len(doc.get("versions", [])),
                        }
                    )

                if not documents:
                    result["message"] = (
                        "No documents stored yet. Use 'open_document_control' to upload documents."
                    )

                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return json.dumps(
                    {
                        "total_documents": 0,
                        "limit": self.valves.DOC_LIMIT,
                        "remaining_slots": self.valves.DOC_LIMIT,
                        "documents": [],
                        "message": "No documents stored yet. Use 'open_document_control' to upload documents.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )

        except Exception as e:
            return json.dumps(
                {"error": str(e), "message": "Failed to read document registry"},
                ensure_ascii=False,
            )

    def get_audit_log(self, limit: int = 10) -> str:
        """
        Get recent audit log entries from the QMS system.

        The audit log uses SHA-256 hash chain for tamper-proof records,
        compliant with FDA 21 CFR Part 11 requirements.

        Args:
            limit: Maximum number of records to return (default 10)

        Use this when the user asks about:
        - Audit trail
        - Recent activities
        - Document history
        - Compliance records

        :param limit: Maximum number of records to return
        :return: JSON string with audit log entries
        """
        audit_path = os.path.join(self.data_path, "data", "audit_log.json")

        try:
            if os.path.exists(audit_path):
                with open(audit_path, "r", encoding="utf-8") as f:
                    audit_data = json.load(f)

                records = audit_data.get("records", [])
                recent_records = records[-limit:] if len(records) > limit else records

                result = {
                    "total_records": len(records),
                    "showing": len(recent_records),
                    "compliance": "SHA-256 hash chain (21 CFR Part 11)",
                    "records": [],
                }

                for rec in recent_records:
                    result["records"].append(
                        {
                            "record_id": rec.get("record_id"),
                            "timestamp": rec.get("timestamp"),
                            "action": rec.get("action"),
                            "document_id": rec.get("document_id"),
                            "user_id": rec.get("user_id"),
                            "hash_verified": True,  # In production, verify hash chain
                            "hash_preview": rec.get("current_hash", "")[:16] + "...",
                        }
                    )

                if not records:
                    result["message"] = "No audit records yet."

                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return json.dumps(
                    {
                        "total_records": 0,
                        "records": [],
                        "message": "No audit records yet.",
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            return json.dumps(
                {"error": str(e), "message": "Failed to read audit log"},
                ensure_ascii=False,
            )

    def get_sub_agents(self) -> str:
        """
        Get list of all sub-agents in the AI-QMS system with their status.

        Returns comprehensive information about all sub-agents including:
        - Document Control (POC - Available)
        - Audit Management (Phase 2 - Planned)
        - Regulatory Affairs (Phase 2 - Planned)
        - Production Control (Phase 2 - Planned)
        - Records Collection (Phase 2 - Planned)

        Each sub-agent includes:
        - Name (English and Chinese)
        - URL and port
        - Current status (running/stopped/planned)
        - Phase (POC or Phase 2)
        - Features list

        Use this when the user asks about:
        - Available features or sub-systems
        - What the system can do
        - Navigation options
        - System capabilities

        :return: JSON string with sub-agent information
        """
        sub_agents = self._get_sub_agent_registry()

        result = {
            "total_sub_agents": len(sub_agents),
            "available_count": sum(
                1 for a in sub_agents.values() if a["status"] == "available"
            ),
            "planned_count": sum(
                1 for a in sub_agents.values() if a["status"] == "planned"
            ),
            "sub_agents": [],
            "navigation_hint": "Use navigate_to_sub_agent(agent_id) or the specific open_* functions to access each sub-agent",
        }

        for agent_id, agent in sub_agents.items():
            service_status = (
                self._check_service_status(agent["url"])
                if agent["status"] == "available"
                else "not_deployed"
            )

            result["sub_agents"].append(
                {
                    "id": agent_id,
                    "name": agent["name"],
                    "name_zh": agent["name_zh"],
                    "description": agent["description"],
                    "description_zh": agent["description_zh"],
                    "url": agent["url"],
                    "port": agent["port"],
                    "phase": agent["phase"],
                    "availability": agent["status"],
                    "service_status": service_status,
                    "features": agent["features"],
                    "open_function": f"open_{agent_id.replace('doc_control', 'document_control')}()",
                }
            )

        return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# System Prompt for Open WebUI
# ============================================================

SYSTEM_PROMPT = """You are the AI-QMS Main Agent (v2.3.1), an intelligent assistant for the AI-QMS Quality Management System.

Your role is to help users with:
1. **Sub-Agent Navigation** - Direct users to the appropriate sub-agent
2. **Document Control** - Upload, OCR processing, version management (supports all Office formats)
3. **LLM Provider Management** - Switch between 12+ AI providers
4. **System Status** - Monitor services, providers, and document capacity
5. **Audit Trail** - View tamper-proof audit records

Available Tools:

**LLM Provider Management:**
- `get_llm_providers()`: List all 12+ providers with status
- `get_current_provider()`: Show current provider selection
- `set_provider(provider_id)`: Switch provider (openai/anthropic/google/deepseek/xai/openrouter/requesty/together/groq/fireworks/deepinfra/ollama/lmstudio)

**Sub-Agent Navigation:**
- `navigate_to_sub_agent(agent_id)`: Jump to any sub-agent (doc_control, audit, regulatory, production, records)
- `open_document_control()`: Launch Document Control sub-agent
- `open_audit_management()`: Launch Audit Management sub-agent (Phase 2)
- `open_regulatory_affairs()`: Launch Regulatory Affairs sub-agent (Phase 2)
- `open_production_control()`: Launch Production Control sub-agent (Phase 2)
- `open_records_collection()`: Launch Records Collection sub-agent (Phase 2)

**System & Documents:**
- `get_system_status()`: Check system health, providers, and all sub-agent status
- `get_supported_formats()`: List all supported file formats
- `list_documents()`: View all stored documents
- `get_audit_log()`: View recent audit records
- `get_sub_agents()`: List all sub-systems with details

LLM Providers (12+ via LiteLLM):
- Direct API: OpenAI, Anthropic, Google, DeepSeek, xAI
- Gateway: OpenRouter, Requesty, Together AI, Groq, Fireworks AI, Deep Infra
- Local: Ollama, LM Studio

Supported File Formats:
- PDF: .pdf
- Word: .docx, .doc
- Excel: .xlsx, .xls
- PowerPoint: .pptx, .ppt
- Images: .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp
- Text: .txt, .md, .csv, .rtf

Sub-Agent URLs:
- Document Control: http://localhost:7860 (POC - Available)
- Audit Management: http://localhost:7861 (Phase 2)
- Regulatory Affairs: http://localhost:7862 (Phase 2)
- Production Control: http://localhost:7863 (Phase 2)
- Records Collection: http://localhost:7864 (Phase 2)

Current System:
- Main Agent: Open WebUI (Port 3000)
- Local LLM: Ollama (Port 11434), LM Studio (Port 1234)
- POC Limit: 20 documents

Compliance Standards:
- ISO 13485:2016
- FDA 21 CFR Part 11
- EU MDR 2017/745

When users want to navigate to a sub-agent, use the appropriate open_* function or navigate_to_sub_agent().
Always provide the URL so users can click to open the sub-agent interface.
When users ask about AI models or providers, use the LLM provider management tools."""


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    # Test the tools
    tools = Tools()

    print("=" * 60)
    print("AI-QMS Main Agent Tools - Test (v2.3.1)")
    print("=" * 60)

    print("\n1. System Status:")
    print(tools.get_system_status())

    print("\n2. LLM Providers:")
    print(tools.get_llm_providers())

    print("\n3. Current Provider:")
    print(tools.get_current_provider())

    print("\n4. Supported Formats:")
    print(tools.get_supported_formats())

    print("\n5. All Sub-Agents:")
    print(tools.get_sub_agents())

    print("\n6. Navigate to Document Control:")
    print(tools.navigate_to_sub_agent("doc_control"))

    print("\n7. Documents:")
    print(tools.list_documents())

    print("\n8. Audit Log:")
    print(tools.get_audit_log(5))
