from pathlib import Path

import fitz
import pytest

from packages.exporters import pdf_exporter


def test_pdf_preserves_extractable_chinese_text(tmp_path: Path) -> None:
    output = pdf_exporter.html_to_pdf(
        "<h1>错题卷</h1><p>粉笔正确答案：C</p><p>粉笔官方解析：本题考查定义判断。</p>",
        tmp_path / "chinese.pdf",
    )
    with fitz.open(output) as document:
        text = "".join(page.get_text() for page in document)
    assert "粉笔正确答案" in text
    assert "粉笔官方解析" in text
    assert "本题考查定义判断" in text


def test_missing_unicode_renderer_fails_instead_of_writing_question_marks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_exporter, "_reportlab_pdf", lambda lines, destination: False)
    with pytest.raises(RuntimeError, match="Unicode"):
        pdf_exporter.html_to_pdf("<p>粉笔官方解析</p>", tmp_path / "broken.pdf")
    assert not (tmp_path / "broken.pdf").exists()
