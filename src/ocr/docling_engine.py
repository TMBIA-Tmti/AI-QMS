"""
AI-QMS Phase 2 — Docling 文件解析引擎
=======================================

主引擎：Docling（高品質，支援 PDF 表格結構、版面分析）
備援引擎：MarkItDown（快速，適合簡單文件）
最後備援：純文字抽取（避免完全失敗）

自動選擇策略：
  1. 若文件 < DOCLING_SIZE_THRESHOLD_BYTES（預設 100KB）→ MarkItDown（毫秒級）
  2. 若 Docling 可用 → Docling（秒級，品質高）
  3. 若 Docling 安裝失敗 → MarkItDown fallback
  4. 若 MarkItDown 也失敗 → 嘗試 UTF-8 純文字讀取

使用範例：
    from src.ocr.docling_engine import get_engine

    engine = get_engine()
    result = engine.parse("./uploads/SOP-001.pdf")
    if result.success:
        print(f"解析引擎：{result.engine_used}")
        print(f"表格數：{result.tables_found}")
        print(result.markdown[:500])
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 支援的文件格式
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}


# ============================================================
# 結果資料結構
# ============================================================


@dataclass
class ParseResult:
    """文件解析結果"""
    success: bool
    markdown: str
    engine_used: str            # "docling" | "markitdown" | "plain_text" | "error"
    page_count: int = 0
    tables_found: int = 0
    images_found: int = 0
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# ============================================================
# DoclingEngine 類別
# ============================================================


class DoclingEngine:
    """
    文件解析引擎

    依文件大小與 Docling 可用性自動選擇最適合的解析方法。
    設計為 Singleton，首次使用時延遲初始化（避免啟動時間過長）。
    """

    def __init__(self):
        self._docling_available: bool = False
        self._markitdown_available: bool = False
        self._initialized: bool = False

        # Docling 物件（延遲初始化）
        self._docling_converter = None

        # MarkItDown 物件（延遲初始化）
        self._markitdown = None

    def initialize(self) -> None:
        """
        初始化引擎（嘗試載入 Docling 與 MarkItDown）

        冪等操作，多次呼叫無副作用。
        """
        if self._initialized:
            return

        # 嘗試初始化 MarkItDown
        try:
            from markitdown import MarkItDown  # type: ignore
            self._markitdown = MarkItDown()
            self._markitdown_available = True
            logger.debug("MarkItDown 初始化成功")
        except ImportError:
            logger.warning("MarkItDown 未安裝，備援引擎不可用")
        except Exception as e:
            logger.warning("MarkItDown 初始化失敗：%s", e)

        # 嘗試初始化 Docling
        if _is_docling_enabled():
            try:
                self._docling_converter = _build_docling_converter()
                self._docling_available = True
                logger.info("Docling 引擎初始化成功")
            except ImportError:
                logger.warning(
                    "Docling 未安裝（pip install docling），將使用 MarkItDown"
                )
            except Exception as e:
                logger.warning("Docling 初始化失敗：%s，將使用 MarkItDown", e)
        else:
            logger.info("Docling 已停用（DOCLING_ENABLED=false）")

        self._initialized = True
        logger.info(
            "DoclingEngine 就緒：Docling=%s, MarkItDown=%s",
            self._docling_available, self._markitdown_available,
        )

    def parse(
        self,
        filepath: str | Path,
        force_engine: str = "auto",
    ) -> ParseResult:
        """
        解析文件

        Args:
            filepath:     文件路徑
            force_engine: "auto" | "docling" | "markitdown"
                          "auto" 根據文件大小自動選擇

        Returns:
            ParseResult 解析結果
        """
        if not self._initialized:
            self.initialize()

        path = Path(filepath)

        # 基本檢查
        if not path.exists():
            return ParseResult(
                success=False,
                markdown="",
                engine_used="error",
                error=f"檔案不存在：{filepath}",
            )

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return ParseResult(
                success=False,
                markdown="",
                engine_used="error",
                error=f"不支援的檔案格式：{suffix}",
            )

        # 決定使用哪個引擎
        file_size = path.stat().st_size
        engine = _select_engine(
            force_engine=force_engine,
            file_size=file_size,
            docling_available=self._docling_available,
            markitdown_available=self._markitdown_available,
        )

        logger.debug(
            "解析 %s（%d KB）使用引擎：%s",
            path.name, file_size // 1024, engine,
        )

        # 執行解析
        if engine == "docling":
            result = self._parse_with_docling(path)
            # Docling 失敗時自動降級
            if not result.success and self._markitdown_available:
                logger.warning(
                    "Docling 失敗，降級至 MarkItDown（%s）", result.error
                )
                result = self._parse_with_markitdown(path)
                result.warnings.append("Docling 失敗，已自動降級至 MarkItDown")
        elif engine == "markitdown":
            result = self._parse_with_markitdown(path)
        else:
            result = self._parse_plain_text(path)

        return result

    def _parse_with_docling(self, path: Path) -> ParseResult:
        """使用 Docling 解析（高品質，支援表格結構）"""
        try:
            conv_result = self._docling_converter.convert(str(path))
            doc = conv_result.document

            markdown = doc.export_to_markdown()

            # 統計表格與圖片數
            tables_found = len(list(doc.tables)) if hasattr(doc, "tables") else 0
            images_found = len(list(doc.pictures)) if hasattr(doc, "pictures") else 0
            page_count = len(list(doc.pages)) if hasattr(doc, "pages") else 0

            return ParseResult(
                success=True,
                markdown=markdown,
                engine_used="docling",
                page_count=page_count,
                tables_found=tables_found,
                images_found=images_found,
            )
        except Exception as e:
            logger.error("Docling 解析失敗（%s）：%s", path.name, e)
            return ParseResult(
                success=False,
                markdown="",
                engine_used="docling",
                error=str(e),
            )

    def _parse_with_markitdown(self, path: Path) -> ParseResult:
        """使用 MarkItDown 解析（快速，適合簡單文件）"""
        try:
            result = self._markitdown.convert(str(path))
            markdown = result.text_content or ""

            return ParseResult(
                success=True,
                markdown=markdown,
                engine_used="markitdown",
                page_count=0,       # MarkItDown 不提供頁數資訊
                tables_found=markdown.count("|---"),  # 粗估 Markdown 表格數
            )
        except Exception as e:
            logger.error("MarkItDown 解析失敗（%s）：%s", path.name, e)
            return ParseResult(
                success=False,
                markdown="",
                engine_used="markitdown",
                error=str(e),
            )

    def _parse_plain_text(self, path: Path) -> ParseResult:
        """最後備援：嘗試以純文字讀取（適合 .txt 等）"""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return ParseResult(
                success=True,
                markdown=f"```\n{text}\n```",
                engine_used="plain_text",
            )
        except Exception as e:
            return ParseResult(
                success=False,
                markdown="",
                engine_used="error",
                error=f"無法讀取檔案：{e}",
            )

    @property
    def docling_available(self) -> bool:
        """Docling 是否可用"""
        return self._docling_available

    @property
    def markitdown_available(self) -> bool:
        """MarkItDown 是否可用"""
        return self._markitdown_available


# ============================================================
# 輔助函式
# ============================================================


def _is_docling_enabled() -> bool:
    """讀取 DOCLING_ENABLED 設定"""
    try:
        from src.config import DOCLING_ENABLED
        return DOCLING_ENABLED
    except ImportError:
        return os.getenv("DOCLING_ENABLED", "true").lower() == "true"


def _build_docling_converter():
    """建立並設定 Docling DocumentConverter"""
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode  # type: ignore
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice  # type: ignore

    # 讀取設定
    try:
        from src.config import DOCLING_NUM_THREADS, DOCLING_TABLE_MODE
        num_threads = DOCLING_NUM_THREADS
        table_mode_str = DOCLING_TABLE_MODE
    except ImportError:
        import multiprocessing
        num_threads = max(1, multiprocessing.cpu_count() // 2)
        table_mode_str = "fast"

    table_mode = (
        TableFormerMode.ACCURATE
        if table_mode_str == "accurate"
        else TableFormerMode.FAST
    )

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = table_mode
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads,
        device=AcceleratorDevice.AUTO,  # 自動偵測 GPU/CPU
    )

    return DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _select_engine(
    force_engine: str,
    file_size: int,
    docling_available: bool,
    markitdown_available: bool,
) -> str:
    """決定使用哪個引擎"""
    if force_engine in ("docling", "markitdown"):
        # 強制指定引擎
        if force_engine == "docling" and not docling_available:
            logger.warning("要求使用 Docling 但不可用，改用 MarkItDown")
            return "markitdown" if markitdown_available else "plain_text"
        return force_engine

    # 自動模式
    try:
        from src.config import DOCLING_SIZE_THRESHOLD_BYTES
        threshold = DOCLING_SIZE_THRESHOLD_BYTES
    except ImportError:
        threshold = 100 * 1024  # 預設 100KB

    if file_size < threshold or not docling_available:
        # 小文件 or Docling 不可用 → MarkItDown
        return "markitdown" if markitdown_available else "plain_text"

    return "docling"


# ============================================================
# Singleton 管理
# ============================================================

_engine_instance: Optional[DoclingEngine] = None
_engine_lock = __import__("threading").Lock()


def get_engine() -> DoclingEngine:
    """
    取得 DoclingEngine Singleton 實例

    首次呼叫會自動執行 initialize()。

    Returns:
        DoclingEngine 實例
    """
    global _engine_instance

    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = DoclingEngine()
                _engine_instance.initialize()

    return _engine_instance


def reset_engine_singleton() -> None:
    """重設 Singleton（測試用途）"""
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
