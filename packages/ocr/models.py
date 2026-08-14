"""OCR transport models independent of any vendor SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BoundingBox = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    bbox: BoundingBox | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("OCR confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "confidence": self.confidence, "bbox": self.bbox}


@dataclass(frozen=True, slots=True)
class OcrResult:
    image_path: Path
    lines: tuple[OcrLine, ...]
    engine: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    @property
    def confidence(self) -> float:
        return sum(line.confidence for line in self.lines) / len(self.lines) if self.lines else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "image_path": str(self.image_path),
            "engine": self.engine,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "lines": [line.to_dict() for line in self.lines],
        }
