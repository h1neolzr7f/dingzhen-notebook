from __future__ import annotations

from packages.ai import (
    AIAnalysisService,
    AnalysisKind,
    AnalysisStatus,
    FileAnalysisCache,
    MockAIModelAdapter,
)
from packages.core import Option, Question, QuestionType


def question(**changes) -> Question:
    payload = {
        "id": "q-ai-001",
        "paper_id": "paper-ai",
        "sequence": 1,
        "question_type": QuestionType.SINGLE_CHOICE,
        "stem_md": "下列哪项正确？",
        "options": [Option(label="A", content_md="甲"), Option(label="B", content_md="乙"), Option(label="C", content_md="丙")],
        "user_answer": ["B"],
        "official_answer": ["C"],
        "is_correct": False,
        "official_explanation_md": "粉笔官方解析：C。",
        "duration_seconds": 83,
    }
    payload.update(changes)
    return Question.model_validate(payload)


def test_question_analysis_never_overwrites_official_fields_and_flags_attempt(tmp_path) -> None:
    adapter = MockAIModelAdapter(
        {
            "ai_fields": {
                "error_cause": "漏看条件",
                "official_answer": ["A"],
                "official_explanation": "模型伪造的解析",
            }
        }
    )
    service = AIAnalysisService(adapter, cache=FileAnalysisCache(tmp_path / "cache"))
    original = question()
    result = service.analyze_question(original)
    assert result.status is AnalysisStatus.NEEDS_REVIEW
    assert result.data["error_cause"] == "漏看条件"
    assert "official_answer" not in result.data
    assert "official_explanation" not in result.data
    assert "AI_ATTEMPTED_OFFICIAL_FIELD_IGNORED" in result.warnings
    attached = service.attach_to_question(original, result)
    assert attached.official_answer == ["C"]
    assert attached.official_explanation_md == original.official_explanation_md
    assert attached.ai_analysis["error_cause"] == "漏看条件"


def test_missing_official_fields_returns_review_without_calling_model(tmp_path) -> None:
    adapter = MockAIModelAdapter({"ai_fields": {"error_cause": "never called"}})
    service = AIAnalysisService(adapter, cache=FileAnalysisCache(tmp_path / "cache"))
    result = service.analyze_question(question(official_answer=None, official_explanation_md=None))
    assert result.status is AnalysisStatus.NEEDS_REVIEW
    assert "missing_official_answer" in result.warnings
    assert "missing_official_explanation" in result.warnings
    assert adapter.calls == []


def test_cache_hit_avoids_second_model_call_and_cost(tmp_path) -> None:
    adapter = MockAIModelAdapter({"ai_fields": {"error_cause": "条件"}}, usage={"prompt_tokens": 10, "completion_tokens": 5})
    service = AIAnalysisService(adapter, cache=FileAnalysisCache(tmp_path / "cache"))
    first = service.analyze_question(question())
    second = service.analyze_question(question())
    assert first.status is AnalysisStatus.COMPLETED
    assert second.status is AnalysisStatus.CACHED
    assert len(adapter.calls) == 1
    assert service.cost_summary["total"]["calls"] == 1
    assert service.cost_summary["total"]["cached_calls"] == 1


def test_all_five_analysis_products_use_offline_fake_model(tmp_path) -> None:
    adapter = MockAIModelAdapter({"ai_fields": {"summary": "ok", "items": []}})
    service = AIAnalysisService(adapter, cache=FileAnalysisCache(tmp_path / "cache"))
    q = question()
    paper = {"id": "paper-ai", "title": "mock", "questions": [q.model_dump(mode="json")]}
    assert service.analyze_question(q).kind is AnalysisKind.QUESTION_ERROR
    assert service.analyze_paper(paper).kind is AnalysisKind.PAPER
    assert service.analyze_history([paper]).kind is AnalysisKind.HISTORY
    assert service.generate_learning_strategy({"accuracy": 0.5}).kind is AnalysisKind.LEARNING_STRATEGY
    assert service.generate_review_plan([q.model_dump(mode="json")]).kind is AnalysisKind.REVIEW_PLAN
    assert len(adapter.calls) == 5

