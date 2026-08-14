from __future__ import annotations

from .base import OcrEngine
from .mock import MockOcrEngine
from .paddle import PaddleOcrEngine


def create_ocr_engine(name: str = "mock") -> OcrEngine:
    normalized = name.strip().casefold()
    if normalized == "mock":
        return MockOcrEngine()
    if normalized in {"paddle", "paddleocr"}:
        return PaddleOcrEngine()
    raise ValueError(f"Unknown OCR engine: {name}. Choose 'mock' or 'paddle'.")
