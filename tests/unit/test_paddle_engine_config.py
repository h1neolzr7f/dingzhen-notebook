from __future__ import annotations

import sys
from types import SimpleNamespace

from packages.ocr.paddle import PaddleOcrEngine


def test_windows_disables_mkldnn_by_default(monkeypatch) -> None:
    received: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            received.update(kwargs)

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOCR))
    monkeypatch.setattr(sys, "platform", "win32")

    PaddleOcrEngine()

    assert received["enable_mkldnn"] is False


def test_explicit_mkldnn_setting_is_preserved(monkeypatch) -> None:
    received: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            received.update(kwargs)

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOCR))
    monkeypatch.setattr(sys, "platform", "win32")

    PaddleOcrEngine(enable_mkldnn=True)

    assert received["enable_mkldnn"] is True
