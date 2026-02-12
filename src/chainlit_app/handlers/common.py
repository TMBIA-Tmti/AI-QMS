"""
AI-QMS Chainlit - Common Utilities
===================================
Shared helper functions for both Main Agent and Doc Control profiles.
"""

import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm_providers import (
    LLMProviderManager,
    DEFAULT_PROVIDERS,
    create_provider_manager,
    auto_update_models,
    print_update_summary,
    load_cached_models,
    _save_model_cache,
)
from src.storage.markdown_storage import MarkdownStorageManager, POC_DOCUMENT_LIMIT
from src.services.markdown_store_service import (
    MarkdownStoreService,
    get_markdown_store,
)
from src.database.audit_log import ImmutableAuditLog
from src.database.document_store import DocumentStore
from src.utils.audit_export import (
    format_audit_table_markdown,
    export_to_word,
    export_to_excel,
)
from src.ocr.vision_ocr import VisionOCRProcessor, process_document, OCRResult


# ============================================================
# Constants
# ============================================================

UPLOAD_FOLDER = Path("./uploads")

ALLOWED_EXTENSIONS = {
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
}


# ============================================================
# Helper Functions
# ============================================================


def ensure_upload_folder():
    """Ensure upload folder exists"""
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_document_count() -> tuple:
    """Get current document count and limit"""
    try:
        storage = MarkdownStorageManager()
        stats = storage.get_storage_stats()
        return stats.get("total_documents", 0), stats.get("limit", POC_DOCUMENT_LIMIT)
    except Exception:
        return 0, POC_DOCUMENT_LIMIT


def get_provider_choices() -> list:
    """Get list of (display_name, provider_id) tuples"""
    if not DEFAULT_PROVIDERS:
        return [("Ollama (Local)", "ollama")]

    choices = []
    for provider_id, config in DEFAULT_PROVIDERS.items():
        display_name = config.get("display_name", provider_id)
        if config.get("is_local"):
            display_name += " (Local)"
        choices.append((display_name, provider_id))
    return choices


def get_model_choices(provider_id: str) -> list:
    """Get available models for a provider"""
    import requests

    if not DEFAULT_PROVIDERS or provider_id not in DEFAULT_PROVIDERS:
        return ["default"]

    config = DEFAULT_PROVIDERS[provider_id]

    # For Ollama: dynamically fetch installed models
    if provider_id == "ollama":
        try:
            api_base = config.get("api_base_url", "http://localhost:11434")
            response = requests.get(f"{api_base}/api/tags", timeout=3)
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    return models
        except Exception:
            pass

    # For LM Studio: dynamically fetch loaded models
    elif provider_id == "lmstudio":
        try:
            api_base = config.get("api_base_url", "http://localhost:1234/v1")
            response = requests.get(f"{api_base}/models", timeout=3)
            if response.status_code == 200:
                data = response.json()
                models = [m["id"] for m in data.get("data", [])]
                if models:
                    return models
        except Exception:
            pass

    return config.get("available_models", [config.get("default_model", "default")])


def get_provider_id_from_display(display_name: str) -> str:
    """Convert display name to provider ID"""
    if not DEFAULT_PROVIDERS:
        return "ollama"

    for provider_id, config in DEFAULT_PROVIDERS.items():
        display = config.get("display_name", provider_id)
        if config.get("is_local"):
            display += " (Local)"
        if display == display_name:
            return provider_id

    return "ollama"


def setup_api_key(provider_id: str, api_key: str):
    """Set API key in environment for a provider"""
    if api_key and not DEFAULT_PROVIDERS.get(provider_id, {}).get("is_local"):
        env_key = DEFAULT_PROVIDERS.get(provider_id, {}).get("env_key_name", "")
        if env_key:
            os.environ[env_key] = api_key


def test_llm_connection(provider_id: str, model_name: str, api_key: str = "") -> str:
    """Test LLM connection and return status message"""
    try:
        setup_api_key(provider_id, api_key)
        mgr = create_provider_manager(provider_id)
        res = mgr.test_connection(model=model_name if model_name else None)
        if res.get("success"):
            return f"✅ 連線成功！ 提供商: {res['provider']} | 模型: {res['model']} | 延遲: {res['latency_ms']}ms"
        else:
            return f"❌ 連線失敗 模型: {res.get('model', 'N/A')} | 錯誤: {res.get('error', '未知錯誤')}"
    except Exception as e:
        return f"❌ 測試失敗: {str(e)}"
