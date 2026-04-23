"""
AI-QMS OCR 統一調度引擎
========================

依文件類型與環境自動選擇最適 OCR 引擎：

  PDF 文件：
    Tier 0: PyMuPDF     — 原生文字層抽取（< 10ms，零 ML）
    Tier 1: EasyOCR CPU — 掃描 PDF，32 國語系，無 CUDA 需求
    Tier 2: MarkItDown  — 通用 fallback
    Tier 3: Docling     — 最後手段（重型，GPU 可選）
    Tier 4: plain_text  — 絕對備援

  Word / Excel / PPT：
    Tier 2: MarkItDown（內建 python-docx / openpyxl）
    Tier 3: Docling
    Tier 4: plain_text

  圖片（PNG / JPG / TIFF）：
    Tier 1: EasyOCR CPU
    Tier 2: MarkItDown
    Tier 3: Docling

使用範例：
    from src.ocr.docling_engine import get_engine

    engine = get_engine()
    result = engine.parse("./uploads/SOP-001.pdf", country="tw")
    if result.success:
        print(f"引擎：{result.engine_used}")
        print(result.markdown[:500])
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx", ".doc",
    ".pptx", ".ppt",
    ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif",
}

_PDF_EXTS = {".pdf"}
_OFFICE_EXTS = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}


# ============================================================
# 結果資料結構
# ============================================================


@dataclass
class ParseResult:
    """文件解析結果"""
    success: bool
    markdown: str
    engine_used: str        # "pymupdf" | "easyocr" | "markitdown" | "docling" | "plain_text" | "error"
    page_count: int = 0
    tables_found: int = 0
    images_found: int = 0
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# ============================================================
# OCR 調度引擎（原 DoclingEngine，保持向後相容）
# ============================================================


class DoclingEngine:
    """
    OCR 統一調度引擎

    按 Tier 0→1→2→3→4 順序嘗試，失敗自動降級。
    Singleton，首次使用時延遲初始化。
    """

    def __init__(self) -> None:
        self._pymupdf_available: bool = False
        self._easyocr_available: bool = False
        self._markitdown_available: bool = False
        self._docling_available: bool = False
        self._initialized: bool = False
        self._init_lock = threading.Lock()

        self._docling_converter = None
        self._markitdown = None

    # ── 初始化 ────────────────────────────────────────────────

    def initialize(self) -> None:
        """探測各引擎可用性（冪等）。"""
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return
            self._do_initialize()
            self._initialized = True

    def _do_initialize(self) -> None:
        # Tier 0: PyMuPDF
        try:
            import fitz  # noqa: F401
            self._pymupdf_available = True
            logger.info("Tier 0 PyMuPDF 可用")
        except ImportError:
            logger.warning("PyMuPDF 未安裝（pip install pymupdf），Tier 0 不可用")

        # Tier 1: EasyOCR
        try:
            import easyocr  # noqa: F401
            self._easyocr_available = True
            logger.info("Tier 1 EasyOCR 可用")
        except ImportError:
            logger.warning("EasyOCR 未安裝（pip install easyocr），Tier 1 不可用")

        # Tier 2: MarkItDown
        try:
            from markitdown import MarkItDown  # type: ignore
            self._markitdown = MarkItDown()
            self._markitdown_available = True
            logger.info("Tier 2 MarkItDown 可用")
        except ImportError:
            logger.warning("MarkItDown 未安裝，Tier 2 不可用")
        except Exception as e:
            logger.warning("MarkItDown 初始化失敗: %s", e)

        # Tier 3: Docling（重型，最後手段）
        if _is_docling_enabled():
            try:
                self._docling_converter = _build_docling_converter()
                self._docling_available = True
                logger.info("Tier 3 Docling 可用")
            except ImportError:
                logger.info("Docling 未安裝，Tier 3 不可用")
            except Exception as e:
                logger.warning("Docling 初始化失敗: %s", e)
        else:
            logger.info("Docling 已停用（DOCLING_ENABLED=false）")

        logger.info(
            "OCR 引擎就緒 | PyMuPDF=%s EasyOCR=%s MarkItDown=%s Docling=%s",
            self._pymupdf_available,
            self._easyocr_available,
            self._markitdown_available,
            self._docling_available,
        )

    # ── 主入口 ────────────────────────────────────────────────

    def parse(
        self,
        filepath: "str | Path",
        force_engine: str = "auto",
        country: str = "",
    ) -> ParseResult:
        """
        解析文件，自動選擇最適引擎。

        Args:
            filepath:     文件路徑
            force_engine: "auto"（預設）| "pymupdf" | "easyocr" | "markitdown" | "docling"
            country:      文件來源國家代碼（影響 EasyOCR 語系選擇，如 "tw", "de"）

        Returns:
            ParseResult
        """
        if not self._initialized:
            self.initialize()

        path = Path(filepath)

        if not path.exists():
            return ParseResult(
                success=False, markdown="", engine_used="error",
                error=f"檔案不存在：{filepath}",
            )

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return ParseResult(
                success=False, markdown="", engine_used="error",
                error=f"不支援的格式：{suffix}",
            )

        # 強制指定引擎
        if force_engine != "auto":
            return self._parse_forced(path, force_engine, country)

        # 自動路由
        if suffix in _PDF_EXTS:
            return self._parse_pdf(path, country)
        elif suffix in _OFFICE_EXTS:
            return self._parse_office(path)
        elif suffix in _IMAGE_EXTS:
            return self._parse_image(path, country)
        else:
            return self._parse_plain_text(path)

    # ── PDF 路由（Tier 0→1→2→3→4） ────────────────────────────

    def _parse_pdf(self, path: Path, country: str) -> ParseResult:
        # Tier 0: PyMuPDF 文字層
        if self._pymupdf_available:
            from src.ocr.pymupdf_engine import extract_pdf_text_layer
            text = extract_pdf_text_layer(path)
            if text:
                return ParseResult(
                    success=True,
                    markdown=text,
                    engine_used="pymupdf",
                    page_count=text.count("\n\n") + 1,
                )

        # Tier 1: EasyOCR CPU（掃描 PDF）
        if self._easyocr_available:
            from src.ocr.easyocr_engine import ocr_pdf
            text = ocr_pdf(path, country=country)
            if text:
                return ParseResult(
                    success=True,
                    markdown=text,
                    engine_used="easyocr",
                    page_count=text.count("<!-- Page"),
                )

        # Tier 2: MarkItDown
        if self._markitdown_available:
            result = self._parse_with_markitdown(path)
            if result.success:
                return result

        # Tier 3: Docling
        if self._docling_available:
            result = self._parse_with_docling(path)
            if result.success:
                result.warnings.append("Docling used as last resort (Tier 3)")
                return result

        # Tier 4: plain_text
        return self._parse_plain_text(path)

    # ── Office 文件路由（Tier 2→3→4） ─────────────────────────

    def _parse_office(self, path: Path) -> ParseResult:
        # Tier 2: MarkItDown（內建 python-docx / openpyxl）
        if self._markitdown_available:
            result = self._parse_with_markitdown(path)
            if result.success:
                return result

        # Tier 3: Docling
        if self._docling_available:
            result = self._parse_with_docling(path)
            if result.success:
                result.warnings.append("Docling used as last resort (Tier 3)")
                return result

        # Tier 4
        return self._parse_plain_text(path)

    # ── 圖片路由（Tier 1→2→3） ────────────────────────────────

    def _parse_image(self, path: Path, country: str) -> ParseResult:
        # Tier 1: EasyOCR CPU
        if self._easyocr_available:
            from src.ocr.easyocr_engine import ocr_image
            text = ocr_image(path, country=country)
            if text:
                return ParseResult(
                    success=True, markdown=text, engine_used="easyocr"
                )

        # Tier 2: MarkItDown
        if self._markitdown_available:
            result = self._parse_with_markitdown(path)
            if result.success:
                return result

        # Tier 3: Docling
        if self._docling_available:
            result = self._parse_with_docling(path)
            if result.success:
                result.warnings.append("Docling used as last resort (Tier 3)")
                return result

        return ParseResult(
            success=False, markdown="", engine_used="error",
            error="所有引擎皆無法識別此圖片",
        )

    # ── 強制引擎 ──────────────────────────────────────────────

    def _parse_forced(self, path: Path, engine: str, country: str) -> ParseResult:
        if engine == "pymupdf":
            if not self._pymupdf_available:
                return ParseResult(success=False, markdown="", engine_used="error",
                                   error="PyMuPDF 不可用")
            from src.ocr.pymupdf_engine import extract_pdf_text_layer
            text = extract_pdf_text_layer(path)
            if text:
                return ParseResult(success=True, markdown=text, engine_used="pymupdf")
            return ParseResult(success=False, markdown="", engine_used="pymupdf",
                               error="無文字層")

        elif engine == "easyocr":
            if not self._easyocr_available:
                return ParseResult(success=False, markdown="", engine_used="error",
                                   error="EasyOCR 不可用")
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                from src.ocr.easyocr_engine import ocr_pdf
                text = ocr_pdf(path, country=country)
            else:
                from src.ocr.easyocr_engine import ocr_image
                text = ocr_image(path, country=country)
            if text:
                return ParseResult(success=True, markdown=text, engine_used="easyocr")
            return ParseResult(success=False, markdown="", engine_used="easyocr",
                               error="EasyOCR 識別失敗")

        elif engine == "markitdown":
            if not self._markitdown_available:
                return ParseResult(success=False, markdown="", engine_used="error",
                                   error="MarkItDown 不可用")
            return self._parse_with_markitdown(path)

        elif engine == "docling":
            if not self._docling_available:
                logger.warning("強制 Docling 但不可用，降級至 MarkItDown")
                return self._parse_with_markitdown(path)
            return self._parse_with_docling(path)

        return ParseResult(success=False, markdown="", engine_used="error",
                           error=f"未知引擎: {engine}")

    # ── 各引擎實作 ────────────────────────────────────────────

    def _parse_with_docling(self, path: Path) -> ParseResult:
        try:
            conv_result = self._docling_converter.convert(str(path))
            doc = conv_result.document
            markdown = doc.export_to_markdown()
            tables_found = len(list(doc.tables)) if hasattr(doc, "tables") else 0
            images_found = len(list(doc.pictures)) if hasattr(doc, "pictures") else 0
            page_count = len(list(doc.pages)) if hasattr(doc, "pages") else 0
            return ParseResult(
                success=True, markdown=markdown, engine_used="docling",
                page_count=page_count, tables_found=tables_found,
                images_found=images_found,
            )
        except Exception as e:
            logger.error("Docling 解析失敗（%s）: %s", path.name, e)
            return ParseResult(success=False, markdown="", engine_used="docling",
                               error=str(e))

    def _parse_with_markitdown(self, path: Path) -> ParseResult:
        try:
            result = self._markitdown.convert(str(path))
            markdown = result.text_content or ""
            return ParseResult(
                success=True, markdown=markdown, engine_used="markitdown",
                tables_found=markdown.count("|---"),
            )
        except Exception as e:
            logger.error("MarkItDown 解析失敗（%s）: %s", path.name, e)
            return ParseResult(success=False, markdown="", engine_used="markitdown",
                               error=str(e))

    def _parse_plain_text(self, path: Path) -> ParseResult:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return ParseResult(
                success=True,
                markdown=f"```\n{text}\n```",
                engine_used="plain_text",
            )
        except Exception as e:
            return ParseResult(success=False, markdown="", engine_used="error",
                               error=f"無法讀取檔案: {e}")

    # ── Properties ────────────────────────────────────────────

    @property
    def docling_available(self) -> bool:
        return self._docling_available

    @property
    def markitdown_available(self) -> bool:
        return self._markitdown_available

    @property
    def easyocr_available(self) -> bool:
        return self._easyocr_available

    @property
    def pymupdf_available(self) -> bool:
        return self._pymupdf_available


# ============================================================
# Docling 建構輔助（Tier 3 用）
# ============================================================


def _is_docling_enabled() -> bool:
    try:
        from src.config import DOCLING_ENABLED
        return DOCLING_ENABLED
    except ImportError:
        return os.getenv("DOCLING_ENABLED", "true").lower() == "true"


def _build_docling_converter():
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode  # type: ignore
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice  # type: ignore

    try:
        from src.config import DOCLING_NUM_THREADS, DOCLING_TABLE_MODE, FORCE_CPU
        num_threads = DOCLING_NUM_THREADS
        table_mode_str = DOCLING_TABLE_MODE
        force_cpu = FORCE_CPU
    except ImportError:
        import multiprocessing
        num_threads = max(1, multiprocessing.cpu_count() // 2)
        table_mode_str = "fast"
        force_cpu = os.getenv("FORCE_CPU", "false").lower() == "true"

    table_mode = (
        TableFormerMode.ACCURATE if table_mode_str == "accurate" else TableFormerMode.FAST
    )

    device = AcceleratorDevice.CPU if force_cpu else AcceleratorDevice.AUTO

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = table_mode
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads,
        device=device,
    )

    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )


# ============================================================
# Singleton 管理
# ============================================================

_engine_instance: Optional[DoclingEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> DoclingEngine:
    """
    取得 OCR 調度引擎 Singleton。

    首次呼叫自動執行 initialize()。
    """
    global _engine_instance

    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = DoclingEngine()
                _engine_instance.initialize()

    return _engine_instance


def reset_engine_singleton() -> None:
    """重設 Singleton（測試用）。"""
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
