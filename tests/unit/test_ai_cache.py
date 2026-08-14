from __future__ import annotations

import json
import sqlite3

from packages.ai import (
    AIUsage,
    AnalysisKind,
    AnalysisResult,
    FileAnalysisCache,
    SQLiteAnalysisCache,
    make_cache_key,
)


def _result(key):
    return AnalysisResult(
        kind=AnalysisKind.QUESTION_ERROR,
        data={"error_cause": "条件"},
        model=key.model,
        prompt_version=key.prompt_version,
        input_hash=key.input_hash,
        cache_key=key.value,
        usage=AIUsage(input_tokens=2, output_tokens=3),
    )


def test_file_cache_key_includes_input_model_and_prompt_version(tmp_path) -> None:
    first = make_cache_key({"x": 1}, model="m1", prompt_version="p5.v1", kind=AnalysisKind.PAPER)
    second = make_cache_key({"x": 1}, model="m2", prompt_version="p5.v1", kind=AnalysisKind.PAPER)
    third = make_cache_key({"x": 1}, model="m1", prompt_version="p5.v2", kind=AnalysisKind.PAPER)
    assert first.value != second.value != third.value
    cache = FileAnalysisCache(tmp_path / "cache")
    cache.set(first, _result(first))
    restored = cache.get(first)
    assert restored is not None
    assert restored.data["error_cause"] == "条件"
    assert cache.get(second) is None
    assert cache.get(third) is None
    assert "api_key" not in (tmp_path / "cache" / f"{first.value}.json").read_text(encoding="utf-8")


def test_sqlite_cache_uses_own_table_and_round_trips() -> None:
    connection = sqlite3.connect(":memory:")
    key = make_cache_key({"question": 1}, model="m", prompt_version="p5.v1", kind="question_error")
    cache = SQLiteAnalysisCache(connection)
    cache.set(key, _result(key))
    restored = cache.get(key)
    assert restored is not None
    assert restored.cache_key == key.value
    assert connection.execute("SELECT COUNT(*) FROM ai_analysis_cache").fetchone()[0] == 1

