from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import OcrResult


@runtime_checkable
class OcrEngine(Protocol):
    """Stable adapter boundary for local and future OCR implementations."""

    def recognize(self, image_path: Path) -> OcrResult:
        ...
