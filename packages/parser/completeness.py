"""Boundary between OCR field parsing and the core integrity state machine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from packages.core.integrity import IntegrityReport, transition_question
from packages.core.models import Question


def finalize_parsed_question(
    parsed: Question | Mapping[str, Any], *, confidence_threshold: float = 0.80
) -> tuple[Question, IntegrityReport]:
    """Build an incomplete-safe model, check it, and return its review status."""
    question = parsed if isinstance(parsed, Question) else Question.model_validate(parsed)
    report = transition_question(question, confidence_threshold)
    return question, report
