"""Deterministic usage and cost accounting for P5 model calls."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

from .models import AIResponse, AIUsage


@dataclass(frozen=True, slots=True)
class CostSummary:
    calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "cached_calls": self.cached_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }


class CostTracker:
    """Track actual adapter calls and estimate cost for local models.

    ``pricing`` maps a model to ``(input_usd_per_1k, output_usd_per_1k)``.
    Explicit ``usage.cost_usd`` from an adapter takes precedence.  Cache hits
    can be recorded for observability but never add token/cost totals.
    """

    def __init__(
        self,
        pricing: Mapping[str, tuple[float, float] | Mapping[str, float]] | None = None,
        *,
        default_pricing: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.pricing = dict(pricing or {})
        self.default_pricing = (float(default_pricing[0]), float(default_pricing[1]))
        self._by_model: dict[str, dict[str, float]] = defaultdict(lambda: {
            "calls": 0,
            "cached_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        })

    def record(
        self,
        model: str,
        usage: AIUsage | Mapping[str, object] | None = None,
        *,
        cached: bool = False,
    ) -> AIUsage:
        name = str(model)
        actual = AIUsage.from_value(usage)
        bucket = self._by_model[name]
        if cached:
            bucket["cached_calls"] += 1
            return actual
        bucket["calls"] += 1
        cost = actual.cost_usd
        if cost <= 0:
            input_rate, output_rate = self._rates(name)
            cost = (actual.input_tokens / 1000.0) * input_rate + (actual.output_tokens / 1000.0) * output_rate
            actual = AIUsage(
                input_tokens=actual.input_tokens,
                output_tokens=actual.output_tokens,
                total_tokens=actual.total_tokens,
                cost_usd=cost,
                latency_ms=actual.latency_ms,
            )
        bucket["input_tokens"] += actual.input_tokens
        bucket["output_tokens"] += actual.output_tokens
        bucket["total_tokens"] += actual.total_tokens
        bucket["cost_usd"] += actual.cost_usd
        return actual

    record_usage = record

    def record_response(self, response: AIResponse, *, cached: bool = False) -> AIUsage:
        return self.record(response.model or "unknown", response.usage, cached=cached)

    def _rates(self, model: str) -> tuple[float, float]:
        value = self.pricing.get(model)
        if value is None:
            return self.default_pricing
        if isinstance(value, Mapping):
            return float(value.get("input", value.get("input_usd_per_1k", 0.0))), float(value.get("output", value.get("output_usd_per_1k", 0.0)))
        return float(value[0]), float(value[1])

    def for_model(self, model: str) -> CostSummary:
        bucket = self._by_model.get(str(model))
        if not bucket:
            return CostSummary()
        return CostSummary(**{key: int(value) if key in {"calls", "cached_calls", "input_tokens", "output_tokens", "total_tokens"} else float(value) for key, value in bucket.items()})

    def summary(self) -> dict[str, object]:
        by_model = {model: self.for_model(model).to_dict() for model in sorted(self._by_model)}
        total = CostSummary(
            calls=sum(item["calls"] for item in by_model.values()),
            cached_calls=sum(item["cached_calls"] for item in by_model.values()),
            input_tokens=sum(item["input_tokens"] for item in by_model.values()),
            output_tokens=sum(item["output_tokens"] for item in by_model.values()),
            total_tokens=sum(item["total_tokens"] for item in by_model.values()),
            cost_usd=sum(float(item["cost_usd"]) for item in by_model.values()),
        )
        return {"total": total.to_dict(), "by_model": by_model}

    to_dict = summary

    @property
    def total_cost_usd(self) -> float:
        return float(self.summary()["total"]["cost_usd"])

    @property
    def total_tokens(self) -> int:
        return int(self.summary()["total"]["total_tokens"])

