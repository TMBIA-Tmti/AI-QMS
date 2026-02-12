"""
AI-QMS Phase 1 - OCR Processing Module
Vision-First OCR Pipeline with LLM fallback
"""

from .vision_ocr import VisionOCRProcessor, OCRResult

__all__ = ["VisionOCRProcessor", "OCRResult"]
