from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from packages.core.integrity import assess_question
from packages.core.models import Paper, PipelineStatus, Question
from packages.core.repository import SQLiteRepository
from apps.desktop.workflow import DesktopWorkflow
from packages.ocr import MockOcrEngine


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "samples" / "golden"


def load_cases() -> list[tuple[Path, dict]]:
    return [
        (path.parent, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(GOLDEN.glob("*/expected.json"))
    ]


def test_every_golden_case_has_valid_png_and_expected_json() -> None:
    cases = load_cases()
    assert cases, "Golden 测试集不能为空"
    for case_dir, expected in cases:
        assert expected["case_id"] == case_dir.name
        frames = sorted(case_dir.glob("*.png"))
        assert frames, f"{case_dir.name} 缺少截图"
        for frame in frames:
            with Image.open(frame) as image:
                image.verify()
            with Image.open(frame) as image:
                assert image.size == (1080, 1920)


def test_question_cases_match_integrity_policy() -> None:
    for _, expected in load_cases():
        if expected["question"] is None:
            continue
        question = Question.model_validate(expected["question"])
        report = assess_question(question)
        assert report.status.value == expected["expected_status"], expected["case_id"]
        assert [issue.code for issue in report.issues] == expected["expected_review_reasons"]


def test_verified_questions_have_three_required_sources_and_evidence() -> None:
    for _, expected in load_cases():
        if expected["expected_status"] != PipelineStatus.VERIFIED.value:
            continue
        question = Question.model_validate(expected["question"])
        assert question.user_answer is not None
        assert question.official_answer
        assert question.official_explanation_md
        assert question.evidence.question_frames
        assert question.evidence.analysis_frames
        for relative in {
            *question.evidence.question_frames,
            *question.evidence.analysis_frames,
        }:
            assert (ROOT / relative).is_file(), relative


def test_duplicate_fixture_has_identical_content_hashes() -> None:
    case_dir = GOLDEN / "duplicate_frame"
    hashes = {
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(case_dir.glob("*.png"))
    }
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    assert len(hashes) == expected["expected_unique_frames"]
    assert len(list(case_dir.glob("*.png"))) - len(hashes) == expected["expected_duplicate_frames"]


def test_sqlite_round_trip_is_idempotent_and_preserves_official_fields(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "integration.db")
    repository.create_schema()
    repository.upsert_paper(Paper(id="paper_fixture_001", title="离线模拟试卷"))

    source = json.loads(
        (GOLDEN / "verified_wrong" / "expected.json").read_text(encoding="utf-8")
    )["question"]
    question = Question.model_validate(source)
    repository.upsert_question(question)
    repository.upsert_question(question)

    rows = repository.list_questions("paper_fixture_001")
    assert len(rows) == 1
    restored = rows[0]
    assert restored.user_answer == ["B"]
    assert restored.official_answer == ["C"]
    assert restored.official_explanation_md == source["official_explanation_md"]
    assert restored.is_correct is False
    assert restored.evidence.analysis_frames == source["evidence"]["analysis_frames"]


def test_mock_ocr_runs_complete_single_screen_workflow() -> None:
    case_dir = GOLDEN / "verified_wrong"
    workflow = DesktopWorkflow(MockOcrEngine())
    workflow.import_paths([case_dir / "screen_01.png"])
    workflow.assign([0], "q001", "question")
    draft = workflow.recognize_group("q001")
    assert draft.user_answer == ["B"]
    assert draft.official_answer == ["C"]
    assert draft.official_explanation_md.startswith("甲未通过")
    assert draft.missing_required_fields == []


def test_mock_ocr_merges_interrupted_question_and_analysis_frames() -> None:
    case_dir = GOLDEN / "interrupted_resume"
    workflow = DesktopWorkflow(MockOcrEngine())
    workflow.import_paths([case_dir / "screen_01.png", case_dir / "screen_02.png"])
    workflow.assign([0], "q005", "question")
    workflow.assign([1], "q005", "analysis")
    draft = workflow.recognize_group("q005")
    assert draft.user_answer == ["C"]
    assert draft.official_answer == ["C"]
    assert draft.official_explanation_md == "题干已直接给出同比增长 10%，对应 C。"
    assert draft.missing_required_fields == []
