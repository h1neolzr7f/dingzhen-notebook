"""OCR-text page labels used by capture grouping and auto-stop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DEFAULTS = {
    "question_number": r"(?:第\s*)?(\d{1,3})\s*(?:题|[、./])",
    "user_answer": ("你的答案", "我的答案", "用户答案"),
    "official_answer": ("正确答案", "参考答案", "官方答案"),
    "explanation": ("答案解析", "官方解析"),
    "end_markers": ("知识点", "题目来源", "本题用时", "下一题"),
    "paper_end": ("已是最后一题", "没有下一题", "本卷已结束", "查看报告", "练习报告", "交卷成功", "返回报告"),
    "skip": ("手机号登录", "验证码登录", "密码登录", "登录粉笔"),
    "next_question": ("下一题", "下一题>"),
}


@lru_cache(maxsize=1)
def load_page_markers() -> dict[str, object]:
    markers = dict(_DEFAULTS)
    path = Path(__file__).resolve().parents[2] / "config" / "page_markers.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key == "schema_version":
                continue
            markers[key] = tuple(value) if isinstance(value, list) else value
    return markers


@dataclass(frozen=True, slots=True)
class PageClass:
    question_number: int | None
    page_kind: str
    complete: bool
    paper_ended: bool
    skip: bool
    has_next_question: bool


def classify_ocr_text(text: str) -> PageClass:
    markers = load_page_markers()
    raw = text or ""
    skip = any(marker in raw for marker in markers["skip"])
    number = re.search(str(markers["question_number"]), raw)
    analysis_marks = (*markers["user_answer"], *markers["official_answer"], *markers["explanation"])
    is_analysis = any(marker in raw for marker in analysis_marks)
    complete = (
        any(marker in raw for marker in markers["user_answer"])
        and any(marker in raw for marker in markers["official_answer"])
        and any(marker in raw for marker in markers["explanation"])
        and any(marker in raw for marker in markers["end_markers"])
    )
    has_next = any(marker in raw for marker in markers["next_question"])
    ended = any(marker in raw for marker in markers["paper_end"]) or (complete and not has_next)
    return PageClass(
        question_number=int(number.group(1)) if number else None,
        page_kind="analysis" if is_analysis else "question",
        complete=complete,
        paper_ended=ended and not skip,
        skip=skip,
        has_next_question=has_next,
    )
