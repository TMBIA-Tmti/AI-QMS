"""
AI-QMS Phase 1 - Main Agent Gradio Interface
=============================================

Version: v2.4.7
Updated: 2026-02-05

This is the main entry point for AI-QMS system, replacing Open WebUI.
Provides a professional chat interface with sub-agent navigation and LLM management.

Design based on: docs/diagrams/Main-Agent-UI-Mockup.svg

Features:
- Sub-Agent Navigation (5 sub-systems)
- LLM Provider Management (13+ providers)
- Real-time chat with streaming
- System status monitoring
- Document count tracking
"""

import os
import sys
import json
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Optional, Generator

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import gradio as gr

    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False
    print("[ERROR] Gradio not installed. Run: pip install gradio")

try:
    from src.llm_providers import (
        LLMProviderManager,
        DEFAULT_PROVIDERS,
        create_provider_manager,
        auto_update_models,
        print_update_summary,
    )

    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("[WARN] LLM providers not available")
    DEFAULT_PROVIDERS = {}

    def auto_update_models(*a, **kw):
        return {}

    def print_update_summary(*a, **kw):
        return ""


try:
    from src.storage.markdown_storage import MarkdownStorageManager, POC_DOCUMENT_LIMIT
    from src.services.markdown_store_service import (
        MarkdownStoreService,
        get_markdown_store,
    )

    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    POC_DOCUMENT_LIMIT = 20
    print("[WARN] Storage manager not available")

# Audit log and export
try:
    from src.database.audit_log import ImmutableAuditLog
    from src.utils.audit_export import (
        format_audit_table_markdown,
        export_to_word,
        export_to_excel,
    )

    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    print("[WARN] Audit module not available")


# ============================================================
# Custom CSS - Matching SVG Design Exactly
# ============================================================

