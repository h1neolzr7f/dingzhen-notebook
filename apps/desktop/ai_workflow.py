"""User-facing orchestration for optional local-model deep analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from packages.ai import (
    AIAnalysisService,
    AIModelAdapter,
    FileAnalysisCache,
    LocalHTTPAIModelAdapter,
    PROTECTED_OFFICIAL_FIELDS,
)
from packages.core import SQLiteRepository, safe_paper_id


@dataclass(frozen=True, slots=True)
class AIWorkflowResult:
    json_path: Path
    markdown_path: Path
    questions_analyzed: int
    needs_review: int
    model: str


def _without_official_fields(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _without_official_fields(item)
            for key, item in value.items()
            if str(key) not in PROTECTED_OFFICIAL_FIELDS
        }
    if isinstance(value, list):
        return [_without_official_fields(item) for item in value]
    return value


def run_ai_analysis(
    database: str | Path,
    paper_id: str,
    *,
    output_root: str | Path = "exports",
    endpoint: str = "http://127.0.0.1:11434/api/generate",
    model: str = "local",
    adapter: AIModelAdapter | None = None,
) -> AIWorkflowResult:
    """Analyze one paper without ever allowing model output into official fields."""

    paper_id = safe_paper_id(paper_id)
    repository = SQLiteRepository(database)
    repository.create_schema()
    paper = repository.get_paper(paper_id)
    if paper is None:
        raise KeyError(f"试卷不存在：{paper_id}")
    questions = repository.list_questions(paper_id)
    root = Path(output_root) / paper_id / "ai"
    selected_adapter = adapter or LocalHTTPAIModelAdapter(endpoint, model=model)
    service = AIAnalysisService(
        selected_adapter,
        cache=FileAnalysisCache(root / "cache"),
        model=model if adapter is None else getattr(selected_adapter, "model", model),
    )
    paper_result = service.analyze_paper(paper, questions)
    question_results = []
    needs_review = 0
    for question in questions:
        original_answer = list(question.official_answer or [])
        original_explanation = question.official_explanation_md
        result = service.analyze_question(question)
        safe_data = _without_official_fields(result.data)
        payload = dict(question.ai_analysis or {})
        payload["deep_analysis"] = safe_data
        payload["analysis_status"] = result.status.value
        question.ai_analysis = payload
        # Guard both in memory and in the durable row even if a hostile model
        # emits keys named like protected official fields.
        question.official_answer = original_answer or None
        question.official_explanation_md = original_explanation
        repository.upsert_question(question)
        question_results.append(result.to_dict())
        if result.status.value == "needs_review":
            needs_review += 1
    review_result = service.generate_review_plan({"paper": paper, "questions": questions})
    strategy_result = service.generate_learning_strategy(
        {"paper": paper, "questions": questions, "paper_analysis": paper_result.data},
    )
    document = {
        "schema_version": 1,
        "paper_id": paper_id,
        "model": service.model,
        "official_fields_policy": "model output is stored only under ai_analysis",
        "paper_analysis": paper_result.to_dict(),
        "question_analyses": question_results,
        "review_plan": review_result.to_dict(),
        "learning_strategy": strategy_result.to_dict(),
        "cost": service.cost_tracker.summary(),
    }
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "deep_analysis.json"
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = root / "deep_analysis.md"
    markdown_path.write_text(
        "\n".join(
            [
                "---",
                "schema_version: 1",
                f"paper_id: {json.dumps(paper_id, ensure_ascii=False)}",
                f"model: {json.dumps(service.model, ensure_ascii=False)}",
                "official_fields_separated: true",
                "---",
                "",
                "# AI 深度分析",
                "",
                "> 粉笔正确答案和官方解析只作为输入证据；以下均为 AI 推断，不会覆盖官方字段。",
                "",
                "## 整卷分析",
                "",
                "```json",
                json.dumps(paper_result.data, ensure_ascii=False, indent=2),
                "```",
                "",
                "## 复习计划",
                "",
                "```json",
                json.dumps(review_result.data, ensure_ascii=False, indent=2),
                "```",
                "",
                "## 学习策略",
                "",
                "```json",
                json.dumps(strategy_result.data, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return AIWorkflowResult(json_path, markdown_path, len(questions), needs_review, service.model)


__all__ = ["AIWorkflowResult", "run_ai_analysis"]
