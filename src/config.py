"""
AI-QMS Phase 1 Document Control - 配置檔
LLM 與系統配置
"""
import os
from typing import Literal

# ============================================================
# LLM Provider 設定
# ============================================================

LLM_PROVIDER: Literal["openai", "ollama", "lmstudio"] = os.getenv("LLM_PROVIDER", "ollama")

# OpenAI 設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Ollama 設定 (本地 LLM)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# LM Studio 設定
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")


# ============================================================
# 資料庫配置
# ============================================================

# ChromaDB (本地向量資料庫)
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")

# Weaviate (生產向量資料庫)
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")

# PostgreSQL
POSTGRES_URL = os.getenv("POSTGRES_URL", "")


# ============================================================
# 檔案上傳配置
# ============================================================

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "png", "jpg", "jpeg", "tiff"}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB


# ============================================================
# 硬體配置 (RTX 5060 Ti 16GB + 32GB RAM)
# ============================================================

HARDWARE_CONFIG = {
    "gpu": "RTX 5060 Ti",
    "vram": "16GB",
    "ram": "32GB",
    "estimated_ocr_speed": "3-5 pages/min",  # olmocr 預估
    "max_concurrent_uploads": 5,
}


# ============================================================
# Phase 2A Deployment Mode
# ============================================================

DEPLOYMENT_MODE: Literal["standalone", "server"] = os.getenv("QMS_MODE", "standalone")
"""
standalone: Single-machine mode (default) — auto-login, asyncio task management
server:     Multi-user server mode — password auth, Celery task queue
"""

# Permission matrix (Server mode)
PERMISSIONS: dict[str, list[str]] = {
    "admin":   ["upload", "delete", "create_capa", "close_capa", "manage_users", "view_all_audits", "export"],
    "auditor": ["upload",           "create_capa", "close_capa",                 "view_all_audits", "export"],
    "editor":  ["upload",                                                                             "export"],
    "viewer":  [],
}


# ============================================================
# Phase 2A SQLite Database
# ============================================================

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/qms.db")


# ============================================================
# Phase 2A LightRAG
# ============================================================

LIGHTRAG_WORKING_DIR = os.getenv("LIGHTRAG_WORKING_DIR", "./data/lightrag")


# ============================================================
# Phase 2A Docling Settings（Tier 3 最後手段）
# ============================================================

import multiprocessing as _mp

DOCLING_ENABLED: bool = os.getenv("DOCLING_ENABLED", "true").lower() == "true"

# Half of CPU cores to avoid blocking the system
DOCLING_NUM_THREADS: int = int(
    os.getenv("DOCLING_NUM_THREADS", str(max(1, _mp.cpu_count() // 2)))
)

# "fast" = TableFormerMode.FAST (CPU optimized), "accurate" = TableFormerMode.ACCURATE
DOCLING_TABLE_MODE: str = os.getenv("DOCLING_TABLE_MODE", "fast")

# Documents smaller than this use MarkItDown (milliseconds); larger use Docling (high quality)
DOCLING_SIZE_THRESHOLD_BYTES: int = int(
    os.getenv("DOCLING_SIZE_THRESHOLD_BYTES", str(100 * 1024))  # Default 100KB
)


# ============================================================
# GPU / CPU 模式
# ============================================================

# 強制所有 ML 引擎使用 CPU（適用於：CUDA 不匹配、Blackwell 新 GPU、記憶體不足）
# 設定方式：python scripts/setup_models.py --cpu  → 自動寫入此值
FORCE_CPU: bool = os.getenv("FORCE_CPU", "false").lower() == "true"


# ============================================================
# OCR 引擎設定
# ============================================================

# EasyOCR（Tier 1）
EASYOCR_ENABLED: bool = os.getenv("EASYOCR_ENABLED", "true").lower() == "true"

# EasyOCR 語系分組（用於 setup_models.py 預下載）
# 注意：CJK 語言不能混合在同一個 Reader，各自與 English 配對
EASYOCR_LANGUAGE_GROUPS: list[list[str]] = [
    ["ch_tra", "en"],   # 繁體中文（台灣/香港）
    ["ch_sim", "en"],   # 簡體中文（中國/新加坡）
    ["ja", "en"],       # 日文
    ["ko", "en"],       # 韓文
    ["en", "de", "fr", "it", "es", "pt", "nl", "pl", "vi", "id", "ms", "cs", "tr"],  # 拉丁系
    ["ar", "en"],       # 阿拉伯文
    ["hi", "en"],       # 天城文（印地文）
    ["th", "en"],       # 泰文
    ["ru", "en"],       # 西里爾（俄文）
]

# 國家代碼 → EasyOCR 語系清單
# 調度引擎根據文件來源國選擇最適合的語系
COUNTRY_TO_EASYOCR_LANGS: dict[str, list[str]] = {
    # CJK
    "tw": ["ch_tra", "en"],
    "cn": ["ch_sim", "en"],
    "hk": ["ch_tra", "en"],
    "mo": ["ch_tra", "en"],
    "jp": ["ja", "en"],
    "kr": ["ko", "en"],
    "sg": ["ch_sim", "en"],
    # 特殊文字
    "in": ["hi", "en"],
    "sa": ["ar", "en"],
    "ae": ["ar", "en"],
    "eg": ["ar", "en"],
    "th": ["th", "en"],
    "ru": ["ru", "en"],
    # 拉丁系
    "us": ["en"],
    "gb": ["en"],
    "uk": ["en"],
    "au": ["en"],
    "ca": ["fr", "en"],
    "de": ["de", "en"],
    "fr": ["fr", "en"],
    "it": ["it", "en"],
    "es": ["es", "en"],
    "pt": ["pt", "en"],
    "br": ["pt", "en"],
    "nl": ["nl", "en"],
    "be": ["fr", "nl", "en"],
    "ch": ["de", "fr", "it", "en"],
    "at": ["de", "en"],
    "pl": ["pl", "en"],
    "cz": ["cs", "en"],
    "se": ["en"],
    "dk": ["en"],
    "no": ["en"],
    "tr": ["tr", "en"],
    "vn": ["vi", "en"],
    "id": ["id", "en"],
    "my": ["ms", "en"],
    "mx": ["es", "en"],
    "co": ["es", "en"],
}
