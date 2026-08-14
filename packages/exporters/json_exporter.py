"""JSON interchange export."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from packages.core.models import Paper, Question
from packages.core.repository import SQLiteRepository

from ._resolve import resolve_paper


def paper_document(paper: Paper, questions: Iterable[Question]) -> dict[str, Any]:
    ordered = sorted(questions, key=lambda q: (q.sequence, q.id))
    return {
        "schema_version": 1,
        "paper": paper.model_dump(mode="json"),
        "questions": [question.model_dump(mode="json") for question in ordered],
    }


def export_paper_json(
    paper_or_repository: Paper | SQLiteRepository,
    questions_or_paper_id: Iterable[Question] | str,
    destination: str | Path,
) -> Path:
    paper, questions = resolve_paper(paper_or_repository, questions_or_paper_id)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(paper_document(paper, questions), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


export_json = export_paper_json
