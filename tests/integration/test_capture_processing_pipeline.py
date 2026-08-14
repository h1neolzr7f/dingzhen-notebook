from __future__ import annotations

from pathlib import Path

from apps.desktop.capture_controller import CaptureController, CaptureFrame
from apps.desktop.pipeline import process_capture_frames
from packages.core import SQLiteRepository
from packages.ocr import MockOcrEngine


class CallbackAndReturnService:
    def __init__(self, frame: Path) -> None:
        self.frame = frame

    def start(self, on_frame=None):
        value = CaptureFrame(sequence=0, path=self.frame)
        if on_frame:
            on_frame(value)
        return [value]

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass


def test_capture_controller_does_not_duplicate_callback_frames(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"not-used")
    controller = CaptureController(CallbackAndReturnService(frame), output_dir=tmp_path)
    snapshot = controller.start(wait=True)
    assert snapshot.frames_captured == 1
    assert [item.path for item in controller.frames] == [frame]


def test_capture_frames_flow_through_ocr_database_analysis_and_paper_exports(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    frame = root / "samples" / "golden" / "ordinary_single_choice" / "screen_01.png"
    result = process_capture_frames(
        [frame],
        engine=MockOcrEngine(),
        workspace=tmp_path,
        database=tmp_path / "fenbi.db",
        paper_id="paper_e2e",
        paper_title="端到端验收卷",
    )

    repository = SQLiteRepository(tmp_path / "fenbi.db")
    questions = repository.list_questions("paper_e2e")
    assert len(questions) == 1
    question = questions[0]
    assert question.user_answer == ["B"]
    assert question.official_answer == ["C"]
    assert question.official_explanation_md == "模拟证据"
    assert question.evidence.question_frames
    assert question.evidence.analysis_frames
    assert result.paper_json.is_file()
    assert result.paper_markdown.is_file()
    assert result.analysis_markdown.is_file()
    assert result.explanation_book.is_file()
