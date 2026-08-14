from __future__ import annotations

from pathlib import Path

from packages.ai import (
    AIAnalysisService,
    AnalysisStatus,
    CompositeAnalysisCache,
    FileAnalysisCache,
    MockAIModelAdapter,
    SQLiteAnalysisCache,
)
from packages.core import Option, Question, QuestionType


def test_p5_file_and_sqlite_cache_share_same_content_address(tmp_path: Path) -> None:
    question = Question(
        id="q-p5-int",
        paper_id="paper-p5",
        sequence=1,
        question_type=QuestionType.SINGLE_CHOICE,
        stem_md="题干",
        options=[Option(label="A", content_md="甲"), Option(label="B", content_md="乙")],
        user_answer=["A"],
        official_answer=["B"],
        is_correct=False,
        official_explanation_md="官方解析",
    )
    adapter = MockAIModelAdapter({"ai_fields": {"error_cause": "概念混淆"}})
    sqlite = SQLiteAnalysisCache(tmp_path / "study.db")
    cache = CompositeAnalysisCache(FileAnalysisCache(tmp_path / "files"), sqlite)
    first_service = AIAnalysisService(adapter, cache=cache)
    first = first_service.analyze_question(question)
    assert first.status is AnalysisStatus.COMPLETED

    second_adapter = MockAIModelAdapter({"ai_fields": {"error_cause": "should not run"}})
    second_service = AIAnalysisService(second_adapter, cache=cache)
    second = second_service.analyze_question(question)
    assert second.status is AnalysisStatus.CACHED
    assert second.data["error_cause"] == "概念混淆"
    assert second_adapter.calls == []


def test_p5_aggregate_analysis_surfaces_incomplete_questions_without_guessing(tmp_path: Path) -> None:
    incomplete = {
        "id": "q-incomplete",
        "stem_md": "题干",
        "user_answer": ["A"],
        "official_answer": None,
        "official_explanation_md": "",
    }
    adapter = MockAIModelAdapter({"ai_fields": {"summary": "not allowed"}})
    service = AIAnalysisService(adapter, cache=FileAnalysisCache(tmp_path / "cache"))
    result = service.analyze_paper({"id": "paper", "questions": [incomplete]})
    assert result.status is AnalysisStatus.NEEDS_REVIEW
    assert any(item.startswith("questions_missing_official_fields") for item in result.warnings)
    assert adapter.calls == []

