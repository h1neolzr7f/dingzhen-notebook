"""Release smoke test using the real PaddleOCR engine, not sidecar fixtures."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from packages.ocr import PaddleOcrEngine, parse_question_fields


def create_fixture(image_path: Path, font_path: Path) -> None:
    """Render an actual Chinese PNG containing every mandatory field."""

    image = Image.new("RGB", (1280, 1100), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 48)
    rows = (
        "模拟题干：下列说法正确的是？",
        "A. 选项甲",
        "B. 选项乙",
        "用户答案：B",
        "正确答案：A",
        "官方解析：选项甲符合题意。",
    )
    for index, row in enumerate(rows):
        draw.text((70, 70 + index * 150), row, font=font, fill="black")
    image.save(image_path)


def main() -> int:
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc"
    if not font_path.is_file():
        raise RuntimeError(f"Chinese release-test font is unavailable: {font_path}")

    # Generate pixels at runtime so this test cannot accidentally pass through
    # MockOcrEngine sidecars.  The four required semantic regions are all
    # rendered as ordinary screenshot-like Chinese text.
    with TemporaryDirectory(prefix="fenbi-real-ocr-") as temporary:
        image_path = Path(temporary) / "mandatory-fields.png"
        create_fixture(image_path, font_path)

        result = PaddleOcrEngine().recognize(image_path)
        draft = parse_question_fields(result)
    payload = {
        "engine": result.engine,
        "lines": len(result.lines),
        "confidence": result.confidence,
        "recognized_text": [line.text for line in result.lines],
        "user_answer": draft.user_answer,
        "official_answer": draft.official_answer,
        "official_explanation_md": draft.official_explanation_md,
        "missing": draft.missing_required_fields,
    }
    print(json.dumps(payload, ensure_ascii=False))
    # OCR quality is evaluated through the same hard completeness boundary as
    # production; no sidecar or MockOcrEngine is consulted here.
    return 0 if not draft.missing_required_fields else 1


if __name__ == "__main__":
    raise SystemExit(main())
