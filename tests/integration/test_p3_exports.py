from pathlib import Path

from packages.core.models import Evidence, Paper, PipelineStatus, Question
from packages.exporters import export_analysis_json, export_analysis_markdown
from packages.analysis import analyze_paper
from packages.paper_builder import build_paper_bundle


def _fixture() -> tuple[Paper, list[Question]]:
    paper = Paper(id="p3", title="P3 mock paper")
    question = Question(
        id="q-p3-1",
        paper_id=paper.id,
        sequence=1,
        section="模块",
        stem_md="Which option?",
        user_answer=["B"],
        official_answer=["C"],
        is_correct=False,
        official_explanation_md="官方解释必须来自 Question",
        official_knowledge_points=["知识点"],
        evidence=Evidence(question_frames=["q.png"], analysis_frames=["a.png"]),
        verification_status=PipelineStatus.VERIFIED,
    )
    return paper, [question]


def test_p3_bundle_has_three_printables_and_provenance(tmp_path: Path) -> None:
    paper, questions = _fixture()
    result = build_paper_bundle(paper, questions, tmp_path, formats=("pdf", "html"))
    assert {path.name for path in result.paths()} >= {
        "01_wrong_paper.pdf",
        "02_answer_sheet.pdf",
        "03_explanation_book.pdf",
    }
    assert (tmp_path / "01_wrong_paper.pdf").read_bytes().startswith(b"%PDF")
    explanation = (tmp_path / "03_explanation_book.html").read_text(encoding="utf-8")
    assert "C" in explanation
    assert "官方解释必须来自 Question" in explanation
    assert 'data-source="Question.official_answer"' in explanation


def test_needs_review_is_not_exported_as_verified(tmp_path: Path) -> None:
    paper, questions = _fixture()
    questions[0].verification_status = PipelineStatus.NEEDS_REVIEW
    report = analyze_paper(paper, questions)
    assert report.verified is False
    build_paper_bundle(paper, questions, tmp_path, formats=("html",))
    text = (tmp_path / "03_explanation_book.html").read_text(encoding="utf-8")
    assert "verified=false" in text
    assert "尚未验证" in text


def test_analysis_exports_are_json_and_markdown(tmp_path: Path) -> None:
    paper, questions = _fixture()
    report = analyze_paper(paper, questions)
    json_path = export_analysis_json(report, tmp_path / "analysis.json")
    md_path = export_analysis_markdown(report, tmp_path / "analysis.md")
    assert '"accuracy": 0.0' in json_path.read_text(encoding="utf-8")
    assert "模块统计" in md_path.read_text(encoding="utf-8")
