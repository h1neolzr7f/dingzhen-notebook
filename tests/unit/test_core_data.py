from __future__ import annotations

import json

from packages.core import (
    Evidence,
    EvidenceRegion,
    Option,
    Paper,
    PipelineStatus,
    Question,
    QuestionType,
    SQLiteRepository,
    assess_question,
)
from packages.exporters import export_paper_json, export_paper_markdown
from packages.parser import finalize_parsed_question


def complete_question(**overrides):
    values = {
        "id": "q1",
        "paper_id": "p1",
        "sequence": 1,
        "question_type": QuestionType.SINGLE_CHOICE,
        "stem_md": "下列正确的是？",
        "options": [Option(label="A", content_md="甲"), Option(label="B", content_md="乙")],
        "user_answer": ["a"],
        "official_answer": ["B"],
        "is_correct": False,
        "official_explanation_md": "B 符合题意。",
        "evidence": Evidence(
            question_frames=["captures/q1.png"],
            analysis_frames=["captures/q1a.png"],
            field_regions={
                "official_answer": [EvidenceRegion(image="captures/q1a.png", bbox=(10, 20, 30, 40))],
                "official_explanation_md": [EvidenceRegion(image="captures/q1a.png", bbox=(10, 50, 300, 400))],
            },
        ),
        "ocr_confidence": 0.96,
        "parse_confidence": 0.93,
    }
    values.update(overrides)
    return Question(**values)


def test_missing_any_mandatory_study_field_is_reviewable_not_rejected():
    for field in ("user_answer", "official_answer", "official_explanation_md"):
        question = complete_question(**{field: None})
        report = assess_question(question)
        assert question.verification_status == PipelineStatus.NEEDS_REVIEW
        assert report.status == PipelineStatus.NEEDS_REVIEW
        assert f"missing_{field.removesuffix('_md')}" in {issue.code for issue in report.issues}


def test_explicit_unanswered_is_not_missing_user_answer():
    question = complete_question(user_answer=[], is_correct=False)
    _, report = finalize_parsed_question(question)
    assert "missing_user_answer" not in {issue.code for issue in report.issues}
    assert report.status == PipelineStatus.VERIFIED


def test_integrity_catches_answer_conflict_and_missing_evidence():
    question = complete_question(is_correct=True, evidence=Evidence())
    report = assess_question(question)
    assert {issue.code for issue in report.issues} >= {
        "answer_result_conflict", "missing_question_evidence", "missing_analysis_evidence"
    }


def test_sqlite_repository_upserts_and_builds_review_queue(tmp_path):
    repo = SQLiteRepository(tmp_path / "study.db")
    repo.create_schema()
    repo.upsert_paper(Paper(id="p1", title="模拟卷", total_questions=1))
    question = complete_question(official_explanation_md=None)
    repo.upsert_question(question)
    repo.upsert_question(question)
    assert len(repo.list_questions("p1")) == 1
    assert [item.id for item in repo.review_queue()] == ["q1"]
    assert repo.get_question("q1").review_reasons == ["missing_official_explanation"]


def test_json_and_markdown_exports_accept_repository(tmp_path):
    repo = SQLiteRepository(tmp_path / "study.db")
    repo.create_schema()
    paper = Paper(id="p1", title="模拟卷", total_questions=1, answered_questions=1)
    repo.upsert_paper(paper)
    question = complete_question()
    repo.upsert_question(question)

    json_path = export_paper_json(repo, "p1", tmp_path / "paper.json")
    md_path = export_paper_markdown(repo, "p1", tmp_path / "paper_ai.md")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    assert document["questions"][0]["user_answer"] == ["A"]
    assert document["questions"][0]["official_answer"] == ["B"]
    assert document["questions"][0]["official_explanation_md"] == "B 符合题意。"
    assert "- 用户答案：A" in markdown
    assert "- 粉笔正确答案：B" in markdown
    assert "## 粉笔官方解析" in markdown and "B 符合题意。" in markdown
    assert "captures/q1a.png" in markdown


def test_exporters_accept_models_directly(tmp_path):
    paper = Paper(id="p1", title="模型导出")
    question = complete_question()
    path = export_paper_json(paper, [question], tmp_path / "direct.json")
    assert json.loads(path.read_text(encoding="utf-8"))["paper"]["id"] == "p1"
