"""
AI-QMS Phase 1 Document Control - LLM Provider Abstraction Layer

Comprehensive LLM provider support via LiteLLM, inspired by OpenCode's provider system.

=== Direct API Providers ===
- OpenAI (GPT-4.1, GPT-4o, GPT-5, o1, o3, o4-mini)
- Anthropic (Claude 4 Opus, Claude 4 Sonnet, Claude 3.5/3.7 Sonnet)
- Google (Gemini 3 Pro, Gemini 2.5 Pro/Flash)
- DeepSeek (DeepSeek-V3.2, DeepSeek-R1)
- xAI (Grok 4, Grok 3)
- Mistral (Mistral Large 3, Codestral, Ministral)
- Cohere (Command A, Command R+)
- Perplexity (Sonar Pro, Sonar Reasoning)

=== LLM Gateway/Router Platforms ===
- OpenRouter (200+ models via single API)
- Requesty (unified LLM gateway with caching)
- Together AI (200+ open source models)
- Groq (ultra-fast LPU inference)
- Fireworks AI (optimized inference)
- Deep Infra (cost-effective inference)

=== Local Providers ===
- Ollama (100+ local models)
- LM Studio (local LLM with OpenAI-compatible API)

Version: 2.7.0
Updated: 2026-02-11
Reference: OpenCode /connect providers (https://opencode.ai/docs/providers)
"""

import copy
import os
import base64
from typing import TypedDict, Optional, Any
from pathlib import Path

try:
    import litellm
    from litellm import completion  # noqa: F401 — kept for backward compat

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    print("[WARN] litellm not installed. Run: pip install litellm")


# ============================================================
# Type Definitions
# ============================================================


class LLMProviderConfig(TypedDict):
    """LLM Provider configuration structure"""

    provider_id: str
    display_name: str
    display_name_zh: str  # Chinese display name
    category: str  # "direct_api", "gateway", "local"
    api_base_url: str
    api_key: Optional[str]
    default_model: str
    available_models: list[str]
    supports_vision: bool
    supports_streaming: bool
    max_tokens: int
    temperature: float
    is_local: bool
    env_key_name: str  # Environment variable name for API key


# ============================================================
# Default Provider Configurations
# ============================================================

