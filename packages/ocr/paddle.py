"""Optional PaddleOCR 3.x adapter with compatibility for common result shapes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

from .models import OcrLine, OcrResult


class PaddleOcrUnavailable(RuntimeError):
    pass


class PaddleOcrEngine:
    def __init__(self, language: str = "ch", **kwargs: Any) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise PaddleOcrUnavailable(
                "PaddleOCR is optional. Install it with: pip install -e .[ocr]"
            ) from exc
        options = {"lang": language, "use_doc_orientation_classify": False,
                   "use_doc_unwarping": False, "use_textline_orientation": False}
        # PaddleOCR 3.7.0 + PaddlePaddle 3.3.1 currently raises a PIR
        # ArrayAttribute conversion error in the Windows oneDNN path.  The
        # plain CPU kernels are stable and callers can still opt back in.
        if sys.platform.startswith("win"):
            options["enable_mkldnn"] = False
        options.update(kwargs)
        self._ocr = PaddleOCR(**options)

    def recognize(self, image_path: Path) -> OcrResult:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        if hasattr(self._ocr, "predict"):
            raw = self._ocr.predict(str(path))
        else:  # PaddleOCR 2.x compatibility
            raw = self._ocr.ocr(str(path), cls=False)
        lines = tuple(self._extract_lines(raw))
        warnings = () if lines else ("PaddleOCR returned no text.",)
        return OcrResult(path, lines, "paddleocr", warnings)

    def _extract_lines(self, raw: Any) -> Iterable[OcrLine]:
        for page in raw or []:
            payload = getattr(page, "json", None)
            if callable(payload):
                payload = payload()
            if isinstance(payload, dict):
                payload = payload.get("res", payload)
            elif hasattr(page, "res"):
                payload = page.res
            else:
                payload = page

            if isinstance(payload, dict) and "rec_texts" in payload:
                texts = payload.get("rec_texts", [])
                scores = payload.get("rec_scores", [0.0] * len(texts))
                boxes = payload.get("rec_boxes") or payload.get("dt_polys") or [None] * len(texts)
                for text, score, box in zip(texts, scores, boxes):
                    yield OcrLine(str(text), _score(score), _bbox(box))
                continue

            rows = payload or []
            if rows and isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list):
                rows = rows[0]
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                text_score = row[1]
                if isinstance(text_score, (list, tuple)) and len(text_score) >= 2:
                    yield OcrLine(str(text_score[0]), _score(text_score[1]), _bbox(row[0]))


def _score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _bbox(value: Any) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    try:
        points = list(value)
        if len(points) == 4 and all(not isinstance(point, (list, tuple)) for point in points):
            x1, y1, x2, y2 = (int(float(item)) for item in points)
            return x1, y1, x2, y2
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    except (TypeError, ValueError, IndexError):
        return None
