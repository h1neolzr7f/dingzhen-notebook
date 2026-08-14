"""Small, serialisable value objects used by the P3 analysis pipeline.

The analysis layer deliberately does not add fields to :mod:`packages.core`.
Analysis is a derived view of a ``Question`` and is therefore safe to rebuild
when a question is corrected.  ``Question.ai_analysis`` is only used for
user-editable labels; official fields are never copied or overwritten here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ERROR_TAGS: tuple[str, ...] = (
    "KNOWLEDGE_GAP",
    "CONCEPT_CONFUSION",
    "MISSED_CONDITION",
    "READING_ERROR",
    "CALCULATION_ERROR",
    "METHOD_ERROR",
    "TIME_PRESSURE",
    "CARELESSNESS",
    "GUESSING",
    "FALSE_CONFIDENCE",
    "SLOW_BUT_CORRECT",
    "UNCERTAIN_CORRECT",
)

# A stable public mapping is useful to UIs while keeping the report language
# independent from the locale of the desktop application.
ERROR_TAG_LABELS: dict[str, str] = {
    "KNOWLEDGE_GAP": "知识点不熟",
    "CONCEPT_CONFUSION": "概念混淆",
    "MISSED_CONDITION": "漏读限制条件",
    "READING_ERROR": "阅读题意偏差",
    "CALCULATION_ERROR": "计算错误",
    "METHOD_ERROR": "方法选择错误",
    "TIME_PRESSURE": "时间压力",
    "CARELESSNESS": "粗心",
    "GUESSING": "猜测作答",
    "FALSE_CONFIDENCE": "自信但错误",
    "SLOW_BUT_CORRECT": "做对但过慢",
    "UNCERTAIN_CORRECT": "做对但不确定",
}


@dataclass(slots=True)
class Metric:
    """Counts and a percentage for one analysis dimension."""

    key: str
    total: int = 0
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    accuracy: float | None = None

    def finish(self) -> "Metric":
        denominator = self.answered
        self.accuracy = self.correct / denominator if denominator else None
        return self

    # Friendly aliases used by report consumers and older integrations.
    @property
    def total_questions(self) -> int:
        return self.total

    @property
    def answered_questions(self) -> int:
        return self.answered

    @property
    def correct_questions(self) -> int:
        return self.correct

    @property
    def wrong_questions(self) -> int:
        return self.wrong

    @property
    def accuracy_rate(self) -> float | None:
        return self.accuracy

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrendPoint:
    """One paper/session point in chronological learning history."""

    paper_id: str
    title: str
    date: str | None
    total: int
    answered: int
    correct: int
    accuracy: float | None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalysisReport:
    """P3 report containing aggregate and drill-down dimensions."""

    paper_id: str | None = None
    title: str | None = None
    total: int = 0
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    accuracy: float | None = None
    verified: bool = False
    review_count: int = 0
    module_stats: dict[str, Metric] = field(default_factory=dict)
    knowledge_stats: dict[str, Metric] = field(default_factory=dict)
    error_stats: dict[str, int] = field(default_factory=dict)
    trend: list[TrendPoint] = field(default_factory=list)
    risk_question_ids: list[str] = field(default_factory=list)
    wrong_question_ids: list[str] = field(default_factory=list)
    repeated_wrong_question_ids: list[str] = field(default_factory=list)

    @property
    def total_questions(self) -> int:
        return self.total

    @property
    def answered_questions(self) -> int:
        return self.answered

    @property
    def correct_questions(self) -> int:
        return self.correct

    @property
    def wrong_questions(self) -> int:
        return self.wrong

    @property
    def accuracy_rate(self) -> float | None:
        return self.accuracy

    @property
    def knowledge_point_stats(self) -> dict[str, Metric]:
        return self.knowledge_stats

    @property
    def error_tag_stats(self) -> dict[str, int]:
        return self.error_stats

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "total": self.total,
            "total_questions": self.total,
            "answered": self.answered,
            "answered_questions": self.answered,
            "correct": self.correct,
            "correct_questions": self.correct,
            "wrong": self.wrong,
            "wrong_questions": self.wrong,
            "unknown": self.unknown,
            "accuracy": self.accuracy,
            "accuracy_rate": self.accuracy,
            "verified": self.verified,
            "review_count": self.review_count,
            "module_stats": {key: value.to_dict() for key, value in self.module_stats.items()},
            "knowledge_stats": {key: value.to_dict() for key, value in self.knowledge_stats.items()},
            "knowledge_point_stats": {key: value.to_dict() for key, value in self.knowledge_stats.items()},
            "error_stats": dict(self.error_stats),
            "error_tag_stats": dict(self.error_stats),
            "trend": [point.to_dict() for point in self.trend],
            "risk_question_ids": list(self.risk_question_ids),
            "wrong_question_ids": list(self.wrong_question_ids),
            "repeated_wrong_question_ids": list(self.repeated_wrong_question_ids),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    model_dump = to_dict  # convenient parity with Pydantic models


__all__ = [
    "AnalysisReport",
    "ERROR_TAGS",
    "ERROR_TAG_LABELS",
    "Metric",
    "TrendPoint",
]
