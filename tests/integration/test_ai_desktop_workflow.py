from __future__ import annotations

from pathlib import Path

from apps.desktop.ai_workflow import run_ai_analysis
from apps.desktop.pipeline import process_capture_frames
from packages.ai import MockAIModelAdapter
from packages.core import SQLiteRepository
from packages.ocr import MockOcrEngine


def test_ai_workflow_is_exposed_and_cannot_overwrite_official_fields(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    frame = root / "samples" / "golden" / "ordinary_single_choice" / "screen_01.png"
    process_capture_frames(
        [frame], engine=MockOcrEngine(), workspace=tmp_path, database=tmp_path / "db.sqlite", paper_id="paper_ai"
    )
    adapter = MockAIModelAdapter(
        response={
            "error_analysis": "漏看限定条件",
            "official_answer": ["A"],
            "official_explanation_md": "恶意覆盖",
        },
    )
    result = run_ai_analysis(
        tmp_path / "db.sqlite",
        "paper_ai",
        output_root=tmp_path / "exports",
        adapter=adapter,
    )
    question = SQLiteRepository(tmp_path / "db.sqlite").list_questions("paper_ai")[0]
    assert question.official_answer == ["C"]
    assert question.official_explanation_md == "模拟证据"
    assert "official_answer" not in question.ai_analysis["deep_analysis"]
    assert result.json_path.is_file()
    assert result.markdown_path.is_file()
