"""Core domain models and persistence for the Fenbi study pipeline."""

from .version import __version__
from .answers import parse_choice_answers
from .ids import new_paper_id, safe_paper_id
from .integrity import IntegrityIssue, IntegrityReport, assess_question, transition_question
from .models import (
    AttemptState,
    Evidence,
    EvidenceRegion,
    MediaItem,
    Option,
    Paper,
    PipelineStatus,
    Question,
    QuestionType,
)
from .repository import SQLiteRepository

__all__ = [
    "__version__",
    "AttemptState",
    "Evidence",
    "EvidenceRegion",
    "IntegrityIssue",
    "IntegrityReport",
    "MediaItem",
    "Option",
    "Paper",
    "PipelineStatus",
    "Question",
    "QuestionType",
    "SQLiteRepository",
    "assess_question",
    "new_paper_id",
    "parse_choice_answers",
    "safe_paper_id",
    "transition_question",
]
