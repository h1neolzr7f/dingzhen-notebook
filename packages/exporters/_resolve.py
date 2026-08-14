from __future__ import annotations

from collections.abc import Iterable

from packages.core.models import Paper, Question
from packages.core.repository import SQLiteRepository


def resolve_paper(
    paper_or_repository: Paper | SQLiteRepository,
    questions_or_paper_id: Iterable[Question] | str,
) -> tuple[Paper, list[Question]]:
    """Support both ``(Paper, questions)`` and ``(repository, paper_id)``."""
    if isinstance(paper_or_repository, SQLiteRepository):
        if not isinstance(questions_or_paper_id, str):
            raise TypeError("repository export requires a paper_id string")
        paper = paper_or_repository.get_paper(questions_or_paper_id)
        if paper is None:
            raise KeyError(f"paper does not exist: {questions_or_paper_id}")
        return paper, paper_or_repository.list_questions(paper.id)
    if isinstance(questions_or_paper_id, str):
        raise TypeError("Paper export requires an iterable of Question objects")
    return paper_or_repository, sorted(list(questions_or_paper_id), key=lambda q: (q.sequence, q.id))
