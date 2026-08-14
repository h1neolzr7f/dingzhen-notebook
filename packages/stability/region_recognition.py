"""Local OCR re-recognition that preserves raw screenshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from packages.ocr import OcrEngine, OcrResult


@dataclass(frozen=True, slots=True)
class RegionRecognition:
    source: Path
    derived_image: Path
    bbox: tuple[int, int, int, int]
    result: OcrResult


def recognize_region(
    engine: OcrEngine,
    image_path: str | Path,
    bbox: tuple[int, int, int, int],
    *,
    derived_dir: str | Path = Path("data") / "derived-ocr",
) -> RegionRecognition:
    source = Path(image_path)
    with Image.open(source) as opened:
        width, height = opened.size
        x1, y1, x2, y2 = bbox
        clamped = (max(0, x1), max(0, y1), min(width, x2), min(height, y2))
        if clamped[2] <= clamped[0] or clamped[3] <= clamped[1]:
            raise ValueError("OCR region is outside the source image")
        crop = opened.crop(clamped)
        destination = Path(derived_dir) / f"{source.stem}_{clamped[0]}_{clamped[1]}_{clamped[2]}_{clamped[3]}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        crop.save(destination)
    result = engine.recognize(destination)
    return RegionRecognition(source, destination, clamped, result)

