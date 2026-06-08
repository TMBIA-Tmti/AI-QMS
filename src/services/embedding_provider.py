"""
AI-QMS Phase 2 — Embedding 提供者模組
=======================================

自動選擇最佳 Embedding 策略：

  優先級 1：Ollama bge-m3          (1024 維，最佳多語言品質)
  優先級 2：Ollama nomic-embed-text (768 維，次佳)
  優先級 3：sentence-transformers   (384 維，離線降級，需額外安裝)

設計原則：
  - 零設定：系統啟動時自動偵測 Ollama，選擇最佳策略
  - 降級透明：fallback 時記錄 WARNING，功能不中斷
  - Embedding 降級不影響 LightRAG 知識圖譜品質
    （圖譜由 LLM 實體抽取建立，Embedding 僅輔助向量搜尋）

使用範例：
    from src.services.embedding_provider import get_embedding_provider

    provider = get_embedding_provider()
    await provider.initialize()

    vectors = await provider.embed_texts(["矯正措施", "CAPA 管理"])
    print(f"使用 {provider.provider_name}，維度 {provider.embedding_dim}")
"""

import asyncio
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Embedding 降級模型（Ollama 不可用時）
FALLBACK_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
FALLBACK_EMBEDDING_DIM = 384

_safe_device_cache: Optional[str] = None


def _select_safe_torch_device() -> str:
    """Pick 'cuda' only if the installed PyTorch build actually has compiled
    kernels for this GPU's compute capability; otherwise fall back to 'cpu'.

    Some installs report torch.cuda.is_available() == True (driver/runtime load
    fine) yet crash at the first kernel launch with "CUDA error: no kernel
    image is available for execution on the device" — e.g. a cu124 build on a
    Blackwell (sm_120) GPU. Detecting that mismatch up front avoids crashing
    every embedding call; once the user installs a torch build that ships
    sm_120 kernels, this will automatically pick 'cuda' again.
    """
    global _safe_device_cache
    if _safe_device_cache is not None:
        return _safe_device_cache

    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability(0)
            arch_list = torch.cuda.get_arch_list()
            if f"sm_{major}{minor}" in arch_list:
                device = "cuda"
            else:
                logger.warning(
                    "GPU compute capability sm_%d%d not in this PyTorch build's "
                    "arch list %s — using CPU for embeddings to avoid CUDA "
                    "kernel crashes (reinstall torch with matching CUDA support "
                    "to enable GPU)",
                    major, minor, arch_list,
                )
    except Exception as e:
        logger.debug("CUDA capability check failed, defaulting to CPU: %s", e)

    _safe_device_cache = device
    return device


# ============================================================
# EmbeddingProvider 類別
# ============================================================


