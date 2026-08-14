"""Small dependency-free timing primitive for P6 performance diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TimingSample:
    operation: str
    elapsed_ms: float
    ok: bool


def timed(operation: str, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> tuple[T, TimingSample]:
    started = perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception:
        elapsed = (perf_counter() - started) * 1000
        raise
    return result, TimingSample(operation, (perf_counter() - started) * 1000, True)

