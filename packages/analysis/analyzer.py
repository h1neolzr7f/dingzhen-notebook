"""Deterministic statistics and selection helpers for P3.

This module works on the existing ``Paper``/``Question`` models and has no
network or model dependency.  Every value is either explicitly present on a
question or marked unknown; in particular, a ``NEEDS_REVIEW`` question is
never upgraded to ``VERIFIED`` by an analysis operation.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from packages.core.models import Paper, PipelineStatus, Question
from packages.core.repository import SQLiteRepository

from .models import AnalysisReport, ERROR_TAGS, Metric, TrendPoint

_MISSING = "未分类"


def resolve_questions(
    paper_or_repository: Paper | SQLiteRepository | Iterable[Question],
    questions_or_paper_id: Iterable[Question] | str | None = None,
) -> tuple[Paper | None, list[Question]]:
    """Resolve the convenient supported input forms.

    ``(Paper, questions)``, ``(repository, paper_id)`` and a bare iterable of
    questions are all accepted.  The last form is useful for offline tests.
    """

    if isinstance(paper_or_repository, SQLiteRepository):
        if not isinstance(questions_or_paper_id, str):
            raise TypeError("repository analysis requires a paper_id string")
        paper = paper_or_repository.get_paper(questions_or_paper_id)
        if paper is None:
            raise KeyError(f"paper does not exist: {questions_or_paper_id}")
        return paper, paper_or_repository.list_questions(paper.id)
    if isinstance(paper_or_repository, Paper):
        if questions_or_paper_id is None or isinstance(questions_or_paper_id, str):
            raise TypeError("Paper analysis requires an iterable of Question objects")
        return paper_or_repository, sorted(list(questions_or_paper_id), key=lambda q: (q.sequence, q.id))
    if questions_or_paper_id is not None:
        raise TypeError("a bare question iterable cannot be combined with a second argument")
    return None, sorted(list(paper_or_repository), key=lambda q: (q.paper_id, q.sequence, q.id))


def _answerable(question: Question) -> bool:
    # ``[]`` is the explicit unanswered state.  ``None`` means not captured.
    return question.user_answer is not None and bool(question.user_answer)


def _metric(key: str, questions: Iterable[Question]) -> Metric:
    result = Metric(key=key)
    for question in questions:
        result.total += 1
        if _answerable(question):
            result.answered += 1
            if question.is_correct is True:
                result.correct += 1
            elif question.is_correct is False:
                result.wrong += 1
            else:
                result.unknown += 1
        else:
            result.unknown += 1
    result.finish()
    return result


def _grouped_metrics(questions: Iterable[Question], field: str) -> dict[str, Metric]:
    groups: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        value = getattr(question, field, None)
        if isinstance(value, str):
            values = [value.strip()] if value.strip() else [_MISSING]
        elif field == "official_knowledge_points":
            values = [str(item).strip() for item in (value or []) if str(item).strip()] or [_MISSING]
        else:
            values = [_MISSING]
        for group in dict.fromkeys(values):
            groups[group].append(question)
    return {key: _metric(key, values) for key, values in sorted(groups.items())}


def _get_tag_values(question: Question) -> list[str]:
    """Read only user-editable tags from ``ai_analysis``.

    Older imported records may use one of several spellings, so this helper
    accepts each without treating any of it as official content.
    """

    data = question.ai_analysis or {}
    values: Any = data.get("error_tags", data.get("error_tag", data.get("tags", [])))
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    return [str(item).strip().upper() for item in values if str(item).strip()]


def get_error_tags(question: Question) -> list[str]:
    """Return normalized editable tags, retaining custom labels."""

    return list(dict.fromkeys(_get_tag_values(question)))


def set_error_tags(question: Question, tags: Iterable[str]) -> list[str]:
    """Set user-editable error tags on a question and return the normalized list.

    The operation preserves every existing key in ``ai_analysis`` and never
    writes ``official_answer`` or ``official_explanation_md``.
    """

    normalized = list(dict.fromkeys(str(tag).strip().upper() for tag in tags if str(tag).strip()))
    payload = dict(question.ai_analysis or {})
    payload["error_tags"] = normalized
    question.ai_analysis = payload
    return normalized


def add_error_tag(question: Question, tag: str) -> list[str]:
    return set_error_tags(question, [*get_error_tags(question), tag])


def remove_error_tag(question: Question, tag: str) -> list[str]:
    target = str(tag).strip().upper()
    return set_error_tags(question, [item for item in get_error_tags(question) if item != target])


class ErrorTagStore:
    """Tiny editable tag store for a UI or batch editor.

    ``apply`` writes only to ``Question.ai_analysis['error_tags']``.  A store
    is intentionally in-memory; callers can persist the changed Question via
    ``SQLiteRepository.upsert_question``.
    """

    def __init__(self, questions: Iterable[Question] = ()) -> None:
        self._tags: dict[str, list[str]] = {question.id: get_error_tags(question) for question in questions}

    def get(self, question_id: str) -> list[str]:
        return list(self._tags.get(question_id, []))

    def set(self, question_id: str, tags: Iterable[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(tag).strip().upper() for tag in tags if str(tag).strip()))
        self._tags[question_id] = normalized
        return list(normalized)

    def add(self, question_id: str, tag: str) -> list[str]:
        return self.set(question_id, [*self.get(question_id), tag])

    def remove(self, question_id: str, tag: str) -> list[str]:
        target = str(tag).strip().upper()
        return self.set(question_id, [item for item in self.get(question_id) if item != target])

    def apply(self, question: Question) -> Question:
        if question.id in self._tags:
            set_error_tags(question, self._tags[question.id])
        return question

    def apply_all(self, questions: Iterable[Question]) -> list[Question]:
        return [self.apply(question) for question in questions]


def question_key(question: Question) -> str:
    """Build a cross-paper key for repeated-question detection."""

    stem = re.sub(r"\s+", " ", (question.stem_md or "").strip().lower())
    option_parts: list[str] = []
    for item in question.options:
        content = re.sub(r"\s+", " ", item.content_md.strip().lower())
        option_parts.append(f"{item.label}:{content}")
    options = "|".join(option_parts)
    return f"{stem}\n{options}" if stem or options else question.id


def filter_wrong_questions(questions: Iterable[Question], *, verified_only: bool = False) -> list[Question]:
    """Select explicit wrong answers without inferring missing answers."""

    result = [question for question in questions if question.is_correct is False]
    if verified_only:
        result = [question for question in result if is_verified(question)]
    return sorted(result, key=lambda q: (q.sequence, q.id))


def _history_wrong_count(question: Question) -> int:
    data = question.ai_analysis or {}
    for key in ("wrong_attempts", "wrong_count", "repeat_count"):
        try:
            value = int(data.get(key, 0))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    history = data.get("attempt_history", data.get("history", []))
    if isinstance(history, (list, tuple)):
        return sum(1 for item in history if isinstance(item, dict) and item.get("is_correct") is False)
    return 0


def filter_repeated_wrong_questions(questions: Iterable[Question]) -> list[Question]:
    """Select questions wrong on more than one recorded occurrence.

    Repetition can be explicit in ``ai_analysis`` or be observed when the
    same normalized stem appears in multiple supplied papers.
    """

    values = list(questions)
    groups: dict[str, list[Question]] = defaultdict(list)
    for question in values:
        if question.is_correct is False:
            groups[question_key(question)].append(question)
    selected: list[Question] = []
    for question in values:
        repeated = len(groups.get(question_key(question), [])) > 1 or _history_wrong_count(question) > 1
        if repeated and question.is_correct is False:
            selected.append(question)
        elif question.is_correct is False and bool((question.ai_analysis or {}).get("repeat_wrong")):
            selected.append(question)
    unique: dict[str, Question] = {question.id: question for question in selected}
    return sorted(unique.values(), key=lambda q: (q.paper_id, q.sequence, q.id))


def risk_score(question: Question) -> float:
    """Return a transparent 0..1 risk score used by risk filters."""

    score = 0.0
    if question.is_correct is False:
        score += 0.55
    if question.is_correct is None or not _answerable(question):
        score += 0.20
    if question.verification_status == PipelineStatus.NEEDS_REVIEW:
        # An unverified record is itself a material review risk, even when no
        # wrong answer has been recorded yet.
        score += 0.30
    confidence = [item for item in (question.ocr_confidence, question.parse_confidence) if item is not None]
    if confidence and min(confidence) < 0.8:
        score += 0.15
    if _history_wrong_count(question) > 1 or bool((question.ai_analysis or {}).get("repeat_wrong")):
        score += 0.20
    return min(1.0, score)


def filter_risk_questions(
    questions: Iterable[Question], *, threshold: float = 0.5, verified_only: bool = False
) -> list[Question]:
    result = [question for question in questions if risk_score(question) >= threshold]
    if verified_only:
        result = [question for question in result if is_verified(question)]
    return sorted(result, key=lambda q: (-risk_score(q), q.sequence, q.id))


def filter_special_questions(
    questions: Iterable[Question],
    *,
    knowledge_points: Iterable[str] | None = None,
    section: str | None = None,
    tags: Iterable[str] | None = None,
    question_type: str | None = None,
) -> list[Question]:
    """Filter a practice set by knowledge point/module/tag/type."""

    points = {str(item).strip() for item in (knowledge_points or ()) if str(item).strip()}
    wanted_tags = {str(item).strip().upper() for item in (tags or ()) if str(item).strip()}
    result: list[Question] = []
    for question in questions:
        if section and (question.section or "") != section:
            continue
        if question_type and getattr(question.question_type, "value", question.question_type) != question_type:
            continue
        if points and not points.intersection(question.official_knowledge_points):
            continue
        if wanted_tags and not wanted_tags.intersection(get_error_tags(question)):
            continue
        result.append(question)
    return sorted(result, key=lambda q: (q.sequence, q.id))


def is_verified(question: Question) -> bool:
    return question.verification_status in {PipelineStatus.VERIFIED, PipelineStatus.EXPORTED}


def _date_value(paper: Paper) -> str | None:
    value = paper.completed_at or paper.started_at
    return value.isoformat() if isinstance(value, datetime) else None


def _paper_point(paper: Paper, questions: Sequence[Question]) -> TrendPoint:
    metric = _metric(paper.id, questions)
    return TrendPoint(
        paper_id=paper.id,
        title=paper.title,
        date=_date_value(paper),
        total=metric.total,
        answered=metric.answered,
        correct=metric.correct,
        accuracy=metric.accuracy,
        score=paper.score,
    )


def build_trend(
    papers: Iterable[tuple[Paper, Iterable[Question]]] | Iterable[Paper],
    question_lookup: dict[str, Iterable[Question]] | None = None,
) -> list[TrendPoint]:
    """Build chronological points from papers and their questions.

    Accepts either ``[(paper, questions), ...]`` or ``[paper, ...]`` with a
    lookup mapping paper id to questions.
    """

    points: list[TrendPoint] = []
    for item in papers:
        if isinstance(item, tuple):
            paper, questions = item
        else:
            paper = item
            if question_lookup is None:
                raise TypeError("question_lookup is required when passing papers only")
            questions = question_lookup.get(paper.id, [])
        points.append(_paper_point(paper, list(questions)))
    return sorted(points, key=lambda point: (point.date or "", point.paper_id))


def analyze_questions(
    questions: Iterable[Question], *, paper: Paper | None = None, trend: Iterable[TrendPoint] = ()
) -> AnalysisReport:
    values = sorted(list(questions), key=lambda q: (q.sequence, q.id))
    overall = _metric(paper.id if paper else "all", values)
    report = AnalysisReport(
        paper_id=paper.id if paper else (values[0].paper_id if values else None),
        title=paper.title if paper else None,
        total=overall.total,
        answered=overall.answered,
        correct=overall.correct,
        wrong=overall.wrong,
        unknown=overall.unknown,
        accuracy=overall.accuracy,
        verified=bool(values) and all(is_verified(question) for question in values),
        review_count=sum(1 for question in values if question.verification_status == PipelineStatus.NEEDS_REVIEW),
        module_stats=_grouped_metrics(values, "section"),
        knowledge_stats=_grouped_metrics(values, "official_knowledge_points"),
        trend=list(trend),
        risk_question_ids=[question.id for question in filter_risk_questions(values)],
        wrong_question_ids=[question.id for question in filter_wrong_questions(values)],
        repeated_wrong_question_ids=[question.id for question in filter_repeated_wrong_questions(values)],
    )
    error_counts: Counter[str] = Counter()
    for question in values:
        error_counts.update(get_error_tags(question))
    report.error_stats = dict(sorted(error_counts.items()))
    return report


def analyze_paper(
    paper_or_repository: Paper | SQLiteRepository | Iterable[Question],
    questions_or_paper_id: Iterable[Question] | str | None = None,
) -> AnalysisReport:
    paper, questions = resolve_questions(paper_or_repository, questions_or_paper_id)
    return analyze_questions(questions, paper=paper)


class PaperAnalyzer:
    """Object-oriented facade for integrations that prefer an engine object."""

    def analyze(
        self,
        paper_or_repository: Paper | SQLiteRepository | Iterable[Question],
        questions_or_paper_id: Iterable[Question] | str | None = None,
    ) -> AnalysisReport:
        return analyze_paper(paper_or_repository, questions_or_paper_id)

    analyze_paper = analyze
    report = analyze

    def wrong(self, questions: Iterable[Question], *, verified_only: bool = False) -> list[Question]:
        return filter_wrong_questions(questions, verified_only=verified_only)

    def risk(self, questions: Iterable[Question], *, threshold: float = 0.5) -> list[Question]:
        return filter_risk_questions(questions, threshold=threshold)

    def special(self, questions: Iterable[Question], **kwargs: Any) -> list[Question]:
        return filter_special_questions(questions, **kwargs)


AnalysisEngine = PaperAnalyzer


analyze = analyze_paper
compute_statistics = analyze_paper
build_analysis_report = analyze_paper
get_statistics = analyze_paper
wrong_questions = filter_wrong_questions
risk_questions = filter_risk_questions
special_questions = filter_special_questions
repeated_wrong_questions = filter_repeated_wrong_questions


__all__ = [
    "ErrorTagStore",
    "AnalysisEngine",
    "PaperAnalyzer",
    "add_error_tag",
    "analyze",
    "analyze_paper",
    "analyze_questions",
    "build_trend",
    "build_analysis_report",
    "compute_statistics",
    "filter_repeated_wrong_questions",
    "filter_risk_questions",
    "filter_special_questions",
    "filter_wrong_questions",
    "get_error_tags",
    "get_statistics",
    "is_verified",
    "question_key",
    "remove_error_tag",
    "resolve_questions",
    "risk_questions",
    "risk_score",
    "set_error_tags",
    "special_questions",
    "wrong_questions",
]