class EmbeddingProvider:
    """
    Embedding 提供者

    自動依 Ollama 可用性選擇策略：
      - Ollama 可用且有合格模型 → 使用 Ollama Embedding API
      - Ollama 不可用 → 使用 sentence-transformers 本地模型

    執行緒安全：initialize() 使用 asyncio.Lock 防止重複初始化。
    """

    def __init__(self):
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._provider_name: str = "uninitialised"
        self._embedding_dim: int = 0
        self._ollama_model: Optional[str] = None
        self._ollama_base_url: Optional[str] = None
        self._st_model = None               # sentence-transformers 模型物件
        self._use_ollama: bool = False

    async def initialize(self) -> None:
        """
        初始化：偵測 Ollama，決定使用策略

        冪等操作：多次呼叫只初始化一次。
        """
        async with self._init_lock:
            if self._initialized:
                return

            try:
                from src.services.ollama_detector import detect_ollama
                from src.config import OLLAMA_BASE_URL
                base_url = OLLAMA_BASE_URL
            except ImportError:
                base_url = "http://localhost:11434"

            try:
                from src.services.ollama_detector import detect_ollama
                status = await detect_ollama(base_url)
            except Exception as e:
                logger.warning("Ollama 偵測失敗，直接降級：%s", e)
                status = None

            if status and status.available and status.embedding_model:
                # 使用 Ollama Embedding
                self._use_ollama = True
                self._ollama_model = status.embedding_model
                self._ollama_base_url = status.base_url
                self._embedding_dim = status.embedding_dim
                self._provider_name = f"ollama/{status.embedding_model}"
                logger.info(
                    "Embedding 策略：Ollama %s（%d 維）",
                    status.embedding_model, status.embedding_dim,
                )
            else:
                # 降級至 sentence-transformers
                fallback_reason = (
                    status.fallback_reason if status else "Ollama 偵測失敗"
                )
                logger.warning(
                    "Ollama Embedding 不可用（%s），降級至 sentence-transformers",
                    fallback_reason,
                )
                await self._load_sentence_transformers()

            self._initialized = True

    async def _load_sentence_transformers(self) -> None:
        """載入 sentence-transformers 降級模型"""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise ImportError(
                "sentence-transformers 未安裝。\n"
                "請執行：pip install sentence-transformers torch\n"
                f"原始錯誤：{e}"
            ) from e

        device = _select_safe_torch_device()
        logger.info("載入 sentence-transformers 模型：%s（device=%s）", FALLBACK_MODEL_NAME, device)
        # 在 executor 中載入（避免阻塞 event loop）
        loop = asyncio.get_event_loop()
        self._st_model = await loop.run_in_executor(
            None,
            lambda: SentenceTransformer(FALLBACK_MODEL_NAME, device=device),
        )
        self._use_ollama = False
        self._embedding_dim = FALLBACK_EMBEDDING_DIM
        self._provider_name = f"sentence-transformers/{FALLBACK_MODEL_NAME}"
        logger.info(
            "Embedding 策略（降級）：%s（%d 維）",
            FALLBACK_MODEL_NAME, FALLBACK_EMBEDDING_DIM,
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        批次向量化文字

        Args:
            texts: 要向量化的文字清單

        Returns:
            向量清單，每個元素為 float list，長度為 embedding_dim
        """
        if not self._initialized:
            await self.initialize()

        if not texts:
            return []

        if self._use_ollama:
            return await self._embed_with_ollama(texts)
        else:
            return await self._embed_with_sentence_transformers(texts)

    async def _embed_with_ollama(self, texts: list[str]) -> list[list[float]]:
        """使用 Ollama Embedding API"""
        try:
            import httpx
        except ImportError:
            logger.error("httpx 未安裝，無法呼叫 Ollama")
            raise

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                response = await client.post(
                    f"{self._ollama_base_url}/api/embeddings",
                    json={"model": self._ollama_model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                results.append(data["embedding"])
        return results

    async def _embed_with_sentence_transformers(
        self, texts: list[str]
    ) -> list[list[float]]:
        """使用 sentence-transformers 本地模型（在 executor 中執行）"""
        if self._st_model is None:
            await self._load_sentence_transformers()

        loop = asyncio.get_event_loop()
        embeddings: np.ndarray = await loop.run_in_executor(
            None,
            lambda: self._st_model.encode(texts, convert_to_numpy=True),
        )
        return embeddings.tolist()

    @property
    def embedding_dim(self) -> int:
        """向量維度"""
        return self._embedding_dim

    @property
    def provider_name(self) -> str:
        """目前使用的 Provider 名稱（格式：provider/model）"""
        return self._provider_name

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized


# ============================================================
# Singleton 管理
# ============================================================

_provider_instance: Optional[EmbeddingProvider] = None
_provider_lock = __import__("threading").Lock()


def get_embedding_provider() -> EmbeddingProvider:
    """
    取得 EmbeddingProvider Singleton 實例

    注意：取得實例後仍需呼叫 await provider.initialize() 才能使用。

    Returns:
        EmbeddingProvider 實例
    """
    global _provider_instance

    if _provider_instance is None:
        with _provider_lock:
            if _provider_instance is None:
                _provider_instance = EmbeddingProvider()

    return _provider_instance


def reset_provider_singleton() -> None:
    """重設 Singleton（測試用途）"""
    global _provider_instance
    with _provider_lock:
        _provider_instance = None