CUSTOM_CSS = """
/* ============================================
   Override Gradio CSS Variables - Remove ALL shadows
   v2.4.8: More aggressive shadow removal
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
    --checkbox-shadow: none !important;
    --block-label-shadow: none !important;
}

/* ============================================
   NUCLEAR: Remove ALL shadows from entire page
   Including scroll indicator gradients
   ============================================ */
*, *::before, *::after {
    box-shadow: none !important;
    -webkit-box-shadow: none !important;
    -moz-box-shadow: none !important;
}

/* Remove Gradio chatbot scroll indicator shadows (gradient overlays) */
[data-testid="chatbot"]::before,
[data-testid="chatbot"]::after,
.chatbot-container::before,
.chatbot-container::after,
[class*="chatbot"]::before,
[class*="chatbot"]::after,
[class*="wrap"]::before,
[class*="wrap"]::after,
.chat-container::before,
.chat-container::after {
    display: none !important;
    background: none !important;
    background-image: none !important;
    opacity: 0 !important;
    height: 0 !important;
    content: none !important;
}

/* Also target Gradio's scroll-shadow elements directly */
[class*="scroll"],
[class*="fade"],
[class*="shadow"],
[class*="gradient"],
[class*="indicator"] {
    background-image: none !important;
    mask-image: none !important;
    -webkit-mask-image: none !important;
}

/* v2.4.9: Aggressive Gradio 6.x scroll indicator removal */
/* Gradio uses ::before/::after with linear-gradient on scroll containers */
.chatbot-container *::before,
.chatbot-container *::after,
[data-testid="chatbot"] *::before,
[data-testid="chatbot"] *::after,
.gradio-chatbot *::before,
.gradio-chatbot *::after {
    background: none !important;
    background-image: none !important;
    background-color: transparent !important;
    display: none !important;
    content: none !important;
    opacity: 0 !important;
    height: 0 !important;
    width: 0 !important;
    pointer-events: none !important;
}

/* Remove mask-image from all chatbot scroll wrappers */
.chatbot-container div,
.chatbot-container [class*="wrap"],
[data-testid="chatbot"] div,
[data-testid="chatbot"] [class*="wrap"] {
    mask-image: none !important;
    -webkit-mask-image: none !important;
    mask: none !important;
    -webkit-mask: none !important;
}

/* ============================================
   Chat bubbles: FIT CONTENT, not full width
   ============================================ */
/* Target Gradio 6.x message structure */
.message-row, 
[class*="message-row"],
[data-testid="bot"], 
[data-testid="user"] {
    width: 100% !important;
    display: flex !important;
}

/* Bot messages - align left */
.message-row.bot-row,
[class*="bot-row"],
[data-testid="bot"] {
    justify-content: flex-start !important;
}

/* User messages - align right */
.message-row.user-row,
[class*="user-row"],
[data-testid="user"] {
    justify-content: flex-end !important;
}

/* Message bubble itself - fit content (NOT bubble-wrap which is the scroll container) */
/* v2.6.0: Removed max-width here — controlled by the v2.6.0 outer-only rule below */
.message-row .message,
.message-row [class*="message-bubble"] {
    width: fit-content !important;
    display: inline-block !important;
}

/* bubble-wrap is the main scroll container - MUST be full width */
.bubble-wrap,
[class*="bubble-wrap"] {
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
}

/* Global Styles */
.gradio-container {
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* Header Bar - Purple Gradient */
.header-bar {
    background: linear-gradient(90deg, #4F46E5, #7C3AED) !important;
    padding: 12px 20px !important;
    margin: -10px -10px 0 -10px !important;
    border-radius: 0 !important;
}

.header-bar h1 {
    color: white !important;
    font-size: 18px !important;
    margin: 0 !important;
    font-weight: bold !important;
}

.header-icons {
    display: flex;
    gap: 8px;
}

.header-icon-btn {
    background: rgba(255,255,255,0.2) !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 4px 8px !important;
    color: white !important;
    min-width: 36px !important;
}

/* Sidebar - Dark Gray */
.sidebar-container {
    background: #1F2937 !important;
    min-height: calc(100vh - 120px) !important;
    padding: 15px !important;
    border-radius: 0 !important;
}

.sidebar-title,
.sidebar-title *,
.sidebar-title h3,
.sidebar-title p,
.sidebar-title span,
.sidebar-title .prose,
.sidebar-title .md,
.sidebar-container .sidebar-title,
.sidebar-container .sidebar-title *,
.sidebar-container h3,
.sidebar-container p,
.sidebar-container .prose,
.sidebar-container .md,
.sidebar-container span.md,
.sidebar-container [class*="prose"],
.sidebar-container [class*="md"] {
    color: #D1D5DB !important;
    font-size: 12px !important;
    font-weight: bold !important;
    margin-bottom: 10px !important;
}

/* Sidebar dropdown labels - lighter for readability */
.sidebar-container label,
.sidebar-container label span,
.sidebar-container .svelte-jdcl7l,
.sidebar-container [class*="container"] > span {
    color: #9CA3AF !important;
}

/* Navigation Buttons */
.nav-btn-active {
    background: #3B82F6 !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 12px !important;
    width: 100% !important;
    text-align: left !important;
    margin-bottom: 8px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
}

.nav-btn-active:hover {
    background: #2563EB !important;
}

.nav-btn-disabled {
    background: #374151 !important;
    color: #6B7280 !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 10px !important;
    width: 100% !important;
    text-align: left !important;
    margin-bottom: 6px !important;
    cursor: not-allowed !important;
}

/* LLM Settings Panel */
.llm-settings-panel {
    background: #374151 !important;
    border-radius: 6px !important;
    padding: 12px !important;
    margin-top: 15px !important;
}

.llm-settings-panel label {
    color: #9CA3AF !important;
    font-size: 10px !important;
}

.llm-settings-panel select, .llm-settings-panel input {
    background: #1F2937 !important;
    color: white !important;
    border: none !important;
    border-radius: 4px !important;
}

/* Main Chat Area - Light background to contrast with dark sidebar */
.chat-container {
    background: #F9FAFB !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    border: none !important;
    min-height: calc(100vh - 180px) !important;
    padding: 0 !important;  /* No padding - scrollbar flush with edge */
    overflow: hidden !important;
    max-width: 100% !important;
    width: 100% !important;
    box-sizing: border-box !important;
    margin-right: 0 !important;
}

/* Force all children of chat-container to respect boundaries */
.chat-container > *,
.chat-container > * > * {
    max-width: 100% !important;
    box-sizing: border-box !important;
}

.chat-header {
    background: #F9FAFB !important;
    padding: 12px 20px !important;
    border-radius: 0 !important;
    border: none !important;
    border-bottom: 1px solid #E5E7EB !important;
}

.chat-header h3 {
    margin: 0 !important;
    color: #374151 !important;
    font-size: 14px !important;
    font-weight: 600 !important;
}

/* ============================================
   Chatbot Styles - Match SVG Design Exactly
   SVG: Main-Agent-UI-Mockup.svg
   AI Message: #EFF6FF, no border, no shadow
   User Message: #DBEAFE, no border, no shadow
   
   Gradio 6.x uses specific class patterns for messages
   ============================================ */

/* NUCLEAR OPTION: Remove ALL shadows from entire page */
* {
    box-shadow: none !important;
    -webkit-box-shadow: none !important;
    -moz-box-shadow: none !important;
}

/* Re-add shadows ONLY where needed (buttons, etc) */
.nav-btn-active {
    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
}

/* Main chatbot container - white background for contrast */
.chatbot-container {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    margin: 12px 0px 12px 12px !important;  /* No right margin - scrollbar flush with border */
    box-shadow: none !important;
    overflow: hidden !important;
    max-width: calc(100% - 12px) !important;
    width: calc(100% - 12px) !important;
    position: relative !important;
}

/* Gradio 6.x Chatbot inner wrappers - CRITICAL for overflow control */
.chatbot-container > div,
.chatbot-container > div > div,
.chatbot-container [class*="chatbot"],
.chatbot-container [class*="wrap"] {
    background: #FFFFFF !important;
    box-shadow: none !important;
    border: none !important;
    border-radius: 12px !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    max-width: 100% !important;
    width: 100% !important;
}

/* Chatbot scroll area */
[data-testid="chatbot"],
.gradio-chatbot {
    background: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 10px !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    max-width: 100% !important;
    width: 100% !important;
}

/* Message rows - prevent overflow */
.chatbot-container [class*="message-row"],
.chatbot-container [class*="row"],
[data-testid="chatbot"] [class*="message-row"] {
    max-width: 100% !important;
    overflow: hidden !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
}

/* ============================================
   Gradio 6.x Chatbot Bubble Styling
   Note: bubble_full_width=False handles sizing
   ============================================ */

/* Bot message - light blue bubble (LINE/WhatsApp style) */
/* v2.6.0: padding 8px 12px for centered text within bubble */
.bot-row .message,
[class*="bot-row"] .message,
.chatbot-container .message.bot,
.chatbot-container .message[class*="bot"] {
    background: #EFF6FF !important;
    border-radius: 16px !important;
    border-bottom-left-radius: 4px !important;
    padding: 8px 12px !important;
    box-shadow: none !important;
    border: none !important;
}

/* User message - slightly darker blue (LINE/WhatsApp style) */
/* v2.6.0: padding 8px 12px for centered text within bubble */
.user-row .message,
[class*="user-row"] .message,
.chatbot-container .message.user,
.chatbot-container .message[class*="user"] {
    background: #DBEAFE !important;
    border-radius: 16px !important;
    border-bottom-right-radius: 4px !important;
    padding: 8px 12px !important;
    box-shadow: none !important;
    border: none !important;
}

/* LINE/WhatsApp style: prevent vertical text on short messages */
.chatbot-container .message,
.chatbot-container .message.user,
.chatbot-container .message.bot,
.chatbot-container [class*="message"],
[class*="message-row"] .message,
.message-row .message {
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    writing-mode: horizontal-tb !important;
    min-width: 60px !important;
}

/* Also target Gradio's panel-full-width messages */
.chatbot-container .panel-full-width,
.chatbot-container .message.panel-full-width {
    min-width: 60px !important;
    white-space: pre-wrap !important;
    word-break: break-word !important;
    writing-mode: horizontal-tb !important;
}

/* Text styling inside messages */
.message-row .message,
.message-row .message p,
.message-row .message span,
.message-row .message li {
    color: #1F2937 !important;
    text-align: left !important;
}

/* Clickable button in chat - styled link */
.chatbot-container a[href*="localhost"] {
    display: inline-block !important;
    background: #3B82F6 !important;
    color: white !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
    text-decoration: none !important;
    font-weight: bold !important;
    margin: 10px 0 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
}

.chatbot-container a[href*="localhost"]:hover {
    background: #2563EB !important;
    transform: translateY(-1px) !important;
}

/* Text colors - dark for readability on light backgrounds */
.chatbot-container [class*="bot"] p,
.chatbot-container [class*="bot"] span,
.chatbot-container [class*="bot"] li,
.chatbot-container [class*="bot"] div,
[role="assistant"] p,
[role="assistant"] span {
    color: #1F2937 !important;
}

.chatbot-container [class*="user"] p,
.chatbot-container [class*="user"] span,
[role="user"] p,
[role="user"] span {
    color: #1F2937 !important;
}

/* Bot message title - darker */
.chatbot-container [class*="bot"] strong,
.chatbot-container [class*="bot"] b,
[role="assistant"] strong {
    color: #312E81 !important;
}

/* Lists */
.chatbot-container ul,
.chatbot-container ol,
.chatbot-container li {
    color: #1F2937 !important;
}

/* Remove shadows from avatars and icons */
.chatbot-container [class*="avatar"],
.chatbot-container [class*="icon"],
.chatbot-container img {
    box-shadow: none !important;
    border: none !important;
}

/* HIDE chatbot message action buttons (like, copy, retry) 
   Note: Be specific to chatbot-container to avoid hiding input controls */
.chatbot-container [class*="icon-button"],
.chatbot-container [class*="icon_button"],
.chatbot-container [class*="message-action"],
.chatbot-container [class*="toolbar"],
[data-testid="chatbot"] [class*="toolbar"],
[data-testid="chatbot"] [class*="icon-button"],
.chatbot-container .message-actions,
.chatbot-container .copy-button,
.chatbot-container [class*="likeable"],
.chatbot-container [class*="like"],
.chatbot-container [class*="dislike"] {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}

/* Chat Input - light theme matching chat area, NO SHADOW */
.chat-input-container {
    background: #F3F4F6 !important;
    border-radius: 8px !important;
    padding: 8px !important;
    margin: 12px 0px 12px 12px !important;  /* No right margin - align with chatbot container */
    border: 1px solid #E5E7EB !important;
    max-width: calc(100% - 12px) !important;
    box-shadow: none !important;
}

.chat-input-container input,
.chat-input-container textarea,
.chat-input-container [class*="textbox"],
.chat-input-container [class*="multimodal"] {
    background: #FFFFFF !important;
    color: #1F2937 !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 6px !important;
    box-shadow: none !important;
}

/* Remove shadow from ALL input-related elements */
.chat-input-container *,
[class*="multimodal-textbox"] *,
[class*="input-container"] * {
    box-shadow: none !important;
}

.chat-input-container input::placeholder,
.chat-input-container textarea::placeholder {
    color: #9CA3AF !important;
}

.send-btn {
    background: #6366F1 !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 8px 16px !important;
}

.send-btn:hover {
    background: #4F46E5 !important;
}

/* Status Bar */
.status-bar {
    background: #1F2937 !important;
    padding: 10px 20px !important;
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    display: flex !important;
    align-items: center !important;
    gap: 20px !important;
    z-index: 1000 !important;
}

.status-bar span {
    color: #9CA3AF !important;
    font-size: 11px !important;
}

.status-ok {
    color: #10B981 !important;
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #10B981;
    border-radius: 50%;
    margin-right: 5px;
}

/* Action Button */
.action-btn {
    background: #3B82F6 !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 10px 20px !important;
    font-weight: bold !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
}

.action-btn:hover {
    background: #2563EB !important;
}

/* Footer spacing for status bar */
.main-content {
    margin-bottom: 50px !important;
}

/* Clear Button - in chat header */
.clear-btn {
    background: #EF4444 !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 6px 12px !important;
    font-size: 12px !important;
    cursor: pointer !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
}

.clear-btn:hover {
    background: #DC2626 !important;
}

/* Chat header layout - flex with space between */
.chat-header {
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
    background: #F9FAFB !important;
    padding: 12px 20px !important;
    border-radius: 0 !important;
    border: none !important;
    border-bottom: 1px solid #E5E7EB !important;
}

/* Fix message bubble - remove outer wrapper background */
.chatbot-container > div > div > div,
[data-testid="chatbot"] > div > div,
.gradio-chatbot > div > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* Message wrapper - no background */
[data-testid="chatbot"] [class*="message-wrap"],
[data-testid="chatbot"] [class*="wrapper"],
.chatbot-container [class*="message-wrap"],
.chatbot-container [class*="wrapper"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

/* Message bubbles - FIT CONTENT, not fixed width */
/* v2.6.0: Only constrain OUTER message bubble. Uses .chatbot-container (NOT [data-testid]) */
/* OUTER .message: max-width 90%, fit-content */
.chatbot-container .message-row .flex-wrap > .message {
    max-width: 90% !important;
    width: fit-content !important;
    min-width: 60px !important;
    overflow-wrap: break-word !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
    hyphens: auto !important;
}

/* INNER nested .message (panel-full-width) and .message-content: NO constraint */
.chatbot-container .message-row .message .message,
.chatbot-container .message-row .message .message-content,
.chatbot-container .message-row .message .message.panel-full-width {
    max-width: 100% !important;
    width: auto !important;
    min-width: 0 !important;
    padding: 0px !important;
    background: transparent !important;
}

/* .flex-wrap.role container: transparent background so bubble color shows */
.chatbot-container .message-row .flex-wrap.role,
.chatbot-container .message-row [class*="flex-wrap"][class*="role"] {
    background: transparent !important;
}

/* .md.prose inside message: transparent background */
.chatbot-container .message-row .message .md,
.chatbot-container .message-row .message .prose,
.chatbot-container .message-row .message span.md {
    background: transparent !important;
}

/* Message row alignment */
.chatbot-container [class*="bot-row"],
.chatbot-container [class*="user-row"] {
    display: flex !important;
    width: 100% !important;
}

/* Bot messages align left */
.chatbot-container [class*="bot-row"] {
    justify-content: flex-start !important;
}

/* User messages align right */
.chatbot-container [class*="user-row"] {
    justify-content: flex-end !important;
}

/* Bubble content - fit content, not full width */
.chatbot-container [class*="message"] p,
.chatbot-container [class*="message"] span,
.chatbot-container [class*="message"] div,
.chatbot-container [class*="message"] li,
.chatbot-container [class*="message"] pre,
.chatbot-container [class*="message"] code {
    max-width: 100% !important;
    width: auto !important;
    overflow-wrap: break-word !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
    white-space: pre-wrap !important;
}

/* Hide Gradio built-in refresh/undo button (bottom left ↺ button) 
   Note: Be careful not to hide the send button or multimodal textbox buttons */
[data-testid="undo-btn"],
[data-testid="retry-btn"],
[data-testid="clear-btn"],
button[aria-label="Undo"],
button[aria-label="Retry"],
/* Only hide icon buttons in chatbot area, not in input area */
.chatbot-container button[class*="undo"],
.chatbot-container button[class*="retry"] {
    display: none !important;
    visibility: hidden !important;
}

/* Ensure MultimodalTextbox is visible */
.chat-input-container,
.chat-input-container textarea,
.chat-input-container input,
.chat-input-container [class*="multimodal"],
.chat-input-container [class*="textbox"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}

/* ============================================
   FINAL OVERRIDE: Scroll containers MUST be full width
   bubble-wrap and message-wrap are scroll containers, NOT message bubbles.
   They must fill the full chatbot width so the scrollbar appears
   at the right edge of the dialog, flush with the border.
   This MUST come LAST to override any earlier fit-content rules.
   ============================================ */
.chatbot-container .bubble-wrap,
.chatbot-container [class*="bubble-wrap"],
.chatbot-container .message-wrap,
.chatbot-container [class*="message-wrap"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 100% !important;
    display: block !important;
    box-sizing: border-box !important;
}

/* FINAL OVERRIDE: Message rows MUST be flex + full width for left/right alignment */
.chatbot-container .message-row,
.chatbot-container [class*="message-row"] {
    display: flex !important;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}

/* Bot rows: align content to left */
.chatbot-container [class*="bot-row"] {
    justify-content: flex-start !important;
}

/* User rows: align content to right */
.chatbot-container [class*="user-row"] {
    justify-content: flex-end !important;
}

/* FINAL FIX: Prevent vertical text on short messages (e.g. "hi") */
/* Target Gradio's inner panel-full-width div and its children */
/* These are the elements that shrink to near-zero width for short text */
.chatbot-container [class*="panel-full-width"],
.chatbot-container .message > div,
.chatbot-container [class*="message"]:not([class*="message-row"]):not([class*="message-wrap"]) > div {
    min-width: 32px !important;
    writing-mode: horizontal-tb !important;
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

/* ============================================
   v2.6.0 FIX: Chat bubble sizing (FINAL)
   NOTE: [data-testid="chatbot"] does NOT exist in Gradio 6.5.1 DOM.
   Use .chatbot-container as the ancestor selector.
   ============================================ */
"""


