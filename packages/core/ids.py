"""Stable, path-safe paper identifiers."""

from __future__ import annotations

import re
from datetime import datetime

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def new_paper_id(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return safe_paper_id(f"{prefix}_{stamp}")


def safe_paper_id(paper_id: str) -> str:
    raw = str(paper_id).strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("试卷编号不合法")
    cleaned = _SAFE.sub("_", raw).strip("._-")
    if not cleaned:
        raise ValueError("试卷编号不合法")
    return cleaned
