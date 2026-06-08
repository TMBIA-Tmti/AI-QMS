"""
ChromaDB vector store service for QMS document semantic search. (P1-1)
Singleton with graceful degraded mode when chromadb unavailable.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False
    logger.warning("chromadb not installed — vector store in degraded mode")

_instance: Optional["VectorStore"] = None


class VectorStore:
    COLLECTION_NAME = "qms_documents"

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._degraded = False
        self._embedding_provider = None
        self._embedding_unavailable_logged = False
        self._init()

    def _init(self) -> None:
        if not _CHROMADB_AVAILABLE:
            self._degraded = True
            return
        try:
            from src.config import CHROMA_PERSIST_DIR
            self._client = chromadb.PersistentClient(
                path=str(CHROMA_PERSIST_DIR),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB initialised at %s", CHROMA_PERSIST_DIR)
        except Exception as exc:
            self._degraded = True
            logger.warning("ChromaDB init failed: %s", exc)

    def _provider(self):
        if self._embedding_provider is None:
            from src.services.embedding_provider import EmbeddingProvider
            self._embedding_provider = EmbeddingProvider()
        return self._embedding_provider

    async def _embedding_ready(self) -> bool:
        """Initialise the embedding provider and report whether it can embed text.

        Logs the "unavailable" condition exactly once per process instead of
        once per chunk — with no Ollama/sentence-transformers fallback installed,
        every add_document/search_similar call would otherwise re-attempt
        initialisation and log a fresh WARNING+ERROR pair, flooding the log
        (observed: 9k+ WARNING / 880+ ERROR lines from a single startup).
        """
        provider = self._provider()
        if not provider.is_initialized:
            await provider.initialize()
        if provider.is_available:
            return True
        if not self._embedding_unavailable_logged:
            logger.warning(
                "Vector store running without embeddings (%s) — "
                "semantic indexing/search disabled, keyword search still works",
                provider.unavailable_reason,
            )
            self._embedding_unavailable_logged = True
        return False

    async def add_document(self, doc_id: str, content: str, metadata: dict) -> None:
        if self._degraded or self._collection is None:
            return
        if not await self._embedding_ready():
            return
        try:
            vecs = await self._provider().embed_texts([content])
            safe = {k: v if isinstance(v, (str, int, float, bool)) else str(v) for k, v in metadata.items()}
            self._collection.upsert(ids=[doc_id], embeddings=[vecs[0]], documents=[content], metadatas=[safe])
        except Exception as exc:
            logger.error("add_document failed (doc_id=%s): %s", doc_id, exc)

    async def search_similar(self, query: str, n_results: int = 5) -> list[dict]:
        if self._degraded or self._collection is None:
            return []
        if not await self._embedding_ready():
            return []
        try:
            vecs = await self._provider().embed_texts([query])
            r = self._collection.query(query_embeddings=[vecs[0]], n_results=n_results,
                                       include=["documents", "metadatas", "distances"])
            return [{"doc_id": i, "content": d, "metadata": m or {}, "score": float(1.0 - s)}
                    for i, d, m, s in zip(r["ids"][0], r["documents"][0],
                                          r["metadatas"][0], r["distances"][0])]
        except Exception as exc:
            logger.error("search_similar failed: %s", exc)
            return []

    async def delete_document(self, doc_id: str) -> None:
        if self._degraded or self._collection is None:
            return
        try:
            self._collection.delete(ids=[doc_id])
        except Exception as exc:
            logger.error("delete_document failed (doc_id=%s): %s", doc_id, exc)

    async def document_exists(self, doc_id: str) -> bool:
        if self._degraded or self._collection is None:
            return False
        try:
            return len(self._collection.get(ids=[doc_id], include=[]).get("ids", [])) > 0
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        return not self._degraded


def get_vector_store() -> VectorStore:
    global _instance
    if _instance is None:
        _instance = VectorStore()
    return _instance