DEFAULT_PROVIDERS: dict[str, LLMProviderConfig] = {
    # ============================================================
    # Direct API Providers
    # ============================================================
    "openai": {
        "provider_id": "openai",
        "display_name": "OpenAI",
        "display_name_zh": "OpenAI",
        "category": "direct_api",
        "api_base_url": "https://api.openai.com/v1",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "default_model": "gpt-4.1",
        "available_models": [
            # GPT-4.1 Series (Latest - April 2025)
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            # GPT-4o Series
            "gpt-4o",
            "gpt-4o-mini",
            # GPT-4.5 (Preview)
            "gpt-4.5-preview",
            # GPT-4 Turbo
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            # o-Series (Reasoning Models)
            "o1",
            "o1-pro",
            "o1-mini",
            "o1-preview",
            "o3",
            "o3-mini",
            "o4-mini",
            # GPT-3.5
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "OPENAI_API_KEY",
    },
    "anthropic": {
        "provider_id": "anthropic",
        "display_name": "Anthropic",
        "display_name_zh": "Anthropic",
        "category": "direct_api",
        "api_base_url": "https://api.anthropic.com",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "default_model": "claude-sonnet-4-6",
        "available_models": [
            # Claude 4.6 Series (Latest)
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            # Claude 4 Series
            "claude-opus-4-20251124",
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20251015",
            # Claude 4.5 Series
            "claude-opus-4.5-20251124",
            "claude-sonnet-4.5-20250929",
            "claude-haiku-4.5-20251015",
            # Claude 3.7 Series
            "claude-3-7-sonnet-20250219",
            "claude-3-7-sonnet-extended-thinking",
            # Claude 3.5 Series
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            # Claude 3 Series (Legacy)
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "ANTHROPIC_API_KEY",
    },
    "google": {
        "provider_id": "google",
        "display_name": "Google Gemini",
        "display_name_zh": "Google Gemini",
        "category": "direct_api",
        "api_base_url": "https://generativelanguage.googleapis.com",
        "api_key": os.getenv("GOOGLE_API_KEY"),
        "default_model": "gemini-2.5-pro",
        "available_models": [
            # Gemini 3 Series (Latest - 2025)
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-3-pro-image-preview",
            # Gemini 2.5 Series
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-image",
            # Gemini 2.0 Series
            "gemini-2.0-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash-thinking-exp",
            # Gemini 1.5 Series
            "gemini-1.5-pro",
            "gemini-1.5-pro-002",
            "gemini-1.5-flash",
            "gemini-1.5-flash-002",
            "gemini-1.5-flash-8b",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 65536,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "GOOGLE_API_KEY",
    },
    "deepseek": {
        "provider_id": "deepseek",
        "display_name": "DeepSeek",
        "display_name_zh": "DeepSeek 深度求索",
        "category": "direct_api",
        "api_base_url": "https://api.deepseek.com",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "default_model": "deepseek-chat",
        "available_models": [
            # DeepSeek-V3.2 (Latest - Dec 2025)
            "deepseek-chat",  # DeepSeek-V3.2 Non-thinking Mode
            "deepseek-reasoner",  # DeepSeek-V3.2 Thinking Mode (R1)
            # Legacy models
            "deepseek-coder",
        ],
        "supports_vision": False,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "DEEPSEEK_API_KEY",
    },
    "xai": {
        "provider_id": "xai",
        "display_name": "xAI (Grok)",
        "display_name_zh": "xAI (Grok)",
        "category": "direct_api",
        "api_base_url": "https://api.x.ai/v1",
        "api_key": os.getenv("XAI_API_KEY"),
        "default_model": "grok-4-0709",
        "available_models": [
            # Grok 4 Series (Latest - July 2025)
            "grok-4-0709",
            "grok-4.1",
            "grok-4.1-thinking",
            "grok-4.1-fast",
            # Grok 3 Series
            "grok-3",
            "grok-3-mini",
            # Grok 2 Series
            "grok-2",
            "grok-2-image-1212",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "XAI_API_KEY",
    },
    "mistral": {
        "provider_id": "mistral",
        "display_name": "Mistral AI",
        "display_name_zh": "Mistral AI",
        "category": "direct_api",
        "api_base_url": "https://api.mistral.ai/v1",
        "api_key": os.getenv("MISTRAL_API_KEY"),
        "default_model": "mistral-large-latest",
        "available_models": [
            # Frontier Models
            "mistral-large-latest",  # Mistral Large 3
            "mistral-medium-latest",  # Mistral Medium 3.1
            "mistral-small-latest",  # Mistral Small 3.2
            # Specialist Models
            "codestral-latest",  # Codestral 25.01
            "devstral-latest",  # Devstral 2
            "magistral-latest",  # Magistral 1.2
            # Edge Models
            "ministral-3b-latest",
            "ministral-8b-latest",
            "ministral-14b-latest",
            # Other Models
            "mistral-nemo-latest",
            "pixtral-12b-latest",
            "mistral-ocr-latest",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "MISTRAL_API_KEY",
    },
    "cohere": {
        "provider_id": "cohere",
        "display_name": "Cohere",
        "display_name_zh": "Cohere",
        "category": "direct_api",
        "api_base_url": "https://api.cohere.ai/v1",
        "api_key": os.getenv("COHERE_API_KEY"),
        "default_model": "command-a-03-2025",
        "available_models": [
            # Command A (Latest)
            "command-a-03-2025",
            # Command R+ Series
            "command-r-plus-08-2024",
            "command-r-plus",
            # Command R Series
            "command-r-08-2024",
            "command-r",
            # Embed Models
            "embed-english-v3.0",
            "embed-multilingual-v3.0",
            # Rerank Models
            "rerank-english-v3.0",
            "rerank-multilingual-v3.0",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "COHERE_API_KEY",
    },
    "perplexity": {
        "provider_id": "perplexity",
        "display_name": "Perplexity",
        "display_name_zh": "Perplexity 搜尋AI",
        "category": "direct_api",
        "api_base_url": "https://api.perplexity.ai",
        "api_key": os.getenv("PERPLEXITY_API_KEY"),
        "default_model": "sonar-pro",
        "available_models": [
            # Sonar Search Models
            "sonar",
            "sonar-pro",
            # Sonar Reasoning Models
            "sonar-reasoning-pro",
            # Sonar Research Models
            "sonar-deep-research",
        ],
        "supports_vision": False,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "PERPLEXITY_API_KEY",
    },
    # ============================================================
    # LLM Gateway/Router Platforms
    # ============================================================
    "openrouter": {
        "provider_id": "openrouter",
        "display_name": "OpenRouter",
        "display_name_zh": "OpenRouter 路由平台",
        "category": "gateway",
        "api_base_url": "https://openrouter.ai/api/v1",
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "default_model": "google/gemini-3-pro-preview",
        "available_models": [
            # Google via OpenRouter (Gemini 3 - Latest)
            "google/gemini-3-pro-preview",
            "google/gemini-3-flash-preview",
            "google/gemini-2.5-pro",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
            "google/gemini-2.0-flash",
            "google/gemini-2.0-flash-lite-001",
            # Anthropic via OpenRouter
            "anthropic/claude-opus-4",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.7-sonnet",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.5-haiku",
            # OpenAI via OpenRouter
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/o1",
            "openai/o3-mini",
            "openai/o4-mini",
            # Meta Llama via OpenRouter
            "meta-llama/llama-4-maverick",
            "meta-llama/llama-4-scout",
            "meta-llama/llama-3.3-70b-instruct",
            "meta-llama/llama-3.1-405b-instruct",
            # Mistral via OpenRouter
            "mistralai/mistral-large-3",
            "mistralai/mistral-medium-3.1",
            "mistralai/codestral-latest",
            # DeepSeek via OpenRouter
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
            # Qwen via OpenRouter
            "qwen/qwen3-235b-a22b",
            "qwen/qwen-2.5-72b-instruct",
            "qwen/qwen-2.5-coder-32b-instruct",
            # xAI via OpenRouter
            "xai/grok-4",
            "xai/grok-3",
            # Cohere via OpenRouter
            "cohere/command-a",
            "cohere/command-r-plus",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "OPENROUTER_API_KEY",
    },
    "requesty": {
        "provider_id": "requesty",
        "display_name": "Requesty",
        "display_name_zh": "Requesty 統一網關",
        "category": "gateway",
        "api_base_url": os.getenv("REQUESTY_BASE_URL", "https://router.requesty.ai/v1"),
        "api_key": os.getenv("REQUESTY_API_KEY"),
        "default_model": "anthropic/claude-3.5-sonnet",
        "available_models": [
            # Anthropic via Requesty
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-haiku",
            # OpenAI via Requesty
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            # Google via Requesty
            "google/gemini-1.5-pro",
            "google/gemini-1.5-flash",
            # Other models via Requesty
            "mistral/mistral-large",
            "meta/llama-3.1-70b",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "REQUESTY_API_KEY",
    },
    "together": {
        "provider_id": "together",
        "display_name": "Together AI",
        "display_name_zh": "Together AI",
        "category": "gateway",
        "api_base_url": "https://api.together.xyz/v1",
        "api_key": os.getenv("TOGETHER_API_KEY"),
        "default_model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "available_models": [
            # Llama 4 Series
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            # Llama 3.3 Series
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            # Llama 3.1 Series
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            # DeepSeek
            "deepseek-ai/DeepSeek-R1",
            "deepseek-ai/DeepSeek-R1-0528-tput",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-V3.1",
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            # Qwen 3 Series
            "Qwen/Qwen3-235B-A22B-FP8-Throughput",
            "Qwen/Qwen3-235B-A22B-Instruct-2507-FP8",
            # Qwen 2.5 Series
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
            "Qwen/Qwen2.5-Coder-32B-Instruct",
            "Qwen/Qwen2.5-VL-72B-Instruct",
            # Mistral
            "mistralai/Mistral-Small-3-Instruct",
            "mistralai/Mixtral-8x22B-Instruct-v0.1",
            # Gemma
            "google/gemma-3-27b-it",
            # Kimi
            "moonshotai/Kimi-K2-Instruct-0905",
            # Image Generation
            "black-forest-labs/FLUX.1-dev",
            "black-forest-labs/FLUX.1-schnell",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "TOGETHER_API_KEY",
    },
    "groq": {
        "provider_id": "groq",
        "display_name": "Groq",
        "display_name_zh": "Groq 超快推理",
        "category": "gateway",
        "api_base_url": "https://api.groq.com/openai/v1",
        "api_key": os.getenv("GROQ_API_KEY"),
        "default_model": "llama-3.3-70b-versatile",
        "available_models": [
            # Groq Compound (Agentic AI System)
            "groq-compound",
            # OpenAI GPT-OSS
            "gpt-oss-120b",
            "gpt-oss-20b",
            # Llama 3.3
            "llama-3.3-70b-versatile",
            "llama-3.3-70b-specdec",
            # Llama 3.1
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            # Llama 3.2 Vision
            "llama-3.2-90b-vision-preview",
            "llama-3.2-11b-vision-preview",
            # DeepSeek
            "deepseek-r1-distill-llama-70b",
            # Mixtral
            "mixtral-8x7b-32768",
            # Gemma
            "gemma2-9b-it",
            # Qwen
            "qwen-qwq-32b",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "GROQ_API_KEY",
    },
    "fireworks": {
        "provider_id": "fireworks",
        "display_name": "Fireworks AI",
        "display_name_zh": "Fireworks AI",
        "category": "gateway",
        "api_base_url": "https://api.fireworks.ai/inference/v1",
        "api_key": os.getenv("FIREWORKS_API_KEY"),
        "default_model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "available_models": [
            "accounts/fireworks/models/llama-v3p1-70b-instruct",
            "accounts/fireworks/models/llama-v3p1-405b-instruct",
            "accounts/fireworks/models/qwen2p5-72b-instruct",
            "accounts/fireworks/models/mixtral-8x22b-instruct",
            "accounts/fireworks/models/deepseek-v3",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "FIREWORKS_API_KEY",
    },
    "deepinfra": {
        "provider_id": "deepinfra",
        "display_name": "Deep Infra",
        "display_name_zh": "Deep Infra",
        "category": "gateway",
        "api_base_url": "https://api.deepinfra.com/v1/openai",
        "api_key": os.getenv("DEEPINFRA_API_KEY"),
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "available_models": [
            "meta-llama/Llama-3.3-70B-Instruct",
            "meta-llama/Meta-Llama-3.1-405B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "mistralai/Mixtral-8x22B-Instruct-v0.1",
            "deepseek-ai/DeepSeek-V3",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": False,
        "env_key_name": "DEEPINFRA_API_KEY",
    },
    # ============================================================
    # Local Providers
    # ============================================================
    "ollama": {
        "provider_id": "ollama",
        "display_name": "Ollama",
        "display_name_zh": "Ollama (本地)",
        "category": "local",
        "api_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "api_key": None,
        "default_model": "TwinkleAI/gemma-3-4B-T1-it:latest",  # Smallest available model (2.7GB)
        "available_models": [
            # ============================================
            # USER'S INSTALLED MODELS (from ollama list)
            # ============================================
            "TwinkleAI/gemma-3-4B-T1-it:latest",  # 2.7GB - Default
            "qwen2.5vl:7b",  # 5.6GB - Vision
            "qwen2.5vl-ufo:latest",  # 5.6GB - Vision
            "qwen-lite:latest",  # 5.6GB - Vision
            "mistral-ufo:latest",  # 15GB
            "mistral-small3.1:24b",  # 15GB
            "TwinkleAI/Llama-3.2-3B-F1-Resoning-Instruct:Q8_0",  # 3.6GB
            # ============================================
            # OTHER POPULAR MODELS (for reference)
            # ============================================
            # Qwen 3 Series
            "qwen3:8b",
            "qwen3:14b",
            "qwen3:32b",
            # Qwen 2.5 Series
            "qwen2.5:7b",
            "qwen2.5:14b",
            "qwen2.5:32b",
            # Llama Series
            "llama3.2:latest",
            "llama3.2:3b",
            # DeepSeek Series
            "deepseek-r1:8b",
            "deepseek-r1:14b",
            # Gemma Series
            "gemma3:4b",
            "gemma3:12b",
            "gemma2:9b",
            # Vision Models
            "llava:13b",
            "qwen2-vl:7b",
            # Phi Series
            "phi4:latest",
            "phi3:latest",
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 32768,
        "temperature": 0.1,
        "is_local": True,
        "env_key_name": "OLLAMA_BASE_URL",
    },
    "lmstudio": {
        "provider_id": "lmstudio",
        "display_name": "LM Studio",
        "display_name_zh": "LM Studio (本地)",
        "category": "local",
        "api_base_url": os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        "api_key": "not-needed",
        "default_model": "qwen/qwen2.5-vl-7b",
        "available_models": [
            # User's LM Studio models
            "qwen/qwen2.5-vl-7b",
            "gemma-3-4b-t1-it",
            "qwen2.5-14b-instruct",
            "qwen/qwen3-vl-8b",
            "mistralai/ministral-3-14b-reasoning",
            "translategemma-12b-it",
            "local-model",  # Fallback for dynamic loading
        ],
        "supports_vision": True,
        "supports_streaming": True,
        "max_tokens": 8192,
        "temperature": 0.1,
        "is_local": True,
        "env_key_name": "LMSTUDIO_BASE_URL",
    },
}

# Fallback chain for providers (order of preference when primary fails)
FALLBACK_CHAIN = [
    # Direct API - highest reliability
    "openai",
    "anthropic",
    "google",
    "deepseek",
    "xai",
    "mistral",
    "cohere",
    "perplexity",
    # Gateway - access to multiple providers
    "openrouter",
    "requesty",
    "together",
    "groq",
    "fireworks",
    "deepinfra",
    # Local - no API costs
    "ollama",
    "lmstudio",
]

# Provider categories for UI grouping
PROVIDER_CATEGORIES = {
    "direct_api": {
        "name": "Direct API Providers",
        "name_zh": "直接 API 提供商",
        "providers": [
            "openai",
            "anthropic",
            "google",
            "deepseek",
            "xai",
            "mistral",
            "cohere",
            "perplexity",
        ],
    },
    "gateway": {
        "name": "LLM Gateway/Router Platforms",
        "name_zh": "LLM 網關/路由平台",
        "providers": [
            "openrouter",
            "requesty",
            "together",
            "groq",
            "fireworks",
            "deepinfra",
        ],
    },
    "local": {
        "name": "Local Providers",
        "name_zh": "本地提供商",
        "providers": ["ollama", "lmstudio"],
    },
}


# ============================================================
# LLM Provider Manager
# ============================================================


class LLMProviderManager:
    """
    Manages LLM provider connections with dynamic switching and fallback support.
    Uses LiteLLM for unified API access across providers.
    """

    def __init__(self, provider_id: str = "ollama"):
        """
        Initialize the LLM Provider Manager.

        Args:
            provider_id: Initial provider to use (default: ollama for local)
        """
        self.providers = copy.deepcopy(DEFAULT_PROVIDERS)
        self.current_provider_id = provider_id
        self.fallback_chain = FALLBACK_CHAIN.copy()
        self.disable_fallback = False  # Set True to skip fallback chain

        # Validate provider exists
        if provider_id not in self.providers:
            raise ValueError(
                f"Unknown provider: {provider_id}. Available: {list(self.providers.keys())}"
            )

        self._configure_litellm()

    def _configure_litellm(self) -> None:
        """Configure LiteLLM settings"""
        if not LITELLM_AVAILABLE:
            return

        # Set API keys from environment
        litellm.openai_key = os.getenv("OPENAI_API_KEY")
        litellm.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        # Enable verbose logging in debug mode
        litellm.set_verbose = os.getenv("DEBUG", "false").lower() == "true"

    @property
    def current_provider(self) -> LLMProviderConfig:
        """Get current provider configuration"""
        return self.providers[self.current_provider_id]

    def switch_provider(self, provider_id: str) -> bool:
        """
        Switch to a different LLM provider.

        Args:
            provider_id: Provider to switch to

        Returns:
            True if switch successful, False otherwise
        """
        if provider_id not in self.providers:
            print(f"[ERROR] Unknown provider: {provider_id}")
            return False

        self.current_provider_id = provider_id
        print(
            f"[INFO] Switched to provider: {self.providers[provider_id]['display_name']}"
        )
        return True

    def get_provider_runtime_info(self) -> dict:
        """Return current provider info dict for run_metadata collection."""
        p = self.current_provider
        return {
            "provider_id": p["provider_id"],
            "provider_name": p["display_name"],
            "provider_type": "Local LLM" if p["is_local"] else "Cloud API",
            "is_local": p["is_local"],
            "model": p.get("default_model", ""),
            "api_base_url": p.get("api_base_url", "") if p["is_local"] else "",
            "category": p.get("category", ""),
        }

    def get_available_models(self) -> list[str]:
        """Get list of available models for current provider"""
        return self.current_provider["available_models"]

    def get_all_providers(self) -> list[dict]:
        """Get list of all available providers with their info"""
        return [
            {
                "id": p["provider_id"],
                "name": p["display_name"],
                "name_zh": p["display_name_zh"],
                "category": p["category"],
                "is_local": p["is_local"],
                "supports_vision": p["supports_vision"],
                "default_model": p["default_model"],
                "env_key_name": p["env_key_name"],
            }
            for p in self.providers.values()
        ]

    def get_providers_by_category(self) -> dict:
        """Get providers grouped by category"""
        result = {}
        for cat_id, cat_info in PROVIDER_CATEGORIES.items():
            result[cat_id] = {
                "name": cat_info["name"],
                "name_zh": cat_info["name_zh"],
                "providers": [
                    self.providers[p]
                    for p in cat_info["providers"]
                    if p in self.providers
                ],
            }
        return result

    def _get_litellm_model_name(self, model: Optional[str] = None) -> str:
        """
        Convert model name to LiteLLM format.

        Args:
            model: Model name (uses default if None)

        Returns:
            LiteLLM-formatted model name
        """
        provider = self.current_provider
        model_name = provider["default_model"] if (not model or model == "default") else model

        # LiteLLM model naming convention
        provider_id = provider["provider_id"]

        if provider_id == "openai":
            return f"openai/{model_name}"
        elif provider_id == "anthropic":
            return f"anthropic/{model_name}"
        elif provider_id == "google":
            return f"gemini/{model_name}"
        elif provider_id == "deepseek":
            return f"deepseek/{model_name}"
        elif provider_id == "xai":
            return f"xai/{model_name}"
        elif provider_id == "mistral":
            return f"mistral/{model_name}"
        elif provider_id == "cohere":
            return f"cohere/{model_name}"
        elif provider_id == "perplexity":
            return f"perplexity/{model_name}"
        elif provider_id == "openrouter":
            # OpenRouter uses openrouter/ prefix
            # Model names already include provider (e.g., anthropic/claude-3.5-sonnet)
            return f"openrouter/{model_name}"
        elif provider_id == "requesty":
            # Requesty uses OpenAI-compatible API with custom base URL
            return model_name
        elif provider_id == "together":
            return f"together_ai/{model_name}"
        elif provider_id == "groq":
            return f"groq/{model_name}"
        elif provider_id == "fireworks":
            return f"fireworks_ai/{model_name}"
        elif provider_id == "deepinfra":
            return f"deepinfra/{model_name}"
        elif provider_id == "ollama":
            return f"ollama/{model_name}"
        elif provider_id == "lmstudio":
            return f"openai/{model_name}"  # LM Studio uses OpenAI-compatible API
        else:
            return model_name

    def completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        """
        Call LLM completion API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (uses provider default if None)
            temperature: Temperature setting (uses provider default if None)
            max_tokens: Max tokens (uses provider default if None)
            stream: If True, returns streaming generator; if False, returns dict
            **kwargs: Additional parameters passed to LiteLLM

        Returns:
            If stream=False: Response dict with 'content' and 'usage' keys
            If stream=True: Generator yielding response chunks
        """
        if not LITELLM_AVAILABLE:
            if stream:

                def error_gen():
                    yield {
                        "choices": [
                            {"delta": {"content": "[ERROR] LiteLLM not installed"}}
                        ]
                    }

                return error_gen()
            return {"content": "[ERROR] LiteLLM not installed", "usage": {}}

        provider = self.current_provider
        litellm_model = self._get_litellm_model_name(model)

        try:
            # Build API parameters
            api_params = {
                "model": litellm_model,
                "messages": messages,
                "temperature": temperature if temperature is not None else provider["temperature"],
                "max_tokens": max_tokens if max_tokens is not None else provider["max_tokens"],
                "stream": stream,
            }

            # Add API base for local providers or custom endpoints
            if provider["is_local"] or provider["category"] == "gateway":
                api_params["api_base"] = provider["api_base_url"]

            # Add API key - re-read from env if not cached at import time
            api_key = provider["api_key"] or os.getenv(
                provider.get("env_key_name", ""), ""
            )
            if api_key:
                api_params["api_key"] = api_key

            # Local providers: no timeout by default (user requirement: 永久 — wait forever).
            # Set LOCAL_LLM_TIMEOUT env var (seconds) to override when needed.
            # Cloud providers: 180s default.
            if "timeout" not in api_params:
                if provider["is_local"]:
                    _local_to = os.getenv("LOCAL_LLM_TIMEOUT")
                    api_params["timeout"] = int(_local_to) if _local_to else None
                else:
                    api_params["timeout"] = 180

            # Merge additional kwargs (but don't override stream)
            for k, v in kwargs.items():
                if k != "stream":
                    api_params[k] = v

            # Call LiteLLM (use litellm.completion() not local import,
            # so OpenTelemetry/Phoenix instrumentor can intercept the call)
            response = litellm.completion(**api_params)

            # If streaming, return the generator directly
            if stream:
                return response

            # Non-streaming: return structured dict
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": response.usage.completion_tokens
                    if response.usage
                    else 0,
                    "total_tokens": response.usage.total_tokens
                    if response.usage
                    else 0,
                },
                "model": response.model,
                "provider": provider["provider_id"],
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] LLM completion failed: {error_msg}")

            # ── Auto-reconnect for local providers ──────────────────────────
            # When Ollama / LM Studio disconnects (connection error / server error),
            # wait until the service comes back before returning the error.
            # This is transparent to all callers — they receive the result once
            # the service recovers and the retry succeeds.
            # No timeout by default (永久). Set LOCAL_LLM_RECONNECT_MAX_WAIT
            # env var to limit wait time.
            _is_conn_error = any(t in error_msg.lower() for t in (
                "connection error", "connectionerror", "connection refused",
                "cannot connect", "failed to establish", "remotedisconnected",
                "broken pipe", "econnrefused", "network error",
            ))
            if provider["is_local"] and _is_conn_error and not stream:
                _wait_for_local_service_ready(provider)
                # Retry with backoff after service recovers.
                # The health check passes once the HTTP server is up, but the model
                # may still be loading (especially on CPU-only machines). We try up to
                # 3 times with increasing delays before giving up.
                import time as _time
                _reconnect_delays = [0, 15, 30]
                for _r_idx, _r_delay in enumerate(_reconnect_delays):
                    if _r_delay:
                        print(
                            f"[WAIT] {provider.get('display_name', 'Local LLM')} model "
                            f"still loading — retrying in {_r_delay}s "
                            f"(attempt {_r_idx + 1}/{len(_reconnect_delays)})"
                        )
                        _time.sleep(_r_delay)
                    try:
                        _retry_params = dict(api_params)
                        _retry_params.pop("stream", None)
                        _retry_params["stream"] = False
                        _retry_response = litellm.completion(**_retry_params)
                        return {
                            "content": _retry_response.choices[0].message.content,
                            "usage": {
                                "prompt_tokens": _retry_response.usage.prompt_tokens
                                if _retry_response.usage else 0,
                                "completion_tokens": _retry_response.usage.completion_tokens
                                if _retry_response.usage else 0,
                                "total_tokens": _retry_response.usage.total_tokens
                                if _retry_response.usage else 0,
                            },
                            "model": _retry_response.model,
                            "provider": provider["provider_id"],
                            "reconnected": True,
                        }
                    except Exception as retry_e:
                        error_msg = str(retry_e)
                        if _r_idx < len(_reconnect_delays) - 1:
                            print(f"[WAIT] Reconnect retry {_r_idx + 1} failed: {error_msg[:120]}")
                        else:
                            print(f"[ERROR] LLM retry after reconnect failed: {error_msg}")

            # For streaming, yield an error message
            if stream:

                def error_stream():
                    class ErrorChunk:
                        class Choice:
                            class Delta:
                                content = f"[連線錯誤] {error_msg}"

                            delta = Delta()

                        choices = [Choice()]

                    yield ErrorChunk()

                return error_stream()

            # Skip fallback if explicitly disabled (user selected specific provider)
            if self.disable_fallback:
                return {
                    "content": f"[ERROR] {error_msg}",
                    "usage": {},
                    "all_failed": True,
                }

            # Try fallback if available (non-streaming only)
            return self._try_fallback(
                messages, model, temperature, max_tokens, error_msg, **kwargs
            )

    def _try_fallback(
        self,
        messages: list[dict],
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        original_error: str,
        **kwargs,
    ) -> dict:
        """Try fallback providers when primary fails"""
        current_idx = (
            self.fallback_chain.index(self.current_provider_id)
            if self.current_provider_id in self.fallback_chain
            else len(self.fallback_chain)
        )

        for fallback_id in self.fallback_chain[current_idx + 1 :]:
            if fallback_id == self.current_provider_id:
                continue

            print(f"[INFO] Trying fallback provider: {fallback_id}")

            # Temporarily switch provider
            original_provider = self.current_provider_id
            self.current_provider_id = fallback_id

            prev_disable_fallback = self.disable_fallback
            self.disable_fallback = True
            try:
                result = self.completion(
                    messages,
                    model=None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                if "ERROR" not in result.get("content", ""):
                    result["fallback_used"] = True
                    result["original_provider"] = original_provider
                    return result
            except Exception:
                continue
            finally:
                self.disable_fallback = prev_disable_fallback
                # Restore original provider
                self.current_provider_id = original_provider

        return {
            "content": f"[ERROR] All providers failed. Original error: {original_error}",
            "usage": {},
            "fallback_used": True,
            "all_failed": True,
        }

    def vision_completion(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        image_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        Call Vision LLM API with image input.

        Args:
            prompt: Text prompt for the image
            image_path: Path to local image file
            image_base64: Base64-encoded image data
            image_url: URL to image
            model: Model to use (uses provider default if None)
            **kwargs: Additional parameters

        Returns:
            Response dict with 'content' key
        """
        if not self.current_provider["supports_vision"]:
            return {
                "content": f"[ERROR] Provider {self.current_provider_id} does not support vision",
                "usage": {},
            }

        # Prepare image content
        image_content = None

        if image_path:
            # Read and encode local file
            path = Path(image_path)
            if not path.exists():
                return {
                    "content": f"[ERROR] Image file not found: {image_path}",
                    "usage": {},
                }

            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Detect MIME type
            suffix = path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_types.get(suffix, "image/png")

            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
            }
        elif image_base64:
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
            }
        elif image_url:
            image_content = {"type": "image_url", "image_url": {"url": image_url}}
        else:
            return {"content": "[ERROR] No image provided", "usage": {}}

        # Build messages with image
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}, image_content],
            }
        ]

        return self.completion(messages, model=model, **kwargs)

    def pdf_completion(
        self,
        prompt: str,
        pdf_base64: str,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[dict]:
        """
        Send PDF directly to LLM for processing (native PDF OCR).
        Only works with providers/models that support PDF file input (e.g., Gemini).

        Args:
            prompt: Text prompt for PDF processing
            pdf_base64: Base64-encoded PDF data
            model: Model to use (uses provider default if None)
            **kwargs: Additional parameters

        Returns:
            Response dict with 'content' key, or None if not supported
        """
        # Check if provider supports vision (PDF input requires vision capability)
        if not self.current_provider["supports_vision"]:
            return None

        # Build messages with PDF content
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/pdf;base64,{pdf_base64}"
                        },
                    },
                ],
            }
        ]

        try:
            result = self.completion(messages, model=model, **kwargs)
            # Check if completion returned an error (e.g., all providers failed)
            if result.get("all_failed") or "[ERROR]" in result.get("content", ""):
                print(
                    f"[WARN] Native PDF OCR completion failed: {result.get('content', '')[:200]}"
                )
                return None
            return result
        except Exception as e:
            error_msg = str(e).lower()
            # If the error indicates PDF is not supported or auth failure, return None for fallback
            if any(
                kw in error_msg
                for kw in [
                    "pdf",
                    "unsupported",
                    "mime",
                    "format",
                    "file type",
                    "authentication",
                    "unauthorized",
                    "401",
                    "api key",
                ]
            ):
                print(f"[INFO] Native PDF OCR not available: {e}")
                return None
            # For other errors (network, etc.), also return None to allow fallback to pdf2image
            print(f"[WARN] Native PDF OCR error: {e}")
            return None

    def test_connection(self, model: Optional[str] = None) -> dict:
        """
        Test connection to current provider with the specified model.

        Args:
            model: Model to test with. If None, uses provider default.

        Returns:
            Dict with 'success', 'provider', 'model', 'latency_ms' keys
        """
        import time

        provider = self.current_provider
        test_model = model or provider["default_model"]

        try:
            start = time.time()

            response = self.completion(
                messages=[
                    {"role": "user", "content": "Hello, respond with 'OK' only."}
                ],
                model=test_model,
                max_tokens=10,
                timeout=15,
            )

            latency = int((time.time() - start) * 1000)

            success = "ERROR" not in response.get("content", "ERROR")

            return {
                "success": success,
                "provider": provider["display_name"],
                "provider_id": provider["provider_id"],
                "model": test_model,
                "latency_ms": latency,
                "response": response.get("content", "")[:50],
            }

        except Exception as e:
            return {
                "success": False,
                "provider": provider["display_name"],
                "provider_id": provider["provider_id"],
                "model": test_model,
                "error": str(e),
            }


# ============================================================
# Convenience Functions
# ============================================================


def get_default_provider() -> str:
    """Get default provider based on environment"""
    env_provider = os.getenv("LLM_PROVIDER", "ollama")
    if env_provider in DEFAULT_PROVIDERS:
        return env_provider
    return "ollama"


def create_provider_manager(provider_id: Optional[str] = None) -> LLMProviderManager:
    """
    Factory function to create a provider manager.

    Args:
        provider_id: Provider to use (uses environment default if None)

    Returns:
        Configured LLMProviderManager instance
    """
    return LLMProviderManager(provider_id or get_default_provider())


def get_provider_display_list() -> list[str]:
    """Get list of provider display names for UI dropdowns"""
    return [p["display_name"] for p in DEFAULT_PROVIDERS.values()]


def get_provider_id_from_display_name(display_name: str) -> Optional[str]:
    """Convert display name to provider ID"""
    for provider_id, config in DEFAULT_PROVIDERS.items():
        if config["display_name"] == display_name:
            return provider_id
    return None


# ============================================================
# Auto-Update Model Lists from Provider APIs
# ============================================================

import logging
import requests

_update_logger = logging.getLogger("llm_providers.auto_update")


def _fetch_models_openrouter(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from OpenRouter (public, no auth needed)."""
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(
            "https://openrouter.ai/api/v1/models", headers=headers, timeout=15
        )
        if resp.status_code != 200:
            _update_logger.warning(f"OpenRouter /models returned {resp.status_code}")
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"OpenRouter model fetch failed: {e}")
        return None


def _fetch_models_groq(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Groq."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"Groq model fetch failed: {e}")
        return None


def _fetch_models_together(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Together AI."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.together.xyz/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Together returns list directly or under "data"
        items = data if isinstance(data, list) else data.get("data", data)
        if isinstance(items, list):
            models = [m["id"] for m in items if isinstance(m, dict) and m.get("id")]
        else:
            return None
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"Together model fetch failed: {e}")
        return None


def _fetch_models_deepinfra(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Deep Infra."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.deepinfra.com/v1/openai/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"DeepInfra model fetch failed: {e}")
        return None


def _fetch_models_ollama(base_url: str | None = None) -> list[str] | None:
    """Fetch installed model names from local Ollama."""
    url = (base_url or "http://localhost:11434").rstrip("/")
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["name"] for m in data.get("models", []) if m.get("name")]
        return sorted(models) if models else None
    except Exception:
        return None


def _fetch_models_lmstudio(base_url: str | None = None) -> list[str] | None:
    """Fetch loaded model names from local LM Studio."""
    url = (base_url or "http://localhost:1234/v1").rstrip("/")
    try:
        resp = requests.get(f"{url}/models", timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception:
        return None


def _is_local_service_up(provider: dict) -> bool:
    """Ping the local LLM service health endpoint.

    Returns True if the service responds (regardless of model list).
    Works for both Ollama (/api/tags) and LM Studio (/v1/models).
    """
    base_url = provider.get("api_base_url", "")
    pid = provider.get("provider_id", "")
    try:
        if pid == "ollama" or "11434" in base_url:
            url = base_url.rstrip("/") or "http://localhost:11434"
            # Ollama: root returns "Ollama is running" with 200
            resp = requests.get(url.rstrip("/v1") or url, timeout=3)
        else:
            # LM Studio and other OpenAI-compatible local servers
            url = base_url.rstrip("/") or "http://localhost:1234/v1"
            resp = requests.get(f"{url}/models", timeout=3)
        return resp.status_code < 500
    except Exception:
        return False


def _wait_for_local_service_ready(provider: dict) -> None:
    """Block until the local LLM service (Ollama / LM Studio) responds.

    Polls the health endpoint at configurable intervals.
    Default: infinite wait (永久) with 15-second intervals.

    Env vars:
        LOCAL_LLM_RECONNECT_INTERVAL  — seconds between polls (default 15)
        LOCAL_LLM_RECONNECT_MAX_WAIT  — total seconds before giving up (default 0 = infinite)
    """
    import time as _t

    interval = int(os.getenv("LOCAL_LLM_RECONNECT_INTERVAL", "15"))
    max_wait = int(os.getenv("LOCAL_LLM_RECONNECT_MAX_WAIT", "0"))  # 0 = infinite
    provider_name = provider.get("display_name", "Local LLM")

    waited = 0
    attempt = 0
    while True:
        attempt += 1
        if _is_local_service_up(provider):
            if attempt > 1:
                print(f"[OK] {provider_name} reconnected after {waited}s (attempt {attempt})")
                # Extra warm-up: service health endpoint responds before the model finishes
                # loading into VRAM/RAM. Give it time to be actually ready for inference.
                _t.sleep(10)
            return
        print(
            f"[WAIT] {provider_name} unreachable — retrying in {interval}s "
            f"(attempt {attempt}{f', waited {waited}s so far' if waited else ''})"
        )
        _t.sleep(interval)
        waited += interval
        if max_wait > 0 and waited >= max_wait:
            print(
                f"[WARN] {provider_name} did not recover within {max_wait}s "
                f"(LOCAL_LLM_RECONNECT_MAX_WAIT). Proceeding with error."
            )
            return


def _fetch_models_openai(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from OpenAI."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Filter to chat models only (exclude embeddings, tts, whisper, dall-e, etc.)
        chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-")
        models = [
            m["id"]
            for m in data.get("data", [])
            if m.get("id") and any(m["id"].startswith(p) for p in chat_prefixes)
        ]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"OpenAI model fetch failed: {e}")
        return None


def _fetch_models_anthropic(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Anthropic."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"Anthropic model fetch failed: {e}")
        return None


def _fetch_models_google(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Google Gemini API."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Google returns "models/gemini-2.5-pro" format — strip the "models/" prefix
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if name.startswith("models/"):
                name = name[7:]
            # Only include generative (chat) models
            if "gemini" in name or "gemma" in name:
                models.append(name)
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"Google model fetch failed: {e}")
        return None


def _fetch_models_mistral(api_key: str | None = None) -> list[str] | None:
    """Fetch available model IDs from Mistral AI."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return sorted(models) if models else None
    except Exception as e:
        _update_logger.warning(f"Mistral model fetch failed: {e}")
        return None


# ============================================================
# Model Cache Persistence (v3.1.0)
# ============================================================

# Cache file stores model lists fetched from provider APIs.
# On next startup, cached models are loaded so users see the full
# model list without needing to re-enter their API key first.
_MODEL_CACHE_FILE = Path(__file__).parent.parent / "data" / "model_cache.json"


def _load_model_cache() -> dict:
    """Load cached model lists from disk.

    Returns:
        Dict mapping provider_id -> list of model names.
    """
    try:
        if _MODEL_CACHE_FILE.exists():
            import json

            with open(_MODEL_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if isinstance(cache, dict):
                return cache
    except Exception as e:
        _update_logger.warning(f"Failed to load model cache: {e}")
    return {}


def _save_model_cache(provider_models: dict | None = None):
    """Save current model lists to disk for next startup.

    Args:
        provider_models: Optional dict of {provider_id: [model_names]}.
            If None, saves all non-local providers from DEFAULT_PROVIDERS.
    """
    import json

    try:
        _MODEL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        if provider_models is None:
            # Save all non-local providers' current model lists
            provider_models = {}
            for pid, config in DEFAULT_PROVIDERS.items():
                if not config.get("is_local"):
                    provider_models[pid] = config.get("available_models", [])

        # Merge with existing cache (don't lose providers not in this update)
        existing = _load_model_cache()
        existing.update(provider_models)

        with open(_MODEL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        _update_logger.info(
            f"Model cache saved: {len(existing)} providers, file: {_MODEL_CACHE_FILE}"
        )
    except Exception as e:
        _update_logger.warning(f"Failed to save model cache: {e}")


def load_cached_models():
    """Load cached model lists into DEFAULT_PROVIDERS on startup.

    Call this early in app initialization, before auto_update_models().
    Cached models supplement (not replace) the static defaults — any
    model in the cache that isn't already in the static list is added.
    """
    cache = _load_model_cache()
    if not cache:
        return

    loaded_count = 0
    for pid, cached_models in cache.items():
        if pid not in DEFAULT_PROVIDERS:
            continue
        if not isinstance(cached_models, list) or not cached_models:
            continue

        config = DEFAULT_PROVIDERS[pid]
        current_set = set(config.get("available_models", []))
        cached_set = set(cached_models)

        # Merge: use cached list as the full list (it was fetched from API)
        if cached_set != current_set:
            # Replace with cached list (which is the most recent API result)
            config["available_models"] = sorted(cached_models)
            loaded_count += 1
            _update_logger.info(
                f"Loaded {len(cached_models)} cached models for "
                f"{config.get('display_name', pid)}"
            )

    if loaded_count:
        _update_logger.info(f"Model cache loaded: {loaded_count} providers updated")


# Mapping from provider_id to fetch function + key source
_PROVIDER_FETCHERS = {
    "openai": (_fetch_models_openai, "OPENAI_API_KEY"),
    "anthropic": (_fetch_models_anthropic, "ANTHROPIC_API_KEY"),
    "google": (_fetch_models_google, "GOOGLE_API_KEY"),
    "mistral": (_fetch_models_mistral, "MISTRAL_API_KEY"),
    "openrouter": (_fetch_models_openrouter, "OPENROUTER_API_KEY"),
    "groq": (_fetch_models_groq, "GROQ_API_KEY"),
    "together": (_fetch_models_together, "TOGETHER_API_KEY"),
    "deepinfra": (_fetch_models_deepinfra, "DEEPINFRA_API_KEY"),
    "ollama": (_fetch_models_ollama, None),
    "lmstudio": (_fetch_models_lmstudio, None),
}


def auto_update_models(providers_to_update: list[str] | None = None) -> dict:
    """
    Auto-update available_models for each provider by fetching live data from APIs.

    Call this on startup to ensure model lists are current.
    - New models found online are ADDED to the list.
    - Models no longer available online are REMOVED from the list.
    - default_model is preserved (if still available) or updated to first model.
    - Providers without API keys or unreachable APIs are silently skipped.

    Args:
        providers_to_update: List of provider_ids to update. If None, updates all.

    Returns:
        Dict with per-provider results: {provider_id: {added: [...], removed: [...], error: str|None}}
    """
    results = {}
    target_ids = providers_to_update or list(_PROVIDER_FETCHERS.keys())

    for pid in target_ids:
        if pid not in _PROVIDER_FETCHERS:
            continue
        if pid not in DEFAULT_PROVIDERS:
            continue

        fetch_fn, env_key = _PROVIDER_FETCHERS[pid]
        config = DEFAULT_PROVIDERS[pid]

        # Get API key or base URL for local providers
        if pid == "ollama":
            arg = config.get("api_base_url")
        elif pid == "lmstudio":
            arg = config.get("api_base_url")
        else:
            arg = os.getenv(env_key, "") if env_key else None

        try:
            live_models = fetch_fn(arg) if arg else fetch_fn()
        except Exception as e:
            results[pid] = {"added": [], "removed": [], "error": str(e)}
            continue

        if live_models is None:
            # Fetch failed or no API key — skip, keep existing list
            results[pid] = {"added": [], "removed": [], "error": "fetch_skipped"}
            continue

        old_set = set(config["available_models"])
        new_set = set(live_models)

        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)

        if added or removed:
            # Update the model list in-place
            config["available_models"] = sorted(live_models)

            # Ensure default_model is still valid
            if config["default_model"] not in new_set:
                # Try to find a similar model or use first
                if config["available_models"]:
                    config["default_model"] = config["available_models"][0]

            display = config.get("display_name", pid)
            if added:
                _update_logger.info(
                    f"[{display}] 新增 {len(added)} 個模型: {added[:5]}{'...' if len(added) > 5 else ''}"
                )
            if removed:
                _update_logger.info(
                    f"[{display}] 移除 {len(removed)} 個已下架模型: {removed[:5]}{'...' if len(removed) > 5 else ''}"
                )

        results[pid] = {"added": added, "removed": removed, "error": None}

    # v3.1.0: Persist updated model lists to cache file
    any_updates = any(
        r.get("added") or r.get("removed")
        for r in results.values()
        if not r.get("error")
    )
    if any_updates:
        _save_model_cache()

    return results


def print_update_summary(results: dict, lang: str = "zh-TW") -> str:
    """Format auto_update_models results into a human-readable summary."""
    from src.chainlit_app.lang_config import lang_key as _lang_key
    _zh = _lang_key(lang) == "zh"
    lines = ["[LLM 模型清單自動更新]" if _zh else "[LLM Model List Auto-Update]"]
    any_change = False

    for pid, info in results.items():
        if info.get("error") == "fetch_skipped":
            continue
        if info.get("error"):
            _err = "錯誤" if _zh else "Error"
            lines.append(f"  ⚠️ {pid}: {_err} - {info['error']}")
            continue

        added = info.get("added", [])
        removed = info.get("removed", [])

        if added or removed:
            any_change = True
            display = DEFAULT_PROVIDERS.get(pid, {}).get("display_name", pid)
            lines.append(f"  📡 {display}:")
            if added:
                _added_msg = f"新增 {len(added)} 個模型" if _zh else f"Added {len(added)} models"
                lines.append(f"    ✅ {_added_msg}")
                for m in added[:10]:
                    lines.append(f"       + {m}")
                if len(added) > 10:
                    _more = f"及其他 {len(added) - 10} 個" if _zh else f"and {len(added) - 10} more"
                    lines.append(f"       ... {_more}")
            if removed:
                _rem_msg = f"移除 {len(removed)} 個已下架模型" if _zh else f"Removed {len(removed)} delisted models"
                lines.append(f"    ❌ {_rem_msg}")
                for m in removed[:10]:
                    lines.append(f"       - {m}")
                if len(removed) > 10:
                    _more = f"及其他 {len(removed) - 10} 個" if _zh else f"and {len(removed) - 10} more"
                    lines.append(f"       ... {_more}")

    if not any_change:
        _uptodate = "所有模型清單已是最新" if _zh else "All model lists are up to date"
        lines.append(f"  ✅ {_uptodate}")

    return "\n".join(lines)


# ============================================================
# Module Initialization
# ============================================================

if __name__ == "__main__":
    # Test the provider manager
    print("=" * 70)
    print("AI-QMS LLM Provider Manager - Test")
    print("=" * 70)

    manager = create_provider_manager()
    print(f"\nCurrent provider: {manager.current_provider['display_name']}")
    print(f"Available models: {manager.get_available_models()[:5]}...")

    print("\n--- All Providers ---")
    for provider in manager.get_all_providers():
        status = "Local" if provider["is_local"] else "Cloud"
        vision = "Vision" if provider["supports_vision"] else ""
        print(
            f"  [{provider['category']:10}] {provider['name']:25} ({status}) {vision}"
        )

    print("\n--- Providers by Category ---")
    for cat_id, cat_info in manager.get_providers_by_category().items():
        print(f"\n{cat_info['name']} ({cat_info['name_zh']}):")
        for p in cat_info["providers"]:
            print(f"  - {p['display_name']}")

    # Test connection
    print("\n--- Connection Test ---")
    result = manager.test_connection()
    print(f"Connection test: {result}")
