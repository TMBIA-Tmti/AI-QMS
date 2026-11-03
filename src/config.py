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

# Single source of truth for allowed upload extensions (no leading dot —
# consumed by legacy src/app.py's `allowed_file()`). Mirrors what the OCR
# pipeline can actually process (see src/ocr/vision_ocr.SUPPORTED_EXTENSIONS).
# src/chainlit_app/handlers/common.py derives its dotted-extension set from
# this list — update this list only, do not maintain a separate one there.
ALLOWED_EXTENSIONS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "tiff",
    "tif",
    "bmp",
    "docx",
    "doc",
    "xlsx",
    "xls",
    "pptx",
    "ppt",
    "txt",
    "md",
    "csv",
    "rtf",
}
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
# 稽核紀錄鏈簽章金鑰 (21 CFR Part 11 防竄改)
# ============================================================

# HMAC-SHA256 簽章金鑰。生產環境務必以環境變數提供，切勿寫入版控檔案。
# 未設定時，系統會在 AUDIT_LOG_KEY_FILE 自動產生隨機金鑰（僅適用於單機測試）。
AUDIT_LOG_HMAC_KEY = os.getenv("AUDIT_LOG_HMAC_KEY", "")

# 自動產生金鑰的存放位置（預設 data/，已列入 .gitignore，且與被保護的
# audit_log.json 分開存放）
AUDIT_LOG_KEY_FILE = os.getenv("AUDIT_LOG_KEY_FILE", "./data/.audit_key")

# ============================================================
# 登入驗證開關（2026-09-04：自動判斷 — 尚未建立帳號前預設開放使用）
# ============================================================
#
# 判斷順序：
#   1. 環境變數 QMS_AUTH_ENABLED 明確設為 true/false 時，一律以它為準
#      （強制開啟或強制關閉，忽略帳號庫狀態）。
#   2. 未設定環境變數時，改為自動判斷：帳號庫（data/auth/users.json）裡
#      「目前有沒有至少一個帳號」——沒有帳號就代表沒人能登入，此時保持開放
#      使用（不顯示登入頁面）；一旦用 scripts/create_qms_user.py 建立了第一
#      個帳號，*下次啟動*就會自動要求登入，不需要手動改設定或設環境變數。
#
# 注意：Chainlit 是否顯示登入頁面，是應用程式啟動當下就決定好、不會在執行
# 期間動態切換的——也就是說「建立帳號後自動上鎖」指的是「下一次重新啟動」，
# 不是同一個執行中的程序會立刻變成需要登入。
#
# src/chainlit_app/app.py 的 password_auth_callback、src/analysis/
# report_api.py 的 _resolve_authenticated_user 都會讀這個值：關閉時報告頁面
# 的寫入端點（override／add_note／restore／evidence 相關／rerun／pause／
# resume）會以固定的 "anonymous" 身分寫入稽核紀錄，功能照常可用，只是無法
# 歸屬到真實驗證過的身分。


def _auth_effectively_enabled() -> bool:
    _forced = os.getenv("QMS_AUTH_ENABLED", "").strip().lower()
    if _forced in ("true", "1", "yes"):
        return True
    if _forced in ("false", "0", "no"):
        return False
    try:
        from src.utils.auth_store import load_users

        return bool(load_users())
    except Exception:
        # 帳號庫讀取失敗（例如檔案損毀）時，保守起見視為「尚無帳號」，
        # 不因為讀取失敗而意外把整個系統鎖死。
        return False


AUTH_ENABLED = _auth_effectively_enabled()


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
