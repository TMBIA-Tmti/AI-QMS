"""
AI-QMS Phase 2 — Ollama 自動偵測模組
======================================

偵測 Ollama 是否運行，並識別最佳可用的 Embedding 和 LLM 模型。
結果快取 5 分鐘，避免頻繁呼叫 API。

偵測流程：
  1. GET {base_url}/api/tags
  2. 解析已安裝模型清單
  3. 依優先級選擇 Embedding 模型（bge-m3 > nomic-embed-text > mxbai-embed-large）
  4. 選擇最大且合格的 LLM 模型（≥ 3GB）

使用範例：
    from src.services.ollama_detector import detect_ollama, get_cached_status

    status = await detect_ollama()
    if status.available:
        print(f"使用 Embedding：{status.embedding_model} ({status.embedding_dim} 維)")
    else:
        print(f"Ollama 不可用：{status.fallback_reason}")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 常數設定
# ============================================================

# Embedding 模型優先級（名稱包含子字串即符合）
EMBEDDING_MODEL_PRIORITY: list[tuple[str, int]] = [
    ("bge-m3",              1024),   # 最佳：多語言，1024 維
    ("nomic-embed-text",     768),   # 次佳：768 維
    ("mxbai-embed-large",   1024),   # 替代：1024 維
]

# LLM 最小規模（GB），低於此規模不採用
LLM_MIN_SIZE_GB: float = 3.0

# 合格的 LLM 系列（子字串匹配）
LLM_QUALIFIED_FAMILIES: list[str] = [
    "qwen2.5", "qwen2", "llama3", "llama2",
    "gemma2", "gemma", "mistral", "phi3",
    "deepseek", "yi",
]

# 快取有效期（秒）
CACHE_TTL_SECONDS: int = 300  # 5 分鐘


# ============================================================
# 資料結構
# ============================================================


@dataclass
class OllamaStatus:
    """Ollama 偵測結果"""
    available: bool
    base_url: str
    embedding_model: Optional[str] = None    # 最佳可用 Embedding 模型名稱
    embedding_dim: int = 384                 # 向量維度（降級時為 384）
    llm_model: Optional[str] = None          # 最佳可用 LLM 模型名稱
    installed_models: list[str] = field(default_factory=list)
    fallback_reason: Optional[str] = None    # 未使用 Ollama 的原因
    detected_at: float = field(default_factory=time.time)


# ============================================================
# 快取
# ============================================================

_cache: Optional[OllamaStatus] = None
_cache_lock = asyncio.Lock() if False else __import__("threading").Lock()


def get_cached_status() -> Optional[OllamaStatus]:
    """
    取得快取的偵測結果

    Returns:
        快取結果（若快取過期或不存在則回傳 None）
    """
    with _cache_lock:
        if _cache is None:
            return None
        age = time.time() - _cache.detected_at
        if age > CACHE_TTL_SECONDS:
            logger.debug("Ollama 偵測快取已過期（%.0f 秒前）", age)
            return None
        return _cache


def _set_cache(status: OllamaStatus) -> None:
    """更新快取"""
    global _cache
    with _cache_lock:
        _cache = status


def invalidate_cache() -> None:
    """強制清除快取（測試用途或設定變更後呼叫）"""
    global _cache
    with _cache_lock:
        _cache = None


# ============================================================
# 核心偵測邏輯
# ============================================================


async def detect_ollama(
    base_url: str = "http://localhost:11434",
    timeout: float = 5.0,
) -> OllamaStatus:
    """
    偵測 Ollama 是否運行，並選擇最佳模型

    Args:
        base_url: Ollama API 基礎 URL
        timeout:  HTTP 請求逾時（秒）

    Returns:
        OllamaStatus 偵測結果
    """
    # 先回傳快取
    cached = get_cached_status()
    if cached is not None and cached.base_url == base_url:
        logger.debug("使用 Ollama 偵測快取（模型：%s）", cached.embedding_model)
        return cached

    logger.info("開始偵測 Ollama：%s", base_url)

    try:
        import httpx
    except ImportError:
        status = OllamaStatus(
            available=False,
            base_url=base_url,
            fallback_reason="httpx 未安裝，無法偵測 Ollama",
        )
        _set_cache(status)
        return status

    # Step 1：連線測試
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError:
        status = OllamaStatus(
            available=False,
            base_url=base_url,
            fallback_reason="Ollama 未運行或無法連線",
        )
        _set_cache(status)
        logger.info("Ollama 不可用：連線失敗")
        return status
    except httpx.TimeoutException:
        status = OllamaStatus(
            available=False,
            base_url=base_url,
            fallback_reason=f"Ollama 連線逾時（{timeout}s）",
        )
        _set_cache(status)
        logger.warning("Ollama 偵測逾時")
        return status
    except Exception as e:
        status = OllamaStatus(
            available=False,
            base_url=base_url,
            fallback_reason=f"Ollama 偵測錯誤：{e}",
        )
        _set_cache(status)
        logger.error("Ollama 偵測失敗：%s", e)
        return status

    # Step 2：解析模型清單
    models = data.get("models", [])
    model_names = [m.get("name", "") for m in models]
    model_sizes = {m.get("name", ""): m.get("size", 0) for m in models}

    logger.debug("Ollama 已安裝模型：%s", model_names)

    # Step 3：選擇 Embedding 模型
    selected_embed_model = None
    selected_embed_dim = 384

    for embed_name, embed_dim in EMBEDDING_MODEL_PRIORITY:
        for model_name in model_names:
            if embed_name in model_name.lower():
                selected_embed_model = model_name
                selected_embed_dim = embed_dim
                break
        if selected_embed_model:
            break

    # Step 4：選擇 LLM 模型（最大的合格模型）
    selected_llm_model = None
    best_size = 0

    for model_name in model_names:
        # 檢查是否屬於合格系列
        name_lower = model_name.lower()
        is_qualified_family = any(
            family in name_lower for family in LLM_QUALIFIED_FAMILIES
        )
        if not is_qualified_family:
            continue

        # 檢查大小（bytes → GB）
        size_bytes = model_sizes.get(model_name, 0)
        size_gb = size_bytes / (1024 ** 3)

        if size_gb >= LLM_MIN_SIZE_GB and size_gb > best_size:
            best_size = size_gb
            selected_llm_model = model_name

    # 建立結果
    if not selected_embed_model:
        fallback_reason = (
            "Ollama 已連線但未找到合適的 Embedding 模型，"
            f"需要：{[p[0] for p in EMBEDDING_MODEL_PRIORITY]}"
        )
    else:
        fallback_reason = None

    status = OllamaStatus(
        available=True,
        base_url=base_url,
        embedding_model=selected_embed_model,
        embedding_dim=selected_embed_dim if selected_embed_model else 384,
        llm_model=selected_llm_model,
        installed_models=model_names,
        fallback_reason=fallback_reason,
    )

    _set_cache(status)

    logger.info(
        "Ollama 偵測完成：Embedding=%s(%d 維), LLM=%s",
        selected_embed_model or "無（需降級）",
        status.embedding_dim,
        selected_llm_model or "無",
    )

    return status


def detect_ollama_sync(
    base_url: str = "http://localhost:11434",
    timeout: float = 5.0,
) -> OllamaStatus:
    """
    同步版 detect_ollama（在非 async 環境呼叫）

    Args:
        base_url: Ollama API 基礎 URL
        timeout:  HTTP 請求逾時（秒）
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 若在 async 環境中呼叫，建立新執行緒執行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, detect_ollama(base_url, timeout)
                )
                return future.result()
        else:
            return loop.run_until_complete(detect_ollama(base_url, timeout))
    except Exception as e:
        logger.error("同步偵測 Ollama 失敗：%s", e)
        return OllamaStatus(
            available=False,
            base_url=base_url,
            fallback_reason=str(e),
        )
