"""Versioned, strict prompt templates for P5.

Templates use two explicit JSON blocks: ``OFFICIAL_SOURCE`` is read-only
evidence captured from Fenbi, while ``USER_AND_HISTORY`` contains observations
and derived context.  The model is asked to write only AI fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Mapping

from .cache import canonical_json
from .models import AnalysisKind, PROTECTED_OFFICIAL_FIELDS


PROMPT_VERSION = "p5.v1"

_COMMON_RULES = """
You are an assistant for a local personal study database.
The OFFICIAL_SOURCE block is immutable evidence copied from the Fenbi page.
Treat official_answer, official_explanation_md, official_explanation and
official_knowledge_points as read-only. Never change, infer, repair, or
rewrite those fields. Do not place your own explanation into an official
field. If an official field is missing, conflicting, or appears incorrect,
return a `needs_review` warning and a separate `controversy_note`; do not guess.
Clearly label every conclusion as an AI inference. Do not assert
carelessness without evidence. Do not output secrets, account data, tokens,
or API keys.
""".strip()


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    kind: AnalysisKind
    version: str
    body: str
    source_path: Path | None = None

    def render(
        self,
        *,
        official_source: Mapping[str, Any],
        user_and_history: Mapping[str, Any],
        output_contract: Mapping[str, Any] | None = None,
    ) -> str:
        # Deliberately use canonical JSON: stable whitespace improves cache
        # hits and keeps prompts reproducible for offline audits.
        official = json.dumps(dict(official_source), ensure_ascii=False, sort_keys=True, indent=2)
        context = json.dumps(dict(user_and_history), ensure_ascii=False, sort_keys=True, indent=2)
        contract = json.dumps(dict(output_contract or {}), ensure_ascii=False, sort_keys=True, indent=2)
        return (
            f"PROMPT_VERSION: {self.version}\n"
            f"ANALYSIS_KIND: {self.kind.value}\n\n"
            f"{_COMMON_RULES}\n\n"
            "===== OFFICIAL_SOURCE (READ ONLY; DO NOT COPY INTO AI FIELDS) =====\n"
            f"{official}\n"
            "===== END OFFICIAL_SOURCE =====\n\n"
            "===== USER_AND_HISTORY (OBSERVATIONS; MAY BE EMPTY) =====\n"
            f"{context}\n"
            "===== END USER_AND_HISTORY =====\n\n"
            f"{self.body.strip()}\n\n"
            "Return one JSON object only. The JSON must contain an `ai_fields`"
            " object, optional `warnings` list, and optional `controversy_note`."
            " Never include or replace official_answer or official_explanation"
            " in `ai_fields`.\n"
            "OUTPUT_CONTRACT:\n"
            f"{contract}\n"
        )


_FALLBACK_BODIES: dict[AnalysisKind, str] = {
    AnalysisKind.QUESTION_ERROR: """
Analyze why the user's answer differs from the official answer. Return
`ai_fields` with: error_labels (zero or more fixed labels such as
KNOWLEDGE_GAP, CONCEPT_CONFUSION, MISSED_CONDITION, READING_ERROR,
CALCULATION_ERROR, METHOD_ERROR, TIME_PRESSURE, CARELESSNESS, GUESSING,
FALSE_CONFIDENCE, SLOW_BUT_CORRECT, UNCERTAIN_CORRECT), error_cause,
missed_condition, choice_trap, correct_method, faster_method, memory_rule,
related_history, and review_advice. If the user is correct but slow, use
SLOW_BUT_CORRECT; if correct but uncertain, use UNCERTAIN_CORRECT.
""".strip(),
    AnalysisKind.PAPER: """
Analyze the complete paper using every question, not only wrong questions.
Return section accuracy, knowledge-point patterns, timing risks, wrong and
unanswered counts, priorities, and three concrete next actions in `ai_fields`.
Do not recalculate or overwrite official answers.
""".strip(),
    AnalysisKind.HISTORY: """
Compare the supplied historical records. Return recent-seven-day and
recent-thirty-day trends, improving/declining modules, repeated error labels,
timing changes, and uncertainty notes in `ai_fields`.
""".strip(),
    AnalysisKind.LEARNING_STRATEGY: """
Create an evidence-based learning strategy from the supplied statistics and
history. Return strengths, weaknesses, prioritized actions, practice mix,
time-management advice, and measurable checkpoints in `ai_fields`.
""".strip(),
    AnalysisKind.REVIEW_PLAN: """
