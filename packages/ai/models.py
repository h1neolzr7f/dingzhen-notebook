"""P5 AI-domain models.

The AI layer intentionally has its own small set of models instead of
extending :mod:`packages.core.models.Question`.  A model response is an
*interpretation* of the captured record; it is never the source of the
official answer or official explanation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


class AnalysisKind(StrEnum):
    """Supported P5 analysis products."""

    QUESTION_ERROR = "question_error"
    PAPER = "paper"
    HISTORY = "history"
    LEARNING_STRATEGY = "learning_strategy"
    REVIEW_PLAN = "review_plan"


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    CACHED = "cached"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AIUsage:
    """Usage returned by an adapter.

    Both OpenAI-style (``prompt_tokens``/``completion_tokens``) and
    Ollama/local style (``input_tokens``/``output_tokens``) names are
    accepted by :meth:`from_value`.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_tokens", max(0, int(self.input_tokens)))
        object.__setattr__(self, "output_tokens", max(0, int(self.output_tokens)))
        total = int(self.total_tokens)
        if total <= 0:
            total = int(self.input_tokens) + int(self.output_tokens)
        object.__setattr__(self, "total_tokens", max(0, total))
        object.__setattr__(self, "cost_usd", max(0.0, float(self.cost_usd)))
        if self.latency_ms is not None:
            object.__setattr__(self, "latency_ms", max(0.0, float(self.latency_ms)))

    @classmethod
    def from_value(cls, value: object | None) -> "AIUsage":
        if isinstance(value, AIUsage):
            return value
        if not isinstance(value, Mapping):
            return cls()
        def number(*names: str) -> float:
            for name in names:
                if name in value and value[name] is not None:
                    try:
                        return float(value[name])
                    except (TypeError, ValueError):
                        continue
            return 0.0

        return cls(
            input_tokens=int(number("input_tokens", "prompt_tokens", "input")),
            output_tokens=int(number("output_tokens", "completion_tokens", "output")),
            total_tokens=int(number("total_tokens", "tokens", "total")),
            cost_usd=number("cost_usd", "cost", "price"),
            latency_ms=(number("latency_ms", "latency") or None),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class AIResponse:
    """Adapter-neutral response envelope."""

    content: object
    model: str | None = None
    usage: AIUsage = field(default_factory=AIUsage)
    raw: object | None = None
    request_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage.to_dict(),
            "request_id": self.request_id,
        }


@dataclass(slots=True)
class AnalysisResult:
    """Result of one deterministic, cacheable analysis call."""

    kind: AnalysisKind
    data: dict[str, Any] = field(default_factory=dict)
    status: AnalysisStatus = AnalysisStatus.COMPLETED
    warnings: list[str] = field(default_factory=list)
    entity_id: str | None = None
    model: str = "unknown"
    prompt_version: str = "p5.v1"
    input_hash: str = ""
    cache_key: str = ""
    usage: AIUsage = field(default_factory=AIUsage)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cached_from: str | None = None

    def __post_init__(self) -> None:
        self.kind = AnalysisKind(self.kind)
        self.status = AnalysisStatus(self.status)
        self.data = dict(self.data or {})
        self.warnings = list(dict.fromkeys(str(item) for item in self.warnings if str(item).strip()))
        self.usage = AIUsage.from_value(self.usage)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        else:
            self.created_at = self.created_at.astimezone(timezone.utc)

    @property
    def ai_fields(self) -> dict[str, Any]:
        """Alias used by callers that want to distinguish AI fields."""

        return self.data

    @property
    def needs_review(self) -> bool:
        return self.status is AnalysisStatus.NEEDS_REVIEW or bool(self.warnings)

    def to_dict(self) -> dict[str, object]:
        return {
            "analysis_kind": self.kind.value,
            "data": self.data,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "entity_id": self.entity_id,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "input_hash": self.input_hash,
            "cache_key": self.cache_key,
            "usage": self.usage.to_dict(),
            "created_at": self.created_at.isoformat(),
            "cached_from": self.cached_from,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AnalysisResult":
        created = value.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                created = None
        return cls(
            kind=value.get("analysis_kind", value.get("kind", AnalysisKind.QUESTION_ERROR)),
            data=value.get("data", value.get("ai_fields", {})),
            status=value.get("status", AnalysisStatus.COMPLETED),
            warnings=list(value.get("warnings", [])),
            entity_id=value.get("entity_id"),
            model=str(value.get("model", "unknown")),
            prompt_version=str(value.get("prompt_version", "p5.v1")),
            input_hash=str(value.get("input_hash", "")),
            cache_key=str(value.get("cache_key", "")),
            usage=AIUsage.from_value(value.get("usage")),
            created_at=created if isinstance(created, datetime) else datetime.now(timezone.utc),
            cached_from=value.get("cached_from"),
        )


@dataclass(frozen=True, slots=True)
class CacheKey:
    """The versioned cache identity required by P5."""

    value: str
    input_hash: str
    model: str
    prompt_version: str
    kind: str

    def __str__(self) -> str:
        return self.value

    def to_dict(self) -> dict[str, str]:
        return {
            "cache_key": self.value,
            "input_hash": self.input_hash,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "analysis_kind": self.kind,
        }


class AIError(RuntimeError):
    """Base error raised by the AI layer."""


class AIAdapterError(AIError):
    """The configured adapter could not produce a response."""


class AIConfigurationError(AIError):
    """An unsafe or incomplete adapter configuration was supplied."""


PROTECTED_OFFICIAL_FIELDS = frozenset(
    {
        "official_answer",
        "official_explanation",
        "official_explanation_md",
        "official_knowledge_points",
    }
)

