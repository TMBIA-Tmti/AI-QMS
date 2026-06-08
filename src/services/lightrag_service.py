"""
LightRAG knowledge-graph service. (P1-1/P1-2)
Wraps lightrag-hku with EmbeddingProvider. Graceful degraded mode.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    LightRAG = None
    QueryParam = None
    EmbeddingFunc = None
    logger.warning("lightrag-hku not installed — LightRAG in degraded mode")

_instance: Optional[Any] = None
_initialized = False
_init_failed = False
_completion_fn: Optional[Any] = None


async def _embed(texts: list[str]):
    """LightRAG's EmbeddingFunc wrapper validates dimensions via `result.size`,
    which only exists on numpy arrays — EmbeddingProvider returns plain
    list[list[float]], so convert before returning."""
    import numpy as np
    from src.services.embedding_provider import get_embedding_provider
    vectors = await get_embedding_provider().embed_texts(texts)
    return np.asarray(vectors, dtype=np.float32)


async def _build_embed_func() -> Optional[Any]:
    if not _AVAILABLE:
        return None
    try:
        from src.services.embedding_provider import get_embedding_provider
        provider = get_embedding_provider()
        await provider.initialize()  # populates embedding_dim from the active backend
        dim = provider.embedding_dim or 1024
    except Exception:
        dim = 1024
    return EmbeddingFunc(embedding_dim=dim, max_token_size=8192, func=_embed)


def _get_completion_fn() -> Optional[Any]:
    """Resolve a `(messages, **kwargs) -> {"content": ...}` completion function.

    Mirrors src.analysis.report_api._get_llm_completion_fn_standalone: prefer the
    provider saved in user settings (so LightRAG uses the same model the user
    picked in the UI), falling back to the project-wide default provider.
    """
    global _completion_fn
    if _completion_fn is not None:
        return _completion_fn
    try:
        from src.utils.user_settings import load_user_settings
        from src.llm_providers import create_provider_manager

        settings = load_user_settings()
        provider_id = settings.get("provider_id") if settings else None
        manager = create_provider_manager(provider_id)
        _completion_fn = manager.completion
    except Exception as exc:
        logger.warning("LightRAG: failed to resolve LLM completion function: %s", exc)
        _completion_fn = None
    return _completion_fn


async def _llm_model_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[list] = None,
    **kwargs: Any,
) -> str:
    """LightRAG's required `llm_model_func`.

    LightRAG calls this (async, returning plain text) for entity/relation
    extraction during ingestion and for answer generation during query — see
    lightrag.llm.openai.openai_complete_if_cache for the expected signature.
    We bridge it to the project's LLMProviderManager.completion, which already
    handles provider selection, fallback chains and local-model reconnection.
    """
    completion_fn = _get_completion_fn()
    if completion_fn is None:
        return ""

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})

    # completion() is synchronous (litellm.completion under the hood) — push it
    # to a worker thread so it doesn't block the event loop during ainsert/aquery.
    result = await asyncio.to_thread(completion_fn, messages)
    return result.get("content", "") if isinstance(result, dict) else str(result)


async def initialize_lightrag() -> bool:
    global _instance, _initialized, _init_failed
    if _initialized:
        return _instance is not None
    if _init_failed or not _AVAILABLE:
        _init_failed = True
        return False
    try:
        from src.config import LIGHTRAG_WORKING_DIR
        from pathlib import Path
        Path(str(LIGHTRAG_WORKING_DIR)).mkdir(parents=True, exist_ok=True)
        ef = await _build_embed_func()
        if ef is None:
            raise RuntimeError("No embedding function")
        _instance = LightRAG(
            working_dir=str(LIGHTRAG_WORKING_DIR),
            embedding_func=ef,
            llm_model_func=_llm_model_func,
        )
        # lightrag-hku >= 1.4 requires explicit storage initialisation before
        # any ainsert/aquery call, otherwise JsonDocStatusStorage raises
        # "not initialized" — see HKUDS/LightRAG initialization requirements.
        await _instance.initialize_storages()
        _initialized = True
        logger.info("LightRAG initialised at %s", LIGHTRAG_WORKING_DIR)
        return True
    except Exception as exc:
        _init_failed = True
        logger.warning("LightRAG init failed: %s", exc)
        return False


async def insert_document(doc_id: str, content: str) -> bool:
    if not _initialized and not await initialize_lightrag():
        return False
    try:
        await _instance.ainsert(content)
        return True
    except Exception as exc:
        logger.error("LightRAG insert failed (doc_id=%s): %s", doc_id, exc)
        return False


async def query_knowledge(question: str, mode: str = "hybrid") -> str:
    if not _initialized and not await initialize_lightrag():
        return ""
    try:
        param = QueryParam(mode=mode) if QueryParam is not None else None
        return await _instance.aquery(question, param=param) or ""
    except Exception as exc:
        logger.error("LightRAG query failed: %s", exc)
        return ""


def get_lightrag_instance() -> Optional[Any]:
    return _instance
