import json
from pathlib import Path

from apps.desktop.main import main
from packages.core.models import Evidence, Paper, PipelineStatus, Question
from packages.exporters import paper_document


def test_build_paper_cli_generates_all_printables(tmp_path: Path, capsys) -> None:
    paper = Paper(id="p3-cli", title="CLI mock paper")
    question = Question(
        id="q-p3-cli-1",
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
    paper_json = tmp_path / "paper.json"
    paper_json.write_text(
        json.dumps(paper_document(paper, [question]), ensure_ascii=False),
        encoding="utf-8",
    )
    destination = tmp_path / "bundle"
    assert main(
        [
            "build-paper",
            "--paper-json",
            str(paper_json),
            "--paper-output",
            str(destination),
            "--paper-formats",
            "pdf",
            "html",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["questions"] == 1
    assert (destination / "01_wrong_paper.pdf").is_file()
    assert (destination / "03_explanation_book.html").is_file()