Create a simple review schedule. Use 1, 3, 7, 14, and 30 day intervals for
successive correct reviews; after another error return to one day. Return
review items with question id, reason, due date (when a date is available),
interval, and objective in `ai_fields`.
""".strip(),
}


_DEFAULT_CONTRACTS: dict[AnalysisKind, dict[str, Any]] = {
    AnalysisKind.QUESTION_ERROR: {
        "ai_fields": {
            "error_labels": "list[str]",
            "error_cause": "string",
            "missed_condition": "string|null",
            "choice_trap": "string|null",
            "correct_method": "string",
            "faster_method": "string|null",
            "memory_rule": "string|null",
            "related_history": "list[string]",
            "review_advice": "string",
            "controversy_note": "string|null",
        }
    },
    AnalysisKind.PAPER: {"ai_fields": {"section_insights": "object", "priorities": "list[string]", "summary": "string"}},
    AnalysisKind.HISTORY: {"ai_fields": {"trends": "object", "recurring_errors": "list[string]", "summary": "string"}},
    AnalysisKind.LEARNING_STRATEGY: {"ai_fields": {"strengths": "list[string]", "weaknesses": "list[string]", "actions": "list[object]"}},
    AnalysisKind.REVIEW_PLAN: {"ai_fields": {"items": "list[object]", "schedule_notes": "list[string]"}},
}


class PromptRegistry:
    """Load templates from the repository while retaining an offline fallback."""

    def __init__(self, root: str | Path | None = None, *, version: str = PROMPT_VERSION) -> None:
        self.root = Path(root).expanduser() if root is not None else _default_prompt_root()
        self.version = str(version)
        self._templates: dict[AnalysisKind, PromptTemplate] = {}
        for kind in AnalysisKind:
            self._templates[kind] = self._load(kind)

    def _load(self, kind: AnalysisKind) -> PromptTemplate:
        filename = {
            AnalysisKind.QUESTION_ERROR: "question-analysis.md",
            AnalysisKind.PAPER: "paper-analysis.md",
            AnalysisKind.HISTORY: "history-trend.md",
            AnalysisKind.LEARNING_STRATEGY: "learning-strategy.md",
            AnalysisKind.REVIEW_PLAN: "review-plan.md",
        }[kind]
        path = self.root / filename
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            body = _FALLBACK_BODIES[kind]
            path = None
        return PromptTemplate(kind, self.version, body, path)

    def get(self, kind: AnalysisKind | str) -> PromptTemplate:
        return self._templates[AnalysisKind(kind)]

    def render(
        self,
        kind: AnalysisKind | str,
        *,
        official_source: Mapping[str, Any],
        user_and_history: Mapping[str, Any],
        output_contract: Mapping[str, Any] | None = None,
    ) -> str:
        analysis_kind = AnalysisKind(kind)
        return self.get(analysis_kind).render(
            official_source=official_source,
            user_and_history=user_and_history,
            output_contract=output_contract or _DEFAULT_CONTRACTS[analysis_kind],
        )

    def version_for(self, kind: AnalysisKind | str) -> str:
        return self.get(kind).version


def build_prompt(
    kind: AnalysisKind | str,
    *,
    official_source: Mapping[str, Any] | None = None,
    user_and_history: Mapping[str, Any] | None = None,
    registry: PromptRegistry | None = None,
) -> str:
    return (registry or PromptRegistry()).render(
        kind,
        official_source=official_source or {},
        user_and_history=user_and_history or {},
    )


build_analysis_prompt = build_prompt


def split_question_payload(value: object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a Question/mapping into immutable official and AI context blocks."""

    payload = _to_mapping(value)
    official: dict[str, Any] = {}
    context: dict[str, Any] = {}
    for key, item in payload.items():
        if key in PROTECTED_OFFICIAL_FIELDS:
            official[key] = item
        else:
            context[key] = item
    return official, context


def split_official_fields(value: object) -> tuple[dict[str, Any], dict[str, Any]]:
    return split_question_payload(value)


def _to_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return dict(dumper(mode="json"))
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError("analysis input must be a mapping or an object with model_dump()")


def _default_prompt_root() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts"


__all__ = [
    "PROMPT_VERSION",
    "PromptRegistry",
    "PromptTemplate",
    "build_prompt",
    "build_analysis_prompt",
    "split_question_payload",
    "split_official_fields",
]

