"""Spaced-review planner inspired by 今知「预习/一刷/二刷/多轮复习」.

Does not call cloud APIs. Stages are derived from correctness and existing
``ai_analysis`` counters when present.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

from packages.core.models import Question


class ReviewStage(StrEnum):
    PREVIEW = "preview"  # 预习
    FIRST = "first_pass"  # 一刷
    SECOND = "second_pass"  # 二刷
    INTERVAL = "interval"  # 间隔/多轮
    MASTERED = "mastered"


def _history_wrong_count(question: Question) -> int:
    data = question.ai_analysis or {}
    for key in ("wrong_attempts", "wrong_count", "repeat_count"):
        try:
            value = int(data.get(key, 0))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return 0


def classify_stage(question: Question) -> ReviewStage:
    if question.is_correct is True and _history_wrong_count(question) == 0:
        return ReviewStage.MASTERED
    if question.is_correct is False:
        wrongs = max(1, _history_wrong_count(question))
        if wrongs >= 3:
            return ReviewStage.INTERVAL
        if wrongs == 2:
            return ReviewStage.SECOND
        return ReviewStage.FIRST
    if question.user_answer is None:
        return ReviewStage.PREVIEW
    return ReviewStage.FIRST


def build_review_plan(
    questions: Iterable[Question],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Group questions into review tracks with simple due dates."""

    now = as_of or datetime.now(timezone.utc)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    due_offsets = {
        ReviewStage.PREVIEW: 0,
        ReviewStage.FIRST: 1,
        ReviewStage.SECOND: 3,
        ReviewStage.INTERVAL: 7,
        ReviewStage.MASTERED: 30,
    }
    for question in questions:
        stage = classify_stage(question)
        due = (now + timedelta(days=due_offsets[stage])).date().isoformat()
        buckets[stage.value].append(
            {
                "id": question.id,
                "sequence": question.sequence,
                "stem": (question.stem_md or "")[:120],
                "is_correct": question.is_correct,
                "knowledge_points": list(question.official_knowledge_points),
                "due_date": due,
                "stage": stage.value,
            }
        )
    for items in buckets.values():
        items.sort(key=lambda item: (item["due_date"], item["sequence"], item["id"]))
    total = sum(len(items) for items in buckets.values())
    return {
        "generated_at": now.isoformat(),
        "total_questions": total,
        "tracks": {
            "preview": buckets.get(ReviewStage.PREVIEW.value, []),
            "first_pass": buckets.get(ReviewStage.FIRST.value, []),
            "second_pass": buckets.get(ReviewStage.SECOND.value, []),
            "interval": buckets.get(ReviewStage.INTERVAL.value, []),
            "mastered": buckets.get(ReviewStage.MASTERED.value, []),
        },
        "summary": {
            stage: len(buckets.get(stage, []))
            for stage in (
                ReviewStage.PREVIEW.value,
                ReviewStage.FIRST.value,
                ReviewStage.SECOND.value,
                ReviewStage.INTERVAL.value,
                ReviewStage.MASTERED.value,
            )
        },
        "method": "jinzhi-inspired-local-spaced-review",
    }


def export_knowledge_mindmap(questions: Iterable[Question], output_path: str | Path) -> Path:
    """Export a Markdown mind-map of knowledge points -> wrong questions."""

    tree: dict[str, list[str]] = defaultdict(list)
    for question in questions:
        points = question.official_knowledge_points or ["未标注知识点"]
        label = f"Q{question.sequence} {(question.stem_md or '')[:40]}".strip()
        if question.is_correct is False:
            label = f"❌ {label}"
        elif question.is_correct is True:
            label = f"✅ {label}"
        else:
            label = f"❔ {label}"
        for point in points:
            tree[str(point) or "未标注知识点"].append(label)

    lines = ["# 知识点复习导图", "", f"生成时间：{datetime.now().astimezone().isoformat()}", ""]
    for point in sorted(tree):
        lines.append(f"## {point}")
        for item in tree[point]:
            lines.append(f"- {item}")
        lines.append("")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_review_plan(plan: dict[str, Any], output_json: str | Path, output_md: str | Path | None = None) -> tuple[Path, Path | None]:
    json_path = Path(output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path: Path | None = None
    if output_md is not None:
        md_path = Path(output_md)
        lines = [
            "# 复习计划",
            "",
            f"生成时间：{plan.get('generated_at')}",
            "",
            "## 汇总",
            "",
        ]
        summary = plan.get("summary") or {}
        mapping = {
            "preview": "预习",
            "first_pass": "一刷",
            "second_pass": "二刷",
            "interval": "间隔复习",
            "mastered": "已掌握",
        }
        for key, title in mapping.items():
            lines.append(f"- {title}：{summary.get(key, 0)} 题")
        lines.append("")
        tracks = plan.get("tracks") or {}
        for key, title in mapping.items():
            items = tracks.get(key) or []
            if not items:
                continue
            lines.append(f"## {title}")
            for item in items:
                lines.append(f"- [{item.get('due_date')}] {item.get('stem')}")
            lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
