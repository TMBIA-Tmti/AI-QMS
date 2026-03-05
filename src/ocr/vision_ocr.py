"""
AI-QMS Phase 1 Document Control - MarkItDown-First Document Processing Pipeline
Primary: MarkItDown (Microsoft) for fast markdown conversion (0 tokens)
Fallback: LLM Vision OCR for scanned/image-based PDFs
Signature: LLM Vision checks first page image for stamps/signatures

Supported File Formats:
- PDF: .pdf
- Images: .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp
- Word: .docx, .doc
- Excel: .xlsx, .xls
- PowerPoint: .pptx, .ppt
- Text: .txt, .md, .csv, .rtf

Version: 3.0.0
Updated: 2026-02-12
"""

import re
import json
import time
import base64
import platform
from pathlib import Path
from typing import TypedDict, Optional, Any


# ============================================================
# MarkItDown - Primary converter (fast, 0 tokens)
# ============================================================

try:
    from markitdown import MarkItDown

    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False
    print("[WARN] markitdown not installed. MarkItDown conversion disabled.")

# ============================================================
# Optional Dependencies - Graceful Degradation
# ============================================================

try:
    from pdf2image import convert_from_path

    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    print("[WARN] pdf2image not installed. PDF-to-image conversion disabled.")

try:
    from PIL import Image  # noqa: F401
    import io

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[WARN] Pillow not installed. Image processing disabled.")

# PyPDF2 for page count
try:
    import PyPDF2

    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

# pypdf for image extraction check
try:
    import pypdf  # noqa: F401

    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# For legacy .doc, .xls, .ppt formats (Windows only with pywin32)
WIN32COM_AVAILABLE = False
if platform.system() == "Windows":
    try:
        import win32com.client
        import pythoncom

        WIN32COM_AVAILABLE = True
    except ImportError:
        print(
            "[WARN] pywin32 not installed. Legacy Office formats (.doc, .xls, .ppt) disabled."
        )


# ============================================================
# Supported File Extensions
# ============================================================

SUPPORTED_EXTENSIONS = {
    # PDF
    ".pdf": "pdf",
    # Images
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".bmp": "image",
    # Word
    ".docx": "word",
    ".doc": "word_legacy",
    # Excel
    ".xlsx": "excel",
    ".xls": "excel_legacy",
    # PowerPoint
    ".pptx": "powerpoint",
    ".ppt": "powerpoint_legacy",
    # Text
    ".txt": "text",
    ".md": "text",
    ".csv": "csv",
    ".rtf": "text",
}


# ============================================================
# Type Definitions
# ============================================================


class DetectedElements(TypedDict):
    """Elements detected in document"""

    stamps: list[dict]
    signatures: list[dict]
    tables: list[dict]
    headers: list[str]
    metadata: dict


class OCRResult(TypedDict):
    """OCR processing result"""

    success: bool
    provider_used: str
    text_content: str
    markdown_content: str
    confidence: float
    processing_time_ms: int
    page_count: int
    detected_elements: DetectedElements
    fallback_used: bool
    error_message: Optional[str]
    file_type: str


# ============================================================
# Vision OCR System Prompt (used only for signature detection
# and scanned PDF fallback)
# ============================================================

