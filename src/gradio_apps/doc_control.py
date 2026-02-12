"""
AI-QMS Phase 1 Document Control - Gradio Sub-Agent Interface
Complete document management interface with OCR, version control, and stamp confirmation.
"""

import os
import sys
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import gradio as gr

    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False
    print("[ERROR] Gradio not installed. Run: pip install gradio")

from src.llm_providers import (
    LLMProviderManager,
    DEFAULT_PROVIDERS,
    create_provider_manager,
    auto_update_models,
    print_update_summary,
)
from src.ocr.vision_ocr import VisionOCRProcessor, process_document, OCRResult
from src.storage.markdown_storage import MarkdownStorageManager, POC_DOCUMENT_LIMIT
from src.database.audit_log import ImmutableAuditLog
from src.database.document_store import DocumentStore
from src.services.markdown_store_service import get_markdown_store, MarkdownStoreService
from src.utils.audit_export import (
    format_audit_table_markdown,
    export_to_word,
    export_to_excel,
)


# ============================================================
# Constants
# ============================================================

UPLOAD_FOLDER = Path("./uploads")

# Supported file extensions - All Office formats + PDF + Images + Text
ALLOWED_EXTENSIONS = {
    # PDF
    ".pdf",
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".tiff",
    ".tif",
    ".bmp",
    # Word
    ".docx",
    ".doc",
    # Excel
    ".xlsx",
    ".xls",
    # PowerPoint
    ".pptx",
    ".ppt",
    # Text
    ".txt",
    ".md",
    ".csv",
    ".rtf",
}


# ============================================================
# Custom CSS for Doc Control Sub-Agent
# ============================================================

DOC_CONTROL_CSS = """
/* ============================================
   FORCE LIGHT THEME - Override dark mode completely
   ============================================ */
:root, .gradio-container, .dark, body, html {
    /* Background colors */
    --body-background-fill: #F9FAFB !important;
    --background-fill-primary: #FFFFFF !important;
    --background-fill-secondary: #F9FAFB !important;
    --block-background-fill: #FFFFFF !important;
    --panel-background-fill: #FFFFFF !important;
    --input-background-fill: #FFFFFF !important;
    --button-secondary-background-fill: #F3F4F6 !important;
    --neutral-50: #F9FAFB !important;
    --neutral-100: #F3F4F6 !important;
    --neutral-200: #E5E7EB !important;
    --color-accent: #4F46E5 !important;
    color-scheme: light !important;
    
    /* TEXT COLORS - Force dark text on light background */
    --body-text-color: #1F2937 !important;
    --block-title-text-color: #1F2937 !important;
    --block-label-text-color: #374151 !important;
    --input-text-color: #1F2937 !important;
    --neutral-700: #374151 !important;
    --neutral-800: #1F2937 !important;
    --neutral-900: #111827 !important;
    color: #1F2937 !important;
    
    /* FONT - Times New Roman for English, system fonts for Chinese */
    --font-family: "Times New Roman", "Noto Serif TC", "PMingLiU", serif !important;
}

/* Apply Times New Roman font globally - NUCLEAR option */
html, body, .gradio-container, .gradio-container *,
div, span, p, h1, h2, h3, h4, h5, h6,
input, textarea, button, select, option,
label, a, li, td, th, pre, code,
.block, .form, .panel, [class*="svelte"] {
    font-family: "Times New Roman", "Noto Serif TC", "PMingLiU", "Microsoft JhengHei", serif !important;
}

/* Override Gradio font variables */
:root {
    --font: "Times New Roman", "Noto Serif TC", "PMingLiU", serif !important;
    --font-mono: "Times New Roman", "Noto Serif TC", monospace !important;
}

/* Page Background - Light Gray */
.gradio-container {
    background: #F9FAFB !important;
    background-color: #F9FAFB !important;
    color: #1F2937 !important;
}

body {
    background: #F9FAFB !important;
    background-color: #F9FAFB !important;
    color: #1F2937 !important;
}

/* Force all blocks to have light background AND dark text */
/* EXCEPT blocks inside .doc-header */
.gradio-container .block:not(.doc-header .block),
.gradio-container .form,
.gradio-container .panel,
.gradio-container [class*="panel"],
.gradio-container [class*="form"] {
    background: #FFFFFF !important;
    background-color: #FFFFFF !important;
    color: #1F2937 !important;
}

/* Header blocks should be transparent */
.doc-header .block {
    background: transparent !important;
    background-color: transparent !important;
}

/* Force ALL text elements to be dark */
.gradio-container h1,
.gradio-container h2,
.gradio-container h3,
.gradio-container h4,
.gradio-container h5,
.gradio-container h6,
.gradio-container p,
.gradio-container span,
.gradio-container label,
.gradio-container div,
.gradio-container li,
.gradio-container td,
.gradio-container th {
    color: #1F2937 !important;
}

/* Input and textarea text */
.gradio-container input,
.gradio-container textarea,
.gradio-container select {
    color: #1F2937 !important;
    background: #FFFFFF !important;
}

/* Placeholder text - lighter gray */
.gradio-container input::placeholder,
.gradio-container textarea::placeholder {
    color: #9CA3AF !important;
}

/* Radio and checkbox labels */
.gradio-container [class*="radio"] label,
.gradio-container [class*="checkbox"] label,
.gradio-container [class*="Radio"] span,
.gradio-container [class*="Checkbox"] span {
    color: #1F2937 !important;
}

/* Accordion header */
.gradio-container [class*="accordion"] button,
.gradio-container [class*="Accordion"] button {
    color: #1F2937 !important;
}

/* ============================================
   Remove ALL shadows globally
   ============================================ */
:root, .gradio-container, .dark {
    --shadow-drop: none !important;
    --shadow-drop-lg: none !important;
    --shadow-sm: none !important;
    --shadow-md: none !important;
    --shadow-lg: none !important;
    --shadow-xl: none !important;
    --shadow-xs: none !important;
    --shadow-inset: none !important;
    --shadow-spread: 0 !important;
    --block-shadow: none !important;
    --input-shadow: none !important;
    --input-shadow-focus: none !important;
}

* {
    box-shadow: none !important;
    -webkit-box-shadow: none !important;
    -moz-box-shadow: none !important;
}

/* ============================================
   Header - Purple Gradient (matching Main Agent)
   ============================================ */
.doc-header {
    background: linear-gradient(90deg, #4F46E5, #7C3AED) !important;
    padding: 12px 20px !important;
    border-radius: 8px !important;
    margin-bottom: 12px !important;
}

/* Header title - MUST be white on purple background */
/* Use very specific selectors to override global rules */
.doc-header h1,
.doc-header .prose h1,
.doc-header .md h1,
.doc-header [data-testid="markdown"] h1,
.doc-header .block h1 {
    color: white !important;
    font-size: 20px !important;
    margin: 0 !important;
}

/* Override the global dark text rule for header - be very specific */
.doc-header,
.doc-header .block,
.doc-header .prose,
.doc-header .md,
.doc-header span,
.doc-header p {
    color: white !important;
}

/* But storage-status inside header needs dark text - highest specificity */
.doc-header .storage-status,
.doc-header .storage-status *,
.doc-header .storage-status p,
.doc-header .storage-status span,
.doc-header .storage-status .prose,
.doc-header .storage-status .md,
.doc-header div.storage-status,
.doc-header div.storage-status *,
.storage-status p,
.storage-status span {
    color: #1F2937 !important;
    background: #FFFFFF !important;
}

/* ============================================
   File Upload Section - White card on gray bg
   ============================================ */
.upload-section {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin-bottom: 12px !important;
}

.upload-section .gr-file,
.upload-section [data-testid="file"],
.upload-section .file-upload {
    background: #F9FAFB !important;
    border: 2px dashed #D1D5DB !important;
    border-radius: 8px !important;
}

/* ============================================
   Document Type Detection - White card
   ============================================ */
.doc-type-section {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    padding: 16px !important;
    max-height: 500px !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
}

.doc-type-section h3 {
    color: #374151 !important;
}

/* ============================================
   OCR Preview Section - White card
   ============================================ */
.ocr-section {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    padding: 16px !important;
}

.ocr-section h3 {
    color: #374151 !important;
}

.ocr-preview {
    background: #F9FAFB !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    padding: 12px !important;
    max-height: 400px !important;
    overflow-y: auto !important;
    color: #1F2937 !important;
}

/* ============================================
   Stamp Confirmation Modal - Light Yellow
   ============================================ */
.stamp-modal {
    background: #FFFBEB !important;
    border: 2px solid #F59E0B !important;
    border-radius: 12px !important;
    padding: 20px !important;
    margin: 12px 0 !important;
}

.stamp-modal h2 {
    color: #92400E !important;
}

.stamp-modal p, .stamp-modal strong {
    color: #78350F !important;
}

/* ============================================
   AI Chat Section - White card with bubble style
   ============================================ */
.chat-section {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin-top: 12px !important;
}

.chat-section h3 {
    color: #374151 !important;
    margin-bottom: 8px !important;
}

/* Chatbot container */
.doc-chatbot {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    overflow: hidden !important;
}

.doc-chatbot > div,
.doc-chatbot > div > div {
    background: #FFFFFF !important;
    border: none !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
}

/* Bot message bubble (LINE/WhatsApp style) */
.doc-chatbot .bot-row .message,
.doc-chatbot [class*="bot-row"] .message {
    background: #EFF6FF !important;
    border-radius: 16px !important;
    border-bottom-left-radius: 4px !important;
    padding: 8px 12px !important;
    border: none !important;
    color: #1F2937 !important;
    min-width: 60px !important;
    white-space: normal !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* User message bubble (LINE/WhatsApp style) */
.doc-chatbot .user-row .message,
.doc-chatbot [class*="user-row"] .message {
    background: #DBEAFE !important;
    border-radius: 16px !important;
    border-bottom-right-radius: 4px !important;
    padding: 8px 12px !important;
    border: none !important;
    color: #1F2937 !important;
    min-width: 60px !important;
    white-space: normal !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* CRITICAL: Force min-width on Gradio internal panel-full-width message divs */
/* These are the inner content divs that shrink to near-zero for short text */
.doc-chatbot [class*="panel-full-width"],
.doc-chatbot .message [class*="panel-full-width"],
.doc-chatbot [class*="message"] > div {
    min-width: 32px !important;
    writing-mode: horizontal-tb !important;
    white-space: normal !important;
}

/* Ensure horizontal text layout in all message content */
.doc-chatbot .message-row .message p,
.doc-chatbot .message-row .message span,
.doc-chatbot .message-row .message div,
.doc-chatbot p, .doc-chatbot span, .doc-chatbot li {
    color: #1F2937 !important;
    white-space: normal !important;
    word-break: break-word !important;
    writing-mode: horizontal-tb !important;
}

/* Chat input */
.chat-section input,
.chat-section textarea {
    background: #FFFFFF !important;
    color: #1F2937 !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 6px !important;
}

.chat-section input::placeholder,
.chat-section textarea::placeholder {
    color: #9CA3AF !important;
}

/* ============================================
   LLM Settings Accordion
   ============================================ */
.llm-settings {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    margin-bottom: 12px !important;
}

/* ============================================
   Buttons - Consistent styling with proper sizing
   v2.4.8: Improved button layout and sizing
   ============================================ */

/* Primary button - Purple */
button.primary,
.gr-button.primary,
button[class*="primary"] {
    background: #4F46E5 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    min-height: 42px !important;
    cursor: pointer !important;
    transition: background 0.2s ease !important;
}

button.primary:hover,
.gr-button.primary:hover,
button[class*="primary"]:hover {
    background: #4338CA !important;
}

/* Secondary button - Gray outline */
button.secondary,
.gr-button.secondary,
button[class*="secondary"] {
    background: #FFFFFF !important;
    color: #374151 !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    min-height: 42px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
}

button.secondary:hover,
.gr-button.secondary:hover,
button[class*="secondary"]:hover {
    background: #F3F4F6 !important;
    border-color: #9CA3AF !important;
}

/* Upload/Process button - Full width, larger */
.upload-section button.primary,
.upload-section .gr-button.primary {
    width: 100% !important;
    min-height: 48px !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    margin-top: 12px !important;
}

/* Confirm buttons in doc-type-section - Equal width */
.doc-type-section .gr-button,
.doc-type-section button {
    flex: 1 !important;
    min-width: 140px !important;
    min-height: 44px !important;
    font-size: 13px !important;
}

/* Stamp modal buttons */
.stamp-modal .gr-button,
.stamp-modal button {
    min-width: 150px !important;
    min-height: 44px !important;
    font-size: 14px !important;
}

/* Chat send button */
.chat-section .gr-button,
.chat-section button {
    min-height: 40px !important;
    padding: 8px 16px !important;
}

/* Processing status */
.processing-status {
    background: #F0FDF4 !important;
    border: 1px solid #BBF7D0 !important;
    border-radius: 8px !important;
    padding: 12px 16px !important;
    color: #166534 !important;
    font-size: 14px !important;
    margin: 12px 0 !important;
}

/* OCR auto-save hint */
.ocr-auto-save-hint {
    color: #6B7280 !important;
    font-size: 12px !important;
    font-style: normal !important;
    margin-bottom: 8px !important;
}
.ocr-auto-save-hint em,
.ocr-auto-save-hint i {
    font-style: normal !important;
}
.auto-save-hint {
    font-family: "DFKai-SB", "BiauKai", "\6A19\6977\9AD4", "Times New Roman", Times, serif !important;
    font-style: normal !important;
}

/* Storage status badge - in header, needs white background */
.storage-status {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    padding: 6px 12px !important;
    color: #1F2937 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* Ensure storage-status text is visible */
.storage-status p,
.storage-status span {
    color: #1F2937 !important;
}

/* v2.5.1: Signature detection status */
.signature-status {
    padding: 8px 12px !important;
    border-radius: 6px !important;
    margin-bottom: 8px !important;
    font-size: 13px !important;
}
.signature-status p {
    margin: 0 !important;
}
.signature-confirm-checkbox {
    border: 2px solid #F59E0B !important;
    border-radius: 6px !important;
    padding: 8px 12px !important;
    background: #FFFBEB !important;
    margin-bottom: 8px !important;
}
.signature-confirm-checkbox label {
    color: #92400E !important;
    font-weight: 600 !important;
}

/* v2.5.3: Remove Gradio scroll-fade white gradient overlay on chat input textarea */
.chat-section .scroll-fade,
.scroll-fade.svelte-kmbucf {
    display: none !important;
    background-image: none !important;
    background: transparent !important;
}

/* v2.5.3: English text in auto-save-hint uses Times New Roman explicitly */
.auto-save-hint .en-text {
    font-family: "Times New Roman", Times, serif !important;
}

/* v2.6.0: OUTER message max-width constraint */
.doc-chatbot .message-row .flex-wrap > .message {
    max-width: 90% !important;
    width: fit-content !important;
    min-width: 60px !important;
}

/* v2.6.0: INNER nested .message - NO constraint */
.doc-chatbot .message-row .message .message,
.doc-chatbot .message-row .message .message-content,
.doc-chatbot .message-row .message .message.panel-full-width {
    max-width: 100% !important;
    width: auto !important;
    min-width: 0 !important;
    padding: 0px !important;
    background: transparent !important;
}

/* v2.6.0: Transparent backgrounds for wrapper elements */
.doc-chatbot .message-row .flex-wrap.role,
.doc-chatbot .message-row [class*="flex-wrap"][class*="role"] {
    background: transparent !important;
}

.doc-chatbot .message-row .message .md,
.doc-chatbot .message-row .message .prose,
.doc-chatbot .message-row .message span.md {
    background: transparent !important;
}
"""


