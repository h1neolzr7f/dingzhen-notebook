from __future__ import annotations

import json
import zipfile
from pathlib import Path

from packages.core.models import Option, Paper, Question, QuestionType
from packages.mistake_package import (
    export_mistake_package,
    import_mistake_package,
    package_from_questions,
    validate_package,
)
from packages.review import build_review_plan, export_knowledge_mindmap


def _sample() -> tuple[Paper, list[Question]]:
    paper = Paper(id="paper_x", title="演示卷", platform="fenbi", total_questions=2)
    questions = [
        Question(
            id="q1",
            paper_id="paper_x",
            sequence=1,
            question_type=QuestionType.SINGLE_CHOICE,
            stem_md="1+1=?",
            options=[Option(label="A", content_md="1"), Option(label="B", content_md="2")],
            user_answer=["A"],
            official_answer=["B"],
            is_correct=False,
            official_explanation_md="应为 2",
            official_knowledge_points=["算术"],
        ),
        Question(
            id="q2",
            paper_id="paper_x",
            sequence=2,
            stem_md="已掌握题",
            user_answer=["A"],
            official_answer=["A"],
            is_correct=True,
            official_explanation_md="正确",
            official_knowledge_points=["算术"],
        ),
    ]
    return paper, questions


def test_package_roundtrip_and_validation(tmp_path: Path) -> None:
    paper, questions = _sample()
    document = package_from_questions(paper, questions, only_wrong=True)
    assert document["format"] == "jinzhi-mistake-package"
    assert len(document["mistakes"]) == 1
    assert validate_package(document) == []

    zip_path = tmp_path / "pkg.zip"
    export_mistake_package(paper, questions, zip_path, only_wrong=True)
    with zipfile.ZipFile(zip_path) as archive:
        assert "manifest.json" in archive.namelist()
        loaded = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert loaded["mistakes"][0]["question"]["text"] == "1+1=?"

    media_dir = tmp_path / "media"
    paper2, questions2, _ = import_mistake_package(zip_path, extract_media_to=media_dir)
    assert paper2.platform == "jinzhi-import"
    assert len(questions2) == 1
    assert questions2[0].official_answer == ["B"]
    assert questions2[0].user_answer == ["A"]
    assert questions2[0].is_correct is False


def test_review_plan_tracks_and_mindmap(tmp_path: Path) -> None:
    _, questions = _sample()
    plan = build_review_plan(questions)
    assert plan["summary"]["first_pass"] >= 1
    assert plan["summary"]["mastered"] >= 1
    mind = export_knowledge_mindmap(questions, tmp_path / "map.md")
    text = mind.read_text(encoding="utf-8")
    assert "算术" in text
    assert "知识点复习导图" in text
