"""Normalize objective-question choice labels without inventing answers."""

from __future__ import annotations

import re

_CHOICE = re.compile(r"[A-H]", re.IGNORECASE)
_UNANSWERED = {"未作答", "未答", "没做", "未填写"}


def parse_choice_answers(text: str | None) -> list[str] | None:
    """Return ``None`` if nothing was captured, ``[]`` if explicitly unanswered."""

    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    if raw in _UNANSWERED:
        return []
    labels = list(dict.fromkeys(item.upper() for item in _CHOICE.findall(raw)))
    return labels or None
