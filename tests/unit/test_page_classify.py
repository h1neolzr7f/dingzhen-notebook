from pathlib import Path

from apps.desktop.pipeline import auto_assign_captured_images, process_capture_frames
from apps.desktop.workflow import DesktopWorkflow
from packages.image_processing import ImportedImage
from packages.ocr import MockOcrEngine, classify_ocr_text
from datetime import datetime, timezone


def test_classify_detects_complete_last_question() -> None:
    page = classify_ocr_text(
        "第8题\n你的答案 A\n正确答案 B\n答案解析 理由\n知识点 逻辑\n本题用时 12秒"
    )
    assert page.question_number == 8
    assert page.page_kind == "analysis"
    assert page.complete
    assert page.paper_ended
    assert not page.has_next_question


def test_classify_keeps_going_when_next_exists() -> None:
    page = classify_ocr_text("第2题 你的答案 A 正确答案 B 答案解析 理由 知识点 下一题")
    assert page.complete
    assert page.has_next_question
    assert not page.paper_ended


def test_process_capture_returns_reviewable_workflow(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    frame = root / "samples" / "golden" / "ordinary_single_choice" / "screen_01.png"
    result = process_capture_frames(
        [frame],
        engine=MockOcrEngine(),
        workspace=tmp_path,
        database=tmp_path / "fenbi.db",
        paper_id="paper_flow",
        paper_title="流程卷",
    )
    assert result.groups
    assert result.workflow.drafts
    assert result.workflow.images
    assert all(image.group_id != "unassigned" for image in result.workflow.images)


def test_auto_assign_groups_question_then_analysis(tmp_path: Path) -> None:
    engine = MockOcrEngine()
    workflow = DesktopWorkflow(engine)
    now = datetime.now(timezone.utc)
    first = tmp_path / "q.png"
    second = tmp_path / "a.png"
    first.write_bytes(b"x")
    second.write_bytes(b"y")
    (tmp_path / "q.png.ocr.json").write_text(
        '{"lines":[{"text":"第1题 题干","confidence":0.9}]}',
        encoding="utf-8",
    )
    (tmp_path / "a.png.ocr.json").write_text(
        '{"lines":[{"text":"你的答案 A 正确答案 B 答案解析 理由 知识点 下一题","confidence":0.9}]}',
        encoding="utf-8",
    )
    workflow.images = [
        ImportedImage(first, first, "a", 1, 1, now, 0),
        ImportedImage(second, second, "b", 1, 1, now, 1),
    ]
    groups = auto_assign_captured_images(workflow)
    assert groups == ("q001",)
    assert [image.page_kind for image in workflow.images] == ["question", "analysis"]