# ============================================================
# Sub-Agent Configuration
# ============================================================

SUB_AGENTS = {
    "doc_control": {
        "id": "doc_control",
        "name": "文件管制",
        "name_en": "Document Control",
        "icon": "📄",
        "port": 7860,
        "url": "http://localhost:7860",
        "status": "available",
        "phase": "POC",
        "description": "文件上傳、OCR處理、版本控制",
    },
    "audit": {
        "id": "audit",
        "name": "稽核",
        "name_en": "Audit Management",
        "icon": "🔍",
        "port": 7861,
        "url": "http://localhost:7861",
        "status": "phase2",
        "phase": "Phase 2",
        "description": "稽核管理與追蹤",
    },
    "regulatory": {
        "id": "regulatory",
        "name": "法規事務",
        "name_en": "Regulatory Affairs",
        "icon": "⚖️",
        "port": 7862,
        "url": "http://localhost:7862",
        "status": "phase2",
        "phase": "Phase 2",
        "description": "法規符合性管理",
    },
    "production": {
        "id": "production",
        "name": "生產製造",
        "name_en": "Production Control",
        "icon": "🏭",
        "port": 7863,
        "url": "http://localhost:7863",
        "status": "phase2",
        "phase": "Phase 2",
        "description": "生產流程控制",
    },
    "records": {
        "id": "records",
        "name": "紀錄蒐集",
        "name_en": "Records Collection",
        "icon": "📊",
        "port": 7864,
        "url": "http://localhost:7864",
        "status": "phase2",
        "phase": "Phase 2",
        "description": "品質紀錄蒐集與分析",
    },
}


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """你是 AI-QMS 品質管理系統的主要 AI 助理 (v2.4.0)。

你的職責是協助使用者進行：
1. **子系統導航** - 引導使用者到適當的子系統
2. **文件管制** - 文件上傳、OCR處理、版本控制（支援所有 Office 格式）
3. **LLM 提供商管理** - 切換 13+ AI 提供商
4. **系統狀態** - 監控服務、提供商和文件容量
5. **稽核追蹤** - 查看防篡改稽核記錄

可用子系統：
- 📄 文件管制 (可用) - 請點擊左側「📄 文件管制」按鈕前往
- 🔍 稽核 (Phase 2)
- ⚖️ 法規事務 (Phase 2)
- 🏭 生產製造 (Phase 2)
- 📊 紀錄蒐集 (Phase 2)

支援的文件格式：
- PDF: .pdf
- Word: .docx, .doc
- Excel: .xlsx, .xls
- PowerPoint: .pptx, .ppt
- 圖片: .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp
- 文字: .txt, .md, .csv, .rtf

合規標準：
- ISO 13485:2016
- FDA 21 CFR Part 11
- EU MDR 2017/745

當使用者想要上傳文件或進行文件管理時，請引導他們點擊左側「📄 文件管制」按鈕前往文件管制子系統。
重要：回覆中絕對不要顯示任何 URL 或網址（如 http://localhost:7860），只需引導使用者點擊左側按鈕即可。
"""