VISION_OCR_SYSTEM_PROMPT = """你是專業的文件 OCR 處理專家，專門處理醫療器材品質管理系統 (QMS) 文件。
文件可能來自全球各地的供應商、合作夥伴及法規機構，因此可能包含任何語言的文字。

你的任務：
1. 精確辨識圖片中的所有文字內容（任何語言）
2. 保持原始文件的結構和格式
3. 識別並標記特殊元素（不限語言）：

   【印章 / Stamps / Seals — 任何語言】
   - 中文：公司章、簽核章、日期章、騎縫章、職章、負責人章、法人章、圓形章、方形章
   - 日本語：実印、認印、社印、角印、丸印、代表者印
   - 한국어：도장、인감、직인、관인、법인인감
   - Any circular/rectangular red/blue ink pattern, rubber stamp impression, embossed seal, wax seal
   - Official seals from any country (notary seals, government seals, corporate seals)

   【手寫簽名 / Handwritten Signatures — 任何語言】
   - 任何手寫筆跡、親筆簽名、草書簽名、initials
   - Signatures in any script: Latin, CJK, Arabic, Devanagari, Thai, Cyrillic, etc.

   【電子簽名 / Digital Signatures — 任何語言】
   - 數位簽章標記、電子簽名圖片
   - Digital certificate stamps, PKI signatures, timestamp tokens

   【審核欄位 / Approval Fields — 任何語言】
   - English: Approved by / Reviewed by / Prepared by / Checked by / Verified by / Released by
   - 中文：核准 / 審核 / 制定 / 確認 / 覆核
   - 日本語：承認 / 確認 / 検認 / 決裁 / 起案
   - 한국어：승인 / 검토 / 확인 / 결재 / 기안
   - Deutsch: Genehmigt von / Geprüft von / Freigegeben von / Erstellt von
   - Français: Approuvé par / Vérifié par / Validé par / Rédigé par
   - Español: Aprobado por / Revisado por / Firmado por / Elaborado por
   - Português: Aprovado por / Verificado por / Assinado por
   - Русский: Утверждено / Проверено / Подпись
   - العربية: توقيع / ختم / موافقة / معتمد
   - ภาษาไทย: อนุมัติ / ตรวจสอบ / ลงนาม
   - Tiếng Việt: Phê duyệt / Xác nhận / Ký tên
   - Bahasa: Diluluskan / Disetujui / Ditandatangani
   - Türkçe: Onay / İmza / Mühür
   - Any other language's equivalent approval/review/signature fields

   【其他元素】
   - 表格結構
   - 文件編號和版本號
   - 生效日期

重要：
- 即使印章或簽名模糊、部分遮擋、或為紅色/藍色印泥，仍應盡力辨識並記錄。
- 如果看到任何類似印章的圓形/方形紅色/藍色圖案，或任何手寫筆跡，都必須記錄在 stamps_detected 或 signatures_detected 中。
- 文件可能混合多種語言（例如中英日混合），請辨識所有語言的內容。
- 不認識的文字也要盡量轉錄，並標記其可能的語言。

輸出格式要求：
1. 使用 Markdown 格式輸出
2. 表格使用 Markdown 表格語法
3. 標題使用適當的 # 層級
4. **絕對不要**在輸出中使用 Markdown 圖片語法 ![...](...) 或任何圖片 URL。
   印章和簽名請用純文字描述，例如：「[印章: 公司章，紅色圓形]」、「[簽名: 手寫簽名]」。
   不要生成或編造任何圖片連結。
5. 在文件末尾附加 JSON 格式的元資料區塊，用 ```json 包裹

元資料區塊格式：
```json
{
  "document_id": "文件編號",
  "version": "版本號",
  "effective_date": "生效日期",
  "stamps_detected": ["印章描述1", "印章描述2"],
  "signatures_detected": ["簽名描述1"],
  "languages_detected": ["zh-TW", "en", "ja"],
  "confidence": 0.95
}
```

請確保辨識準確，特別注意繁體中文字符。如果無法辨識某些內容，請標記為 [無法辨識]。"""


# ============================================================
# MarkItDown-First Document Processor
# ============================================================


