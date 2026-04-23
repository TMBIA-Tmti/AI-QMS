"""
OCR 模型首次下載守衛

應用啟動時呼叫 ensure_ocr_models_ready()。
若模型尚未下載，在背景 Thread 執行，不阻塞主程序。
若文件到來時模型還未就緒，自動 fallback 至 MarkItDown，不崩潰。
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

EASYOCR_CACHE_DIR = Path.home() / ".EasyOCR" / "model"
SENTINEL_FILE = EASYOCR_CACHE_DIR / ".qms_models_ready"

_download_thread: threading.Thread | None = None
_download_lock = threading.Lock()


# ============================================================
# 公開 API
# ============================================================


def ensure_ocr_models_ready() -> None:
    """
    確保 EasyOCR 語言模型已下載。

    若 sentinel 檔存在 → 立即返回（< 1ms）。
    若不存在 → 啟動背景 Thread 下載，主程序繼續不阻塞。
    """
    if SENTINEL_FILE.exists():
        logger.debug("OCR 模型已就緒（sentinel 存在）")
        return

    global _download_thread
    with _download_lock:
        if _download_thread is not None and _download_thread.is_alive():
            logger.debug("OCR 模型背景下載已在進行中")
            return

        logger.info(
            "OCR 語言模型尚未下載，啟動背景下載...\n"
            "  首份掃描文件可能需等待模型就緒（約 3-10 分鐘，視網路速度）\n"
            "  下次啟動不需重新下載\n"
            "  如需立即備妥，請執行：python scripts/setup_models.py"
        )
        _download_thread = threading.Thread(
            target=_download_models_background,
            name="ocr-model-downloader",
            daemon=True,
        )
        _download_thread.start()


def is_models_ready() -> bool:
    """檢查 EasyOCR 模型是否已就緒。"""
    return SENTINEL_FILE.exists()


def reset_sentinel() -> None:
    """刪除 sentinel，強制下次重新下載（測試 / 重置用）。"""
    if SENTINEL_FILE.exists():
        SENTINEL_FILE.unlink()
        logger.info("OCR sentinel 已刪除，下次啟動將重新下載模型")


# ============================================================
# 背景下載
# ============================================================


def _download_models_background() -> None:
    """背景執行緒：下載所有語系 EasyOCR 模型。"""
    try:
        import easyocr  # noqa: F401
    except ImportError:
        logger.warning("EasyOCR 未安裝，跳過背景模型下載（請執行 pip install easyocr）")
        return

    try:
        from src.config import EASYOCR_LANGUAGE_GROUPS
        groups = EASYOCR_LANGUAGE_GROUPS
    except (ImportError, AttributeError):
        groups = [
            ["ch_tra", "ch_sim", "ja", "ko"],
            ["en", "de", "fr", "it", "es", "pt", "nl", "pl", "vi", "id"],
            ["ar", "hi", "th", "ru"],
        ]

    import easyocr

    total = len(groups)
    for i, group in enumerate(groups, 1):
        try:
            logger.info("背景下載語系組 %d/%d: %s", i, total, group)
            easyocr.Reader(group, gpu=False, verbose=False)
            logger.info("語系組 %d/%d 下載完成", i, total)
        except Exception as e:
            logger.warning("語系組 %d/%d 下載失敗 (%s): %s", i, total, group, e)

    try:
        EASYOCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        SENTINEL_FILE.touch()
        logger.info("OCR 模型背景下載全部完成，sentinel 已寫入")
    except Exception as e:
        logger.warning("sentinel 寫入失敗（不影響功能）: %s", e)
