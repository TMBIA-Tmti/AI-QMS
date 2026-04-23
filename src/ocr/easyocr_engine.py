"""
Tier 1 OCR 引擎：EasyOCR CPU
==============================

適用：掃描 PDF（無文字層）、圖片
語言：32 國語系
GPU：強制 CPU（gpu=False），規避 CUDA 相容性問題

EasyOCR 語言相容性規則：
  - CJK（繁中/簡中/日/韓）各自只能與 English 配對，不能混合
  - 拉丁系語言可全部放在同一個 Reader
  - 阿拉伯/天城文/泰文/西里爾各自與 English 配對

Reader 依語言組合快取（tuple → Reader），需要哪組就 lazy load 哪組。
"""

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 國家代碼 → 語言 tuple（EasyOCR Reader 的語言清單）────────
# CJK 必須各自配 English，不能混合
# 拉丁系國家共用同一個大型 Latin Reader
_LATIN = ("en", "de", "fr", "it", "es", "pt", "nl", "pl", "vi", "id", "ms", "cs", "tr")

_COUNTRY_TO_LANGS: dict[str, tuple] = {
    # 繁體中文
    "tw": ("ch_tra", "en"),
    "hk": ("ch_tra", "en"),
    "mo": ("ch_tra", "en"),
    # 簡體中文
    "cn": ("ch_sim", "en"),
    "sg": ("ch_sim", "en"),
    # 日文
    "jp": ("ja", "en"),
    # 韓文
    "kr": ("ko", "en"),
    # 阿拉伯文
    "sa": ("ar", "en"),
    "ae": ("ar", "en"),
    "eg": ("ar", "en"),
    # 天城文（印地文）
    "in": ("hi", "en"),
    # 泰文
    "th": ("th", "en"),
    # 西里爾
    "ru": ("ru", "en"),
    # 拉丁系（共用 _LATIN Reader）
    "us": _LATIN, "gb": _LATIN, "uk": _LATIN, "au": _LATIN,
    "ca": _LATIN,
    "de": _LATIN, "fr": _LATIN, "it": _LATIN, "es": _LATIN,
    "pt": _LATIN, "br": _LATIN, "nl": _LATIN, "be": _LATIN,
    "ch": _LATIN, "at": _LATIN, "pl": _LATIN, "cz": _LATIN,
    "se": _LATIN, "dk": _LATIN, "no": _LATIN,
    "tr": _LATIN,
    "vn": _LATIN, "id": _LATIN, "my": _LATIN,
    "mx": _LATIN, "co": _LATIN,
}

_DEFAULT_LANGS: tuple = ("en",)

# ── Reader 快取（key = 語言 tuple） ───────────────────────────
_reader_cache: dict[tuple, object] = {}
_cache_lock = threading.Lock()


# ── 輔助 ──────────────────────────────────────────────────────

def _langs_for_country(country: str) -> tuple:
    """取得國家對應的語言 tuple。"""
    return _COUNTRY_TO_LANGS.get(country.lower().strip(), _DEFAULT_LANGS)


def _get_reader(langs: tuple):
    """取得或建立對應語言組合的 EasyOCR Reader（lazy + thread-safe）。"""
    if langs in _reader_cache:
        return _reader_cache[langs]

    with _cache_lock:
        if langs in _reader_cache:
            return _reader_cache[langs]

        try:
            import easyocr
        except ImportError:
            raise ImportError("EasyOCR 未安裝，請執行：pip install easyocr")

        lang_list = list(langs)
        logger.info("初始化 EasyOCR Reader（語言: %s）...", lang_list)
        reader = easyocr.Reader(lang_list, gpu=False, verbose=False)
        _reader_cache[langs] = reader
        logger.info("EasyOCR Reader 就緒（%s）", lang_list)
        return reader


# ── 公開 API ──────────────────────────────────────────────────

def ocr_pdf(path: Path, country: str = "") -> Optional[str]:
    """
    對掃描 PDF 執行 OCR。

    使用 PyMuPDF 將每頁渲染為圖片，再由 EasyOCR 識別文字。

    Args:
        path:    PDF 路徑
        country: 來源國家代碼（如 "tw", "de"），決定使用的語言模型

    Returns:
        str:  識別文字（含頁碼標記）
        None: 失敗
    """
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF 未安裝，EasyOCR 無法渲染 PDF 頁面")
        return None

    langs = _langs_for_country(country)

    try:
        reader = _get_reader(langs)
    except Exception as e:
        logger.error("EasyOCR Reader 初始化失敗（%s）: %s", langs, e)
        return None

    try:
        doc = fitz.open(str(path))
        page_results: list[str] = []

        for page_num, page in enumerate(doc, 1):
            mat = fitz.Matrix(150 / 72, 150 / 72)  # 150 DPI
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_bytes = pix.tobytes("png")

            try:
                lines = reader.readtext(img_bytes, detail=0, paragraph=True)
                page_text = "\n".join(str(line) for line in lines)
                page_results.append(f"<!-- Page {page_num} -->\n{page_text}")
                logger.debug("EasyOCR 第 %d 頁：%d 字", page_num, len(page_text))
            except Exception as e:
                logger.warning("EasyOCR 第 %d 頁失敗: %s", page_num, e)
                page_results.append(f"<!-- Page {page_num}: OCR failed -->")

        doc.close()
        return "\n\n".join(page_results) if page_results else None

    except Exception as e:
        logger.error("EasyOCR 處理 PDF 失敗（%s）: %s", path.name, e)
        return None


def ocr_image(path: Path, country: str = "") -> Optional[str]:
    """
    對圖片執行 OCR。

    Args:
        path:    圖片路徑（PNG / JPG / TIFF）
        country: 來源國家代碼

    Returns:
        str:  識別文字
        None: 失敗
    """
    langs = _langs_for_country(country)

    try:
        reader = _get_reader(langs)
    except Exception as e:
        logger.error("EasyOCR Reader 初始化失敗（%s）: %s", langs, e)
        return None

    try:
        lines = reader.readtext(str(path), detail=0, paragraph=True)
        text = "\n".join(str(line) for line in lines)
        logger.debug("EasyOCR 圖片 OCR 完成：%d 字", len(text))
        return text if text.strip() else None
    except Exception as e:
        logger.error("EasyOCR 圖片 OCR 失敗（%s）: %s", path.name, e)
        return None
