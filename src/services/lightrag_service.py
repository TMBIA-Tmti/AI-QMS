"""
LightRAG knowledge-graph service. (P1-1/P1-2)
Wraps lightrag-hku with EmbeddingProvider. Graceful degraded mode.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    logger.warning("lightrag-hku not installed — LightRAG in degraded mode")

_instance: Optional[Any] = None
_initialized = False
_init_failed = False


async def _embed(texts: list[str]) -> list[list[float]]:
    from src.services.embedding_provider import EmbeddingProvider
    return await EmbeddingProvider().embed_texts(texts)


def _build_embed_func() -> Optional[Any]:
    if not _AVAILABLE:
        return None
    try:
        from src.services.embedding_provider import EmbeddingProvider
        dim = getattr(EmbeddingProvider(), "embedding_dim", 1024)
    except Exception:
        dim = 1024
    return EmbeddingFunc(embedding_dim=dim, max_token_size=8192, func=_embed)


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
        ef = _build_embed_func()
        if ef is None:
            raise RuntimeError("No embedding function")
        _instance = LightRAG(working_dir=str(LIGHTRAG_WORKING_DIR), embedding_func=ef)
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
        return await _instance.aquery(question, param=QueryParam(mode=mode)) or ""
    except Exception as exc:
        logger.error("LightRAG query failed: %s", exc)
        return ""


def get_lightrag_instance() -> Optional[Any]:
    return _instance
