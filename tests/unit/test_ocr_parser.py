from pathlib import Path

from packages.ocr import MockOcrEngine, OcrLine, OcrResult, parse_question_fields


def test_parser_keeps_three_required_answers_separate_with_evidence():
    result = OcrResult(
        Path("q1.png"),
        (
            OcrLine("1. 下列说法正确的是？", 0.98, (10, 10, 300, 35)),
            OcrLine("A. 甲", 0.99, (10, 50, 100, 75)),
            OcrLine("B. 乙", 0.99, (10, 80, 100, 105)),
            OcrLine("你的答案：A", 0.96, (10, 120, 150, 145)),
            OcrLine("正确答案：B", 0.97, (10, 150, 150, 175)),
            OcrLine("官方解析：乙符合题意。", 0.95, (10, 180, 300, 205)),
            OcrLine("其余选项不符合题意。", 0.94, (10, 210, 300, 235)),
        ),
        "mock",
    )

    draft = parse_question_fields(result)

    assert draft.user_answer == ["A"]
    assert draft.official_answer == ["B"]
    assert draft.official_explanation_md == "乙符合题意。\n其余选项不符合题意。"
    assert draft.options == {"A": "甲", "B": "乙"}
    assert draft.verification_status == "pending_review"
    assert draft.evidence["official_answer"][0].image_path == "q1.png"
    assert draft.evidence["official_answer"][0].boxes == ((10, 150, 150, 175),)


def test_missing_official_content_is_never_guessed():
    result = OcrResult(
        Path("question-only.png"),
        (OcrLine("题干内容", 0.9), OcrLine("你的答案：C", 0.8)),
        "mock",
    )

    draft = parse_question_fields(result)

    assert draft.user_answer == ["C"]
    assert draft.official_answer is None
    assert draft.official_explanation_md == ""
    assert draft.verification_status == "needs_review"
    assert "official_answer" in draft.missing_required_fields
    assert "official_explanation_md" in draft.missing_required_fields


def test_explicit_unanswered_state_counts_as_observed_user_answer():
    result = OcrResult(
        Path("unanswered.png"),
        (
            OcrLine("题干内容", 0.9),
            OcrLine("你的答案：未作答", 0.95),
            OcrLine("正确答案：A", 0.96),
            OcrLine("官方解析：理由", 0.92),
        ),
        "mock",
    )

    draft = parse_question_fields(result)

    assert draft.user_answer == []
    assert "user_answer" not in draft.missing_required_fields
    assert draft.verification_status == "pending_review"
    draft.reviewed = True
    assert draft.verification_status == "verified"


def test_uncaptured_user_answer_is_none_not_unanswered():
    result = OcrResult(
        Path("missing-user.png"),
        (
            OcrLine("题干内容", 0.9),
            OcrLine("正确答案：A", 0.96),
            OcrLine("官方解析：理由", 0.92),
        ),
        "mock",
    )

    draft = parse_question_fields(result)

    assert draft.user_answer is None
    assert "user_answer" in draft.missing_required_fields
    assert draft.to_dict()["user_answer"] is None


def test_mock_engine_reads_utf8_sidecar(tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"not-read-by-mock")
    sidecar = tmp_path / "screen.png.ocr.json"
    sidecar.write_text(
        '{"lines":[{"text":"正确答案：D","confidence":0.91,"bbox":[1,2,3,4]}]}',
        encoding="utf-8",
    )

    result = MockOcrEngine().recognize(image)

    assert result.text == "正确答案：D"
    assert result.lines[0].bbox == (1, 2, 3, 4)
    assert result.confidence == 0.91
