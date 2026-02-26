"""
AI-QMS Phase 1 - Chainlit Application
======================================

Version: v3.4.0
Updated: 2026-02-25

Single Chainlit app with Chat Profiles:
  - Main Agent: System navigation, document listing, obsolete, audit, LLM chat
  - Doc Control: File upload, OCR, version detection, stamp confirmation

Replaces: src/gradio_apps/main_agent.py + src/gradio_apps/doc_control.py
Port: 3000 (single app)
"""

import os
import sys
import re
import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

# Web Search (ddgs >= 8.0 or legacy duckduckgo-search)
try:
    from ddgs import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS

        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        print("[WARN] ddgs not installed. Run: pip install ddgs")

import chainlit as cl
from chainlit.input_widget import Select, TextInput, Switch

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.chainlit_app.handlers.common import (
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    ensure_upload_folder,
    calculate_file_hash,
    get_document_count,
    get_provider_choices,
    get_model_choices,
    get_provider_id_from_display,
    setup_api_key,
    test_llm_connection,
)
from src.llm_providers import (
    LLMProviderManager,
    DEFAULT_PROVIDERS,
    create_provider_manager,
    auto_update_models,
    print_update_summary,
    load_cached_models,
    _save_model_cache,
)
from src.storage.markdown_storage import POC_DOCUMENT_LIMIT  # noqa: F401 (re-exported)
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
from src.utils.regulatory_export import (
    format_regulatory_table_markdown,
    export_regulatory_to_word,
    export_regulatory_to_excel,
    format_reference_table_markdown,
    export_reference_to_word,
    export_reference_to_excel,
)
from src.utils.doclist_export import (
    export_doclist_to_word,
    export_doclist_to_excel,
    export_allrecords_to_word,
    export_allrecords_to_excel,
)
from src.ocr.vision_ocr import VisionOCRProcessor, process_document

# v3.1.0: Load cached model lists from previous sessions on startup.
# This ensures cloud provider models appear immediately without
# needing to re-enter API keys.
load_cached_models()


# ============================================================
# Arize Phoenix - LLM Observability (v3.4.0)
# ============================================================
# Auto-instruments all LiteLLM completion() calls with OpenTelemetry.
# Traces are sent to a local Phoenix server (http://localhost:6006).
# If Phoenix is not running, the app works normally without tracing.

PHOENIX_ENABLED = False

try:
    from phoenix.otel import register as phoenix_register
    from openinference.instrumentation.litellm import LiteLLMInstrumentor

    _phoenix_endpoint = os.getenv(
        "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"
    )
    _phoenix_project = os.getenv("PHOENIX_PROJECT_NAME", "ai-qms-doc-control")

    _phoenix_tracer_provider = phoenix_register(
        project_name=_phoenix_project,
        endpoint=_phoenix_endpoint,
    )
    LiteLLMInstrumentor().instrument(tracer_provider=_phoenix_tracer_provider)

    PHOENIX_ENABLED = True
    print(
        f"[OK] Phoenix tracing enabled → {_phoenix_endpoint} (project: {_phoenix_project})"
    )
except ImportError:
    # Auto-install Phoenix packages for users who upgraded via git pull
    print("[INFO] Phoenix packages not found. Auto-installing...")
    try:
        import subprocess, sys

        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "arize-phoenix>=9.0.0",
                "arize-phoenix-otel>=0.8.0",
                "openinference-instrumentation-litellm>=0.1.18",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Retry after install
        from phoenix.otel import register as phoenix_register
        from openinference.instrumentation.litellm import LiteLLMInstrumentor

        _phoenix_endpoint = os.getenv(
            "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"
        )
        _phoenix_project = os.getenv("PHOENIX_PROJECT_NAME", "ai-qms-doc-control")
        _phoenix_tracer_provider = phoenix_register(
            project_name=_phoenix_project, endpoint=_phoenix_endpoint
        )
        LiteLLMInstrumentor().instrument(tracer_provider=_phoenix_tracer_provider)
        PHOENIX_ENABLED = True
        print(
            f"[OK] Phoenix auto-installed and enabled → {_phoenix_endpoint} (project: {_phoenix_project})"
        )
    except Exception as auto_err:
        print(f"[INFO] Phoenix auto-install failed ({auto_err}). LLM tracing disabled.")
except Exception as e:
    print(
        f"[WARN] Phoenix tracing init failed: {e}. App will continue without tracing."
    )

# ============================================================
# Internationalization (i18n) - v3.2.0 (20 languages)
# ============================================================

try:
    from src.chainlit_app.i18n import (
        SUPPORTED_LANGUAGES,
        LANG_CODE_MAP,
        I18N,
        COMMANDS,
        get_all_command_keywords,
    )
except ImportError:
    from i18n import (
        SUPPORTED_LANGUAGES,
        LANG_CODE_MAP,
        I18N,
        COMMANDS,
        get_all_command_keywords,
    )


