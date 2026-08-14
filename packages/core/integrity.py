"""Deterministic completeness checks and workflow transitions."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AttemptState, PipelineStatus, Question


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class IntegrityReport:
    status: PipelineStatus
    issues: tuple[IntegrityIssue, ...]

    @property
    def complete(self) -> bool:
        return not self.issues


def assess_question(question: Question, confidence_threshold: float = 0.80) -> IntegrityReport:
    issues: list[IntegrityIssue] = []

    def add(code: str, message: str) -> None:
        if not any(issue.code == code for issue in issues):
            issues.append(IntegrityIssue(code, message))

    if question.user_answer is None:
        add("missing_user_answer", "未采集用户答案（空列表可明确表示未作答）")
    if not question.official_answer:
        add("missing_official_answer", "缺少粉笔正确答案")
    if not (question.official_explanation_md or "").strip():
        add("missing_official_explanation", "缺少粉笔官方解析")
    if not question.stem_md.strip():
        add("missing_stem", "缺少题干")

    labels = [option.label for option in question.options]
    if len(labels) != len(set(labels)):
        add("duplicate_option_labels", "选项标签重复")
    if question.official_answer and labels and not set(question.official_answer).issubset(labels):
        add("official_answer_not_in_options", "正确答案不在已识别选项中")

    expected_correct: bool | None = None
    if question.user_answer is not None and question.official_answer:
        expected_correct = set(question.user_answer) == set(question.official_answer)
    if question.is_correct is not None and expected_correct is not None and question.is_correct != expected_correct:
        add("answer_result_conflict", "用户答案、正确答案与作答结果矛盾")
    if question.attempt_state == AttemptState.UNANSWERED and question.user_answer:
        add("attempt_state_conflict", "未作答状态却存在用户答案")
    if question.ocr_confidence is not None and question.ocr_confidence < confidence_threshold:
        add("low_ocr_confidence", "OCR 置信度低")
    if question.parse_confidence is not None and question.parse_confidence < confidence_threshold:
        add("low_parse_confidence", "字段解析置信度低")
    if not question.evidence.question_frames:
        add("missing_question_evidence", "缺少题目原始截图证据")
    if not question.evidence.analysis_frames:
        add("missing_analysis_evidence", "缺少答案解析原始截图证据")
    if question.official_answer and not question.evidence.field_regions.get("official_answer"):
        add("missing_official_answer_evidence", "官方答案未关联原始截图区域")
    if question.official_explanation_md and not question.evidence.field_regions.get(
        "official_explanation_md"
    ):
        add("missing_official_explanation_evidence", "官方解析未关联原始截图区域")

    status = PipelineStatus.NEEDS_REVIEW if issues else PipelineStatus.VERIFIED
    return IntegrityReport(status=status, issues=tuple(issues))


def transition_question(question: Question, confidence_threshold: float = 0.80) -> IntegrityReport:
    """Assess and mutate status/reasons in one explicit state-machine step."""
    report = assess_question(question, confidence_threshold)
    question.verification_status = report.status
    question.review_reasons = [issue.code for issue in report.issues]
    return report
