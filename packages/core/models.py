"""Pydantic domain models.

Incomplete OCR/parser output is deliberately representable.  Completeness is a
workflow concern: missing required study fields moves a question to
``NEEDS_REVIEW`` instead of making ingestion fail validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PipelineStatus(StrEnum):
    RAW_CAPTURED = "raw_captured"
    PREPROCESSED = "preprocessed"
    OCR_DONE = "ocr_done"
    PARSED = "parsed"
    COMPLETENESS_CHECKED = "completeness_checked"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    EXPORTED = "exported"


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    OTHER = "other"


class AttemptState(StrEnum):
    ANSWERED = "answered"
    UNANSWERED = "unanswered"
    UNKNOWN = "unknown"


class Option(BaseModel):
    label: str
    content_md: str = ""

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.strip().upper()


class MediaItem(BaseModel):
    type: str = "image"
    path: str


class EvidenceRegion(BaseModel):
    """Trace one parsed field back to an immutable screenshot region."""

    image: str
    bbox: tuple[int, int, int, int] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class Evidence(BaseModel):
    question_frames: list[str] = Field(default_factory=list)
    analysis_frames: list[str] = Field(default_factory=list)
    field_regions: dict[str, list[EvidenceRegion]] = Field(default_factory=dict)


class Question(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    paper_id: str
    sequence: int = Field(ge=1)
    section: str | None = None
    subsection: str | None = None
    question_type: QuestionType = QuestionType.OTHER
    stem_md: str = ""
    options: list[Option] = Field(default_factory=list)
    media: list[MediaItem] = Field(default_factory=list)
    # None means the field was not captured. [] explicitly records "unanswered".
    user_answer: list[str] | None = None
    official_answer: list[str] | None = None
    is_correct: bool | None = None
    attempt_state: AttemptState = AttemptState.UNKNOWN
    duration_seconds: int | None = Field(default=None, ge=0)
    official_explanation_md: str | None = None
    official_knowledge_points: list[str] = Field(default_factory=list)
    source: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    parse_confidence: float | None = Field(default=None, ge=0, le=1)
    verification_status: PipelineStatus = PipelineStatus.RAW_CAPTURED
    review_reasons: list[str] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)
    ai_analysis: dict[str, Any] | None = None

    @field_validator("user_answer", "official_answer")
    @classmethod
    def normalize_answers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [item.strip().upper() for item in value if item.strip()]

    @model_validator(mode="after")
    def force_incomplete_to_review(self) -> "Question":
        # Imported lazily to keep the model module independent of its policy helpers.
        reasons: list[str] = []
        if self.user_answer is None:
            reasons.append("missing_user_answer")
        if not self.official_answer:
            reasons.append("missing_official_answer")
        if not (self.official_explanation_md or "").strip():
            reasons.append("missing_official_explanation")
        if reasons:
            object.__setattr__(self, "verification_status", PipelineStatus.NEEDS_REVIEW)
            object.__setattr__(self, "review_reasons", list(dict.fromkeys([*self.review_reasons, *reasons])))
        return self

    @classmethod
    def stable_id(
        cls, platform: str, paper_key: str, sequence: int, stem_md: str, options: list[Option]
    ) -> str:
        normalized = "\n".join(
            [platform.strip().lower(), paper_key.strip(), str(sequence), " ".join(stem_md.split())]
            + [f"{o.label}:{' '.join(o.content_md.split())}" for o in options]
        )
        return "q_" + sha256(normalized.encode("utf-8")).hexdigest()


class Paper(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    title: str
    platform: str = "fenbi"
    exam_category: str | None = None
    subject: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_questions: int = Field(default=0, ge=0)
    answered_questions: int = Field(default=0, ge=0)
    correct_questions: int = Field(default=0, ge=0)
    score: float | None = None
    capture_status: PipelineStatus = PipelineStatus.RAW_CAPTURED
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
