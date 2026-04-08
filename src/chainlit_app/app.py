"""
AI-QMS Phase 1 - Chainlit Application
======================================

Version: v3.5.0
Updated: 2026-02-27

Single Chainlit app with Chat Profiles:
  - Main Agent: System navigation, document listing, obsolete, audit, LLM chat
  - Doc Control: File upload, OCR, version detection, stamp confirmation

Replaces legacy Gradio UI (removed)
Port: 3000 (single app)
"""

import os
import sys
import re
import json
import time
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================
# Dependency Check — Auto-install missing packages on startup
# ============================================================
# Ensures all required packages from requirements.txt are installed.
# pip install is idempotent: already-installed packages are skipped
# instantly (~1-2s total overhead when everything is up to date).
# This catches cases where users upgrade via git pull but forget
# to re-run pip install, or when start.bat's check was incomplete.
# ============================================================


def _check_and_install_dependencies():
    """Check and auto-install missing dependencies from requirements.txt."""
    project_root = Path(__file__).parent.parent.parent
    requirements_file = project_root / "requirements.txt"

    if not requirements_file.exists():
        return

    # Quick check: test critical packages that are most commonly missing
    critical_packages = {
        "cv2": "opencv-python",
        "litellm": "litellm",
        "chainlit": "chainlit",
        "markitdown": "markitdown",
        "pdf2image": "pdf2image",
        "pypdf": "pypdf",
        "PIL": "Pillow",
        "numpy": "numpy",
        "ddgs": "ddgs",
    }

    missing = []
    for import_name, pip_name in critical_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[INFO] Missing packages detected: {', '.join(missing)}")
        print("[INFO] Auto-installing from requirements.txt...")
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(requirements_file),
                    "--quiet",
                    "--disable-pip-version-check",
                    "--no-deps",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            print("[OK] Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] Auto-install failed: {e}")
            print("[WARN] Please run manually: pip install -r requirements.txt")
        except Exception as e:
            print(f"[WARN] Auto-install error: {e}")


_check_and_install_dependencies()

# ============================================================
# Arize Phoenix - LLM Observability (v3.5.1)
# ============================================================
# IMPORTANT: This block MUST execute BEFORE any `from src.*` imports
# because LiteLLMInstrumentor patches litellm.completion globally,
# and downstream modules capture `completion` at import time.
# If instrumentation happens after import, traces are silently lost.
#
# Multi-Project Architecture:
#   - ai-qms-main        → Main Agent traces
#   - ai-qms-doc-control  → Document Control Sub-Agent traces
#   - ai-qms-audit        → (Future) Audit Sub-Agent traces
# Use get_phoenix_project(profile) + dangerously_using_project()
# to route traces to the correct Phoenix project per-request.
# ============================================================

PHOENIX_ENABLED = False
_phoenix_using_project = None  # Will hold dangerously_using_project if available
_phoenix_using_attributes = None  # Will hold using_attributes if available
_phoenix_tracer = None  # Will hold OTel tracer for custom (non-LLM) spans

# Agent profile → Phoenix project name mapping (extensible for future agents)
PHOENIX_PROJECT_MAP = {
    "主系統 (Main Agent)": "ai-qms-main",
    "文件管制 (Doc Control)": "ai-qms-doc-control",
    # Phase 2: "稽核 (Audit)": "ai-qms-audit",
}
PHOENIX_DEFAULT_PROJECT = "ai-qms-main"


def get_phoenix_project(profile: str = "") -> str:
    """Get Phoenix project name for the given chat profile."""
    return PHOENIX_PROJECT_MAP.get(profile, PHOENIX_DEFAULT_PROJECT)


def _detect_phoenix_endpoint() -> str:
    """Auto-detect Phoenix endpoint by scanning ports 6006-6016.

    Priority:
      1. PHOENIX_COLLECTOR_ENDPOINT env var (set by start.bat / start_chainlit.bat)
      2. Scan ports 6006-6016 for a running Phoenix server
      3. Fallback to default http://localhost:6006/v1/traces
    """
    import socket

    # 1. Check environment variable first (set by .bat launcher)
    env_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if env_endpoint:
        return env_endpoint

    # 2. Scan ports 6006-6016 for a running Phoenix server
    for port in range(6006, 6017):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("localhost", port)) == 0:
                    endpoint = f"http://localhost:{port}/v1/traces"
                    if port != 6006:
                        print(f"[INFO] Phoenix detected on non-default port {port}")
                    return endpoint
        except Exception:
            continue

    # 3. Fallback to default
    return "http://localhost:6006/v1/traces"


try:
    from phoenix.otel import register as phoenix_register
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from openinference.instrumentation import (
        dangerously_using_project,
        using_attributes,
    )

    _phoenix_endpoint = _detect_phoenix_endpoint()

    # Register with default project; per-request routing via dangerously_using_project()
    _phoenix_tracer_provider = phoenix_register(
        project_name=PHOENIX_DEFAULT_PROJECT,
        endpoint=_phoenix_endpoint,
        batch=False,  # Immediate export for debugging; set True in production
    )
    LiteLLMInstrumentor().instrument(tracer_provider=_phoenix_tracer_provider)

    # Get a tracer for custom (non-LLM) spans like web search, OCR, etc.

    _phoenix_tracer = _phoenix_tracer_provider.get_tracer("ai-qms-custom")

    _phoenix_using_project = dangerously_using_project
    _phoenix_using_attributes = using_attributes
    PHOENIX_ENABLED = True
    print(
        f"[OK] Phoenix multi-project tracing enabled → {_phoenix_endpoint}"
        f" (projects: {', '.join(PHOENIX_PROJECT_MAP.values())})"
    )
except ImportError:
    # Auto-install Phoenix packages for users who upgraded via git pull
    print("[INFO] Phoenix packages not found. Auto-installing...")
    try:
        import subprocess as _sp

        _sp.check_call(
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
                "openinference-instrumentation>=0.1.38",
            ],
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
        )
        # Retry after install
        from phoenix.otel import register as phoenix_register
        from openinference.instrumentation.litellm import LiteLLMInstrumentor
        from openinference.instrumentation import (
            dangerously_using_project,
            using_attributes,
        )

        _phoenix_endpoint = _detect_phoenix_endpoint()
        _phoenix_tracer_provider = phoenix_register(
            project_name=PHOENIX_DEFAULT_PROJECT,
            endpoint=_phoenix_endpoint,
            batch=False,
        )
        LiteLLMInstrumentor().instrument(tracer_provider=_phoenix_tracer_provider)

        _phoenix_tracer = _phoenix_tracer_provider.get_tracer("ai-qms-custom")
        _phoenix_using_project = dangerously_using_project
        _phoenix_using_attributes = using_attributes
        PHOENIX_ENABLED = True
        print(
            f"[OK] Phoenix auto-installed and enabled → {_phoenix_endpoint}"
            f" (projects: {', '.join(PHOENIX_PROJECT_MAP.values())})"
        )
    except Exception as auto_err:
        print(f"[INFO] Phoenix auto-install failed ({auto_err}). LLM tracing disabled.")
except Exception as e:
    print(
        f"[WARN] Phoenix tracing init failed: {e}. App will continue without tracing."
    )

from contextlib import contextmanager


@contextmanager
def phoenix_trace(profile: str = "", command: str = ""):
    """Context manager for Phoenix per-request project routing + metadata.

    Usage::

        with phoenix_trace(profile, command="web_search"):
            response = manager.completion(...)  # Traced to correct project

    If Phoenix is disabled, acts as a no-op (nullcontext).
    """
    if not PHOENIX_ENABLED or _phoenix_using_project is None:
        yield
        return

    project_name = get_phoenix_project(profile)
    metadata = {}
    if command:
        metadata["command_type"] = command
    if profile:
        metadata["agent_profile"] = profile

    # Stack: project routing + metadata attributes
    with _phoenix_using_project(project_name=project_name):
        if _phoenix_using_attributes is not None and metadata:
            with _phoenix_using_attributes(
                metadata=metadata,
                tags=[project_name, command] if command else [project_name],
            ):
                yield
        else:
            yield


@contextmanager
def phoenix_span(name: str, profile: str = "", attributes: dict = None):
    """Create a custom (non-LLM) OpenTelemetry span for Phoenix tracing.

    Use this for non-LLM operations like web search, regulatory crawl, OCR, etc.
    The span will appear in Phoenix Dashboard under the correct project.

    Usage::

        with phoenix_span("duckduckgo_search", profile=profile,
                         attributes={"query": query, "result_count": 15}):
            results = _web_search_sync(query)

    If Phoenix is disabled, acts as a no-op.
    """
    if not PHOENIX_ENABLED or _phoenix_tracer is None:
        yield None
        return

    project_name = get_phoenix_project(profile)
    with _phoenix_using_project(project_name=project_name):
        with _phoenix_tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass  # Skip non-serializable values
            yield span


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
    DEFAULT_PROVIDERS,
    create_provider_manager,
    auto_update_models,
    load_cached_models,
)
from src.storage.markdown_storage import POC_DOCUMENT_LIMIT  # noqa: F401 (re-exported)
from src.services.markdown_store_service import (
    MarkdownStoreService,
    get_markdown_store,
)
from src.database.audit_log import ImmutableAuditLog
from src.utils.audit_export import (
    format_audit_table_markdown,
    export_to_word,
    export_to_excel,
)
from src.utils.regulatory_export import (
    format_regulatory_table_markdown,
    export_regulatory_to_word,
    export_regulatory_to_excel,
    export_reference_to_word,
    export_reference_to_excel,
)
from src.utils.doclist_export import (
    export_doclist_to_word,
    export_doclist_to_excel,
    export_allrecords_to_word,
    export_allrecords_to_excel,
    _build_download_stats,
)
from src.ocr.vision_ocr import process_document
from src.services.regulatory_crawler import (
    get_regulatory_crawler,
    get_available_regions,
)
from src.storage.regulatory_storage import (
    get_regulatory_config,
    get_regulatory_store,
)
from src.utils.regulatory_update_export import (
    format_regulatory_update_markdown,
    export_regulatory_update_to_word,
    export_regulatory_update_to_excel,
)
from src.storage.regulatory_markdown_storage import (
    get_regulatory_markdown_store,
)
from src.storage.regulatory_analysis_storage import (
    get_regulatory_analysis_store,
)
from src.storage.product_docs_storage import get_product_docs_store
from src.analysis.pipeline_runner import run_pipeline_analysis, PipelineRunResult
from src.analysis.report_api import report_router
from src.utils.user_settings import save_user_settings, load_user_settings
from src.utils.analysis_cache import (
    save_analysis_cache,
    get_pending_reports,
    mark_cache_delivered,
)
from src.utils.watermark import (
    add_watermark_to_pdf,
    generate_watermark_preview,
    convert_to_pdf_for_viewing,
    get_document_level,
    should_allow_download,
)

# v3.1.0: Load cached model lists from previous sessions on startup.
# This ensures cloud provider models appear immediately without
# needing to re-enter API keys.
load_cached_models()

# ── Phase D: Mount report API on Chainlit's underlying FastAPI app ──
# Chainlit registers a catch-all SPA route /{full_path:path} that intercepts
# all unmatched paths. We must move it to the end AFTER mounting our router.
try:
    from chainlit.server import app as _chainlit_fastapi_app

    _chainlit_fastapi_app.include_router(report_router)

    # Move Chainlit's catch-all SPA route to the very end so our
    # /api/report/* routes are matched first.
    _catch_all = None
    for _i, _route in enumerate(_chainlit_fastapi_app.routes):
        if (
            hasattr(_route, "path")
            and getattr(_route, "path", "") == "/{full_path:path}"
        ):
            _catch_all = _chainlit_fastapi_app.routes.pop(_i)
            break
    if _catch_all:
        _chainlit_fastapi_app.routes.append(_catch_all)
        logging.getLogger(__name__).info(
            "Report API mounted + Chainlit catch-all route moved to end"
        )
    else:
        logging.getLogger(__name__).info("Report API mounted")
