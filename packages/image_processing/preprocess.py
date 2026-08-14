"""Conservative OCR preprocessing. Raw screenshots are never modified."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass(frozen=True, slots=True)
class PreprocessOptions:
    grayscale: bool = True
    autocontrast: bool = True
    median_filter_size: int = 0
    threshold: int | None = None
    scale: float = 1.0


def preprocess_image(
    source: str | Path,
    destination: str | Path,
    options: PreprocessOptions | None = None,
) -> Path:
    """Create a derived OCR image while preserving the original screenshot."""

    options = options or PreprocessOptions()
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        if options.scale != 1.0:
            image = image.resize(
                (max(1, round(image.width * options.scale)), max(1, round(image.height * options.scale))),
                Image.Resampling.LANCZOS,
            )
        if options.grayscale:
            image = image.convert("L")
        if options.autocontrast:
            image = ImageOps.autocontrast(image)
        if options.median_filter_size:
            size = options.median_filter_size
            if size < 3 or size % 2 == 0:
                raise ValueError("median_filter_size must be an odd integer >= 3")
            image = image.filter(ImageFilter.MedianFilter(size))
        if options.threshold is not None:
            if not 0 <= options.threshold <= 255:
                raise ValueError("threshold must be between 0 and 255")
            if image.mode != "L":
                image = ImageOps.grayscale(image)
            image = image.point(lambda value: 255 if value >= options.threshold else 0)
        image = ImageEnhance.Sharpness(image).enhance(1.1)
        image.save(output)
    return output
