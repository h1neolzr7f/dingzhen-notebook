"""Pluggable OCR engines and Fenbi question field parsing."""

from .base import OcrEngine
from .factory import create_ocr_engine
from .mock import MockOcrEngine
from .models import BoundingBox, OcrLine, OcrResult
from .paddle import PaddleOcrEngine, PaddleOcrUnavailable
from .page_classify import PageClass, classify_ocr_text, load_page_markers
from .parser import FieldEvidence, ParsedQuestionDraft, parse_question_fields

__all__ = [
    "BoundingBox",
    "FieldEvidence",
    "MockOcrEngine",
    "OcrEngine",
    "OcrLine",
    "OcrResult",
    "PaddleOcrEngine",
    "PaddleOcrUnavailable",
    "ParsedQuestionDraft",
    "PageClass",
    "classify_ocr_text",
    "load_page_markers",
    "create_ocr_engine",
    "parse_question_fields",
]
