"""
AI-QMS Phase 1 - Chainlit Application
======================================

Version: v3.1.0
Updated: 2026-02-12

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

import chainlit as cl
from chainlit.input_widget import Select, TextInput

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
from src.ocr.vision_ocr import VisionOCRProcessor, process_document

# v3.1.0: Load cached model lists from previous sessions on startup.
# This ensures cloud provider models appear immediately without
# needing to re-enter API keys.
load_cached_models()


# ============================================================
# System Prompts
# ============================================================

MAIN_AGENT_SYSTEM_PROMPT = """你是 AI-QMS 品質管理系統的主要 AI 助理 (v3.1.0)。

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
- 「狀態」或「status」- 系統狀態

重要：回覆中絕對不要顯示任何 URL 或網址。
請根據文件資料庫內容回答問題。如果資料庫中沒有相關資訊，請明確告知，不要編造答案。"""

DOC_CONTROL_SYSTEM_PROMPT = """你是 AI-QMS 文件管制子系統的 AI 助理 (v3.0.0)。

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
- 「狀態」- 系統狀態
- 「刪除資料庫」- 刪除所有文件（需確認）

上傳文件：直接在對話框拖放或上傳文件即可開始 OCR 處理。

請根據文件資料庫內容回答問題。如果資料庫中沒有相關資訊，請明確告知，不要編造答案。"""


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
    title_from_filename = re.sub(
        r"^[A-Za-z]{2,4}[-_]?\d{2,4}(?:[-_]\d{1,2})?\s*", "", title_from_filename
    ).strip()
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
    """Check if PDF contains embedded images (stamps/signatures) on the first page.

    Stamps and signatures are embedded as images in PDFs.
    Unsigned documents have 0 images; stamped/signed documents have 1+ images.

    Returns:
        True if images found (likely stamped/signed)
        False if no images found (likely unsigned)
        None if check failed (can't determine)
    """
    try:
        import pypdf

        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            # Check first 3 pages for images
            for i, page in enumerate(reader.pages[:3]):
                try:
                    images = page.images
                    if len(list(images)) > 0:
                        return True
                except Exception:
                    continue
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


def detect_signature(ocr_result, file_path: str = "") -> dict:
    """Detect if document has signatures/stamps.

    Uses a two-phase approach:
    1. Check OCR metadata and text for stamp/signature indicators
    2. Cross-verify with raw PDF text extraction to catch LLM hallucinations

    Args:
        ocr_result: OCR processing result dict
        file_path: Path to original file for raw text cross-verification

    Returns a dict with:
        - detected (bool): True if real signatures/stamps found
        - stamps (list): List of detected stamp descriptions
        - signatures (list): List of detected signature descriptions
        - keyword_hits (list): Keyword matches found in text
        - reason (str): Human-readable explanation
    """
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
        "電子簽章",
        "數位簽章",
    ]

    for kw in presence_keywords:
        if kw in ocr_text:
            result["keyword_hits"].append(kw)

    general_keywords_found = []
    for kw in SIGNATURE_KEYWORDS:
        if kw in ocr_text:
            general_keywords_found.append(kw)

    # --- Phase 1 decision (from OCR) ---
    has_real_stamps = len(result["stamps"]) > 0
    has_real_sigs = len(result["signatures"]) > 0
    has_presence_keywords = len(result["keyword_hits"]) > 0
    ocr_says_signed = has_real_stamps or has_real_sigs or has_presence_keywords

    # --- Phase 2: Cross-verify with embedded image analysis ---
    # LLMs can hallucinate stamps/signatures. Verify by checking if the file
    # actually contains embedded images (stamps/signatures are images).
    # Also covers general_keywords (e.g. "approved by", "signature") which may
    # appear as table headers in unsigned documents.
    any_keywords_found = ocr_says_signed or len(general_keywords_found) > 0
    file_lower = file_path.lower() if file_path else ""
    if file_path and any_keywords_found:
        has_images = None
        file_type_label = ""
        if file_lower.endswith(".pdf"):
            has_images = _pdf_has_stamp_images(file_path)
            file_type_label = "PDF"
        elif file_lower.endswith(".docx"):
            has_images = _docx_has_stamp_images(file_path)
            file_type_label = "Word"
        if has_images is False:
            result["detected"] = False
            result["reason"] = (
                f"文件中偵測到簽章相關關鍵字，但 {file_type_label} 中未發現嵌入圖片"
                "（印章/簽名），判定為未簽署文件"
            )
            return result

    # --- Final decision ---
    if has_real_stamps or has_real_sigs:
        result["detected"] = True
        parts = []
        if result["stamps"]:
            parts.append(f"印章: {', '.join(result['stamps'])}")
        if result["signatures"]:
            parts.append(f"簽名: {', '.join(result['signatures'])}")
        result["reason"] = "偵測到 " + "; ".join(parts)
    elif has_presence_keywords:
        result["detected"] = True
        result["reason"] = (
            f"文字中偵測到簽章相關描述: {', '.join(result['keyword_hits'][:3])}"
        )
    elif general_keywords_found:
        has_placeholders = any(
            p in ocr_text
            for p in ["[無法辨識]", "[空白]", "[empty]", "[blank]", "[n/a]"]
        )
        if has_placeholders and not has_real_stamps and not has_real_sigs:
            result["detected"] = False
            result["reason"] = "偵測到簽章欄位但內容為空白或無法辨識"
        else:
            result["detected"] = True
            result["reason"] = (
                f"偵測到簽章相關關鍵字: {', '.join(general_keywords_found[:3])}"
            )
    else:
        result["detected"] = False
        result["reason"] = "未偵測到任何簽名或印章"

    return result


# ============================================================
# Chat Profiles
# ============================================================


@cl.set_chat_profiles
async def chat_profile():
    return [
        cl.ChatProfile(
            name="主系統 (Main Agent)",
            markdown_description="AI-QMS 品質管理系統主控台。文件列表、搜尋、作廢、文件更動紀錄、LLM 對話。",
            icon="/public/main_agent.svg",
        ),
        cl.ChatProfile(
            name="文件管制 (Doc Control)",
            markdown_description="文件上傳、OCR 處理、版本控制、簽章確認。拖放文件即可開始。",
            icon="/public/doc_control.svg",
        ),
    ]


# ============================================================
# Chat Settings (LLM Configuration)
# ============================================================


def build_chat_settings(
    current_provider_name: str | None = None,
    current_provider_id: str | None = None,
    current_api_key: str = "",
    current_model: str | None = None,
):
    """Build ChatSettings widgets for LLM configuration.

    Args:
        current_provider_name: Currently selected provider display name.
            If None, uses the first available provider.
        current_provider_id: Currently selected provider ID.
            If None, uses the first available provider.
        current_api_key: Current API key value.
        current_model: Currently selected model name.
            If provided and found in model list, preserves the selection.
    """
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

    return cl.ChatSettings(
        [
            Select(
                id="Provider",
                label="LLM 提供商",
                values=provider_names,
                initial_index=provider_index,
            ),
            Select(
                id="Model",
                label="模型",
                values=model_list,
                initial_index=model_index,
            ),
            TextInput(
                id="ApiKey",
                label="API Key (雲端服務需要)",
                initial=current_api_key,
                placeholder="輸入 API Key...",
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
    """
    provider_name = settings.get("Provider", "")
    provider_id = get_provider_id_from_display(provider_name)
    api_key = settings.get("ApiKey", "")
    selected_model = settings.get("Model", "default")

    # Update API key
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

    # v3.1.0: When API key is newly entered for a cloud provider,
    # fetch live model list and persist to cache
    if api_key_changed and not DEFAULT_PROVIDERS.get(provider_id, {}).get("is_local"):
        update_msg = cl.Message(
            content=f"🔄 正在從 {provider_name} 取得最新模型清單..."
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
                update_msg.content = (
                    f"📡 {provider_name} 模型清單已更新\n"
                    f"- 新增: {len(added)} 個模型\n"
                    f"- 移除: {len(removed)} 個已下架模型\n"
                    f"- 目前共 {model_count} 個可用模型\n"
                    f"- 模型清單已快取，下次啟動時自動載入"
                )
            else:
                update_msg.content = (
                    f"✅ {provider_name} 模型清單已是最新 "
                    f"({model_count} 個可用模型，已快取)"
                )
            await update_msg.update()
        except Exception as e:
            update_msg.content = f"⚠️ 模型清單更新失敗: {str(e)}（使用預設清單）"
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
        ).send()

        settings_msg = (
            f"⚙️ LLM 設定已更新\n"
            f"- 提供商: {provider_name}\n"
            f"- 模型: {active_model}\n"
            f"- 可用模型數: {len(new_models)}"
        )
        await cl.Message(content=settings_msg).send()

        # Auto-test LLM connection after provider change
        test_msg = cl.Message(content="🔄 正在測試 LLM 連線...")
        await test_msg.send()
        try:
            connection_result = await asyncio.to_thread(
                test_llm_connection, provider_id, active_model, api_key
            )
            test_msg.content = connection_result
            await test_msg.update()
        except Exception as e:
            test_msg.content = f"❌ 連線測試失敗: {str(e)}"
            await test_msg.update()
    else:
        cl.user_session.set("model_name", selected_model)
        settings_msg = (
            f"⚙️ LLM 設定已更新\n- 提供商: {provider_name}\n- 模型: {selected_model}"
        )
        await cl.Message(content=settings_msg).send()

        # Auto-test LLM connection after model change
        test_msg = cl.Message(content="🔄 正在測試 LLM 連線...")
        await test_msg.send()
        try:
            connection_result = await asyncio.to_thread(
                test_llm_connection, provider_id, selected_model, api_key
            )
            test_msg.content = connection_result
            await test_msg.update()
        except Exception as e:
            test_msg.content = f"❌ 連線測試失敗: {str(e)}"
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
        welcome = f"""📄 **AI-QMS 文件管制子系統**

歡迎使用文件管制系統！

📊 文件數量: {doc_count}/{doc_limit}

**操作方式：**
• **上傳文件** → 直接在對話框拖放或點擊上傳按鈕
• **文件清單** → 現行正式版本文件
• **列表** → 所有文件紀錄（含進版、作廢）
• **搜尋 關鍵字** → 搜尋文件內容
• **下載 文件編號** → 下載原始文件
• **作廢 文件編號** → 作廢文件
• **文件更動紀錄** → 查看操作紀錄
• **下載文件更動紀錄 word/excel** → 匯出紀錄
• **法規清單** → 列出所有引用的法規標準
• **下載法規清單 word/excel** → 匯出法規清單
• **刪除資料庫** → 刪除所有文件（需確認）
• **幫助** → 顯示完整指南

支援格式: PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""
    else:
        welcome = f"""🏥 **AI-QMS 品質管理系統**

您好！我是 AI-QMS 品質管理系統助理。

📊 文件數量: {doc_count}/{doc_limit}

**可用功能：**
• **文件清單** → 現行正式版本文件
• **列表** → 所有文件紀錄（含進版、作廢）
• **搜尋 關鍵字** → 搜尋文件內容
• **作廢 文件編號** → 作廢文件
• **文件更動紀錄** → 查看操作紀錄
• **下載文件更動紀錄 word/excel** → 匯出紀錄
• **法規清單** → 列出所有引用的法規標準
• **狀態** → 系統狀態
• **幫助** → 使用指南
• 直接提問 → AI 將搜尋文件資料庫後回答

💡 切換到「文件管制」Profile 可上傳文件進行 OCR 處理"""

    await cl.Message(content=welcome).send()


# ============================================================
# Command Handlers (shared between profiles)
# ============================================================


async def handle_help(profile: str) -> str:
    """Handle help command"""
    if profile == "文件管制 (Doc Control)":
        return """🤖 **文件管制使用指南**

**文件上傳：**
1. 在對話框拖放或上傳文件
2. 系統自動進行 OCR 處理
3. 偵測文件類型（新文件/進版）
4. 偵測簽章/印章
5. 自動存入 Markdown DB

**對話指令：**
- 「文件清單」- 現行正式版本文件
- 「列表」- 所有文件紀錄（含進版、作廢）
- 「搜尋 關鍵字」- 搜尋文件
- 「下載 文件編號」- 下載原始文件 (如: 下載 QP-852)
- 「作廢 文件編號」- 作廢文件 (如: 作廢 OTHER-016)
- 「文件更動紀錄」- 查看操作紀錄
- 「下載文件更動紀錄 word」- 匯出 Word 格式
- 「下載文件更動紀錄 excel」- 匯出 Excel 格式
- 「法規清單」- 列出所有引用的法規標準
- 「下載法規清單 word/excel」- 匯出法規清單
- 「下載引用清單 word/excel」- 匯出進版引用清單
- 「刪除資料庫」- 刪除所有文件
- 「狀態」- 系統狀態

**支援格式：** PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""
    else:
        return """🤖 **AI-QMS 助理使用指南**

**可用功能：**
1. 輸入「狀態」- 查看系統狀態
2. 輸入「文件清單」- 現行正式版本文件
3. 輸入「列表」- 所有文件紀錄（含進版、作廢）
4. 輸入「搜尋 關鍵字」- 搜尋文件內容
5. 輸入「作廢 文件編號」- 作廢文件 (如: 作廢 OTHER-016)
6. 輸入「文件更動紀錄」- 查看所有操作紀錄
7. 輸入「下載文件更動紀錄 word」或「下載文件更動紀錄 excel」- 匯出紀錄
8. 輸入「法規清單」- 列出所有文件引用的法規標準
9. 輸入「下載法規清單 word」或「下載法規清單 excel」- 匯出法規清單
10. 直接提問 - AI 將搜尋文件資料庫後回答

**切換 Profile：**
- 點擊頂部 Profile 選擇器切換到「文件管制」可上傳文件

**支援格式：** PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""


async def handle_status() -> str:
    """Handle status command"""
    doc_count, doc_limit = get_document_count()
    provider_name = cl.user_session.get("provider_name", "N/A")
    model_name = cl.user_session.get("model_name", "N/A")

    return f"""📊 **系統狀態**

- **文件數量**: {doc_count}/{doc_limit}
- **LLM 提供商**: {provider_name}
- **模型**: {model_name}
- **OCR**: 就緒
- **UI 框架**: Chainlit"""


async def handle_list() -> str:
    """Handle 列表 command - show ALL documents including version history and obsolete."""
    try:
        storage = get_markdown_store()
        registry = storage.registry
        all_docs = registry.get("documents", [])

        if not all_docs:
            return "📋 目前沒有任何文件紀錄。\n\n請切換到「文件管制」Profile 上傳文件。"

        active_count = sum(1 for d in all_docs if d.get("status", "active") == "active")
        obsolete_count = sum(1 for d in all_docs if d.get("status") == "obsolete")
        total_versions = sum(len(d.get("versions", [])) for d in all_docs)
        superseded_count = 0  # count of 已進版 version entries

        doc_lines = []
        for doc in all_docs:
            doc_id = doc["doc_id"]
            title = doc.get("title", "N/A")
            doc_type = doc.get("doc_type", "OTHER")
            status_str = doc.get("status", "active")
            current_ver = doc.get("current_version", "?")

            for ver_entry in doc.get("versions", []):
                ver = ver_entry.get("version", "?")
                created_at = ver_entry.get("created_at", "")[:10]  # date only
                created_by = ver_entry.get("created_by", "system")
                files_removed = ver_entry.get("files_removed", False)

                # Determine row status display
                if status_str == "obsolete":
                    row_status = "🗑️ 已作廢"
                elif files_removed:
                    row_status = "📦 已進版"
                    superseded_count += 1
                elif ver == current_ver:
                    row_status = "✅ 現行版"
                else:
                    row_status = "📦 已進版"
                    superseded_count += 1

                doc_lines.append(
                    f"| {doc_id} | {title} | {doc_type} | v{ver} | {created_at} | {created_by} | {row_status} |"
                )

        doc_list = "\n".join(doc_lines)
        # Build summary parts
        summary_parts = [f"有效 {active_count} 份"]
        if superseded_count:
            summary_parts.append(f"已進版 {superseded_count} 份")
        if obsolete_count:
            summary_parts.append(f"已作廢 {obsolete_count} 份")
        summary_str = "，".join(summary_parts)
        return f"""📋 **列表** — 所有文件紀錄 (共 {len(all_docs)} 份文件，{total_versions} 筆版本紀錄，{summary_str})

| 文件編號 | 標題 | 類型 | 版本 | 日期 | 操作者 | 狀態 |
|---------|------|------|------|------|--------|------|
{doc_list}

💡 輸入「文件清單」查看現行正式版本
💡 輸入「文件更動紀錄」查看完整操作紀錄"""
    except Exception as e:
        return f"無法讀取列表: {str(e)}"


async def handle_document_list() -> str:
    """Handle 文件清單 command - show only current formal (active) versions."""
    try:
        md_service = MarkdownStoreService()
        docs = md_service.list_documents()
        stats = md_service.get_stats()

        if not docs:
            return "📄 目前沒有已儲存的文件。\n\n請切換到「文件管制」Profile 上傳文件。"

        # Filter active documents only
        active_docs = [d for d in docs if d.get("status", "active") == "active"]

        if not active_docs:
            return "📄 目前沒有現行有效的正式文件。\n\n所有文件已作廢或尚未上傳。"

        doc_lines = []
        for d in active_docs:
            doc_lines.append(
                f"| {d['doc_id']} | {d.get('title', 'N/A')} | {d['doc_type']} | v{d['current_version']} |"
            )
        doc_list = "\n".join(doc_lines)
        return f"""📄 **文件清單** — 現行正式版本 (共 {len(active_docs)} 份)

| 文件編號 | 標題 | 類型 | 現行版本 |
|---------|------|------|----------|
{doc_list}

💡 輸入「列表」查看所有版本紀錄（含進版、作廢）
💡 輸入「搜尋 關鍵字」可搜尋文件內容"""
    except Exception as e:
        return f"無法讀取文件清單: {str(e)}"


async def handle_search(query: str) -> str:
    """Handle search command"""
    if not query:
        return "請輸入搜尋關鍵字，例如：搜尋 品質手冊"
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
            return f"🔍 **搜尋「{query}」結果** (共 {len(results)} 筆)\n\n{result_list}"
        else:
            return f"🔍 找不到包含「{query}」的文件。\n\n請確認關鍵字是否正確，或嘗試其他搜尋詞。"
    except Exception as e:
        return f"搜尋失敗: {str(e)}"


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
        reason = reason_text.strip() or "使用者手動作廢"

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
            return (
                f"🗑️ **文件已作廢**\n\n"
                f"- **文件編號**: {doc_id}\n"
                f"- **標題**: {result.get('title', 'N/A')}\n"
                f"- **類型**: {result.get('doc_type', 'N/A')}\n"
                f"- **版本**: v{result.get('version', 'N/A')}\n"
                f"- **原因**: {reason}\n"
                f"- **刪除檔案數**: {result.get('files_deleted_count', 0)}\n\n"
                f"文件已從資料庫中刪除，僅保留作廢紀錄供稽核追蹤。"
            )
        else:
            return f"❌ 作廢失敗: {result.get('error', '未知錯誤')}"
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
                f"請指定要作廢的文件編號。\n\n"
                f"**目前有效文件** ({len(active_docs)} 份):\n\n"
                f"| 文件編號 | 標題 | 類型 | 版本 |\n"
                f"|---------|------|------|------|\n"
                f"{doc_list}\n\n"
                f"範例：輸入「作廢 OTHER-016」或「作廢 OTHER-016 已被新版取代」"
            )
        else:
            return "目前沒有可作廢的文件。"


async def handle_audit() -> str:
    """Handle audit record display"""
    audit_log = ImmutableAuditLog()
    records = audit_log.get_all_records()
    is_valid, integrity_msg = audit_log.verify_chain_integrity()
    table_md = format_audit_table_markdown(records)
    if is_valid:
        table_md += f"\n\n🔒 鏈完整性驗證: ✅ {integrity_msg}"
    else:
        table_md += f"\n\n🔒 鏈完整性驗證: ❌ {integrity_msg}"
    return table_md


async def handle_audit_export(format_type: str):
    """Handle audit export to Word/Excel, returns file element"""
    audit_log = ImmutableAuditLog()
    records = audit_log.get_all_records()
    if not records:
        return None, "📋 目前沒有任何文件更動紀錄，無法匯出。"

    if format_type == "word":
        filepath = export_to_word(records)
        msg = f"📋 已產生文件更動紀錄 Word 報告 (共 {len(records)} 筆紀錄)。"
    elif format_type == "excel":
        filepath = export_to_excel(records)
        msg = f"📋 已產生文件更動紀錄 Excel 報告 (共 {len(records)} 筆紀錄)。"
    else:
        return (
            None,
            "📋 PDF 匯出功能開發中。\n\n目前支援：\n- 「下載文件更動紀錄 word」\n- 「下載文件更動紀錄 excel」",
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
        return None, "📋 資料庫中的文件未引用任何法規或標準，無法匯出。"

    if format_type == "word":
        filepath = export_regulatory_to_word(scan_result)
        msg = f"📋 已產生法規清單 Word 報告 (共 {len(aggregate)} 項標準)。"
    elif format_type == "excel":
        filepath = export_regulatory_to_excel(scan_result)
        msg = f"📋 已產生法規清單 Excel 報告 (共 {len(aggregate)} 項標準)。"
    else:
        return None, "📋 目前支援：\n- 「下載法規清單 word」\n- 「下載法規清單 excel」"

    return filepath, msg


async def handle_reference_export(format_type: str):
    """Handle 下載引用清單 word/excel command (after version update)."""
    ref_data = cl.user_session.get("last_reference_result")
    if not ref_data:
        return (
            None,
            "📋 目前沒有引用清單資料。請先進行文件進版，系統會自動產生引用清單。",
        )

    doc_id = ref_data.get("doc_id", "UNKNOWN")
    ref_docs = ref_data.get("ref_docs", [])
    if not ref_docs:
        return None, f"📋 沒有其他文件引用 {doc_id}，無需匯出。"

    if format_type == "word":
        filepath = export_reference_to_word(doc_id, ref_docs)
        msg = f"📋 已產生 {doc_id} 引用清單 Word 報告 (共 {len(ref_docs)} 份引用文件)。"
    elif format_type == "excel":
        filepath = export_reference_to_excel(doc_id, ref_docs)
        msg = (
            f"📋 已產生 {doc_id} 引用清單 Excel 報告 (共 {len(ref_docs)} 份引用文件)。"
        )
    else:
        return None, "📋 目前支援：\n- 「下載引用清單 word」\n- 「下載引用清單 excel」"

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
            fname = Path(file_path).name
            return file_path, f"已找到文件 {req_doc_id} 的原始檔案：\n\n📄 **{fname}**"
        else:
            return None, f"文件 {req_doc_id} 存在於資料庫中，但原始檔案無法找到。"
    else:
        storage = get_markdown_store()
        docs = storage.list_documents_with_files()
        available = [d for d in docs if d["has_original_file"]]
        msg = f"請指定文件編號。可下載的文件 ({len(available)} 份)：\n\n" + "\n".join(
            [
                f"- **{d['doc_id']}** ({d['file_extension']}) - {d['title']}"
                for d in available[:10]
            ]
        )
        if len(available) > 10:
            msg += f"\n... 還有 {len(available) - 10} 份"
        msg += "\n\n範例：輸入「下載 QP-852」"
        return None, msg


async def handle_delete_db():
    """Handle delete database command"""
    cl.user_session.set("awaiting_delete_confirm", True)

    actions = [
        cl.Action(
            name="confirm_delete",
            payload={"action": "delete_all"},
            label="⚠️ 確認刪除所有資料庫",
        ),
        cl.Action(
            name="cancel_delete",
            payload={"action": "cancel"},
            label="取消",
        ),
    ]

    await cl.Message(
        content="⚠️ **警告：此操作將刪除所有文件和資料庫紀錄（無法復原）**\n\n文件更動紀錄將被保留（不可刪除）。\n\n請確認是否繼續？",
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
            content=f"✅ 已刪除 {deleted_count} 份 Markdown 文件和 {upload_deleted} 份上傳檔案。資料庫已重置。\n\n⚠️ 文件更動紀錄已保留（不可刪除）。"
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ 刪除失敗: {str(e)}").send()

    await action.remove()


@cl.action_callback("cancel_delete")
async def on_cancel_delete(action):
    """Cancel database deletion"""
    cl.user_session.set("awaiting_delete_confirm", False)
    await cl.Message(content="已取消刪除操作。").send()
    await action.remove()


# ============================================================
# Download Action Callbacks
# ============================================================


async def _send_file_download(filepath: str, msg_text: str):
    """Helper: send a file as a download with cl.File element."""
    elements = [cl.File(name=Path(filepath).name, path=filepath, display="inline")]
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


@cl.action_callback("download_original_file")
async def on_download_original_file(action):
    """Download original uploaded file by doc_id."""
    doc_id = action.payload.get("doc_id", "")
    if not doc_id:
        await cl.Message(content="❌ 無法取得文件編號。").send()
        await action.remove()
        return

    storage = get_markdown_store()
    file_path = storage.get_original_file_path(doc_id)
    if file_path:
        fname = Path(file_path).name
        await _send_file_download(file_path, f"📄 **{doc_id}** — {fname}")
    else:
        await cl.Message(content=f"❌ 文件 {doc_id} 的原始檔案無法找到。").send()
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
            f"  **轉換引擎**: {engine_label} | {page_count} 頁 | {time_str} | {content_len:,} 字元 | 格式 {file_type}"
        )

    # Document type detection
    doc_info = result.get("doc_info", {})
    if doc_info:
        doc_type = doc_info.get("doc_type", "OTHER")
        doc_id = doc_info.get("doc_id", "")
        is_new = doc_info.get("is_new", True)
        det_ver = doc_info.get("detected_version", "")
        type_label = "新文件" if is_new else "已存在"
        ver_str = f" v{det_ver}" if det_ver else ""
        lines.append(
            f"  **文件判斷**: 類型 {doc_type} | 編號 {doc_id}{ver_str} | {type_label}"
        )

    # Signature detection
    sig = result.get("sig_result", {})
    if sig:
        if sig.get("detected"):
            stamp_list = sig.get("stamps", [])
            sig_list = sig.get("signatures", [])
            parts = []
            if stamp_list:
                parts.append(f"印章 {len(stamp_list)} 個: {', '.join(stamp_list[:3])}")
            if sig_list:
                parts.append(f"簽名 {len(sig_list)} 個: {', '.join(sig_list[:3])}")
            if not parts:
                parts.append(sig.get("reason", "已偵測"))
            lines.append(f"  **簽章偵測**: ✅ {'; '.join(parts)}")
        else:
            lines.append(f"  **簽章偵測**: ❌ {sig.get('reason', '未偵測到')}")

    # Save result
    if result.get("success"):
        doc_id = result.get("saved_doc_id", "")
        if result.get("is_version_update"):
            dup_id = result.get("duplicate_doc", {}).get("doc_id", "")
            existing_ver = result.get("existing_version", "?")
            new_ver = result.get("new_version", "?")
            lines.append(
                f"  **儲存結果**: 🔄 偵測到新版本 ({dup_id} V{existing_ver} → V{new_ver})"
            )
        elif result.get("is_duplicate"):
            dup_id = result.get("duplicate_doc", {}).get("doc_id", "")
            lines.append(f"  **儲存結果**: ⚠️ 重複文件 ({dup_id})")
        elif doc_id:
            lines.append(f"  **儲存結果**: ✅ 已存入 → {doc_id}")
    else:
        error = result.get("error", "未知錯誤")
        lines.append(f"  **結果**: ❌ {error}")

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
    api_key = cl.user_session.get("api_key", "")
    model_name = cl.user_session.get("model_name", "")

    # Initial progress message
    provider_name = cl.user_session.get("provider_name", provider_id)
    progress_msg = cl.Message(
        content=(
            f"📄 **開始處理 {total} 份文件**\n"
            f"- 轉換引擎: MarkItDown + LLM 備援\n"
            f"- LLM: {provider_name} / {model_name}\n"
        )
    )
    await progress_msg.send()

    for idx, file_el in enumerate(files):
        step = f"({idx + 1}/{total})"
        file_name = file_el.name

        # --- Step 1: Show "Markdown 轉換中" ---
        progress_msg.content = (
            f"📄 **處理進度 {step}**: `{file_name}`\n\n"
            f"  ▶ Step 1/3: Markdown 轉換中...\n"
            f"  ○ Step 2/3: 簽章偵測\n"
            f"  ○ Step 3/3: 存入資料庫\n"
        )
        await progress_msg.update()

        result = await asyncio.to_thread(
            process_uploaded_file_sync, file_el, provider_id, api_key, model_name
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
            else "🔄 偵測到新版本"
            if result.get("is_version_update")
            else "⚠️ 重複"
            if result.get("is_duplicate")
            else ""
        )

        progress_msg.content = (
            f"📄 **處理進度 {step}**: `{file_name}` {status_icon}\n\n"
            f"  ✅ Step 1/3: Markdown 轉換 ({provider}, {time_str})\n"
            f"  {sig_icon} Step 2/3: 簽章偵測 — {sig_text}\n"
            f"  {'✅' if result['success'] else '❌'} Step 3/3: 存入資料庫 {save_text}\n"
        )
        await progress_msg.update()

    # ---- Build final summary ----
    is_bulk = total > 1  # Bulk upload: simplified summary without details
    lines = [f"📋 **上傳處理結果** (共 {total} 份文件)\n"]

    if is_bulk:
        # Bulk upload: compact one-line-per-file summary (no detailed breakdown)
        for r in succeeded + failed:
            status_icon = "✅" if r.get("success") else "❌"
            doc_id = r.get("saved_doc_id") or r.get("duplicate_doc", {}).get(
                "doc_id", ""
            )
            id_str = f" → **{doc_id}**" if doc_id else ""
            if r.get("is_version_update"):
                dup_tag = " (進版)"
            elif r.get("is_duplicate"):
                dup_tag = " (重複)"
            else:
                dup_tag = ""
            err_str = ""
            if not r.get("success"):
                err_str = f" — {r.get('error', '未知錯誤')}"
            lines.append(f"- {status_icon} `{r['filename']}`{id_str}{dup_tag}{err_str}")
    else:
        # Single file upload: show full detailed results
        for r in succeeded + failed:
            status_icon = "✅" if r.get("success") else "❌"
            doc_id = r.get("saved_doc_id") or r.get("duplicate_doc", {}).get(
                "doc_id", ""
            )
            id_str = f" → **{doc_id}**" if doc_id else ""
            if r.get("is_version_update"):
                dup_tag = " (進版)"
            elif r.get("is_duplicate"):
                dup_tag = " (重複)"
            else:
                dup_tag = ""
            lines.append(f"### {status_icon} {r['filename']}{id_str}{dup_tag}\n")
            lines.append(_format_process_detail(r))
            lines.append("")

    # Summary counts
    lines.append(
        f"\n---\n**統計**: ✅ 成功 {len(succeeded)} 份 | ❌ 失敗 {len(failed)} 份"
    )

    # Show OCR preview only for single file upload
    if not is_bulk and succeeded:
        last = succeeded[-1]
        ocr_content = last.get("ocr_result", {}).get("markdown_content", "")
        if ocr_content:
            preview = ocr_content[:2000]
            if len(ocr_content) > 2000:
                preview += "\n\n... (內容已截斷)"
            lines.append(f"\n---\n📝 **OCR 預覽** ({last['filename']}):\n\n{preview}")

    # Handle duplicate detection (works for both single and bulk)
    if succeeded:
        last = succeeded[-1]
        if last.get("is_duplicate"):
            dup = last["duplicate_doc"]
            existing_ver = last.get("existing_version", dup.get("current_version", "?"))
            new_ver = last.get("new_version", "?")
            lines.append(
                f"\n\n⚠️ 偵測到文件進版: {dup['doc_id']} "
                f"(現有 V{existing_ver} → 新版 V{new_ver})"
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
                label="📝 確認為文件進版",
            ),
            cl.Action(
                name="cancel_version_update",
                payload={"action": "cancel"},
                label="取消",
            ),
        ]
        await cl.Message(
            content=(
                f"此文件 ({last['duplicate_doc']['doc_id']}) 已存在於資料庫中。\n"
                f"現有版本: **V{existing_ver}** → 新版本: **V{new_ver}**\n\n"
                f"是否要進行文件進版？"
            ),
            actions=actions,
        ).send()


def process_uploaded_file_sync(
    file_element, provider_id: str = "ollama", api_key: str = "", model_name: str = ""
):
    """Synchronous wrapper for file processing (runs in thread).

    NOTE: cl.user_session is NOT accessible from a thread context.
    All session data must be passed as parameters.
    """
    file_path = file_element.path
    filename = file_element.name
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "filename": filename,
            "error": f"不支援的檔案格式: {suffix}",
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
            "error": f"LLM 初始化失敗: {str(e)}",
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
            "error": f"OCR 失敗: {ocr_result.get('error_message', '未知錯誤')}",
        }

    ocr_text_for_detection = ocr_result.get("text_content", "") or ocr_result.get(
        "markdown_content", ""
    )
    doc_info = detect_document_type(filename, ocr_text_for_detection)
    sig_result = detect_signature(ocr_result, file_path=str(dest_path))

    if not sig_result["detected"]:
        try:
            dest_path.unlink()
        except Exception:
            pass
        return {
            "success": False,
            "filename": filename,
            "error": f"未偵測到簽名或印章 ({sig_result['reason']})",
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
                        "error": f"同版本文件已存在 ({extracted_doc_id} V{norm_existing})，無法重複上傳。",
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
            "error": f"存儲失敗: {save_result.get('error', '未知錯誤')}",
        }


# ============================================================
# Version Update / Stamp Confirmation Actions
# ============================================================


@cl.action_callback("confirm_version_update")
async def on_confirm_version_update(action):
    """Ask user to type confirmer name for version update"""
    await action.remove()

    sig_status = "🟢 **OCR 自動偵測**: 文件中偵測到簽名/簽章相關內容"

    # Set session flag: next text message = confirmer name
    cl.user_session.set("awaiting_confirmer_name", True)

    await cl.Message(
        content=f"""## ⚠️ 進版簽章確認

{sig_status}

**請確認已完成以下程序：**
- ☐ 主管審核簽章
- ☐ 品保確認蓋章
- ☐ 管理代表核准 (若適用)

**重要提醒**: 確認後將產生不可竄改的文件更動紀錄 (SHA-256 雜湊鏈)。

👤 **請在下方輸入框輸入確認人員姓名，按 Enter 送出即可完成進版。**""",
    ).send()


async def _execute_version_update(confirmer_name: str):
    """Execute version update after confirmer name is provided."""
    ocr_result = cl.user_session.get("current_ocr_result")
    doc_info = cl.user_session.get("current_doc_info")
    file_path = cl.user_session.get("current_file_path")

    if not ocr_result or not doc_info:
        await cl.Message(content="❌ 無法找到待處理的文件資料。請重新上傳。").send()
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
                f"✅ **文件進版完成**\n\n"
                f"- **文件編號**: {doc_info.get('doc_id')}\n"
                f"- **版本**: v{result['previous_version']} → v{result['version']}\n"
                f"- **確認人員**: {confirmer_name}\n"
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
                    msg += f"\n⚠️ 以下文件引用了此文件，請確認是否需要同步更新：\n{ref_list}"
                    msg += f"\n\n💡 輸入「下載引用清單 word」或「下載引用清單 excel」可匯出引用清單"
            except Exception:
                pass

            await cl.Message(content=msg).send()
        else:
            await cl.Message(content=f"❌ 儲存失敗: {result.get('error')}").send()

    except Exception as e:
        await cl.Message(content=f"❌ 進版處理失敗: {str(e)}").send()

    # Clear state
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)


@cl.action_callback("cancel_stamps")
async def on_cancel_stamps(action):
    """Cancel stamp confirmation"""
    await action.remove()
    await cl.Message(
        content="已取消簽章確認。請確保文件已完成所有必要簽章後再次提交。"
    ).send()


@cl.action_callback("cancel_version_update")
async def on_cancel_version_update(action):
    """Cancel version update"""
    await action.remove()
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)
    cl.user_session.set("awaiting_confirmer_name", False)
    await cl.Message(content="已取消文件進版。").send()


# ============================================================
# LLM Chat with Markdown DB Context
# ============================================================


async def chat_with_llm(message_text: str, profile: str):
    """Send message to LLM with Markdown DB context and stream response"""
    provider_id = cl.user_session.get("provider_id", "ollama")
    model_name = cl.user_session.get("model_name", "default")
    api_key = cl.user_session.get("api_key", "")

    setup_api_key(provider_id, api_key)

    try:
        manager = create_provider_manager(provider_id)
        # Disable fallback chain when user explicitly selected a provider
        if provider_id != "ollama":
            manager.disable_fallback = True
    except Exception as e:
        await cl.Message(
            content=f"⚠️ LLM 初始化失敗: {str(e)}\n\n請在設定中確認 LLM 提供商和 API Key。"
        ).send()
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
                        f"[文件 {r['doc_id']} - {r['title']}]\n{content}"
                    )
                    ref_docs.append(r["doc_id"])
            if context_parts:
                db_context = (
                    "\n\n以下是從文件資料庫中找到的相關文件:\n\n"
                    + "\n\n---\n\n".join(context_parts)
                )
    except Exception:
        pass

    # Build system prompt
    system_prompt = (
        MAIN_AGENT_SYSTEM_PROMPT
        if profile != "文件管制 (Doc Control)"
        else DOC_CONTROL_SYSTEM_PROMPT
    )
    if db_context:
        system_prompt += db_context
        system_prompt += "\n\n請根據上述文件內容回答使用者的問題。如果文件中沒有相關資訊，請明確告知，不要編造答案。"
    else:
        system_prompt += "\n\n目前文件資料庫中沒有找到與此問題相關的文件。請根據你的知識回答，但提醒使用者可以上傳相關文件到系統中。"

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
            full_response = "抱歉，未收到 LLM 回應。請檢查模型是否可用。"
            msg.content = full_response
            await msg.update()

        if ref_docs:
            full_response += "\n\n📚 參考文件: " + ", ".join(ref_docs)
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
            hint = "模型未找到，請確認模型名稱正確或嘗試其他模型"
        elif "connection" in error_lower or "connect" in error_lower:
            hint = "無法連接到 LLM 服務，請確認服務已啟動"
        elif "api_key" in error_lower or "apikey" in error_lower:
            hint = "API Key 無效或未設定"
        elif "timeout" in error_lower:
            hint = "連線逾時，請稍後再試"
        else:
            hint = "請檢查 LLM 設定或嘗試其他提供商"

        msg.content = f"""⚠️ LLM 連線發生問題 ({error_type})：
{error_detail}

💡 建議：{hint}

您可以：
- 輸入「狀態」查看系統狀態
- 輸入「幫助」獲取使用指南
- 在設定中調整 LLM 提供商和模型"""
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
            await cl.Message(content="❌ 姓名不可為空，請重新輸入。").send()
            cl.user_session.set("awaiting_confirmer_name", True)
            return
        await _execute_version_update(confirmer_name)
        return

    # ============================================================
    # Command routing (both profiles)
    # ============================================================

    # Help
    if "幫助" in text or "help" == msg_lower:
        response = await handle_help(profile)
        await cl.Message(content=response).send()
        return

    # Status
    if "狀態" in text or "status" == msg_lower:
        response = await handle_status()
        await cl.Message(content=response).send()
        return

    # 文件清單 — current formal versions only (must check before generic 清單)
    if "文件清單" in text:
        response = await handle_document_list()
        await cl.Message(content=response).send()
        return

    # 列表 — all records (active + obsolete + version history)
    is_list_cmd = "列表" in text or "list" == msg_lower or "所有文件" in text
    if is_list_cmd:
        response = await handle_list()
        await cl.Message(content=response).send()
        return

    # Search
    if "搜尋" in text or text.lower().startswith("search"):
        query = text.replace("搜尋", "").replace("search", "").strip()
        response = await handle_search(query)
        await cl.Message(content=response).send()
        return

    # ============================================================
    # Export / Download with Action Buttons
    # ============================================================
    # Helper: detect if user specified a format suffix
    text_lower_stripped = text.lower().strip()
    has_word_suffix = any(text_lower_stripped.endswith(s) for s in [" word", " docx"])
    has_excel_suffix = any(text_lower_stripped.endswith(s) for s in [" excel", " xlsx"])
    has_pdf_suffix = text_lower_stripped.endswith(" pdf")

    # --- Audit / 文件更動紀錄 export ---
    audit_dl_keywords = [
        "下載文件更動紀錄",
        "匯出文件更動紀錄",
        "下載稽核紀錄",
        "匯出稽核紀錄",
    ]
    is_audit_dl = any(kw in text for kw in audit_dl_keywords)

    if is_audit_dl:
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
            # No format specified → show two download buttons
            actions = [
                cl.Action(
                    name="download_audit_word",
                    payload={"format": "word"},
                    label="📥 下載 Word (.docx)",
                ),
                cl.Action(
                    name="download_audit_excel",
                    payload={"format": "excel"},
                    label="📥 下載 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content="📋 **文件更動紀錄匯出**\n\n請選擇下載格式：",
                actions=actions,
            ).send()
        return

    # --- Regulatory / 法規清單 export ---
    reg_dl_keywords = [
        "下載法規清單",
        "匯出法規清單",
    ]
    is_reg_dl = any(kw in text for kw in reg_dl_keywords)

    if is_reg_dl:
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
                    label="📥 下載 Word (.docx)",
                ),
                cl.Action(
                    name="download_regulatory_excel",
                    payload={"format": "excel"},
                    label="📥 下載 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content="📋 **法規清單匯出**\n\n請選擇下載格式：",
                actions=actions,
            ).send()
        return

    # Regulatory standards list (display only, no download)
    if "法規清單" in text or "法規標準" in text or "regulatory" in msg_lower:
        response = await handle_regulatory_list()
        await cl.Message(content=response).send()
        return

    # --- Reference / 引用清單 export ---
    ref_dl_keywords = [
        "下載引用清單",
        "匯出引用清單",
    ]
    is_ref_dl = any(kw in text for kw in ref_dl_keywords)

    if is_ref_dl:
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
                    label="📥 下載 Word (.docx)",
                ),
                cl.Action(
                    name="download_reference_excel",
                    payload={"format": "excel"},
                    label="📥 下載 Excel (.xlsx)",
                ),
            ]
            await cl.Message(
                content="📋 **引用清單匯出**\n\n請選擇下載格式：",
                actions=actions,
            ).send()
        return

    # Audit records (display only, no download)
    audit_keywords = ["文件更動紀錄", "稽核紀錄", "審計紀錄", "操作紀錄"]
    if any(kw in text for kw in audit_keywords) or "audit" == msg_lower:
        response = await handle_audit()
        await cl.Message(content=response).send()
        return

    # Obsolete
    if "作廢" in text or "obsolete" in msg_lower:
        response = await handle_obsolete(text)
        await cl.Message(content=response).send()
        return

    # ============================================================
    # Doc Control specific commands
    # ============================================================
    if profile == "文件管制 (Doc Control)":
        # Download original file by doc_id
        is_file_request = any(
            kw in text for kw in ["下載", "取得正本", "取得", "提供正本", "提供文件"]
        ) or any(kw in msg_lower for kw in ["download", "get file"])
        # Exclude audit/regulatory/reference list download keywords
        if is_file_request and not any(
            kw in text for kw in ["稽核", "審計", "更動紀錄", "法規清單", "引用清單"]
        ):
            filepath, msg_text = await handle_download(text)
            if filepath:
                # Single file → single download button
                fname = Path(filepath).name
                doc_id_match = re.search(
                    r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)", text, re.IGNORECASE
                )
                doc_id = doc_id_match.group(1).upper() if doc_id_match else ""
                actions = [
                    cl.Action(
                        name="download_original_file",
                        payload={"doc_id": doc_id},
                        label=f"📥 下載 {fname}",
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
        if "刪除資料庫" in text or "刪除所有" in text or "delete database" in msg_lower:
            await handle_delete_db()
            return

        # LLM test connection
        if (
            "連線測試" in text
            or "test connection" in msg_lower
            or "llm 連線" in msg_lower
        ):
            provider_id = cl.user_session.get("provider_id", "ollama")
            model_name = cl.user_session.get("model_name", "default")
            api_key = cl.user_session.get("api_key", "")
            result = test_llm_connection(provider_id, model_name, api_key)
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
            or "document" in msg_lower
            or ("文件管制" in text and len(text.strip()) <= 10)
        )
        if is_doc_command:
            await cl.Message(
                content="📄 **文件管制系統**\n\n請切換到「文件管制 (Doc Control)」Profile 來上傳和管理文件。\n\n點擊頂部的 Profile 選擇器即可切換。"
            ).send()
            return

        # LLM test connection
        if (
            "連線測試" in text
            or "test connection" in msg_lower
            or "llm 連線" in msg_lower
        ):
            provider_id = cl.user_session.get("provider_id", "ollama")
            model_name = cl.user_session.get("model_name", "default")
            api_key = cl.user_session.get("api_key", "")
            result = test_llm_connection(provider_id, model_name, api_key)
            await cl.Message(content=result).send()
            return

    # ============================================================
    # Default: LLM Chat with Markdown DB context
    # ============================================================
    await chat_with_llm(text, profile)