# ============================================================
# Helper Functions
# ============================================================


def ensure_upload_folder():
    """Ensure upload folder exists"""
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def detect_document_type(filename: str, ocr_text: str) -> dict:
    """
    Detect if document is new or version update based on filename and content.

    Returns:
        Dict with 'is_new', 'doc_id', 'doc_type', 'confidence', 'detected_version'
    """
    # Extract document ID from filename
    name = Path(filename).stem.upper()

    # Common document type patterns
    doc_type = "OTHER"
    if "SOP" in name:
        doc_type = "SOP"
    elif "WI" in name or "WORK" in name:
        doc_type = "WI"
    elif "FORM" in name or "FM" in name:
        doc_type = "FORM"
    elif "DHF" in name or "DESIGN" in name:
        doc_type = "DHF"

    # Try to extract document ID (e.g., SOP-001, WI-002)
    import re

    doc_id_pattern = r"([A-Z]{2,4}[-_]?\d{2,4})"
    matches = re.findall(doc_id_pattern, name)
    doc_id = matches[0].replace("_", "-") if matches else name[:20]

    # Try to detect version from filename first
    version_pattern = r"[vV]?(\d+[._]\d+)"
    version_matches = re.findall(version_pattern, name)
    detected_version = version_matches[0].replace("_", ".") if version_matches else None

    # v2.5.2: Also scan OCR content for version number (more reliable)
    if ocr_text:
        # Common version patterns in document content
        ocr_version_patterns = [
            r"[Vv]ersion\s*[:：]?\s*(\d+(?:\.\d+)+)",  # Version: 2.0
            r"[Rr]ev(?:ision)?\.?\s*[:：]?\s*(\d+(?:\.\d+)+)",  # Rev: 3.1
            r"版本\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",  # 版本：2.0
            r"版次\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",  # 版次：3.0
            r"修訂版\s*[:：]?\s*[vV]?(\d+(?:\.\d+)+)",  # 修訂版：2.1
            r"[Dd]ocument\s+[Vv]ersion\s*[:：]?\s*(\d+(?:\.\d+)+)",  # Document Version: 1.2
            r"[Rr]elease\s*[:：]?\s*(\d+(?:\.\d+)+)",  # Release: 2.0
        ]
        for pat in ocr_version_patterns:
            ocr_ver_matches = re.findall(pat, ocr_text)
            if ocr_ver_matches:
                detected_version = ocr_ver_matches[0]
                break

    # Check if document exists in storage
    storage = MarkdownStorageManager()
    is_new = not storage.document_exists(doc_id)

    # Calculate confidence based on pattern matching
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
        "confidence": min(confidence, 0.99),
        "detected_version": detected_version,
        "existing_version": None
        if is_new
        else storage.get_document(doc_id).get("metadata", {}).get("version"),
    }


# ============================================================
# Gradio Interface Components
# ============================================================