class VisionOCRProcessor:
    """
    MarkItDown-First Document Processor.

    New pipeline (v3.0.0):
    1. MarkItDown converts file to markdown (fast, 0 tokens)
    2. For scanned/image PDFs where MarkItDown returns empty: LLM Vision OCR fallback
    3. Images always use LLM Vision OCR

    Signature detection is handled separately in app.py using pypdf image check.
    """

    def __init__(self, llm_provider_manager=None):
        """
        Initialize the Document Processor.

        Args:
            llm_provider_manager: LLMProviderManager instance (creates new if None)
        """
        if llm_provider_manager is None:
            from src.llm_providers import create_provider_manager

            self.llm = create_provider_manager()
        else:
            self.llm = llm_provider_manager

        self.system_prompt = VISION_OCR_SYSTEM_PROMPT

        # Initialize MarkItDown
        if MARKITDOWN_AVAILABLE:
            self._markitdown = MarkItDown()
        else:
            self._markitdown = None

    # --------------------------------------------------------
    # Main Processing Methods
    # --------------------------------------------------------

    def process_file(self, file_path: str, model_name: str = "") -> OCRResult:
        """
        Process any supported file type.
        Uses MarkItDown as primary converter for all non-image files.
        Falls back to LLM Vision OCR for images and scanned PDFs.

        Args:
            file_path: Path to file
            model_name: Model to use for LLM fallback (empty string uses provider default)

        Returns:
            OCRResult with extracted text and metadata
        """
        self.model_name = model_name
        start_time = time.time()
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            return self._error_result(
                f"Unsupported file type: {suffix}. Supported: {list(SUPPORTED_EXTENSIONS.keys())}",
                start_time,
                file_type="unknown",
            )

        file_type = SUPPORTED_EXTENSIONS[suffix]

        try:
            # Images always use LLM Vision OCR (MarkItDown can't extract text from images)
            if file_type == "image":
                return self.process_image(file_path)

            # Legacy formats that need win32com
            if file_type in ("word_legacy", "excel_legacy", "powerpoint_legacy"):
                return self._process_legacy_format(file_path, file_type)

            # All other formats: try MarkItDown first
            if self._markitdown is not None:
                result = self._process_with_markitdown(file_path, file_type)
                if result is not None:
                    return result

            # MarkItDown not available or failed: use LLM for PDFs, error for others
            if file_type == "pdf":
                return self._process_pdf_with_llm(file_path)
            else:
                return self._error_result(
                    "MarkItDown not available and no fallback for this file type.",
                    start_time,
                    file_type,
                )

        except Exception as e:
            return self._error_result(
                f"Processing failed: {str(e)}", start_time, file_type
            )

    def _process_with_markitdown(
        self, file_path: str, file_type: str
    ) -> Optional[OCRResult]:
        """
        Process file using MarkItDown.
        Returns None if MarkItDown fails or returns empty content (scanned PDF).

        Args:
            file_path: Path to file
            file_type: Type of file (pdf, word, excel, etc.)

        Returns:
            OCRResult or None if MarkItDown can't handle this file
        """
        start_time = time.time()

        try:
            result = self._markitdown.convert(file_path)
            markdown_content = result.markdown or ""

            # Check if content is meaningful (not empty/too short)
            stripped = markdown_content.strip()
            if len(stripped) < 50:
                # MarkItDown returned empty/minimal content
                # This likely means it's a scanned PDF (image-only)
                if file_type == "pdf":
                    print(
                        f"[INFO] MarkItDown returned minimal content ({len(stripped)} chars), "
                        f"falling back to LLM Vision OCR for scanned PDF"
                    )
                    return None  # Signal to use LLM fallback
                # For non-PDF files, still return the result (might be legitimately short)

            processing_time = int((time.time() - start_time) * 1000)

            # Get page count for PDFs
            page_count = 1
            if file_type == "pdf" and PYPDF2_AVAILABLE:
                try:
                    with open(file_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        page_count = len(reader.pages)
                except Exception:
                    pass

            return OCRResult(
                success=True,
                provider_used="MarkItDown",
                text_content=markdown_content,
                markdown_content=markdown_content,
                confidence=1.0,  # Direct text extraction = high confidence
                processing_time_ms=processing_time,
                page_count=page_count,
                detected_elements={
                    "stamps": [],
                    "signatures": [],
                    "tables": [],
                    "headers": [],
                    "metadata": {},
                },
                fallback_used=False,
                error_message=None,
                file_type=file_type,
            )

        except Exception as e:
            print(f"[WARN] MarkItDown failed: {e}")
            if file_type == "pdf":
                return None  # Fall back to LLM for PDFs
            # For non-PDF, return error
            return self._error_result(
                f"MarkItDown conversion failed: {e}",
                start_time,
                file_type,
            )

    def _process_pdf_with_llm(self, pdf_path: str) -> OCRResult:
        """
        Process PDF using LLM Vision OCR (fallback for scanned PDFs).
        Tries native PDF OCR first, then pdf2image per-page approach.
        """
        start_time = time.time()

        path = Path(pdf_path)
        if not path.exists():
            return self._error_result(
                f"PDF file not found: {pdf_path}", start_time, "pdf"
            )

        # Try native PDF OCR first (send PDF directly to LLM)
        native_result = self._try_native_pdf_ocr(pdf_path, start_time)
        if native_result is not None:
            return native_result

        # Fallback: pdf2image per-page approach
        if not PDF2IMAGE_AVAILABLE:
            if PYPDF2_AVAILABLE:
                return self._extract_pdf_text(pdf_path, start_time)
            return self._error_result(
                "Cannot process scanned PDF: pdf2image not installed.",
                start_time,
                "pdf",
            )

        try:
            images = convert_from_path(str(path), dpi=200)
            page_count = len(images)

            if page_count == 0:
                return self._error_result("PDF has no pages", start_time, "pdf")

            all_text = []
            all_markdown = []
            all_elements: DetectedElements = {
                "stamps": [],
                "signatures": [],
                "tables": [],
                "headers": [],
                "metadata": {},
            }
            total_confidence = 0.0
            fallback_used = True
            provider_used = ""

            for i, image in enumerate(images):
                print(f"[INFO] LLM Vision OCR page {i + 1}/{page_count}...")

                image_base64 = self._pil_to_base64(image)
                result = self._call_vision_llm(image_base64)

                if result.get("success"):
                    text_content = result.get("content", "")
                    markdown_content, metadata = self._parse_ocr_response(text_content)

                    all_text.append(f"--- Page {i + 1} ---\n{text_content}")
                    all_markdown.append(f"## Page {i + 1}\n\n{markdown_content}")

                    page_elements = self._extract_detected_elements(metadata)
                    all_elements["stamps"].extend(page_elements["stamps"])
                    all_elements["signatures"].extend(page_elements["signatures"])
                    all_elements["tables"].extend(page_elements["tables"])
                    all_elements["headers"].extend(page_elements["headers"])

                    if i == 0:
                        all_elements["metadata"] = page_elements["metadata"]

                    total_confidence += metadata.get("confidence", 0.8)
                    provider_used = result.get("provider", self.llm.current_provider_id)
                else:
                    error_detail = result.get("error", "")
                    if i == 0 and any(
                        kw in str(error_detail).lower()
                        for kw in [
                            "authentication",
                            "401",
                            "api key",
                            "unauthorized",
                            "user not found",
                        ]
                    ):
                        return self._error_result(
                            f"LLM 認證失敗: {error_detail}", start_time, "pdf"
                        )
                    all_text.append(f"--- Page {i + 1} ---\n[OCR Failed]")
                    all_markdown.append(f"## Page {i + 1}\n\n[OCR Failed]")
                    total_confidence += 0.0

            processing_time = int((time.time() - start_time) * 1000)
            avg_confidence = total_confidence / page_count if page_count > 0 else 0.0

            return OCRResult(
                success=True,
                provider_used=provider_used,
                text_content="\n\n".join(all_text),
                markdown_content="\n\n".join(all_markdown),
                confidence=avg_confidence,
                processing_time_ms=processing_time,
                page_count=page_count,
                detected_elements=all_elements,
                fallback_used=fallback_used,
                error_message=None,
                file_type="pdf",
            )

        except Exception as e:
            return self._error_result(f"LLM Vision OCR failed: {e}", start_time, "pdf")

    def process_image(self, image_path: str) -> OCRResult:
        """
        Process a single image file with LLM Vision OCR.
        Images always require LLM since MarkItDown can't extract text from images.

        Args:
            image_path: Path to image file (PNG, JPG, etc.)

        Returns:
            OCRResult with extracted text and metadata
        """
        start_time = time.time()

        path = Path(image_path)
        if not path.exists():
            return self._error_result(
                f"Image file not found: {image_path}", start_time, "image"
            )

        try:
            image_base64 = self._encode_image(path)
            result = self._call_vision_llm(image_base64)

            if result.get("success"):
                processing_time = int((time.time() - start_time) * 1000)

                text_content = result.get("content", "")
                markdown_content, metadata = self._parse_ocr_response(text_content)
                detected_elements = self._extract_detected_elements(metadata)

                return OCRResult(
                    success=True,
                    provider_used=result.get("provider", self.llm.current_provider_id),
                    text_content=text_content,
                    markdown_content=markdown_content,
                    confidence=metadata.get("confidence", 0.8),
                    processing_time_ms=processing_time,
                    page_count=1,
                    detected_elements=detected_elements,
                    fallback_used=False,
                    error_message=None,
                    file_type="image",
                )
            else:
                return self._error_result(
                    f"LLM Vision OCR failed: {result.get('error', 'unknown')}",
                    start_time,
                    "image",
                )

        except Exception as e:
            return self._error_result(
                f"Image processing failed: {str(e)}", start_time, "image"
            )

    # --------------------------------------------------------
    # Legacy Format Processing (win32com)
    # --------------------------------------------------------

    def _process_legacy_format(self, file_path: str, file_type: str) -> OCRResult:
        """Process legacy Office formats (.doc, .xls, .ppt) using win32com."""
        start_time = time.time()

        if not WIN32COM_AVAILABLE:
            return self._error_result(
                "pywin32 not installed. Cannot process legacy format. "
                "Please convert to modern format (.docx, .xlsx, .pptx).",
                start_time,
                file_type,
            )

        path = Path(file_path)
        if not path.exists():
            return self._error_result(
                f"File not found: {file_path}", start_time, file_type
            )

        try:
            pythoncom.CoInitialize()

            if file_type == "word_legacy":
                text_content = self._extract_doc_legacy(path)
            elif file_type == "excel_legacy":
                text_content = self._extract_xls_legacy(path)
            elif file_type == "powerpoint_legacy":
                text_content = self._extract_ppt_legacy(path)
            else:
                return self._error_result(
                    f"Unknown legacy format: {file_type}", start_time, file_type
                )

            pythoncom.CoUninitialize()

            processing_time = int((time.time() - start_time) * 1000)

            return OCRResult(
                success=True,
                provider_used="win32com",
                text_content=text_content,
                markdown_content=text_content,
                confidence=1.0,
                processing_time_ms=processing_time,
                page_count=1,
                detected_elements={
                    "stamps": [],
                    "signatures": [],
                    "tables": [],
                    "headers": [],
                    "metadata": {},
                },
                fallback_used=False,
                error_message=None,
                file_type=file_type,
            )

        except Exception as e:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            return self._error_result(
                f"Legacy format processing failed: {e}", start_time, file_type
            )

    def _extract_doc_legacy(self, path: Path) -> str:
        """Extract text from .doc using win32com."""
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = None
        try:
            doc = word.Documents.Open(str(path.absolute()))
            text = doc.Content.Text
            return text
        finally:
            try:
                if doc:
                    doc.Close()
            except Exception:
                pass
            try:
                word.Quit()
            except Exception:
                pass

    def _extract_xls_legacy(self, path: Path) -> str:
        """Extract text from .xls using win32com."""
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        wb = None
        try:
            wb = excel.Workbooks.Open(str(path.absolute()))

            all_text = []
            for sheet in wb.Sheets:
                used_range = sheet.UsedRange
                if used_range:
                    values = used_range.Value
                    if values:
                        all_text.append(f"### Sheet: {sheet.Name}\n")
                        if isinstance(values, tuple):
                            for row in values:
                                if isinstance(row, tuple):
                                    cells = [str(c) if c else "" for c in row]
                                    all_text.append("| " + " | ".join(cells) + " |")
                                else:
                                    all_text.append(str(row))

            return "\n".join(all_text)
        finally:
            try:
                if wb:
                    wb.Close()
            except Exception:
                pass
            try:
                excel.Quit()
            except Exception:
                pass

    def _extract_ppt_legacy(self, path: Path) -> str:
        """Extract text from .ppt using win32com."""
        ppt = win32com.client.Dispatch("PowerPoint.Application")
        presentation = None
        try:
            presentation = ppt.Presentations.Open(
                str(path.absolute()), WithWindow=False
            )

            all_text = []
            for i, slide in enumerate(presentation.Slides, 1):
                slide_text = [f"## Slide {i}"]
                for shape in slide.Shapes:
                    if shape.HasTextFrame:
                        if shape.TextFrame.HasText:
                            slide_text.append(shape.TextFrame.TextRange.Text)
                all_text.append("\n\n".join(slide_text))

            return "\n\n---\n\n".join(all_text)
        finally:
            try:
                if presentation:
                    presentation.Close()
            except Exception:
                pass
            try:
                ppt.Quit()
            except Exception:
                pass

    # --------------------------------------------------------
    # Helper Methods
    # --------------------------------------------------------

    def _encode_image(self, path: Path) -> str:
        """Encode image file to base64"""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _pil_to_base64(self, image: Any) -> str:
        """Convert PIL Image to base64"""
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _try_native_pdf_ocr(
        self, pdf_path: str, start_time: float
    ) -> Optional[OCRResult]:
        """
        Try sending PDF directly to LLM (native PDF OCR).
        Works with Gemini models that support PDF file input.
        Returns None if native PDF OCR is not supported by current provider.
        """
        try:
            with open(pdf_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

            response = self.llm.pdf_completion(
                prompt=self.system_prompt,
                pdf_base64=pdf_base64,
                model=self.model_name or None,
            )

            if response is None:
                return None

            if "[ERROR]" in response.get("content", ""):
                print(f"[WARN] Native PDF OCR failed: {response.get('content')}")
                return None

            text_content = response.get("content", "")
            markdown_content, metadata = self._parse_ocr_response(text_content)
            detected_elements = self._extract_detected_elements(metadata)
            processing_time = int((time.time() - start_time) * 1000)

            page_count = 1
            if PYPDF2_AVAILABLE:
                try:
                    with open(pdf_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        page_count = len(reader.pages)
                except Exception:
                    pass

            return OCRResult(
                success=True,
                provider_used=response.get("provider", self.llm.current_provider_id),
                text_content=text_content,
                markdown_content=markdown_content,
                confidence=metadata.get("confidence", 0.9),
                processing_time_ms=processing_time,
                page_count=page_count,
                detected_elements=detected_elements,
                fallback_used=True,
                error_message=None,
                file_type="pdf",
            )

        except Exception as e:
            print(f"[WARN] Native PDF OCR error: {e}, falling back to pdf2image...")
            return None

    def _call_vision_llm(self, image_base64: str) -> dict:
        """
        Call Vision LLM with image.

        Args:
            image_base64: Base64-encoded image data

        Returns:
            Dict with 'success', 'content', 'provider' keys
        """
        try:
            response = self.llm.vision_completion(
                prompt=self.system_prompt,
                image_base64=image_base64,
                model=self.model_name or None,
            )

            if "[ERROR]" in response.get("content", ""):
                return {"success": False, "error": response.get("content")}

            return {
                "success": True,
                "content": response.get("content", ""),
                "provider": response.get("provider", self.llm.current_provider_id),
                "fallback_used": response.get("fallback_used", False),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_pdf_text(self, pdf_path: str, start_time: float) -> OCRResult:
        """Extract text from PDF using PyPDF2 (last resort fallback)"""
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages.append(f"## Page {i + 1}\n\n{text}")

            text_content = "\n\n".join(pages)
            processing_time = int((time.time() - start_time) * 1000)

            return OCRResult(
                success=True,
                provider_used="PyPDF2",
                text_content=text_content,
                markdown_content=text_content,
                confidence=0.7,
                processing_time_ms=processing_time,
                page_count=len(reader.pages),
                detected_elements={
                    "stamps": [],
                    "signatures": [],
                    "tables": [],
                    "headers": [],
                    "metadata": {},
                },
                fallback_used=True,
                error_message=None,
                file_type="pdf",
            )
        except Exception as e:
            return self._error_result(
                f"PDF text extraction failed: {e}", start_time, "pdf"
            )

    def _parse_ocr_response(self, text: str) -> tuple[str, dict]:
        """
        Parse OCR response to extract markdown and metadata.

        Args:
            text: Raw OCR response text

        Returns:
            Tuple of (markdown_content, metadata_dict)
        """
        json_pattern = r"```json\s*([\s\S]*?)\s*```"
        matches = re.findall(json_pattern, text)

        metadata = {}
        markdown_content = text

        if matches:
            try:
                metadata = json.loads(matches[-1])
                markdown_content = re.sub(json_pattern, "", text).strip()
            except json.JSONDecodeError:
                pass

        # Post-process: strip hallucinated image URLs from LLM output
        markdown_content = re.sub(
            r"!\[([^\]]*)\]\(https?://[^\)]+\)",
            r"[\1]",
            markdown_content,
        )
        markdown_content = re.sub(
            r"!\[([^\]]*)\]\([^\)]+\)",
            r"[\1]",
            markdown_content,
        )

        return markdown_content, metadata

    def _extract_detected_elements(self, metadata: dict) -> DetectedElements:
        """Extract detected elements from metadata."""
        stamps = []
        if "stamps_detected" in metadata:
            stamps = [
                {"name": s, "confidence": 0.9} for s in metadata["stamps_detected"]
            ]

        signatures = []
        if "signatures_detected" in metadata:
            signatures = [
                {"name": s, "confidence": 0.9} for s in metadata["signatures_detected"]
            ]

        return DetectedElements(
            stamps=stamps,
            signatures=signatures,
            tables=[],
            headers=[],
            metadata={
                "document_id": metadata.get("document_id", ""),
                "version": metadata.get("version", ""),
                "effective_date": metadata.get("effective_date", ""),
            },
        )

    def _error_result(
        self, error_message: str, start_time: float, file_type: str = "unknown"
    ) -> OCRResult:
        """Create error OCRResult"""
        processing_time = int((time.time() - start_time) * 1000)

        return OCRResult(
            success=False,
            provider_used="none",
            text_content="",
            markdown_content="",
            confidence=0.0,
            processing_time_ms=processing_time,
            page_count=0,
            detected_elements={
                "stamps": [],
                "signatures": [],
                "tables": [],
                "headers": [],
                "metadata": {},
            },
            fallback_used=False,
            error_message=error_message,
            file_type=file_type,
        )


# ============================================================
# Convenience Functions
# ============================================================


def process_document(
    file_path: str, llm_provider_manager=None, model_name: str = ""
) -> OCRResult:
    """
    Process a document file (PDF, Image, Word, Excel, PowerPoint, Text).

    Args:
        file_path: Path to document file
        llm_provider_manager: Optional LLMProviderManager instance
        model_name: Model to use for LLM fallback (empty string uses provider default)

    Returns:
        OCRResult with extracted text and metadata
    """
    processor = VisionOCRProcessor(llm_provider_manager)
    return processor.process_file(file_path, model_name=model_name)


def get_supported_extensions() -> list[str]:
    """Get list of supported file extensions."""
    return list(SUPPORTED_EXTENSIONS.keys())


def is_supported_file(file_path: str) -> bool:
    """Check if file type is supported."""
    suffix = Path(file_path).suffix.lower()
    return suffix in SUPPORTED_EXTENSIONS


# ============================================================
# Module Test
# ============================================================

if __name__ == "__main__":
    print("MarkItDown-First Document Processor Test")
    print("=" * 60)
    print(f"Supported extensions: {get_supported_extensions()}")
    print()
    print("Library availability:")
    print(f"  - MARKITDOWN: {MARKITDOWN_AVAILABLE}")
    print(f"  - PDF2IMAGE: {PDF2IMAGE_AVAILABLE}")
    print(f"  - PIL: {PIL_AVAILABLE}")
    print(f"  - PYPDF2: {PYPDF2_AVAILABLE}")
    print(f"  - PYPDF: {PYPDF_AVAILABLE}")
    print(f"  - WIN32COM: {WIN32COM_AVAILABLE}")
    print()

    test_files = [
        "test.png",
        "test.pdf",
        "test.docx",
        "test.xlsx",
        "test.pptx",
        "uploads/test.pdf",
        "uploads/test.docx",
    ]

    for test_file in test_files:
        if Path(test_file).exists():
            print(f"\nProcessing: {test_file}")
            result = process_document(test_file)
            print(f"  Success: {result['success']}")
            print(f"  Provider: {result['provider_used']}")
            print(f"  File Type: {result['file_type']}")
            print(f"  Time: {result['processing_time_ms']}ms")
            if result["success"]:
                print(f"  Content length: {len(result['markdown_content'])} chars")
            else:
                print(f"  Error: {result['error_message']}")