# ============================================================
# Helper Functions
# ============================================================


def get_document_count() -> tuple[int, int]:
    """Get current document count and limit"""
    if STORAGE_AVAILABLE:
        try:
            storage = MarkdownStorageManager()
            stats = storage.get_storage_stats()
            return stats.get("total_documents", 0), stats.get(
                "limit", POC_DOCUMENT_LIMIT
            )
        except Exception:
            pass
    return 0, POC_DOCUMENT_LIMIT


def get_provider_choices() -> list[str]:
    """Get list of provider display names"""
    if not DEFAULT_PROVIDERS:
        return ["Ollama (Local)"]

    choices = []
    for provider_id, config in DEFAULT_PROVIDERS.items():
        display_name = config.get("display_name", provider_id)
        if config.get("is_local"):
            display_name += " (Local)"
        choices.append(display_name)
    return choices


def get_model_choices(provider_display_name: str) -> list[str]:
    """Get available models for a provider.

    For local providers (Ollama, LM Studio), dynamically fetches installed models.
    For cloud providers, returns the static list from config.
    """
    import requests

    if not DEFAULT_PROVIDERS:
        return ["qwen2.5:7b"]

    # Map display name back to provider_id
    for provider_id, config in DEFAULT_PROVIDERS.items():
        display = config.get("display_name", provider_id)
        if config.get("is_local"):
            display += " (Local)"
        if display == provider_display_name:
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
                    pass  # Fall back to static list

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
                    pass  # Fall back to static list

            # Return static list for cloud providers or if dynamic fetch failed
            return config.get(
                "available_models", [config.get("default_model", "default")]
            )

    return ["default"]


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