def t(key: str, lang: str = None, **kwargs) -> str:
    """Get translated string for the current session language.

    Falls back to zh-TW if key not found in the selected language.
    Supports {placeholder} formatting via kwargs.
    """
    if lang is None:
        try:
            lang = cl.user_session.get("language", "zh-TW")
        except Exception:
            lang = "zh-TW"
    translations = I18N.get(lang, I18N["zh-TW"])
    text = translations.get(key, I18N["zh-TW"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def _match_cmd(text: str, cmd_key: str) -> bool:
    """Check if text matches any keyword for the given command across all languages."""
    all_kw = get_all_command_keywords(cmd_key)
    text_lower = text.lower() if text else ""
    for kw in all_kw:
        if kw in text_lower:
            return True
    return False


def _match_cmd_exact(text: str, cmd_key: str) -> bool:
    """Check if text exactly equals any keyword for the given command (case-insensitive)."""
    all_kw = get_all_command_keywords(cmd_key)
    text_lower = text.lower().strip() if text else ""
    return text_lower in all_kw


def _match_cmd_startswith(text: str, cmd_key: str) -> bool:
    """Check if text starts with any keyword for the given command."""
    all_kw = get_all_command_keywords(cmd_key)
    text_lower = text.lower() if text else ""
    for kw in all_kw:
        if text_lower.startswith(kw):
            return True
    return False


def _extract_after_cmd(text: str, cmd_key: str) -> str:
    """Extract the text after the matched command keyword."""
    all_kw = get_all_command_keywords(cmd_key)
    text_lower = text.lower() if text else ""
    for kw in sorted(all_kw, key=len, reverse=True):
        if kw in text_lower:
            idx = text_lower.index(kw) + len(kw)
            return text[idx:].strip()
    return text.strip()


def get_system_prompt(profile: str, lang: str = None) -> str:
    """Get system prompt based on profile and language."""
    if lang is None:
        try:
            lang = cl.user_session.get("language", "zh-TW")
        except Exception:
            lang = "zh-TW"

    if lang == "zh-TW":
        if profile == "文件管制 (Doc Control)":
            return """你是 AI-QMS 文件管制子系統的 AI 助理 (v3.3.0)。

你的職責是協助使用者進行文件管制操作：
1. 文件上傳與 OCR 處理（自動存入 Markdown DB）
2. 文件類型判斷（初次輸入/進版）
3. 簽章確認流程
4. 文件搜尋與下載

可用指令：
- 「幫助」- 顯示使用指南
- 「文件清單」- 現行正式版本文件
- 「列表」- 所有文件紀錄（含進版、作廢）
- 「搜尋 關鍵字」- 搜尋文件
- 「作廢 文件編號」- 作廢文件
- 「下載 文件編號」- 下載原始文件
- 「文件更動紀錄」- 查看文件更動紀錄
- 「下載文件更動紀錄 word/excel」- 匯出文件更動紀錄
- 「法規清單」- 列出所有文件引用的法規標準
- 「下載法規清單 word/excel」- 匯出法規清單
- 「下載引用清單 word/excel」- 匯出文件進版後的引用清單
- 「/web 關鍵字」- 搜尋網路（如：/web 最新 ISO 13485 版本）
- 「狀態」- 系統狀態
- 「刪除資料庫」- 刪除所有文件（需確認）

上傳文件：直接在對話框拖放或上傳文件即可開始 OCR 處理。

請根據文件資料庫內容回答問題。使用者可用 /web 指令搜尋網路取得最新資訊。如果資料庫中沒有相關資訊，請明確告知，不要編造答案。"""
        else:
            return """你是 AI-QMS 品質管理系統的主要 AI 助理 (v3.3.0)。

你的職責是協助使用者進行：
1. **文件管制** - 文件上傳、MarkItDown 轉換、版本控制（支援所有 Office 格式）
2. **LLM 提供商管理** - 切換 16+ AI 提供商
3. **系統狀態** - 監控服務、提供商和文件容量
4. **文件更動紀錄** - 查看防篡改文件更動紀錄

可用指令：
- 「幫助」或「help」- 顯示使用指南
- 「文件清單」- 現行正式版本文件
- 「列表」或「list」- 所有文件紀錄（含進版、作廢）
- 「搜尋 關鍵字」- 搜尋文件內容
- 「作廢 文件編號」- 作廢文件
- 「文件更動紀錄」- 查看文件更動紀錄
- 「下載文件更動紀錄 word/excel」- 匯出文件更動紀錄
- 「法規清單」- 列出所有文件引用的法規標準
- 「下載法規清單 word/excel」- 匯出法規清單
- 「/web 關鍵字」- 搜尋網路取得最新資訊（如：/web 最新 ISO 13485）
- 「狀態」或「status」- 系統狀態

重要：回覆中絕對不要顯示任何 URL 或網址。
請根據文件資料庫內容回答問題。使用者可用 /web 指令搜尋網路取得最新資訊。如果資料庫中沒有相關資訊，請明確告知，不要編造答案。"""

    elif lang == "ja-JP":
        if profile == "文件管制 (Doc Control)":
            return """あなたは AI-QMS 文書管理サブシステムの AI アシスタントです (v3.3.0)。

あなたの責務：
1. 文書アップロードと OCR 処理（Markdown DB に自動保存）
2. 文書タイプ判定（新規/版更新）
3. 印鑑確認ワークフロー
4. 文書検索とダウンロード

利用可能なコマンド：
- 「ヘルプ」- 使用ガイドを表示
- 「文書一覧」- 現行正式版文書
- 「リスト」- 全記録（版更新・廃止含む）
- 「検索 キーワード」- 文書を検索
- 「廃止 文書ID」- 文書を廃止
- 「ダウンロード 文書ID」- 原本ファイルをダウンロード
- 「監査証跡」- 監査記録を表示
- 「監査証跡ダウンロード word/excel」- 監査記録をエクスポート
- 「規制リスト」- 引用規格一覧
- 「規制リストダウンロード word/excel」- 規格をエクスポート
- 「/web キーワード」- ウェブ検索（例：/web 最新 ISO 13485 バージョン）
- 「ステータス」- システム状態
- 「データベース削除」- 全文書を削除（確認必要）

ファイルアップロード：チャットにファイルをドラッグ＆ドロップまたはアップロードして OCR 処理を開始。

文書データベースの内容に基づいて質問に回答してください。ユーザーは /web コマンドでウェブ検索ができます。関連情報がない場合は明確にその旨を伝え、回答を捏造しないでください。"""
        else:
            return """あなたは AI-QMS 品質管理システムのメイン AI アシスタントです (v3.3.0)。

あなたの責務：
1. **文書管理** - 文書アップロード、MarkItDown 変換、版管理（全 Office 形式対応）
2. **LLM プロバイダー管理** - 16以上の AI プロバイダーの切替
3. **システム状態** - サービス、プロバイダー、文書容量の監視
4. **監査証跡** - 改ざん防止の監査記録の閲覧

利用可能なコマンド：
- 「ヘルプ」- 使用ガイドを表示
- 「文書一覧」- 現行正式版文書
- 「リスト」- 全記録（版更新・廃止含む）
- 「検索 キーワード」- 文書内容を検索
- 「廃止 文書ID」- 文書を廃止
- 「監査証跡」- 監査記録を表示
- 「監査証跡ダウンロード word/excel」- 監査記録をエクスポート
- 「規制リスト」- 引用規格一覧
- 「規制リストダウンロード word/excel」- 規格をエクスポート
- 「/web キーワード」- ウェブ検索で最新情報を取得（例：/web 最新 ISO 13485）
- 「ステータス」- システム状態

重要：回答に URL やウェブアドレスを表示しないでください。
文書データベースの内容に基づいて質問に回答してください。ユーザーは /web コマンドでウェブ検索ができます。関連情報がない場合は明確にその旨を伝え、回答を捏造しないでください。"""

    else:  # en-US (default for all other languages)
        if profile == "文件管制 (Doc Control)":
            return """You are the AI assistant for the AI-QMS Document Control Sub-System (v3.3.0).

Your responsibilities include:
1. Document upload and OCR processing (auto-save to Markdown DB)
2. Document type detection (new/version update)
3. Stamp confirmation workflow
4. Document search and download

Available commands:
- "help" - Show usage guide
- "document list" - Current formal versions
- "list" - All records (incl. versions, obsolete)
- "search keyword" - Search documents
- "obsolete doc_id" - Obsolete a document
- "download doc_id" - Download original file
- "audit trail" - View audit records
- "download audit word/excel" - Export audit records
- "regulatory list" - List referenced standards
- "download regulatory word/excel" - Export standards
- "download reference word/excel" - Export version reference list
- "/web keyword" - Search the web (e.g., /web latest ISO 13485 version)
- "status" - System status
- "delete database" - Delete all documents (confirm required)

Upload files: Drag & drop or upload files in the chat to start OCR processing.

Answer questions based on document database content. Users can use the /web command to search the web for the latest information. If no relevant information is found, clearly state so. Do not fabricate answers."""
        else:
            return """You are the main AI assistant for the AI-QMS Quality Management System (v3.3.0).

Your responsibilities include:
1. **Document Control** - Document upload, MarkItDown conversion, version control (all Office formats)
2. **LLM Provider Management** - Switch between 16+ AI providers
3. **System Status** - Monitor services, providers, and document capacity
4. **Audit Trail** - View tamper-proof audit records

Available commands:
- "help" - Show usage guide
- "document list" - Current formal versions
- "list" - All records (incl. versions, obsolete)
- "search keyword" - Search document content
- "obsolete doc_id" - Obsolete a document
- "audit trail" - View audit records
- "download audit word/excel" - Export audit records
- "regulatory list" - List referenced standards
- "download regulatory word/excel" - Export standards
- "/web keyword" - Search the web for latest information (e.g., /web latest ISO 13485)
- "status" - System status

Important: Never display any URLs in your responses.
Answer questions based on document database content. Users can use the /web command to search the web for the latest information. If no relevant information is found, clearly state so. Do not fabricate answers."""


# ============================================================
# Signature Keywords (from doc_control.py)
# ============================================================

SIGNATURE_KEYWORDS = [
    # English
    "signature",
    "signed",
    "sign:",
    "sign here",
    "approved by",
    "reviewed by",
    "authorized by",
    "prepared by",
    "checked by",
    "verified by",
    "confirmed by",
    "endorsed by",
    "accepted by",
    "released by",
    "stamp",
    "seal",
    "chop",
    "company seal",
    "official seal",
    "digitally signed",
    "electronic signature",
    "e-signature",
    # 繁體中文
    "簽名",
    "簽署",
    "簽字",
    "親簽",
    "手簽",
    "簽章",
    "蓋章",
    "用印",
    "鈐印",
    "印章",
    "公司章",
    "負責人章",
    "法人章",
    "職章",
    "圖章",
    "戳章",
    "騎縫章",
    "核准",
    "審核",
    "核准人",
    "審核人",
    "批准",
    "審批",
    "核定",
    "會簽",
    "擬定",
    "制定",
    "審查",
    "承認",
    "確認人",
    "覆核",
    "複核",
    "電子簽章",
    "數位簽章",
    "電子簽名",
    # 簡體中文
    "签名",
    "签章",
    "盖章",
    "审核",
    "批准人",
    "审批",
    # 日本語
    "署名",
    "捺印",
    "押印",
    "印鑑",
    "実印",
    "認印",
    "社印",
    "角印",
    "丸印",
    "代表者印",
    "承認",
    "承認者",
    "確認者",
    "検認",
    "決裁",
    "決裁者",
    "起案",
    "起案者",
    "合議",
    "電子署名",
    "電子印鑑",
    "タイムスタンプ",
    # 한국어
    "서명",
    "날인",
    "도장",
    "인감",
    "직인",
    "사인",
    "관인",
    "법인인감",
    "승인",
    "승인자",
    "검토",
    "검토자",
    "확인",
    "결재",
    "기안",
    "기안자",
    "합의",
    "전자서명",
    "전자도장",
    # Deutsch
    "unterschrift",
    "unterzeichnet",
    "genehmigt",
    "genehmigt von",
    "geprüft",
    "geprüft von",
    "freigegeben",
    "freigegeben von",
    "erstellt von",
    "stempel",
    "dienstsiegel",
    "firmenstempel",
    "elektronische unterschrift",
    "digitale signatur",
    # Français
    "signé",
    "signé par",
    "approuvé",
    "approuvé par",
    "vérifié par",
    "validé par",
    "rédigé par",
    "tampon",
    "cachet",
    "sceau",
    "visa",
    "signature électronique",
    "signature numérique",
    # Español
    "firma",
    "firmado",
    "firmado por",
    "aprobado",
    "aprobado por",
    "revisado por",
    "verificado por",
    "elaborado por",
    "sello",
    "timbre",
    "cuño",
    "firma electrónica",
    "firma digital",
    # Português
    "assinatura",
    "assinado",
    "assinado por",
    "aprovado",
    "aprovado por",
    "verificado por",
    "elaborado por",
    "carimbo",
    "selo",
    "chancela",
    "assinatura eletrônica",
    "assinatura digital",
    # Italiano
    "timbro",
    "sigillo",
    "firmato",
    "firmato da",
    "approvato",
    "approvato da",
    "verificato da",
    "firma digitale",
    "firma elettronica",
    # Nederlands
    "handtekening",
    "ondertekend",
    "ondertekend door",
    "goedgekeurd",
    "goedgekeurd door",
    "gecontroleerd door",
    "elektronische handtekening",
    # Русский
    "подпись",
    "подписано",
    "утверждено",
    "утверждено:",
    "проверено",
    "проверено:",
    "печать",
    "штамп",
    "гербовая печать",
    "электронная подпись",
    # العربية
    "توقيع",
    "موقع",
    "ختم",
    "طابع",
    "موافقة",
    "معتمد",
    "مراجعة",
    "توقيع إلكتروني",
    # ภาษาไทย
    "ลายเซ็น",
    "ลงนาม",
    "ตราประทับ",
    "ตรายาง",
    "อนุมัติ",
    "อนุมัติโดย",
    "ตรวจสอบโดย",
    "ลายเซ็นอิเล็กทรอนิกส์",
    # Tiếng Việt
    "chữ ký",
    "ký tên",
    "con dấu",
    "đóng dấu",
    "phê duyệt",
    "phê duyệt bởi",
    "xác nhận",
    "chữ ký số",
    "chữ ký điện tử",
    # Bahasa
    "tandatangan",
    "ditandatangani",
    "cap",
    "meterai",
    "mohor",
    "stempel",
    "diluluskan",
    "disetujui",
    "disahkan",
    "diperiksa oleh",
    "tanda tangan elektronik",
    # Türkçe
    "imza",
    "imzalı",
    "mühür",
    "kaşe",
    "onay",
    "onaylayan",
    "kontrol eden",
    "elektronik imza",
    # हिन्दी
    "हस्ताक्षर",
    "मुहर",
    "छाप",
    "अनुमोदित",
    "सत्यापित",
    "डिजिटल हस्ताक्षर",
    # Vision LLM OCR markers
    "stamps_detected",
    "signatures_detected",
    "[印章]",
    "[簽名]",
    "[stamp]",
    "[seal]",
]


# ============================================================
# Document Type Detection (from doc_control.py)
# ============================================================


def detect_document_type(filename: str, ocr_text: str = "") -> dict:
    """Detect document type from filename and OCR content.

    doc_id is always extracted from the filename prefix (e.g. QM-001, QP-423,
    WI-751-01, FM-423-01).  doc_type is inferred from the prefix or keywords
    in the filename and is used only for storage subfolder classification.
    """
    name = filename.upper()

    # --- Extract document ID first (needed for prefix-based type detection) ---
    doc_id_pattern = r"([A-Z]{2,4}[-_]?\d{2,4}(?:[-_]\d{1,2})?)"
    matches = re.findall(doc_id_pattern, name)
    doc_id = matches[0].replace("_", "-") if matches else name[:20]

    # --- Detect doc_type from prefix, then fall back to keywords ---
    prefix = doc_id.split("-")[0] if "-" in doc_id else ""

    # Prefix-based mapping (highest priority)
    PREFIX_TYPE_MAP = {
        "QP": "SOP",  # Quality Procedure → SOP
        "SOP": "SOP",
        "QM": "SOP",  # Quality Manual → SOP (Level 1 document)
        "WI": "WI",  # Work Instruction
        "FM": "FORM",  # Form
        "FORM": "FORM",
        "DHF": "DHF",  # Design History File
    }
    doc_type = PREFIX_TYPE_MAP.get(prefix, "")

    # Keyword fallback if prefix didn't match
    if not doc_type:
        if "SOP" in name or "PROCEDURE" in name or "MANUAL" in name:
            doc_type = "SOP"
        elif "WI" in name or "WORK" in name or "INSTRUCTION" in name:
            doc_type = "WI"
        elif "FM" in name or "FORM" in name or "TEMPLATE" in name:
            doc_type = "FORM"
        elif "DHF" in name or "DESIGN" in name:
            doc_type = "DHF"
        else:
            doc_type = "OTHER"

    # --- Extract human-readable title from filename ---
    # "QM-001 ISO 13485 Quality Manual.pdf" → "ISO 13485 Quality Manual"
    stem = Path(filename).stem  # remove extension
    # Remove the doc_id prefix (and optional timestamp prefix from uploads)
    title_from_filename = re.sub(
        r"^\d{14}_", "", stem
    )  # strip "20260212111639_" timestamp
    title_from_filename = (
        re.sub(
            r"^[A-Za-z]{2,4}[-_]?\d{2,4}(?:[-_]\d{1,2})?\s*", "", title_from_filename
        )
        .strip()
        .lstrip("_")
    )
    if not title_from_filename:
        title_from_filename = stem

    # Detect version from filename
    version_pattern = r"[vV]?(\d+[._]\d+)"
    version_matches = re.findall(version_pattern, name)
    detected_version = version_matches[0].replace("_", ".") if version_matches else None

    # Scan OCR content for version
    if ocr_text:
        import sys

        # --- Strategy 1: Same-line patterns (label + value on one line) ---
        ocr_version_patterns = [
            # Dotted versions: 1.0, 2.1, etc.
            r"[Vv]ersion\s*[:：]?\s*(\d+(?:\.\d+)+)",
            r"[Rr]ev(?:ision)?\.?\s*[:：]?\s*(\d+(?:\.\d+)+)",
            r"版本\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",
            r"版次\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",
            r"修訂版\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",
            r"[Dd]ocument\s+[Vv]ersion\s*[:：]?\s*(\d+(?:\.\d+)+)",
            r"[Rr]elease\s*[:：]?\s*(\d+(?:\.\d+)+)",
            # Simple V1/V2/V3 patterns (no dots) — works when on same line
            r"[Rr]ev(?:ision)?\.?\s*[:：]?\s*[Vv](\d+)\b",
            r"[Vv]ersion\s*[:：]?\s*[Vv](\d+)\b",
            r"版本\s*[:：]?\s*[Vv](\d+)\b",
            r"\b[Rr]ev\.\s*[Vv](\d+)\b",
        ]
        for pat in ocr_version_patterns:
            ocr_ver_matches = re.findall(pat, ocr_text)
            if ocr_ver_matches:
                try:
                    ver = max(ocr_ver_matches, key=lambda x: float(x))
                except (ValueError, TypeError):
                    ver = ocr_ver_matches[-1]
                detected_version = ver
                break

        # --- Strategy 2: Cross-line detection for MarkItDown PDF tables ---
        # MarkItDown extracts PDF tables as separate lines:
        #   Line N:   "Revision:"
        #   Line N+k: "V2"  (value appears several lines after label)
        # If strategy 1 only found version from Rev. history (not header),
        # or found nothing, try scanning lines near "Revision:" for Vn.
        if not detected_version or detected_version:
            lines = ocr_text.split("\n")
            revision_line_idx = None
            for i, line in enumerate(lines):
                stripped = line.strip().lower()
                if stripped in ("revision:", "revision：", "rev:", "rev."):
                    revision_line_idx = i
                    break
            if revision_line_idx is not None:
                # Scan the next 10 lines for standalone V\d+ pattern
                header_versions = []
                for j in range(
                    revision_line_idx + 1,
                    min(revision_line_idx + 11, len(lines)),
                ):
                    m = re.match(r"^\s*[Vv](\d+(?:\.\d+)*)\s*$", lines[j])
                    if m:
                        header_versions.append(m.group(1))
                if header_versions:
                    try:
                        header_ver = max(header_versions, key=lambda x: float(x))
                    except (ValueError, TypeError):
                        header_ver = header_versions[0]
                    detected_version = header_ver

    # Check if document exists
    storage = get_markdown_store()
    is_new = not storage.document_exists(doc_id)

    confidence = 0.7
    if doc_type != "OTHER":
        confidence += 0.1
    if detected_version:
        confidence += 0.1
    if matches:
        confidence += 0.1

    return {
        "is_new": is_new,
        "doc_id": doc_id,
        "doc_type": doc_type,
        "title": title_from_filename,
        "confidence": min(confidence, 0.99),
        "detected_version": detected_version,
        "existing_version": None
        if is_new
        else storage.get_document(doc_id).get("metadata", {}).get("version"),
    }


def _pdf_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if PDF contains embedded images (stamps/signatures) on ANY page.

    Stamps and signatures may appear on any page (not just the first few).
    They can be embedded as XObject images, annotations, form fields, or
    digital signature dictionaries.

    Returns:
        True if images/stamps/signatures found (likely stamped/signed)
        False if nothing found (likely unsigned)
        None if check failed (can't determine)
    """
    try:
        import pypdf

        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)

            # --- Check 1: Scan ALL pages for stamp/signature-sized images ---
            # Content images (charts, figures, logos) are typically large
            # (e.g. 900x350, 600x475). Stamps/signatures are typically
            # small-to-medium (e.g. company stamps ~200x200, signature
            # images ~400x200). However, some stamps can be large
            # (e.g. 1477x1108 full-page stamp overlay).
            #
            # Strategy: Check if image could be a stamp by looking at
            # its XObject name (FormXob = form/signature overlay) and
            # aspect ratio / size heuristics.
            for page_idx, page in enumerate(reader.pages):
                try:
                    resources = page.get("/Resources")
                    if not resources:
                        continue
                    res_obj = (
                        resources.get_object()
                        if hasattr(resources, "get_object")
                        else resources
                    )
                    xobjects = res_obj.get("/XObject")
                    if not xobjects:
                        continue
                    xobj_dict = (
                        xobjects.get_object()
                        if hasattr(xobjects, "get_object")
                        else xobjects
                    )
                    for name, ref in xobj_dict.items():
                        try:
                            obj = (
                                ref.get_object() if hasattr(ref, "get_object") else ref
                            )
                            subtype = str(obj.get("/Subtype", ""))
                            if subtype != "/Image":
                                continue
                            width = int(obj.get("/Width", 0))
                            height = int(obj.get("/Height", 0))
                            name_str = str(name)

                            # Form XObject overlays (stamp/signature overlays)
                            if "formxob" in name_str.lower():
                                return True

                            if width > 0 and height > 0:
                                area = width * height
                                aspect = max(width, height) / max(min(width, height), 1)
                                # Small square-ish images (< 350x350 area,
                                # aspect < 2.0) are likely stamps/seals.
                                # Content images (charts/figures) are usually
                                # 400+ px wide and more rectangular.
                                if area < 120000 and aspect < 2.0:
                                    return True
                                # Last-page images are likely approval
                                # stamps/signatures (approval section at end)
                                if page_idx == len(reader.pages) - 1:
                                    return True
                                # Last-page images are more likely stamps
                                # (approval section is usually at the end)
                                if page_idx == len(reader.pages) - 1:
                                    return True
                        except Exception:
                            continue
                except Exception:
                    continue

            # --- Check 2: Scan ALL pages for annotations ---
            # Stamps/signatures can be PDF annotations (Stamp, Widget, Ink, etc.)
            for page in reader.pages:
                annots = page.get("/Annots")
                if annots:
                    annot_list = annots if isinstance(annots, list) else [annots]
                    for annot_ref in annot_list:
                        try:
                            annot = (
                                annot_ref.get_object()
                                if hasattr(annot_ref, "get_object")
                                else annot_ref
                            )
                            subtype = str(annot.get("/Subtype", ""))
                            # Signature-related annotation subtypes
                            if subtype in ("/Widget", "/Stamp", "/Ink", "/FreeText"):
                                ft = str(annot.get("/FT", ""))
                                if ft == "/Sig" or subtype in ("/Stamp", "/Ink"):
                                    return True
                                # Widget with appearance stream = filled form field
                                ap = annot.get("/AP")
                                if ap:
                                    return True
                        except Exception:
                            continue

            # --- Check 3: Document-level AcroForm / digital signatures ---
            try:
                catalog = reader.trailer["/Root"].get_object()
                acroform = catalog.get("/AcroForm")
                if acroform:
                    acroform_obj = (
                        acroform.get_object()
                        if hasattr(acroform, "get_object")
                        else acroform
                    )
                    # SigFlags indicates document has signature fields
                    sig_flags = acroform_obj.get("/SigFlags")
                    if sig_flags:
                        return True
                    # Check individual form fields for /Sig type
                    fields = acroform_obj.get("/Fields", [])
                    for field_ref in fields:
                        try:
                            field = (
                                field_ref.get_object()
                                if hasattr(field_ref, "get_object")
                                else field_ref
                            )
                            if str(field.get("/FT", "")) == "/Sig":
                                return True
                        except Exception:
                            continue
                # Check for Perms (permission/signature dictionary)
                if catalog.get("/Perms"):
                    return True
                # Check for DSS (Document Security Store)
                if catalog.get("/DSS"):
                    return True
            except Exception:
                pass

            return False
    except Exception:
        return None


def _docx_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if a Word (.docx) file contains embedded images (stamps/signatures).

    Stamps and signatures in Word documents are embedded as image parts.
    Unsigned documents have 0 images; stamped/signed documents have 1+ images.

    Returns:
        True if images found (likely stamped/signed)
        False if no images found (likely unsigned)
        None if check failed (can't determine)
    """
    try:
        from docx import Document as DocxDocument
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        doc = DocxDocument(file_path)
        # Check for image relationships in the document
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                return True
        return False
    except Exception:
        return None


def _xlsx_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if an Excel (.xlsx) file contains embedded images (stamps/signatures).

    Stamps and signatures in Excel files are embedded as images in the worksheet.
    Unsigned Excel forms have 0 images; stamped/signed versions have 1+ images.

    Returns:
        True if images found (likely stamped/signed)
        False if no images found (likely unsigned)
        None if check failed (can't determine)
    """
    try:
        from openpyxl import load_workbook

        wb = load_workbook(file_path, data_only=True)
        for ws in wb.worksheets:
            if ws._images:
                return True
        return False
    except Exception:
        return None


def detect_signature(ocr_result, file_path: str = "", lang: str = "zh-TW") -> dict:
    """Detect if document has signatures/stamps.

    Uses a two-phase approach:
    1. Check OCR metadata and text for stamp/signature indicators
    2. Cross-verify with raw PDF text extraction to catch LLM hallucinations

    Args:
        ocr_result: OCR processing result dict
        file_path: Path to original file for raw text cross-verification
        lang: Language code for i18n reason strings

    Returns a dict with:
        - detected (bool): True if real signatures/stamps found
        - stamps (list): List of detected stamp descriptions
        - signatures (list): List of detected signature descriptions
        - keyword_hits (list): Keyword matches found in text
        - reason (str): Human-readable explanation
    """
    from src.chainlit_app.i18n import I18N

    def _t(key, **kwargs):
        """Thread-safe translation."""
        text = I18N.get(lang, I18N.get("zh-TW", {})).get(
            key, I18N.get("zh-TW", {}).get(key, key)
        )
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return text

    result = {
        "detected": False,
        "stamps": [],
        "signatures": [],
        "keyword_hits": [],
        "reason": "",
    }

    # --- Check 1: structured detected_elements from OCR metadata ---
    detected = ocr_result.get("detected_elements", {})
    if detected:
        raw_stamps = detected.get("stamps", [])
        raw_sigs = detected.get("signatures", [])

        # Filter out placeholder / unrecognized entries
        placeholder_patterns = [
            "無法辨識",
            "n/a",
            "none",
            "null",
            "未偵測",
            "未檢測",
            "不明",
            "unknown",
            "unrecognized",
            "undetected",
        ]

        for s in raw_stamps:
            name = s.get("name", "") if isinstance(s, dict) else str(s)
            name_lower = name.lower().strip()
            if name_lower and not any(p in name_lower for p in placeholder_patterns):
                result["stamps"].append(name)

        for s in raw_sigs:
            name = s.get("name", "") if isinstance(s, dict) else str(s)
            name_lower = name.lower().strip()
            if name_lower and not any(p in name_lower for p in placeholder_patterns):
                result["signatures"].append(name)

    # --- Check 2: keyword search in OCR text ---
    ocr_text = (
        ocr_result.get("markdown_content", "")
        + " "
        + ocr_result.get("text_content", "")
    ).lower()

    # Keywords that indicate actual stamp/signature PRESENCE
    presence_keywords = [
        "[印章",
        "[簽名",
        "[stamp",
        "[seal",
        "[signature",
        "印章:",
        "簽名:",
        "stamp:",
        "seal:",
        "紅色圓形",
        "紅色方形",
        "藍色圓形",
        "藍色方形",
        "公司章",
        "負責人章",
        "法人章",
        "職章",
        "手寫簽名",
        "親筆簽名",
        "handwritten",
        "digitally signed",
    ]

    import re

    def _keyword_in_text(keyword: str, text: str) -> bool:
        """Check if keyword appears in text with word boundary awareness.

        For English keywords (ASCII-only, no brackets/colons), use word
        boundary matching to prevent partial matches like 'cap' in
        'capability' or 'visa' in 'Trevisan'.

        For CJK keywords and structured patterns (e.g. '[印章', 'stamp:'),
        use simple substring matching (CJK has no word boundaries).
        """
        # Structured patterns with brackets/colons → substring match
        if keyword.startswith("[") or keyword.endswith(":"):
            return keyword in text
        # Check if keyword is purely ASCII (English)
        is_ascii = all(ord(c) < 128 for c in keyword)
        if is_ascii and len(keyword) >= 2:
            # Use word boundary regex for English keywords
            pattern = r"\b" + re.escape(keyword) + r"\b"
            return bool(re.search(pattern, text))
        # CJK / mixed → substring match
        return keyword in text

    for kw in presence_keywords:
        if _keyword_in_text(kw, ocr_text):
            result["keyword_hits"].append(kw)

    general_keywords_found = []
    for kw in SIGNATURE_KEYWORDS:
        if _keyword_in_text(kw, ocr_text):
            general_keywords_found.append(kw)

    # --- Phase 1 decision (from OCR) ---
    has_real_stamps = len(result["stamps"]) > 0
    has_real_sigs = len(result["signatures"]) > 0
    has_presence_keywords = len(result["keyword_hits"]) > 0

    # --- Phase 2: Cross-verify with embedded image/signature analysis ---
    # Purpose: Catch LLM hallucinations in OCR metadata (stamps/signatures
    # detected_elements). Keywords from OCR text are TRUSTED because they
    # come from actual document text extraction, not LLM vision.
    #
    # Only gate LLM vision metadata; keyword hits are NOT gated by image check.
    file_lower = file_path.lower() if file_path else ""
    has_images = None  # None = can't determine or not applicable
    if file_path:
        if file_lower.endswith(".pdf"):
            has_images = _pdf_has_stamp_images(file_path)
        elif file_lower.endswith(".docx"):
            has_images = _docx_has_stamp_images(file_path)
        elif file_lower.endswith((".xlsx", ".xls")):
            has_images = _xlsx_has_stamp_images(file_path)

    # If LLM vision claimed stamps/sigs but file has NO embedded images,
    # discard those claims (likely hallucination).
    if (has_real_stamps or has_real_sigs) and has_images is False:
        result["stamps"] = []
        result["signatures"] = []
        has_real_stamps = False
        has_real_sigs = False

    # --- Final decision ---
    if has_real_stamps or has_real_sigs:
        # Trusted: LLM vision detected AND file has embedded images
        result["detected"] = True
        parts = []
        if result["stamps"]:
            parts.append(f"{_t('sig.stamps_label')}: {', '.join(result['stamps'])}")
        if result["signatures"]:
            parts.append(
                f"{_t('sig.signatures_label')}: {', '.join(result['signatures'])}"
            )
        result["reason"] = _t("sig.detected_prefix") + " " + "; ".join(parts)
    elif has_presence_keywords:
        # Trusted: strong presence keywords (e.g. [印章], 手寫簽名, digitally signed)
        result["detected"] = True
        result["reason"] = _t(
            "sig.presence_keywords", keywords=", ".join(result["keyword_hits"][:3])
        )
    elif general_keywords_found:
        # General keywords (e.g. "approved by", "signature", "簽章") found in text.
        # These could be table headers in unsigned docs. Use image check to decide:
        # - If file HAS embedded images → trust keywords (real signatures likely)
        # - If file has NO images → keywords are just form labels, not real sigs
        # - If can't determine (non-PDF/DOCX/XLSX or check failed) → trust keywords
        has_placeholders = any(
            p in ocr_text
            for p in ["[無法辨識]", "[空白]", "[empty]", "[blank]", "[n/a]"]
        )
        if has_placeholders and not has_real_stamps and not has_real_sigs:
            result["detected"] = False
            result["reason"] = _t("sig.empty_fields")
        elif has_images is False:
            # Keywords found but NO embedded images → just form/table headers
            result["detected"] = False
            file_type = "PDF"
            if file_lower.endswith(".docx"):
                file_type = "Word"
            elif file_lower.endswith((".xlsx", ".xls")):
                file_type = "Excel"
            result["reason"] = _t(
                "sig.keyword_no_image",
                type=file_type,
            )
        else:
            # has_images is True or None → trust the keywords
            result["detected"] = True
            result["reason"] = _t(
                "sig.keyword_detected", keywords=", ".join(general_keywords_found[:3])
            )
    elif has_images is True:
        # No keywords found, but stamp/signature-sized images detected in file.
        # This covers external documents where stamps are image-only without
        # any signature-related text (e.g. academic papers with a stamp overlay).
        # The _pdf_has_stamp_images() function already filters for stamp-like
        # images (FormXob overlays, small/square images, last-page images),
        # so has_images=True is a strong standalone signal.
        result["detected"] = True
        result["reason"] = _t("sig.image_detected")
    else:
        result["detected"] = False
        result["reason"] = _t("sig.none_detected")

    return result


# ============================================================
# Chat Profiles
# ============================================================


@cl.set_chat_profiles
async def chat_profile():
    # NOTE: @cl.set_chat_profiles runs BEFORE any user session exists,
    # so t() cannot determine the user's language. We use multilingual
    # inline descriptions as a workaround (zh-TW / EN / ja-JP).
    return [
        cl.ChatProfile(
            name="主系統 (Main Agent)",
            markdown_description=(
                "AI-QMS 品質管理系統主控台。文件列表、搜尋、作廢、稽核紀錄、LLM 對話。\n\n"
                "Quality Management Console. Document list, search, obsolete, audit trail, LLM chat.\n\n"
                "品質管理コンソール。文書一覧、検索、廃止、監査証跡、LLM チャット。"
            ),
            icon="/public/main_agent.svg",
        ),
        cl.ChatProfile(
            name="文件管制 (Doc Control)",
            markdown_description=(
                "文件上傳、OCR 處理、版本控制、簽章確認。拖放文件即可開始。\n\n"
                "File upload, OCR processing, version control, stamp confirmation. Drag & drop to start.\n\n"
                "ファイルアップロード、OCR 処理、版管理、印鑑確認。ドラッグ＆ドロップで開始。"
            ),
            icon="/public/doc_control.svg",
        ),
    ]


# ============================================================
# Chat Settings (LLM Configuration)
# ============================================================


def _mask_api_key(api_key: str) -> str:
    """Mask API key, showing only last 4 characters."""
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "••••"
    return "••••••••" + api_key[-4:]


def build_chat_settings(
    current_provider_name: str | None = None,
    current_provider_id: str | None = None,
    current_api_key: str = "",
    current_model: str | None = None,
    show_api_key: bool = False,
    current_language: str = None,
):
    """Build ChatSettings widgets for LLM configuration.

    Args:
        current_provider_name: Currently selected provider display name.
            If None, uses the first available provider.
        current_provider_id: Currently selected provider ID.
            If None, uses the first available provider.
        current_api_key: Current API key value (real, unmasked).
        current_model: Currently selected model name.
            If provided and found in model list, preserves the selection.
        show_api_key: Whether to show the API key in plain text.
        current_language: Current language display name.
    """
    # Determine language
    if current_language is None:
        try:
            lang_code = cl.user_session.get("language", "zh-TW")
            # Reverse lookup display name from code
            current_language = next(
                (k for k, v in LANG_CODE_MAP.items() if v == lang_code),
                SUPPORTED_LANGUAGES[0],
            )
        except Exception:
            current_language = SUPPORTED_LANGUAGES[0]

    lang_index = (
        SUPPORTED_LANGUAGES.index(current_language)
        if current_language in SUPPORTED_LANGUAGES
        else 0
    )
    lang_code = LANG_CODE_MAP.get(current_language, "zh-TW")

    provider_choices = get_provider_choices()
    provider_names = [p[0] for p in provider_choices]

    # Determine provider index and models
    if current_provider_name and current_provider_name in provider_names:
        provider_index = provider_names.index(current_provider_name)
    else:
        provider_index = 0

    if current_provider_id:
        models = get_model_choices(current_provider_id)
    else:
        default_pid = provider_choices[0][1] if provider_choices else "ollama"
        models = get_model_choices(default_pid)

    # Determine model index — preserve user's selection if valid
    model_list = models if models else ["default"]
    model_index = 0
    if current_model and current_model in model_list:
        model_index = model_list.index(current_model)

    # Mask API key if not showing
    display_api_key = current_api_key
    if current_api_key and not show_api_key:
        display_api_key = _mask_api_key(current_api_key)

    return cl.ChatSettings(
        [
            Select(
                id="Language",
                label=t("settings.language", lang=lang_code),
                values=SUPPORTED_LANGUAGES,
                initial_index=lang_index,
            ),
            Select(
                id="Provider",
                label=t("settings.provider", lang=lang_code),
                values=provider_names,
                initial_index=provider_index,
            ),
            Select(
                id="Model",
                label=t("settings.model", lang=lang_code),
                values=model_list,
                initial_index=model_index,
            ),
            TextInput(
                id="ApiKey",
                label=t("settings.api_key", lang=lang_code),
                initial=display_api_key,
                placeholder=t("settings.api_key_placeholder", lang=lang_code),
            ),
            Switch(
                id="ShowApiKey",
                label=t("settings.show_api_key", lang=lang_code),
                initial=show_api_key,
            ),
        ]
    )


@cl.on_settings_update
async def on_settings_update(settings):
    """Handle LLM settings changes.

    When the provider changes, rebuild and re-send ChatSettings so
    the Model dropdown refreshes with models for the new provider.

    v3.1.0: When API key is entered for a cloud provider, fetch live
    model list from the provider API, update the dropdown, and persist
    the model cache so models appear automatically on next startup.

    v3.2.0: Language selector and API key masking support.
    """
    # --- Handle language change ---
    language_display = settings.get("Language", SUPPORTED_LANGUAGES[0])
    lang_code = LANG_CODE_MAP.get(language_display, "zh-TW")
    prev_lang = cl.user_session.get("language", "zh-TW")
    language_changed = prev_lang != lang_code
    cl.user_session.set("language", lang_code)

    # --- Handle API key masking ---
    show_api_key = settings.get("ShowApiKey", False)
    raw_api_key_input = settings.get("ApiKey", "") or ""
    stored_real_key = cl.user_session.get("real_api_key", "") or ""
    prev_show = cl.user_session.get("show_api_key", False)
    show_toggled = prev_show != show_api_key
    cl.user_session.set("show_api_key", show_api_key)

    # Determine the real API key
    if "••••" in raw_api_key_input:
        # User didn't change the masked value — keep stored key
        api_key = stored_real_key
    else:
        # User entered a new key — strip whitespace to avoid header errors
        api_key = raw_api_key_input.strip()
        if api_key:
            cl.user_session.set("real_api_key", api_key)

    provider_name = settings.get("Provider", "")
    provider_id = get_provider_id_from_display(provider_name)
    selected_model = settings.get("Model", "default")

    # Update API key in environment
    if api_key:
        setup_api_key(provider_id, api_key)

    # Check if provider changed — need to refresh model list
    prev_provider_id = cl.user_session.get("provider_id", "")
    prev_api_key = cl.user_session.get("api_key", "")
    provider_changed = prev_provider_id != provider_id
    api_key_changed = prev_api_key != api_key and api_key

    # Store settings in session
    cl.user_session.set("provider_name", provider_name)
    cl.user_session.set("provider_id", provider_id)
    cl.user_session.set("api_key", api_key)

    # If only language or show_api_key toggled, rebuild settings UI and return
    if (
        (language_changed or show_toggled)
        and not provider_changed
        and not api_key_changed
    ):
        await build_chat_settings(
            current_provider_name=provider_name,
            current_provider_id=provider_id,
            current_api_key=api_key,
            current_model=selected_model,
            show_api_key=show_api_key,
            current_language=language_display,
        ).send()
        if show_toggled and api_key:
            if show_api_key:
                await cl.Message(content=f"🔓 API Key: `{api_key}`").send()
            else:
                await cl.Message(
                    content=f"🔒 API Key: `{_mask_api_key(api_key)}`"
                ).send()
        if language_changed:
            await cl.Message(content=t("settings.language_changed")).send()
            # Re-send welcome/instructions in the new language
            profile = cl.user_session.get("chat_profile")
            doc_count, doc_limit = get_document_count()
            if profile == "文件管制 (Doc Control)":
                welcome = (
                    f"{t('welcome.doc_control.title')}\n\n"
                    f"{t('welcome.doc_control.greeting')}\n\n"
                    f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
                    f"{t('welcome.doc_control.instructions')}\n\n"
                    f"{t('welcome.doc_control.formats')}"
                )
            else:
                welcome = (
                    f"{t('welcome.main.title')}\n\n"
                    f"{t('welcome.main.greeting')}\n\n"
                    f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
                    f"{t('welcome.main.instructions')}\n\n"
                    f"{t('welcome.main.switch_hint')}"
                )
            await cl.Message(content=welcome).send()
        return

    # v3.1.0: When API key is newly entered for a cloud provider,
    # fetch live model list and persist to cache
    if api_key_changed and not DEFAULT_PROVIDERS.get(provider_id, {}).get("is_local"):
        update_msg = cl.Message(
            content=t("settings.fetching_models", provider=provider_name)
        )
        await update_msg.send()
        try:
            update_results = await asyncio.to_thread(auto_update_models, [provider_id])
            result = update_results.get(provider_id, {})
            added = result.get("added", [])
            removed = result.get("removed", [])
            # Get current model count after update
            current_models = get_model_choices(provider_id)
            model_count = len(current_models)
            if added or removed:
                update_msg.content = t(
                    "settings.models_updated",
                    provider=provider_name,
                    added=len(added),
                    removed=len(removed),
                    total=model_count,
                )
            else:
                update_msg.content = t(
                    "settings.models_current",
                    provider=provider_name,
                    total=model_count,
                )
            await update_msg.update()
        except Exception as e:
            update_msg.content = t("settings.models_update_failed", error=str(e))
            await update_msg.update()
        # Force refresh model list after update
        provider_changed = True

    if provider_changed:
        # Rebuild ChatSettings with new provider's model list
        new_models = get_model_choices(provider_id)
        # Preserve user's selected model if it exists in new list;
        # otherwise fall back to first model.
        if selected_model in new_models:
            active_model = selected_model
        else:
            active_model = new_models[0] if new_models else "default"
        cl.user_session.set("model_name", active_model)

        # Re-send ChatSettings to update the Model dropdown in UI
        await build_chat_settings(
            current_provider_name=provider_name,
            current_provider_id=provider_id,
            current_api_key=api_key,
            current_model=active_model,
            show_api_key=show_api_key,
            current_language=language_display,
        ).send()

        settings_msg = t(
            "settings.updated",
            provider=provider_name,
            model=active_model,
            count=len(new_models),
        )
        await cl.Message(content=settings_msg).send()

        # Auto-test LLM connection after provider change
        test_msg = cl.Message(content=t("settings.testing_connection"))
        await test_msg.send()
        try:
            connection_result = await asyncio.to_thread(
                test_llm_connection, provider_id, active_model, api_key, lang_code
            )
            test_msg.content = connection_result
            await test_msg.update()
        except Exception as e:
            test_msg.content = t("settings.connection_failed", error=str(e))
            await test_msg.update()

        if language_changed:
            await cl.Message(content=t("settings.language_changed")).send()
            profile = cl.user_session.get("chat_profile")
            doc_count, doc_limit = get_document_count()
            if profile == "文件管制 (Doc Control)":
                welcome = (
                    f"{t('welcome.doc_control.title')}\n\n"
                    f"{t('welcome.doc_control.greeting')}\n\n"
                    f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
                    f"{t('welcome.doc_control.instructions')}\n\n"
                    f"{t('welcome.doc_control.formats')}"
                )
            else:
                welcome = (
                    f"{t('welcome.main.title')}\n\n"
                    f"{t('welcome.main.greeting')}\n\n"
                    f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
                    f"{t('welcome.main.instructions')}\n\n"
                    f"{t('welcome.main.switch_hint')}"
                )
            await cl.Message(content=welcome).send()
    else:
        cl.user_session.set("model_name", selected_model)
        settings_msg = t(
            "settings.updated_short",
            provider=provider_name,
            model=selected_model,
        )
        await cl.Message(content=settings_msg).send()

        # Auto-test LLM connection after model change
        test_msg = cl.Message(content=t("settings.testing_connection"))
        await test_msg.send()
        try:
            connection_result = await asyncio.to_thread(
                test_llm_connection, provider_id, selected_model, api_key, lang_code
            )
            test_msg.content = connection_result
            await test_msg.update()
        except Exception as e:
            test_msg.content = t("settings.connection_failed", error=str(e))
            await test_msg.update()


# ============================================================
# Chat Start
# ============================================================


@cl.on_chat_start
async def on_chat_start():
    """Initialize chat session"""
    profile = cl.user_session.get("chat_profile")
    ensure_upload_folder()

    # Initialize session state
    provider_choices = get_provider_choices()
    default_provider_name = (
        provider_choices[0][0] if provider_choices else "Ollama (Local)"
    )
    default_provider_id = provider_choices[0][1] if provider_choices else "ollama"
    default_models = get_model_choices(default_provider_id)
    default_model = default_models[0] if default_models else "default"

    cl.user_session.set("provider_name", default_provider_name)
    cl.user_session.set("provider_id", default_provider_id)
    cl.user_session.set("model_name", default_model)
    cl.user_session.set("api_key", "")
    cl.user_session.set("real_api_key", "")
    cl.user_session.set("show_api_key", False)
    cl.user_session.set("language", "zh-TW")
    cl.user_session.set("message_history", [])

    # Doc Control specific state
    cl.user_session.set("pending_files", [])
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)
    cl.user_session.set("awaiting_delete_confirm", False)

    # Send settings
    settings = build_chat_settings()
    await settings.send()

    # Welcome message based on profile
    doc_count, doc_limit = get_document_count()

    if profile == "文件管制 (Doc Control)":
        welcome = (
            f"{t('welcome.doc_control.title')}\n\n"
            f"{t('welcome.doc_control.greeting')}\n\n"
            f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
            f"{t('welcome.doc_control.instructions')}\n\n"
            f"{t('welcome.doc_control.formats')}"
        )
    else:
        welcome = (
            f"{t('welcome.main.title')}\n\n"
            f"{t('welcome.main.greeting')}\n\n"
            f"{t('welcome.doc_control.doc_count', count=doc_count, limit=doc_limit)}\n\n"
            f"{t('welcome.main.instructions')}\n\n"
            f"{t('welcome.main.switch_hint')}"
        )

    await cl.Message(content=welcome).send()


# ============================================================
# Command Handlers (shared between profiles)
# ============================================================


async def handle_help(profile: str) -> str:
    """Handle help command"""
    if profile == "文件管制 (Doc Control)":
        return t("help.doc_control")
    else:
        return t("help.main")


async def handle_status() -> str:
    """Handle status command"""
    doc_count, doc_limit = get_document_count()
    provider_name = cl.user_session.get("provider_name", "N/A")
    model_name = cl.user_session.get("model_name", "N/A")

    phoenix_status = "✅ Active" if PHOENIX_ENABLED else "❌ Disabled"
    phoenix_url = os.getenv(
        "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"
    ).replace("/v1/traces", "")

    return f"""{t("status.title")}

- **{t("status.doc_count")}**: {doc_count}/{doc_limit}
- **{t("status.provider")}**: {provider_name}
- **{t("status.model")}**: {model_name}
- **{t("status.ocr")}**: {t("status.ocr_ready")}
- **{t("status.ui")}**: Chainlit
- **Phoenix Tracing**: {phoenix_status} ({phoenix_url})"""


async def handle_list() -> str:
    """Handle 列表 command - show ALL documents including version history and obsolete."""
    try:
        storage = get_markdown_store()
        registry = storage.registry
        all_docs = registry.get("documents", [])

        if not all_docs:
            return t("no_docs")

        active_count = sum(1 for d in all_docs if d.get("status", "active") == "active")
        obsolete_count = sum(1 for d in all_docs if d.get("status") == "obsolete")
        total_versions = sum(len(d.get("versions", [])) for d in all_docs)
        superseded_count = 0

        doc_lines = []
        for doc in all_docs:
            doc_id = doc["doc_id"]
            title = doc.get("title", "N/A")
            doc_type = doc.get("doc_type", "OTHER")
            status_str = doc.get("status", "active")
            current_ver = doc.get("current_version", "?")

            for ver_entry in doc.get("versions", []):
                ver = ver_entry.get("version", "?")
                created_at = ver_entry.get("created_at", "")[:10]
                created_by = ver_entry.get("created_by", "system")
                files_removed = ver_entry.get("files_removed", False)

                if status_str == "obsolete":
                    row_status = t("allrecords.status_obsolete")
                elif files_removed:
                    row_status = t("allrecords.status_superseded")
                    superseded_count += 1
                elif ver == current_ver:
                    row_status = t("allrecords.status_current")
                else:
                    row_status = t("allrecords.status_superseded")
                    superseded_count += 1

                doc_lines.append(
                    f"| {doc_id} | {title} | {doc_type} | v{ver} | {created_at} | {created_by} | {row_status} |"
                )

        doc_list = "\n".join(doc_lines)
        summary_parts = [t("allrecords.summary_active", count=active_count)]
        if superseded_count:
            summary_parts.append(
                t("allrecords.summary_superseded", count=superseded_count)
            )
        if obsolete_count:
            summary_parts.append(t("allrecords.summary_obsolete", count=obsolete_count))
        lang = cl.user_session.get("language", "zh-TW")
        sep = "、" if lang == "ja-JP" else "，" if lang.startswith("zh") else ", "
        summary_str = sep.join(summary_parts)
        return f"""{t("allrecords.title", doc_count=len(all_docs), version_count=total_versions, summary=summary_str)}

{t("allrecords.header")}
{doc_list}

{t("allrecords.hint_doclist")}
{t("allrecords.hint_audit")}
{t("allrecords.hint_export")}"""
    except Exception as e:
        return t("allrecords.error", error=str(e))


async def handle_document_list() -> str:
    """Handle 文件清單 command - show only current formal (active) versions."""
    try:
        md_service = MarkdownStoreService()
        docs = md_service.list_documents()
        stats = md_service.get_stats()

        if not docs:
            return t("no_saved_docs")

        active_docs = [d for d in docs if d.get("status", "active") == "active"]

        if not active_docs:
            return t("no_active_docs")

        doc_lines = []
        for d in active_docs:
            doc_lines.append(
                f"| {d['doc_id']} | {d.get('title', 'N/A')} | {d['doc_type']} | v{d['current_version']} |"
            )
        doc_list = "\n".join(doc_lines)
        return f"""{t("doclist.title", count=len(active_docs))}

{t("doclist.header")}
{doc_list}

{t("doclist.hint_list")}
{t("doclist.hint_search")}
{t("doclist.hint_export")}"""
    except Exception as e:
        return t("doclist.error", error=str(e))


async def handle_search(query: str) -> str:
    """Handle search command"""
    if not query:
        return t("search.empty")
    try:
        md_service = MarkdownStoreService()
        results = md_service.search(query, limit=5)
        if results:
            result_list = "\n".join(
                [
                    f"- **{r['doc_id']}**: {r.get('title', 'N/A')} (v{r.get('version', '?')})\n  > {r.get('snippet', '')[:100]}..."
                    for r in results
                ]
            )
            return (
                t("search.results", query=query, count=len(results))
                + f"\n\n{result_list}"
            )
        else:
            return t("search.no_results", query=query)
    except Exception as e:
        return t("search.failed", error=str(e))


async def handle_obsolete(text: str) -> str:
    """Handle obsolete command"""
    doc_id_match = re.search(
        r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if doc_id_match:
        doc_id = doc_id_match.group(1).upper()
        reason_text = text
        for kw in ["作廢", "obsolete", doc_id_match.group(0)]:
            reason_text = reason_text.replace(kw, "")
        reason = reason_text.strip() or t("obsolete.default_reason")

        md_service = MarkdownStoreService()
        result = md_service.obsolete_document(
            doc_id=doc_id,
            reason=reason,
            user_id="chainlit_user",
        )
        if result.get("success"):
            audit_log = ImmutableAuditLog()
            audit_log.create_record(
                action="DOCUMENT_OBSOLETED",
                document_id=doc_id,
                user_id="chainlit_user",
                details={
                    "title": result.get("title", ""),
                    "doc_type": result.get("doc_type", ""),
                    "version": result.get("version", ""),
                    "reason": reason,
                    "files_deleted_count": result.get("files_deleted_count", 0),
                },
            )
            return t(
                "obsolete.success",
                doc_id=doc_id,
                title=result.get("title", "N/A"),
                doc_type=result.get("doc_type", "N/A"),
                version=result.get("version", "N/A"),
                reason=reason,
                files_deleted=result.get("files_deleted_count", 0),
            )
        else:
            return t("obsolete.failed", error=result.get("error", "Unknown"))
    else:
        # No doc_id specified, show available documents
        md_service = MarkdownStoreService()
        docs = md_service.list_documents()
        active_docs = [d for d in docs if d.get("status", "active") == "active"]
        if active_docs:
            doc_list = "\n".join(
                [
                    f"| {d['doc_id']} | {d.get('title', 'N/A')} | {d['doc_type']} | v{d['current_version']} |"
                    for d in active_docs[:20]
                ]
            )
            return (
                f"{t('obsolete.no_doc')}\n\n"
                f"{t('obsolete.available_title', count=len(active_docs))}\n\n"
                f"{t('obsolete.table_header')}\n"
                f"{doc_list}\n\n"
                f"{t('obsolete.example')}"
            )
        else:
            return t("obsolete.no_docs_available")


async def handle_audit() -> str:
    """Handle audit record display"""
    audit_log = ImmutableAuditLog()
    records = audit_log.get_all_records()
    is_valid, integrity_msg = audit_log.verify_chain_integrity()
    table_md = format_audit_table_markdown(records)
    if is_valid:
        table_md += f"\n\n{t('audit.chain_valid', msg=integrity_msg)}"
    else:
        table_md += f"\n\n{t('audit.chain_invalid', msg=integrity_msg)}"
    return table_md


async def handle_audit_export(format_type: str):
    """Handle audit export to Word/Excel, returns file element"""
    audit_log = ImmutableAuditLog()
    records = audit_log.get_all_records()
    if not records:
        return None, t("audit.no_records")

    if format_type == "word":
        filepath = export_to_word(records)
        msg = t("audit.export_word", count=len(records))
    elif format_type == "excel":
        filepath = export_to_excel(records)
        msg = t("audit.export_excel", count=len(records))
    else:
        return (
            None,
            t("audit.export_pdf_wip"),
        )

    return filepath, msg


async def handle_regulatory_list():
    """Handle 法規清單 command — scan and display regulatory standards from all documents."""
    storage = get_markdown_store()
    scan_result = storage.scan_regulatory_references()
    # Store in session for later export
    cl.user_session.set("last_regulatory_scan", scan_result)
    return format_regulatory_table_markdown(scan_result)


async def handle_regulatory_export(format_type: str):
    """Handle 下載法規清單 word/excel command."""
    scan_result = cl.user_session.get("last_regulatory_scan")
    if not scan_result:
        # Run scan if not already cached
        storage = get_markdown_store()
        scan_result = storage.scan_regulatory_references()
        cl.user_session.set("last_regulatory_scan", scan_result)

    aggregate = scan_result.get("aggregate", [])
    if not aggregate:
        return None, t("regulatory.no_refs")

    if format_type == "word":
        filepath = export_regulatory_to_word(scan_result)
        msg = t("regulatory.export_word", count=len(aggregate))
    elif format_type == "excel":
        filepath = export_regulatory_to_excel(scan_result)
        msg = t("regulatory.export_excel", count=len(aggregate))
    else:
        return None, t("regulatory.export_hint")

    return filepath, msg


async def handle_reference_export(format_type: str):
    """Handle 下載引用清單 word/excel command (after version update)."""
    ref_data = cl.user_session.get("last_reference_result")
    if not ref_data:
        return (
            None,
            t("reference.no_data"),
        )

    doc_id = ref_data.get("doc_id", "UNKNOWN")
    ref_docs = ref_data.get("ref_docs", [])
    if not ref_docs:
        return None, t("reference.no_refs", doc_id=doc_id)

    if format_type == "word":
        filepath = export_reference_to_word(doc_id, ref_docs)
        msg = t("reference.export_word", doc_id=doc_id, count=len(ref_docs))
    elif format_type == "excel":
        filepath = export_reference_to_excel(doc_id, ref_docs)
        msg = t("reference.export_excel", doc_id=doc_id, count=len(ref_docs))
    else:
        return None, t("reference.export_hint")

    return filepath, msg


async def handle_doclist_export(format_type: str):
    """Handle document list (current formal versions) export to Word/Excel."""
    md_service = MarkdownStoreService()
    docs = md_service.list_documents()
    active_docs = [d for d in docs if d.get("status", "active") == "active"]
    if not active_docs:
        return None, t("doclist.no_export_data")

    if format_type == "word":
        filepath = export_doclist_to_word(active_docs)
        msg = t("doclist.export_word", count=len(active_docs))
    elif format_type == "excel":
        filepath = export_doclist_to_excel(active_docs)
        msg = t("doclist.export_excel", count=len(active_docs))
    else:
        return None, t("doclist.export_hint")

    return filepath, msg


async def handle_allrecords_export(format_type: str):
    """Handle all records export to Word/Excel."""
    storage = get_markdown_store()
    registry = storage.registry
    all_docs = registry.get("documents", [])
    if not all_docs:
        return None, t("allrecords.no_export_data")

    if format_type == "word":
        filepath = export_allrecords_to_word(all_docs)
        msg = t("allrecords.export_word", count=len(all_docs))
    elif format_type == "excel":
        filepath = export_allrecords_to_excel(all_docs)
        msg = t("allrecords.export_excel", count=len(all_docs))
    else:
        return None, t("allrecords.export_hint")

    return filepath, msg


async def handle_download(text: str):
    """Handle file download request, returns (filepath, message)"""
    doc_id_match = re.search(
        r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if doc_id_match:
        req_doc_id = doc_id_match.group(1).upper()
        storage = get_markdown_store()
        file_path = storage.get_original_file_path(req_doc_id)
        if file_path:
            fname = re.sub(r"^\d{14}_", "", Path(file_path).name)
            return file_path, t("download.found", doc_id=req_doc_id, filename=fname)
        else:
            return None, t("download.not_found", doc_id=req_doc_id)
    else:
        storage = get_markdown_store()
        docs = storage.list_documents_with_files()
        available = [d for d in docs if d["has_original_file"]]
        msg = (
            t("download.specify", count=len(available))
            + "\n\n"
            + "\n".join(
                [
                    f"- **{d['doc_id']}** ({d['file_extension']}) - {d['title']}"
                    for d in available[:10]
                ]
            )
        )
        if len(available) > 10:
            msg += "\n" + t("download.more", count=len(available) - 10)
        msg += "\n\n" + t("download.example")
        return None, msg


async def handle_delete_db():
    """Handle delete database command"""
    cl.user_session.set("awaiting_delete_confirm", True)

    actions = [
        cl.Action(
            name="confirm_delete",
            payload={"action": "delete_all"},
            label=t("delete.confirm_btn"),
        ),
        cl.Action(
            name="cancel_delete",
            payload={"action": "cancel"},
            label=t("delete.cancel_btn"),
        ),
    ]

    await cl.Message(
        content=t("delete.warning"),
        actions=actions,
    ).send()


@cl.action_callback("confirm_delete")
async def on_confirm_delete(action):
    """Execute database deletion"""
    try:
        storage_manager = get_markdown_store()
        audit_log = ImmutableAuditLog()

        docs_dir = storage_manager.documents_path
        doc_list = []
        try:
            for doc in storage_manager.registry.get("documents", []):
                doc_list.append(doc.get("doc_id", "unknown"))
        except Exception:
            pass

        deleted_count = 0
        for md_file in docs_dir.rglob("*.md"):
            md_file.unlink()
            deleted_count += 1

        storage_manager.registry = {
            "registry_version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "document_count": 0,
            "documents": [],
        }
        storage_manager._save_registry()

        doc_store_path = Path("data/document_store.json")
        if doc_store_path.exists():
            with open(doc_store_path, "w", encoding="utf-8") as f:
                json.dump({"documents": {}}, f, ensure_ascii=False, indent=2)

        uploads_dir = UPLOAD_FOLDER
        upload_deleted = 0
        if uploads_dir.exists():
            for f in uploads_dir.iterdir():
                if f.is_file():
                    f.unlink()
                    upload_deleted += 1

        audit_log.create_record(
            action="bulk_delete",
            document_id="ALL",
            user_id="chainlit_user",
            details={
                "deleted_md_count": deleted_count,
                "deleted_upload_count": upload_deleted,
                "deleted_doc_ids": doc_list,
            },
        )

        await cl.Message(
            content=t(
                "delete.success", md_count=deleted_count, upload_count=upload_deleted
            )
        ).send()
    except Exception as e:
        await cl.Message(content=t("delete.failed", error=str(e))).send()

    await action.remove()


@cl.action_callback("cancel_delete")
async def on_cancel_delete(action):
    """Cancel database deletion"""
    cl.user_session.set("awaiting_delete_confirm", False)
    await cl.Message(content=t("delete.cancelled")).send()
    await action.remove()


# ============================================================
# Download Action Callbacks
# ============================================================


async def _send_file_download(filepath: str, msg_text: str):
    """Helper: send a file as a download with cl.File element."""
    display_name = re.sub(r"^\d{14}_", "", Path(filepath).name)
    elements = [cl.File(name=display_name, path=filepath, display="inline")]
    await cl.Message(content=msg_text, elements=elements).send()


@cl.action_callback("download_audit_word")
async def on_download_audit_word(action):
    """Download audit records as Word."""
    filepath, msg_text = await handle_audit_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_audit_excel")
async def on_download_audit_excel(action):
    """Download audit records as Excel."""
    filepath, msg_text = await handle_audit_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_regulatory_word")
async def on_download_regulatory_word(action):
    """Download regulatory standards list as Word."""
    filepath, msg_text = await handle_regulatory_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_regulatory_excel")
async def on_download_regulatory_excel(action):
    """Download regulatory standards list as Excel."""
    filepath, msg_text = await handle_regulatory_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_reference_word")
async def on_download_reference_word(action):
    """Download reference list as Word."""
    filepath, msg_text = await handle_reference_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_reference_excel")
async def on_download_reference_excel(action):
    """Download reference list as Excel."""
    filepath, msg_text = await handle_reference_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_doclist_word")
async def on_download_doclist_word(action):
    """Download document list as Word."""
    filepath, msg_text = await handle_doclist_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_doclist_excel")
async def on_download_doclist_excel(action):
    """Download document list as Excel."""
    filepath, msg_text = await handle_doclist_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_allrecords_word")
async def on_download_allrecords_word(action):
    """Download all records as Word."""
    filepath, msg_text = await handle_allrecords_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_allrecords_excel")
async def on_download_allrecords_excel(action):
    """Download all records as Excel."""
    filepath, msg_text = await handle_allrecords_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()
    await action.remove()


@cl.action_callback("download_original_file")
async def on_download_original_file(action):
    """Download original uploaded file by doc_id."""
    doc_id = action.payload.get("doc_id", "")
    if not doc_id:
        await cl.Message(content=t("download.no_doc_id")).send()
        await action.remove()
        return

    storage = get_markdown_store()
    file_path = storage.get_original_file_path(doc_id)
    if file_path:
        fname = Path(file_path).name
        await _send_file_download(file_path, f"📄 **{doc_id}** — {fname}")
    else:
        await cl.Message(content=t("download.file_error", doc_id=doc_id)).send()
    await action.remove()

    # ============================================================
    # Doc Control: File Upload Processing
    # ============================================================


def _format_process_detail(result: dict) -> str:
    """Format detailed processing information for a single file result."""
    lines = []
    filename = result.get("filename", "")

    # Conversion result details
    ocr = result.get("ocr_result", {})
    if ocr:
        provider = ocr.get("provider_used", "unknown")
        confidence = ocr.get("confidence", 0)
        time_ms = ocr.get("processing_time_ms", 0)
        page_count = ocr.get("page_count", 0)
        file_type = ocr.get("file_type", "unknown")
        content_len = len(ocr.get("markdown_content", ""))

        time_str = f"{time_ms / 1000:.1f}s" if time_ms else "N/A"
        conf_str = f"{confidence * 100:.0f}%" if confidence else "N/A"

        # Show whether MarkItDown or LLM was used
        engine_label = "MarkItDown" if provider == "MarkItDown" else f"LLM ({provider})"
        lines.append(
            f"  {t('upload.engine_label')}: {engine_label} | {page_count} pg | {time_str} | {content_len:,} chars | {file_type}"
        )

    # Document type detection
    doc_info = result.get("doc_info", {})
    if doc_info:
        doc_type = doc_info.get("doc_type", "OTHER")
        doc_id = doc_info.get("doc_id", "")
        is_new = doc_info.get("is_new", True)
        det_ver = doc_info.get("detected_version", "")
        type_label = t("upload.doc_new") if is_new else t("upload.doc_exists")
        ver_str = f" v{det_ver}" if det_ver else ""
        lines.append(
            f"  {t('upload.doc_detect_label')}: {doc_type} | {doc_id}{ver_str} | {type_label}"
        )

    # Signature detection
    sig = result.get("sig_result", {})
    if sig:
        if sig.get("detected"):
            stamp_list = sig.get("stamps", [])
            sig_list = sig.get("signatures", [])
            parts = []
            if stamp_list:
                parts.append(
                    t("upload.sig_stamps", count=len(stamp_list))
                    + f": {', '.join(stamp_list[:3])}"
                )
            if sig_list:
                parts.append(
                    t("upload.sig_signatures", count=len(sig_list))
                    + f": {', '.join(sig_list[:3])}"
                )
            if not parts:
                parts.append(sig.get("reason", ""))
            lines.append(f"  {t('upload.sig_label')}: ✅ {'; '.join(parts)}")
        else:
            lines.append(f"  {t('upload.sig_label')}: ❌ {sig.get('reason', '')}")

    # Save result
    if result.get("success"):
        doc_id = result.get("saved_doc_id", "")
        if result.get("is_version_update"):
            dup_id = result.get("duplicate_doc", {}).get("doc_id", "")
            existing_ver = result.get("existing_version", "?")
            new_ver = result.get("new_version", "?")
            lines.append(
                f"  {t('upload.save_label')}: {t('upload.save_new_version', doc_id=dup_id, old_ver=existing_ver, new_ver=new_ver)}"
            )
        elif result.get("is_duplicate"):
            dup_id = result.get("duplicate_doc", {}).get("doc_id", "")
            lines.append(
                f"  {t('upload.save_label')}: {t('upload.save_duplicate', doc_id=dup_id)}"
            )
        elif doc_id:
            lines.append(
                f"  {t('upload.save_label')}: {t('upload.save_success', doc_id=doc_id)}"
            )
    else:
        error = result.get("error", "")
        lines.append(f"  {t('upload.result_label')}: ❌ {error}")

    return "\n".join(lines)


async def handle_file_upload(files):
    """Handle file upload in Doc Control profile.

    Shows step-by-step progress per file:
    Step 1: Markdown 轉換 (MarkItDown)
    Step 2: 簽章偵測 (pypdf image check)
    Step 3: 存入資料庫
    """
    if not files:
        return

    total = len(files)
    succeeded = []
    failed = []

    # Pre-fetch session data for thread-safe access
    provider_id = cl.user_session.get("provider_id", "ollama")
    api_key = cl.user_session.get("api_key", "").strip()
    model_name = cl.user_session.get("model_name", "")

    # Initial progress message
    provider_name = cl.user_session.get("provider_name", provider_id)
    progress_msg = cl.Message(
        content=t(
            "file.start_processing",
            total=total,
            provider=provider_name,
            model=model_name,
        )
    )
    await progress_msg.send()

    for idx, file_el in enumerate(files):
        step = f"({idx + 1}/{total})"
        file_name = file_el.name

        # --- Step 1: Show progress ---
        progress_msg.content = (
            t("upload.progress_title", step=step, filename=file_name) + "\n\n"
            f"  {t('upload.step1_active')}\n"
            f"  {t('upload.step2_pending')}\n"
            f"  {t('upload.step3_pending')}\n"
        )
        await progress_msg.update()

        lang = cl.user_session.get("language", "zh-TW")
        result = await asyncio.to_thread(
            process_uploaded_file_sync, file_el, provider_id, api_key, model_name, lang
        )

        if result["success"]:
            succeeded.append(result)
        else:
            failed.append(result)

        # --- Show completed result for this file ---
        detail = _format_process_detail(result)
        status_icon = "✅" if result["success"] else "❌"

        # Build completed steps display
        ocr = result.get("ocr_result", {})
        provider = ocr.get("provider_used", "unknown") if ocr else "unknown"
        time_ms = ocr.get("processing_time_ms", 0) if ocr else 0
        time_str = f"{time_ms / 1000:.1f}s" if time_ms else "N/A"

        sig = result.get("sig_result", {})
        sig_icon = "✅" if sig.get("detected") else "❌"
        sig_text = sig.get("reason", "") if sig else ""

        saved_id = result.get("saved_doc_id", "")
        save_text = (
            f"✅ → {saved_id}"
            if saved_id
            else ("❌ " + result.get("error", ""))
            if not result["success"]
            else "🔄"
            if result.get("is_version_update")
            else "⚠️"
            if result.get("is_duplicate")
            else ""
        )

        progress_msg.content = (
            t("upload.progress_title", step=step, filename=file_name)
            + f" {status_icon}\n\n"
            f"  {t('upload.step1_done', provider=provider, time=time_str)}\n"
            f"  {t('upload.step2_done', icon=sig_icon, reason=sig_text)}\n"
            f"  {t('upload.step3_done', icon='✅' if result['success'] else '❌', detail=save_text)}\n"
        )
        await progress_msg.update()

    # ---- Build final summary (compact one-line-per-file for all uploads) ----
    lines = [t("file.summary", total=total)]

    for r in succeeded + failed:
        status_icon = "✅" if r.get("success") else "❌"
        doc_id = r.get("saved_doc_id") or r.get("duplicate_doc", {}).get("doc_id", "")
        id_str = f" → **{doc_id}**" if doc_id else ""
        if r.get("is_version_update"):
            dup_tag = " " + t("upload.tag_version")
        elif r.get("is_duplicate"):
            dup_tag = " " + t("upload.tag_duplicate")
        else:
            dup_tag = ""
        # Signature status
        sig = r.get("sig_result", {})
        sig_str = ""
        if sig:
            if sig.get("detected"):
                sig_str = f" | {t('upload.sig_label')}: ✅"
            else:
                sig_str = f" | {t('upload.sig_label')}: ❌"
        err_str = ""
        if not r.get("success"):
            err_str = f" — {r.get('error', '')}"
        lines.append(
            f"- {status_icon} `{r['filename']}`{id_str}{dup_tag}{sig_str}{err_str}"
        )

    # Summary counts
    lines.append(
        f"\n---\n{t('file.stats', success=len(succeeded), failed=len(failed))}"
    )

    # Handle duplicate detection (works for both single and bulk)
    if succeeded:
        last = succeeded[-1]
        if last.get("is_duplicate"):
            dup = last["duplicate_doc"]
            existing_ver = last.get("existing_version", dup.get("current_version", "?"))
            new_ver = last.get("new_version", "?")
            lines.append(
                "\n\n"
                + t(
                    "file.version_detected",
                    doc_id=dup["doc_id"],
                    old_ver=existing_ver,
                    new_ver=new_ver,
                )
            )

            # Store state for version update flow
            cl.user_session.set("current_ocr_result", last.get("ocr_result"))
            cl.user_session.set("current_doc_info", last.get("doc_info"))
            cl.user_session.set("current_file_path", last.get("dest_path"))

    progress_msg.content = "\n".join(lines)
    await progress_msg.update()

    # If there's a version update candidate, offer version update
    if succeeded and succeeded[-1].get("is_duplicate"):
        last = succeeded[-1]
        existing_ver = last.get("existing_version", "?")
        new_ver = last.get("new_version", "?")
        actions = [
            cl.Action(
                name="confirm_version_update",
                payload={"action": "version_update"},
                label=t("file.confirm_version"),
            ),
            cl.Action(
                name="cancel_version_update",
                payload={"action": "cancel"},
                label=t("file.cancel"),
            ),
        ]
        await cl.Message(
            content=t(
                "file.version_exists",
                doc_id=last["duplicate_doc"]["doc_id"],
                old_ver=existing_ver,
                new_ver=new_ver,
            ),
            actions=actions,
        ).send()


def process_uploaded_file_sync(
    file_element,
    provider_id: str = "ollama",
    api_key: str = "",
    model_name: str = "",
    lang: str = "zh-TW",
):
    """Synchronous wrapper for file processing (runs in thread).

    NOTE: cl.user_session is NOT accessible from a thread context.
    All session data must be passed as parameters.
    """
    from src.chainlit_app.i18n import I18N

    def _t(key, **kwargs):
        """Thread-safe translation without cl.user_session."""
        text = I18N.get(lang, I18N.get("zh-TW", {})).get(
            key, I18N.get("zh-TW", {}).get(key, key)
        )
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return text

    file_path = file_element.path
    filename = file_element.name
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "filename": filename,
            "error": _t("file.unsupported", suffix=suffix),
        }

    ensure_upload_folder()
    dest_path = UPLOAD_FOLDER / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    shutil.copy(file_path, dest_path)

    setup_api_key(provider_id, api_key)

    try:
        llm_manager = create_provider_manager(provider_id)
        # Disable fallback chain when user explicitly selected a provider
        if provider_id != "ollama":
            llm_manager.disable_fallback = True
    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "error": _t("upload.llm_init_error", error=str(e)),
        }

    ocr_result = process_document(str(dest_path), llm_manager, model_name=model_name)
    if not ocr_result.get("success"):
        try:
            dest_path.unlink()
        except Exception:
            pass
        return {
            "success": False,
            "filename": filename,
            "error": _t("upload.ocr_error", error=ocr_result.get("error_message", "")),
        }

    ocr_text_for_detection = ocr_result.get("text_content", "") or ocr_result.get(
        "markdown_content", ""
    )
    doc_info = detect_document_type(filename, ocr_text_for_detection)
    sig_result = detect_signature(ocr_result, file_path=str(dest_path), lang=lang)

    if not sig_result["detected"]:
        try:
            dest_path.unlink()
        except Exception:
            pass
        return {
            "success": False,
            "filename": filename,
            "error": _t("upload.no_sig_error", reason=sig_result["reason"]),
            "ocr_result": ocr_result,
            "doc_info": doc_info,
            "sig_result": sig_result,
        }

    md_service = MarkdownStoreService()
    duplicate_doc = md_service.check_duplicate(str(dest_path))

    if duplicate_doc:
        return {
            "success": True,
            "filename": filename,
            "dest_path": str(dest_path),
            "ocr_result": ocr_result,
            "doc_info": doc_info,
            "sig_result": sig_result,
            "duplicate_doc": duplicate_doc,
            "is_duplicate": True,
        }

    # Check if doc_id already exists — compare versions to decide action
    extracted_doc_id = doc_info.get("doc_id")
    new_version = doc_info.get("detected_version")
    if extracted_doc_id:
        storage_mgr = md_service._manager
        if storage_mgr.document_exists(extracted_doc_id):
            existing_doc = None
            for doc in storage_mgr.registry["documents"]:
                if doc["doc_id"] == extracted_doc_id:
                    existing_doc = doc
                    break
            if existing_doc:
                existing_version = existing_doc.get("current_version", "")
                # Normalize for comparison: strip "v"/"V" prefix
                norm_new = (new_version or "").lstrip("vV").strip()
                norm_existing = existing_version.lstrip("vV").strip()

                if norm_new and norm_new == norm_existing:
                    # Same version = true duplicate, reject outright
                    try:
                        dest_path.unlink()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "filename": filename,
                        "error": _t(
                            "upload.same_version_error",
                            doc_id=extracted_doc_id,
                            version=norm_existing,
                        ),
                    }
                else:
                    # Different version (or version unknown) = potential version update
                    return {
                        "success": True,
                        "filename": filename,
                        "dest_path": str(dest_path),
                        "ocr_result": ocr_result,
                        "doc_info": doc_info,
                        "sig_result": sig_result,
                        "duplicate_doc": existing_doc,
                        "is_duplicate": True,
                        "is_version_update": True,
                        "new_version": new_version,
                        "existing_version": existing_version,
                    }

    save_result = md_service.save_ocr_result(
        markdown_content=ocr_result["markdown_content"],
        source_filename=filename,
        source_file_path=str(dest_path),
        doc_id=doc_info.get("doc_id"),
        title=doc_info.get("title"),
        doc_type=doc_info.get("doc_type", "OTHER"),
        tags=[doc_info.get("doc_type", "OTHER"), "ocr-auto"],
        ocr_provider=ocr_result.get("provider_used", "unknown"),
        ocr_confidence=ocr_result.get("confidence", 0.0),
        detected_version=new_version,
    )

    if save_result.get("success"):
        return {
            "success": True,
            "filename": filename,
            "dest_path": str(dest_path),
            "ocr_result": ocr_result,
            "doc_info": doc_info,
            "sig_result": sig_result,
            "saved_doc_id": save_result.get("doc_id"),
            "is_duplicate": False,
        }
    else:
        return {
            "success": False,
            "filename": filename,
            "error": _t("upload.storage_error", error=save_result.get("error", "")),
        }


# ============================================================
# Version Update / Stamp Confirmation Actions
# ============================================================


@cl.action_callback("confirm_version_update")
async def on_confirm_version_update(action):
    """Ask user to type confirmer name for version update"""
    await action.remove()

    sig_status = t("version.stamp_status")

    # Set session flag: next text message = confirmer name
    cl.user_session.set("awaiting_confirmer_name", True)

    await cl.Message(
        content=f"""{t("version.stamp_confirm_title")}

{sig_status}

{t("version.checklist")}

{t("version.warning")}

{t("version.enter_name")}""",
    ).send()


async def _execute_version_update(confirmer_name: str):
    """Execute version update after confirmer name is provided."""
    ocr_result = cl.user_session.get("current_ocr_result")
    doc_info = cl.user_session.get("current_doc_info")
    file_path = cl.user_session.get("current_file_path")

    if not ocr_result or not doc_info:
        await cl.Message(content=t("version.no_data")).send()
        return

    try:
        storage_manager = get_markdown_store()
        audit_log = ImmutableAuditLog()

        ocr_detected_version = doc_info.get("detected_version", None)
        result = storage_manager.update_document(
            doc_id=doc_info.get("doc_id", "UNKNOWN"),
            markdown_content=ocr_result.get("markdown_content", ""),
            original_file=file_path or "",
            ocr_provider=ocr_result.get("provider_used", "unknown"),
            ocr_confidence=ocr_result.get("confidence", 0.0),
            user_id=confirmer_name,
            explicit_version=ocr_detected_version,
        )

        if result["success"]:
            audit_log.create_record(
                action="document_version_updated",
                document_id=doc_info.get("doc_id"),
                user_id=confirmer_name,
                details={
                    "previous_version": result["previous_version"],
                    "new_version": result["version"],
                    "file_hash": calculate_file_hash(file_path) if file_path else "",
                    "confirmed_by": confirmer_name,
                    "stamps_confirmed": ["主管審核簽章", "品保確認蓋章"],
                    "ocr_provider": ocr_result.get("provider_used"),
                },
            )

            msg = (
                t(
                    "version.complete",
                    doc_id=doc_info.get("doc_id"),
                    old_ver=result["previous_version"],
                    new_ver=result["version"],
                    confirmer=confirmer_name,
                )
                + "\n"
            )

            # Cross-reference check
            try:
                current_doc_id = doc_info.get("doc_id", "")
                ref_docs = storage_manager.find_referencing_documents(current_doc_id)
                if ref_docs:
                    # Store in session for later export
                    cl.user_session.set(
                        "last_reference_result",
                        {
                            "doc_id": current_doc_id,
                            "ref_docs": ref_docs,
                        },
                    )
                    ref_list = "\n".join(
                        [
                            f"  - {r['doc_id']} ({r['title']}) - {r['doc_type']} v{r['current_version']}"
                            for r in ref_docs
                        ]
                    )
                    msg += f"\n{t('version.ref_warning')}\n{ref_list}"
                    msg += f"\n\n{t('version.ref_export_hint')}"
            except Exception:
                pass

            await cl.Message(content=msg).send()

            # --- LLM Version Diff Analysis ---
            try:
                previous_version = result["previous_version"]
                new_version = result["version"]
                doc_id = doc_info.get("doc_id", "")
                new_content = ocr_result.get("markdown_content", "")

                # Fetch old version content
                old_doc = storage_manager.get_document(doc_id, version=previous_version)
                old_content = (
                    old_doc.get("content", "") if old_doc.get("success") else ""
                )

                if old_content and new_content:
                    # Truncate to avoid token overflow
                    max_chars = 6000
                    old_truncated = old_content[:max_chars] + (
                        "..." if len(old_content) > max_chars else ""
                    )
                    new_truncated = new_content[:max_chars] + (
                        "..." if len(new_content) > max_chars else ""
                    )

                    diff_msg = cl.Message(content=t("version.diff_analyzing"))
                    await diff_msg.send()

                    provider_id = cl.user_session.get("provider_id", "ollama")
                    api_key_val = cl.user_session.get("api_key", "").strip()
                    model_name = cl.user_session.get("model_name", "")

                    setup_api_key(provider_id, api_key_val)
                    manager = create_provider_manager(provider_id)

                    diff_prompt = t(
                        "version.diff_prompt",
                        old_ver=previous_version,
                        new_ver=new_version,
                        old_content=old_truncated,
                        new_content=new_truncated,
                    )

                    diff_response = await asyncio.to_thread(
                        lambda: manager.completion(
                            messages=[{"role": "user", "content": diff_prompt}],
                            model=model_name,
                            temperature=0.3,
                            max_tokens=2000,
                            stream=False,
                            timeout=60,
                        )
                    )

                    diff_text = ""
                    if hasattr(diff_response, "choices") and diff_response.choices:
                        diff_text = diff_response.choices[0].message.content or ""

                    if diff_text:
                        diff_msg.content = (
                            t(
                                "version.diff_header",
                                old_ver=previous_version,
                                new_ver=new_version,
                            )
                            + diff_text
                        )
                    else:
                        diff_msg.content = (
                            t(
                                "version.diff_header",
                                old_ver=previous_version,
                                new_ver=new_version,
                            )
                            + "N/A"
                        )
                    await diff_msg.update()
            except Exception as diff_err:
                try:
                    await cl.Message(
                        content=t("version.diff_error", error=str(diff_err))
                    ).send()
                except Exception:
                    pass

        else:
            await cl.Message(
                content=t("version.save_failed", error=result.get("error"))
            ).send()

    except Exception as e:
        await cl.Message(content=t("version.process_failed", error=str(e))).send()

    # Clear state
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)


@cl.action_callback("cancel_stamps")
async def on_cancel_stamps(action):
    """Cancel stamp confirmation"""
    await action.remove()
    await cl.Message(content=t("stamp.cancelled")).send()


@cl.action_callback("cancel_version_update")
async def on_cancel_version_update(action):
    """Cancel version update"""
    await action.remove()
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)
    cl.user_session.set("awaiting_confirmer_name", False)
    await cl.Message(content=t("version.cancelled")).send()


# ============================================================
# LLM Chat with Markdown DB Context
# ============================================================


async def chat_with_llm(message_text: str, profile: str):
    """Send message to LLM with Markdown DB context and stream response"""
    provider_id = cl.user_session.get("provider_id", "ollama")
    model_name = cl.user_session.get("model_name", "default")
    api_key = cl.user_session.get("api_key", "").strip()

    setup_api_key(provider_id, api_key)

    try:
        manager = create_provider_manager(provider_id)
        # Disable fallback chain when user explicitly selected a provider
        if provider_id != "ollama":
            manager.disable_fallback = True
    except Exception as e:
        await cl.Message(content=t("error.llm_init", error=str(e))).send()
        return

    # Search Markdown DB for context
    db_context = ""
    ref_docs = []
    try:
        md_service = MarkdownStoreService()
        search_results = md_service.search(message_text, limit=3)
        if search_results:
            context_parts = []
            for r in search_results:
                doc_data = md_service.get_document(r["doc_id"])
                if doc_data.get("success"):
                    content = doc_data["content"]
                    if len(content) > 2000:
                        content = content[:2000] + "..."
                    context_parts.append(
                        f"{t('llm.doc_label', doc_id=r['doc_id'], title=r['title'])}\n{content}"
                    )
                    ref_docs.append(r["doc_id"])
            if context_parts:
                db_context = t("llm.db_context_header") + "\n\n---\n\n".join(
                    context_parts
                )
    except Exception:
        pass

    # Build system prompt
    lang = cl.user_session.get("language", "zh-TW")
    system_prompt = get_system_prompt(profile, lang)
    if db_context:
        system_prompt += db_context
        system_prompt += t("llm.answer_from_docs")
    else:
        system_prompt += t("llm.no_docs_context")

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    # Add history
    history = cl.user_session.get("message_history", [])
    for h in history[-10:]:  # Last 10 messages for context
        messages.append(h)

    messages.append({"role": "user", "content": message_text})

    # Stream response
    msg = cl.Message(content="")
    await msg.send()

    try:
        response = manager.completion(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=2000,
            stream=True,
            timeout=30,
        )

        full_response = ""
        for chunk in response:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    full_response += delta.content
                    await msg.stream_token(delta.content)

        if not full_response:
            full_response = t("error.no_response")
            msg.content = full_response
            await msg.update()

        if ref_docs:
            ref_str = ", ".join(ref_docs)
            # Only append if LLM didn't already cite these docs
            if ref_str not in full_response:
                full_response += "\n\n" + t("llm.ref_docs", docs=ref_str)
                msg.content = full_response
                await msg.update()

        # Update history
        history.append({"role": "user", "content": message_text})
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", history)

    except Exception as e:
        error_detail = str(e) if str(e) else repr(e)
        error_type = type(e).__name__

        error_lower = error_detail.lower()
        if "not found" in error_lower or "does not exist" in error_lower:
            hint = t("error.model_not_found")
        elif "connection" in error_lower or "connect" in error_lower:
            hint = t("error.connection")
        elif "api_key" in error_lower or "apikey" in error_lower:
            hint = t("error.api_key")
        elif "timeout" in error_lower:
            hint = t("error.timeout")
        else:
            hint = t("error.generic")

        msg.content = t(
            "error.llm_problem",
            error_type=error_type,
            error_detail=error_detail,
            hint=hint,
        )
        await msg.update()


# ============================================================
# Web Search + LLM Chat
# ============================================================


def _web_source_priority(url: str) -> int:
    """Return sort priority for a URL (lower = higher priority).

    Tier 0 – International standards bodies & regulatory authorities (ALL countries)
    Tier 1 – Government domains (.gov, .go.*, .gouv.*, etc.)
    Tier 2 – Academic / educational (.edu, .ac.*)
    Tier 3 – Certification bodies, standards orgs, academic publishers, industry bodies
    Tier 4 – Normal results (news, blogs, commercial)
    Tier 9 – Wikipedia / wiki sites (user-editable, not authoritative)
    """
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return 4

    host = host.lower()

    # --- Tier 9: Wikipedia and similar user-editable wikis ---
    if "wikipedia.org" in host or "wikimedia.org" in host or "wikidata.org" in host:
        return 9

    # --- Tier 0: International standards & regulatory bodies (ALL countries) ---
    tier0_domains = (
        # ── International / Supranational ──
        "iso.org",  # International Organization for Standardization
        "iec.ch",  # International Electrotechnical Commission
        "who.int",  # World Health Organization
        "trialsearch.who.int",  # WHO ICTRP (International Clinical Trials Registry)
        "ich.org",  # International Council for Harmonisation
        "imdrf.org",  # International Medical Device Regulators Forum
        "clinicaltrials.gov",  # US NIH Clinical Trials Registry
        # ── Pharmacopeias ──
        "usp.org",  # United States Pharmacopeia (USP)
        "edqm.eu",  # European Pharmacopoeia (EDQM)
        "jpdb.nihs.go.jp",  # Japanese Pharmacopoeia Database
        "pharmacopoeia.ru",  # Russian Pharmacopoeia
        # ── Americas ──
        "fda.gov",  # US FDA (matches *.fda.gov including accessdata.fda.gov)
        "accessdata.fda.gov",  # US FDA databases (MAUDE, 510k, PMA, standards)
        "ecfr.gov",  # US Electronic Code of Federal Regulations (21 CFR)
        "federalregister.gov",  # US Federal Register
        "health.canada.ca",  # Health Canada
        "canada.ca",  # Government of Canada portal
        "medical-devices.canada.ca",  # Health Canada Medical Devices DB
        "anvisa.gov.br",  # Brazil ANVISA
        "consultas.anvisa.gov.br",  # Brazil ANVISA product databases
        "invima.gov.co",  # Colombia INVIMA
        "cecmed.cu",  # Cuba CECMED
        # ── Europe ──
        "ema.europa.eu",  # European Medicines Agency
        "ec.europa.eu",  # European Commission (MDCG, NANDO)
        "eur-lex.europa.eu",  # EUR-Lex (EU regulations, directives: MDR, IVDR)
        "eudamed.eu",  # EUDAMED (EU medical device database)
        "mhra.gov.uk",  # UK MHRA
        "legislation.gov.uk",  # UK legislation database
        "info.mhra.gov.uk",  # UK MHRA device/drug databases
        "swissmedic.ch",  # Switzerland Swissmedic
        "ansm.sante.fr",  # France ANSM
        "base-donnees-publique.medicaments.gouv.fr",  # France public drug DB
        "bfarm.de",  # Germany BfArM
        "pei.de",  # Germany PEI
        "dimdi.de",  # Germany DIMDI (medical devices info)
        "aifa.gov.it",  # Italy AIFA
        "aemps.gob.es",  # Spain AEMPS
        "cima.aemps.es",  # Spain CIMA drug/device DB
        "basg.gv.at",  # Austria BASG
        "famhp.be",  # Belgium FAMHP
        "halmed.hr",  # Croatia HALMED
        "sukl.cz",  # Czechia SUKL
        "laegemiddelstyrelsen.dk",  # Denmark DKMA
        "fimea.fi",  # Finland Fimea
        "hpra.ie",  # Ireland HPRA
        "cbg-meb.nl",  # Netherlands CBG-MEB
        "igj.nl",  # Netherlands IGJ
        "dmp.no",  # Norway NMPA
        "infarmed.pt",  # Portugal INFARMED
        "anm.ro",  # Romania ANMDMR
        "jazmp.si",  # Slovenia JAZMP
        "lakemedelsverket.se",  # Sweden MPA
        "ravimiamet.ee",  # Estonia SAM
        "eof.gr",  # Greece EOF
        "sukl.sk",  # Slovakia SUKL
        "bda.bg",  # Bulgaria BDA
        "llv.li",  # Liechtenstein
        # ── Asia-Pacific ──
        "pmda.go.jp",  # Japan PMDA
        "mhlw.go.jp",  # Japan MHLW
        "std.pmda.go.jp",  # Japan PMDA standards/criteria database
        "elaws.e-gov.go.jp",  # Japan e-Gov legislation database
        "nmpa.gov.cn",  # China NMPA
        "samr.gov.cn",  # China SAMR (standards administration)
        "openstd.samr.gov.cn",  # China national standards (GB/T) database
        "mfds.go.kr",  # Korea MFDS
        "law.go.kr",  # Korea legislation database
        "nedrug.mfds.go.kr",  # Korea MFDS drug/device information DB
        "fda.gov.tw",  # Taiwan TFDA
        "mohw.gov.tw",  # Taiwan MOHW
        "law.moj.gov.tw",  # Taiwan laws & regulations database
        "bsmi.gov.tw",  # Taiwan BSMI (CNS standards)
        "cnsonline.com.tw",  # Taiwan CNS Online standards database
        "mdlicense.itri.org.tw",  # Taiwan TFDA medical device DB (ITRI)
        "hsa.gov.sg",  # Singapore HSA
        "sso.agc.gov.sg",  # Singapore Statutes Online
        "eservice.hsa.gov.sg",  # Singapore HSA device/drug database
        "cdsco.gov.in",  # India CDSCO
        "cdscoonline.gov.in",  # India CDSCO online portal/databases
        "fda.moph.go.th",  # Thailand Thai FDA
        "privus.fda.moph.go.th",  # Thailand FDA product databases
        "pom.go.id",  # Indonesia BPOM
        "cekbpom.pom.go.id",  # Indonesia BPOM product check database
        "mda.gov.my",  # Malaysia MDA
        "quest3plus.mda.gov.my",  # Malaysia MDA device registration DB
        "fda.gov.ph",  # Philippines FDA
        "verification.fda.gov.ph",  # Philippines FDA verification portal
        "moh.gov.vn",  # Vietnam MOH
        "drap.gov.pk",  # Pakistan DRAP
        "mdd.gov.hk",  # Hong Kong MDD
        "eservice.mdd.gov.hk",  # Hong Kong MDD device listing
        # ── Oceania ──
        "tga.gov.au",  # Australia TGA
        "legislation.gov.au",  # Australia legislation database
        "artg.tga.gov.au",  # Australia ARTG (device/drug register)
        "medsafe.govt.nz",  # New Zealand Medsafe
        "wand.medsafe.govt.nz",  # NZ WAND database (medical devices)
        # ── Middle East & Africa ──
        "sfda.gov.sa",  # Saudi Arabia SFDA
        "mdma.sfda.gov.sa",  # Saudi SFDA medical device database
        "mohap.gov.ae",  # UAE MOHAP
        "health.gov.il",  # Israel MOH
        "sahpra.org.za",  # South Africa SAHPRA
        "edaegypt.gov.eg",  # Egypt EDA
        "nafdac.gov.ng",  # Nigeria NAFDAC
        "fdaghana.gov.gh",  # Ghana FDA
        "efda.gov.et",  # Ethiopia EFDA
        "tmda.go.tz",  # Tanzania TMDA
        "pharmacyboardkenya.org",  # Kenya PPB
        "jfda.jo",  # Jordan JFDA
    )
    for d in tier0_domains:
        if host == d or host.endswith("." + d):
            return 0

    # --- Tier 1: Government domains (catch-all pattern) ---
    gov_patterns = (
        ".gov",  # US, many countries (.gov.xx)
        ".gov.",  # .gov.tw, .gov.uk, etc.
        ".go.",  # .go.jp, .go.kr, .go.th, .go.id
        ".gob.",  # Spanish-speaking (.gob.mx, .gob.es)
        ".gouv.",  # French-speaking (.gouv.fr)
        ".gc.ca",  # Canada government
        ".govt.",  # .govt.nz
        ".mil",  # Military
        ".gv.",  # Austria (.gv.at)
        ".gub.",  # Uruguay (.gub.uy)
        ".government.",  # Some African nations
    )
    for p in gov_patterns:
        if p in host:
            return 1

    # --- Tier 2: Academic / educational (pattern matching) ---
    edu_patterns = (
        ".edu",  # US universities
        ".edu.",  # .edu.tw, .edu.au, etc.
        ".ac.",  # .ac.uk, .ac.jp, .ac.kr
        ".uni-",  # German universities (uni-muenchen.de)
        ".univ-",  # French universities
    )
    for p in edu_patterns:
        if p in host:
            return 2

    # --- Tier 3: Certification bodies, standards orgs, publishers, industry ---
    tier3_domains = (
        # ── Testing Labs & Notified Bodies ──
        "tuvsud.com",  # TÜV SÜD
        "tuv.com",  # TÜV Rheinland
        "tuev-nord.de",  # TÜV NORD
        "sgs.com",  # SGS
        "bsigroup.com",  # BSI Group
        "ul.com",  # UL (Underwriters Laboratories)
        "intertek.com",  # Intertek
        "dekra.com",  # DEKRA
        "dnv.com",  # DNV
        "bureauveritas.com",  # Bureau Veritas
        "eurofins.com",  # Eurofins Scientific
        "lrqa.com",  # LRQA
        "csagroup.org",  # CSA Group
        "nsf.org",  # NSF International
        "nelsonlabs.com",  # Nelson Labs
        "namsa.com",  # NAMSA
        "wuxiapptec.com",  # WuXi AppTec
        "toxikon.com",  # Toxikon
        "pacificbiolabs.com",  # Pacific BioLabs
        "battelle.org",  # Battelle
        "applus.com",  # Applus+
        "qima.com",  # QIMA
        # ── Standards Bodies ──
        "astm.org",  # ASTM International
        "asme.org",  # ASME
        "ieee.org",  # IEEE
        "ieeexplore.ieee.org",  # IEEE Xplore
        "ansi.org",  # ANSI
        "din.de",  # DIN (Germany)
        "afnor.org",  # AFNOR (France)
        "jsa.or.jp",  # JSA (Japan)
        "cen.eu",  # CEN (European)
        "cenelec.eu",  # CENELEC (European)
        "aami.org",  # AAMI (medical instrumentation)
        "bsmi.gov.tw",  # BSMI (Taiwan CNS standards)
        # ── Industry Associations ──
        "advamed.org",  # AdvaMed
        "medtecheurope.org",  # MedTech Europe
        "gmdnagency.org",  # GMDN Agency
        "team-nb.org",  # Team-NB (EU Notified Bodies)
        # ── Academic Publishers & Databases ──
        "pubmed.ncbi.nlm.nih.gov",  # PubMed (also matches Tier 1 via .gov — OK)
        "scholar.google.com",  # Google Scholar
        "cochranelibrary.com",  # Cochrane Library
        "arxiv.org",  # arXiv
        "biorxiv.org",  # bioRxiv
        "medrxiv.org",  # medRxiv
        "webofscience.com",  # Web of Science
        "scopus.com",  # Scopus
        "embase.com",  # EMBASE
        "springer.com",  # Springer
        "link.springer.com",  # Springer Link
        "nature.com",  # Nature
        "elsevier.com",  # Elsevier
        "sciencedirect.com",  # ScienceDirect
        "cell.com",  # Cell Press
        "thelancet.com",  # The Lancet
        "bmj.com",  # BMJ
        "wiley.com",  # Wiley
        "onlinelibrary.wiley.com",  # Wiley Online Library
        "tandfonline.com",  # Taylor & Francis Online
        "taylorandfrancis.com",  # Taylor & Francis
        "mdpi.com",  # MDPI
        "frontiersin.org",  # Frontiers
        "plos.org",  # PLOS
        "academic.oup.com",  # Oxford Academic
        "cambridge.org",  # Cambridge University Press
        "sagepub.com",  # SAGE Publishing
        "lww.com",  # Wolters Kluwer / Lippincott
        "wolterskluwer.com",  # Wolters Kluwer
        "jamanetwork.com",  # JAMA Network
        "nejm.org",  # NEJM
        "science.org",  # AAAS Science
    )
    for d in tier3_domains:
        if host == d or host.endswith("." + d):
            return 3

    # --- Tier 4: Everything else ---
    return 4


def _web_tier_label(tier: int) -> str:
    """Return a human-readable tier label with icon for display."""
    labels = {
        0: "🏛️ Official Standard/Regulatory",
        1: "🏛️ Government",
        2: "🎓 Academic",
        3: "✅ Certification/Industry Body",
        4: "🌐 General",
        9: "⬇️ Wikipedia",
    }
    return labels.get(tier, "🌐 General")


def _detect_regulatory_sites(query: str) -> list:
    """Detect regulatory body mentions in query and return site: domains to search."""
    q = query.lower()
    # Ordered: more specific keywords first to avoid false matches
    site_map = [
        # ── Taiwan TFDA (before generic 'fda') ──
        ("tfda", "fda.gov.tw"),
        ("食藥署", "fda.gov.tw"),
        ("衛福部", "mohw.gov.tw"),
        ("台灣 fda", "fda.gov.tw"),
        ("taiwan fda", "fda.gov.tw"),
        # ── US FDA ──
        ("fda", "fda.gov"),
        ("fda", "accessdata.fda.gov"),  # FDA recognized consensus standards DB
        # ── EU ──
        ("ema", "ema.europa.eu"),
        ("ce marking", "ec.europa.eu"),
        ("eu mdr", "ec.europa.eu"),
        ("eu ivdr", "ec.europa.eu"),
        # ── Japan ──
        ("pmda", "pmda.go.jp"),
        ("厚生労働省", "mhlw.go.jp"),
        ("厚労省", "pmda.go.jp"),
        # ── China ──
        ("nmpa", "nmpa.gov.cn"),
        ("药监局", "nmpa.gov.cn"),
        ("藥監局", "nmpa.gov.cn"),
        ("cfda", "nmpa.gov.cn"),
        # ── Korea ──
        ("mfds", "mfds.go.kr"),
        ("식약처", "mfds.go.kr"),
        # ── UK ──
        ("mhra", "mhra.gov.uk"),
        # ── Australia ──
        ("tga", "tga.gov.au"),
        # ── Canada ──
        ("health canada", "canada.ca"),
        # ── Brazil ──
        ("anvisa", "anvisa.gov.br"),
        # ── India ──
        ("cdsco", "cdsco.gov.in"),
        # ── Thailand ──
        ("thai fda", "fda.moph.go.th"),
        # ── Indonesia ──
        ("bpom", "pom.go.id"),
        # ── Malaysia ──
        ("mda malaysia", "mda.gov.my"),
        # ── Singapore ──
        ("hsa", "hsa.gov.sg"),
        # ── Saudi Arabia ──
        ("sfda", "sfda.gov.sa"),
        # ── South Africa ──
        ("sahpra", "sahpra.org.za"),
        # ── Switzerland ──
        ("swissmedic", "swissmedic.ch"),
        # ── International standards ──
        ("iso ", "iso.org"),
        ("iso:", "iso.org"),
        ("iso ", "accessdata.fda.gov"),  # FDA recognized consensus standards
        ("iec ", "iec.ch"),
        ("iec:", "iec.ch"),
        ("iec ", "accessdata.fda.gov"),  # FDA recognized consensus standards
        ("who", "who.int"),
        ("ich ", "ich.org"),
        # ── EU regulatory databases ──
        ("eu mdr", "eur-lex.europa.eu"),
        ("eu ivdr", "eur-lex.europa.eu"),
        # ── Taiwan ──
        ("cns ", "bsmi.gov.tw"),
        ("cns:", "bsmi.gov.tw"),
        ("台灣", "mdlicense.itri.org.tw"),
        ("tfda", "mdlicense.itri.org.tw"),
        ("醫療器材", "mdlicense.itri.org.tw"),
        # ── Japan PMDA databases ──
        ("pmda", "std.pmda.go.jp"),  # PMDA standards/criteria DB
        ("日本", "std.pmda.go.jp"),
        ("jis ", "std.pmda.go.jp"),
        # ── China ──
        ("gb/t", "openstd.samr.gov.cn"),
        ("gb ", "openstd.samr.gov.cn"),
        ("国标", "openstd.samr.gov.cn"),
        # ── Korea ──
        ("ks ", "nedrug.mfds.go.kr"),
        ("한국", "nedrug.mfds.go.kr"),
        # ── Australia ──
        ("artg", "artg.tga.gov.au"),
        ("tga", "artg.tga.gov.au"),
    ]
    sites = []
    for keyword, domain in site_map:
        if keyword in q and domain not in sites:
            sites.append(domain)
    return sites


def _web_search_sync(query: str, max_results: int = 10) -> list:
    """Synchronous web search using DuckDuckGo (runs in thread).

    Strategy: English-first search with supplementary queries for standards.
    Deduplicates by both URL (normalised) and title similarity.
    Returns at most ~30 high-quality results sorted by credibility tier.
    """
    import re as _re
    from urllib.parse import urlparse

    # --- Tier quotas (max results to keep per tier) ---
    _TIER_QUOTA = {0: 15, 1: 10, 2: 8, 3: 8, 4: 5, 9: 2}
    _DEFAULT_QUOTA = 3

    def _norm_url(url: str) -> str:
        """Normalise URL for dedup: strip scheme, trailing slash, www., query."""
        try:
            p = urlparse(url)
            host = p.netloc.lower().lstrip("www.")
            path = p.path.rstrip("/")
            return f"{host}{path}"
        except Exception:
            return url.lower().rstrip("/")

    def _norm_title(title: str) -> str:
        """Normalise title for dedup: lowercase, strip non-alnum."""
        return _re.sub(r"[^a-z0-9]", "", title.lower())

    seen_urls: set = set()
    seen_titles: set = set()

    def _add(results, seen, seen_t, merged):
        for r in results:
            url = r.get("href", r.get("link", ""))
            title = r.get("title", "")
            if not url:
                continue
            nurl = _norm_url(url)
            ntitle = _norm_title(title)
            # Skip if URL or title already seen (avoids near-duplicate pages)
            if nurl in seen:
                continue
            if ntitle and ntitle in seen_t:
                continue
            seen.add(nurl)
            if ntitle:
                seen_t.add(ntitle)
            merged.append(r)

    try:
        merged: list = []

        with DDGS() as ddgs:
            # --- 1. Primary search: English (priority, 15 results) ---
            try:
                _add(
                    list(ddgs.text(query, region="us-en", max_results=15)),
                    seen_urls,
                    seen_titles,
                    merged,
                )
            except Exception:
                pass

            # --- 2. Secondary search: worldwide (only for non-ASCII, 10 results) ---
            is_ascii_only = all(ord(c) < 128 for c in query if c.strip())
            if not is_ascii_only:
                try:
                    _add(
                        list(ddgs.text(query, region="wt-wt", max_results=10)),
                        seen_urls,
                        seen_titles,
                        merged,
                    )
                except Exception:
                    pass

            # --- 3. English supplementary search (for CJK queries with standards) ---
            _std_match = _re.search(
                r"(?:iso|iec|astm|en|cns|gb[/ ]?t?)\s*(\d{4,6}(?:[- :/.]\d+)?)",
                query.lower(),
            )
            if _std_match:
                std_num = _std_match.group(0).strip().upper()
                extra_queries = [
                    f"{std_num} latest version current edition",
                    f"FDA recognized consensus standard {std_num}",
                ]
                if not is_ascii_only:
                    extra_queries.insert(1, f"{std_num} medical device standard")
                for extra_q in extra_queries:
                    try:
                        _add(
                            list(ddgs.text(extra_q, region="us-en", max_results=8)),
                            seen_urls,
                            seen_titles,
                            merged,
                        )
                    except Exception:
                        pass

            # --- 4. Targeted site: searches for regulatory domains ---
            reg_sites = _detect_regulatory_sites(query)
            for site_domain in reg_sites[:5]:
                try:
                    _add(
                        list(
                            ddgs.text(
                                f"site:{site_domain} {query}",
                                region="wt-wt",
                                max_results=3,
                            )
                        ),
                        seen_urls,
                        seen_titles,
                        merged,
                    )
                except Exception:
                    pass

            # --- 5. Keyword variation (limited, English-first) ---
            q_lower = query.lower()
            _variants = []
            if any(k in q_lower for k in ["版本", "version", "バージョン", "버전"]):
                _variants.append(f"{query} revision history changelog")
            if any(k in q_lower for k in ["fda", "美國", "us "]):
                _variants.append(f"{query} 21 CFR regulatory guidance")
            if any(k in q_lower for k in ["台灣", "taiwan", "tfda"]):
                _variants.append(f"{query} CNS 標準 台灣法規")
            if any(k in q_lower for k in ["醫療器材", "medical device", "医疗器械"]):
                _variants.append(f"{query} medical device regulation")
            for vq in _variants[:2]:
                try:
                    _add(
                        list(ddgs.text(vq, region="us-en", max_results=5)),
                        seen_urls,
                        seen_titles,
                        merged,
                    )
                except Exception:
                    pass

        # --- Apply tier-based quotas ---
        tier_buckets: dict = {}
        for r in merged:
            url = r.get("href", r.get("link", ""))
            tier = _web_source_priority(url)
            r["_tier"] = tier
            tier_buckets.setdefault(tier, []).append(r)

        filtered: list = []
        for tier in sorted(tier_buckets.keys()):
            quota = _TIER_QUOTA.get(tier, _DEFAULT_QUOTA)
            filtered.extend(tier_buckets[tier][:quota])

        # Sort by credibility (lower tier = higher priority)
        filtered.sort(key=lambda r: r.get("_tier", 4))

        return filtered

    except Exception as e:
        print(f"[WARN] DuckDuckGo search failed: {e}")
        return []


async def chat_with_llm_web(message_text: str, profile: str):
    """Send message to LLM with web search results + Markdown DB context and stream response.

    This function is triggered by the /web command prefix. It:
    1. Searches the web using DuckDuckGo
    2. Also searches the local Markdown DB
    3. Combines both as context for the LLM
    4. Streams the response
    """
    provider_id = cl.user_session.get("provider_id", "ollama")
    model_name = cl.user_session.get("model_name", "default")
    api_key = cl.user_session.get("api_key", "").strip()

    setup_api_key(provider_id, api_key)

    try:
        manager = create_provider_manager(provider_id)
        if provider_id != "ollama":
            manager.disable_fallback = True
    except Exception as e:
        await cl.Message(content=t("error.llm_init", error=str(e))).send()
        return

    # --- Step 1: Web Search ---
    web_context = ""
    web_sources = []

    if not DDGS_AVAILABLE:
        await cl.Message(
            content="⚠️ duckduckgo-search not installed. Run: `pip install duckduckgo-search`"
        ).send()
        # Fall back to regular chat
        await chat_with_llm(message_text, profile)
        return

    search_msg = cl.Message(content=t("web.searching"))
    await search_msg.send()

    try:
        web_results = await asyncio.to_thread(_web_search_sync, message_text)
        if web_results:
            # --- Build LLM context from top 20 results (quality over quantity) ---
            _llm_max = min(20, len(web_results))
            web_parts = []
            for i, r in enumerate(web_results[:_llm_max], 1):
                title = r.get("title", "")
                url = r.get("href", r.get("link", ""))
                snippet = r.get("body", r.get("snippet", ""))
                tier = r.get("_tier", _web_source_priority(url))
                tier_label = _web_tier_label(tier)
                web_parts.append(
                    f"{i}. [{tier_label}] **{title}**\n   URL: {url}\n   {snippet}"
                )

            web_context = t("web.results_header") + "\n\n".join(web_parts)

            # --- Build UI display list (top 10, deduplicated) ---
            _display_max = 10
            _seen_display: set = set()
            for r in web_results:
                if len(web_sources) >= _display_max:
                    break
                title = r.get("title", "")
                url = r.get("href", r.get("link", ""))
                # Skip entries with empty or duplicate titles
                short_title = title[:80].strip()
                if not short_title:
                    continue
                if short_title in _seen_display:
                    continue
                _seen_display.add(short_title)
                tier = r.get("_tier", _web_source_priority(url))
                tier_label = _web_tier_label(tier)
                # Sanitise title for Markdown link (escape brackets)
                safe_title = short_title.replace("[", "\\[").replace("]", "\\]")
                web_sources.append(f"{tier_label} [{safe_title}]({url})")

            search_msg.content = (
                f"🌐 {t('web.source_label')}: {len(web_sources)} results\n"
                + "\n".join(web_sources)
            )
            await search_msg.update()
        else:
            search_msg.content = t("web.no_results")
            await search_msg.update()
    except Exception as e:
        search_msg.content = t("web.error", error=str(e))
        await search_msg.update()

    # --- Step 2: Search Markdown DB for context (same as chat_with_llm) ---
    db_context = ""
    ref_docs = []
    try:
        md_service = MarkdownStoreService()
        search_results = md_service.search(message_text, limit=3)
        if search_results:
            context_parts = []
            for r in search_results:
                doc_data = md_service.get_document(r["doc_id"])
                if doc_data.get("success"):
                    content = doc_data["content"]
                    if len(content) > 2000:
                        content = content[:2000] + "..."
                    context_parts.append(
                        f"{t('llm.doc_label', doc_id=r['doc_id'], title=r['title'])}\n{content}"
                    )
                    ref_docs.append(r["doc_id"])
            if context_parts:
                db_context = t("llm.db_context_header") + "\n\n---\n\n".join(
                    context_parts
                )
    except Exception:
        pass

    # --- Step 3: Build combined system prompt ---
    lang = cl.user_session.get("language", "zh-TW")
    system_prompt = get_system_prompt(profile, lang)

    # When web search is active, remove the "never display URLs" restriction
    # because we WANT the LLM to cite web sources
    if web_context:
        for no_url_phrase in [
            "重要：回覆中絕對不要顯示任何 URL 或網址。",
            "Important: Never display any URLs in your responses.",
            "重要：回答に URL やウェブアドレスを表示しないでください。",
            "重要：回复中绝对不要显示任何 URL 或网址。",
        ]:
            system_prompt = system_prompt.replace(no_url_phrase, "")

    if web_context:
        system_prompt += web_context
    if db_context:
        system_prompt += db_context
    if web_context:
        system_prompt += t("web.combined_context")
    elif db_context:
        system_prompt += t("llm.answer_from_docs")
    else:
        system_prompt += t("llm.no_docs_context")

    # --- Step 4: Build messages and stream ---
    messages = [{"role": "system", "content": system_prompt}]

    history = cl.user_session.get("message_history", [])
    for h in history[-10:]:
        messages.append(h)

    # Append version comparison reminder directly in user message
    # so lightweight LLMs don't miss it buried in system prompt
    user_content = message_text
    if web_context and db_context:
        user_content += "\n\n（請同時比對本地文件資料庫的版本與網路查到的最新版本，明確說明是否一致）"

    messages.append({"role": "user", "content": user_content})

    msg = cl.Message(content="")
    await msg.send()

    try:
        response = manager.completion(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=4000,
            stream=True,
            timeout=60,
        )

        full_response = ""
        for chunk in response:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    full_response += delta.content
                    await msg.stream_token(delta.content)

        if not full_response:
            full_response = t("error.no_response")
            msg.content = full_response
            await msg.update()

        # Add source citations (web sources already shown in search_msg)
        # Skip if LLM already cited these docs in its response
        citations = []
        if ref_docs:
            ref_str = ", ".join(ref_docs)
            citation_text = t("llm.ref_docs", docs=ref_str)
            # Only append if LLM didn't already include the doc IDs
            if ref_str not in full_response:
                citations.append(citation_text)

        if citations:
            full_response += "\n\n" + "\n".join(citations)
            msg.content = full_response
            await msg.update()

        # Update history
        history.append({"role": "user", "content": f"/web {message_text}"})
        history.append({"role": "assistant", "content": full_response})
        cl.user_session.set("message_history", history)

    except Exception as e:
        error_detail = str(e) if str(e) else repr(e)
        error_type = type(e).__name__

        error_lower = error_detail.lower()
        if "not found" in error_lower or "does not exist" in error_lower:
            hint = t("error.model_not_found")
        elif "connection" in error_lower or "connect" in error_lower:
            hint = t("error.connection")
        elif "api_key" in error_lower or "apikey" in error_lower:
            hint = t("error.api_key")
        elif "timeout" in error_lower:
            hint = t("error.timeout")
        else:
            hint = t("error.generic")

        msg.content = t(
            "error.llm_problem",
            error_type=error_type,
            error_detail=error_detail,
            hint=hint,
        )
        await msg.update()


# ============================================================
# Main Message Handler
# ============================================================


@cl.on_message
async def on_message(message: cl.Message):
    """Handle all incoming messages"""
    profile = cl.user_session.get("chat_profile")
    text = message.content.strip() if message.content else ""
    msg_lower = text.lower()

    # Check for file uploads (Doc Control profile)
    if message.elements and profile == "文件管制 (Doc Control)":
        file_elements = [el for el in message.elements if hasattr(el, "path")]
        if file_elements:
            await handle_file_upload(file_elements)
            return

    # Empty message
    if not text:
        return

    # ============================================================
    # Intercept: awaiting confirmer name for version update
    # ============================================================
    if cl.user_session.get("awaiting_confirmer_name"):
        cl.user_session.set("awaiting_confirmer_name", False)
        confirmer_name = text.strip()
        if not confirmer_name:
            await cl.Message(content=t("version.name_empty")).send()
            cl.user_session.set("awaiting_confirmer_name", True)
            return
        await _execute_version_update(confirmer_name)
        return

    # ============================================================
    # Command routing (both profiles) — i18n aware (20 languages)
    # ============================================================

    # Help
    if _match_cmd(text, "cmd.help") or _match_cmd_exact(text, "cmd.help"):
        response = await handle_help(profile)
        await cl.Message(content=response).send()
        return

    # Status
    if _match_cmd(text, "cmd.status") or _match_cmd_exact(text, "cmd.status"):
        response = await handle_status()
        await cl.Message(content=response).send()
        return

    # ============================================================
    # Suffix detection (used by all export commands below)
    # ============================================================
    text_lower_stripped = text.lower().strip()
    has_word_suffix = any(text_lower_stripped.endswith(s) for s in [" word", " docx"])
    has_excel_suffix = any(text_lower_stripped.endswith(s) for s in [" excel", " xlsx"])
    has_pdf_suffix = text_lower_stripped.endswith(" pdf")

    # --- Document list export (must check before document_list display) ---
    if _match_cmd(text, "cmd.download_doclist"):
        if has_word_suffix:
            filepath, msg_text = await handle_doclist_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_doclist_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        else:
            actions = [
                cl.Action(
                    name="download_doclist_word",
                    payload={"format": "word"},
                    label="📥 Word (.docx)",
                ),
                cl.Action(
                    name="download_doclist_excel",
                    payload={"format": "excel"},
                    label="📥 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content=t("export.doclist_prompt"),
                actions=actions,
            ).send()
        return

    # --- All records export (must check before list display) ---
    if _match_cmd(text, "cmd.download_allrecords"):
        if has_word_suffix:
            filepath, msg_text = await handle_allrecords_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_allrecords_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        else:
            actions = [
                cl.Action(
                    name="download_allrecords_word",
                    payload={"format": "word"},
                    label="📥 Word (.docx)",
                ),
                cl.Action(
                    name="download_allrecords_excel",
                    payload={"format": "excel"},
                    label="📥 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content=t("export.allrecords_prompt"),
                actions=actions,
            ).send()
        return

    # Document list — current formal versions only (must check before generic list)
    if _match_cmd(text, "cmd.document_list"):
        response = await handle_document_list()
        actions = [
            cl.Action(
                name="download_doclist_word",
                payload={"format": "word"},
                label="📥 Word (.docx)",
            ),
            cl.Action(
                name="download_doclist_excel",
                payload={"format": "excel"},
                label="📥 Excel (.xlsx)",
            ),
        ]
        await cl.Message(content=response, actions=actions).send()
        return

    # List — all records (active + obsolete + version history)
    if _match_cmd(text, "cmd.list") or _match_cmd_exact(text, "cmd.list"):
        response = await handle_list()
        actions = [
            cl.Action(
                name="download_allrecords_word",
                payload={"format": "word"},
                label="📥 Word (.docx)",
            ),
            cl.Action(
                name="download_allrecords_excel",
                payload={"format": "excel"},
                label="📥 Excel (.xlsx)",
            ),
        ]
        await cl.Message(content=response, actions=actions).send()
        return

    # Web Search: /web prefix → LLM Chat with Web + DB context
    # (must be checked BEFORE cmd.search to avoid "/web 搜尋..." matching "搜尋")
    if _match_cmd_startswith(text, "cmd.web"):
        query = _extract_after_cmd(text, "cmd.web")
        if query:
            await chat_with_llm_web(query, profile)
        else:
            await cl.Message(content=t("web.no_query")).send()
        return

    # Search (prefix command: "search keyword")
    if _match_cmd(text, "cmd.search"):
        query = _extract_after_cmd(text, "cmd.search")
        response = await handle_search(query)
        await cl.Message(content=response).send()
        return

    # ============================================================
    # Export / Download with Action Buttons
    # ============================================================

    # --- Audit export (must check before audit display) ---
    if _match_cmd(text, "cmd.download_audit"):
        if has_word_suffix:
            filepath, msg_text = await handle_audit_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_audit_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_pdf_suffix:
            _, msg_text = await handle_audit_export("pdf")
            await cl.Message(content=msg_text).send()
        else:
            actions = [
                cl.Action(
                    name="download_audit_word",
                    payload={"format": "word"},
                    label="📥 Word (.docx)",
                ),
                cl.Action(
                    name="download_audit_excel",
                    payload={"format": "excel"},
                    label="📥 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content=t("export.audit_prompt"),
                actions=actions,
            ).send()
        return

    # --- Regulatory export (must check before regulatory display) ---
    if _match_cmd(text, "cmd.download_regulatory"):
        if has_word_suffix:
            filepath, msg_text = await handle_regulatory_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_regulatory_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        else:
            actions = [
                cl.Action(
                    name="download_regulatory_word",
                    payload={"format": "word"},
                    label="📥 Word (.docx)",
                ),
                cl.Action(
                    name="download_regulatory_excel",
                    payload={"format": "excel"},
                    label="📥 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content=t("export.regulatory_prompt"),
                actions=actions,
            ).send()
        return

    # Regulatory standards list (display only)
    if _match_cmd(text, "cmd.regulatory"):
        response = await handle_regulatory_list()
        actions = [
            cl.Action(
                name="download_regulatory_word",
                payload={"format": "word"},
                label="📥 Word (.docx)",
            ),
            cl.Action(
                name="download_regulatory_excel",
                payload={"format": "excel"},
                label="📥 Excel (.xlsx)",
            ),
        ]
        await cl.Message(content=response, actions=actions).send()
        return

    # --- Reference export ---
    if _match_cmd(text, "cmd.download_reference"):
        if has_word_suffix:
            filepath, msg_text = await handle_reference_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_reference_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        else:
            actions = [
                cl.Action(
                    name="download_reference_word",
                    payload={"format": "word"},
                    label="📥 Word (.docx)",
                ),
                cl.Action(
                    name="download_reference_excel",
                    payload={"format": "excel"},
                    label="📥 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content=t("export.reference_prompt"),
                actions=actions,
            ).send()
        return

    # Audit records (display only)
    if _match_cmd(text, "cmd.audit"):
        response = await handle_audit()
        actions = [
            cl.Action(
                name="download_audit_word",
                payload={"format": "word"},
                label="📥 Word (.docx)",
            ),
            cl.Action(
                name="download_audit_excel",
                payload={"format": "excel"},
                label="📥 Excel (.xlsx)",
            ),
        ]
        await cl.Message(content=response, actions=actions).send()
        return

    # Obsolete (prefix command: "obsolete doc_id")
    if _match_cmd(text, "cmd.obsolete"):
        response = await handle_obsolete(text)
        await cl.Message(content=response).send()
        return

    # ============================================================
    # Doc Control specific commands
    # ============================================================
    if profile == "文件管制 (Doc Control)":
        # Download original file by doc_id (exclude audit/regulatory/reference)
        is_file_request = _match_cmd(text, "cmd.download_file")
        if (
            is_file_request
            and not _match_cmd(text, "cmd.download_audit")
            and not _match_cmd(text, "cmd.download_regulatory")
            and not _match_cmd(text, "cmd.download_reference")
            and not _match_cmd(text, "cmd.download_doclist")
            and not _match_cmd(text, "cmd.download_allrecords")
            and not _match_cmd(text, "cmd.audit")
            and not _match_cmd(text, "cmd.regulatory")
        ):
            filepath, msg_text = await handle_download(text)
            if filepath:
                fname = Path(filepath).name
                doc_id_match = re.search(
                    r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)", text, re.IGNORECASE
                )
                doc_id = doc_id_match.group(1).upper() if doc_id_match else ""
                actions = [
                    cl.Action(
                        name="download_original_file",
                        payload={"doc_id": doc_id},
                        label=f"📥 {fname}",
                    ),
                ]
                elements = [cl.File(name=fname, path=filepath, display="inline")]
                await cl.Message(
                    content=msg_text, elements=elements, actions=actions
                ).send()
            else:
                await cl.Message(content=msg_text).send()
            return

        # Delete database
        if _match_cmd(text, "cmd.delete_database"):
            await handle_delete_db()
            return

        # LLM test connection
        if _match_cmd(text, "cmd.test_connection"):
            provider_id = cl.user_session.get("provider_id", "ollama")
            model_name = cl.user_session.get("model_name", "default")
            api_key = cl.user_session.get("api_key", "")
            lang = cl.user_session.get("language", "zh-TW")
            result = test_llm_connection(provider_id, model_name, api_key, lang)
            await cl.Message(content=result).send()
            return

    # ============================================================
    # Main Agent specific commands
    # ============================================================
    if profile == "主系統 (Main Agent)":
        # Document management shortcut
        is_doc_command = (
            text.strip() in ["文件", "文件管制", "開啟文件", "上傳"]
            or "上傳" in text
            or ("文件管制" in text and len(text.strip()) <= 10)
        )
        if is_doc_command:
            await cl.Message(content=t("switch_to_doc_control")).send()
            return

        # LLM test connection
        if _match_cmd(text, "cmd.test_connection"):
            provider_id = cl.user_session.get("provider_id", "ollama")
            model_name = cl.user_session.get("model_name", "default")
            api_key = cl.user_session.get("api_key", "")
            lang = cl.user_session.get("language", "zh-TW")
            result = test_llm_connection(provider_id, model_name, api_key, lang)
            await cl.Message(content=result).send()
            return

    # ============================================================
    # Default: LLM Chat with Markdown DB context
    # ============================================================
    await chat_with_llm(text, profile)
