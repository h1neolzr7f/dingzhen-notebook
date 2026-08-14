"""Deterministic OCR engine for development and golden tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .models import OcrLine, OcrResult


class MockOcrEngine:
    """Read configured text or a ``<image>.ocr.json`` sidecar file."""

    def __init__(self, results: Mapping[str, str | Sequence[OcrLine]] | None = None) -> None:
        self._results = dict(results or {})

    def recognize(self, image_path: Path) -> OcrResult:
        path = Path(image_path)
        configured = self._results.get(str(path)) or self._results.get(path.name)
        if configured is not None:
            lines = self._coerce(configured)
            return OcrResult(path, lines, "mock")

        sidecar = Path(f"{path}.ocr.json")
        if sidecar.exists():
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            raw_lines = payload.get("lines", payload) if isinstance(payload, dict) else payload
            lines = tuple(
                OcrLine(
                    text=str(item["text"]),
                    confidence=float(item.get("confidence", 1.0)),
                    bbox=tuple(item["bbox"]) if item.get("bbox") else None,
                )
                if isinstance(item, dict)
                else OcrLine(str(item), 1.0)
                for item in raw_lines
            )
            return OcrResult(path, lines, "mock-sidecar")
        return OcrResult(path, (), "mock", ("No mock OCR text or sidecar was found.",))

    @staticmethod
    def _coerce(value: str | Sequence[OcrLine]) -> tuple[OcrLine, ...]:
        if isinstance(value, str):
            return tuple(OcrLine(line, 1.0) for line in value.splitlines() if line.strip())
        return tuple(value)
