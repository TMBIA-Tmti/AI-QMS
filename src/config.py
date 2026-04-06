"""
AI-QMS Phase 1 Document Control - 配置檔
LLM 與系統配置
"""
import os
from typing import Literal
from dataclasses import dataclass

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
# Major Agent LLM 配置
# ============================================================

@dataclass
class MajorAgentConfig:
    """主 Agent (文件控制中央協調器) 配置"""
    model: str = "qwen2.5:32b"           # Ollama 模型
    openai_model: str = "gpt-4o-mini"    # OpenAI 備援
    temperature: float = 0.1
    max_tokens: int = 4096
    
    system_prompt: str = """你是 AI-QMS 文件控制系統的中央協調 Agent。
你的職責：
1. 解析使用者上傳的文件
2. 判斷文件類型（初次輸入或進版）
3. 協調各子 Agent 執行任務
4. 確保所有操作符合 ISO 13485:2016 要求

你必須嚴格遵循流程，不可跳過任何步驟。"""


# ============================================================
# Sub-Agent LLM 配置矩陣
# ============================================================

@dataclass
class SubAgentConfig:
    """子 Agent 配置"""
    name: str
    model: str
    openai_model: str
    temperature: float
    max_tokens: int
    system_prompt: str


# 文件輸入判斷 Sub-Agent
INPUT_DETECTION_AGENT = SubAgentConfig(
    name="input_detection",
    model="qwen2.5:7b",
    openai_model="gpt-4o-mini",
    temperature=0.0,
    max_tokens=2048,
    system_prompt="""你是文件類型判斷專家。
分析上傳的文件，判斷是：
1. 初次輸入 (新文件，設為母版)
2. 文件進版 (更新現有文件)

輸出 JSON 格式：
{"is_new_document": true/false, "confidence": 0.0-1.0, "reason": "判斷理由"}"""
)

# 版本控制 Sub-Agent
VERSION_CONTROL_AGENT = SubAgentConfig(
    name="version_control",
    model="qwen2.5:7b",
    openai_model="gpt-4o-mini",
    temperature=0.0,
    max_tokens=2048,
    system_prompt="""你是文件版本控制專家。
職責：
1. 檢查進版程序是否完成（DCR、影響分析、簽章）
2. 管理版本號遞增規則
3. 生成版本變更紀錄

輸出 JSON 格式：
{"version_valid": true/false, "missing_steps": [], "new_version": "v1.0"}"""
)

# OCR 後處理 Sub-Agent
OCR_POSTPROCESS_AGENT = SubAgentConfig(
    name="ocr_postprocess",
    model="qwen2.5-vl:7b",
    openai_model="gpt-4o",
    temperature=0.1,
    max_tokens=4096,
    system_prompt="""你是 OCR 後處理專家。
分析 OCR 輸出的文字內容，識別：
1. 印章區域與內容
2. 手寫簽名區域
3. 文件結構（標題、日期、編號）

輸出 JSON 格式。"""
)

# 法規識別 Sub-Agent
REGULATION_AGENT = SubAgentConfig(
    name="regulation",
    model="qwen2.5:14b",
    openai_model="gpt-4o",
    temperature=0.1,
    max_tokens=4096,
    system_prompt="""你是醫療器材法規專家。
從文件中識別所有法規引用：
- ISO 標準 (ISO 13485, ISO 14971 等)
- FDA 法規 (21 CFR Part 820 等)
- IEC 標準
- EU MDR
- TFDA 台灣法規

輸出法規清單並確認是否為最新版本。"""
)

# 關聯文件更新 Sub-Agent
RELATION_UPDATE_AGENT = SubAgentConfig(
    name="relation_update",
    model="qwen2.5:7b",
    openai_model="gpt-4o-mini",
    temperature=0.0,
    max_tokens=2048,
    system_prompt="""你是文件關聯分析專家。
當文件進版時，搜尋所有引用舊版次的其他文件。
輸出需進版的文件清單。"""
)

# Markdown 轉換 Sub-Agent
MARKDOWN_AGENT = SubAgentConfig(
    name="markdown",
    model="qwen2.5:7b",
    openai_model="gpt-4o-mini",
    temperature=0.0,
    max_tokens=8192,
    system_prompt="""你是文件格式轉換專家。
將 OCR 輸出的文字轉換為結構化的 Markdown 格式。
保留所有重要資訊：標題、表格、列表、段落。"""
)


# ============================================================
# 所有 Sub-Agent 配置清單
# ============================================================

SUB_AGENTS = {
    "input_detection": INPUT_DETECTION_AGENT,
    "version_control": VERSION_CONTROL_AGENT,
    "ocr_postprocess": OCR_POSTPROCESS_AGENT,
    "regulation": REGULATION_AGENT,
    "relation_update": RELATION_UPDATE_AGENT,
    "markdown": MARKDOWN_AGENT,
}


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
# Phase 2A Docling Settings
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
