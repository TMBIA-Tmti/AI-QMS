"""AI-QMS — PDF Watermark Utility
==================================

Adds image-based watermarks to PDF documents for controlled distribution.
Supports adjustable opacity (顏色深淺), rotation angle (角度), and tile count (數量).

Usage:
    from src.utils.watermark import add_watermark_to_pdf, generate_watermark_preview

    # Full watermark application
    output_path = add_watermark_to_pdf(
        pdf_path="uploads/QP-001.pdf",
        watermark_image_path="uploads/watermark.png",
        opacity=0.15,
        angle=45,
        tile_count=3,
    )

    # Preview with adjustable parameters (generates a 1-page sample)
    preview_path = generate_watermark_preview(
        watermark_image_path="uploads/watermark.png",
        opacity=0.15,
        angle=45,
        tile_count=3,
    )

Dependencies: pypdf, reportlab, Pillow (all in requirements.txt)
"""

import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default watermark parameters
DEFAULT_OPACITY = 0.15
DEFAULT_ANGLE = 45
DEFAULT_TILE_COUNT = 3  # tiles per row/column

# Preview page size (A4)
_A4_WIDTH = 595.27
_A4_HEIGHT = 841.89


def _create_watermark_overlay_with_opacity(
    watermark_image_path: str,
    page_width: float,
    page_height: float,
    opacity: float = DEFAULT_OPACITY,
    angle: float = DEFAULT_ANGLE,
    tile_count: int = DEFAULT_TILE_COUNT,
) -> bytes:
    """Create watermark overlay PDF with proper opacity support.

    Uses Pillow to pre-process the watermark image with desired opacity,
    then tiles it onto a PDF page via reportlab.
    """
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    # Pre-process image: apply opacity via Pillow
    img = Image.open(watermark_image_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Apply opacity by modifying alpha channel
    r, g, b, a = img.split()
    # Scale alpha by opacity factor
    a = a.point(lambda x: int(x * opacity))
    img = Image.merge("RGBA", (r, g, b, a))

    # Save to temporary buffer
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    img_w, img_h = img.size
    aspect = img_h / img_w if img_w else 1

    # Create PDF canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    # Calculate tile size
    margin_ratio = 0.1
    tile_w = page_width / tile_count * (1 - margin_ratio)
    tile_h = tile_w * aspect

    max_tile_h = page_height / tile_count * (1 - margin_ratio)
    if tile_h > max_tile_h:
        tile_h = max_tile_h
        tile_w = tile_h / aspect

    spacing_x = page_width / tile_count
    spacing_y = page_height / tile_count

    for row in range(tile_count + 1):
        for col in range(tile_count + 1):
            cx = spacing_x * col + spacing_x / 2
            cy = spacing_y * row + spacing_y / 2

            c.saveState()
            c.translate(cx, cy)
            c.rotate(angle)

            img_buf.seek(0)
            c.drawImage(
                ImageReader(img_buf),
                -tile_w / 2,
                -tile_h / 2,
                width=tile_w,
                height=tile_h,
                mask="auto",
                preserveAspectRatio=True,
                anchor="c",
            )
            c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()


def add_watermark_to_pdf(
    pdf_path: str,
    watermark_image_path: str,
    opacity: float = DEFAULT_OPACITY,
    angle: float = DEFAULT_ANGLE,
    tile_count: int = DEFAULT_TILE_COUNT,
    output_path: Optional[str] = None,
) -> str:
    """Add watermark to every page of a PDF document.

    Args:
        pdf_path: Path to the source PDF file.
        watermark_image_path: Path to the watermark image (PNG/JPG).
        opacity: Watermark opacity 0.0-1.0. Default 0.15.
        angle: Rotation angle in degrees. Default 45.
        tile_count: Tiles per row/column. Default 3.
        output_path: Output PDF path. If None, auto-generates beside source.

    Returns:
        Path to the watermarked PDF file.
    """
    from pypdf import PdfReader, PdfWriter

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not Path(watermark_image_path).exists():
        raise FileNotFoundError(f"Watermark image not found: {watermark_image_path}")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        # Get page dimensions
        media_box = page.mediabox
        pw = float(media_box.width)
        ph = float(media_box.height)

        # Create watermark overlay matching this page's size
        overlay_bytes = _create_watermark_overlay_with_opacity(
            watermark_image_path,
            pw,
            ph,
            opacity=opacity,
            angle=angle,
            tile_count=tile_count,
        )
        overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
        overlay_page = overlay_reader.pages[0]

        # Merge watermark onto original page
        page.merge_page(overlay_page)
        writer.add_page(page)

    # Determine output path
    if not output_path:
        src = Path(pdf_path)
        output_path = str(src.parent / f"{src.stem}_watermarked{src.suffix}")

    with open(output_path, "wb") as f:
        writer.write(f)

    logger.info(f"Watermarked PDF saved: {output_path}")
    return output_path


def generate_watermark_preview(
    watermark_image_path: str,
    opacity: float = DEFAULT_OPACITY,
    angle: float = DEFAULT_ANGLE,
    tile_count: int = DEFAULT_TILE_COUNT,
    output_path: Optional[str] = None,
    sample_pdf_path: Optional[str] = None,
) -> str:
    """Generate a preview PDF showing watermark effect for user adjustment.

    If sample_pdf_path is provided, watermarks the first page of that PDF.
    Otherwise, creates an A4 page with sample text to demonstrate the effect.

    Args:
        watermark_image_path: Path to the watermark image.
        opacity: Opacity 0.0-1.0.
        angle: Rotation angle in degrees.
        tile_count: Tiles per row/column.
        output_path: Output path. If None, auto-generates in data/exports/.
        sample_pdf_path: Optional existing PDF to use as base for preview.

    Returns:
        Path to the preview PDF.
    """
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4

    exports_dir = Path("data/exports")
    exports_dir.mkdir(parents=True, exist_ok=True)

    if not output_path:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        output_path = str(exports_dir / f"{ts}_watermark_preview.pdf")

    if sample_pdf_path and Path(sample_pdf_path).exists():
        # Use first page of existing PDF as base
        src_reader = PdfReader(sample_pdf_path)
        page = src_reader.pages[0]
        pw = float(page.mediabox.width)
        ph = float(page.mediabox.height)
    else:
        # Create a sample A4 page with placeholder text
        pw, ph = A4
        sample_buf = io.BytesIO()
        c = rl_canvas.Canvas(sample_buf, pagesize=A4)
        c.setFont("Helvetica", 14)
        c.drawString(72, ph - 72, "AI-QMS Watermark Preview")
        c.setFont("Helvetica", 11)

        # Draw sample content lines
        y = ph - 120
        sample_lines = [
            "This is a preview page to demonstrate the watermark effect.",
            "您可以調整以下參數：",
            f"  • 顏色深淺 (Opacity): {opacity}",
            f"  • 角度 (Angle): {angle}°",
            f"  • 數量 (Tile Count): {tile_count} x {tile_count}",
            "",
            "調整滿意後，確認即可套用至所有上傳文件。",
            "After adjustment, confirm to apply to all uploaded documents.",
        ]
        for line in sample_lines:
            c.drawString(72, y, line)
            y -= 20

        c.showPage()
        c.save()
        sample_buf.seek(0)
        src_reader = PdfReader(sample_buf)
        page = src_reader.pages[0]

    # Create watermark overlay
    overlay_bytes = _create_watermark_overlay_with_opacity(
        watermark_image_path,
        pw,
        ph,
        opacity=opacity,
        angle=angle,
        tile_count=tile_count,
    )
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))

    # Merge
    page.merge_page(overlay_reader.pages[0])

    writer = PdfWriter()
    writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)

    logger.info(
        f"Watermark preview generated: {output_path} "
        f"(opacity={opacity}, angle={angle}, tiles={tile_count})"
    )
    return output_path


