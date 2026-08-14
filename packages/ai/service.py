"""High-level P5 analysis orchestration.

The service owns prompt rendering, content-addressed caching, response
sanitisation and cost accounting.  It does not mutate the core Question/Paper
models unless a caller explicitly asks :meth:`attach_to_question` to create a
copy with ``ai_analysis`` set.
"""

from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .adapters import AIModelAdapter, coerce_response
from .cache import AnalysisCache, NullAnalysisCache, make_cache_key
from .models import (
    AIAdapterError,
    AIResponse,
    AIUsage,
    AnalysisKind,
    AnalysisResult,
    AnalysisStatus,
    PROTECTED_OFFICIAL_FIELDS,
)
from .prompts import PromptRegistry, split_question_payload
from .stats import CostTracker


_OFFICIAL_ALIASES = {
    "official_answer",
    "official_explanation",
    "official_explanation_md",
    "official_knowledge_points",
}


class AIAnalysisService:
    """Run one of the five P5 analysis products."""

    def __init__(
        self,
        adapter: AIModelAdapter,
        *,
        cache: AnalysisCache | None = None,
        prompt_registry: PromptRegistry | None = None,
        cost_tracker: CostTracker | None = None,
        model: str | None = None,
    ) -> None:
        self.adapter = adapter
        self.cache = cache or NullAnalysisCache()
        self.prompts = prompt_registry or PromptRegistry()
        self.cost_tracker = cost_tracker or CostTracker()
        self.model = str(model or getattr(adapter, "model", adapter.__class__.__name__))

    @property
    def prompt_version(self) -> str:
        return self.prompts.version

    def cache_key_for(self, kind: AnalysisKind | str, payload: object) -> str:
        key = make_cache_key(payload, model=self.model, prompt_version=self.prompt_version, kind=kind)
        return key.value

    def analyze(
        self,
        kind: AnalysisKind | str,
        payload: object,
        *,
        entity_id: str | None = None,
        history: object | None = None,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        analysis_kind = AnalysisKind(kind)
        raw_payload = _to_mapping_or_value(payload)
        official, context = _partition_payload(raw_payload)
        if history is not None:
            context["history"] = _safe_value(history)
        if analysis_kind is AnalysisKind.PAPER:
            context.setdefault("deterministic_statistics", deterministic_paper_statistics(context.get("questions", [])))
        elif analysis_kind is AnalysisKind.HISTORY:
            context.setdefault("deterministic_statistics", deterministic_history_statistics(context.get("history", context)))
        elif analysis_kind is AnalysisKind.REVIEW_PLAN:
            context.setdefault("deterministic_schedule", deterministic_review_schedule(context.get("questions", raw_payload)))

        key = make_cache_key(raw_payload, model=self.model, prompt_version=self.prompt_version, kind=analysis_kind)
        missing = _missing_official_fields(analysis_kind, official, raw_payload)
        if missing:
            warnings = [
                "NEEDS_REVIEW",
                *[
                    field if field.startswith("questions_missing_") else f"missing_{field}"
                    for field in missing
                ],
                "AI 不得猜测缺失的粉笔官方字段",
            ]
            result = AnalysisResult(
                kind=analysis_kind,
                data={
                    "needs_review": True,
                    "missing_official_fields": missing,
                    "controversy_note": "官方字段不完整，未调用 AI 推断答案或解析。",
                },
                status=AnalysisStatus.NEEDS_REVIEW,
                warnings=warnings,
                entity_id=entity_id or _entity_id(raw_payload),
                model=self.model,
                prompt_version=self.prompt_version,
                input_hash=key.input_hash,
                cache_key=key.value,
            )
            # Cache the safe review decision too; this avoids repeatedly
            # prompting a model when a capture still needs human correction.
            if not force:
                cached = self.cache.get(key)
                if cached is not None:
                    return _as_cached(cached)
            self.cache.set(key, result)
            return result

        if not force:
            cached = self.cache.get(key)
            if cached is not None:
                self.cost_tracker.record(cached.model or self.model, cached.usage, cached=True)
                return _as_cached(cached)

        prompt = self.prompts.render(
            analysis_kind,
            official_source=official,
            user_and_history=context,
        )
        call_metadata = {"analysis_kind": analysis_kind.value, "entity_id": entity_id or _entity_id(raw_payload)}
        if metadata:
            call_metadata.update(_safe_mapping(metadata))
        try:
            response = _call_adapter(self.adapter, prompt, metadata=call_metadata)
        except Exception as exc:
            if isinstance(exc, AIAdapterError):
                error = exc
            else:
                error = AIAdapterError(str(exc))
            result = AnalysisResult(
                kind=analysis_kind,
                data={"error": str(error)},
                status=AnalysisStatus.FAILED,
                warnings=["AI_ADAPTER_ERROR", str(error)],
                entity_id=entity_id or _entity_id(raw_payload),
                model=self.model,
                prompt_version=self.prompt_version,
                input_hash=key.input_hash,
                cache_key=key.value,
            )
            # Adapter errors are intentionally not cached: a later retry may
            # succeed after a local model starts.
            return result

        data, warnings, needs_review = _normalise_content(response.content)
        usage = self.cost_tracker.record(response.model or self.model, response.usage)
        result = AnalysisResult(
            kind=analysis_kind,
            data=data,
            status=AnalysisStatus.NEEDS_REVIEW if needs_review else AnalysisStatus.COMPLETED,
            warnings=warnings,
            entity_id=entity_id or _entity_id(raw_payload),
            model=response.model or self.model,
            prompt_version=self.prompt_version,
            input_hash=key.input_hash,
            cache_key=key.value,
            usage=usage,
        )
        self.cache.set(key, result)
        return result

    def analyze_question(
        self,
        question: object,
        *,
        history: object | None = None,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        return self.analyze(
            AnalysisKind.QUESTION_ERROR,
            question,
            entity_id=_entity_id(question),
            history=history,
            force=force,
            metadata=metadata,
        )

    question_error_analysis = analyze_question
    analyze_question_error = analyze_question

    def analyze_paper(
        self,
        paper: object,
        questions: Sequence[object] | None = None,
        *,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        payload = _to_mapping_or_value(paper)
        if questions is not None:
            payload = dict(payload) if isinstance(payload, Mapping) else {"paper": payload}
            payload["questions"] = [_safe_value(item) for item in questions]
        return self.analyze(AnalysisKind.PAPER, payload, entity_id=_entity_id(paper), force=force, metadata=metadata)

    paper_analysis = analyze_paper

    def analyze_history(
        self,
        history: object,
        *,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        payload = history if isinstance(history, Mapping) else {"history": _safe_value(history)}
        return self.analyze(AnalysisKind.HISTORY, payload, entity_id="history", force=force, metadata=metadata)

    history_trend_analysis = analyze_history
    analyze_history_trend = analyze_history

    def generate_learning_strategy(
        self,
        profile_or_history: object,
        *,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        payload = profile_or_history if isinstance(profile_or_history, Mapping) else {"history": _safe_value(profile_or_history)}
        return self.analyze(AnalysisKind.LEARNING_STRATEGY, payload, entity_id="learning_strategy", force=force, metadata=metadata)

    learning_strategy = generate_learning_strategy
    analyze_learning_strategy = generate_learning_strategy

    def generate_review_plan(
        self,
        questions_or_history: object,
        *,
        as_of: date | datetime | None = None,
        force: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisResult:
        payload = questions_or_history if isinstance(questions_or_history, Mapping) else {"questions": _safe_value(questions_or_history)}
        payload = dict(payload)
        payload.setdefault("as_of", (as_of or datetime.now(timezone.utc)).isoformat() if isinstance(as_of or datetime.now(timezone.utc), datetime) else (as_of or date.today()).isoformat())
        return self.analyze(AnalysisKind.REVIEW_PLAN, payload, entity_id="review_plan", force=force, metadata=metadata)

    review_plan = generate_review_plan
    analyze_review_plan = generate_review_plan

    @staticmethod
    def attach_to_question(question: object, result: AnalysisResult) -> object:
        """Return a copy carrying AI fields while preserving official fields."""

        if result.kind is not AnalysisKind.QUESTION_ERROR:
            raise ValueError("only question_error results can be attached to a question")
        if hasattr(question, "model_copy"):
            # Pydantic model_copy avoids invoking a potentially strict
            # assignment validator on unrelated official fields.
            return question.model_copy(update={"ai_analysis": copy.deepcopy(result.data)})
        if isinstance(question, Mapping):
            value = dict(question)
            value["ai_analysis"] = copy.deepcopy(result.data)
            return value
        value = copy.deepcopy(question)
        setattr(value, "ai_analysis", copy.deepcopy(result.data))
        return value

    def analyze_and_attach_question(self, question: object, **kwargs: object) -> tuple[object, AnalysisResult]:
        result = self.analyze_question(question, **kwargs)
        return self.attach_to_question(question, result), result

    @property
    def cost_summary(self) -> dict[str, object]:
        return self.cost_tracker.summary()

    usage_summary = cost_summary


AIAnalyzer = AIAnalysisService
AnalysisService = AIAnalysisService


def _call_adapter(adapter: object, prompt: str, *, metadata: Mapping[str, object]) -> AIResponse:
    method = getattr(adapter, "complete", None) or getattr(adapter, "generate", None) or getattr(adapter, "analyze", None)
    if method is None:
        raise AIAdapterError("adapter must provide complete(), generate(), or analyze()")
    try:
        value = method(prompt, metadata=metadata)
    except TypeError:
        try:
            value = method(prompt)
        except TypeError:
            value = method(prompt, None)
    return coerce_response(value, model=getattr(adapter, "model", None))


def _normalise_content(content: object) -> tuple[dict[str, Any], list[str], bool]:
    warnings: list[str] = []
    needs_review = False
    value = content
    if isinstance(value, str):
        text = value.strip()
        # Models sometimes wrap JSON in a markdown fence.  Accept it without
        # weakening the official-field guard.
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip("\n ")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            warnings.append("AI_RESPONSE_NOT_JSON")
            value = {"raw_analysis": content}
    if isinstance(value, Mapping):
        envelope = dict(value)
        if isinstance(envelope.get("ai_fields"), Mapping):
            data = dict(envelope["ai_fields"])
        elif isinstance(envelope.get("data"), Mapping):
            data = dict(envelope["data"])
        else:
            data = {key: item for key, item in envelope.items() if key not in {"warnings", "status", "controversy_note"}}
        raw_warnings = envelope.get("warnings", [])
        if isinstance(raw_warnings, str):
            warnings.append(raw_warnings)
        elif isinstance(raw_warnings, Iterable):
            warnings.extend(str(item) for item in raw_warnings)
        controversy = envelope.get("controversy_note")
        if controversy:
            data["controversy_note"] = str(controversy)
            warnings.append("AI提出官方字段争议，请人工核对")
            needs_review = True
    else:
        data = {"raw_analysis": value}

    clean, removed = _strip_protected(data)
    if removed:
        warnings.append("AI_ATTEMPTED_OFFICIAL_FIELD_IGNORED")
        warnings.append("NEEDS_REVIEW")
        needs_review = True
    return clean, list(dict.fromkeys(warnings)), needs_review


def _strip_protected(value: object, key: str | None = None) -> tuple[object, bool]:
    removed = False
    if key and key.lower() in _OFFICIAL_ALIASES:
        return None, True
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            name = str(raw_key)
            clean, was_removed = _strip_protected(raw_value, name)
            removed = removed or was_removed
            if not (was_removed and name.lower() in _OFFICIAL_ALIASES):
                result[name] = clean
        return result, removed
    if isinstance(value, list):
        result_list: list[object] = []
        for item in value:
            clean, was_removed = _strip_protected(item)
            result_list.append(clean)
            removed = removed or was_removed
        return result_list, removed
    return value, False


def _partition_payload(value: object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recursively split protected fields while preserving question lists."""

    if isinstance(value, Mapping):
        official: dict[str, Any] = {}
        context: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key in PROTECTED_OFFICIAL_FIELDS:
                official[key] = _safe_value(raw_value)
                continue
            if isinstance(raw_value, Mapping):
                nested_official, nested_context = _partition_payload(raw_value)
                if nested_official:
                    official[key] = nested_official
                context[key] = nested_context
            elif isinstance(raw_value, list):
                official_items: list[Any] = []
                context_items: list[Any] = []
                has_official = False
                for item in raw_value:
                    if isinstance(item, Mapping):
                        nested_official, nested_context = _partition_payload(item)
                        official_items.append(nested_official)
                        context_items.append(nested_context)
                        has_official = has_official or bool(nested_official)
                    else:
                        context_items.append(_safe_value(item))
                        official_items.append({})
                if has_official:
                    official[key] = official_items
                context[key] = context_items
            else:
                context[key] = _safe_value(raw_value)
        return official, context
    return {}, {"value": _safe_value(value)}


def _missing_official_fields(kind: AnalysisKind, official: Mapping[str, Any], raw_payload: object) -> list[str]:
    if kind is AnalysisKind.QUESTION_ERROR:
        answer = official.get("official_answer")
        explanation = official.get("official_explanation_md") or official.get("official_explanation")
        missing: list[str] = []
        if not answer:
            missing.append("official_answer")
        if not str(explanation or "").strip():
            missing.append("official_explanation")
        return missing
    # Paper/history/strategy/plan can still run on aggregate data, but if they
    # carry questions with missing official values surface an explicit warning
    # through the same review result rather than allowing a model to fill them.
    questions = _find_questions(raw_payload)
    if not questions:
        return []
    missing_count = 0
    for question in questions:
        q_official, _ = _partition_payload(question)
        if not q_official.get("official_answer") or not str(q_official.get("official_explanation_md") or q_official.get("official_explanation") or "").strip():
            missing_count += 1
    return [f"questions_missing_official_fields:{missing_count}"] if missing_count else []


def _find_questions(value: object) -> list[object]:
    if isinstance(value, Mapping):
        if isinstance(value.get("questions"), Sequence) and not isinstance(value.get("questions"), (str, bytes, bytearray)):
            return list(value["questions"])
        if "official_answer" in value or "stem_md" in value:
            return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _as_cached(result: AnalysisResult) -> AnalysisResult:
    return AnalysisResult(
        kind=result.kind,
        data=copy.deepcopy(result.data),
        status=AnalysisStatus.CACHED,
        warnings=list(result.warnings),
        entity_id=result.entity_id,
        model=result.model,
        prompt_version=result.prompt_version,
        input_hash=result.input_hash,
        cache_key=result.cache_key,
        usage=result.usage,
        created_at=result.created_at,
        cached_from=result.status.value,
    )


def _safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _safe_value(item, str(key)) for key, item in value.items() if _safe_value(item, str(key)) is not None}


def _safe_value(value: object, key: str | None = None) -> object:
    if key and any(token in key.lower().replace("-", "_") for token in ("api_key", "apikey", "access_token", "refresh_token", "password", "passwd", "cookie", "authorization", "secret")):
        return None
    if isinstance(value, Mapping):
        return _safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return _safe_value(dumper(mode="json"))
    return str(value)


def _to_mapping_or_value(value: object) -> object:
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return dumper(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return {"value": _safe_value(value)}


def _entity_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        for key in ("id", "paper_id", "question_id"):
            if value.get(key) is not None:
                return str(value[key])
    value_id = getattr(value, "id", None)
    return str(value_id) if value_id is not None else None


def deterministic_paper_statistics(questions: object) -> dict[str, object]:
    values = _find_questions(questions)
    total = len(values)
    answered = correct = wrong = unanswered = 0
    by_section: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0, "unanswered": 0})
    durations: list[int] = []
    labels: Counter[str] = Counter()
    for value in values:
        payload = _safe_value(value)
        if not isinstance(payload, Mapping):
            continue
        user = payload.get("user_answer")
        official = payload.get("official_answer")
        is_correct = payload.get("is_correct")
        if user is None:
            unanswered += 1
        elif is_correct is True or (is_correct is None and user and official and list(user) == list(official)):
            answered += 1
            correct += 1
        else:
            answered += 1
            wrong += 1
        duration = payload.get("duration_seconds")
        if duration is not None:
            try:
                durations.append(int(duration))
            except (TypeError, ValueError):
                pass
        section = str(payload.get("section") or "未分类")
        bucket = by_section[section]
        bucket["total"] += 1
        if user is None:
            bucket["unanswered"] += 1
        elif is_correct is True or (is_correct is None and user and official and list(user) == list(official)):
            bucket["correct"] += 1
        else:
            bucket["wrong"] += 1
        for tag in payload.get("ai_analysis", {}).get("error_labels", []) if isinstance(payload.get("ai_analysis"), Mapping) else []:
            labels[str(tag)] += 1
    return {
        "total_questions": total,
        "answered_questions": answered,
        "correct_questions": correct,
        "wrong_questions": wrong,
        "unanswered_questions": unanswered,
        "accuracy": (correct / answered if answered else None),
        "average_duration_seconds": (sum(durations) / len(durations) if durations else None),
        "by_section": dict(by_section),
        "error_labels": dict(labels),
    }


def deterministic_history_statistics(history: object) -> dict[str, object]:
    records = _find_questions(history)
    if isinstance(history, Mapping) and isinstance(history.get("papers"), Sequence):
        records = list(history["papers"])
    paper_stats: list[dict[str, object]] = []
    for item in records:
        payload = _safe_value(item)
        if isinstance(payload, Mapping):
            if "questions" in payload:
                stats = deterministic_paper_statistics(payload.get("questions", []))
            else:
                stats = dict(payload)
            paper_stats.append({"id": payload.get("id"), "date": payload.get("completed_at", payload.get("date")), "stats": stats})
    return {"records": len(paper_stats), "papers": paper_stats[-30:], "recent": paper_stats[-7:]}


def deterministic_review_schedule(questions: object, *, as_of: date | datetime | None = None) -> list[dict[str, object]]:
    now = as_of or datetime.now(timezone.utc)
    if isinstance(now, datetime):
        base = now.date()
    else:
        base = now
    values = _find_questions(questions)
    schedule: list[dict[str, object]] = []
    for value in values:
        payload = _safe_value(value)
        if not isinstance(payload, Mapping):
            continue
        user = payload.get("user_answer")
        is_correct = payload.get("is_correct")
        if user is None:
            continue
        previous_reviews = int(payload.get("review_count", payload.get("revision_count", 0)) or 0)
        interval = 1 if is_correct is not True else {0: 3, 1: 7, 2: 14, 3: 30}.get(previous_reviews, 30)
        due = base + timedelta(days=interval)
        schedule.append({"question_id": payload.get("id"), "interval_days": interval, "due_date": due.isoformat(), "reason": "wrong" if is_correct is False else "reinforce"})
    return schedule


__all__ = [
    "AIAnalysisService",
    "AIAnalyzer",
    "AnalysisService",
    "deterministic_history_statistics",
    "deterministic_paper_statistics",
    "deterministic_review_schedule",
]