except Exception as _mount_err:
    logging.getLogger(__name__).warning(
        f"Failed to mount report API router: {_mount_err}"
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
        COMMANDS,  # noqa: F401
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


# --- Region aliases for natural language matching ---
_REGION_ALIASES = {
    # Chinese aliases
    "台灣": "台灣 (Taiwan)",
    "台湾": "台灣 (Taiwan)",
    "美國": "美國 (USA)",
    "美国": "美國 (USA)",
    "歐盟": "歐盟 (EU)",
    "欧盟": "歐盟 (EU)",
    "歐洲": "歐盟 (EU)",
    "欧洲": "歐盟 (EU)",
    "英國": "英國 (UK)",
    "英国": "英國 (UK)",
    "日本": "日本 (Japan)",
    "中國": "中國 (China)",
    "中国": "中國 (China)",
    "大陸": "中國 (China)",
    "大陆": "中國 (China)",
    "韓國": "韓國 (Korea)",
    "韩国": "韓國 (Korea)",
    "加拿大": "加拿大 (Canada)",
    "澳洲": "澳洲 (Australia)",
    "澳大利亞": "澳洲 (Australia)",
    "澳大利亚": "澳洲 (Australia)",
    "瑞士": "瑞士 (Switzerland)",
    "巴西": "巴西 (Brazil)",
    "國際": "國際標準 (International)",
    "国际": "國際標準 (International)",
    "國際標準": "國際標準 (International)",
    # English aliases
    "taiwan": "台灣 (Taiwan)",
    "tw": "台灣 (Taiwan)",
    "usa": "美國 (USA)",
    "us": "美國 (USA)",
    "america": "美國 (USA)",
    "united states": "美國 (USA)",
    "eu": "歐盟 (EU)",
    "europe": "歐盟 (EU)",
    "european union": "歐盟 (EU)",
    "uk": "英國 (UK)",
    "britain": "英國 (UK)",
    "england": "英國 (UK)",
    "united kingdom": "英國 (UK)",
    "japan": "日本 (Japan)",
    "jp": "日本 (Japan)",
    "china": "中國 (China)",
    "cn": "中國 (China)",
    "korea": "韓國 (Korea)",
    "kr": "韓國 (Korea)",
    "south korea": "韓國 (Korea)",
    "canada": "加拿大 (Canada)",
    "ca": "加拿大 (Canada)",
    "australia": "澳洲 (Australia)",
    "au": "澳洲 (Australia)",
    "switzerland": "瑞士 (Switzerland)",
    "swiss": "瑞士 (Switzerland)",
    "ch": "瑞士 (Switzerland)",
    "brazil": "巴西 (Brazil)",
    "br": "巴西 (Brazil)",
    "international": "國際標準 (International)",
    "iso": "國際標準 (International)",
    # New regions (v2.0)
    "印度": "印度 (India)",
    "india": "印度 (India)",
    "in": "印度 (India)",
    "新加坡": "新加坡 (Singapore)",
    "singapore": "新加坡 (Singapore)",
    "sg": "新加坡 (Singapore)",
    "沙烏地阿拉伯": "沙烏地阿拉伯 (Saudi Arabia)",
    "沙特": "沙烏地阿拉伯 (Saudi Arabia)",
    "沙乌地阿拉伯": "沙烏地阿拉伯 (Saudi Arabia)",
    "saudi arabia": "沙烏地阿拉伯 (Saudi Arabia)",
    "saudi": "沙烏地阿拉伯 (Saudi Arabia)",
    "sa": "沙烏地阿拉伯 (Saudi Arabia)",
    "泰國": "泰國 (Thailand)",
    "泰国": "泰國 (Thailand)",
    "thailand": "泰國 (Thailand)",
    "th": "泰國 (Thailand)",
    "紐西蘭": "紐西蘭 (New Zealand)",
    "纽西兰": "紐西蘭 (New Zealand)",
    "new zealand": "紐西蘭 (New Zealand)",
    "nz": "紐西蘭 (New Zealand)",
    "墨西哥": "墨西哥 (Mexico)",
    "mexico": "墨西哥 (Mexico)",
    "mx": "墨西哥 (Mexico)",
    "阿根廷": "阿根廷 (Argentina)",
    "argentina": "阿根廷 (Argentina)",
    "ar": "阿根廷 (Argentina)",
    "南非": "南非 (South Africa)",
    "south africa": "南非 (South Africa)",
    "za": "南非 (South Africa)",
    "土耳其": "土耳其 (Turkey)",
    "turkey": "土耳其 (Turkey)",
    "türkiye": "土耳其 (Turkey)",
    "tr": "土耳其 (Turkey)",
    "印尼": "印尼 (Indonesia)",
    "印度尼西亞": "印尼 (Indonesia)",
    "印度尼西亚": "印尼 (Indonesia)",
    "indonesia": "印尼 (Indonesia)",
    "id": "印尼 (Indonesia)",
    "馬來西亞": "馬來西亞 (Malaysia)",
    "马来西亚": "馬來西亞 (Malaysia)",
    "malaysia": "馬來西亞 (Malaysia)",
    "my": "馬來西亞 (Malaysia)",
    "以色列": "以色列 (Israel)",
    "israel": "以色列 (Israel)",
    "il": "以色列 (Israel)",
    "菲律賓": "菲律賓 (Philippines)",
    "菲律宾": "菲律賓 (Philippines)",
    "philippines": "菲律賓 (Philippines)",
    "ph": "菲律賓 (Philippines)",
    "越南": "越南 (Vietnam)",
    "vietnam": "越南 (Vietnam)",
    "vn": "越南 (Vietnam)",
    "哥倫比亞": "哥倫比亞 (Colombia)",
    "哥伦比亚": "哥倫比亞 (Colombia)",
    "colombia": "哥倫比亞 (Colombia)",
    "co": "哥倫比亞 (Colombia)",
    "俄羅斯": "俄羅斯 (Russia)",
    "俄罗斯": "俄羅斯 (Russia)",
    "russia": "俄羅斯 (Russia)",
    "ru": "俄羅斯 (Russia)",
    "埃及": "埃及 (Egypt)",
    "egypt": "埃及 (Egypt)",
    "eg": "埃及 (Egypt)",
    "智利": "智利 (Chile)",
    "chile": "智利 (Chile)",
    "cl": "智利 (Chile)",
    "阿聯酋": "阿聯酋 (UAE)",
    "阿联酋": "阿聯酋 (UAE)",
    "uae": "阿聯酋 (UAE)",
    "united arab emirates": "阿聯酋 (UAE)",
}

# Exclusion keywords (Chinese + English)
_EXCLUSION_KEYWORDS = [
    "除了",
    "不要",
    "不含",
    "移除",
    "刪除",
    "排除",
    "去掉",
    "不包含",
    "去除",
    "不需要",
    "不用",
    "except",
    "exclude",
    "remove",
    "without",
    "not",
]

# Keep/only keywords (Chinese + English)
_KEEP_KEYWORDS = [
    "只保留",
    "僅保留",
    "只要",
    "僅要",
    "只爬",
    "只需要",
    "only",
    "just",
    "keep only",
]


def _parse_region_selection(
    user_input: str, available_regions: list, success_regions: list
) -> list:
    """Parse user natural-language region selection input.

    Supports:
      - Numbers: "1,2,5" or "1 2 5"
      - Names: "美國、日本、台灣"
      - Aliases: "EU", "US", "歐盟", "欧洲"
      - Keep syntax: "只保留美國" -> keep only USA
      - Exclude syntax: "除了中國以外都要" -> all except China
      - "all" / "全部" -> all available
    """
    input_lower = user_input.lower().strip()

    # Handle "all" / "全部" / "所有"
    if input_lower in ("all", "全部", "所有", "全部都要", "都要"):
        return list(available_regions)

    # Detect exclusion mode: "除了X以外" / "except X"
    is_exclude = any(kw in input_lower for kw in _EXCLUSION_KEYWORDS)
    # Detect keep-only mode: "只保留X" / "only X"
    is_keep_only = any(kw in input_lower for kw in _KEEP_KEYWORDS)

    # Extract mentioned regions
    mentioned = _extract_regions_from_text(input_lower, available_regions)

    if is_exclude and mentioned:
        # "除了中國以外都要" -> return all except mentioned
        return [r for r in available_regions if r not in mentioned]
    elif is_keep_only and mentioned:
        # "只保留美國" -> return only mentioned
        return mentioned
    elif mentioned:
        # Direct mention without modifiers -> keep mentioned
        return mentioned
    else:
        # Fall through to empty -> caller handles default
        return []


def _extract_regions_from_text(text_lower: str, available_regions: list) -> list:
    """Extract region names from user text using aliases and substring matching."""
    found = []

    # 1. Try numeric extraction first
    numbers = re.findall(r"\b(\d{1,2})\b", text_lower)
    if numbers:
        for num_str in numbers:
            idx = int(num_str) - 1
            if 0 <= idx < len(available_regions):
                region = available_regions[idx]
                if region not in found:
                    found.append(region)
        # If we got numeric results, return them (don't mix with text parsing)
        if found:
            return found

    # 2. Try alias matching (exact alias -> region)
    for alias, region_name in _REGION_ALIASES.items():
        if alias in text_lower and region_name in available_regions:
            if region_name not in found:
                found.append(region_name)

    if found:
        return found

    # 3. Try substring matching against region display names
    for region in available_regions:
        # Extract Chinese name and English name from "XX (YY)" format
        parts = re.match(r"^(.+?)\s*\((.+?)\)$", region)
        if parts:
            cn_name = parts.group(1)
            en_name = parts.group(2).lower()
            if cn_name in text_lower or en_name in text_lower:
                if region not in found:
                    found.append(region)
        elif region.lower() in text_lower:
            if region not in found:
                found.append(region)

    return found


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
- 「下載 文件編號」- 下載原始文件（所有 1-4 階及外來文件皆可下載，下載記錄於稽核紀錄）
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
    # --- Additional keywords (comprehensive coverage) ---
    # English (QMS / regulatory / legal)
    "controlled copy",
    "controlled document",
    "uncontrolled copy",
    "obsolete",
    "superseded",
    "effective",
    "void",
    "draft",
    "notary",
    "notarized",
    "notarial",
    "apostille",
    "wet signature",
    "ink signature",
    "counter-signed",
    "countersigned",
    "co-signed",
    "cosigned",
    "initialed",
    "initials",
    "electronically signed",
    "electronically signed by",
    "meaning: approval",
    "meaning: review",
    "21 cfr part 11",
    "signed and dated",
    "date signed",
    "witnessed by",
    "attested by",
    "certified copy",
    "authenticated",
    # 繁體中文 (additional)
    "大章",
    "小章",
    "私章",
    "管制文件",
    "受控文件",
    "正本",
    "副本",
    "公證",
    "公證人",
    # 簡體中文 (additional)
    "公章",
    "合同专用章",
    "财务章",
    "发票章",
    "人事章",
    "法人章",
    "电子签章",
    "电子签名",
    "数字签名",
    "受控副本",
    "公证",
    "公证人",
    # 日本語 (additional)
    "判子",
    "認め印",
    "三文判",
    "公証",
    "公証人",
    "銀行印",
    "契印",
    "消印",
    "割印",
    # 한국어 (additional)
    "공증",
    "공증인",
    "전자인감",
    "대표인",
    "통제문서",
    # Deutsch (additional)
    "amtssiegel",
    "notarsiegel",
    "beglaubigt",
    # Français (additional)
    "paraphe",
    "notarié",
    "certifié conforme",
    # Español (additional)
    "rúbrica",
    "escritura notarial",
    "certificado",
    # Português (additional)
    "rubrica",
    "tabelião",
    "reconhecimento de firma",
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


# ============================================================
# OpenCV Color-Based Stamp & Handwriting Detection
# (scanned document fallback)
# ============================================================


def _detect_stamps_by_color(image_data, max_dimension: int = 1000) -> bool:
    """Detect stamps (red/blue ink) and handwritten signatures in images.

    For scanned documents where stamps/signatures are part of a full-page
    image (not separate embedded objects). Uses two detection strategies:
    1. Color detection: red/blue ink regions (stamps, seals)
    2. Stroke detection: dark ink handwritten strokes (signatures)

    Performance: images are resized to max_dimension before analysis,
    so even a 300dpi A4 scan (~2480x3508) processes in ~20-50ms.

    Args:
        image_data: Raw image bytes or numpy array.
        max_dimension: Resize longest side to this value (default 1000px).
                       Lower = faster but may miss small stamps.

    Returns:
        True if stamp or handwritten signature detected, False otherwise.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False

    try:
        # --- Decode image ---
        if isinstance(image_data, np.ndarray):
            img = image_data.copy()
        else:
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return False

        # --- Resize for performance ---
        h_orig, w_orig = img.shape[:2]
        longest = max(h_orig, w_orig)
        if longest > max_dimension:
            scale = max_dimension / longest
            new_w = int(w_orig * scale)
            new_h = int(h_orig * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        img_h, img_w = img.shape[:2]
        img_area = img_h * img_w

        # ==========================================================
        # Strategy 1: Color-based detection (red / blue ink)
        # Detects both stamps (compact shapes) and colored-ink
        # signatures (elongated strokes in red/blue pen).
        # ==========================================================
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Red ink (wraps around H=0/180 in HSV)
        lower_red1 = np.array([0, 70, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 70, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red1, upper_red1),
            cv2.inRange(hsv, lower_red2, upper_red2),
        )

        # Blue ink
        lower_blue = np.array([100, 70, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

        mask_color = cv2.bitwise_or(mask_red, mask_blue)

        # Morphological ops: close gaps, remove noise
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_color = cv2.morphologyEx(mask_color, cv2.MORPH_CLOSE, k_close)
        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_color = cv2.morphologyEx(mask_color, cv2.MORPH_OPEN, k_open)

        contours_color, _ = cv2.findContours(
            mask_color, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours_color:
            area = cv2.contourArea(contour)
            if area < 300 or area > img_area * 0.25:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            bbox_area = w * h
            if bbox_area == 0:
                continue
            aspect = max(w, h) / max(min(w, h), 1)

            # Mode A: Stamp (compact, roughly circular/square)
            if aspect <= 3.0:
                perimeter = cv2.arcLength(contour, True)
                if perimeter > 0:
                    circularity = 4 * 3.14159 * area / (perimeter * perimeter)
                    if circularity > 0.15:
                        return True  # Stamp detected

            # Mode B: Colored-ink signature (elongated strokes in red/blue)
            # Handwritten signatures in colored pen produce long, curvy
            # contours with low fill ratio (ink strokes, not solid blocks).
            if aspect > 1.5 and area >= 500:
                fill_ratio = area / bbox_area
                if fill_ratio < 0.5:  # Sparse = strokes, not solid fill
                    perimeter = cv2.arcLength(contour, True)
                    diagonal = (w**2 + h**2) ** 0.5
                    if diagonal > 0 and perimeter / diagonal > 2.5:
                        return True  # Colored-ink signature detected

        # ==========================================================
        # Strategy 2: Dark-ink handwritten signature detection
        # For black/dark pen signatures that have no distinctive color.
        # ==========================================================
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold to isolate dark marks (ink on paper)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15
        )

        # Remove areas already covered by color detection (stamps)
        binary = cv2.bitwise_and(binary, cv2.bitwise_not(mask_color))

        # Gentle dilation to group nearby strokes into signature clusters
        k_group = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        grouped = cv2.dilate(binary, k_group, iterations=1)

        contours_dark, _ = cv2.findContours(
            grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours_dark:
            area = cv2.contourArea(contour)
            # Too small = noise/punctuation/individual letters
            # Too large = text block or border
            if area < 800 or area > img_area * 0.15:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            bbox_area = w * h
            if bbox_area == 0:
                continue
            aspect = max(w, h) / max(min(w, h), 1)

            if aspect > 5.0:
                continue

            # Combined height + aspect filter: thin, elongated contours
            # (h < 40px AND aspect > 3.0) are printed text lines/underlines,
            # not handwriting. E.g. 'Approved by: ________' at 120x30 px,
            # aspect=4.0 — clearly a text line, not a signature.
            # Real signatures at 1000px resize are typically h >= 40px
            # or have moderate aspect ratio (<3.0).
            if h < 40 and aspect > 3.0:
                continue

            # Fill ratio: handwriting is sparse (~3%-55%)
            fill_ratio = area / bbox_area
            if fill_ratio > 0.6:
                continue

            # Minimum bounding box: signatures span at least ~80px wide
            # and ~20px tall after resize.
            if w < 80 or h < 20:
                continue

            # Count strokes from original binary (before dilation)
            roi = binary[y : y + h, x : x + w]
            n_labels, _, stats, _ = cv2.connectedComponentsWithStats(roi)
            n_strokes = n_labels - 1  # Subtract background

            # Stroke count analysis:
            # - 0 strokes = noise (contour exists only in dilated image)
            # - 1 stroke = could be signature (single connected cursive)
            #   but needs stronger curviness proof (p/d > 3.5)
            # - 2-100 strokes = typical multi-stroke handwriting
            # - >100 = dense printed text
            if n_strokes < 1 or n_strokes > 100:
                continue

            # Stroke density filter: printed text has many strokes
            # packed tightly. Handwriting is more spread out.
            # Printed text: >0.08 strokes/px. Handwriting: <0.06.
            stroke_density = n_strokes / max(w, 1)
            if stroke_density > 0.08:
                continue

            # Curviness: handwriting has perimeter >> diagonal
            perimeter = cv2.arcLength(contour, True)
            diagonal = (w**2 + h**2) ** 0.5
            if diagonal > 0:
                p_d_ratio = perimeter / diagonal
                # Single-stroke needs higher curviness threshold (3.5)
                # to avoid false positives on simple curved lines.
                # Multi-stroke (2+) uses standard threshold (2.5).
                min_p_d = 3.5 if n_strokes == 1 else 2.5
                if p_d_ratio > min_p_d:
                    return True  # Handwritten signature detected

        return False

    except Exception:
        return False


def _pdf_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if PDF contains embedded images (stamps/signatures) on ANY page.

    Stamps and signatures may appear on any page (not just the first few).
    They can be embedded as XObject images, annotations, form fields, or
    digital signature dictionaries.

    Uses a scoring system to distinguish stamp/signature images from
    content images (logos, charts, photos). Each image gets a score based
    on size, aspect ratio, position, and naming. A score >= 2 means
    "likely stamp/signature".

    Returns:
        True if images/stamps/signatures found (likely stamped/signed)
        False if nothing found (likely unsigned)
        None if check failed (can't determine)
    """
    try:
        import pypdf

        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            total_pages = len(reader.pages)

            # --- Check 1: Scan ALL pages for stamp/signature images ---
            # Uses a scoring heuristic to distinguish stamps from content
            # images. Stamps come in all sizes:
            #   - Small personal seals: ~100x100
            #   - Standard company stamps: ~200x200
            #   - Large company seals: ~400x400 to ~600x600
            #   - Full-page stamp overlays: ~1477x1108
            # Content images (charts, photos, logos) also vary in size,
            # so we use multiple signals rather than a single area threshold.
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
                            name_str = str(name).lower()

                            # Form XObject overlays (stamp/signature overlays)
                            if "formxob" in name_str:
                                return True

                            if width <= 0 or height <= 0:
                                continue

                            area = width * height
                            aspect = max(width, height) / max(min(width, height), 1)
                            short_side = min(width, height)

                            # --- Scoring system ---
                            # Each signal adds to the score. Score >= 2 = stamp.
                            score = 0

                            # Signal 1: XObject name contains stamp/sig hints
                            stamp_name_hints = [
                                "stamp",
                                "seal",
                                "sign",
                                "sig",
                                "chop",
                                "ink",
                                "approval",
                            ]
                            if any(h in name_str for h in stamp_name_hints):
                                score += 3  # Very strong signal

                            # Signal 2: Small square-ish images (personal seals,
                            # small company stamps). Area < 160,000 (~400x400)
                            # and nearly square (aspect < 1.8).
                            if area < 160000 and aspect < 1.8:
                                score += 2

                            # Signal 3: Medium square-ish images (large company
                            # stamps, round seals). Area 160k-500k (~400x400
                            # to ~700x700) and nearly square (aspect < 1.5).
                            elif area < 500000 and aspect < 1.5:
                                score += 2

                            # Signal 4: Large overlay images that cover a
                            # significant portion of the page (full-page stamp
                            # overlays, riding seals). These are large but
                            # typically NOT the same size as a full-page scan
                            # (which would be ~2480x3508 at 300dpi = 8.7M).
                            # Stamp overlays are usually < 4M pixels.
                            elif area < 4000000 and area > 500000 and aspect < 2.0:
                                score += 1  # Weaker signal alone

                            # Signal 5: Tiny images (< 50x50) are likely
                            # decorative dots/bullets, not stamps.
                            if short_side < 50:
                                score -= 2

                            # Signal 6: Very large full-page images (>= 4M)
                            # are likely scanned page backgrounds, photos,
                            # or full-page graphics — NOT stamps.
                            if area >= 4000000:
                                score -= 2

                            # Signal 7: Very wide/tall banners (aspect >= 4.0)
                            # are likely headers, footers, or decorative bars.
                            if aspect >= 4.0:
                                score -= 1

                            # Signal 8: Images on approval-heavy pages
                            # (last 2 pages) get a small boost — approval
                            # sections with stamp/signature fields are
                            # commonly at the end of QMS documents.
                            if total_pages > 1 and page_idx >= total_pages - 2:
                                # Only boost medium-sized images, not tiny
                                # logos or huge background images.
                                if 2500 < area < 4000000 and aspect < 3.0:
                                    score += 1

                            if score >= 2:
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

            # --- Check 4: OpenCV stamp & handwriting detection (scanned pages) ---
            # For scanned PDFs where stamps/signatures are part of the page
            # image. Uses priority page order for 300+ page performance:
            #   Tier 1: First page + last page (most common stamp locations)
            #   Tier 2: Pages 2-4 + last 2-4 pages (secondary stamp locations)
            #   Tier 3: All remaining pages
            # Early termination: returns True on first detection.
            try:
                seen = set()
                priority_indices = []

                # Tier 1: First page + last page
                for i in [0, total_pages - 1]:
                    if 0 <= i < total_pages and i not in seen:
                        priority_indices.append(i)
                        seen.add(i)

                # Tier 2: Pages 2-4 (indices 1,2,3) + last 2-4 pages
                for i in range(1, min(4, total_pages)):
                    if i not in seen:
                        priority_indices.append(i)
                        seen.add(i)
                for i in range(max(0, total_pages - 4), total_pages - 1):
                    if i not in seen:
                        priority_indices.append(i)
                        seen.add(i)

                # Tier 3: Remaining pages
                for i in range(total_pages):
                    if i not in seen:
                        priority_indices.append(i)

                for page_idx in priority_indices:
                    page = reader.pages[page_idx]
                    for image in page.images:
                        try:
                            if _detect_stamps_by_color(image.data):
                                return True
                        except Exception:
                            continue
            except Exception:
                pass

            return False
    except Exception:
        return None


def _docx_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if a Word (.docx) file contains embedded images (stamps/signatures).

    Filters out common non-signature images (tiny icons, large photos/charts)
    by checking image dimensions. Stamp/signature images are typically
    50x50 to 800x800 with a near-square aspect ratio.

    Returns:
        True if stamp/signature-sized images found
        False if no qualifying images found
        None if check failed (can't determine)
    """
    try:
        from docx import Document as DocxDocument

        doc = DocxDocument(file_path)
        large_image_blobs = []  # Collect large images for color-based fallback
        for rel in doc.part.rels.values():
            if "image" not in rel.reltype:
                continue
            # Try to get image dimensions to filter out logos/photos
            try:
                from PIL import Image as PILImage
                import io

                image_data = rel.target_part.blob
                img = PILImage.open(io.BytesIO(image_data))
                w, h = img.size
                area = w * h
                aspect = max(w, h) / max(min(w, h), 1)
                # Skip tiny images (icons, bullets): < 50x50
                if min(w, h) < 50:
                    continue
                # Large images (photos, full-page scans): > 2M px
                # Save for color-based detection instead of skipping
                if area > 2000000:
                    large_image_blobs.append(image_data)
                    continue
                # Skip extreme aspect ratios (banners, borders): > 4.0
                if aspect > 4.0:
                    continue
                # Remaining images are likely stamps/signatures
                return True
            except Exception:
                # Can't check dimensions (PIL not available or corrupt image).
                # Fall back to assuming image is a stamp (conservative).
                return True

        # --- Color-based fallback for large images (scanned pages) ---
        # Large images that were skipped may be scanned pages with stamps.
        for blob in large_image_blobs:
            try:
                if _detect_stamps_by_color(blob):
                    return True
            except Exception:
                continue

        return False
    except Exception:
        return None


def _xlsx_has_stamp_images(file_path: str) -> Optional[bool]:
    """Check if an Excel (.xlsx) file contains embedded images (stamps/signatures).

    Filters out common non-signature images (tiny icons, large photos/charts)
    by checking image dimensions. Stamp/signature images are typically
    50x50 to 800x800 with a near-square aspect ratio.

    Returns:
        True if stamp/signature-sized images found
        False if no qualifying images found
        None if check failed (can't determine)
    """
    try:
        from openpyxl import load_workbook

        wb = load_workbook(file_path, data_only=True)
        large_image_blobs = []  # Collect large images for color-based fallback
        for ws in wb.worksheets:
            for img in ws._images:
                try:
                    # openpyxl Image stores width/height in EMU or pixels
                    w = getattr(img, "width", 0) or 0
                    h = getattr(img, "height", 0) or 0
                    # If dimensions are in EMU (> 100000), convert to pixels
                    if w > 100000:
                        w = int(w / 9525)  # 1 px = 9525 EMU
                    if h > 100000:
                        h = int(h / 9525)
                    if w <= 0 or h <= 0:
                        # Can't determine size — assume it could be a stamp
                        return True
                    area = w * h
                    aspect = max(w, h) / max(min(w, h), 1)
                    # Skip tiny images (icons, bullets): < 50x50
                    if min(w, h) < 50:
                        continue
                    # Large images (photos, charts): > 2M px
                    # Save for color-based detection instead of skipping
                    if area > 2000000:
                        try:
                            blob = img._data()
                            large_image_blobs.append(blob)
                        except Exception:
                            pass
                        continue
                    # Skip extreme aspect ratios (banners, borders): > 4.0
                    if aspect > 4.0:
                        continue
                    # Remaining images are likely stamps/signatures
                    return True
                except Exception:
                    # Can't check dimensions — assume it could be a stamp
                    return True

        # --- Color-based fallback for large images (scanned pages) ---
        for blob in large_image_blobs:
            try:
                if _detect_stamps_by_color(blob):
                    return True
            except Exception:
                continue

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
            icon="/public/avatars/eira.svg",
        ),
        cl.ChatProfile(
            name="文件管制 (Doc Control)",
            markdown_description=(
                "文件上傳、OCR 處理、版本控制、簽章確認。拖放文件即可開始。\n\n"
                "File upload, OCR processing, version control, stamp confirmation. Drag & drop to start.\n\n"
                "ファイルアップロード、OCR 処理、版管理、印鑑確認。ドラッグ＆ドロップで開始。"
            ),
            icon="/public/avatars/eira.svg",
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

        # Eira greeting flow after LLM connection
        _user_name = cl.user_session.get("user_name", "")
        if cl.user_session.get("eira_name_pending"):
            # First LLM connection for new user — ask for name
            cl.user_session.set("eira_name_pending", False)
            cl.user_session.set("awaiting_user_name", True)
            await cl.Message(content=t("eira.ask_name"), author="Eira").send()
        elif _user_name:
            # Returning user or subsequent LLM changes — show only Eira intro
            intro = t("eira.introduction", name=_user_name)
            await cl.Message(content=intro, author="Eira").send()
        elif cl.user_session.get("awaiting_user_name"):
            # User switched provider before entering name — re-prompt
            await cl.Message(content=t("eira.ask_name"), author="Eira").send()
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

        # Eira greeting flow after LLM connection
        _user_name = cl.user_session.get("user_name", "")
        if cl.user_session.get("eira_name_pending"):
            # First LLM connection for new user — ask for name
            cl.user_session.set("eira_name_pending", False)
            cl.user_session.set("awaiting_user_name", True)
            await cl.Message(content=t("eira.ask_name"), author="Eira").send()
        elif _user_name:
            # Returning user or subsequent LLM changes — show only Eira intro
            intro = t("eira.introduction", name=_user_name)
            await cl.Message(content=intro, author="Eira").send()
        elif cl.user_session.get("awaiting_user_name"):
            # User switched model before entering name — re-prompt
            await cl.Message(content=t("eira.ask_name"), author="Eira").send()
    # Silently persist settings to file for auto-reconnect (no UI feedback)
    _user_name = cl.user_session.get("user_name", "")
    save_user_settings(
        user_name=_user_name,
        provider_id=cl.user_session.get("provider_id", ""),
        provider_name=cl.user_session.get("provider_name", ""),
        model_name=cl.user_session.get("model_name", ""),
        api_key=cl.user_session.get("real_api_key", "")
        or cl.user_session.get("api_key", ""),
        language=cl.user_session.get("language", "zh-TW"),
    )


# ============================================================
# Background Regulatory Crawler Scheduler (v2.0)
# ============================================================
# Simple asyncio.create_task sleep-loop pattern.
# Starts on first user session; pre-fetches regulatory data daily.

_regulatory_scheduler_started = False
_regulatory_scheduler_lock = asyncio.Lock()
_REGULATORY_SCHEDULE_HOUR = 6  # Run at 6 AM daily


async def _regulatory_background_scheduler():
    """Background loop: pre-fetch regulatory data once per day at scheduled hour.

    Uses asyncio.sleep to wait until the next scheduled time.
    Results are saved to storage; next user session gets instant results.
    """
    import datetime as _dt

    while True:
        try:
            now = _dt.datetime.now()
            target = now.replace(
                hour=_REGULATORY_SCHEDULE_HOUR, minute=0, second=0, microsecond=0
            )
            if now >= target:
                target += _dt.timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            logger_name = logging.getLogger(__name__)
            logger_name.info(
                f"[Scheduler] Next regulatory crawl at {target.isoformat()}"
                f" (in {sleep_seconds / 3600:.1f}h)"
            )
            await asyncio.sleep(sleep_seconds)

            # Execute crawl
            logger_name.info("[Scheduler] Starting scheduled regulatory crawl...")
            crawler = get_regulatory_crawler()
            with phoenix_span(
                "regulatory_crawl_scheduled",
                profile="文件管制 (Doc Control)",
                attributes={"crawl.type": "scheduled_all_regions"},
            ):
                crawl_results = await crawler.crawl_all_regions()

            # Save results
            from src.storage.regulatory_storage import get_regulatory_store

            store = get_regulatory_store()
            store.save_crawl_results(crawl_results)

            # Save to markdown DB
            from src.storage.regulatory_markdown_storage import (
                get_regulatory_markdown_store,
            )

            reg_md_store = get_regulatory_markdown_store()
            reg_md_store.save_from_crawl_results(crawl_results)

            summary = crawl_results.get("summary", {})
            logger_name.info(
                f"[Scheduler] Regulatory crawl complete: "
                f"{summary.get('success_count', 0)}/{summary.get('total_sites', 0)} succeeded"
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).error(
                f"[Scheduler] Regulatory crawl failed: {e}"
            )
            # Wait 1 hour before retry on error
            await asyncio.sleep(3600)


_daily_audit_scheduler_started = False
_daily_audit_scheduler_lock = asyncio.Lock()
_DAILY_AUDIT_SCHEDULE_HOUR = 7  # Run daily audit at 7 AM


async def _daily_audit_background_scheduler():
    """Background loop: run daily audit once per day at scheduled hour.

    Uses the same asyncio sleep-loop pattern as the regulatory crawler.
    After each run, checks whether a 10-day meta review should be auto-triggered.
    """
    import datetime as _dt

    _logger = logging.getLogger(__name__)

    while True:
        try:
            now = _dt.datetime.now()
            target = now.replace(
                hour=_DAILY_AUDIT_SCHEDULE_HOUR, minute=0, second=0, microsecond=0
            )
            if now >= target:
                target += _dt.timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            _logger.info(
                "[DailyAuditScheduler] Next audit at %s (in %.1fh)",
                target.isoformat(),
                sleep_seconds / 3600,
            )
            await asyncio.sleep(sleep_seconds)

            # Get LLM function from current session or stored settings
            _logger.info("[DailyAuditScheduler] Starting scheduled daily audit...")
            try:
                from src.analysis.report_api import (
                    _get_llm_completion_fn_standalone,
                    _maybe_auto_trigger_meta_review,
                )
                from src.analysis.daily_audit import (
                    run_daily_sampling_crossexam,
                    run_daily_audit,
                )
                from src.utils.user_settings import load_user_settings
                from src.utils.app_settings import get_app_setting

                settings = load_user_settings()
                lang = settings.get("language", "zh-TW") if settings else "zh-TW"
                saved_model = (
                    settings.get("model_name", "default") if settings else "default"
                )

                llm_fn = _get_llm_completion_fn_standalone()
                if llm_fn is None:
                    _logger.warning(
                        "[DailyAuditScheduler] No LLM function available, skipping"
                    )
                    await asyncio.sleep(3600)
                    continue

                mdsap_on = get_app_setting("mdsap_verify_enabled", False)

                # Check regulation freshness to determine incomplete countries
                incomplete_countries: list[str] = []
                try:
                    from src.services.regulatory_crawler import (
                        check_country_data_completeness,
                    )

                    completeness = await check_country_data_completeness()
                    incomplete_countries = completeness.get("incomplete_countries", [])
                    if incomplete_countries:
                        _logger.info(
                            "[DailyAuditScheduler] Incomplete data for: %s — "
                            "audit will proceed with warning annotation",
                            incomplete_countries,
                        )
                except Exception as fc_err:
                    _logger.warning(
                        "[DailyAuditScheduler] Freshness check failed: %s — "
                        "proceeding without warning annotation",
                        fc_err,
                    )

                # Preflight: verify Phase 5 pipeline state exists before proceeding
                from src.analysis.daily_audit import _find_latest_pipeline_state
                if _find_latest_pipeline_state() is None:
                    _logger.warning(
                        "[DailyAuditScheduler] Preflight failed: no completed pipeline "
                        "state found. Run Phase 5 first. Skipping this cycle."
                    )
                    await asyncio.sleep(3600)
                    continue

                # Step 1: Run daily sampling cross-exam (Phase 5 on 20% sample)
                sampling_record = run_daily_sampling_crossexam(
                    llm_completion_fn=llm_fn,
                    model=saved_model,
                    mdsap_enabled=mdsap_on,
                    lang=lang,
                )
                if sampling_record is None:
                    _logger.info(
                        "[DailyAuditScheduler] No pipeline state available, skipping"
                    )
                    await asyncio.sleep(3600)
                    continue

                result = run_daily_audit(
                    llm_completion_fn=llm_fn,
                    lang=lang,
                    incomplete_countries=incomplete_countries,
                    mdsap_enabled=mdsap_on,
                )

                _logger.info(
                    "[DailyAuditScheduler] Daily audit complete: "
                    "overall=%.0f, dimA=%.0f, dimB=%.0f",
                    result.overall_score,
                    result.dim_a_score,
                    result.dim_b_score,
                )

                # Auto-trigger meta review if applicable
                try:
                    _maybe_auto_trigger_meta_review(llm_fn, lang)
                except Exception as me:
                    _logger.warning(
                        "[DailyAuditScheduler] Meta review auto-trigger failed: %s", me
                    )

            except ImportError as ie:
                _logger.warning("[DailyAuditScheduler] Module not available: %s", ie)
                await asyncio.sleep(3600)
                continue

        except asyncio.CancelledError:
            break
        except Exception as e:
            _logger.error("[DailyAuditScheduler] Failed: %s", e)
            await asyncio.sleep(3600)


_FRESHNESS_TIMESTAMP_FILE = Path("data/last_freshness_check.json")


def _should_run_freshness_check() -> bool:
    """Return True if freshness check hasn't been run today (date-based, not 24h)."""
    try:
        if _FRESHNESS_TIMESTAMP_FILE.exists():
            data = json.loads(_FRESHNESS_TIMESTAMP_FILE.read_text(encoding="utf-8"))
            last_date = data.get("last_check_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            return last_date != today
    except Exception:
        pass
    return True  # No record or error → run the check


def _record_freshness_check():
    """Record that we ran the freshness check today."""
    try:
        _FRESHNESS_TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FRESHNESS_TIMESTAMP_FILE.write_text(
            json.dumps(
                {
                    "last_check_date": datetime.now().strftime("%Y-%m-%d"),
                    "last_check_ts": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass  # Non-critical


async def _auto_trigger_crossexam():
    """Auto-trigger regulation freshness check and daily cross-examination.

    Runs after welcome message. Checks regulation freshness first,
    shows announcement if needed (including per-country upload reminders),
    then triggers daily audit + 10-day meta review.

    Full startup order for Doc Control:
      1. 法規更新 (freshness check + crawl, once per calendar day)
      2. 當日交叉詰問 daily audit (run or show cached)
      3. 10日總檢 meta review (if ≥10 new daily audits since last meta)
      4. Pipeline progress indicator

    NOTE: Heavy operations (crawling 7 countries, HTTP HEAD checks) are
    rate-limited to once per calendar day (隔日). Daily audit is also
    once per calendar day — subsequent sessions show cached results.
    """
    incomplete_countries: list[str] = []
    try:
        # Gate: only run full freshness check + crawl once per calendar day (隔日)
        if not _should_run_freshness_check():
            logging.getLogger(__name__).debug(
                "Freshness check skipped (already ran today). "
                "Showing pipeline progress only."
            )
            await _show_pipeline_progress()
        else:
            # Step 1: Show progress message, then crawl with live % updates
            from src.services.regulatory_crawler import check_regulation_freshness

            progress_msg = cl.Message(
                content=t("crossexam.freshness_crawling", percent=0, country="..."),
                author="Eira",
            )
            await progress_msg.send()

            async def _on_country_progress(completed: int, total: int, country_zh: str):
                pct = round((completed / total) * 100) if total > 0 else 0
                progress_msg.content = t(
                    "crossexam.freshness_crawling",
                    percent=pct,
                    country=country_zh,
                )
                await progress_msg.update()

            freshness = await check_regulation_freshness(
                progress_callback=_on_country_progress,
            )
            _record_freshness_check()

            progress_msg.content = t("crossexam.freshness_crawl_done")
            await progress_msg.update()
            if freshness.get("announcement_needed"):
                lang = cl.user_session.get("language", "zh-TW")
                if lang.startswith("zh"):
                    announcement = freshness.get("announcement_text_zh", "")
                else:
                    announcement = freshness.get("announcement_text", "")
                if announcement:
                    await cl.Message(content=announcement, author="Eira").send()
            else:
                await cl.Message(
                    content=t("crossexam.freshness_confirmed"),
                    author="Eira",
                ).send()

            # Step 1b: Show per-country upload reminders if incomplete data
            country_data = freshness.get("country_completeness", {})
            incomplete_countries = country_data.get("incomplete_countries", [])
            if incomplete_countries:
                lang = cl.user_session.get("language", "zh-TW")
                countries_info = country_data.get("countries", {})
                lines = []
                for pid in incomplete_countries:
                    info = countries_info.get(pid, {})
                    if lang.startswith("zh"):
                        lines.append(f"  • {info.get('message_zh', pid)}")
                    else:
                        lines.append(f"  • {info.get('message', pid)}")
                upload_msg = (
                    t("crossexam.upload_reminder_title")
                    + "\n"
                    + "\n".join(lines)
                    + "\n\n"
                    + t("crossexam.upload_reminder_instruction")
                )
                await cl.Message(content=upload_msg, author="Eira").send()

            # Step 2: Check MDSAP toggle
            from src.utils.app_settings import get_app_setting

            mdsap_enabled = get_app_setting("mdsap_verify_enabled", False)
            if mdsap_enabled:
                mdsap_msg = t("crossexam.mdsap_enabled_notice")
                await cl.Message(content=mdsap_msg, author="Eira").send()

            # Step 3: Show pipeline progress indicator
            await _show_pipeline_progress()

    except Exception as e:
        logging.getLogger(__name__).error(
            "Auto cross-exam trigger (freshness) failed: %s", e
        )

    # Step 4: Daily audit + meta review (ALWAYS runs, both branches)
    # Uses cached results if today's audit already exists.
    try:
        await _run_and_display_daily_audit(incomplete_countries)
    except Exception as e:
        logging.getLogger(__name__).error("Auto daily audit trigger failed: %s", e)


async def _run_and_display_daily_audit(
    incomplete_countries: list[str] | None = None,
):
    """Run daily sampling cross-exam + audit, display results, then check meta review.

    Flow (once per calendar day):
      1. run_daily_sampling_crossexam() — Phase 5 on 20% sample → DailyCrossExamStore
      2. run_daily_audit() — Dim A + Dim B on DailyCrossExamStore records
      3. Display results
      4. Check 10-day meta review
    """
    import asyncio as _aio
    from datetime import date as _date

    lang = cl.user_session.get("language", "zh-TW")
    today_str = _date.today().isoformat()
    daily_path = Path(f"data/daily_audit/daily_{today_str}.json")

    _log = logging.getLogger(__name__)
    result = None

    if daily_path.exists():
        try:
            from src.analysis.daily_audit import DailyAuditResult

            _data = json.loads(daily_path.read_text(encoding="utf-8"))
            result = DailyAuditResult.from_dict(_data)
            _log.info("Daily audit: loaded cached result for %s", today_str)
        except Exception as e:
            _log.warning("Failed to load cached daily audit: %s", e)
            result = None
    else:
        llm_fn = None
        provider_id = cl.user_session.get("provider_id", "")
        if provider_id:
            try:
                from src.llm_providers import create_provider_manager

                manager = create_provider_manager(provider_id)
                llm_fn = manager.completion
            except Exception as _llm_err:
                _log.warning("Failed to create LLM fn from session: %s", _llm_err)

        if llm_fn is None:
            from src.analysis.report_api import _get_llm_completion_fn_standalone

            llm_fn = _get_llm_completion_fn_standalone()

        if llm_fn is None:
            await cl.Message(content=t("daily_audit.no_llm"), author="Eira").send()
            return

        audit_progress = cl.Message(content=t("daily_audit.running"), author="Eira")
        await audit_progress.send()

        try:
            from src.analysis.daily_audit import (
                run_daily_sampling_crossexam,
                run_daily_audit,
            )
            from src.utils.app_settings import get_app_setting

            mdsap_on = get_app_setting("mdsap_verify_enabled", False)

            sampling_record = await _aio.to_thread(
                run_daily_sampling_crossexam,
                llm_completion_fn=llm_fn,
                model=cl.user_session.get("model_name", "default"),
                mdsap_enabled=mdsap_on,
                lang=lang,
            )

            if sampling_record is None:
                await cl.Message(
                    content=t("daily_audit.no_records"), author="Eira"
                ).send()
                return

            result = await _aio.to_thread(
                run_daily_audit,
                llm_completion_fn=llm_fn,
                lang=lang,
                incomplete_countries=incomplete_countries or [],
                mdsap_enabled=mdsap_on,
            )

            audit_progress.content = t("daily_audit.completed")
            await audit_progress.update()
        except Exception as e:
            _log.error("Daily audit run failed: %s", e)
            audit_progress.content = f"⚠️ Daily audit failed: {str(e)[:200]}"
            await audit_progress.update()
            return

    if result is None:
        return

    if "No cross-examination records" in (result.summary or ""):
        await cl.Message(content=t("daily_audit.no_records"), author="Eira").send()
        return

    await _display_daily_audit_result(result)

    await _run_and_display_meta_review()


async def _display_daily_audit_result(result):
    """Display daily audit scores, deviation warning, HTML link, and exports."""
    lang = cl.user_session.get("language", "zh-TW")
    _report_url = f"/api/report/page/latest?lang={lang}"

    # Build message lines
    lines = [
        t(
            "daily_audit.result_title",
            date=result.audit_date,
        ),
        t(
            "daily_audit.score_line",
            overall=result.overall_score,
            dim_a=result.dim_a_score,
            dim_b=result.dim_b_score,
        ),
    ]

    # Deviation warning
    if result.deviation_detected:
        lines.append(
            t("daily_audit.deviation_warning", details=result.deviation_details)
        )

    # Incomplete data warning
    if result.incomplete_data_warning and result.incomplete_countries:
        lines.append(
            t(
                "daily_audit.incomplete_data_countries",
                countries=", ".join(result.incomplete_countries),
            )
        )

    # Cross-validation: 7-country vs MDSAP 5-country
    cv = result.cross_validation or {}
    if cv and not cv.get("error"):
        mdsap_count = cv.get("mdsap_record_count", 0)
        full_count = cv.get("full_record_count", 0)
        if mdsap_count > 0 or full_count > 0:
            lines.append("")
            lines.append(t("daily_audit.crossval_title"))
            lines.append(
                t(
                    "daily_audit.crossval_records",
                    mdsap_count=mdsap_count,
                    full_count=full_count,
                )
            )
            lines.append(
                t(
                    "daily_audit.crossval_agreement",
                    mdsap_avg=cv.get("mdsap_avg_agreement", 0.0),
                    full_avg=cv.get("full_avg_agreement", 0.0),
                )
            )
            csc = cv.get("country_score_comparison", {})
            if csc:
                lines.append(
                    t(
                        "daily_audit.crossval_country_scores",
                        mdsap_country_avg=csc.get("mdsap_country_avg", 0.0),
                        non_mdsap_country_avg=csc.get("non_mdsap_country_avg", 0.0),
                    )
                )
            assessment = cv.get("consistency_assessment", "consistent")
            delta = cv.get("consistency_delta", 0.0)
            if assessment == "consistent":
                lines.append(t("daily_audit.crossval_consistent", delta=delta))
            elif assessment == "minor_drift":
                lines.append(t("daily_audit.crossval_minor_drift", delta=delta))
            else:
                lines.append(t("daily_audit.crossval_significant_drift", delta=delta))

    # HTML report link
    lines.append(f"\n[🔗 {t('daily_audit.view_report')}]({_report_url})")

    msg_content = "\n".join(lines)

    # Generate Word/Excel exports and attach as downloadable files
    elements = []
    try:
        from src.analysis.daily_audit import (
            export_daily_audit_word,
            export_daily_audit_excel,
        )

        word_path = str(export_daily_audit_word(result))
        if Path(word_path).exists():
            wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
            elements.append(cl.File(name=wname, path=word_path, display="inline"))

        excel_path = str(export_daily_audit_excel(result))
        if Path(excel_path).exists():
            ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
            elements.append(cl.File(name=ename, path=excel_path, display="inline"))
    except Exception as e:
        logging.getLogger(__name__).warning("Daily audit export failed: %s", e)

    await cl.Message(content=msg_content, author="Eira", elements=elements).send()

    # Offer feedback action
    await cl.Message(
        content="對本次每日稽核結果有意見嗎？",
        author="Eira",
        actions=[
            cl.Action(
                name="submit_daily_feedback",
                label="📝 提交回饋",
                description="對本次每日稽核結果提交意見",
                payload={
                    "audit_date": result.audit_date,
                    "audit_id": result.audit_date,
                },
            )
        ],
    ).send()


async def _run_and_display_meta_review():
    """Check if 10-day meta review should run, display results if available.

    Trigger condition: ≥10 new daily audits since last meta review's period_end.
    Each batch of 10 new daily audits triggers a new round (新的一輪).
    Uses _maybe_auto_trigger_meta_review() which handles the ≥10 check internally.
    """
    import asyncio as _aio

    lang = cl.user_session.get("language", "zh-TW")

    # Get LLM function
    from src.analysis.report_api import _get_llm_completion_fn_standalone

    llm_fn = _get_llm_completion_fn_standalone()
    if llm_fn is None:
        # Can't run meta review without LLM, but maybe cached result exists
        from src.analysis.daily_audit import get_latest_meta_review

        meta = get_latest_meta_review()
        if meta:
            await _display_meta_review_result(meta)
        return

    # Run the meta review check (synchronous → thread)
    try:
        from src.analysis.report_api import _maybe_auto_trigger_meta_review

        meta_progress = None
        # Pre-check: do we have ≥10 records? Quick check to decide whether
        # to show a progress message.
        from src.analysis.daily_audit import get_daily_audit_history

        daily_records = get_daily_audit_history(limit=30)
        if len(daily_records) < 10:
            return  # Not enough records, skip entirely

        meta_progress = cl.Message(content=t("meta_review.running"), author="Eira")
        await meta_progress.send()

        meta_dict = await _aio.to_thread(
            _maybe_auto_trigger_meta_review,
            llm_fn,
            lang,
        )

        if meta_dict is not None:
            # Meta review was triggered and completed — show results
            # _maybe_auto_trigger_meta_review returns a summary dict, but we
            # want the full MetaReviewResult for display + exports.
            from src.analysis.daily_audit import get_latest_meta_review

            meta = get_latest_meta_review()
            if meta:
                if meta_progress:
                    await meta_progress.remove()
                await _display_meta_review_result(meta)
            elif meta_progress:
                await meta_progress.remove()
        else:
            # Not triggered (< 10 new records since last meta)
            # Show the latest cached meta review if one exists
            if meta_progress:
                await meta_progress.remove()
            from src.analysis.daily_audit import get_latest_meta_review

            meta = get_latest_meta_review()
            if meta:
                await _display_meta_review_result(meta)
    except Exception as e:
        logging.getLogger(__name__).error("Meta review failed: %s", e)


async def _display_meta_review_result(meta):
    """Display a MetaReviewResult with trend analysis, HTML link, and export files."""
    lang = cl.user_session.get("language", "zh-TW")
    _meta_report_url = f"/api/report/daily-audit/meta-review?lang={lang}"

    lines = [
        t(
            "meta_review.title",
            period_start=meta.period_start or "?",
            period_end=meta.period_end or "?",
        ),
        t(
            "meta_review.score_line",
            avg_dim_a=meta.avg_dim_a,
            avg_dim_b=meta.avg_dim_b,
            count=len(meta.daily_results),
        ),
    ]

    # Trend analysis
    if meta.trend_analysis:
        _trend = meta.trend_analysis[:500]
        lines.append(t("meta_review.trend", trend=_trend))

    # Deviation summary
    if meta.deviation_summary:
        lines.append(t("meta_review.deviation", deviation=meta.deviation_summary[:300]))

    # Recommendations
    if meta.recommendations:
        lines.append(t("meta_review.recommendations_title"))
        for i, rec in enumerate(meta.recommendations[:5], 1):
            lines.append(f"  {i}. {rec}")

    # HTML report link
    lines.append(f"\n[🔗 {t('meta_review.view_report')}]({_meta_report_url})")

    msg_content = "\n".join(lines)

    # Generate Word/Excel exports
    elements = []
    try:
        from src.analysis.daily_audit import (
            export_meta_review_word,
            export_meta_review_excel,
        )

        word_path = str(export_meta_review_word(meta))
        if Path(word_path).exists():
            wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
            elements.append(cl.File(name=wname, path=word_path, display="inline"))

        excel_path = str(export_meta_review_excel(meta))
        if Path(excel_path).exists():
            ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
            elements.append(cl.File(name=ename, path=excel_path, display="inline"))
    except Exception as e:
        logging.getLogger(__name__).warning("Meta review export failed: %s", e)

    await cl.Message(content=msg_content, author="Eira", elements=elements).send()


async def _show_pipeline_progress():
    """Show pipeline progress/completion status. No message if no runs exist."""
    try:
        _pipeline_dir = Path("data/analysis_pipeline")
        if _pipeline_dir.exists():
            _run_files = sorted(
                _pipeline_dir.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for _rf in _run_files[:1]:  # Latest run only
                _rd = json.loads(_rf.read_text(encoding="utf-8"))
                _st = _rd.get("status", "")
                _rows = _rd.get("rows", {})
                _total = _rd.get("total_rows") or len(_rows)
                _completed = _rd.get("completed_rows") or 0
                _pct = _rd.get("progress_percent") or (
                    round((_completed / _total) * 100, 1) if _total > 0 else 0
                )
                _phase = _rd.get("current_phase", "")
                if _st == "running" and _total > 0:
                    _filled = int(_pct / 5)  # 20 chars total
                    _empty = 20 - _filled
                    _bar = "\u2588" * _filled + "\u2591" * _empty
                    progress_msg = t(
                        "crossexam.pipeline_running",
                        bar=_bar,
                        completed=_completed,
                        total=_total,
                        percent=_pct,
                        phase=_phase,
                    )
                    await cl.Message(content=progress_msg, author="Eira").send()
                elif _st == "completed" and _total > 0:
                    progress_msg = t("crossexam.pipeline_completed", total=_total)
                    await cl.Message(content=progress_msg, author="Eira").send()
            # NOTE: No message when no runs exist — "analysis not started"
            # is noise when user hasn't requested analysis yet.
    except Exception:
        pass  # Don't block startup


# ============================================================
# Chat Start
# ============================================================


@cl.on_chat_start
async def on_chat_start():
    """Initialize chat session (guarded against duplicate calls)"""
    profile = cl.user_session.get("chat_profile")
    ensure_upload_folder()

    # Guard against duplicate on_chat_start calls (Chainlit may fire twice with chat profiles)
    if cl.user_session.get("_chat_started"):
        return
    cl.user_session.set("_chat_started", True)

    # Eira avatar: Chainlit 2.9+ auto-loads from /public/avatars/eira.svg by author name

    # Start background regulatory scheduler (first user only)
    global _regulatory_scheduler_started
    async with _regulatory_scheduler_lock:
        if not _regulatory_scheduler_started:
            _regulatory_scheduler_started = True
            asyncio.create_task(_regulatory_background_scheduler())

    # Start background daily audit scheduler (first user only)
    global _daily_audit_scheduler_started
    async with _daily_audit_scheduler_lock:
        if not _daily_audit_scheduler_started:
            _daily_audit_scheduler_started = True
            asyncio.create_task(_daily_audit_background_scheduler())

    # Check for saved user settings (auto-reconnect)
    saved = load_user_settings()

    # Initialize session state
    provider_choices = get_provider_choices()

    if saved and saved.get("provider_id"):
        # Restore saved settings
        default_provider_name = saved.get(
            "provider_name",
            provider_choices[0][0] if provider_choices else "Ollama (Local)",
        )
        default_provider_id = saved.get("provider_id", "ollama")
        default_model = saved.get("model_name", "default")
        restored_api_key = saved.get("api_key", "")
        restored_language = saved.get("language", "zh-TW")
        user_name = saved.get("user_name", "")
    else:
        default_provider_name = (
            provider_choices[0][0] if provider_choices else "Ollama (Local)"
        )
        default_provider_id = provider_choices[0][1] if provider_choices else "ollama"
        default_models = get_model_choices(default_provider_id)
        default_model = default_models[0] if default_models else "default"
        restored_api_key = ""
        restored_language = "zh-TW"
        user_name = ""

    cl.user_session.set("provider_name", default_provider_name)
    cl.user_session.set("provider_id", default_provider_id)
    cl.user_session.set("model_name", default_model)
    cl.user_session.set("api_key", restored_api_key)
    cl.user_session.set("real_api_key", restored_api_key)
    cl.user_session.set("show_api_key", False)
    cl.user_session.set("language", restored_language)
    cl.user_session.set("message_history", [])
    cl.user_session.set("user_name", user_name)

    # Doc Control specific state
    cl.user_session.set("pending_files", [])
    cl.user_session.set("current_ocr_result", None)
    cl.user_session.set("current_doc_info", None)
    cl.user_session.set("current_file_path", None)
    cl.user_session.set("awaiting_delete_confirm", False)

    # Watermark removed — always confirmed
    cl.user_session.set("watermark_confirmed", True)

    # Signature detection toggle state
    cl.user_session.set("signature_detection_enabled", True)  # Default: enabled
    cl.user_session.set("sig_detection_asked", False)

    # If we have saved settings with API key, set it up
    if restored_api_key and default_provider_id != "ollama":
        setup_api_key(default_provider_id, restored_api_key)

    # Send settings (with restored values if available)
    if saved and saved.get("provider_id"):
        settings = build_chat_settings(
            current_provider_name=default_provider_name,
            current_provider_id=default_provider_id,
            current_api_key=restored_api_key,
            current_model=default_model,
            show_api_key=False,
            current_language=next(
                (k for k, v in LANG_CODE_MAP.items() if v == restored_language),
                SUPPORTED_LANGUAGES[0],
            ),
        )
    else:
        settings = build_chat_settings()
    await settings.send()

    # Greeting flow: always show welcome/instructions ONCE at startup
    doc_count, doc_limit = get_document_count()

    # Always show profile-specific welcome + instructions (shown only once at session start)
    if profile == "\u6587\u4ef6\u7ba1\u5236 (Doc Control)":
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

    # Check for pending reports from previous disconnected sessions
    try:
        pending = get_pending_reports()
        if pending:
            for report in pending[:3]:  # Show max 3 pending reports
                cmd = report.get("command", "unknown")
                status = report.get("status", "")
                cache_id = report.get("cache_id", "")
                created = report.get("created_at", "")[:19]  # trim to seconds

                # Prefer final reports, fall back to baseline
                word_path = report.get("final_word_path") or report.get(
                    "baseline_word_path", ""
                )
                excel_path = report.get("final_excel_path") or report.get(
                    "baseline_excel_path", ""
                )

                if word_path and Path(word_path).exists():
                    cmd_label = (
                        "法規清單" if cmd == "regulatory_list" else "法規清單更新"
                    )
                    status_label = (
                        "✅ 完成"
                        if status == "completed"
                        else "⚠️ 基線報告"
                        if status == "baseline_ready"
                        else "⚠️ 中斷"
                    )
                    notice = (
                        f"📥 **先前的報告已產生** ({cmd_label})\n"
                        f"狀態：{status_label} | 時間：{created}\n"
                        f"請下載以下檔案："
                    )
                    # Show cached file as cl.File for direct download
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements = [cl.File(name=wname, path=word_path, display="inline")]
                    # Also check if Excel version exists alongside
                    excel_path = word_path.replace(".docx", ".xlsx")
                    if Path(excel_path).exists():
                        ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                        elements.append(
                            cl.File(name=ename, path=excel_path, display="inline")
                        )
                    await cl.Message(content=notice, elements=elements).send()
                    mark_cache_delivered(cache_id)
    except Exception:
        pass  # Don't block startup if cache check fails

    # Show recent HTML report links on reconnect
    try:
        _pipeline_dir = Path("data/analysis_pipeline")
        if _pipeline_dir.exists():
            _run_files = sorted(
                _pipeline_dir.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            _lang = cl.user_session.get("language", "zh-TW")
            _shown = 0
            for _rf in _run_files[:3]:  # Check latest 3 runs
                try:
                    _run_data = json.loads(_rf.read_text(encoding="utf-8"))
                    _run_status = _run_data.get("status", "")
                    _run_id = _run_data.get("run_id", _rf.stem)
                    if (
                        _run_status == "completed"
                        and _run_data.get("total_rows", 0) > 0
                    ):
                        _report_url = f"/api/report/page/{_run_id}?lang={_lang}"
                        _created = _run_data.get("started_at", "")
                        if isinstance(_created, (int, float)):
                            from datetime import datetime as _dt

                            _created = _dt.fromtimestamp(_created).strftime(
                                "%Y-%m-%d %H:%M"
                            )
                        elif _created:
                            _created = str(_created)[:16]
                        else:
                            continue  # Skip runs with no started_at
                        _total = _run_data.get("total_rows", 0)
                        _completed = _run_data.get("completed_rows", 0)
                        await cl.Message(
                            content=(
                                f"\U0001f4ca **{t('report.previous_report')}**\n"
                                f"{t('report.status')}: \u2705 {t('report.completed')} "
                                f"({_completed}/{_total})\n"
                                f"{t('report.time')}: {_created}\n"
                                f"[\ud83d\udd17 {t('report.view_report')}]({_report_url})"
                            ),
                        ).send()
                        _shown += 1
                except (json.JSONDecodeError, OSError, KeyError):
                    continue
    except Exception:
        pass  # Don't block startup

    # NOTE: Daily audit summary is now shown via _auto_trigger_crossexam()
    # inside _send_eira_introduction(), which handles both fresh runs and
    # cached results. No separate reconnect display needed — the daily audit
    # section in _auto_trigger_crossexam() checks for today's cached file
    # and displays it with scores + HTML link + Word/Excel exports.

    # Eira introduction + freshness check + daily audit + signature detection
    # Correct order: intro → 法規更新 → 簽章詢問
    # _auto_trigger_crossexam() is now called inside _send_eira_introduction()
    # so it runs for BOTH new users (after name entry) and returning users.
    if saved and user_name:
        # Returning user with saved settings — show Eira intro + setup questions
        await _send_eira_introduction(user_name, profile, doc_count, doc_limit)
    else:
        # New user — wait for LLM settings first, then ask name in on_settings_update
        cl.user_session.set("eira_name_pending", True)


async def _send_eira_introduction(
    user_name: str, profile: str, doc_count: int, doc_limit: int
):
    """Send Eira introduction, then run startup sequence, then signature toggle.

    Correct startup order for Doc Control:
      1. Eira 歡迎詞 (introduction)
      2. 法規更新 with progress % (freshness check + crawl, once per calendar day)
      3. 當日交叉詰問 daily audit (run or show cached, once per calendar day)
      4. 10日總檢 meta review (if ≥10 new daily audits since last meta)
      5. 簽章詢問 (signature detection toggle)
    """
    intro = t("eira.introduction", name=user_name)
    await cl.Message(content=intro, author="Eira").send()

    # Only run Doc Control-specific steps for Doc Control profile
    if profile == "文件管制 (Doc Control)":
        # Steps 2-4: Freshness check → daily audit → meta review
        await _auto_trigger_crossexam()

        # Step 5: Ask signature detection toggle
        await _ask_sig_detection_toggle(user_name)


@cl.on_chat_end
async def on_chat_end():
    """Handle session disconnect — save any in-progress analysis to cache."""
    try:
        # Save any in-progress regulatory_list analysis
        assessment = cl.user_session.get("last_regulatory_assessment", "")
        if assessment:
            save_analysis_cache(
                cache_id=f"regulatory_list_session_end_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                command="regulatory_list",
                assessment=assessment,
                status="session_ended",
                provider_id=cl.user_session.get("provider_id", ""),
                model_name=cl.user_session.get("model_name", ""),
            )

        # Save any in-progress regulatory_update analysis
        update_assessment = cl.user_session.get("last_regulatory_update_assessment", "")
        if update_assessment:
            save_analysis_cache(
                cache_id=f"regulatory_update_session_end_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                command="regulatory_update",
                assessment=update_assessment,
                status="session_ended",
                provider_id=cl.user_session.get("provider_id", ""),
                model_name=cl.user_session.get("model_name", ""),
            )

        # Save user settings on disconnect
        user_name = cl.user_session.get("user_name", "")
        if user_name:
            save_user_settings(
                user_name=user_name,
                provider_id=cl.user_session.get("provider_id", ""),
                provider_name=cl.user_session.get("provider_name", ""),
                model_name=cl.user_session.get("model_name", ""),
                api_key=cl.user_session.get("real_api_key", "")
                or cl.user_session.get("api_key", ""),
                language=cl.user_session.get("language", "zh-TW"),
            )
    except Exception:
        pass  # Session may already be cleaned up


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

    phoenix_status = "✅ Active (Multi-Project)" if PHOENIX_ENABLED else "❌ Disabled"
    phoenix_url = _detect_phoenix_endpoint().replace("/v1/traces", "")
    phoenix_projects = (
        ", ".join(PHOENIX_PROJECT_MAP.values()) if PHOENIX_ENABLED else "N/A"
    )

    return f"""{t("status.title")}

- **{t("status.doc_count")}**: {doc_count}/{doc_limit}
- **{t("status.provider")}**: {provider_name}
- **{t("status.model")}**: {model_name}
- **{t("status.ocr")}**: {t("status.ocr_ready")}
- **{t("status.ui")}**: Chainlit
- **Phoenix Tracing**: {phoenix_status} ({phoenix_url})
- **Phoenix Projects**: {phoenix_projects}"""


def _classify_all_docs_sync(all_docs, storage, lang):
    """Classify all documents by content (runs in thread pool to avoid blocking)."""

    doc_type_cache = {}
    for doc in all_docs:
        doc_id = doc["doc_id"]
        title = doc.get("title", "N/A")
        raw_doc_type = doc.get("doc_type", "OTHER")
        doc_result = storage.get_document(doc_id)
        content_for_classify = ""
        if doc_result and doc_result.get("success"):
            content_for_classify = doc_result.get("content", "")[:3000]
        doc_type_cache[doc_id] = _get_display_doc_type(
            doc_id, title, content_for_classify, raw_doc_type, lang
        )
    return doc_type_cache


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
        lang = cl.user_session.get("language", "zh-TW")

        # Classify all docs in background thread (I/O heavy)
        import asyncio

        doc_type_cache = await asyncio.to_thread(
            _classify_all_docs_sync, all_docs, storage, lang
        )

        doc_lines = []
        for doc in all_docs:
            doc_id = doc["doc_id"]
            title = doc.get("title", "N/A")
            display_type = doc_type_cache.get(doc_id, doc.get("doc_type", "OTHER"))
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
                    f"| {doc_id} | {title} | {display_type} | v{ver} | {created_at} | {created_by} | {row_status} |"
                )

        doc_list = "\n".join(doc_lines)
        summary_parts = [t("allrecords.summary_active", count=active_count)]
        if superseded_count:
            summary_parts.append(
                t("allrecords.summary_superseded", count=superseded_count)
            )
        if obsolete_count:
            summary_parts.append(t("allrecords.summary_obsolete", count=obsolete_count))
        sep = "、" if lang == "ja-JP" else "，" if lang.startswith("zh") else ", "
        summary_str = sep.join(summary_parts)
        return f"""{t("allrecords.title", doc_count=len(all_docs), version_count=total_versions, summary=summary_str)}

{t("allrecords.header")}
{doc_list}

{t("allrecords.hint_doclist")}
{t("allrecords.hint_audit")}"""
    except Exception as e:
        return t("allrecords.error", error=str(e))


async def handle_document_list() -> str:
    """Handle 文件清單 command - show only current formal (active) versions."""
    try:
        md_service = MarkdownStoreService()
        storage = get_markdown_store()
        docs = md_service.list_documents()

        lang = cl.user_session.get("language", "zh-TW")

        if not docs:
            return t("no_saved_docs")

        active_docs = [d for d in docs if d.get("status", "active") == "active"]

        if not active_docs:
            return t("no_active_docs")

        # Classify all active docs in background thread
        import asyncio

        doc_type_cache = await asyncio.to_thread(
            _classify_all_docs_sync, active_docs, storage, lang
        )

        doc_lines = []
        for d in active_docs:
            display_type = doc_type_cache.get(d["doc_id"], d.get("doc_type", "OTHER"))
            doc_lines.append(
                f"| {d['doc_id']} | {d.get('title', 'N/A')} | {display_type} | v{d['current_version']} |"
            )
        doc_list = "\n".join(doc_lines)
        return f"""{t("doclist.title", count=len(active_docs))}

{t("doclist.header")}
{doc_list}

{t("doclist.hint_list")}
{t("doclist.hint_search")}"""
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

    download_stats = _build_download_stats(records)

    if format_type == "word":
        filepath = export_to_word(records, download_stats=download_stats)
        msg = t("audit.export_word", count=len(records))
    elif format_type == "excel":
        filepath = export_to_excel(records, download_stats=download_stats)
        msg = t("audit.export_excel", count=len(records))
    else:
        return (
            None,
            t("audit.export_pdf_wip"),
        )

    return filepath, msg


def _classify_document(doc_id: str, title: str, content: str, doc_type: str) -> str:
    """
    Classify a document as 'qms_internal' or 'regulatory_uploaded' based on content analysis.

    QMS internal docs: company procedures, work instructions, forms, quality manuals
    Regulatory uploaded: actual law/standard documents uploaded by user (e.g., ISO 13485 PDF)

    NOTE: doc_id prefixes (QM-, QP-, etc.) are NOT used for classification because
    different companies use different naming conventions. Classification is purely
    content-driven with title/filename as secondary signals.
    """
    import re

    title_upper = (title or "").upper().strip()
    content_sample = (content[:3000] if content else "").lower()

    # --- Signal 1: Title / filename contains regulatory standard identifiers ---
    # If the document itself IS a standard/regulation (not just referencing one)
    regulatory_title_patterns = [
        r"ISO\s*\d{4,5}",  # ISO 13485, ISO 14971
        r"IEC\s*\d{4,5}",  # IEC 62304, IEC 60601
        r"21\s*CFR",  # 21 CFR Part 820
        r"MDR\s*2017",  # EU MDR 2017/745
        r"REGULATION.*\(EU\)",  # Regulation (EU)
        r"CNS\s*\d{4,5}",  # CNS 15013
        r"ASTM\s*[A-Z]?\s*\d{3,5}",  # ASTM standards
        r"GB\s*/?T?\s*\d{4,5}",  # Chinese GB standards
        r"JIS\s*[A-Z]\s*\d{4}",  # Japanese JIS standards
        r"EN\s*\d{4,5}",  # European EN standards
        r"BS\s*EN\s*\d{4,5}",  # British Standards
        r"AS/NZS\s*\d{4}",  # Australia/NZ standards
        r"MDSAP",  # Medical Device Single Audit Program
        r"MDD\s*93",  # EU MDD 93/42/EEC
    ]
    title_is_regulation = any(
        re.search(p, title_upper) for p in regulatory_title_patterns
    )

    # --- Signal 2: Content structure analysis ---
    # QMS internal docs have operational/procedural structure
    qms_indicators = [
        # Structural sections typical of company procedures
        "purpose of this",
        "purpose:",
        "目的",
        "本程序",
        "本作業指導",
        "scope:",
        "適用範圍",
        "responsibility",
        "責任",
        "權限",
        "procedure:",
        "作業步驟",
        "作業程序",
        "作業內容",
        "work instruction",
        "作業指導",
        "程序書",
        "表單說明",
        "form instruction",
        "how to complete",
        "revision history",
        "版本紀錄",
        "文件編號",
        "document number",
        "effective date",
        "生效日期",
        "approved by",
        "核准",
        "審查",
        "reviewed by",
        "this document establishes",
        "this procedure defines",
        # Company-specific process language
        "baseline controls",
        "baseline domain",
        "when to use",
        "trigger:",
        "觸發條件",
        "執行頻率",
    ]
    # Regulatory docs have legal/normative structure
    regulatory_indicators = [
        # Standard/regulation structural language
        "international standard",
        "國際標準",
        "this standard specifies",
        "this standard establishes",
        "this standard provides",
        "normative reference",
        "規範性引用文件",
        "terms and definitions",
        "術語與定義",
        "用語和定義",
        "shall comply",
        "shall conform",
        "shall meet",
        "clause ",
        "annex ",
        "附錄",
        "條款",
        "article ",
        "第.*條",
        "第.*款",
        # Legal language
        "regulation",
        "directive",
        "指令",
        "this regulation",
        "member states",
        "會員國",
        "official journal",
        "federal register",
        "公報",
        "the manufacturer shall",
        "製造商應",
        "notified body",
        "驗證機構",
        "公告機構",
        "conformity assessment",
        "符合性評鑑",
        "essential requirements",
        "general safety and performance",
        "基本要求",
        "一般安全與性能要求",
        "technical documentation",
        "技術文件檔案",
        # Explicitly a published standard document
        "published by",
        "copyright",
        "版權",
        "all rights reserved",
        "iso/tc",
        "iec/tc",
        "技術委員會",
    ]

    qms_score = sum(1 for kw in qms_indicators if kw in content_sample)
    reg_score = sum(1 for kw in regulatory_indicators if kw in content_sample)

    # --- Decision logic ---
    # Title IS a regulation identifier = strong signal
    if title_is_regulation and reg_score >= 2:
        return "regulatory_uploaded"
    if title_is_regulation and qms_score <= 2:
        return "regulatory_uploaded"

    # Content clearly regulatory (many regulatory indicators, few QMS indicators)
    if reg_score >= 5 and reg_score > qms_score:
        return "regulatory_uploaded"

    # doc_type OTHER with more regulatory than QMS signals
    if doc_type == "OTHER" and reg_score > qms_score:
        return "regulatory_uploaded"

    # Default: treat as QMS internal document
    return "qms_internal"


def _get_display_doc_type(
    doc_id: str, title: str, content: str, doc_type: str, lang: str = "zh-TW"
) -> str:
    """
    Return a display-friendly document type label based on content analysis.

    Hierarchy (QMS internal):
      1階: 品質手冊 (Quality Manual)
      2階: 程序書 (Procedure/SOP)
      3階: 作業指導書 (Work Instruction)
      4階: 表單 (Form)
    External:
      外來法規文件 (External Regulatory Document)
    """
    # First: is this a regulatory document or QMS internal?
    classification = _classify_document(doc_id, title, content, doc_type)

    is_zh = lang.startswith("zh")
    is_ja = lang.startswith("ja")

    if classification == "regulatory_uploaded":
        if is_zh:
            return "外來法規文件"
        elif is_ja:
            return "外部規制文書"
        else:
            return "Regulatory Doc"

    # QMS internal: classify by hierarchy level based on content
    content_lower = (content[:3000] if content else "").lower()
    title_lower = (title or "").lower()

    # Level 1: Quality Manual indicators
    manual_indicators = [
        "quality manual",
        "品質手冊",
        "质量手冊",
        "品質政策",
        "組織架構",
        "管理代表",
        "management representative",
        "organizational structure",
        "系統範圍",
        "qms scope",
    ]
    # Level 2: Procedure indicators
    procedure_indicators = [
        "procedure",
        "程序書",
        "程序",
        "受控文件",
        "this procedure defines",
        "本程序",
        "執行程序",
        "process flow",
        "流程",
        "運作程序",
    ]
    # Level 3: Work Instruction indicators
    wi_indicators = [
        "work instruction",
        "作業指導",
        "作業說明",
        "作業步驟",
        "step by step",
        "step 1",
        "this work instruction",
        "本作業指導",
    ]
    # Level 4: Form indicators
    form_indicators = [
        "form",
        "表單",
        "檢查表",
        "checklist",
        "template",
        "紀錄表",
        "record form",
        "申請單",
        "報告表",
        "log",
        "登錄表",
        "審核表",
        "計畫表",
        "how to complete",
        "填寫說明",
        "instructions for completing",
    ]

    manual_score = sum(
        1 for kw in manual_indicators if kw in content_lower or kw in title_lower
    )
    proc_score = sum(
        1 for kw in procedure_indicators if kw in content_lower or kw in title_lower
    )
    wi_score = sum(
        1 for kw in wi_indicators if kw in content_lower or kw in title_lower
    )
    form_score = sum(
        1 for kw in form_indicators if kw in content_lower or kw in title_lower
    )

    scores = {
        "manual": manual_score,
        "procedure": proc_score,
        "wi": wi_score,
        "form": form_score,
    }
    best = max(scores, key=scores.get)

    # Only classify if there's a clear signal (score > 0)
    if scores[best] == 0:
        # Fallback to original doc_type
        fallback_map = {
            "SOP": ("程序書" if is_zh else "手順書" if is_ja else "Procedure"),
            "WI": (
                "作業指導書" if is_zh else "作業指導書" if is_ja else "Work Instruction"
            ),
            "FORM": ("表單" if is_zh else "フォーム" if is_ja else "Form"),
            "DHF": ("設計歷史檔案" if is_zh else "DHF" if is_ja else "DHF"),
            "OTHER": ("其他" if is_zh else "その他" if is_ja else "Other"),
        }
        return fallback_map.get(doc_type, doc_type)

    if is_zh:
        label_map = {
            "manual": "1階-品質手冊",
            "procedure": "2階-程序書",
            "wi": "3階-作業指導書",
            "form": "4階-表單",
        }
    elif is_ja:
        label_map = {
            "manual": "1階-品質マニュアル",
            "procedure": "2階-手順書",
            "wi": "3階-作業指導書",
            "form": "4階-フォーム",
        }
    else:
        label_map = {
            "manual": "L1-Manual",
            "procedure": "L2-Procedure",
            "wi": "L3-WI",
            "form": "L4-Form",
        }

    return label_map[best]


# Helper: wrap synchronous LLM streaming generator with per-chunk timeout
# to prevent indefinite hangs when provider connection stalls mid-stream.
STREAMING_CHUNK_TIMEOUT = 300  # seconds — max wait for a single chunk (increased from 120 for long regulatory analysis)
MAX_CONTINUATIONS = 15  # max auto-continuation loops when LLM output is truncated

_STREAM_SENTINEL = object()  # sentinel for detecting generator exhaustion


async def _iter_stream_with_timeout(
    sync_generator, chunk_timeout: int = STREAMING_CHUNK_TIMEOUT
):
    """Yield chunks from a synchronous streaming generator with per-chunk timeout.

    Runs each `next()` call in a thread pool so it doesn't block the event loop,
    and applies asyncio.wait_for with the given timeout per chunk.
    Raises asyncio.TimeoutError if any single chunk takes longer than chunk_timeout.
    """
    iterator = iter(sync_generator)
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    asyncio.to_thread(next, iterator, _STREAM_SENTINEL),
                    timeout=chunk_timeout,
                )
                if chunk is _STREAM_SENTINEL:
                    return  # generator exhausted normally
                yield chunk
            except asyncio.TimeoutError:
                raise  # propagate to caller
            except StopIteration:
                return
    finally:
        # Clean up the underlying generator to release HTTP connections
        if hasattr(sync_generator, "close"):
            try:
                sync_generator.close()
            except Exception:
                pass


async def _ask_report_type() -> list[str]:
    """Ask user to choose analysis depth: basic (P0-P3), standard (P0-P4), or full (P0-P6).

    Returns:
        list of phase keys to skip.
        ["phase_4", "phase_5", "phase_6"] = basic    (基礎分析, P0-P3)
        ["phase_5", "phase_6"]            = standard (標準分析, P0-P4)
        []                                = full     (完整分析, P0-P6)

    When the dialog times out or fails, falls back to the phase config persisted
    via the HTML report panel (/api/report/phase-config), then to standard mode
    (P0-P4, skip only Phase 5 and 6) so Phase 5 is included when the user has
    explicitly configured it to run.
    """
    def _fallback_skip_phases() -> list[str]:
        """Return persisted phase config or standard default (skip only P5/P6)."""
        try:
            from src.analysis.report_api import get_custom_skip_phases
            saved = get_custom_skip_phases()
            # Only use saved config if it explicitly excludes Phase 5 (user opted in)
            if saved is not None:
                return saved
        except Exception:
            pass
        # Default: standard mode — skip only source-check (P6); keep Phase 5
        return ["phase_6"]

    try:
        res = await cl.AskActionMessage(
            content=(f"{t('report_type.title')}\n\n{t('report_type.description')}"),
            actions=[
                cl.Action(
                    name="report_type_normal",
                    payload={"value": "normal"},
                    label=t("report_type.btn_normal"),
                ),
                cl.Action(
                    name="report_type_risk",
                    payload={"value": "risk"},
                    label=t("report_type.btn_risk"),
                ),
                cl.Action(
                    name="report_type_deep",
                    payload={"value": "deep"},
                    label=t("report_type.btn_deep"),
                ),
            ],
            timeout=120,
        ).send()
    except Exception:
        _fb = _fallback_skip_phases()
        await cl.Message(content=t("report_type.selected_normal")).send()
        return _fb

    action_name = res.get("name", "") if res else ""
    if action_name == "report_type_deep":
        await cl.Message(content=t("report_type.selected_deep")).send()
        return []
    elif action_name == "report_type_risk":
        await cl.Message(content=t("report_type.selected_risk")).send()
        return ["phase_5", "phase_6"]
    elif action_name == "report_type_normal":
        await cl.Message(content=t("report_type.selected_normal")).send()
        return ["phase_4", "phase_5", "phase_6"]
    else:
        # Timeout (res is None) — use persisted config or standard default
        _fb = _fallback_skip_phases()
        await cl.Message(content=t("report_type.selected_normal")).send()
        return _fb


async def _ask_product_docs_upload() -> Optional[str]:
    """Ask user if they want to upload product documents before analysis.

    Returns:
        session_id (str) if user uploaded documents, None if skipped.
    """
    try:
        res = await cl.AskActionMessage(
            content=(
                "📦 **產品文件上傳（選填）**\n\n"
                "您可以在分析前上傳產品相關文件，讓 LLM 更準確地評估法規符合性：\n"
                "- 使用說明書 (IFU)\n"
                "- 產品規格書\n"
                "- 產品介紹\n"
                "- 其他產品相關文件\n\n"
                "📌 上傳的文件僅用於本次分析，報告產生後將自動刪除。"
            ),
            actions=[
                cl.Action(
                    name="upload_product_docs",
                    payload={"value": "upload"},
                    label="📎 上傳產品文件",
                ),
                cl.Action(
                    name="skip_product_docs",
                    payload={"value": "skip"},
                    label="⏭️ 跳過，直接分析",
                ),
            ],
            timeout=120,
        ).send()
    except Exception:
        # Timeout or error — skip upload
        return None

    if not res or res.get("name") != "upload_product_docs":
        await cl.Message(content="⏭️ 跳過產品文件上傳，直接開始分析。").send()
        return None

    # User chose to upload — show file upload dialog
    try:
        files = await cl.AskFileMessage(
            content=(
                "📎 **請上傳產品文件**\n\n"
                "支援格式：PDF、Word、Excel、PowerPoint、圖片、文字檔\n"
                "不限數量，不需簽章。\n\n"
                "上傳完成後點擊確認即可。"
            ),
            accept=["*/*"],
            max_files=20,
            max_size_mb=50,
            timeout=300,
        ).send()
    except Exception:
        await cl.Message(content="⏭️ 上傳逾時或取消，直接開始分析。").send()
        return None

    if not files:
        await cl.Message(content="⏭️ 未上傳任何檔案，直接開始分析。").send()
        return None

    # Process uploaded files through OCR and save to temp storage
    product_store = get_product_docs_store()
    session_id = product_store.create_session()

    await cl.Message(content=f"⏳ 正在處理 {len(files)} 份產品文件...").send()

    success_count = 0
    for f in files:
        try:
            result = process_document(f.path)
            if result and result.get("success") and result.get("content"):
                save_result = product_store.save_document(
                    session_id=session_id,
                    filename=f.name,
                    content=result["content"],
                    original_path=f.path,
                )
                if save_result.get("success"):
                    success_count += 1
            else:
                # If OCR fails, try reading as plain text
                try:
                    raw_text = Path(f.path).read_text(encoding="utf-8", errors="ignore")
                    if raw_text.strip():
                        save_result = product_store.save_document(
                            session_id=session_id,
                            filename=f.name,
                            content=raw_text,
                            original_path=f.path,
                        )
                        if save_result.get("success"):
                            success_count += 1
                except Exception:
                    pass
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to process product doc {f.name}: {e}"
            )

    if success_count > 0:
        await cl.Message(
            content=f"✅ 已成功處理 {success_count}/{len(files)} 份產品文件，將納入本次分析。"
        ).send()
        return session_id
    else:
        product_store.cleanup_session(session_id)
        await cl.Message(content="⚠️ 產品文件處理失敗，將不含產品文件進行分析。").send()
        return None


async def handle_regulatory_list():
    """Handle 法規清單 command — scan regulatory references, integrate crawl data, LLM assessment."""
    storage = get_markdown_store()
    scan_result = storage.scan_regulatory_references()
    # Store in session for later export
    cl.user_session.set("last_regulatory_scan", scan_result)

    # Base table markdown
    base_response = format_regulatory_table_markdown(scan_result)

    # Try to integrate crawl results + LLM assessment
    store = get_regulatory_store()
    last_crawl = store.load_last_results()

    has_crawl_data = last_crawl and last_crawl.get("results")

    if not has_crawl_data:
        # Inform user: no crawl data, but analysis will still proceed
        try:
            await cl.Message(
                content="ℹ️ 尚未執行「法規清單更新」，將僅以本地文件進行合規性分析。\n"
                "如需整合線上法規資訊，可另外執行「法規清單更新」。"
            ).send()
        except Exception:
            pass

    # Build online data summary for LLM (enhanced: source labels + PDF info)
    online_parts = []
    for r in (last_crawl or {}).get("results", []):
        if r.get("crawl_status") == "success":
            content_preview = r.get("content_markdown", "")[:1500]
            pdf_info = ""
            if r.get("has_pdf") and r.get("pdf_urls"):
                pdf_info = f"\n  📥 PDF 可下載: {', '.join(r['pdf_urls'][:3])}"
            online_parts.append(
                f"### [來源: 🌐 網路爬取] {r['region']} — {r['agency']} ({r.get('agency_name', '')})\n"
                f"URL: {r['url']}\n"
                f"爬取日期: {r.get('crawl_timestamp', '未知')[:10]}\n"
                f"{content_preview}{pdf_info}"
            )
    online_data = "\n\n".join(online_parts) if online_parts else "無線上資料"

    # Build local data summary for LLM (enhanced: include standard names + doc_ids)
    aggregate = scan_result.get("aggregate", [])
    local_parts = []
    for ref in aggregate:
        std = ref.get("standard", "")
        docs = ref.get("referenced_by", [])
        if isinstance(docs, list):
            doc_ids = (
                docs
                if all(isinstance(d, str) for d in docs)
                else [d.get("doc_id", "") for d in docs]
            )
        else:
            doc_ids = []
        local_parts.append(f"- {std} (引用於: {', '.join(doc_ids)})")
    local_data = "\n".join(local_parts) if local_parts else "本地文件未引用任何法規標準"

    # Build regulatory Markdown DB content for LLM
    # IMPORTANT: Use user's selected regions from config as the primary filter.
    # This ensures only the regions the user explicitly chose are included,
    # preventing the LLM from citing data from other countries.
    config_mgr = get_regulatory_config()
    if config_mgr.has_config():
        filter_regions = set(config_mgr.get_selected_regions())
    else:
        # Fallback: derive from last crawl results if no config exists yet
        filter_regions = set()
        for r in (last_crawl or {}).get("results", []):
            if r.get("crawl_status") == "success" and r.get("region"):
                filter_regions.add(r["region"])
    reg_md_store = get_regulatory_markdown_store()
    reg_db_parts = []
    # Filter by selected regions to only include relevant data
    if filter_regions:
        for region in filter_regions:
            region_docs = reg_md_store.list_documents(region=region, status="active")
            for rd in region_docs[:10]:  # Limit per region to avoid token overflow
                doc_full = reg_md_store.get_document(rd.get("doc_id", ""))
                if doc_full:
                    content = doc_full.get("content", "")[:800]
                    reg_db_parts.append(
                        f"### {rd.get('region', '')} \u2014 {rd.get('agency', '')} ({rd.get('title', '')[:60]})\n"
                        f"\u5132\u5b58\u8def\u5f91: {rd.get('markdown_path', '')}\n"
                        f"{content}"
                    )
    regulatory_db_data = (
        "\n\n".join(reg_db_parts)
        if reg_db_parts
        else "\u6cd5\u898f Markdown DB \u4e2d\u7121\u5df2\u5132\u5b58\u6587\u4ef6"
    )

    # Classify and split by_document into QMS internal vs regulatory uploaded
    qms_doc_parts = []
    regulatory_doc_parts = []
    by_doc = scan_result.get("by_document", [])
    for doc_info in by_doc[:30]:  # Limit to 30 docs
        doc_id = doc_info.get("doc_id", "")
        title = doc_info.get("title", "")
        standards = doc_info.get("standards", [])
        version = doc_info.get("current_version", "")
        doc_type = doc_info.get("doc_type", "OTHER")
        # Get actual content and metadata from markdown storage
        doc_result = storage.get_document(doc_id)
        content_full = ""
        content_preview = ""
        upload_date = "未知"
        original_file = "未知"
        if doc_result and doc_result.get("success"):
            content_full = doc_result.get("content", "")
            content_preview = content_full[:600]
            upload_date = doc_result.get("created_at", "未知")[:10]
            original_file = doc_result.get("original_file", "未知")
        # Classify based on content analysis
        classification = _classify_document(doc_id, title, content_full, doc_type)
        if classification == "regulatory_uploaded":
            # Distinguish: this document IS the uploaded regulation.
            # Standards listed in 'standards' are referenced WITHIN this document,
            # NOT independently uploaded. Clarify this for the LLM.
            referenced_standards_note = ""
            if standards:
                referenced_standards_note = (
                    f"\n⚠️ 注意：以下標準僅在本文件內被引用/提及，系統中並無這些標準的完整原文："
                    f"\n{', '.join(standards)}"
                    f"\n（請勿將這些被引用的標準視為已上傳的法規文件，它們的條文內容不可用於分析）"
                )
            regulatory_doc_parts.append(
                f"### [來源: 📎 手動上傳的法規文件（獨立上傳的完整原文）] {doc_id} — {title}\n"
                f"版本: v{version} | 上傳日期: {upload_date} | 原始檔案: {original_file}\n"
                f"本文件為使用者直接上傳的法規/標準完整原文，可直接引用其條文內容。"
                f"{referenced_standards_note}\n"
                f"{content_preview}"
            )
        else:
            qms_doc_parts.append(
                f"### [類型: 📄 公司品質文件] {doc_id} — {title}\n"
                f"版本: v{version} | 上傳日期: {upload_date} | 原始檔案: {original_file}\n"
                f"引用標準: {', '.join(standards)}\n"
                f"{content_preview}"
            )
    # Combine: QMS docs first, then regulatory uploads (both go into uploaded_docs_data)
    all_doc_parts = []
    if qms_doc_parts:
        all_doc_parts.append("## 公司品質文件（程序書/作業指導書/表單/品質手冊）")
        all_doc_parts.extend(qms_doc_parts)
    if regulatory_doc_parts:
        all_doc_parts.append(
            "## 手動上傳的法規文件（獨立上傳至系統的法規/標準完整原文，非從其他文件內引用）"
        )
        all_doc_parts.extend(regulatory_doc_parts)
    # Add summary note about document counts for LLM clarity
    if regulatory_doc_parts or qms_doc_parts:
        summary_note = (
            f"\n\n---\n"
            f"ℹ️ 文件統計：共 {len(regulatory_doc_parts)} 份獨立上傳的法規文件，{len(qms_doc_parts)} 份公司品質文件\n"
            f"❗ 重要：只有標記『📎 手動上傳的法規文件』的文件才有完整原文可供分析。"
            f"其他在文件內被引用/提及的標準（如 EN ISO 9001:2015、IEC 62304 等）"
            f"僅為引用關係，系統中並無這些標準的完整條文，請勿編造其內容。"
        )
        all_doc_parts.append(summary_note)
    uploaded_docs_data = "\n\n".join(all_doc_parts) if all_doc_parts else "無上傳文件"

    # Build SOP content data for LLM (actual procedure content for before/after comparison)
    sop_parts = []
    # Get documents that reference regulatory standards (these are the SOPs that may need updating)
    sop_doc_ids = set()
    for ref in aggregate:
        docs = ref.get("referenced_by", [])
        if isinstance(docs, list):
            for d in docs:
                if isinstance(d, str):
                    sop_doc_ids.add(d)
                elif isinstance(d, dict):
                    sop_doc_ids.add(d.get("doc_id", ""))
    # Read actual SOP content (limit to 15 most relevant docs)
    for sid in list(sop_doc_ids)[:15]:
        sop_result = storage.get_document(sid)
        if sop_result and sop_result.get("success"):
            sop_content = sop_result.get("content", "")
            sop_title = sop_result.get("title", sid)
            sop_ver = sop_result.get("version", "")
            # Include up to 3000 chars of SOP content for comparison
            sop_parts.append(
                f"### {sid} — {sop_title} (v{sop_ver})\n{sop_content[:3000]}"
            )
    sop_content_data = "\n\n".join(sop_parts) if sop_parts else "無可用的 SOP 內容"

    # ── Step 0: Ask user for optional product documents ──
    product_docs_session_id = await _ask_product_docs_upload()
    product_docs_data = ""
    if product_docs_session_id:
        product_docs_data = get_product_docs_store().get_session_content_for_prompt(
            product_docs_session_id, max_chars=8000
        )

    # ── Step 0.5: Ask user for report type (normal vs deep) ──
    _skip_phases = await _ask_report_type()

    # ── Step 1: Generate baseline Word/Excel BEFORE LLM (guaranteed report) ──
    _cache_id = f"regulatory_list_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    baseline_word_path = ""
    baseline_excel_path = ""
    try:
        baseline_word_path = export_regulatory_to_word(
            scan_result, assessment=None, source_command="regulatory_list"
        )
        baseline_excel_path = export_regulatory_to_excel(
            scan_result, assessment=None, source_command="regulatory_list"
        )
        save_analysis_cache(
            cache_id=_cache_id,
            command="regulatory_list",
            scan_result=scan_result,
            status="baseline_ready",
            baseline_word_path=baseline_word_path,
            baseline_excel_path=baseline_excel_path,
        )
        import logging

        logging.getLogger(__name__).info(
            f"Baseline regulatory report generated: {baseline_word_path}"
        )
    except Exception as baseline_err:
        import logging

        logging.getLogger(__name__).warning(
            f"Baseline report generation failed: {baseline_err}"
        )

    # ── Run analysis pipeline (replaces one-shot LLM) ──
    provider_id = cl.user_session.get("provider_id", "ollama")
    model_name = cl.user_session.get("model_name", "default")
    api_key = cl.user_session.get("api_key", "").strip()

    assessment = ""
    pipeline_result = None
    try:
        setup_api_key(provider_id, api_key)
        manager = create_provider_manager(provider_id)
        if provider_id != "ollama":
            manager.disable_fallback = True

        # Progress message callback for Chainlit
        async def _send_pipeline_msg(text: str) -> None:
            try:
                await cl.Message(content=text).send()
            except Exception:
                pass

        await cl.Message(content=t("regulatory_update.assessment_analyzing")).send()

        # Run the structured analysis pipeline
        with phoenix_span(
            "analysis_pipeline",
            profile="文件管制 (Doc Control)",
            attributes={
                "pipeline.command": "regulatory_list",
                "pipeline.model": model_name,
                "pipeline.standard": "ISO_13485",
            },
        ):

            async def _on_run_id_ready(run_id: str):
                _lang = cl.user_session.get("language", "zh-TW")
                report_url = f"/api/report/page/{run_id}?lang={_lang}"
                await cl.Message(
                    content=f"\n\n📊 **[{t('report.open_realtime')}]({report_url})**\n\n"
                    f"{t('report.page_online')}"
                ).send()

            # Resolve selected regions → regulation profile IDs
            # Reload crawled profiles from disk first so any new profiles saved
            # during a recent 法規清單更新 are available in PREDEFINED_REGULATIONS.
            try:
                from src.analysis.compliance_rules import (
                    get_profile_ids_for_regions,
                    load_all_crawled_regulations,
                )

                load_all_crawled_regulations()
                _reg_list_selected_ids = get_profile_ids_for_regions(
                    list(filter_regions)
                )
            except Exception:
                _reg_list_selected_ids = []

            pipeline_result = await run_pipeline_analysis(
                scan_result=scan_result,
                llm_completion_fn=manager.completion,
                model=model_name,
                standard="ISO_13485",
                source_command="regulatory_list",
                send_message_fn=_send_pipeline_msg,
                on_run_id_ready=_on_run_id_ready,
                selected_regulations=_reg_list_selected_ids
                if _reg_list_selected_ids
                else None,
                custom_skip_phases=_skip_phases if _skip_phases else None,
            )

        if pipeline_result and pipeline_result.success:
            assessment = pipeline_result.to_summary_markdown()

            # Show pipeline summary
            try:
                await cl.Message(content=assessment).send()
            except Exception:
                pass
        else:
            err_msg = pipeline_result.error if pipeline_result else "未知錯誤"
            assessment = f"⚠️ 分析管線執行失敗: {err_msg}"
            try:
                await cl.Message(content=assessment).send()
            except Exception:
                pass

    except Exception as e:
        assessment = (
            f"⚠️ QMS 評估報告產生失敗: {str(e)[:200]}\n\n"
            f"📋 **可能的阻塞原因：**\n"
            f"- 🔌 **連線中斷**：網路不穩定或 LLM 提供商服務異常\n"
            f"- 🔑 **API Key 無效或過期**：請檢查 API Key 是否正確\n"
            f"- 💾 **提供商限流**：API 請求頻率或 Token 配額已達提供商限制\n"
            f"- ⚙️ **模型不支援**：所選模型可能不支援此類長文分析\n\n"
            f"請確認 LLM 設定正確後重試。"
        )
        try:
            await cl.Message(content=assessment).send()
        except Exception:
            pass

    # Store assessment for export (protected: session may be disconnected)
    try:
        cl.user_session.set("last_regulatory_assessment", assessment)
    except Exception:
        pass  # Session disconnected

    # Update cache with final assessment
    try:
        save_analysis_cache(
            cache_id=_cache_id,
            command="regulatory_list",
            assessment=assessment,
            status="completed"
            if (pipeline_result and pipeline_result.success)
            else "llm_failed",
            provider_id=provider_id,
            model_name=model_name,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Failed to save final analysis cache")

    # Save analysis report to persistent markdown DB
    if assessment and not assessment.startswith("⚠️"):
        try:
            analysis_store = get_regulatory_analysis_store()
            analysis_store.save_analysis_report(
                analysis_content=assessment,
                source_command="regulatory_list",
                crawl_summary=last_crawl.get("summary") if last_crawl else None,
                analyzed_standards=[ref.get("standard", "") for ref in aggregate],
                analyzed_documents=[d.get("doc_id", "") for d in by_doc[:30]],
                provider=provider_id,
                model=model_name,
                is_truncated=False,
            )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Failed to save analysis report: {e}")

    # Save pipeline state file path for report page (Phase D)
    if pipeline_result and pipeline_result.state_file_path:
        try:
            cl.user_session.set(
                "last_pipeline_state_path", pipeline_result.state_file_path
            )
        except Exception:
            pass

        # Send report page link to user
        try:
            _lang = cl.user_session.get("language", "zh-TW")
            report_url = f"/api/report/page/{pipeline_result.run_id}?lang={_lang}"
            await cl.Message(
                content=f"\n\n📊 **[{t('report.open_interactive')}]({report_url})**\n\n"
                f"{t('report.page_features')}"
            ).send()
        except Exception:
            pass

    # Generate Word/Excel exports with pipeline assessment
    if assessment and not assessment.startswith("⚠️"):
        try:
            scan_result_for_export = cl.user_session.get("last_regulatory_scan")
            if scan_result_for_export:
                word_path = export_regulatory_to_word(
                    scan_result_for_export,
                    assessment=assessment,
                    source_command="regulatory_list",
                )
                excel_path = export_regulatory_to_excel(
                    scan_result_for_export,
                    assessment=assessment,
                    source_command="regulatory_list",
                )
                save_analysis_cache(
                    cache_id=_cache_id,
                    command="regulatory_list",
                    final_word_path=word_path,
                    final_excel_path=excel_path,
                    status="completed",
                )
                try:
                    elements = []
                    if word_path and Path(word_path).exists():
                        wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                        elements.append(
                            cl.File(name=wname, path=word_path, display="inline")
                        )
                    if excel_path and Path(excel_path).exists():
                        ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                        elements.append(
                            cl.File(name=ename, path=excel_path, display="inline")
                        )
                    await cl.Message(
                        content=base_response,
                        elements=elements,
                    ).send()
                except Exception:
                    pass
            else:
                try:
                    await cl.Message(content=base_response).send()
                except Exception:
                    pass
        except Exception as export_err:
            import logging

            logging.getLogger(__name__).warning(
                f"Auto-export on normal completion failed: {export_err}"
            )
            try:
                await cl.Message(content=base_response).send()
            except Exception:
                pass
    else:
        try:
            await cl.Message(content=base_response).send()
        except Exception:
            pass

    # Suggestion: update quality documents based on this analysis, then re-run
    if assessment and not assessment.startswith("⚠️"):
        try:
            suggestion = (
                "\n\n---\n"
                "💡 **建議：** 請先依據本次分析結果更新品質文件，再重新執行「法規清單」以驗證修改是否完善。"
            )
            await cl.Message(content=suggestion).send()
        except Exception:
            pass  # WebSocket disconnected

    # ── Cleanup: delete temporary product documents ──
    if product_docs_session_id:
        try:
            get_product_docs_store().cleanup_session(product_docs_session_id)
        except Exception:
            pass


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
        assessment = cl.user_session.get("last_regulatory_assessment")
        filepath = export_regulatory_to_word(
            scan_result, assessment=assessment, source_command="regulatory_list"
        )
        msg = t("regulatory.export_word", count=len(aggregate))
    elif format_type == "excel":
        assessment = cl.user_session.get("last_regulatory_assessment")
        filepath = export_regulatory_to_excel(
            scan_result, assessment=assessment, source_command="regulatory_list"
        )
        msg = t("regulatory.export_excel", count=len(aggregate))
    else:
        return None, t("regulatory.export_hint")

    return filepath, msg


# ============================================================
# Regulatory Update Handlers (法規清單更新)
# ============================================================


async def handle_regulatory_update():
    """Handle 法規清單更新 command — crawl regulatory websites and show results."""
    # Step 0: Show existing local regulatory references first
    storage = get_markdown_store()
    scan_result = storage.scan_regulatory_references()
    aggregate = scan_result.get("aggregate", [])
    by_doc = scan_result.get("by_document", [])

    if aggregate:
        local_lines = ["📚 **目前本地文件引用的法規清單**\n"]
        for ref in aggregate:
            std = ref.get("standard", "")
            doc_ids = ref.get("referenced_by", [])
            local_lines.append(
                f"- **{std}** — 引用文件數: {len(doc_ids)}"
            )  # Bug 10: show count only
        local_lines.append(
            f"\n> 共 {len(aggregate)} 項法規標準，來自 {len(by_doc)} 份文件。"
        )
        local_lines.append("\n---\n")
        await cl.Message(content="\n".join(local_lines)).send()
    else:
        await cl.Message(content="ℹ️ 目前本地文件中尚未引用任何法規標準。\n\n---").send()

    # Also show existing regulatory markdown DB stats
    reg_md_store = get_regulatory_markdown_store()
    reg_stats = reg_md_store.get_stats()
    reg_active = reg_stats.get("total_active", 0)
    if reg_active > 0:
        by_region = reg_stats.get("by_region", {})
        db_lines = [f"\n📂 **法規 Markdown DB** — 共 {reg_active} 份已儲存文件\n"]
        for rg, cnt in sorted(by_region.items()):
            db_lines.append(f"- {rg}: {cnt} 份")
        db_lines.append("\n---")
        await cl.Message(content="\n".join(db_lines)).send()

    # Show last crawl info if any
    result_store = get_regulatory_store()
    last_crawl = result_store.load_last_results()
    if last_crawl and last_crawl.get("results"):
        last_ts = last_crawl.get("crawl_timestamp", "未知")
        last_summary = last_crawl.get("summary", {})
        prev_success = last_summary.get("success_count", 0)
        prev_total = last_summary.get("total_sites", 0)
        await cl.Message(
            content=f"📅 上次爬取時間: {last_ts}\n"
            f"上次結果: {prev_success}/{prev_total} 個網站成功"
        ).send()

    config_mgr = get_regulatory_config()
    store = get_regulatory_store()

    # Check if config already exists (non-first run)
    if config_mgr.has_config():
        selected_regions = config_mgr.get_selected_regions()
        if selected_regions:
            # Non-first run: crawl only selected regions
            await cl.Message(content=t("regulatory_update.scanning_selected")).send()
            crawler = get_regulatory_crawler()
            with phoenix_span(
                "regulatory_crawl",
                profile="文件管制 (Doc Control)",
                attributes={
                    "crawl.type": "selected_regions",
                    "crawl.regions": ", ".join(selected_regions),
                },
            ) as span:
                crawl_results = await crawler.crawl_selected_regions(selected_regions)
                if span is not None:
                    span.set_attribute(
                        "crawl.success_count",
                        crawl_results.get("summary", {}).get("success_count", 0),
                    )
                    span.set_attribute(
                        "crawl.failed_count",
                        crawl_results.get("summary", {}).get("failed_count", 0),
                    )
                    span.set_attribute(
                        "crawl.total_sites",
                        crawl_results.get("summary", {}).get("total_sites", 0),
                    )
        else:
            # Config exists but no regions selected — full crawl
            await cl.Message(content=t("regulatory_update.scanning")).send()
            crawler = get_regulatory_crawler()
            with phoenix_span(
                "regulatory_crawl",
                profile="文件管制 (Doc Control)",
                attributes={"crawl.type": "all_regions_no_config"},
            ) as span:
                crawl_results = await crawler.crawl_all_regions()
                if span is not None:
                    span.set_attribute(
                        "crawl.success_count",
                        crawl_results.get("summary", {}).get("success_count", 0),
                    )
                    span.set_attribute(
                        "crawl.failed_count",
                        crawl_results.get("summary", {}).get("failed_count", 0),
                    )
                    span.set_attribute(
                        "crawl.total_sites",
                        crawl_results.get("summary", {}).get("total_sites", 0),
                    )
    else:
        # First run: crawl all regions
        await cl.Message(content=t("regulatory_update.scanning")).send()
        crawler = get_regulatory_crawler()
        with phoenix_span(
            "regulatory_crawl",
            profile="文件管制 (Doc Control)",
            attributes={"crawl.type": "first_run_all_regions"},
        ) as span:
            crawl_results = await crawler.crawl_all_regions()
            if span is not None:
                span.set_attribute(
                    "crawl.success_count",
                    crawl_results.get("summary", {}).get("success_count", 0),
                )
                span.set_attribute(
                    "crawl.failed_count",
                    crawl_results.get("summary", {}).get("failed_count", 0),
                )
                span.set_attribute(
                    "crawl.total_sites",
                    crawl_results.get("summary", {}).get("total_sites", 0),
                )

    # Store results in session
    cl.user_session.set("last_regulatory_update", crawl_results)

    # Save crawl results to JSON
    store.save_crawl_results(crawl_results)

    # Save individual markdown files to independent regulatory markdown DB
    reg_md_store = get_regulatory_markdown_store()
    save_result = reg_md_store.save_from_crawl_results(crawl_results)
    saved_count = save_result.get("saved_count", 0)
    if saved_count > 0:
        await cl.Message(
            content=f"💾 已儲存 {saved_count} 份法規文件至法規 Markdown DB"
        ).send()
    # Build per-country status summary
    summary = crawl_results.get("summary", {})
    results = crawl_results.get("results", [])

    # Group results by region
    region_status = {}  # region -> {"success": [...], "failed": [...]}
    for r in results:
        region = r.get("region", "Unknown")
        if region not in region_status:
            region_status[region] = {"success": [], "failed": []}
        if r.get("crawl_status") == "success":
            region_status[region]["success"].append(r)
        else:
            region_status[region]["failed"].append(r)

    # Build display: which countries succeeded / failed
    lines = [
        f"📋 **法規清單更新結果** (成功 {summary.get('success_count', 0)}/{summary.get('total_sites', 0)} 個網站，"
        f"耗時 {summary.get('crawl_duration_seconds', 0):.1f} 秒)\n",
        "### ✅ 可爬取的國家/地區\n",
    ]

    success_regions = []
    failed_regions = []

    for region, status in region_status.items():
        success_sites = status["success"]
        failed_sites = status["failed"]
        total_sites = len(success_sites) + len(failed_sites)

        if success_sites:
            success_regions.append(region)
            agencies = ", ".join(s["agency"] for s in success_sites)
            lines.append(
                f"- ✅ **{region}** — {len(success_sites)}/{total_sites} 個網站成功 ({agencies})"
            )
            # If some sites failed in this region, note them
            for fs in failed_sites:
                reason = fs.get("failure_reason", "未知原因")
                lines.append(f"  - ⚠️ {fs['agency']}: {reason[:80]}")
        else:
            failed_regions.append(region)

    if failed_regions:
        lines.append("\n### ❌ 無法爬取的國家/地區\n")
        for region in failed_regions:
            failed_sites = region_status[region]["failed"]
            for fs in failed_sites:
                reason = fs.get("failure_reason", "未知原因")
                lines.append(f"- ❌ **{region}** — {fs['agency']}: {reason[:100]}")

    # Ask user which countries to keep
    lines.append("\n---\n")
    lines.append("### 📝 請選擇要追蹤的法規地區\n")
    lines.append("您可以使用以下任一方式選擇：")
    lines.append("- 輸入編號：`1,2,5` 或 `1 2 5`")
    lines.append("- 輸入地區名稱：`美國、日本、台灣` 或 `USA, Japan`")
    lines.append("- 只保留特定地區：`只保留美國` 或 `只要歐盟和日本`")
    lines.append("- 排除特定地區：`除了中國以外都要`")
    lines.append("- 全部保留：`全部` 或 `all`")
    lines.append("- 刪除特定法規：`刪除 FDA` 或 `刪除 ISO 13485`")
    lines.append("- 或直接點擊下方按鈕\n")

    available_regions = get_available_regions()
    for i, region in enumerate(available_regions, 1):
        if region in success_regions:
            lines.append(f"{i}. ✅ {region}")
        elif region in failed_regions:
            lines.append(f"{i}. ❌ {region} (爬取失敗)")
        else:
            lines.append(f"{i}. ⬜ {region}")

    # Store region mapping in session for later use
    cl.user_session.set("regulatory_available_regions", available_regions)
    cl.user_session.set("regulatory_success_regions", success_regions)
    cl.user_session.set("awaiting_region_selection", True)

    region_display = "\n".join(lines)

    actions = [
        cl.Action(
            name="confirm_regulatory_regions_default",
            payload={"use_default": True},
            label="✅ 使用預設（保留所有可爬取地區）",
        ),
        cl.Action(
            name="skip_regulatory_regions",
            payload={"skip": True},
            label="⏭️ 跳過，直接匯出目前結果",
        ),
        cl.Action(
            name="manage_regulatory_docs",
            payload={"manage": True},
            label="🗑️ 管理已儲存法規文件",
        ),
    ]

    await cl.Message(content=region_display, actions=actions).send()


async def handle_regulatory_update_rescan(selected_regions: list):
    """Re-scan selected regions and show final results with export buttons."""
    config_mgr = get_regulatory_config()
    store = get_regulatory_store()
    available_regions = get_available_regions()

    # Compute excluded regions
    excluded = [r for r in available_regions if r not in selected_regions]

    # Save config
    config_mgr.update_regions(selected_regions, excluded)
    await cl.Message(content=t("regulatory_update.config_saved")).send()

    # Cleanup: remove regulatory markdown DB entries from non-selected regions
    reg_md_store = get_regulatory_markdown_store()
    cleanup_result = reg_md_store.cleanup_non_selected_regions(selected_regions)
    if cleanup_result.get("deleted_count", 0) > 0:
        reg_md_store.purge_deleted()
        import logging

        logging.getLogger(__name__).info(
            f"Cleaned up {cleanup_result['deleted_count']} docs from non-selected regions"
        )

    from src.analysis.compliance_rules import cleanup_non_selected_crawled_profiles

    profile_cleanup = cleanup_non_selected_crawled_profiles(selected_regions)
    if profile_cleanup.get("deleted_count", 0) > 0:
        import logging as _log_cleanup

        _log_cleanup.getLogger(__name__).info(
            f"Removed {profile_cleanup['deleted_count']} old crawled profiles: "
            f"{profile_cleanup['deleted_ids']}"
        )

    # Re-scan only selected regions
    await cl.Message(content=t("regulatory_update.rescan")).send()
    crawler = get_regulatory_crawler()
    with phoenix_span(
        "regulatory_crawl_rescan",
        profile="文件管制 (Doc Control)",
        attributes={
            "crawl.type": "rescan_selected",
            "crawl.regions": ", ".join(selected_regions),
        },
    ) as span:
        crawl_results = await crawler.crawl_selected_regions(selected_regions)
        if span is not None:
            span.set_attribute(
                "crawl.success_count",
                crawl_results.get("summary", {}).get("success_count", 0),
            )
            span.set_attribute(
                "crawl.failed_count",
                crawl_results.get("summary", {}).get("failed_count", 0),
            )
            span.set_attribute(
                "crawl.total_sites",
                crawl_results.get("summary", {}).get("total_sites", 0),
            )
            span.set_attribute(
                "crawl.duration_seconds",
                crawl_results.get("summary", {}).get("crawl_duration_seconds", 0),
            )

    # Store results
    cl.user_session.set("last_regulatory_update", crawl_results)
    store.save_crawl_results(crawl_results)

    # Save individual markdown files to independent regulatory markdown DB
    reg_md_store = get_regulatory_markdown_store()
    reg_md_store.save_from_crawl_results(crawl_results)

    _crawl_summary = crawl_results.get("summary", {})
    _success_n = _crawl_summary.get("success_count", 0)
    _failed_n = _crawl_summary.get("failed_count", 0)
    _total_n = _crawl_summary.get("total_sites", 0)
    _failed_regions_set = set()
    _success_regions_set = set()
    for _cr in crawl_results.get("results", []):
        if _cr.get("crawl_status") == "success":
            _success_regions_set.add(_cr.get("region", ""))
        else:
            _failed_regions_set.add(_cr.get("region", ""))
    _failed_only = _failed_regions_set - _success_regions_set

    _summary_lines = [f"📡 爬蟲完成：{_success_n}/{_total_n} 個網站成功"]
    if _failed_only:
        _summary_lines.append(
            f"⚠️ 以下國家所有網站均爬取失敗，將嘗試備援方式生成 Profile：\n"
            + "\n".join(f"  ❌ {r}" for r in sorted(_failed_only))
        )
    await cl.Message(content="\n".join(_summary_lines)).send()

    # ── Step 0.5: Generate RegulationProfile for countries without one ──
    # For predefined 7 countries, profiles already exist.
    # For any other selected country, use LLM to auto-generate a profile.
    try:
        from src.analysis.compliance_rules import (
            get_regions_without_profile,
            get_profile_ids_for_regions,
            load_all_crawled_regulations,
        )
        from src.analysis.regulation_analyzer import analyze_regulation_with_llm

        regions_needing_profile = get_regions_without_profile(selected_regions)
        if regions_needing_profile:
            await cl.Message(
                content=f"🔍 偵測到 {len(regions_needing_profile)} 個國家尚無法規 Profile，"
                f"開始 LLM 自動分析...\n"
                f"國家：{', '.join(regions_needing_profile)}"
            ).send()

            # Set up LLM for profile generation
            _provider_id = cl.user_session.get("provider_id", "ollama")
            _model_name = cl.user_session.get("model_name", "default")
            _api_key = cl.user_session.get("api_key", "").strip()
            if _provider_id and _model_name and (_provider_id == "ollama" or _api_key):
                setup_api_key(_provider_id, _api_key)
                _manager = create_provider_manager(_provider_id)
                if _provider_id != "ollama":
                    _manager.disable_fallback = True

                for _region in regions_needing_profile:
                    # Gather crawled texts for this region
                    _region_crawl_texts = [
                        {
                            "region": r.get("region", ""),
                            "agency": r.get("agency", ""),
                            "content_markdown": r.get("content_markdown", ""),
                            "url": r.get("url", ""),
                        }
                        for r in crawl_results.get("results", [])
                        if r.get("region") == _region
                        and r.get("crawl_status") == "success"
                        and r.get("content_markdown")
                    ]

                    if not _region_crawl_texts:
                        await cl.Message(
                            content=f"⚠️ {_region} 無可用的爬蟲資料，跳過 Profile 生成。"
                        ).send()
                        continue

                    async def _profile_progress(msg: str) -> None:
                        try:
                            await cl.Message(content=msg).send()
                        except Exception:
                            pass

                    try:
                        _profile = await analyze_regulation_with_llm(
                            region_name=_region,
                            crawled_texts=_region_crawl_texts,
                            llm_completion_fn=_manager.completion,
                            model=_model_name,
                            send_progress_fn=_profile_progress,
                        )
                        if _profile:
                            await cl.Message(
                                content=f"✅ {_region} 法規 Profile 已生成："
                                f"{_profile.regulation_id} "
                                f"({len(_profile.iso_mapped)} 條對應，"
                                f"{len(_profile.unique_requirements)} 項獨有要求)"
                            ).send()
                        else:
                            await cl.Message(
                                content=f"⚠️ {_region} 法規 Profile 生成失敗。"
                            ).send()
                    except Exception as _profile_err:
                        import logging

                        logging.getLogger(__name__).warning(
                            f"Failed to generate profile for {_region}: {_profile_err}"
                        )
                        await cl.Message(
                            content=f"⚠️ {_region} 法規 Profile 生成失敗：{str(_profile_err)[:100]}"
                        ).send()
            else:
                await cl.Message(
                    content="⚠️ 未設定 LLM，無法自動生成法規 Profile。"
                ).send()

        # Resolve selected_regions → profile IDs for pipeline
        # Reload crawled profiles so any LLM-generated profiles from the steps
        # above are guaranteed to be in PREDEFINED_REGULATIONS (handles cases
        # where save_crawled_regulation succeeded on disk but profile generation
        # path was partially re-entered or interrupted).
        load_all_crawled_regulations()
        _selected_regulation_ids = get_profile_ids_for_regions(selected_regions)
    except Exception as _profile_setup_err:
        import logging

        logging.getLogger(__name__).warning(
            f"Profile generation setup failed: {_profile_setup_err}"
        )
        _selected_regulation_ids = []

    # ── Step 1: Generate baseline Word/Excel BEFORE LLM (guaranteed report) ──
    _cache_id_update = f"regulatory_update_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    baseline_word_path_upd = ""
    baseline_excel_path_upd = ""
    try:
        from src.utils.regulatory_update_export import (
            export_regulatory_update_to_word,
            export_regulatory_update_to_excel,
        )

        baseline_word_path_upd = export_regulatory_update_to_word(
            crawl_results, assessment=None, source_command="regulatory_update"
        )
        baseline_excel_path_upd = export_regulatory_update_to_excel(
            crawl_results, assessment=None, source_command="regulatory_update"
        )
        save_analysis_cache(
            cache_id=_cache_id_update,
            command="regulatory_update",
            crawl_results=crawl_results,
            status="baseline_ready",
            baseline_word_path=baseline_word_path_upd,
            baseline_excel_path=baseline_excel_path_upd,
        )
        import logging

        logging.getLogger(__name__).info(
            f"Baseline regulatory update report generated: {baseline_word_path_upd}"
        )
    except Exception as baseline_err:
        import logging

        logging.getLogger(__name__).warning(
            f"Baseline update report generation failed: {baseline_err}"
        )

    # ── Ask user for optional product documents ──
    product_docs_session_id = await _ask_product_docs_upload()
    product_docs_data = ""
    if product_docs_session_id:
        product_docs_data = get_product_docs_store().get_session_content_for_prompt(
            product_docs_session_id, max_chars=8000
        )

    # ── Ask user for report type (normal vs deep) ──
    _skip_phases_update = await _ask_report_type()

    # ── Run analysis pipeline (replaces one-shot LLM) ──
    storage = get_markdown_store()
    scan_result_local = storage.scan_regulatory_references()
    assessment = ""
    pipeline_result = None
    provider_id = cl.user_session.get("provider_id", "ollama")
    model_name = cl.user_session.get("model_name", "default")
    api_key = cl.user_session.get("api_key", "").strip()
    try:
        if provider_id and model_name and (provider_id == "ollama" or api_key):
            setup_api_key(provider_id, api_key)
            manager = create_provider_manager(provider_id)
            if provider_id != "ollama":
                manager.disable_fallback = True

            # Progress message callback for Chainlit
            async def _send_pipeline_msg_update(text: str) -> None:
                try:
                    await cl.Message(content=text).send()
                except Exception:
                    pass

            await cl.Message(content=t("regulatory_update.assessment_analyzing")).send()

            # Run the structured analysis pipeline
            with phoenix_span(
                "analysis_pipeline",
                profile="文件管制 (Doc Control)",
                attributes={
                    "pipeline.command": "regulatory_update",
                    "pipeline.model": model_name,
                    "pipeline.standard": "ISO_13485",
                    "pipeline.regions": ", ".join(selected_regions),
                },
            ):

                async def _on_run_id_ready_update(run_id: str):
                    _lang = cl.user_session.get("language", "zh-TW")
                    report_url = f"/api/report/page/{run_id}?lang={_lang}"
                    await cl.Message(
                        content=f"\n\n📊 **[{t('report.open_realtime')}]({report_url})**\n\n"
                        f"{t('report.page_online')}"
                    ).send()

                pipeline_result = await run_pipeline_analysis(
                    scan_result=scan_result_local,
                    llm_completion_fn=manager.completion,
                    model=model_name,
                    standard="ISO_13485",
                    source_command="regulatory_update",
                    send_message_fn=_send_pipeline_msg_update,
                    on_run_id_ready=_on_run_id_ready_update,
                    selected_regulations=_selected_regulation_ids
                    if _selected_regulation_ids
                    else None,
                    custom_skip_phases=_skip_phases_update
                    if _skip_phases_update
                    else None,
                )

            if pipeline_result and pipeline_result.success:
                assessment = pipeline_result.to_summary_markdown()
                try:
                    await cl.Message(content=assessment).send()
                except Exception:
                    pass
            else:
                err_msg = pipeline_result.error if pipeline_result else "未知錯誤"
                assessment = f"⚠️ 分析管線執行失敗: {err_msg}"
                try:
                    await cl.Message(content=assessment).send()
                except Exception:
                    pass
        else:
            assessment = "⚠️ 未設定 LLM 提供商或 API Key，無法執行分析。"
            try:
                await cl.Message(content=assessment).send()
            except Exception:
                pass

    except Exception as e:
        assessment = (
            f"⚠️ QMS 評估報告產生失敗: {str(e)[:200]}\n\n請確認 LLM 設定正確後重試。"
        )
        import logging

        logging.getLogger(__name__).warning(f"Regulatory update pipeline failed: {e}")
        try:
            await cl.Message(content=assessment).send()
        except Exception:
            pass

    # Store assessment for export (protected: session may be disconnected)
    try:
        cl.user_session.set("last_regulatory_update_assessment", assessment)
    except Exception:
        pass

    # Update cache with final assessment
    try:
        save_analysis_cache(
            cache_id=_cache_id_update,
            command="regulatory_update",
            assessment=assessment,
            status="completed"
            if (pipeline_result and pipeline_result.success)
            else "llm_failed",
            provider_id=provider_id,
            model_name=model_name,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to save final analysis cache for regulatory update"
        )

    # Save analysis report to persistent markdown DB
    if assessment and not assessment.startswith("⚠️"):
        try:
            aggregate_local = scan_result_local.get("aggregate", [])
            by_doc_local = scan_result_local.get("by_document", [])
            analysis_store = get_regulatory_analysis_store()
            crawl_summary = crawl_results.get("summary") if crawl_results else None
            analysis_store.save_analysis_report(
                analysis_content=assessment,
                source_command="regulatory_update",
                crawl_summary=crawl_summary,
                analyzed_standards=[ref.get("standard", "") for ref in aggregate_local],
                analyzed_documents=[d.get("doc_id", "") for d in by_doc_local[:30]],
                provider=provider_id,
                model=model_name,
                is_truncated=False,
            )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Failed to save analysis report: {e}")

    # Save pipeline state file path for report page (Phase D)
    if pipeline_result and pipeline_result.state_file_path:
        try:
            cl.user_session.set(
                "last_pipeline_state_path", pipeline_result.state_file_path
            )
        except Exception:
            pass

        # Send report page link to user
        try:
            _lang = cl.user_session.get("language", "zh-TW")
            report_url = f"/api/report/page/{pipeline_result.run_id}?lang={_lang}"
            await cl.Message(
                content=f"\n\n📊 **[{t('report.open_interactive')}]({report_url})**\n\n"
                f"{t('report.page_features')}"
            ).send()
        except Exception:
            pass

    # Format crawl summary
    response = format_regulatory_update_markdown(crawl_results, assessment=None)

    # Generate Word/Excel exports with pipeline assessment
    if assessment and not assessment.startswith("⚠️"):
        try:
            word_path = export_regulatory_update_to_word(
                crawl_results, assessment=assessment, source_command="regulatory_update"
            )
            excel_path = export_regulatory_update_to_excel(
                crawl_results, assessment=assessment, source_command="regulatory_update"
            )
            save_analysis_cache(
                cache_id=_cache_id_update,
                command="regulatory_update",
                final_word_path=word_path,
                final_excel_path=excel_path,
                status="completed",
            )
            try:
                elements = []
                if word_path and Path(word_path).exists():
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
                if excel_path and Path(excel_path).exists():
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
                await cl.Message(
                    content=response,
                    elements=elements,
                ).send()
            except Exception:
                pass
        except Exception as export_err:
            import logging

            logging.getLogger(__name__).warning(
                f"Auto-export on normal completion failed: {export_err}"
            )
            try:
                await cl.Message(content=response).send()
            except Exception:
                pass
    else:
        try:
            await cl.Message(content=response).send()
        except Exception:
            pass

    # Suggestion: update quality documents based on this analysis, then re-run
    if assessment and not assessment.startswith("⚠️"):
        try:
            suggestion = (
                "\n\n---\n"
                "💡 **建議：** 請先依據本次分析結果更新品質文件，再重新執行「法規清單更新」以驗證修改是否完善。"
            )
            await cl.Message(content=suggestion).send()
        except Exception:
            pass  # WebSocket disconnected

    # ── Cleanup: delete temporary product documents ──
    if product_docs_session_id:
        try:
            get_product_docs_store().cleanup_session(product_docs_session_id)
        except Exception:
            pass


async def _show_regulatory_update_export_buttons():
    """Show export buttons for current regulatory update results (skip rescan)."""
    crawl_results = cl.user_session.get("last_regulatory_update")
    if not crawl_results:
        await cl.Message(content="⚠️ 沒有可匯出的法規更新結果。").send()
        return

    assessment = cl.user_session.get("last_regulatory_update_assessment", "")
    response = format_regulatory_update_markdown(crawl_results, assessment=assessment)

    # Pre-generate Word + Excel for direct download
    elements = []
    try:
        word_path = export_regulatory_update_to_word(
            crawl_results, assessment=assessment, source_command="regulatory_update"
        )
        if word_path and Path(word_path).exists():
            wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
            elements.append(cl.File(name=wname, path=word_path, display="inline"))
    except Exception:
        pass
    try:
        excel_path = export_regulatory_update_to_excel(
            crawl_results, assessment=assessment, source_command="regulatory_update"
        )
        if excel_path and Path(excel_path).exists():
            ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
            elements.append(cl.File(name=ename, path=excel_path, display="inline"))
    except Exception:
        pass

    await cl.Message(content=response, elements=elements).send()


async def handle_regulatory_update_export(format_type: str):
    """Handle regulatory update export to Word/Excel."""
    crawl_results = cl.user_session.get("last_regulatory_update")
    if not crawl_results:
        # Try loading from file
        store = get_regulatory_store()
        crawl_results = store.load_last_results()
        if not crawl_results:
            return None, "⚠️ 沒有可匯出的法規更新結果。請先執行「法規清單更新」。"

    results = crawl_results.get("results", [])
    if not results:
        return None, "⚠️ 法規更新結果為空。"

    total = len(results)
    if format_type == "word":
        assessment = cl.user_session.get("last_regulatory_update_assessment")
        filepath = export_regulatory_update_to_word(
            crawl_results, assessment=assessment, source_command="regulatory_update"
        )
        msg = t("regulatory_update.export_word", count=total)
    elif format_type == "excel":
        assessment = cl.user_session.get("last_regulatory_update_assessment")
        filepath = export_regulatory_update_to_excel(
            crawl_results, assessment=assessment, source_command="regulatory_update"
        )
        msg = t("regulatory_update.export_excel", count=total)
    else:
        return None, t("regulatory_update.export_prompt")

    return filepath, msg


# ============================================================
# Regulatory Document Management (管理已儲存法規文件)
# ============================================================


async def handle_regulatory_doc_management():
    """Show stored regulatory documents and allow deletion."""
    reg_md_store = get_regulatory_markdown_store()
    docs = reg_md_store.list_documents(status="active")

    if not docs:
        await cl.Message(content="ℹ️ 法規 Markdown DB 中尚無已儲存的法規文件。").send()
        return

    lines = [f"📂 **已儲存的法規文件** (共 {len(docs)} 份)\n"]
    for i, doc in enumerate(docs, 1):
        region = doc.get("region", "")
        agency = doc.get("agency", "")
        title = doc.get("title", "")[:60]
        ts = doc.get("crawl_timestamp", "")[:10]
        lines.append(f"{i}. **{region}** — {agency} | {title} ({ts})")

    lines.append("\n---")
    lines.append("\n### 🗑️ 刪除法規文件\n")
    lines.append("您可以使用以下方式刪除：")
    lines.append("- 輸入編號：`刪除 1,3,5` 或 `刪除 1 3 5`")
    lines.append("- 輸入關鍵字：`刪除 FDA` 或 `刪除 台灣`")
    lines.append("- 刪除全部：`刪除全部`")
    lines.append("- 或輸入 `取消` 返回\n")

    cl.user_session.set("awaiting_regulatory_delete", True)
    cl.user_session.set("regulatory_doc_list", docs)

    actions = [
        cl.Action(
            name="cancel_regulatory_delete",
            payload={"cancel": True},
            label="↩️ 取消，返回",
        ),
    ]

    await cl.Message(content="\n".join(lines), actions=actions).send()


async def _execute_regulatory_delete(user_input: str):
    """Parse and execute regulatory document deletion."""
    reg_md_store = get_regulatory_markdown_store()
    docs = cl.user_session.get("regulatory_doc_list", [])
    input_lower = user_input.lower().strip()

    # Detect cancel
    if input_lower in ("取消", "cancel", "返回", "back"):
        await cl.Message(content="✅ 已取消刪除操作。").send()
        return

    # Remove delete prefix keywords
    delete_prefixes = ["刪除", "移除", "刪掉", "去掉", "remove", "delete", "del"]
    cleaned = input_lower
    for prefix in delete_prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            break

    # Handle "全部" / "all"
    if cleaned in ("全部", "all", "所有"):
        all_doc_ids = [d.get("doc_id") for d in docs]
        deleted_items = []
        for doc_id in all_doc_ids:
            result = reg_md_store.delete_document(doc_id)
            if result.get("success"):
                deleted_items.append(result)
        await cl.Message(
            content=f"🗑️ 已刪除全部 {len(deleted_items)} 份法規文件。"
        ).send()
        return

    # Try numeric extraction
    numbers = re.findall(r"\b(\d{1,3})\b", cleaned)
    if numbers:
        deleted_items = []
        for num_str in numbers:
            idx = int(num_str) - 1  # User input is 1-based
            if 0 <= idx < len(docs):
                doc = docs[idx]
                doc_id = doc.get("doc_id", "")
                result = reg_md_store.delete_document(doc_id)
                if result.get("success"):
                    deleted_items.append(result)
        if deleted_items:
            names = ", ".join(f"{d['region']}/{d['agency']}" for d in deleted_items)
            await cl.Message(
                content=f"🗑️ 已刪除 {len(deleted_items)} 份法規文件: {names}"
            ).send()
        else:
            await cl.Message(content="⚠️ 未找到對應的文件編號。").send()
        return

    # Try keyword deletion
    if cleaned:
        result = reg_md_store.delete_by_keyword(cleaned)
        count = result.get("deleted_count", 0)
        if count > 0:
            items = result.get("deleted_items", [])
            names = ", ".join(f"{d['region']}/{d['agency']}" for d in items[:10])
            suffix = " ...等" if len(items) > 10 else ""
            await cl.Message(
                content=f"🗑️ 已刪除 {count} 份包含 '{cleaned}' 的法規文件: {names}{suffix}"
            ).send()
        else:
            await cl.Message(content=f"⚠️ 未找到包含 '{cleaned}' 的法規文件。").send()
        return

    await cl.Message(content="⚠️ 無法解析刪除指令。請輸入編號或關鍵字。").send()


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

    audit_log = ImmutableAuditLog()
    download_stats = _build_download_stats(audit_log.get_all_records())

    if format_type == "word":
        filepath = export_doclist_to_word(active_docs, download_stats=download_stats)
        msg = t("doclist.export_word", count=len(active_docs))
    elif format_type == "excel":
        filepath = export_doclist_to_excel(active_docs, download_stats=download_stats)
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

    audit_log = ImmutableAuditLog()
    download_stats = _build_download_stats(audit_log.get_all_records())

    if format_type == "word":
        filepath = export_allrecords_to_word(all_docs, download_stats=download_stats)
        msg = t("allrecords.export_word", count=len(all_docs))
    elif format_type == "excel":
        filepath = export_allrecords_to_excel(all_docs, download_stats=download_stats)
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

        # Count documents from registry (user-facing count)
        doc_count = len(doc_list)

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

        await cl.Message(content=t("delete.success", doc_count=doc_count)).send()
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


async def _send_inline_view(filepath: str, doc_id: str, level: str):
    """Helper: send a document for inline viewing (no download).

    If watermark decision hasn't been made yet, queue the view and ask first.
    """
    suffix = Path(filepath).suffix.lower()
    # For PDF files, show inline as PDF element
    if suffix == ".pdf":
        display_name = re.sub(r"^\d{14}_", "", Path(filepath).name)
        elements = [cl.Pdf(name=display_name, path=filepath, display="inline")]
        if level == "external":
            hint = t("view.external_hint")
        else:
            level_label = {"1": "1階", "2": "2階", "3": "3階", "4": "4階"}.get(
                level, level
            )
            hint = t("view.inline_hint", level=level_label)
        msg_text = t("view.inline_title", doc_id=doc_id) + "\n" + hint
        await cl.Message(content=msg_text, elements=elements).send()
        return

    # For non-PDF files, try converting to PDF for inline view
    pdf_path = convert_to_pdf_for_viewing(filepath)
    if pdf_path and pdf_path != filepath:
        display_name = Path(pdf_path).name
        elements = [cl.Pdf(name=display_name, path=pdf_path, display="inline")]
        if level == "external":
            hint = t("view.external_hint")
        else:
            level_label = {"1": "1階", "2": "2階", "3": "3階", "4": "4階"}.get(
                level, level
            )
            hint = t("view.inline_hint", level=level_label)
        msg_text = t("view.inline_title", doc_id=doc_id) + "\n" + hint
        await cl.Message(content=msg_text, elements=elements).send()
        return

    # Fallback: show markdown content from storage
    storage = get_markdown_store()
    doc_data = storage.get_document(doc_id)
    if doc_data and doc_data.get("success"):
        md_content = doc_data.get("content", "")
        if len(md_content) > 4000:
            md_content = md_content[:4000] + "\n\n... (內容截斷)"
        if level == "external":
            hint = t("view.external_hint")
        else:
            level_label = {"1": "1階", "2": "2階", "3": "3階", "4": "4階"}.get(
                level, level
            )
            hint = t("view.inline_hint", level=level_label)
        msg_text = (
            t("view.inline_title", doc_id=doc_id)
            + "\n"
            + hint
            + "\n\n"
            + t("view.no_pdf")
            + "\n\n---\n\n"
            + md_content
        )
        await cl.Message(content=msg_text).send()
    else:
        await cl.Message(content=t("view.no_pdf")).send()


async def _process_pending_upload_files():
    """Process any pending file uploads stored before sig detection was answered.

    When files are uploaded before sig detection is asked, they are stored as
    (name, path) tuples in session['pending_upload_files']. After sig detection,
    level range, and watermark are all decided, this function processes them.
    """
    pending = cl.user_session.get("pending_upload_files")
    if not pending:
        return
    cl.user_session.set("pending_upload_files", None)

    # Create simple namespace objects matching what handle_file_upload expects
    from types import SimpleNamespace

    file_elements = [SimpleNamespace(name=name, path=path) for name, path in pending]
    await handle_file_upload(file_elements)


async def _process_pending_inline_view():
    """Process any pending inline view request after watermark decision."""
    pending = cl.user_session.get("pending_inline_view")
    if not pending:
        return
    cl.user_session.set("pending_inline_view", None)
    await _send_inline_view(
        pending["filepath"],
        pending["doc_id"],
        pending["level"],
    )


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


# ============================================================
# Regulatory Update Action Callbacks (法規清單更新)
# ============================================================


@cl.action_callback("confirm_regulatory_regions_default")
async def on_confirm_regulatory_regions_default(action):
    """Use default region selection (all successfully crawled regions)."""
    await action.remove()
    cl.user_session.set("awaiting_region_selection", False)
    success_regions = cl.user_session.get("regulatory_success_regions", [])
    if not success_regions:
        success_regions = get_available_regions()
    await handle_regulatory_update_rescan(success_regions)


@cl.action_callback("skip_regulatory_regions")
async def on_skip_regulatory_regions(action):
    """Skip region selection, show export buttons for current results."""
    await action.remove()
    cl.user_session.set("awaiting_region_selection", False)

    # Save config with current success regions as default
    success_regions = cl.user_session.get("regulatory_success_regions", [])
    available_regions = get_available_regions()
    if success_regions:
        excluded = [r for r in available_regions if r not in success_regions]
        config_mgr = get_regulatory_config()
        config_mgr.update_regions(success_regions, excluded)

    await _show_regulatory_update_export_buttons()


@cl.action_callback("download_regulatory_update_word")
async def on_download_regulatory_update_word(action):
    """Download regulatory update report as Word."""
    await action.remove()
    filepath, msg_text = await handle_regulatory_update_export("word")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()


@cl.action_callback("download_regulatory_update_excel")
async def on_download_regulatory_update_excel(action):
    """Download regulatory update report as Excel."""
    await action.remove()
    filepath, msg_text = await handle_regulatory_update_export("excel")
    if filepath:
        await _send_file_download(filepath, msg_text)
    else:
        await cl.Message(content=msg_text).send()


@cl.action_callback("manage_regulatory_docs")
async def on_manage_regulatory_docs(action):
    """Open the regulatory document management view."""
    await action.remove()
    cl.user_session.set("awaiting_region_selection", False)
    await handle_regulatory_doc_management()


@cl.action_callback("cancel_regulatory_delete")
async def on_cancel_regulatory_delete(action):
    """Cancel regulatory document deletion."""
    await action.remove()
    cl.user_session.set("awaiting_regulatory_delete", False)
    await cl.Message(content="✅ 已取消刪除操作。").send()


@cl.action_callback("download_original_file")
async def on_download_original_file(action):
    """Download original uploaded file by doc_id — all levels allowed."""
    doc_id = action.payload.get("doc_id", "")
    if not doc_id:
        await cl.Message(content=t("download.no_doc_id")).send()
        await action.remove()
        return

    storage = get_markdown_store()
    file_path = storage.get_original_file_path(doc_id)
    if not file_path:
        await cl.Message(content=t("download.file_error", doc_id=doc_id)).send()
        await action.remove()
        return

    # Ask for downloader's name before proceeding
    cl.user_session.set("pending_download_doc_id", doc_id)
    cl.user_session.set("awaiting_download_name", True)
    await cl.Message(content="請問您的姓名？（將記錄於稽核紀錄）").send()
    await action.remove()


# ============================================================
# Signature Detection Toggle & Level Range Callbacks
# ============================================================


async def _ask_sig_detection_toggle(user_name: str):
    """Ask user whether to enable or disable signature detection."""
    actions = [
        cl.Action(
            name="sig_detection_enable",
            payload={"value": "enable"},
            label=t("sig_toggle.btn_enable"),
        ),
        cl.Action(
            name="sig_detection_disable",
            payload={"value": "disable"},
            label=t("sig_toggle.btn_disable"),
        ),
    ]
    await cl.Message(
        content=t("sig_toggle.ask", name=user_name),
        author="Eira",
        actions=actions,
    ).send()


async def _ask_level_range():
    """Ask user to select document control level range."""
    actions = [
        cl.Action(
            name="level_range_1_4",
            payload={"value": "1-4"},
            label=t("level_range.btn_1_4"),
        ),
        cl.Action(
            name="level_range_1_3",
            payload={"value": "1-3"},
            label=t("level_range.btn_1_3"),
        ),
        cl.Action(
            name="level_range_no_watermark",
            payload={"value": "none"},
            label=t("level_range.btn_no_watermark"),
        ),
    ]
    await cl.Message(
        content=t("level_range.ask"),
        author="Eira",
        actions=actions,
    ).send()


async def _show_hierarchy_confirmation_ui(
    hierarchy_flagged: list[dict],
    has_version_update: bool = False,
):
    """Show hierarchy classification results and let user confirm/change each file.

    Displays ALL uploaded files with their LLM-classified hierarchy level.
    User can confirm each one or click 'modify' to re-select.
    After ALL files are confirmed, proceeds to _ask_post_upload_setup().
    """
    from src.services.doc_hierarchy import get_doc_hierarchy

    hier_mgr = get_doc_hierarchy()
    lang = cl.user_session.get("language", "zh-TW")

    # Build pending confirmations: {filename: {level_id, confidence, reasoning, confirmed}}
    pending = {}
    for r in hierarchy_flagged:
        hres = r["hierarchy_result"]
        pending[r["filename"]] = {
            "level_id": hres["level_id"],
            "confidence": int(hres.get("confidence", 0) * 100),
            "reasoning": hres.get("reasoning", ""),
            "confirmed": False,
        }

    cl.user_session.set("hierarchy_pending", pending)
    cl.user_session.set("hierarchy_has_version_update", has_version_update)

    # Show the summary + per-file confirm/change buttons
    await _send_hierarchy_summary_message()


async def _send_hierarchy_summary_message():
    """Build and send the hierarchy summary with confirm/change actions per file."""
    from src.services.doc_hierarchy import get_doc_hierarchy

    hier_mgr = get_doc_hierarchy()
    lang = cl.user_session.get("language", "zh-TW")
    pending = cl.user_session.get("hierarchy_pending", {})
    if not pending:
        return

    lines = [t("hierarchy.confirm_title")]
    all_confirmed = True
    for fname, info in pending.items():
        level_label = hier_mgr.get_label(info["level_id"], lang)
        status_icon = "✅" if info["confirmed"] else "🔄"
        lines.append(
            f"- {status_icon} "
            + t(
                "hierarchy.confirm_line",
                filename=fname,
                level=level_label,
                confidence=info["confidence"],
                reasoning=info["reasoning"],
            )
        )
        if not info["confirmed"]:
            all_confirmed = False

    if all_confirmed:
        lines.append(f"\n{t('hierarchy.all_confirmed')}")
        await cl.Message(content="\n".join(lines), author="Eira").send()
        # All confirmed — proceed to post-upload setup
        has_vu = cl.user_session.get("hierarchy_has_version_update", False)
        if not has_vu:
            await _ask_post_upload_setup()
        return

    lines.append(f"\n{t('hierarchy.confirm_prompt')}")

    # Build action buttons — "Confirm All" first, then per-file confirm/change
    actions = [
        cl.Action(
            name="hierarchy_confirm_all",
            payload={"value": "confirm_all"},
            label=t("hierarchy.btn_confirm_all"),
        ),
    ]
    for fname, info in pending.items():
        if info["confirmed"]:
            continue
        actions.append(
            cl.Action(
                name="hierarchy_confirm",
                payload={"filename": fname, "level_id": info["level_id"]},
                label=f"{t('hierarchy.btn_confirm')} {fname[:20]}",
            )
        )
        actions.append(
            cl.Action(
                name="hierarchy_change",
                payload={"filename": fname},
                label=f"{t('hierarchy.btn_change')} {fname[:20]}",
            )
        )

    await cl.Message(content="\n".join(lines), author="Eira", actions=actions).send()


@cl.action_callback("hierarchy_confirm")
async def on_hierarchy_confirm(action):
    """User confirmed the LLM-classified hierarchy for a file."""
    await action.remove()
    fname = action.payload.get("filename", "")
    level_id = action.payload.get("level_id", "")

    pending = cl.user_session.get("hierarchy_pending", {})
    if fname in pending:
        pending[fname]["confirmed"] = True
        cl.user_session.set("hierarchy_pending", pending)

    from src.services.doc_hierarchy import get_doc_hierarchy

    hier_mgr = get_doc_hierarchy()
    lang = cl.user_session.get("language", "zh-TW")
    level_label = hier_mgr.get_label(level_id, lang)

    await cl.Message(
        content=t("hierarchy.confirmed", filename=fname, level=level_label),
        author="Eira",
    ).send()

    # Re-display summary for remaining unconfirmed files
    await _send_hierarchy_summary_message()


@cl.action_callback("hierarchy_change")
async def on_hierarchy_change(action):
    """User wants to change the hierarchy for a file — show level selection."""
    await action.remove()
    fname = action.payload.get("filename", "")

    from src.services.doc_hierarchy import get_doc_hierarchy

    hier_mgr = get_doc_hierarchy()
    lang = cl.user_session.get("language", "zh-TW")
    levels = hier_mgr.get_all_levels()

    actions = []
    for lv in levels:
        label = hier_mgr.get_label(lv["id"], lang)
        actions.append(
            cl.Action(
                name="hierarchy_select_level",
                payload={"filename": fname, "level_id": lv["id"]},
                label=label,
            )
        )

    await cl.Message(
        content=t("hierarchy.select_prompt", filename=fname),
        author="Eira",
        actions=actions,
    ).send()


@cl.action_callback("hierarchy_select_level")
async def on_hierarchy_select_level(action):
    """User selected a new hierarchy level for a file."""
    await action.remove()
    fname = action.payload.get("filename", "")
    new_level_id = action.payload.get("level_id", "")

    pending = cl.user_session.get("hierarchy_pending", {})
    if fname in pending:
        pending[fname]["level_id"] = new_level_id
        pending[fname]["confirmed"] = True
        pending[fname]["reasoning"] = "User-selected"
        pending[fname]["confidence"] = 100
        cl.user_session.set("hierarchy_pending", pending)

    from src.services.doc_hierarchy import get_doc_hierarchy

    hier_mgr = get_doc_hierarchy()
    lang = cl.user_session.get("language", "zh-TW")
    level_label = hier_mgr.get_label(new_level_id, lang)

    await cl.Message(
        content=t("hierarchy.changed", filename=fname, level=level_label),
        author="Eira",
    ).send()

    # Re-display summary for remaining unconfirmed files
    await _send_hierarchy_summary_message()


@cl.action_callback("hierarchy_confirm_all")
async def on_hierarchy_confirm_all(action):
    """User confirmed ALL LLM-classified hierarchies at once."""
    await action.remove()
    pending = cl.user_session.get("hierarchy_pending", {})
    for fname in pending:
        pending[fname]["confirmed"] = True
    cl.user_session.set("hierarchy_pending", pending)

    await cl.Message(content=t("hierarchy.confirm_all_done"), author="Eira").send()

    # All confirmed — proceed to post-upload setup
    has_vu = cl.user_session.get("hierarchy_has_version_update", False)
    if not has_vu:
        await _ask_post_upload_setup()


@cl.action_callback("obsolete_confirm_all")
async def on_obsolete_confirm_all(action):
    """User confirmed all suspected-obsolete files should continue processing."""
    await action.remove()
    await cl.Message(content=t("obsolete_detect.confirmed_all"), author="Eira").send()
    # Proceed to hierarchy classification step
    await _proceed_to_hierarchy_step()


async def _proceed_to_hierarchy_step():
    """Chain from obsolete detection to hierarchy classification step.

    Uses session-stored hierarchy data set during handle_file_upload().
    """
    hierarchy_flagged = cl.user_session.get("_pending_hierarchy_flagged", [])
    has_version_update = cl.user_session.get("_pending_has_version_update", False)

    if hierarchy_flagged:
        await _show_hierarchy_confirmation_ui(hierarchy_flagged, has_version_update)
    elif not has_version_update:
        # No hierarchy to confirm — go straight to post-upload setup
        await _ask_post_upload_setup()


async def _ask_post_upload_setup():
    """After all files uploaded — watermark and level range removed."""
    pass


@cl.action_callback("sig_detection_enable")
async def on_sig_detection_enable(action):
    """User chose to enable signature detection."""
    await action.remove()
    cl.user_session.set("signature_detection_enabled", True)
    cl.user_session.set("sig_detection_asked", True)
    await cl.Message(content=t("sig_toggle.enabled"), author="Eira").send()
    # If files were uploaded before sig detection was asked, process them now
    await _process_pending_upload_files()


@cl.action_callback("sig_detection_disable")
async def on_sig_detection_disable(action):
    """User chose to disable signature detection."""
    await action.remove()
    cl.user_session.set("signature_detection_enabled", False)
    cl.user_session.set("sig_detection_asked", True)
    await cl.Message(content=t("sig_toggle.disabled"), author="Eira").send()
    # If files were uploaded before sig detection was asked, process them now
    await _process_pending_upload_files()


@cl.action_callback("level_range_1_4")
async def on_level_range_1_4(action):
    await action.remove()


@cl.action_callback("level_range_1_3")
async def on_level_range_1_3(action):
    await action.remove()


@cl.action_callback("level_range_no_watermark")
async def on_level_range_no_watermark(action):
    await action.remove()


# ============================================================
# Watermark Action Callbacks & Flow
# ============================================================


async def _apply_watermark_to_existing_docs():
    pass


@cl.action_callback("watermark_provide")
async def on_watermark_provide(action):
    await action.remove()


@cl.action_callback("watermark_skip")
async def on_watermark_skip(action):
    await action.remove()


@cl.action_callback("watermark_confirm")
async def on_watermark_confirm(action):
    await action.remove()


@cl.action_callback("watermark_adjust_opacity")
async def on_watermark_adjust_opacity(action):
    await action.remove()


@cl.action_callback("watermark_adjust_angle")
async def on_watermark_adjust_angle(action):
    await action.remove()


@cl.action_callback("watermark_adjust_tiles")
async def on_watermark_adjust_tiles(action):
    await action.remove()


async def _send_watermark_preview():
    pass


async def _ask_watermark_before_upload():
    pass
    # ============================================================
    # Doc Control: File Upload Processing
    # ============================================================


def _format_process_detail(result: dict) -> str:
    """Format detailed processing information for a single file result."""
    lines = []

    # Conversion result details
    ocr = result.get("ocr_result", {})
    if ocr:
        provider = ocr.get("provider_used", "unknown")

        time_ms = ocr.get("processing_time_ms", 0)
        page_count = ocr.get("page_count", 0)
        file_type = ocr.get("file_type", "unknown")
        content_len = len(ocr.get("markdown_content", ""))

        time_str = f"{time_ms / 1000:.1f}s" if time_ms else "N/A"

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
        # Get signature detection setting from session
        sig_enabled = cl.user_session.get("signature_detection_enabled", True)
        result = await asyncio.to_thread(
            process_uploaded_file_sync,
            file_el,
            provider_id,
            api_key,
            model_name,
            lang,
            sig_enabled,
        )

        if result["success"]:
            succeeded.append(result)
        else:
            failed.append(result)

        # --- Show completed result for this file ---

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

    # --- Obsolete Detection UI ---
    # Show warnings for files flagged as potentially obsolete
    # Requirement: 只要檢測結果機率不為0都列出來讓使用者確認
    obsolete_flagged = [
        r
        for r in succeeded
        if r.get("obsolete_result", {}).get("is_suspected_obsolete")
    ]

    # --- Hierarchy Classification UI (interactive) ---
    # Show LLM-classified hierarchy for ALL uploaded files, let user confirm/change each one.
    # After ALL confirmations, proceed to post-upload setup (level range → watermark).
    hierarchy_flagged = [
        r
        for r in succeeded
        if r.get("hierarchy_result") and r["hierarchy_result"].get("level_id")
    ]
    has_version_update = succeeded and succeeded[-1].get("is_duplicate")

    # Store hierarchy data in session for the obsolete callback to chain into
    cl.user_session.set("_pending_hierarchy_flagged", hierarchy_flagged)
    cl.user_session.set("_pending_has_version_update", has_version_update)

    if obsolete_flagged:
        obs_lines = ["\n### ⚠️ 作廢文件偵測\n"]
        for r in obsolete_flagged:
            obs = r["obsolete_result"]
            conf_pct = int(obs["confidence"] * 100)
            reasons_str = "; ".join(obs.get("reasons", []))
            obs_lines.append(
                f"- **`{r['filename']}`** — {t('obsolete_detect.confidence')}: {conf_pct}%\n  {t('obsolete_detect.reason')}: {reasons_str}"
            )
        obs_lines.append(f"\n> {t('obsolete_detect.warning')}")
        actions = [
            cl.Action(
                name="obsolete_confirm_all",
                payload={"value": "confirm_all"},
                label=t("obsolete_detect.btn_confirm_all"),
            ),
        ]
        await cl.Message(content="\n".join(obs_lines), actions=actions).send()
    else:
        # No obsolete files — proceed directly to hierarchy
        await _proceed_to_hierarchy_step()

    # If there's a version update candidate, run diff analysis BEFORE confirm
    if succeeded and succeeded[-1].get("is_duplicate"):
        last = succeeded[-1]
        existing_ver = last.get("existing_version", "?")
        new_ver = last.get("new_version", "?")
        dup_doc_id = last["duplicate_doc"]["doc_id"]

        # --- LLM Version Diff Analysis (BEFORE confirm) ---
        try:
            storage_manager = get_markdown_store()
            old_doc = storage_manager.get_document(dup_doc_id, version=existing_ver)
            old_content = old_doc.get("content", "") if old_doc.get("success") else ""
            new_content = last.get("ocr_result", {}).get("markdown_content", "")

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
                    old_ver=existing_ver,
                    new_ver=new_ver,
                    old_content=old_truncated,
                    new_content=new_truncated,
                )

                def _run_version_diff():
                    with phoenix_trace(
                        profile="文件管制 (Doc Control)", command="version_diff"
                    ):
                        return manager.completion(
                            messages=[{"role": "user", "content": diff_prompt}],
                            model=model_name,
                            temperature=0.3,
                            max_tokens=2000,
                            stream=False,
                            timeout=60,
                        )

                diff_response = await asyncio.to_thread(_run_version_diff)

                diff_text = ""
                if isinstance(diff_response, dict):
                    diff_text = diff_response.get("content", "") or ""
                elif hasattr(diff_response, "choices") and diff_response.choices:
                    diff_text = diff_response.choices[0].message.content or ""

                if diff_text:
                    diff_msg.content = (
                        t(
                            "version.diff_header",
                            old_ver=existing_ver,
                            new_ver=new_ver,
                        )
                        + diff_text
                    )
                else:
                    diff_msg.content = (
                        t(
                            "version.diff_header",
                            old_ver=existing_ver,
                            new_ver=new_ver,
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

        # Show confirm/cancel buttons AFTER diff analysis
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
                doc_id=dup_doc_id,
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
    signature_detection_enabled: bool = True,
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

    # Signature detection BEFORE OCR — fail fast for unsigned documents.
    # detect_signature checks PDF structure, annotations, and embedded
    # images directly — no OCR text needed for scanned PDFs.
    # This avoids wasting 10-30 min on OCR for a document that will be
    # rejected anyway due to missing signature/stamp.
    sig_result = None
    if signature_detection_enabled:
        empty_ocr_for_sig = {
            "markdown_content": "",
            "text_content": "",
            "detected_elements": {
                "stamps": [],
                "signatures": [],
                "tables": [],
                "headers": [],
                "metadata": {},
            },
        }
        sig_result = detect_signature(
            empty_ocr_for_sig, file_path=str(dest_path), lang=lang
        )

        if not sig_result["detected"]:
            try:
                dest_path.unlink()
            except Exception:
                pass
            return {
                "success": False,
                "filename": filename,
                "error": _t("upload.no_sig_error", reason=sig_result["reason"]),
                "sig_result": sig_result,
            }
    else:
        # Signature detection disabled — create a dummy result
        sig_result = {
            "detected": False,
            "reason": "Signature detection disabled",
            "stamps": [],
            "signatures": [],
        }

    setup_api_key(provider_id, api_key)

    try:
        llm_manager = create_provider_manager(provider_id)
        if provider_id != "ollama":
            llm_manager.disable_fallback = True
    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "error": _t("upload.llm_init_error", error=str(e)),
        }

    with phoenix_trace(profile="文件管制 (Doc Control)", command="ocr_upload"):
        ocr_result = process_document(
            str(dest_path), llm_manager, model_name=model_name
        )
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

    # --- Obsolete Document Detection ---
    # Requirement: 只要檢測結果機率不為0都列出來讓使用者確認
    from src.services.obsolete_detector import detect_obsolete

    obsolete_result = detect_obsolete(
        filename=filename,
        title=doc_info.get("title", ""),
        ocr_content=ocr_text_for_detection,
        file_path=str(dest_path),
        lang=lang,
    )

    # --- LLM Hierarchy Classification ---
    # Uses LLM to classify document into L1-L4/REG/OTHER
    hierarchy_result = None
    try:
        from src.services.doc_hierarchy import classify_document_hierarchy_llm

        with phoenix_trace(
            profile="文件管制 (Doc Control)", command="hierarchy_classify"
        ):
            hierarchy_result = classify_document_hierarchy_llm(
                content=ocr_text_for_detection,
                filename=filename,
                llm_completion_fn=llm_manager.completion,
                model=model_name,
                lang=lang,
            )
    except Exception:
        hierarchy_result = {
            "level_id": "OTHER",
            "confidence": 0.0,
            "reasoning": "Classification failed",
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
            "obsolete_result": obsolete_result,
            "hierarchy_result": hierarchy_result,
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
                        "obsolete_result": obsolete_result,
                        "hierarchy_result": hierarchy_result,
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
        sig_result=sig_result,
    )

    if save_result.get("success"):
        return {
            "success": True,
            "filename": filename,
            "dest_path": str(dest_path),
            "ocr_result": ocr_result,
            "doc_info": doc_info,
            "sig_result": sig_result,
            "obsolete_result": obsolete_result,
            "hierarchy_result": hierarchy_result,
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
            new_title=doc_info.get("title"),
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
            ref_elements = []
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
                    # Auto-generate Word/Excel reference reports and attach inline
                    try:
                        word_path = export_reference_to_word(current_doc_id, ref_docs)
                        if word_path:
                            wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                            ref_elements.append(
                                cl.File(name=wname, path=word_path, display="inline")
                            )
                    except Exception:
                        pass
                    try:
                        excel_path = export_reference_to_excel(current_doc_id, ref_docs)
                        if excel_path:
                            ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                            ref_elements.append(
                                cl.File(name=ename, path=excel_path, display="inline")
                            )
                    except Exception:
                        pass
            except Exception:
                pass

            if ref_elements:
                await cl.Message(content=msg, elements=ref_elements).send()
            else:
                await cl.Message(content=msg).send()

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
        with phoenix_trace(profile=profile, command="chat"):
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


# ── Full-page content fetcher for /web search enhancement ──
_WEB_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
}
_WEB_FETCH_JINA_BASE = "https://r.jina.ai/"
_WEB_FETCH_MAX_CONTENT = 8_000  # per-page char limit
_WEB_FETCH_TOTAL_MAX = 30_000  # total char limit across all pages
_WEB_FETCH_SKIP_EXTS = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".gz",
    ".tar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".mp4",
    ".mp3",
    ".wav",
    ".avi",
)


def _simple_html_to_text(html: str, url: str = "") -> str:
    """Lightweight HTML → text extraction using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup as _BS

        soup = _BS(html, "html.parser")
        # Remove non-content tags
        for tag in soup.find_all(
            ["script", "style", "nav", "footer", "header", "aside", "noscript"]
        ):
            tag.decompose()
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"role": "main"})
            or soup.find("div", {"id": re.compile(r"content|main", re.I)})
            or soup.find("div", {"class": re.compile(r"content|main", re.I)})
        )
        target = main if main else (soup.body if soup.body else soup)
        lines: list[str] = []
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            lines.append(f"# {title_tag.string.strip()}")
            lines.append("")
        for el in target.find_all(
            ["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote"]
        ):
            text = el.get_text(strip=True)
            if not text:
                continue
            tag_name = el.name
            if tag_name == "h1":
                lines.append(f"# {text}")
            elif tag_name == "h2":
                lines.append(f"## {text}")
            elif tag_name == "h3":
                lines.append(f"### {text}")
            elif tag_name == "h4":
                lines.append(f"#### {text}")
            elif tag_name == "li":
                lines.append(f"- {text}")
            elif tag_name == "pre":
                lines.append(f"```\n{text}\n```")
            elif tag_name == "blockquote":
                lines.append(f"> {text}")
            else:
                lines.append(text)
            lines.append("")
        return "\n".join(lines).strip()
    except Exception:
        return ""


async def _fetch_single_url(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """Fetch a single URL: httpx first, Jina Reader fallback.

    Returns (url, markdown_content). Content is empty string on failure.
    """
    import httpx as _httpx
    from urllib.parse import urlparse

    # Skip non-HTML resources
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _WEB_FETCH_SKIP_EXTS):
        return (url, "")

    _timeout = _httpx.Timeout(timeout, connect=8.0)

    # --- Attempt 1: Direct httpx fetch ---
    try:
        async with _httpx.AsyncClient(
            headers=_WEB_FETCH_HEADERS,
            timeout=_timeout,
            follow_redirects=True,
            verify=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type or "application/xhtml" in content_type:
                    md = _simple_html_to_text(resp.text, url)
                    if md and len(md.strip()) > 200:
                        return (url, md[:_WEB_FETCH_MAX_CONTENT])
    except Exception:
        pass

    # --- Attempt 2: Jina Reader fallback ---
    try:
        jina_url = f"{_WEB_FETCH_JINA_BASE}{url}"
        async with _httpx.AsyncClient(
            timeout=_httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(jina_url, headers={"Accept": "text/markdown"})
            if resp.status_code == 200:
                content = resp.text.strip()
                if content and len(content) > 100:
                    return (url, content[:_WEB_FETCH_MAX_CONTENT])
    except Exception:
        pass

    return (url, "")


async def _fetch_web_full_content(
    urls: list, max_urls: int = 3, timeout: float = 15.0
) -> dict:
    """Fetch full page content from top web search result URLs in parallel.

    Uses httpx first, falls back to Jina Reader for JS-heavy / blocked sites.
    Returns dict mapping URL → markdown content (successful fetches only).
    """
    selected = urls[:max_urls]
    if not selected:
        return {}

    tasks = [
        asyncio.wait_for(_fetch_single_url(u, timeout), timeout=timeout + 5)
        for u in selected
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results: dict[str, str] = {}
    total_chars = 0
    for item in raw:
        if isinstance(item, Exception):
            continue
        url, content = item
        if not content:
            continue
        # Enforce total char budget
        remaining = _WEB_FETCH_TOTAL_MAX - total_chars
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n\n... (truncated)"
        results[url] = content
        total_chars += len(content)

    return results


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

        def _traced_web_search():
            with phoenix_span(
                "duckduckgo_web_search",
                profile=profile,
                attributes={"search.query": message_text},
            ) as span:
                results = _web_search_sync(message_text)
                if span is not None:
                    tier_counts = {}
                    for r in results:
                        t_val = r.get("_tier", 4)
                        tier_counts[f"tier_{t_val}"] = (
                            tier_counts.get(f"tier_{t_val}", 0) + 1
                        )
                    span.set_attribute("search.engine", "DuckDuckGo")
                    span.set_attribute("search.result_count", len(results))
                    span.set_attribute("search.tier_distribution", str(tier_counts))
                    # Record URLs fed to LLM
                    urls = [r.get("href", r.get("link", "")) for r in results[:20]]
                    span.set_attribute("search.urls_for_llm", str(urls))
                return results

        web_results = await asyncio.to_thread(_traced_web_search)
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

            # --- Step 1b: Fetch full page content from top URLs ---
            full_content_context = ""
            try:
                # Pick top URLs by credibility tier (lower = better)
                _seen_fetch: set = set()
                fetch_urls: list = []
                for r in web_results:
                    u = r.get("href", r.get("link", ""))
                    if u and u not in _seen_fetch:
                        _seen_fetch.add(u)
                        fetch_urls.append(u)
                    if len(fetch_urls) >= 5:
                        break

                if fetch_urls:
                    search_msg.content += f"\n\n{t('web.fetching_content')}"
                    await search_msg.update()

                    with phoenix_span(
                        "web_full_content_fetch",
                        profile=profile,
                        attributes={"fetch.url_count": len(fetch_urls)},
                    ) as fc_span:
                        full_content_results = await _fetch_web_full_content(
                            fetch_urls, max_urls=3, timeout=15.0
                        )
                        if fc_span is not None:
                            fc_span.set_attribute(
                                "fetch.success_count", len(full_content_results)
                            )
                            fc_span.set_attribute(
                                "fetch.urls", str(list(full_content_results.keys()))
                            )

                    if full_content_results:
                        fc_parts = [
                            "\n\n--- 以下為搜尋結果的完整頁面內容 (Full Page Content) ---\n"
                        ]
                        for fc_url, fc_content in full_content_results.items():
                            # Find title from search results
                            fc_title = next(
                                (
                                    r.get("title", "")
                                    for r in web_results
                                    if r.get("href", r.get("link", "")) == fc_url
                                ),
                                fc_url,
                            )
                            fc_parts.append(
                                f"### {fc_title}\nSource: {fc_url}\n\n{fc_content}\n"
                            )
                        full_content_context = "\n".join(fc_parts)
                        web_context += full_content_context

                        # Update UI with fetch count
                        search_msg.content = (
                            f"🌐 {t('web.source_label')}: {len(web_sources)} results\n"
                            + "\n".join(web_sources)
                            + f"\n\n{t('web.fetched_content_count', count=len(full_content_results))}"
                        )
                        await search_msg.update()
            except Exception as e_fc:
                print(f"[WARN] Full content fetch failed: {e_fc}")
                # Non-fatal: continue with snippets only
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
        with phoenix_trace(profile=profile, command="web_search"):
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


@cl.action_callback("submit_daily_feedback")
async def on_submit_daily_feedback(action):
    """Prompt user to type feedback for a daily audit result."""
    payload = action.payload or {}
    audit_date = payload.get("audit_date", "")
    cl.user_session.set("pending_feedback_audit_date", audit_date)
    cl.user_session.set("awaiting_daily_feedback", True)
    await cl.Message(
        content=f"請輸入您對 {audit_date} 每日稽核的回饋意見（輸入後按 Enter 送出）：",
        author="Eira",
    ).send()
    await action.remove()


async def _save_daily_feedback_if_pending(user_message: str) -> bool:
    """If user is in feedback-input mode, save feedback and return True."""
    if not cl.user_session.get("awaiting_daily_feedback"):
        return False

    audit_date = cl.user_session.get("pending_feedback_audit_date", "")

    try:
        from src.analysis.daily_audit import AuditFeedback, save_feedback

        fb = AuditFeedback(
            audit_type="daily",
            target_id=audit_date,
            feedback_text=user_message.strip(),
            status="active",
        )
        save_feedback(fb)
        await cl.Message(
            content=f"✅ 回饋已儲存（稽核日期：{audit_date}）。感謝您的意見！",
            author="Eira",
        ).send()
    except Exception as _fb_err:
        logging.getLogger(__name__).warning("Save daily feedback failed: %s", _fb_err)
        await cl.Message(
            content="⚠️ 回饋儲存失敗，請稍後再試。",
            author="Eira",
        ).send()
    finally:
        cl.user_session.set("awaiting_daily_feedback", False)
        cl.user_session.set("pending_feedback_audit_date", "")

    return True


@cl.on_message
async def on_message(message: cl.Message):
    """Handle all incoming messages"""
    profile = cl.user_session.get("chat_profile")
    text = message.content.strip() if message.content else ""

    # Handle pending daily feedback input
    if await _save_daily_feedback_if_pending(text):
        return

    # Check for file uploads (Doc Control profile)
    if message.elements and profile == "文件管制 (Doc Control)":
        file_elements = [el for el in message.elements if hasattr(el, "path")]
        if file_elements:
            # Only block upload if sig detection hasn't been asked yet
            if not cl.user_session.get("sig_detection_asked"):
                # Store pending files and ask sig detection first
                cl.user_session.set(
                    "pending_upload_files", [(el.name, el.path) for el in file_elements]
                )
                user_name = cl.user_session.get("user_name", "")
                await _ask_sig_detection_toggle(user_name or "使用者")
                return

            # Level range and watermark are asked AFTER upload completes
            # Just proceed with upload directly
            await handle_file_upload(file_elements)
            return

    # Empty message
    if not text:
        return

    # ============================================================
    # Intercept: awaiting user name (Eira greeting flow)
    # ============================================================
    if cl.user_session.get("awaiting_user_name"):
        cl.user_session.set("awaiting_user_name", False)
        user_name = text.strip()
        if not user_name:
            cl.user_session.set("awaiting_user_name", True)
            await cl.Message(content=t("eira.name_empty"), author="Eira").send()
            return

        cl.user_session.set("user_name", user_name)

        # Save current LLM settings + user name
        save_user_settings(
            user_name=user_name,
            provider_id=cl.user_session.get("provider_id", ""),
            provider_name=cl.user_session.get("provider_name", ""),
            model_name=cl.user_session.get("model_name", ""),
            api_key=cl.user_session.get("real_api_key", "")
            or cl.user_session.get("api_key", ""),
            language=cl.user_session.get("language", "zh-TW"),
        )

        profile = cl.user_session.get("chat_profile")
        doc_count, doc_limit = get_document_count()
        await _send_eira_introduction(user_name, profile, doc_count, doc_limit)
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
    # Intercept: awaiting regulatory document deletion
    # ============================================================
    if cl.user_session.get("awaiting_regulatory_delete"):
        cl.user_session.set("awaiting_regulatory_delete", False)
        await _execute_regulatory_delete(text.strip())
        return

    # ============================================================
    # Intercept: awaiting downloader name before file download
    # ============================================================
    if cl.user_session.get("awaiting_download_name"):
        cl.user_session.set("awaiting_download_name", False)
        downloader_name = text.strip()
        if not downloader_name:
            cl.user_session.set("awaiting_download_name", True)
            await cl.Message(content="⚠️ 姓名不可空白，請再輸入一次您的姓名：").send()
            return

        # Action-button triggered download
        pending_doc_id = cl.user_session.get("pending_download_doc_id", "")
        if pending_doc_id:
            cl.user_session.set("pending_download_doc_id", "")
            storage = get_markdown_store()
            file_path = storage.get_original_file_path(pending_doc_id)
            if not file_path:
                await cl.Message(content=t("download.file_error", doc_id=pending_doc_id)).send()
                return
            fname = re.sub(r"^\d{14}_", "", Path(file_path).name)
            audit_log = ImmutableAuditLog()
            audit_log.create_record(
                action="DOC_DOWNLOADED",
                document_id=pending_doc_id,
                user_id=downloader_name,
                details={"filename": fname, "triggered_by": "action_button"},
            )
            await _send_file_download(
                file_path,
                t("view.download_title", doc_id=pending_doc_id) + "\n" + t("view.download_hint"),
            )
            return

        # Command-triggered download
        pending_text = cl.user_session.get("pending_download_text", "")
        if pending_text:
            cl.user_session.set("pending_download_text", "")
            filepath, msg_text = await handle_download(pending_text)
            if filepath:
                fname = re.sub(r"^\d{14}_", "", Path(filepath).name)
                doc_id_match = re.search(
                    r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)", pending_text, re.IGNORECASE
                )
                doc_id = doc_id_match.group(1).upper() if doc_id_match else ""
                audit_log = ImmutableAuditLog()
                audit_log.create_record(
                    action="DOC_DOWNLOADED",
                    document_id=doc_id or fname,
                    user_id=downloader_name,
                    details={"filename": fname, "triggered_by": "command"},
                )
                actions = [
                    cl.Action(
                        name="download_original_file",
                        payload={"doc_id": doc_id},
                        label=f"📥 {fname}",
                    ),
                ]
                elements = [cl.File(name=fname, path=filepath, display="inline")]
                download_msg = (
                    t("view.download_title", doc_id=doc_id)
                    + "\n"
                    + t("view.download_hint")
                )
                await cl.Message(
                    content=download_msg, elements=elements, actions=actions
                ).send()
            else:
                await cl.Message(content=msg_text).send()
        return

    # ============================================================
    # Intercept: awaiting region selection for regulatory update
    # ============================================================
    if cl.user_session.get("awaiting_region_selection"):
        cl.user_session.set("awaiting_region_selection", False)
        user_input = text.strip()
        input_lower = user_input.lower()

        # Check if user wants to delete specific regulatory docs instead
        delete_triggers = ["刪除", "移除", "刪掉", "去掉", "delete", "remove", "del "]
        if any(input_lower.startswith(dt) for dt in delete_triggers):
            await _execute_regulatory_delete(user_input)
            return

        available_regions = cl.user_session.get(
            "regulatory_available_regions", get_available_regions()
        )
        success_regions = cl.user_session.get(
            "regulatory_success_regions", available_regions
        )

        selected = _parse_region_selection(
            user_input, available_regions, success_regions
        )

        if not selected:
            # If parsing failed, default to all success regions
            selected = success_regions if success_regions else available_regions
            await cl.Message(
                content="ℹ️ 無法解析輸入，將使用預設選擇（所有可爬取地區）。"
            ).send()

        region_names = ", ".join(selected)
        await cl.Message(
            content=f"✅ 已選擇 {len(selected)} 個地區: {region_names}"
        ).send()
        await handle_regulatory_update_rescan(selected)
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
            elements = []
            try:
                word_path, _ = await handle_doclist_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_doclist_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 文件清單 Word/Excel 報告",
                elements=elements,
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
            elements = []
            try:
                word_path, _ = await handle_allrecords_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_allrecords_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 全部文件紀錄 Word/Excel 報告",
                elements=elements,
            ).send()
        return

    # Document list — current formal versions only (must check before generic list)
    if _match_cmd(text, "cmd.document_list"):
        response = await handle_document_list()
        # Pre-generate Word + Excel for direct download
        elements = []
        try:
            word_path, _ = await handle_doclist_export("word")
            if word_path:
                wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                elements.append(cl.File(name=wname, path=word_path, display="inline"))
        except Exception:
            pass
        try:
            excel_path, _ = await handle_doclist_export("excel")
            if excel_path:
                ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                elements.append(cl.File(name=ename, path=excel_path, display="inline"))
        except Exception:
            pass
        await cl.Message(content=response, elements=elements).send()
        return

    # List — all records (active + obsolete + version history)
    if _match_cmd(text, "cmd.list") or _match_cmd_exact(text, "cmd.list"):
        response = await handle_list()
        # Pre-generate Word + Excel for direct download
        elements = []
        try:
            word_path, _ = await handle_allrecords_export("word")
            if word_path:
                wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                elements.append(cl.File(name=wname, path=word_path, display="inline"))
        except Exception:
            pass
        try:
            excel_path, _ = await handle_allrecords_export("excel")
            if excel_path:
                ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                elements.append(cl.File(name=ename, path=excel_path, display="inline"))
        except Exception:
            pass
        await cl.Message(content=response, elements=elements).send()
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
    # Export / Download with Inline File Attachments
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
            elements = []
            try:
                word_path, _ = await handle_audit_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_audit_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 文件更動紀錄 Word/Excel 報告",
                elements=elements,
            ).send()
        return

    # --- Regulatory UPDATE export (must check before download_regulatory) ---
    if _match_cmd(text, "cmd.download_regulatory_update"):
        if has_word_suffix:
            filepath, msg_text = await handle_regulatory_update_export("word")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        elif has_excel_suffix:
            filepath, msg_text = await handle_regulatory_update_export("excel")
            if filepath:
                await _send_file_download(filepath, msg_text)
            else:
                await cl.Message(content=msg_text).send()
        else:
            elements = []
            try:
                word_path, _ = await handle_regulatory_update_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_regulatory_update_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 法規更新報告 Word/Excel",
                elements=elements,
            ).send()
        return

    # --- Regulatory UPDATE display (must check before cmd.regulatory) ---
    if _match_cmd(text, "cmd.regulatory_update"):
        await handle_regulatory_update()
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
            elements = []
            try:
                word_path, _ = await handle_regulatory_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_regulatory_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 法規清單 Word/Excel 報告",
                elements=elements,
            ).send()
        return

    # Regulatory standards list (display only)
    if _match_cmd(text, "cmd.regulatory"):
        response = await handle_regulatory_list()
        # Pre-generate Word + Excel for direct download
        elements = []
        try:
            word_path, _ = await handle_regulatory_export("word")
            if word_path:
                wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                elements.append(cl.File(name=wname, path=word_path, display="inline"))
        except Exception:
            pass
        try:
            excel_path, _ = await handle_regulatory_export("excel")
            if excel_path:
                ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                elements.append(cl.File(name=ename, path=excel_path, display="inline"))
        except Exception:
            pass
        await cl.Message(content=response, elements=elements).send()
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
            elements = []
            try:
                word_path, _ = await handle_reference_export("word")
                if word_path:
                    wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                    elements.append(
                        cl.File(name=wname, path=word_path, display="inline")
                    )
            except Exception:
                pass
            try:
                excel_path, _ = await handle_reference_export("excel")
                if excel_path:
                    ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                    elements.append(
                        cl.File(name=ename, path=excel_path, display="inline")
                    )
            except Exception:
                pass
            await cl.Message(
                content="📋 引用清單 Word/Excel 報告",
                elements=elements,
            ).send()
        return

    # Audit records (display only)
    if _match_cmd(text, "cmd.audit"):
        response = await handle_audit()
        # Pre-generate Word + Excel for direct download
        elements = []
        try:
            word_path, _ = await handle_audit_export("word")
            if word_path:
                wname = re.sub(r"^\d{14}_", "", Path(word_path).name)
                elements.append(cl.File(name=wname, path=word_path, display="inline"))
        except Exception:
            pass
        try:
            excel_path, _ = await handle_audit_export("excel")
            if excel_path:
                ename = re.sub(r"^\d{14}_", "", Path(excel_path).name)
                elements.append(cl.File(name=ename, path=excel_path, display="inline"))
        except Exception:
            pass
        await cl.Message(content=response, elements=elements).send()
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
            and not _match_cmd(text, "cmd.download_regulatory_update")
            and not _match_cmd(text, "cmd.download_reference")
            and not _match_cmd(text, "cmd.download_doclist")
            and not _match_cmd(text, "cmd.download_allrecords")
            and not _match_cmd(text, "cmd.audit")
            and not _match_cmd(text, "cmd.regulatory")
            and not _match_cmd(text, "cmd.regulatory_update")
        ):
            # Check if file exists before asking for name
            _check_path, _check_msg = await handle_download(text)
            if not _check_path:
                await cl.Message(content=_check_msg).send()
                return
            # File found — ask for downloader's name before proceeding
            cl.user_session.set("pending_download_text", text)
            cl.user_session.set("awaiting_download_name", True)
            await cl.Message(content="請問您的姓名？（將記錄於稽核紀錄）").send()
            return

        # Online view document by doc_id (線上觀看)
        if _match_cmd(text, "cmd.view_file"):
            doc_id_match = re.search(
                r"([A-Z]{2,4}-\d{2,4}(?:-\d{1,2})?)", text, re.IGNORECASE
            )
            if doc_id_match:
                doc_id = doc_id_match.group(1).upper()
                storage = get_markdown_store()
                file_path = storage.get_original_file_path(doc_id)
                if file_path:
                    doc_data = storage.get_document(doc_id)
                    _doc_type = "OTHER"
                    _title = ""
                    _content = ""
                    if doc_data and doc_data.get("success"):
                        _meta = doc_data.get("metadata", {})
                        _doc_type = _meta.get("doc_type", "OTHER")
                        _title = _meta.get("title", "")
                        _content = doc_data.get("content", "")[:3000]
                    level = get_document_level(doc_id, _doc_type, _title, _content)
                    await _send_inline_view(file_path, doc_id, level)
                else:
                    await cl.Message(
                        content=t("download.not_found", doc_id=doc_id)
                    ).send()
            else:
                storage = get_markdown_store()
                docs = storage.list_documents_with_files()
                available = [d for d in docs if d["has_original_file"]]
                msg = (
                    t("view.specify", count=len(available))
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
                msg += "\n\n" + t("view.example")
                await cl.Message(content=msg).send()
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
