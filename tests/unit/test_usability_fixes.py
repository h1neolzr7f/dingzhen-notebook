from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from packages.ai import AIConfigurationError, LocalHTTPAIModelAdapter
from packages.core import new_paper_id, parse_choice_answers, safe_paper_id
from packages.mistake_package.codec import _read_zip_member
from packages.ocr import OcrLine, OcrResult, parse_question_fields


def test_choice_answers_ignore_separators() -> None:
    assert parse_choice_answers("A B") == ["A", "B"]
    assert parse_choice_answers("A,B") == ["A", "B"]
    assert parse_choice_answers("未作答") == []
    assert parse_choice_answers("") is None
    assert parse_choice_answers("A") == ["A"]


def test_paper_id_rejects_path_escape() -> None:
    assert safe_paper_id("paper_ok-1") == "paper_ok-1"
    assert new_paper_id("paper").startswith("paper_")
    with pytest.raises(ValueError):
        safe_paper_id("../secret")
    with pytest.raises(ValueError):
        safe_paper_id("a/b")


def test_parser_accepts_spaced_multiple_choice() -> None:
    draft = parse_question_fields(
        OcrResult(
            Path("q.png"),
            (
                OcrLine("题干", 0.9),
                OcrLine("你的答案：A, C", 0.9),
                OcrLine("正确答案：A C", 0.9),
                OcrLine("官方解析：多选", 0.9),
            ),
            "mock",
        )
    )
    assert draft.user_answer == ["A", "C"]
    assert draft.official_answer == ["A", "C"]


def test_local_http_adapter_rejects_unknown_path() -> None:
    with pytest.raises(AIConfigurationError):
        LocalHTTPAIModelAdapter("http://127.0.0.1:11434/admin")


def test_zip_member_rejects_oversize(tmp_path: Path) -> None:
    zip_path = tmp_path / "big.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", "{}")
    with zipfile.ZipFile(zip_path) as archive:
        data = _read_zip_member(archive, "manifest.json")
        assert data == b"{}"