def check_service_status(url: str) -> bool:
    """Check if a service is running"""
    import requests

    try:
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def start_sub_agent_if_needed() -> tuple[bool, str]:
    """
    Check if Sub-Agent is running, if not, start it.
    Returns (success, message)
    """
    import subprocess
    import time

    sub_agent_url = "http://localhost:7860"

    # Check if already running
    if check_service_status(sub_agent_url):
        return True, "Sub-Agent 已在運行中"

    # Try to start Sub-Agent
    try:
        project_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        python_exe = sys.executable

        # Start sub-agent in background
        subprocess.Popen(
            [python_exe, "-m", "src.gradio_apps.doc_control"],
            cwd=project_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        # Wait for it to start (max 10 seconds)
        for _ in range(20):
            time.sleep(0.5)
            if check_service_status(sub_agent_url):
                return True, "Sub-Agent 已成功啟動"

        return False, "Sub-Agent 啟動超時，請手動啟動"

    except Exception as e:
        return False, f"無法啟動 Sub-Agent: {str(e)}"


# ============================================================
# Chat Function
# ============================================================


def chat_with_llm(
    message: str, history: list, provider_name: str, model_name: str, api_key: str = ""
) -> Generator[str, None, None]:
    """Chat with LLM using streaming"""

    if not message.strip():
        yield ""
        return

    # Handle simple commands locally
    msg_lower = message.lower()

    if "狀態" in message or "status" in msg_lower:
        doc_count, doc_limit = get_document_count()
        doc_control_status = (
            "運行中" if check_service_status("http://localhost:7860") else "未啟動"
        )
        yield f"""📊 **系統狀態**

- **文件管制子系統**: {doc_control_status}
- **文件數量**: {doc_count}/{doc_limit}
- **LLM 提供商**: {provider_name}
- **模型**: {model_name}
- **OCR**: 就緒

合規標準: ISO 13485:2016, FDA 21 CFR Part 11, EU MDR 2017/745"""
        return

    if "幫助" in message or "help" in msg_lower:
        yield """🤖 **AI-QMS 助理使用指南**

**可用功能：**
1. 輸入「狀態」- 查看系統狀態
2. 輸入「文件」- 開啟文件管制系統
3. 輸入「列表」- 查看已儲存文件
4. 輸入「搜尋 關鍵字」- 搜尋文件內容
5. 輸入「作廢 文件編號」- 作廢文件 (如: 作廢 OTHER-016)
6. 直接提問 - AI 將協助回答
7. 輸入「稽核紀錄」- 查看所有操作紀錄
8. 輸入「下載稽核紀錄 word」或「下載稽核紀錄 excel」- 匯出紀錄

**子系統導航：**
- 點擊左側「📄 文件管制」按鈕開啟文件管理介面
- 其他子系統將在 Phase 2 開放

**支援格式：**
PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""
        return

    # v2.5.4: More specific matching - only trigger for short direct commands
    # Avoid matching general questions that happen to contain "文件"
    is_doc_command = (
        message.strip() in ["文件", "文件管制", "開啟文件", "上傳"]
        or "上傳" in message
        or "document" in msg_lower
        or ("文件管制" in message and len(message.strip()) <= 10)
    )
    if is_doc_command:
        # Check and start sub-agent if needed
        success, status_msg = start_sub_agent_if_needed()

        if success:
            yield f"""📄 **文件管制系統**

✅ {status_msg}

請點擊左側「📄 文件管制」按鈕前往文件管制系統。

**功能：**
• 文件上傳與 OCR 處理
• 版本控制與進版管理
• 簽章確認流程
• Markdown 轉換與下載

**支援格式：** PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""
        else:
            yield f"""📄 **文件管制系統**

⚠️ {status_msg}

請先手動啟動 Sub-Agent：
1. 開啟新的命令提示字元
2. 執行 `start_sub_agent.bat`

**功能：**
• 文件上傳與 OCR 處理
• 版本控制與進版管理
• 簽章確認流程
• Markdown 轉換與下載

**支援格式：** PDF, Word, Excel, PowerPoint, 圖片, 文字檔"""
        return

    if (
        "列表" in message
        or "list" in msg_lower
        or "清單" in message
        or "所有文件" in message
    ):
        if STORAGE_AVAILABLE:
            try:
                md_service = MarkdownStoreService()
                docs = md_service.list_documents()
                stats = md_service.get_stats()
                if docs:
                    doc_lines = []
                    for d in docs:
                        status_str = d.get("status", "active")
                        status_display = (
                            "🗑️ 已作廢" if status_str == "obsolete" else "✅ 有效"
                        )
                        doc_lines.append(
                            f"| {d['doc_id']} | {d.get('title', 'N/A')} | {d['doc_type']} | v{d['current_version']} | {status_display} |"
                        )
                    doc_list = "\n".join(doc_lines)
                    active_count = sum(
                        1 for d in docs if d.get("status", "active") == "active"
                    )
                    obsolete_count = sum(
                        1 for d in docs if d.get("status") == "obsolete"
                    )
                    yield f"""📋 **已儲存文件清單** (共 {stats.get("total_documents", len(docs))} 份，有效 {active_count} 份{f"，已作廢 {obsolete_count} 份" if obsolete_count else ""})

| 文件編號 | 標題 | 類型 | 版本 | 狀態 |
|---------|------|------|------|------|
{doc_list}

💡 輸入「搜尋 關鍵字」可搜尋文件內容
💡 輸入「作廢 文件編號」可作廢文件"""
                else:
                    yield "📋 目前沒有已儲存的文件。\n\n請點擊左側「📄 文件管制」按鈕前往文件管制子系統上傳文件。"
            except Exception as e:
                yield f"無法讀取文件列表: {str(e)}"
        else:
            yield "儲存系統未初始化。"
        return

    if "搜尋" in message or "search" in msg_lower:
        query = message.replace("搜尋", "").replace("search", "").strip()
        if query and STORAGE_AVAILABLE:
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
                    yield f"🔍 **搜尋「{query}」結果** (共 {len(results)} 筆)\n\n{result_list}"
                else:
                    yield f"🔍 找不到包含「{query}」的文件。\n\n請確認關鍵字是否正確，或嘗試其他搜尋詞。"
            except Exception as e:
                yield f"搜尋失敗: {str(e)}"
        elif not query:
            yield "請輸入搜尋關鍵字，例如：搜尋 品質手冊"
        else:
            yield "儲存系統未初始化。"
        return

    if "作廢" in message or "obsolete" in msg_lower:
        import re as _re_obs

        obs_doc_id_match = _re_obs.search(
            r"(SOP-\d+|WI-\d+|FORM-\d+|DHF-\d+|OTHER-\d+)",
            message,
            _re_obs.IGNORECASE,
        )
        if obs_doc_id_match and STORAGE_AVAILABLE:
            obs_doc_id = obs_doc_id_match.group(1).upper()
            obs_reason_text = message
            for kw in ["作廢", "obsolete", obs_doc_id_match.group(0)]:
                obs_reason_text = obs_reason_text.replace(kw, "")
            obs_reason = obs_reason_text.strip() or "使用者手動作廢"

            md_service = MarkdownStoreService()
            obs_result = md_service.obsolete_document(
                doc_id=obs_doc_id,
                reason=obs_reason,
                user_id="main_agent_user",
            )
            if obs_result.get("success"):
                if AUDIT_AVAILABLE:
                    audit_log = ImmutableAuditLog()
                    audit_log.create_record(
                        action="DOCUMENT_OBSOLETED",
                        document_id=obs_doc_id,
                        user_id="main_agent_user",
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
                yield (
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
                yield f"❌ 作廢失敗: {obs_result.get('error', '未知錯誤')}"
        elif not obs_doc_id_match and STORAGE_AVAILABLE:
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
                yield (
                    f"請指定要作廢的文件編號。\n\n"
                    f"**目前有效文件** ({len(active_docs)} 份):\n\n"
                    f"| 文件編號 | 標題 | 類型 | 版本 |\n"
                    f"|---------|------|------|------|\n"
                    f"{doc_list}\n\n"
                    f"範例：輸入「作廢 OTHER-016」或「作廢 OTHER-016 已被新版取代」"
                )
            else:
                yield "目前沒有可作廢的文件。"
        else:
            yield "儲存系統未初始化。"
        return

    # For other messages, try to use LLM with Markdown DB context
    if LLM_AVAILABLE:
        try:
            provider_id = get_provider_id_from_display(provider_name)

            # Set API key if provided
            if api_key:
                env_key = DEFAULT_PROVIDERS.get(provider_id, {}).get("env_key_name", "")
                if env_key:
                    os.environ[env_key] = api_key

            manager = create_provider_manager(provider_id)

            # Search Markdown DB for relevant context
            db_context = ""
            ref_docs = []
            if STORAGE_AVAILABLE:
                try:
                    md_service = MarkdownStoreService()
                    search_results = md_service.search(message, limit=3)
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
                except Exception as search_err:
                    print(f"[WARN] Markdown DB search failed: {search_err}")

            # Build system prompt with DB context
            system_content = SYSTEM_PROMPT
            if db_context:
                system_content += db_context
                system_content += "\n\n請根據上述文件內容回答使用者的問題。如果文件中沒有相關資訊，請明確告知，不要編造答案。"
            else:
                system_content += "\n\n目前文件資料庫中沒有找到與此問題相關的文件。請根據你的知識回答，但提醒使用者可以上傳相關文件到系統中。"

            # Build messages
            messages = [{"role": "system", "content": system_content}]

            # Handle both Gradio 6.x dict format and legacy tuple format
            for h in history:
                if isinstance(h, dict):
                    # Gradio 6.x format: {"role": "user/assistant", "content": "..."}
                    role = h.get("role", "user")
                    content = h.get("content", "")
                    if content:
                        messages.append({"role": role, "content": content})
                elif isinstance(h, (list, tuple)) and len(h) >= 2:
                    # Legacy tuple format: (user_msg, assistant_msg)
                    if h[0]:
                        messages.append({"role": "user", "content": h[0]})
                    if h[1]:
                        messages.append({"role": "assistant", "content": h[1]})

            messages.append({"role": "user", "content": message})

            # Try streaming completion (timeout=30s to avoid long hangs)
            response = manager.completion(
                messages=messages,
                model=model_name,
                temperature=0.7,
                max_tokens=2000,
                stream=True,
                timeout=30,
            )

            # Handle streaming response
            full_response = ""
            try:
                for chunk in response:
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            full_response += delta.content
                            yield full_response
            except Exception as stream_err:
                # If streaming fails, yield error
                if full_response:
                    yield full_response + f"\n\n[串流中斷: {str(stream_err)}]"
                else:
                    yield f"[串流錯誤: {str(stream_err)}]"
                return

            # If no content was received, show a message
            if not full_response:
                yield "抱歉，未收到 LLM 回應。請檢查模型是否可用。"
            elif ref_docs:
                yield full_response + "\n\n📚 參考文件: " + ", ".join(ref_docs)

        except Exception as e:
            import traceback

            error_detail = str(e) if str(e) else repr(e)
            error_type = type(e).__name__

            # Log full error for debugging
            print(f"[ERROR] LLM Error: {error_type}: {error_detail}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")

            # Provide more helpful error messages
            error_lower = error_detail.lower()
            if "not found" in error_lower or "does not exist" in error_lower:
                error_hint = "模型未找到，請確認模型名稱正確或嘗試其他模型"
            elif "connection" in error_lower or "connect" in error_lower:
                error_hint = "無法連接到 LLM 服務，請確認服務已啟動"
            elif "api_key" in error_lower or "apikey" in error_lower:
                error_hint = "API Key 無效或未設定"
            elif "timeout" in error_lower:
                error_hint = "連線逾時，請稍後再試"
            elif "memory" in error_lower or "oom" in error_lower:
                error_hint = "記憶體不足，請嘗試較小的模型"
            elif not error_detail or error_detail == "0":
                error_hint = "未知錯誤，請檢查終端機輸出以獲取詳細資訊"
                error_detail = f"{error_type}: 無詳細錯誤訊息"
            else:
                error_hint = "請檢查 LLM 設定或嘗試其他提供商"

            yield f"""我是 AI-QMS 品質管理系統助理。

您的問題：{message}

⚠️ LLM 連線發生問題 ({error_type})：
{error_detail}

💡 建議：{error_hint}

您可以：
- 輸入「狀態」查看系統狀態
- 輸入「幫助」獲取使用指南
- 點擊左側「📄 文件管制」開啟文件管理"""
    else:
        yield f"""我是 AI-QMS 品質管理系統助理。

您的問題：{message}

LLM 模組未載入，但您仍可使用以下功能：
- 輸入「狀態」查看系統狀態
- 輸入「幫助」獲取使用指南
- 點擊左側「📄 文件管制」開啟文件管理"""


# ============================================================
# Create Main Interface
# ============================================================


def create_main_agent_interface():
    """Create the Main Agent Gradio interface matching SVG design"""

    if not GRADIO_AVAILABLE:
        raise RuntimeError("Gradio not available")

    # Get initial values
    doc_count, doc_limit = get_document_count()
    provider_choices = get_provider_choices()
    default_provider = provider_choices[0] if provider_choices else ""
    default_models = get_model_choices(default_provider) if default_provider else []

    # Gradio 6.x: css must be in launch(), not Blocks()
    with gr.Blocks(title="AI-QMS 品質管理系統") as demo:
        # ============================================================
        # Header Bar
        # ============================================================
        with gr.Row(elem_classes=["header-bar"]):
            gr.Markdown("# 🏥 AI-QMS 品質管理系統", elem_classes=["header-title"])
            with gr.Row(elem_classes=["header-icons"]):
                gr.Button("⚙️", elem_classes=["header-icon-btn"], scale=0, min_width=40)
                gr.Button("👤", elem_classes=["header-icon-btn"], scale=0, min_width=40)
                gr.Button("🔔", elem_classes=["header-icon-btn"], scale=0, min_width=40)

        # ============================================================
        # Main Layout: Sidebar + Content
        # ============================================================
        with gr.Row(elem_classes=["main-content"]):
            # --------------------------------------------------------
            # Left Sidebar
            # --------------------------------------------------------
            with gr.Column(scale=1, min_width=220, elem_classes=["sidebar-container"]):
                # Sub-Agent Navigation
                gr.Markdown("### 📋 子系統導航", elem_classes=["sidebar-title"])

                # Document Control - Active
                doc_control_btn = gr.Button(
                    "📄 文件管制",
                    elem_classes=["nav-btn-active"],
                    size="lg",
                )

                # Other sub-agents - Disabled
                gr.Button(
                    "🔍 稽核 (Phase 2)",
                    elem_classes=["nav-btn-disabled"],
                    interactive=False,
                )
                gr.Button(
                    "⚖️ 法規事務 (Phase 2)",
                    elem_classes=["nav-btn-disabled"],
                    interactive=False,
                )
                gr.Button(
                    "🏭 生產製造 (Phase 2)",
                    elem_classes=["nav-btn-disabled"],
                    interactive=False,
                )
                gr.Button(
                    "📊 紀錄蒐集 (Phase 2)",
                    elem_classes=["nav-btn-disabled"],
                    interactive=False,
                )

                gr.Markdown("---")

                # LLM Settings
                gr.Markdown("### ⚙️ LLM 設定", elem_classes=["sidebar-title"])

                with gr.Column(elem_classes=["llm-settings-panel"]):
                    provider_dropdown = gr.Dropdown(
                        choices=provider_choices,
                        value=default_provider,
                        label="Provider",
                        container=True,
                    )
                    model_dropdown = gr.Dropdown(
                        choices=default_models,
                        value=default_models[0]
                        if default_models
                        else "qwen-lite:latest",
                        label="Model",
                        container=True,
                        allow_custom_value=True,
                    )
                    api_key_input = gr.Textbox(
                        label="API Key",
                        type="password",
                        placeholder="雲端服務需要...",
                        container=True,
                    )

                    # LLM Test Button
                    test_llm_btn = gr.Button(
                        "🔗 LLM 連線", variant="secondary", size="sm"
                    )
                    test_llm_result = gr.Markdown("")

                # Status display in sidebar
                gr.Markdown("---")
                status_display = gr.Markdown(
                    f"📊 文件: {doc_count}/{doc_limit}", elem_classes=["sidebar-title"]
                )

                # Language Settings
                gr.Markdown("---")
                gr.Markdown("### 🌐 語言設定", elem_classes=["sidebar-title"])
                language_dropdown = gr.Dropdown(
                    choices=["繁體中文", "English", "日本語"],
                    value="繁體中文",
                    label="Language",
                    container=True,
                )

                # Language translation map
                LANG_MAP = {
                    "繁體中文": {
                        "chat_title": "### 💬 對話區域",
                        "clear_btn": "🗑️ 清空對話",
                        "chat_placeholder": "輸入訊息或上傳文件/圖片...",
                        "send_btn": "發送",
                        "nav_doc": "📄 文件管制 (POC)",
                        "nav_audit": "🔍 稽核 (Phase 2)",
                        "nav_reg": "⚖️ 法規事務 (Phase 2)",
                        "nav_prod": "🏭 生產製造 (Phase 2)",
                        "nav_record": "📊 紀錄蒐集 (Phase 2)",
                        "llm_title": "### ⚙️ LLM 設定",
                        "test_btn": "🔗 LLM 連線",
                        "lang_title": "### 🌐 語言設定",
                        "welcome": "🤖 **AI 助理**\n\n您好！我是 AI-QMS 品質管理系統助理。\n請問需要什麼協助？\n\n可用功能：\n• 文件上傳與版本控制\n• OCR 文字辨識\n• 關聯文件分析\n\n輸入「幫助」獲取更多資訊。",
                    },
                    "English": {
                        "chat_title": "### 💬 Chat Area",
                        "clear_btn": "🗑️ Clear Chat",
                        "chat_placeholder": "Type a message or upload files/images...",
                        "send_btn": "Send",
                        "nav_doc": "📄 Document Control (POC)",
                        "nav_audit": "🔍 Audit (Phase 2)",
                        "nav_reg": "⚖️ Regulatory Affairs (Phase 2)",
                        "nav_prod": "🏭 Manufacturing (Phase 2)",
                        "nav_record": "📊 Records Collection (Phase 2)",
                        "llm_title": "### ⚙️ LLM Settings",
                        "test_btn": "🔗 LLM Connection",
                        "lang_title": "### 🌐 Language Settings",
                        "welcome": "🤖 **AI Assistant**\n\nHello! I am the AI-QMS Quality Management System assistant.\nHow can I help you?\n\nAvailable features:\n• Document upload & version control\n• OCR text recognition\n• Related document analysis\n\nType 'help' for more information.",
                    },
                    "日本語": {
                        "chat_title": "### 💬 チャットエリア",
                        "clear_btn": "🗑️ チャット消去",
                        "chat_placeholder": "メッセージを入力、またはファイル/画像をアップロード...",
                        "send_btn": "送信",
                        "nav_doc": "📄 文書管理 (POC)",
                        "nav_audit": "🔍 監査 (Phase 2)",
                        "nav_reg": "⚖️ 薬事規制 (Phase 2)",
                        "nav_prod": "🏭 製造管理 (Phase 2)",
                        "nav_record": "📊 記録収集 (Phase 2)",
                        "llm_title": "### ⚙️ LLM 設定",
                        "test_btn": "🔗 LLM接続",
                        "lang_title": "### 🌐 言語設定",
                        "welcome": "🤖 **AIアシスタント**\n\nこんにちは！AI-QMS品質管理システムアシスタントです。\nどのようなお手伝いができますか？\n\n利用可能な機能：\n• 文書アップロードとバージョン管理\n• OCRテキスト認識\n• 関連文書分析\n\n「ヘルプ」と入力すると詳細情報が表示されます。",
                    },
                }

                def change_language(lang):
                    """Update UI elements when language changes"""
                    t = LANG_MAP.get(lang, LANG_MAP["繁體中文"])
                    return (
                        t["chat_title"],
                        gr.Button(value=t["clear_btn"]),
                        gr.Button(value=t["test_btn"]),
                        gr.Button(value=t["send_btn"]),
                        [{"role": "assistant", "content": t["welcome"]}],
                    )

            # --------------------------------------------------------
            # Main Content Area
            # --------------------------------------------------------
            with gr.Column(scale=4, elem_classes=["chat-container"]):
                # Chat Header with Clear Button
                with gr.Row(elem_classes=["chat-header"]):
                    with gr.Column(scale=1):
                        chat_title_md = gr.Markdown("### 💬 對話區域")
                    clear_btn = gr.Button(
                        "🗑️ 清空對話",
                        elem_classes=["clear-btn"],
                        scale=0,
                        min_width=100,
                    )

                # Chatbot
                # Gradio 6.x: type="messages" is now default and removed as parameter
                # Gradio 6.x: layout="bubble" for bubble-style chat
                chatbot = gr.Chatbot(
                    value=[
                        {
                            "role": "assistant",
                            "content": """🤖 **AI 助理**

您好！我是 AI-QMS 品質管理系統助理。
請問需要什麼協助？

可用功能：
• 文件上傳與版本控制
• OCR 文字辨識
• 關聯文件分析

輸入「幫助」獲取更多資訊。""",
                        }
                    ],
                    height=450,
                    layout="bubble",  # Gradio 6.x: 使用 bubble 佈局
                    elem_classes=["chatbot-container"],
                    show_label=False,
                )

                # Chat Input - v2.4.8: Multimodal support for file/image upload
                with gr.Row(elem_classes=["chat-input-container"]):
                    # v2.4.8: Use MultimodalTextbox for file upload support
                    chat_input = gr.MultimodalTextbox(
                        placeholder="輸入訊息或上傳文件/圖片...",
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
                        scale=6,
                    )

                    send_btn = gr.Button(
                        "發送 ➤", elem_classes=["send-btn"], scale=0, min_width=80
                    )

                # v2.6.0: File download component for audit export
                file_download = gr.File(
                    label="📥 檔案下載",
                    visible=False,
                    interactive=False,
                )

        # ============================================================
        # Status Bar (Fixed at bottom)
        # ============================================================
        with gr.Row(elem_classes=["status-bar"]):
            gr.HTML(f"""
                <span>📊 系統狀態:</span>
                <span class="status-ok"><span class="status-dot"></span>正常</span>
                <span>|</span>
                <span>LLM: {default_provider}</span>
                <span>|</span>
                <span>文件數: {doc_count}/{doc_limit}</span>
                <span>|</span>
                <span>OCR: 就緒</span>
            """)

        # ============================================================
        # Event Handlers
        # ============================================================

        def open_doc_control():
            """
            Open Document Control sub-agent.
            If not running, start it first, then open in new tab.
            Returns status message for chatbot.
            """
            success, message = start_sub_agent_if_needed()
            if success:
                return [
                    {
                        "role": "assistant",
                        "content": f"✅ {message}\n\n正在開啟文件管制系統...",
                    }
                ]
            else:
                return [
                    {
                        "role": "assistant",
                        "content": f"⚠️ {message}\n\n請手動執行 start_sub_agent.bat",
                    }
                ]

        # Open sub-agent: first ensure it's running, then open in new tab
        doc_control_btn.click(
            open_doc_control,
            inputs=None,
            outputs=[chatbot],
        ).then(
            None,
            None,
            None,
            js="() => { setTimeout(() => window.open('http://localhost:7860', '_blank'), 500); }",
        )

        def update_models(provider_name):
            """Update model dropdown based on provider"""
            models = get_model_choices(provider_name)
            return gr.update(
                choices=models,
                value=models[0] if models else "default",
                allow_custom_value=True,
            )

        def respond(message, history, provider, model, api_key):
            """
            Handle chat response with streaming (Gradio 6.x messages format)
            v2.4.8: Support multimodal input (text + files)

            Note: Files uploaded here are for Q&A only, NOT saved to Markdown DB.
            """
            # v2.4.8: Handle multimodal input from MultimodalTextbox
            # message is a dict: {"text": "...", "files": [...]}
            if isinstance(message, dict):
                text_content = message.get("text", "").strip()
                files = message.get("files", [])
            else:
                # Fallback for plain text
                text_content = str(message).strip() if message else ""
                files = []

            if not text_content and not files:
                yield (
                    history,
                    gr.MultimodalTextbox(value=None),
                    gr.File(value=None, visible=False),
                )
                return

            # Build user message content
            user_content = []

            # Add file references (ephemeral - not saved to DB)
            if files:
                file_info = []
                for f in files:
                    file_path = f if isinstance(f, str) else getattr(f, "name", str(f))
                    file_name = Path(file_path).name if file_path else "unknown"
                    file_info.append(file_name)
                    # Add file to content for display
                    user_content.append({"path": file_path})

                # Add note about files
                if text_content:
                    user_content.append(
                        f"{text_content}\n\n📎 附件: {', '.join(file_info)} (僅供問答，不存入資料庫)"
                    )
                else:
                    user_content.append(
                        f"📎 附件: {', '.join(file_info)} (僅供問答，不存入資料庫)"
                    )
            else:
                user_content.append(text_content)

            # Gradio 6.x uses messages format: {"role": "user/assistant", "content": "..."}
            # For multimodal, content can be a list
            if len(user_content) == 1 and isinstance(user_content[0], str):
                history.append({"role": "user", "content": user_content[0]})
            else:
                history.append({"role": "user", "content": user_content})

            history.append({"role": "assistant", "content": ""})

            # Build prompt with file context if files were uploaded
            prompt = text_content
            if files:
                prompt = f"[用戶上傳了 {len(files)} 個檔案: {', '.join(file_info)}]\n\n{text_content}"

            # v2.6.0: Audit record commands (handle before LLM)
            if AUDIT_AVAILABLE:
                _audit_keywords = ["稽核紀錄", "審計紀錄", "操作紀錄"]
                _audit_dl_word = any(
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
                _audit_dl_excel = any(
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
                _audit_dl_pdf = any(
                    kw in text_content
                    for kw in [
                        "下載稽核紀錄 pdf",
                        "匯出稽核紀錄 pdf",
                        "下載稽核紀錄 PDF",
                        "匯出稽核紀錄 PDF",
                    ]
                )
                _is_audit = (
                    any(kw in text_content for kw in _audit_keywords)
                    or "audit" in text_content.lower()
                )

                if _audit_dl_word or _audit_dl_excel or _audit_dl_pdf or _is_audit:
                    _alog = ImmutableAuditLog()
                    _records = _alog.get_all_records()

                    if _audit_dl_word:
                        if not _records:
                            history[-1]["content"] = (
                                "📋 目前沒有任何稽核紀錄，無法匯出。"
                            )
                            yield (
                                history,
                                gr.MultimodalTextbox(value=None),
                                gr.File(value=None, visible=False),
                            )
                            return
                        _fpath = export_to_word(_records)
                        history[-1]["content"] = (
                            f"📋 已產生稽核紀錄 Word 報告 (共 {len(_records)} 筆紀錄)。\n\n請在下方下載區域下載檔案。"
                        )
                        yield (
                            history,
                            gr.MultimodalTextbox(value=None),
                            gr.File(value=_fpath, visible=True),
                        )
                        return

                    elif _audit_dl_excel:
                        if not _records:
                            history[-1]["content"] = (
                                "📋 目前沒有任何稽核紀錄，無法匯出。"
                            )
                            yield (
                                history,
                                gr.MultimodalTextbox(value=None),
                                gr.File(value=None, visible=False),
                            )
                            return
                        _fpath = export_to_excel(_records)
                        history[-1]["content"] = (
                            f"📋 已產生稽核紀錄 Excel 報告 (共 {len(_records)} 筆紀錄)。\n\n請在下方下載區域下載檔案。"
                        )
                        yield (
                            history,
                            gr.MultimodalTextbox(value=None),
                            gr.File(value=_fpath, visible=True),
                        )
                        return

                    elif _audit_dl_pdf:
                        history[-1]["content"] = (
                            "📋 PDF 匯出功能開發中。\n\n目前支援：\n- 輸入「下載稽核紀錄 word」匯出 Word 格式\n- 輸入「下載稽核紀錄 excel」匯出 Excel 格式"
                        )
                        yield (
                            history,
                            gr.MultimodalTextbox(value=None),
                            gr.File(value=None, visible=False),
                        )
                        return

                    elif _is_audit:
                        _valid, _integrity_msg = _alog.verify_chain_integrity()
                        _table_md = format_audit_table_markdown(_records)
                        if _valid:
                            _table_md += f"\n\n🔒 鏈完整性驗證: ✅ {_integrity_msg}"
                        else:
                            _table_md += f"\n\n🔒 鏈完整性驗證: ❌ {_integrity_msg}"
                        history[-1]["content"] = _table_md
                        yield (
                            history,
                            gr.MultimodalTextbox(value=None),
                            gr.File(value=None, visible=False),
                        )
                        return

            for response in chat_with_llm(
                prompt, history[:-2], provider, model, api_key
            ):
                history[-1]["content"] = response
                yield (
                    history,
                    gr.MultimodalTextbox(value=None),
                    gr.File(value=None, visible=False),
                )

        def update_status():
            """Update status display"""
            doc_count, doc_limit = get_document_count()
            return f"📊 文件: {doc_count}/{doc_limit}"

        # Bind events
        # Note: doc_control_btn.click is bound above with JS

        def clear_chat():
            """Clear chat history and return initial message"""
            return [
                {
                    "role": "assistant",
                    "content": """🤖 **AI 助理**

您好！我是 AI-QMS 品質管理系統助理。
請問需要什麼協助？

可用功能：
• 文件上傳與版本控制
• OCR 文字辨識
• 關聯文件分析

輸入「幫助」獲取更多資訊。""",
                }
            ]

        clear_btn.click(clear_chat, outputs=[chatbot])

        provider_dropdown.change(
            update_models, inputs=[provider_dropdown], outputs=[model_dropdown]
        )

        # LLM Test Connection
        def test_llm_connection(prov_name, mod_name, key):
            """Test LLM connection with user-selected model"""
            try:
                p_id = get_provider_id_from_display(prov_name)
                if key:
                    ek = DEFAULT_PROVIDERS.get(p_id, {}).get("env_key_name", "")
                    if ek:
                        os.environ[ek] = key
                mgr = create_provider_manager(p_id)
                # v2.7.0: Use user-selected model, not provider default
                res = mgr.test_connection(model=mod_name if mod_name else None)
                if res.get("success"):
                    return f"✅ 連線成功！ 提供商: {res['provider']} | 模型: {res['model']} | 延遲: {res['latency_ms']}ms"
                else:
                    return f"❌ 連線失敗 模型: {res.get('model', 'N/A')} | 錯誤: {res.get('error', '未知錯誤')}"
            except Exception as e:
                return f"❌ 測試失敗: {str(e)}"

        test_llm_btn.click(
            test_llm_connection,
            inputs=[provider_dropdown, model_dropdown, api_key_input],
            outputs=[test_llm_result],
        )

        # Language switching
        language_dropdown.change(
            change_language,
            inputs=[language_dropdown],
            outputs=[chat_title_md, clear_btn, test_llm_btn, send_btn, chatbot],
        )

        send_btn.click(
            respond,
            inputs=[
                chat_input,
                chatbot,
                provider_dropdown,
                model_dropdown,
                api_key_input,
            ],
            outputs=[chatbot, chat_input, file_download],
        )

        chat_input.submit(
            respond,
            inputs=[
                chat_input,
                chatbot,
                provider_dropdown,
                model_dropdown,
                api_key_input,
            ],
            outputs=[chatbot, chat_input, file_download],
        )

        # Initial status update on load (Gradio 6.x: 'every' parameter removed)
        demo.load(update_status, outputs=[status_display])

    return demo


# ============================================================
# Launch Function
# ============================================================


def launch_main_agent_app(
    server_name: str = "0.0.0.0", server_port: int = 3000, share: bool = False
):
    """Launch the Main Agent Gradio application"""

    print("=" * 60)
    print("AI-QMS Main Agent - Gradio Interface")
    print("=" * 60)
    print(f"Version: v2.7.0")
    print(f"Server: http://{server_name}:{server_port}")
    print(f"Local: http://localhost:{server_port}")
    print("=" * 60)

    # v2.7.0: Auto-update LLM model lists from provider APIs
    print("[啟動] 正在從各平台 API 更新 LLM 模型清單...")
    try:
        update_results = auto_update_models()
        summary = print_update_summary(update_results)
        print(summary)
    except Exception as e:
        print(f"[警告] 模型清單自動更新失敗: {e}")

    demo = create_main_agent_interface()
    # Gradio 6.x: css must be passed to launch()
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        show_error=True,
        css=CUSTOM_CSS,
    )


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI-QMS Main Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=3000, help="Server port")
    parser.add_argument("--share", action="store_true", help="Create public link")

    args = parser.parse_args()

    launch_main_agent_app(
        server_name=args.host, server_port=args.port, share=args.share
    )