def create_doc_control_interface():
    """Create the Document Control Sub-Agent Gradio interface"""

    if not GRADIO_AVAILABLE:
        raise RuntimeError("Gradio not available")

    ensure_upload_folder()

    # API Key must be entered manually by user via UI

    # Initialize managers
    storage_manager = MarkdownStorageManager()
    audit_log = ImmutableAuditLog()
    document_store = DocumentStore()

    # ============================================================
    # Event Handlers
    # ============================================================

    def get_storage_status():
        """Get current storage status including Markdown DB"""
        stats = storage_manager.get_storage_stats()
        limit = stats.get("limit", 9999)
        try:
            md_service = MarkdownStoreService()
            md_stats = md_service.get_stats()
            count = md_stats["total_documents"]
            return f"文件: {count}/{limit}"
        except Exception:
            count = stats.get("total_documents", 0)
            return f"文件: {count}/{limit}"

    def update_model_choices(provider_name: str):
        """Update model dropdown based on provider selection - dynamically from llm_providers.py"""
        # Build provider map dynamically from DEFAULT_PROVIDERS
        provider_id = None
        for pid, config in DEFAULT_PROVIDERS.items():
            display_name = config.get("display_name", pid)
            if config.get("is_local"):
                display_name += " (Local)"
            if display_name == provider_name:
                provider_id = pid
                break

        if not provider_id:
            provider_id = "ollama"  # Default fallback

        if provider_id in DEFAULT_PROVIDERS:
            models = DEFAULT_PROVIDERS[provider_id]["available_models"]
            default = DEFAULT_PROVIDERS[provider_id]["default_model"]
            return gr.Dropdown(
                choices=models,
                value=default if default in models else (models[0] if models else ""),
                allow_custom_value=True,
            )
        return gr.Dropdown(choices=[], value="", allow_custom_value=True)

    def _process_single_file(
        file, llm_manager, progress_base, progress_step, progress_fn
    ):
        """Process a single file: copy, OCR, signature check, save to DB.

        Returns dict with keys:
            success, filename, doc_id, doc_type, is_new, reject_reason,
            ocr_result, doc_info, dest_path, signature_detected, saved_doc_id,
            duplicate_doc, status_msg
        """
        import re as _re

        file_path = file.name if hasattr(file, "name") else str(file)
        filename = Path(file_path).name
        result = {"success": False, "filename": filename, "reject_reason": None}

        # Check file extension
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            result["reject_reason"] = f"不支援的檔案格式: {suffix}"
            return result

        # Copy to uploads folder
        progress_fn(progress_base, desc=f"複製 {filename}...")
        dest_path = (
            UPLOAD_FOLDER / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        )
        shutil.copy(file_path, dest_path)
        result["dest_path"] = str(dest_path)

        # Process with OCR
        progress_fn(progress_base + progress_step * 0.3, desc=f"OCR {filename}...")
        ocr_result = process_document(str(dest_path), llm_manager)
        result["ocr_result"] = ocr_result

        if not ocr_result.get("success"):
            result["reject_reason"] = (
                f"OCR 失敗: {ocr_result.get('error_message', '未知錯誤')}"
            )
            try:
                if dest_path.exists():
                    dest_path.unlink()
            except Exception:
                pass
            return result

        # Detect document type
        progress_fn(progress_base + progress_step * 0.5, desc=f"分析 {filename}...")
        doc_info = detect_document_type(filename, ocr_result.get("text_content", ""))
        result["doc_info"] = doc_info
        result["doc_id"] = doc_info.get("doc_id", "")
        result["doc_type"] = doc_info.get("doc_type", "OTHER")
        result["is_new"] = doc_info.get("is_new", True)

        # Signature / stamp detection
        # v2.7.0: Comprehensive keyword list covering ALL forms of signatures and stamps.
        # This detection is OCR-content-based (not file-format-based), so it works
        # uniformly across .docx, .pdf, .png, .jpg, .xlsx, .pptx, etc.
        # For PDF/images: Vision LLM OCR extracts text including stamp/signature descriptions.
        # For .docx: python-docx extracts text content; image-only stamps need text labels.
        _ocr_text = (
            ocr_result.get("markdown_content", "")
            + " "
            + ocr_result.get("text_content", "")
        ).lower()
        _sig_keywords = [
            # === English: Handwritten signatures ===
            "signature",
            "signed",
            "sign:",
            "sign here",
            # === English: Approval / review roles ===
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
            # === English: Stamps / seals ===
            "stamp",
            "seal",
            "chop",
            "company seal",
            "official seal",
            # === English: Digital / electronic signatures ===
            "digitally signed",
            "electronic signature",
            "e-signature",
            # === 繁體中文: 手寫簽名 ===
            "簽名",
            "簽署",
            "簽字",
            "親簽",
            "手簽",
            # === 繁體中文: 印章 / 蓋章 ===
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
            # === 繁體中文: 審核 / 核准流程 ===
            "核准",
            "審核",
            "核准人",
            "審核人",
            "批准",
            "審批",
            "核定",
            "會簽",
            "擬定",
            # === 繁體中文: QMS 常見用語 ===
            "制定",
            "審查",
            "承認",
            "確認人",
            "覆核",
            "複核",
            # === 繁體中文: 電子簽章 ===
            "電子簽章",
            "數位簽章",
            "電子簽名",
            # === 簡體中文 (兼容) ===
            "签名",
            "签章",
            "盖章",
            "审核",
            "批准人",
            "审批",
            # === 日本語: 署名・印鑑・承認 ===
            "署名",  # signature (also valid in Chinese)
            "捺印",  # affixing a seal
            "押印",  # stamping a seal
            "印鑑",  # registered seal / seal impression
            "実印",  # registered personal seal
            "認印",  # informal seal
            "社印",  # company seal
            "角印",  # square company seal
            "丸印",  # round representative seal
            "代表者印",  # representative seal
            "承認",  # approval (also valid in Chinese)
            "承認者",  # approver
            "確認者",  # confirmer
            "検認",  # verification / probate
            "決裁",  # final approval / authorization
            "決裁者",  # authorizer
            "起案",  # drafting / origination
            "起案者",  # drafter
            "合議",  # joint deliberation
            "電子署名",  # electronic signature
            "電子印鑑",  # electronic seal
            "タイムスタンプ",  # timestamp (katakana)
            # === 한국어 (Korean): 서명・도장・승인 ===
            "서명",  # signature
            "날인",  # affixing a seal
            "도장",  # stamp/seal
            "인감",  # registered seal
            "직인",  # official seal
            "사인",  # sign (loanword)
            "관인",  # government/official seal
            "법인인감",  # corporate registered seal
            "승인",  # approval
            "승인자",  # approver
            "검토",  # review
            "검토자",  # reviewer
            "확인",  # confirmation
            "결재",  # approval/authorization
            "기안",  # drafting
            "기안자",  # drafter
            "합의",  # agreement/consensus
            "전자서명",  # electronic signature
            "전자도장",  # electronic stamp
            # === Deutsch (German): Unterschrift / Stempel / Genehmigung ===
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
            # === Français (French): Signature / Tampon / Approbation ===
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
            # === Español (Spanish): Firma / Sello / Aprobación ===
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
            # === Português (Portuguese): Assinatura / Carimbo / Aprovação ===
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
            # === Italiano (Italian): Firma / Timbro / Approvazione ===
            "timbro",
            "sigillo",
            "firmato",
            "firmato da",
            "approvato",
            "approvato da",
            "verificato da",
            "firma digitale",
            "firma elettronica",
            # === Nederlands (Dutch): Handtekening / Stempel / Goedkeuring ===
            "handtekening",
            "ondertekend",
            "ondertekend door",
            "goedgekeurd",
            "goedgekeurd door",
            "gecontroleerd door",
            "elektronische handtekening",
            # === Русский (Russian): Подпись / Печать / Утверждение ===
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
            # === العربية (Arabic): توقيع / ختم / موافقة ===
            "توقيع",  # signature
            "موقع",  # signed
            "ختم",  # stamp/seal
            "طابع",  # stamp
            "موافقة",  # approval
            "معتمد",  # approved
            "مراجعة",  # reviewed
            "توقيع إلكتروني",  # electronic signature
            # === ภาษาไทย (Thai): ลายเซ็น / ตราประทับ / อนุมัติ ===
            "ลายเซ็น",  # signature
            "ลงนาม",  # to sign
            "ตราประทับ",  # stamp/seal
            "ตรายาง",  # rubber stamp
            "อนุมัติ",  # approved
            "อนุมัติโดย",  # approved by
            "ตรวจสอบโดย",  # reviewed by
            "ลายเซ็นอิเล็กทรอนิกส์",  # electronic signature
            # === Tiếng Việt (Vietnamese): Chữ ký / Con dấu / Phê duyệt ===
            "chữ ký",  # signature
            "ký tên",  # to sign
            "con dấu",  # seal/stamp
            "đóng dấu",  # to stamp
            "phê duyệt",  # approval
            "phê duyệt bởi",  # approved by
            "xác nhận",  # confirmed
            "chữ ký số",  # digital signature
            "chữ ký điện tử",  # electronic signature
            # === Bahasa (Malay/Indonesian): Tandatangan / Cap / Kelulusan ===
            "tandatangan",  # signature
            "ditandatangani",  # signed
            "cap",  # stamp
            "meterai",  # seal/stamp duty
            "mohor",  # seal (Malay)
            "stempel",  # stamp (Indonesian, also German)
            "diluluskan",  # approved (Malay)
            "disetujui",  # approved (Indonesian)
            "disahkan",  # verified/certified
            "diperiksa oleh",  # checked by
            "tanda tangan elektronik",  # electronic signature
            # === Türkçe (Turkish): İmza / Mühür / Onay ===
            "imza",  # signature
            "imzalı",  # signed
            "mühür",  # seal
            "kaşe",  # stamp
            "onay",  # approval
            "onaylayan",  # approver
            "kontrol eden",  # checker
            "elektronik imza",  # electronic signature
            # === हिन्दी (Hindi): हस्ताक्षर / मुहर / अनुमोदन ===
            "हस्ताक्षर",  # signature
            "मुहर",  # seal
            "छाप",  # stamp
            "अनुमोदित",  # approved
            "सत्यापित",  # verified
            "डिजिटल हस्ताक्षर",  # digital signature
            # === Vision LLM OCR 輸出標記 (stamps_detected / signatures_detected) ===
            "stamps_detected",
            "signatures_detected",
            "[印章]",
            "[簽名]",
            "[stamp]",
            "[seal]",
        ]
        sig_detected = any(kw in _ocr_text for kw in _sig_keywords)
        # Also check Vision LLM detected_elements (for PDF/image OCR)
        _detected = ocr_result.get("detected_elements", {})
        if not sig_detected and _detected:
            if _detected.get("stamps") or _detected.get("signatures"):
                sig_detected = True
        result["signature_detected"] = sig_detected

        # Reject unsigned documents
        if not sig_detected:
            result["reject_reason"] = "未偵測到簽名或印章 (ISO 13485)"
            try:
                if dest_path.exists():
                    dest_path.unlink()
            except Exception:
                pass
            return result

        # Save to Markdown DB
        progress_fn(progress_base + progress_step * 0.8, desc=f"儲存 {filename}...")
        markdown_service = MarkdownStoreService()

        duplicate_doc = markdown_service.check_duplicate(str(dest_path))
        if duplicate_doc:
            result["duplicate_doc"] = duplicate_doc
            result["status_msg"] = f"重複文件: {duplicate_doc['doc_id']}"
            result["success"] = True
            return result

        save_result = markdown_service.save_ocr_result(
            markdown_content=ocr_result["markdown_content"],
            source_filename=filename,
            source_file_path=str(dest_path),
            doc_type=doc_info.get("doc_type", "OTHER"),
            tags=[doc_info.get("doc_type", "OTHER"), "ocr-auto"],
            ocr_provider=ocr_result.get("provider_used", "unknown"),
            ocr_confidence=ocr_result.get("confidence", 0.0),
        )

        if save_result.get("success"):
            result["saved_doc_id"] = save_result.get("doc_id")
            result["status_msg"] = f"已存入: {save_result.get('doc_id')}"
            result["success"] = True
        else:
            result["reject_reason"] = (
                f"存儲失敗: {save_result.get('error', '未知錯誤')}"
            )
            result["success"] = False

        return result

    def process_uploaded_files(
        files: list,
        provider_name: str,
        model_name: str,
        api_key: str,
        state: dict,
        progress=gr.Progress(),
    ):
        """Process uploaded files with OCR — supports batch upload (multiple files)."""
        if not files:
            return (state, "請先上傳文件", "", None, "", "", get_storage_status(), [])

        # Setup LLM provider
        provider_map = {
            # Direct API Providers
            "OpenAI": "openai",
            "Anthropic": "anthropic",
            "Google Gemini": "google",
            "DeepSeek": "deepseek",
            "xAI (Grok)": "xai",
            # LLM Gateway/Router Platforms
            "OpenRouter": "openrouter",
            "Requesty": "requesty",
            "Together AI": "together",
            "Groq": "groq",
            "Fireworks AI": "fireworks",
            "Deep Infra": "deepinfra",
            # Local Providers
            "Ollama (Local)": "ollama",
            "LM Studio (Local)": "lmstudio",
        }
        provider_id = provider_map.get(provider_name, "ollama")

        try:
            llm_manager = create_provider_manager(provider_id)

            # Set API key if provided - use config env_key_name
            if api_key and not DEFAULT_PROVIDERS[provider_id]["is_local"]:
                env_key = DEFAULT_PROVIDERS[provider_id].get(
                    "env_key_name", f"{provider_id.upper()}_API_KEY"
                )
                os.environ[env_key] = api_key

            ocr_processor = VisionOCRProcessor(llm_manager)
        except Exception as e:
            return (
                state,
                f"LLM 初始化失敗: {str(e)}",
                "",
                None,
                "",
                "",
                get_storage_status(),
                [],
            )

        # ============================================================
        # v2.7.0: Batch upload — process ALL files, not just files[0]
        # ============================================================
        total_files = len(files)
        progress_step = 1.0 / max(total_files, 1)

        succeeded = []
        failed = []
        last_ocr_content = ""
        last_doc_info = None

        for idx, file in enumerate(files):
            progress_base = idx * progress_step
            result = _process_single_file(
                file, llm_manager, progress_base, progress_step, progress
            )

            if result["success"]:
                succeeded.append(result)
                # Keep last successful OCR content for preview
                if result.get("ocr_result"):
                    last_ocr_content = result["ocr_result"].get("markdown_content", "")
                last_doc_info = result.get("doc_info")
            else:
                failed.append(result)

        progress(1.0, desc="完成")

        # ============================================================
        # Build batch summary
        # ============================================================
        total_ok = len(succeeded)
        total_fail = len(failed)

        # Status message
        status_parts = [
            f"批量上傳完成: 成功 {total_ok} 份, 失敗 {total_fail} 份 (共 {total_files} 份)"
        ]
        status_msg = " | ".join(status_parts)

        # Chat message with details
        chat_lines = [f"📋 **批量上傳結果** (共 {total_files} 份文件)\n"]
        chat_lines.append(f"✅ **成功: {total_ok} 份**")
        for r in succeeded:
            doc_id = r.get("saved_doc_id") or r.get("duplicate_doc", {}).get(
                "doc_id", ""
            )
            dup_tag = " (重複)" if r.get("duplicate_doc") else ""
            chat_lines.append(f"  - {r['filename']} → {doc_id}{dup_tag}")

        if failed:
            chat_lines.append(f"\n❌ **失敗: {total_fail} 份**")
            for r in failed:
                chat_lines.append(
                    f"  - {r['filename']} → {r.get('reject_reason', '未知原因')}"
                )

        chat_msg = "\n".join(chat_lines)

        # Update state with last processed file info (for single-file compat)
        if succeeded:
            last = succeeded[-1]
            state["current_file"] = last.get("dest_path", "")
            state["filename"] = last["filename"]
            state["ocr_result"] = last.get("ocr_result", {})
            state["doc_info"] = last.get("doc_info", {})
            state["file_hash"] = (
                calculate_file_hash(last["dest_path"]) if last.get("dest_path") else ""
            )
            state["signature_detected"] = last.get("signature_detected", False)
            if last.get("saved_doc_id"):
                state["saved_doc_id"] = last["saved_doc_id"]
            if last.get("duplicate_doc"):
                state["duplicate_doc"] = last["duplicate_doc"]
        # Store batch results in state for reference
        state["batch_results"] = {
            "succeeded": len(succeeded),
            "failed": len(failed),
            "total": total_files,
        }

        # OCR preview: show last successful file's content, or empty
        ocr_preview_text = last_ocr_content if last_ocr_content else ""

        # Doc type / confidence / version: show summary for batch
        if total_files == 1 and succeeded:
            # Single file: show detailed info like before
            di = last_doc_info or {}
            doc_type_label = (
                "初次輸入 (新文件)" if di.get("is_new") else "文件進版 (更新)"
            )
            confidence_text = f"信心度: {di.get('confidence', 0):.0%}"
            version_text = (
                f"文件編號: {di.get('doc_id', '')}\n文件類型: {di.get('doc_type', '')}"
            )
            if di.get("detected_version"):
                version_text += f"\nOCR 偵測版本: v{di['detected_version']}"
            if di.get("existing_version"):
                version_text += f"\n現有版本: v{di['existing_version']}"
        else:
            # Batch: show summary
            doc_type_label = f"批量上傳: {total_ok} 成功 / {total_fail} 失敗"
            confidence_text = f"共 {total_files} 份文件"
            version_text = f"成功: {total_ok} 份\n失敗: {total_fail} 份"
            if failed:
                version_text += "\n\n失敗文件:"
                for r in failed:
                    version_text += f"\n- {r['filename']}: {r.get('reject_reason', '')}"

        chat_history = [{"role": "assistant", "content": chat_msg}]

        return (
            state,
            status_msg,
            ocr_preview_text,
            doc_type_label,
            confidence_text,
            version_text,
            get_storage_status(),
            chat_history,
        )

    def confirm_as_new_document(state: dict):
        """Confirm document as new (first input)"""
        if not state.get("ocr_result"):
            return state, "請先上傳並處理文件", [], gr.Column(visible=False)

        doc_info = state.get("doc_info", {})
        ocr_result = state.get("ocr_result", {})

        # Save to storage
        result = storage_manager.save_document(
            doc_id=doc_info.get("doc_id", "UNKNOWN"),
            title=state.get("filename", "Untitled"),
            doc_type=doc_info.get("doc_type", "OTHER"),
            markdown_content=ocr_result.get("markdown_content", ""),
            original_file=state.get("current_file", ""),
            ocr_provider=ocr_result.get("provider_used", "unknown"),
            ocr_confidence=ocr_result.get("confidence", 0.0),
            user_id="gradio_user",
        )

        if result["success"]:
            # Create audit record
            audit_log.create_record(
                action="document_created",
                document_id=doc_info.get("doc_id"),
                user_id="gradio_user",
                details={
                    "version": result["version"],
                    "file_hash": state.get("file_hash"),
                    "ocr_provider": ocr_result.get("provider_used"),
                },
            )

            msg = f"文件已儲存為新文件\n文件編號: {doc_info.get('doc_id')}\n版本: v{result['version']}\n剩餘配額: {result['remaining_slots']}"
            # Gradio 6.x: Use messages format
            chat = [{"role": "assistant", "content": msg}]

            # Clear state
            state["current_file"] = None
            state["ocr_result"] = None
            state["doc_info"] = None

            return state, msg, chat, gr.Column(visible=False)
        else:
            error_msg = f"儲存失敗: {result.get('error')}"
            return (
                state,
                error_msg,
                # Gradio 6.x: Use messages format
                [{"role": "assistant", "content": error_msg}],
                gr.Column(visible=False),
            )

    def confirm_as_version_update(state: dict):
        """Confirm document as version update - show stamp confirmation"""
        if not state.get("ocr_result"):
            return state, "請先上傳並處理文件", [], gr.Column(visible=True), ""

        doc_info = state.get("doc_info", {})
        msg = f"請確認 {doc_info.get('doc_id')} 的簽章狀態"

        # v2.5.1: Show signature detection result
        sig_detected = state.get("signature_detected", False)
        if sig_detected:
            sig_status = "🟢 **OCR 自動偵測**: 文件中偵測到簽名/簽章相關內容"
        else:
            sig_status = (
                "🔴 **OCR 自動偵測**: 未在文件中偵測到簽名/簽章，請確認文件是否已簽署"
            )

        # Gradio 6.x: Use messages format
        return (
            state,
            msg,
            [
                {
                    "role": "assistant",
                    "content": "請在簽章確認區域確認所有必要簽章已完成。",
                }
            ],
            gr.Column(visible=True),
            sig_status,
        )

    def cancel_stamp_confirmation(state: dict):
        """Cancel stamp confirmation and return to editing"""
        return (
            state,
            "已取消，請補齊簽章後重新確認",
            # Gradio 6.x: Use messages format
            [
                {
                    "role": "assistant",
                    "content": "已取消簽章確認。請確保文件已完成所有必要簽章後再次提交。",
                }
            ],
            gr.Column(visible=False),
        )

    def confirm_stamps_complete(
        state: dict,
        stamps_checked: list,
        confirmer_name: str,
        signature_confirmed: bool,
    ):
        """Confirm stamps are complete and save version update"""
        if not state.get("ocr_result"):
            return state, "請先上傳並處理文件", [], gr.Column(visible=False)

        if not confirmer_name or not confirmer_name.strip():
            # Gradio 6.x: Use messages format
            return (
                state,
                "請輸入確認人員姓名",
                [{"role": "assistant", "content": "請輸入確認人員姓名"}],
                gr.Column(visible=True),
            )

        # v2.5.1: Check signature confirmation
        if not signature_confirmed:
            sig_msg = "請確認文件上有簽名（勾選「✍️ 確認文件上有簽名」）"
            return (
                state,
                sig_msg,
                [{"role": "assistant", "content": sig_msg}],
                gr.Column(visible=True),
            )

        required_stamps = ["主管審核簽章", "品保確認蓋章"]
        missing = [s for s in required_stamps if s not in stamps_checked]

        if missing:
            missing_msg = f"缺少必要簽章: {', '.join(missing)}"
            return (
                state,
                missing_msg,
                # Gradio 6.x: Use messages format
                [{"role": "assistant", "content": missing_msg}],
                gr.Column(visible=True),
            )

        doc_info = state.get("doc_info", {})
        ocr_result = state.get("ocr_result", {})

        # Save version update
        # v2.5.2: Use OCR-detected version from document instead of auto-incrementing
        ocr_detected_version = doc_info.get("detected_version", None)
        result = storage_manager.update_document(
            doc_id=doc_info.get("doc_id", "UNKNOWN"),
            markdown_content=ocr_result.get("markdown_content", ""),
            original_file=state.get("current_file", ""),
            ocr_provider=ocr_result.get("provider_used", "unknown"),
            ocr_confidence=ocr_result.get("confidence", 0.0),
            user_id=confirmer_name.strip(),
            explicit_version=ocr_detected_version,
        )

        if result["success"]:
            # Create audit record
            audit_log.create_record(
                action="document_version_updated",
                document_id=doc_info.get("doc_id"),
                user_id=confirmer_name.strip(),
                details={
                    "previous_version": result["previous_version"],
                    "new_version": result["version"],
                    "file_hash": state.get("file_hash"),
                    "stamps_confirmed": stamps_checked,
                    "ocr_provider": ocr_result.get("provider_used"),
                    "signature_detected_by_ocr": state.get("signature_detected", False),
                    "signature_confirmed_by_user": True,
                },
            )

            msg = f"文件進版完成\n文件編號: {doc_info.get('doc_id')}\n版本: v{result['previous_version']} → v{result['version']}\n確認人員: {confirmer_name}"

            # v2.5.0: Find referencing documents (cross-reference check)
            try:
                ref_docs = storage_manager.find_referencing_documents(
                    doc_info.get("doc_id", "")
                )
                if ref_docs:
                    ref_list = "\n".join(
                        [
                            f"  - {r['doc_id']} ({r['title']}) - {r['doc_type']} v{r['current_version']}"
                            for r in ref_docs
                        ]
                    )
                    msg += f"\n\n⚠️ 以下文件引用了此文件，請確認是否需要同步更新：\n{ref_list}"
            except Exception:
                pass  # Don't fail the version update if cross-ref check fails

            # Gradio 6.x: Use messages format
            chat = [{"role": "assistant", "content": msg}]

            # Clear state
            state["current_file"] = None
            state["ocr_result"] = None
            state["doc_info"] = None

            return state, msg, chat, gr.Column(visible=False)
        else:
            error_msg = f"儲存失敗: {result.get('error')}"
            return (
                state,
                error_msg,
                # Gradio 6.x: Use messages format
                [{"role": "assistant", "content": error_msg}],
                gr.Column(visible=True),
            )

    # v2.4.8: download_markdown function deprecated - OCR results are now auto-saved to Markdown DB
    # Keeping for backward compatibility but no longer used in UI
    def download_markdown(state: dict):
        """
        Generate markdown file for download

        DEPRECATED in v2.4.8: OCR results are now automatically saved to Markdown DB.
        This function is kept for backward compatibility but is no longer used in the UI.
        """
        if not state.get("ocr_result"):
            return None

        content = state["ocr_result"].get("markdown_content", "")
        filename = state.get("filename", "document")

        # Create temp file
        temp_path = UPLOAD_FOLDER / f"{Path(filename).stem}_ocr.md"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(temp_path)

    def chat_respond(
        message,
        history: list,
        provider_name: str,
        model_name: str,
        api_key: str,
        state: dict,
    ):
        """
        Handle chat messages with LLM integration.
        v2.5.0: Fixed Gradio 6.x messages format, added LLM for general questions.
        Searches Markdown DB first for grounded answers (no hallucination).
        """
        # Handle multimodal input from MultimodalTextbox
        if isinstance(message, dict):
            text_content = message.get("text", "").strip()
            files = message.get("files", [])
        else:
            text_content = str(message).strip() if message else ""
            files = []

        if not text_content and not files:
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=None, visible=False),
            )
            return

        # Build display message
        display_msg = text_content
        if files:
            file_names = [
                Path(f if isinstance(f, str) else getattr(f, "name", str(f))).name
                for f in files
            ]
            if text_content:
                display_msg = (
                    f"{text_content}\n\n📎 附件: {', '.join(file_names)} (僅供問答)"
                )
            else:
                display_msg = f"📎 附件: {', '.join(file_names)} (僅供問答)"

        # Gradio 6.x: Use messages format
        history.append({"role": "user", "content": display_msg})

        # Simple command responses
        response = ""
        file_to_download = None  # v2.5.4: Track file download path
        msg_lower = text_content.lower()

        # v2.6.0: Audit record commands — must check BEFORE file download detection
        audit_keywords = ["稽核紀錄", "審計紀錄", "操作紀錄"]
        audit_download_word = any(
            kw in text_content
            for kw in [
                "下載稽核紀錄 word",
                "匯出稽核紀錄 word",
                "下載稽核紀錄 Word",
                "匯出稽核紀錄 Word",
                "下載審計紀錄 word",
                "匯出審計紀錄 word",
            ]
        )
        audit_download_excel = any(
            kw in text_content
            for kw in [
                "下載稽核紀錄 excel",
                "匯出稽核紀錄 excel",
                "下載稽核紀錄 Excel",
                "匯出稽核紀錄 Excel",
                "下載審計紀錄 excel",
                "匯出審計紀錄 excel",
            ]
        )
        audit_download_pdf = any(
            kw in text_content
            for kw in [
                "下載稽核紀錄 pdf",
                "匯出稽核紀錄 pdf",
                "下載稽核紀錄 PDF",
                "匯出稽核紀錄 PDF",
            ]
        )
        is_audit_query = (
            any(kw in text_content for kw in audit_keywords) or "audit" in msg_lower
        )

        if audit_download_word:
            records = audit_log.get_all_records()
            if not records:
                history.append(
                    {
                        "role": "assistant",
                        "content": "📋 目前沒有任何稽核紀錄，無法匯出。",
                    }
                )
                yield (
                    history,
                    gr.MultimodalTextbox(value=None),
                    gr.File(value=None, visible=False),
                )
                return
            filepath = export_to_word(records)
            history.append(
                {
                    "role": "assistant",
                    "content": f"📋 已產生稽核紀錄 Word 報告 (共 {len(records)} 筆紀錄)。\n\n請在下方下載區域下載檔案。",
                }
            )
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=filepath, visible=True),
            )
            return

        elif audit_download_excel:
            records = audit_log.get_all_records()
            if not records:
                history.append(
                    {
                        "role": "assistant",
                        "content": "📋 目前沒有任何稽核紀錄，無法匯出。",
                    }
                )
                yield (
                    history,
                    gr.MultimodalTextbox(value=None),
                    gr.File(value=None, visible=False),
                )
                return
            filepath = export_to_excel(records)
            history.append(
                {
                    "role": "assistant",
                    "content": f"📋 已產生稽核紀錄 Excel 報告 (共 {len(records)} 筆紀錄)。\n\n請在下方下載區域下載檔案。",
                }
            )
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=filepath, visible=True),
            )
            return

        elif audit_download_pdf:
            history.append(
                {
                    "role": "assistant",
                    "content": "📋 PDF 匯出功能開發中。\n\n目前支援：\n- 輸入「下載稽核紀錄 word」匯出 Word 格式\n- 輸入「下載稽核紀錄 excel」匯出 Excel 格式",
                }
            )
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=None, visible=False),
            )
            return

        elif is_audit_query:
            records = audit_log.get_all_records()
            is_valid, integrity_msg = audit_log.verify_chain_integrity()
            table_md = format_audit_table_markdown(records)
            if is_valid:
                table_md += f"\n\n🔒 鏈完整性驗證: ✅ {integrity_msg}"
            else:
                table_md += f"\n\n🔒 鏈完整性驗證: ❌ {integrity_msg}"
            history.append({"role": "assistant", "content": table_md})
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=None, visible=False),
            )
            return

        # v2.5.4: File download request detection
        import re as _re

        file_request_patterns = [
            r"下載\s*(.+)",
            r"取得正本\s*(.+)",
            r"取得\s*(.+)",
            r"提供\s*(.+)",
            r"download\s+(.+)",
            r"get\s+file\s+(.+)",
            r"get\s+(.+)",
        ]
        is_file_request = any(
            kw in text_content
            for kw in ["下載", "取得正本", "取得", "提供正本", "提供文件"]
        ) or any(kw in msg_lower for kw in ["download", "get file"])

        if is_file_request:
            # Extract doc_id from message using pattern matching
            doc_id_match = _re.search(
                r"(QP-\d+|QM-\d+|FM-\d+-\d+|WI-\d+-\d+|OTHER-\d+)",
                text_content,
                _re.IGNORECASE,
            )
            if doc_id_match:
                req_doc_id = doc_id_match.group(1).upper()
                file_path = storage_manager.get_original_file_path(req_doc_id)
                if file_path:
                    file_to_download = file_path
                    fname = Path(file_path).name
                    response = f"已找到文件 {req_doc_id} 的原始檔案：\n\n📄 **{fname}**\n\n檔案已準備好，請在下方下載區域下載。"
                else:
                    response = f"文件 {req_doc_id} 存在於資料庫中，但原始檔案無法找到。\n\n可能原因：原始上傳檔案已被移除。您可以使用 Markdown 版本內容。"
            else:
                # No doc_id found, show available documents
                docs = storage_manager.list_documents_with_files()
                available = [d for d in docs if d["has_original_file"]]
                response = (
                    f"請指定文件編號。可下載的文件 ({len(available)} 份)：\n\n"
                    + "\n".join(
                        [
                            f"- **{d['doc_id']}** ({d['file_extension']}) - {d['title']}"
                            for d in available[:10]
                        ]
                    )
                )
                if len(available) > 10:
                    response += f"\n... 還有 {len(available) - 10} 份"
                response += "\n\n範例：輸入「下載 QP-852」"

        elif "作廢" in text_content or "obsolete" in msg_lower:
            # v2.7.0: Document obsolete (作廢) command
            import re as _re_obs

            obs_doc_id_match = _re_obs.search(
                r"(SOP-\d+|WI-\d+|FORM-\d+|DHF-\d+|OTHER-\d+)",
                text_content,
                _re_obs.IGNORECASE,
            )
            if obs_doc_id_match:
                obs_doc_id = obs_doc_id_match.group(1).upper()
                # Extract reason if provided after doc_id
                obs_reason_text = text_content
                for kw in ["作廢", "obsolete", obs_doc_id_match.group(0)]:
                    obs_reason_text = obs_reason_text.replace(kw, "")
                obs_reason = obs_reason_text.strip()
                if not obs_reason:
                    obs_reason = "使用者手動作廢"

                md_service = MarkdownStoreService()
                obs_result = md_service.obsolete_document(
                    doc_id=obs_doc_id,
                    reason=obs_reason,
                    user_id="doc_control_user",
                )
                if obs_result.get("success"):
                    # Log to audit
                    audit_log.create_record(
                        action="DOCUMENT_OBSOLETED",
                        document_id=obs_doc_id,
                        user_id="doc_control_user",
                        details={
                            "title": obs_result.get("title", ""),
                            "doc_type": obs_result.get("doc_type", ""),
                            "version": obs_result.get("version", ""),
                            "reason": obs_reason,
                            "files_deleted_count": obs_result.get(
                                "files_deleted_count", 0
                            ),
                        },
                    )
                    response = (
                        f"🗑️ **文件已作廢**\n\n"
                        f"- **文件編號**: {obs_doc_id}\n"
                        f"- **標題**: {obs_result.get('title', 'N/A')}\n"
                        f"- **類型**: {obs_result.get('doc_type', 'N/A')}\n"
                        f"- **版本**: v{obs_result.get('version', 'N/A')}\n"
                        f"- **原因**: {obs_reason}\n"
                        f"- **刪除檔案數**: {obs_result.get('files_deleted_count', 0)}\n\n"
                        f"文件已從資料庫中刪除，僅保留作廢紀錄供稽核追蹤。"
                    )
                else:
                    response = f"❌ 作廢失敗: {obs_result.get('error', '未知錯誤')}"
            else:
                # No doc_id specified, show available documents
                docs = storage_manager.list_documents()
                active_docs = [d for d in docs if d.get("status", "active") == "active"]
                if active_docs:
                    doc_list = "\n".join(
                        [
                            f"- **{d['doc_id']}** (v{d['current_version']}) - {d['doc_type']} - {d.get('title', 'N/A')}"
                            for d in active_docs[:20]
                        ]
                    )
                    response = (
                        f"請指定要作廢的文件編號。\n\n"
                        f"**目前有效文件** ({len(active_docs)} 份):\n{doc_list}\n\n"
                        f"範例：輸入「作廢 OTHER-016」或「作廢 OTHER-016 已被新版取代」"
                    )
                else:
                    response = "目前沒有可作廢的文件。"

        elif "狀態" in text_content or "status" in msg_lower:
            try:
                md_service_status = MarkdownStoreService()
                md_stats = md_service_status.get_stats()
                response = f"目前系統狀態:\n- 文件數量: {md_stats['total_documents']}\n- Markdown DB: {md_stats['total_documents']} 份"
            except Exception:
                stats = storage_manager.get_storage_stats()
                response = f"目前系統狀態:\n- 文件數量: {stats['total_documents']}"
        elif "幫助" in text_content or "help" in msg_lower:
            response = "可用功能:\n1. 上傳文件進行 OCR 處理 (自動存入 Markdown DB)\n2. 確認文件類型 (新文件/進版)\n3. 簽章確認流程\n4. 在對話框上傳文件問問題 (不存入資料庫)\n5. 直接提問 - AI 將搜尋文件資料庫後回答\n6. 輸入「下載 文件編號」取得原始文件 (如: 下載 QP-852)\n7. 輸入「作廢 文件編號」作廢文件 (如: 作廢 OTHER-016)\n8. 輸入「稽核紀錄」查看所有操作紀錄\n9. 輸入「下載稽核紀錄 word」或「下載稽核紀錄 excel」匯出紀錄"
        elif "列表" in text_content or "list" in msg_lower:
            md_service_list = MarkdownStoreService()
            docs = md_service_list.list_documents()
            if docs:
                lines = []
                for d in docs:
                    status_icon = "🗑️" if d.get("status") == "obsolete" else "✅"
                    lines.append(
                        f"- {status_icon} {d['doc_id']} (v{d['current_version']}) - {d['doc_type']} [{d.get('status', 'active')}]"
                    )
                response = "已儲存文件:\n" + "\n".join(lines)
            else:
                response = "目前沒有已儲存的文件"
        elif "搜尋" in text_content or "search" in msg_lower:
            query = text_content.replace("搜尋", "").replace("search", "").strip()
            if query:
                md_service = MarkdownStoreService()
                results = md_service.search(query, limit=5)
                if results:
                    response = f"搜尋「{query}」結果:\n" + "\n".join(
                        [f"- {r['doc_id']}: {r['title']}" for r in results]
                    )
                else:
                    response = f"找不到包含「{query}」的文件"
            else:
                response = "請輸入搜尋關鍵字，例如：搜尋 品質手冊"
        elif files and not text_content:
            response = (
                f"收到 {len(files)} 個檔案。這些檔案僅供問答參考，不會存入資料庫。"
            )
        else:
            # General question - use LLM with streaming for faster response
            try:
                # Search Markdown DB for relevant context
                md_service = MarkdownStoreService()
                search_results = md_service.search(text_content, limit=3)

                # Build context from found documents
                context_parts = []
                if search_results:
                    for r in search_results:
                        doc_data = md_service.get_document(r["doc_id"])
                        if doc_data.get("success"):
                            content = doc_data["content"]
                            if len(content) > 2000:
                                content = content[:2000] + "..."
                            context_parts.append(
                                f"[文件 {r['doc_id']} - {r['title']}]\n{content}"
                            )

                # Build provider
                p_map = {}
                for pid, config in DEFAULT_PROVIDERS.items():
                    dn = config.get("display_name", pid)
                    if config.get("is_local"):
                        dn += " (Local)"
                    p_map[dn] = pid
                p_id = p_map.get(provider_name, "openrouter")

                # Set API key
                if api_key and not DEFAULT_PROVIDERS.get(p_id, {}).get("is_local"):
                    ek = DEFAULT_PROVIDERS.get(p_id, {}).get("env_key_name", "")
                    if ek:
                        os.environ[ek] = api_key

                mgr = create_provider_manager(p_id)

                # Build system prompt with context
                sys_content = "你是 AI-QMS 文件管制子系統的 AI 助理。請根據提供的文件資料庫內容來回答問題。如果資料庫中沒有相關資訊，請明確告知使用者，不要編造答案。請用繁體中文回答。"
                if context_parts:
                    sys_content += (
                        "\n\n以下是從文件資料庫中找到的相關文件內容:\n\n"
                        + "\n\n---\n\n".join(context_parts)
                    )
                else:
                    sys_content += "\n\n目前文件資料庫中沒有找到與此問題相關的文件。"

                messages = [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": text_content},
                ]

                # v2.6.0: Use streaming for faster perceived response time
                stream_response = mgr.completion(
                    messages=messages,
                    model=model_name,
                    temperature=0.3,
                    max_tokens=2000,
                    stream=True,
                    timeout=30,
                )

                # Stream the response - yield partial results as they arrive
                history.append({"role": "assistant", "content": ""})
                full_response = ""
                try:
                    for chunk in stream_response:
                        if hasattr(chunk, "choices") and chunk.choices:
                            delta = chunk.choices[0].delta
                            if hasattr(delta, "content") and delta.content:
                                full_response += delta.content
                                history[-1]["content"] = full_response
                                yield (
                                    history,
                                    gr.MultimodalTextbox(value=None),
                                    gr.File(value=None, visible=False),
                                )
                except Exception as stream_err:
                    if full_response:
                        full_response += f"\n\n[串流中斷: {str(stream_err)}]"
                    else:
                        full_response = f"[串流錯誤: {str(stream_err)}]"

                if not full_response:
                    full_response = "抱歉，未收到 LLM 回應。請檢查模型是否可用。"

                if search_results:
                    full_response += "\n\n📚 參考文件: " + ", ".join(
                        [r["doc_id"] for r in search_results]
                    )

                history[-1]["content"] = full_response
                yield (
                    history,
                    gr.MultimodalTextbox(value=None),
                    gr.File(value=None, visible=False),
                )
                return

            except Exception as e:
                response = f"LLM 回應錯誤: {str(e)}\n\n您可以:\n- 輸入「狀態」查看系統狀態\n- 輸入「列表」查看文件\n- 輸入「搜尋 關鍵字」搜尋文件"

        history.append({"role": "assistant", "content": response})
        # v2.5.4: Return file download if requested
        if file_to_download:
            yield (
                history,
                gr.MultimodalTextbox(value=None),
                gr.File(value=file_to_download, visible=True),
            )
            return
        yield (
            history,
            gr.MultimodalTextbox(value=None),
            gr.File(value=None, visible=False),
        )

    # ============================================================
    # Build Interface
    # ============================================================

    # Gradio 6.x: css and theme must be in launch(), not Blocks()
    with gr.Blocks(
        title="AI-QMS 文件管制子系統",
    ) as demo:
        # State management
        session_state = gr.State(
            {
                "current_file": None,
                "filename": None,
                "ocr_result": None,
                "doc_info": None,
                "file_hash": None,
            }
        )

        # Header
        with gr.Row(elem_classes=["doc-header"]):
            gr.Markdown("# 📄 AI-QMS 文件管制子系統")
            with gr.Column(scale=0, min_width=200):
                storage_status = gr.Markdown(
                    get_storage_status(), elem_classes=["storage-status"]
                )

        # LLM Provider Settings
        with gr.Accordion("⚙️ LLM 設定", open=False, elem_classes=["llm-settings"]):
            gr.Markdown("### 選擇 LLM 提供商")
            gr.Markdown("支援直接 API、網關平台和本地模型")
            # Build provider choices dynamically from llm_providers.py
            provider_choices = []
            for provider_id, config in DEFAULT_PROVIDERS.items():
                display_name = config.get("display_name", provider_id)
                if config.get("is_local"):
                    display_name += " (Local)"
                provider_choices.append(display_name)

            default_provider = provider_choices[0] if provider_choices else ""
            default_models = []
            default_model = ""
            if default_provider:
                for pid, cfg in DEFAULT_PROVIDERS.items():
                    dn = cfg.get("display_name", pid)
                    if cfg.get("is_local"):
                        dn += " (Local)"
                    if dn == default_provider:
                        default_models = cfg.get("available_models", [])
                        default_model = cfg.get(
                            "default_model", default_models[0] if default_models else ""
                        )
                        break

            with gr.Row():
                provider_dropdown = gr.Dropdown(
                    choices=provider_choices,
                    value=default_provider,
                    label="LLM Provider",
                )
                model_dropdown = gr.Dropdown(
                    choices=default_models,
                    value=default_model,
                    label="模型",
                    allow_custom_value=True,
                )
                api_key_input = gr.Textbox(
                    label="API Key (雲端服務需要)",
                    type="password",
                    placeholder="輸入 API Key...",
                )

            provider_dropdown.change(
                update_model_choices,
                inputs=[provider_dropdown],
                outputs=[model_dropdown],
            )

            # LLM Connection Test Button
            with gr.Row():
                test_llm_btn = gr.Button("🔗 LLM 連線", variant="secondary", size="sm")
                test_llm_result = gr.Markdown("", elem_classes=["processing-status"])

            def test_llm_connection(prov_name, mod_name, key):
                """Test LLM connection with user-selected model"""
                try:
                    p_map = {}
                    for pid, config in DEFAULT_PROVIDERS.items():
                        dn = config.get("display_name", pid)
                        if config.get("is_local"):
                            dn += " (Local)"
                        p_map[dn] = pid
                    p_id = p_map.get(prov_name, "openrouter")
                    if key and not DEFAULT_PROVIDERS.get(p_id, {}).get("is_local"):
                        ek = DEFAULT_PROVIDERS.get(p_id, {}).get("env_key_name", "")
                        if ek:
                            os.environ[ek] = key
                    mgr = create_provider_manager(p_id)
                    # v2.7.0: Use user-selected model, not provider default
                    res = mgr.test_connection(model=mod_name if mod_name else None)
                    if res.get("success"):
                        return f"✅ 連線成功！ 提供商: {res['provider']} | 模型: {res['model']} | 延遲: {res['latency_ms']}ms | 回應: {res.get('response', '')}"
                    else:
                        return f"❌ 連線失敗 提供商: {res.get('provider', 'N/A')} | 模型: {res.get('model', 'N/A')} | 錯誤: {res.get('error', '未知錯誤')}"
                except Exception as e:
                    return f"❌ 測試失敗: {str(e)}"

            test_llm_btn.click(
                test_llm_connection,
                inputs=[provider_dropdown, model_dropdown, api_key_input],
                outputs=[test_llm_result],
            )

        # File Upload Section - v2.4.8: Improved layout
        with gr.Group(elem_classes=["upload-section"]):
            gr.Markdown("### 📤 文件上傳")
            file_upload = gr.File(
                label="拖放檔案至此處或點擊選擇",
                file_count="multiple",
                file_types=[
                    # PDF
                    ".pdf",
                    # Images
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                    ".tiff",
                    ".tif",
                    ".bmp",
                    # Word
                    ".docx",
                    ".doc",
                    # Excel
                    ".xlsx",
                    ".xls",
                    # PowerPoint
                    ".pptx",
                    ".ppt",
                    # Text
                    ".txt",
                    ".md",
                    ".csv",
                    ".rtf",
                ],
            )
            upload_btn = gr.Button("🔄 開始處理", variant="primary", size="lg")

        # Processing Status
        processing_status = gr.Markdown(
            "等待上傳文件...", elem_classes=["processing-status"]
        )

        # Main Content Area - v2.4.8: Improved layout
        with gr.Row(equal_height=True):
            # Left: Document Type Detection
            with gr.Column(scale=1, elem_classes=["doc-type-section"]):
                gr.Markdown("### 📋 文件類型判斷")
                doc_type_result = gr.Radio(
                    choices=["初次輸入 (新文件)", "文件進版 (更新)"],
                    label="AI 判斷結果",
                    interactive=False,
                )
                with gr.Row():
                    confidence_display = gr.Markdown("信心度: --")
                    version_info = gr.Markdown("版本資訊: --")

                # v2.4.8: Buttons with equal width, stacked vertically for better UX
                gr.Markdown("---")
                confirm_new_btn = gr.Button(
                    "✓ 確認為初次輸入", variant="primary", size="lg"
                )
                confirm_update_btn = gr.Button(
                    "📝 確認為文件進版", variant="secondary", size="lg"
                )

            # Right: OCR Preview
            with gr.Column(scale=2, elem_classes=["ocr-section"]):
                with gr.Row():
                    gr.Markdown("### 📝 OCR 結果預覽")
                    gr.Markdown(
                        "<span class='auto-save-hint'>✓ 自動存入 <span class='en-text'>Markdown DB</span></span>",
                        elem_classes=["ocr-auto-save-hint"],
                    )
                ocr_preview = gr.Markdown(
                    value="等待 OCR 處理...", elem_classes=["ocr-preview"]
                )

        # Stamp Confirmation Modal - v2.4.8: Improved layout
        with gr.Column(visible=False, elem_classes=["stamp-modal"]) as stamp_modal:
            gr.Markdown("## ⚠️ 進版簽章確認")
            gr.Markdown("""
**重要提醒**: 確認後將產生不可竄改的稽核紀錄 (SHA-256 雜湊鏈)，符合 21 CFR Part 11 電子簽章要求。
            """)

            # v2.5.1: Signature detection indicator
            signature_status = gr.Markdown("", elem_classes=["signature-status"])

            stamp_checklist = gr.CheckboxGroup(
                choices=["主管審核簽章", "品保確認蓋章", "管理代表核准 (若適用)"],
                label="請確認已完成以下程序",
            )

            # v2.5.1: Signature confirmation checkbox (required)
            signature_confirm = gr.Checkbox(
                label="✍️ 確認文件上有簽名 (必要)",
                value=False,
                elem_classes=["signature-confirm-checkbox"],
            )

            with gr.Row():
                confirmer_name = gr.Textbox(
                    label="確認人員姓名", placeholder="請輸入您的姓名", scale=2
                )
                # Note: scale parameter removed in Gradio 6.x
                confirm_time = gr.Markdown(
                    f"確認時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

            with gr.Row():
                cancel_stamp_btn = gr.Button(
                    "↩️ 返回補章", variant="secondary", size="lg"
                )
                confirm_stamp_btn = gr.Button(
                    "✓ 確認已完成簽章", variant="primary", size="lg"
                )

        # Delete All Files Section - visible button with confirmation
        with gr.Row():
            with gr.Column(scale=3):
                delete_confirm_checkbox = gr.Checkbox(
                    label="我確認要刪除所有文件和資料庫紀錄 (無法復原)",
                    value=False,
                )
            with gr.Column(scale=1, min_width=160):
                delete_all_btn = gr.Button(
                    "🗑️ 刪除所有資料庫", variant="stop", size="sm"
                )
        delete_result = gr.Markdown("")

        def delete_all_files(confirmed):
            if not confirmed:
                return "請先勾選確認框才能刪除", False, get_storage_status()
            try:
                # Collect info about what will be deleted BEFORE deleting
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
                # NOTE: audit_log.json is intentionally NOT wiped.
                # Audit records are immutable per ISO 13485 / 21 CFR Part 11.
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

                # Record the bulk delete action in the immutable audit log
                audit_log.create_record(
                    action="bulk_delete",
                    document_id="ALL",
                    user_id="gradio_user",
                    details={
                        "deleted_md_count": deleted_count,
                        "deleted_upload_count": upload_deleted,
                        "deleted_doc_ids": doc_list,
                    },
                )

                return (
                    f"已刪除 {deleted_count} 份 Markdown 文件和 {upload_deleted} 份上傳檔案。資料庫已重置。\n⚠️ 稽核紀錄已保留（不可刪除）。",
                    False,
                    get_storage_status(),
                )
            except Exception as e:
                return f"刪除失敗: {str(e)}", False, get_storage_status()

        delete_all_btn.click(
            delete_all_files,
            inputs=[delete_confirm_checkbox],
            outputs=[delete_result, delete_confirm_checkbox, storage_status],
        )

        # AI Chat Section
        with gr.Column(elem_classes=["chat-section"]):
            gr.Markdown("### 💬 AI 助理對話")
            chatbot = gr.Chatbot(
                value=[],
                height=200,
                layout="bubble",
                elem_classes=["doc-chatbot"],
                show_label=False,
            )
            with gr.Row():
                # v2.4.8: Use MultimodalTextbox for file upload support in chat
                chat_input = gr.MultimodalTextbox(
                    placeholder="輸入訊息或上傳文件問問題... (僅供問答，不存入資料庫)",
                    show_label=False,
                    file_count="multiple",
                    file_types=[
                        "image",
                        ".pdf",
                        ".docx",
                        ".xlsx",
                        ".pptx",
                        ".txt",
                        ".md",
                    ],
                    sources=["upload"],
                    scale=4,
                )
                chat_send_btn = gr.Button("發送", scale=1)

            # v2.5.4: File download component for original document retrieval
            file_download = gr.File(
                label="📥 文件下載",
                visible=False,
                interactive=False,
            )

        # ============================================================
        # Event Bindings
        # ============================================================

        # File upload and processing
        upload_btn.click(
            process_uploaded_files,
            inputs=[
                file_upload,
                provider_dropdown,
                model_dropdown,
                api_key_input,
                session_state,
            ],
            outputs=[
                session_state,
                processing_status,
                ocr_preview,
                doc_type_result,
                confidence_display,
                version_info,
                storage_status,
                chatbot,
            ],
        )

        # Confirm as new document
        confirm_new_btn.click(
            confirm_as_new_document,
            inputs=[session_state],
            outputs=[session_state, processing_status, chatbot, stamp_modal],
        )

        # Confirm as version update (show stamp modal)
        confirm_update_btn.click(
            confirm_as_version_update,
            inputs=[session_state],
            outputs=[
                session_state,
                processing_status,
                chatbot,
                stamp_modal,
                signature_status,
            ],
        )

        # Cancel stamp confirmation
        cancel_stamp_btn.click(
            cancel_stamp_confirmation,
            inputs=[session_state],
            outputs=[session_state, processing_status, chatbot, stamp_modal],
        )

        # Confirm stamps complete
        confirm_stamp_btn.click(
            confirm_stamps_complete,
            inputs=[session_state, stamp_checklist, confirmer_name, signature_confirm],
            outputs=[session_state, processing_status, chatbot, stamp_modal],
        )

        # v2.4.8: Download markdown button removed - OCR results are auto-saved to Markdown DB

        # Chat (with LLM settings for grounded Q&A)
        # v2.5.4: Added file_download to outputs for original file retrieval
        chat_send_btn.click(
            chat_respond,
            inputs=[
                chat_input,
                chatbot,
                provider_dropdown,
                model_dropdown,
                api_key_input,
                session_state,
            ],
            outputs=[chatbot, chat_input, file_download],
        )
        chat_input.submit(
            chat_respond,
            inputs=[
                chat_input,
                chatbot,
                provider_dropdown,
                model_dropdown,
                api_key_input,
                session_state,
            ],
            outputs=[chatbot, chat_input, file_download],
        )

    return demo


def launch_doc_control_app(
    server_name: str = "0.0.0.0", server_port: int = 7860, share: bool = False
):
    """
    Launch the Document Control Gradio application.

    Args:
        server_name: Server hostname
        server_port: Server port
        share: Create public share link
    """
    # v2.7.0: Auto-update LLM model lists from provider APIs
    print("[啟動] 正在從各平台 API 更新 LLM 模型清單...")
    try:
        update_results = auto_update_models()
        summary = print_update_summary(update_results)
        print(summary)
    except Exception as e:
        print(f"[警告] 模型清單自動更新失敗: {e}")

    demo = create_doc_control_interface()
    # Gradio 6.x: css and theme must be passed to launch()
    # v2.4.9: Custom theme with Times New Roman font to override Soft's Montserrat
    custom_theme = gr.themes.Soft(
        font=(
            "Times New Roman",
            "Noto Serif TC",
            "PMingLiU",
            "Microsoft JhengHei",
            "serif",
        ),
        font_mono=(
            "Times New Roman",
            "Noto Serif TC",
            "monospace",
        ),
    )
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        show_error=True,
        css=DOC_CONTROL_CSS,
        theme=custom_theme,
    )


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AI-QMS Phase 1 - Document Control Sub-Agent")
    print("=" * 60)
    print(f"Starting Gradio interface on port 7860...")
    print("Access at: http://localhost:7860")
    print("=" * 60)

    launch_doc_control_app()
