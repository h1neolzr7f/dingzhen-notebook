from packages.analysis import (
    analyze_paper,
    filter_repeated_wrong_questions,
    filter_risk_questions,
    filter_special_questions,
    filter_wrong_questions,
    get_error_tags,
    set_error_tags,
)
from packages.core.models import Evidence, Paper, PipelineStatus, Question


def _question(paper_id: str, sequence: int, *, correct: bool | None, section: str = "判断推理", stem: str = "题目") -> Question:
    return Question(
        id=f"q-{paper_id}-{sequence}",
        paper_id=paper_id,
        sequence=sequence,
        section=section,
        stem_md=stem,
        user_answer=[] if correct is None else ["A"],
        official_answer=["A"],
        is_correct=correct,
        official_explanation_md="官方解析",
        official_knowledge_points=["定义判断"],
        evidence=Evidence(question_frames=["question.png"], analysis_frames=["analysis.png"]),
        verification_status=PipelineStatus.VERIFIED,
    )


def test_report_has_overall_module_knowledge_and_tags() -> None:
    paper = Paper(id="p1", title="Mock")
    questions = [_question("p1", 1, correct=False), _question("p1", 2, correct=True, section="资料分析")]
    set_error_tags(questions[0], ["knowledge_gap"])
    report = analyze_paper(paper, questions)
    assert report.total_questions == 2
    assert report.correct_questions == 1
    assert report.accuracy_rate == 0.5
    assert set(report.module_stats) == {"判断推理", "资料分析"}
    assert report.knowledge_point_stats["定义判断"].wrong == 1
    assert report.error_tag_stats == {"KNOWLEDGE_GAP": 1}
    assert get_error_tags(questions[0]) == ["KNOWLEDGE_GAP"]


def test_filters_are_explicit_and_repeated_detection_does_not_guess() -> None:
    first = _question("p1", 1, correct=False, stem="相同题干")
    second = _question("p2", 1, correct=False, stem="相同题干")
    unknown = _question("p1", 2, correct=None)
    unknown.verification_status = PipelineStatus.NEEDS_REVIEW
    assert filter_wrong_questions([first, unknown]) == [first]
    assert unknown in filter_risk_questions([first, unknown])
    assert filter_special_questions([first, second], knowledge_points=["定义判断"]) == [first, second]
    assert {item.id for item in filter_repeated_wrong_questions([first, second])} == {first.id, second.id}