def convert_to_pdf_for_viewing(
    file_path: str, output_path: Optional[str] = None
) -> Optional[str]:
    """Convert a document to PDF format for inline viewing.

    Supports: .pdf (passthrough), .docx, .doc, .xlsx, .xls, .pptx, .ppt, .txt, .md, .csv
    Images (.png, .jpg, etc.) are embedded into a PDF page.

    Args:
        file_path: Path to the source file.
        output_path: Optional output path. Auto-generated if None.

    Returns:
        Path to the PDF file, or None if conversion failed.
    """
    src = Path(file_path)
    suffix = src.suffix.lower()

    if not src.exists():
        logger.error(f"File not found for PDF conversion: {file_path}")
        return None

    exports_dir = Path("data/exports")
    exports_dir.mkdir(parents=True, exist_ok=True)

    if not output_path:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        output_path = str(exports_dir / f"{ts}_{src.stem}_view.pdf")

    # PDF passthrough
    if suffix == ".pdf":
        return file_path  # Already PDF, no conversion needed

    # Images → embed into PDF
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".tif", ".bmp"}
    if suffix in image_exts:
        try:
            from PIL import Image
            from reportlab.pdfgen import canvas as rl_canvas

            img = Image.open(file_path)
            img_w, img_h = img.size
            # Scale to fit A4 with margins
            max_w = _A4_WIDTH - 72  # 0.5 inch margin each side
            max_h = _A4_HEIGHT - 72
            scale = min(max_w / img_w, max_h / img_h, 1.0)
            draw_w = img_w * scale
            draw_h = img_h * scale

            page_w = max(draw_w + 72, _A4_WIDTH)
            page_h = max(draw_h + 72, _A4_HEIGHT)

            c = rl_canvas.Canvas(output_path, pagesize=(page_w, page_h))
            x = (page_w - draw_w) / 2
            y = (page_h - draw_h) / 2
            c.drawImage(
                file_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True
            )
            c.showPage()
            c.save()
            return output_path
        except Exception as e:
            logger.error(f"Image to PDF conversion failed: {e}")
            return None

    # Text files → render as PDF
    text_exts = {".txt", ".md", ".csv", ".rtf"}
    if suffix in text_exts:
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            content = src.read_text(encoding="utf-8", errors="replace")
            c = rl_canvas.Canvas(output_path, pagesize=A4)

            font_name = "Helvetica"
            cjk_font_paths = [
                "C:/Windows/Fonts/msjh.ttc",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/yugothm.ttc",
                "/System/Library/Fonts/PingFang.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            ]
            for fpath in cjk_font_paths:
                if Path(fpath).exists():
                    try:
                        pdfmetrics.registerFont(TTFont("CJKFont", fpath))
                        font_name = "CJKFont"
                        break
                    except Exception:
                        continue

            c.setFont(font_name, 10)
            y = A4[1] - 50
            for line in content.split("\n"):
                if y < 50:
                    c.showPage()
                    c.setFont(font_name, 10)
                    y = A4[1] - 50
                c.drawString(40, y, line[:120])
                y -= 14
            c.showPage()
            c.save()
            return output_path
        except Exception as e:
            logger.error(f"Text to PDF conversion failed: {e}")
            return None

    # Office formats → try python-docx/openpyxl/python-pptx conversion
    # For complex Office conversions, we return None and fall back to
    # showing the Markdown content inline instead.
    # Full Office→PDF conversion would require LibreOffice/unoconv which
    # may not be available in all environments.
    if suffix in {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}:
        logger.info(
            f"Office file {suffix} — using original if PDF, else Markdown fallback"
        )
        return None

    logger.warning(f"Unsupported format for PDF conversion: {suffix}")
    return None


def get_document_level(doc_id: str, doc_type: str, title: str, content: str) -> str:
    """Determine document hierarchy level for view/download decision.

    Returns one of: '1', '2', '3', '4', 'external', 'other'

    Levels:
        1: 品質手冊 (Quality Manual)
        2: 程序書 (Procedure/SOP)
        3: 作業指導書 (Work Instruction)
        4: 表單 (Form)
        external: 外來法規文件
        other: 無法判定
    """
    content_lower = (content[:3000] if content else "").lower()
    title_lower = (title or "").lower()

    # Check if external regulatory document
    # Use same classification logic as _classify_document
    regulatory_title_patterns = [
        "iso ",
        "iec ",
        "21 cfr",
        "mdr 2017",
        "regulation",
        "cns ",
        "astm",
        "gb/t",
        "jis ",
        "en ",
        "bs en",
        "mdsap",
        "mdd",
    ]
    if any(pat in title_lower for pat in regulatory_title_patterns):
        return "external"

    # Check doc_type prefix mapping
    prefix = doc_id.split("-")[0].upper() if "-" in doc_id else ""

    # Level 4: Forms
    if doc_type == "FORM" or prefix == "FM":
        return "4"

    # Level 1: Quality Manual
    manual_kw = ["quality manual", "品質手冊", "品質政策", "管理代表", "qms scope"]
    if prefix == "QM" or any(
        kw in content_lower or kw in title_lower for kw in manual_kw
    ):
        return "1"

    # Level 2: Procedure/SOP
    if doc_type == "SOP" or prefix in ("QP", "SOP"):
        return "2"

    # Level 3: Work Instruction
    if doc_type == "WI" or prefix == "WI":
        return "3"

    # Fallback: content-based detection
    wi_kw = ["work instruction", "作業指導", "作業說明", "作業步驟"]
    form_kw = ["form", "表單", "checklist", "檢查表", "template"]
    proc_kw = ["procedure", "程序書", "本程序", "流程"]

    if any(kw in content_lower or kw in title_lower for kw in form_kw):
        return "4"
    if any(kw in content_lower or kw in title_lower for kw in wi_kw):
        return "3"
    if any(kw in content_lower or kw in title_lower for kw in proc_kw):
        return "2"

    return "other"
