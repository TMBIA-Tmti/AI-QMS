"""
Tier 0 OCR 引擎：PyMuPDF 原生文字層抽取
=========================================

適用：PDF 含原生文字層（數位生成，非掃描）
速度：< 10ms
依賴：pymupdf（無 ML，無 GPU 需求）

若文字量低於門檻 → 返回 None，通知調度器改用 OCR 引擎。
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 每頁平均字元數低於此值，視為掃描 PDF（無有效文字層）
_MIN_CHARS_PER_PAGE = 30


def extract_pdf_text_layer(path: Path) -> Optional[str]:
    """
    嘗試從 PDF 抽取原生文字層。

    Returns:
        str:  抽取到的文字（Markdown 段落格式）
        None: 無有效文字層（掃描 PDF）或非 PDF 檔案
    """
    if path.suffix.lower() != ".pdf":
        return None

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("PyMuPDF 未安裝，跳過 Tier 0")
        return None

    try:
        doc = fitz.open(str(path))
        page_texts: list[str] = []
        total_chars = 0

        for page in doc:
            text = page.get_text("text").strip()
            page_texts.append(text)
            total_chars += len(text)

        doc.close()

        page_count = len(page_texts)
        if page_count == 0:
            return None

        avg_chars = total_chars / page_count
        if avg_chars < _MIN_CHARS_PER_PAGE:
            logger.debug(
                "PyMuPDF: 平均 %.0f 字/頁 < 門檻 %d，判定為掃描 PDF → 交由 EasyOCR",
                avg_chars,
                _MIN_CHARS_PER_PAGE,
            )
            return None

        markdown = "\n\n".join(p for p in page_texts if p)
        logger.debug(
            "PyMuPDF Tier 0 成功：%d 頁，共 %d 字", page_count, total_chars
        )
        return markdown

    except Exception as e:
        logger.debug("PyMuPDF 抽取失敗（%s）: %s", path.name, e)
        return None
