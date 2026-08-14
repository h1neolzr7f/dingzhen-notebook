"""Heuristic, evidence-preserving parser for Chinese question screenshots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from packages.core.answers import parse_choice_answers

from .models import BoundingBox, OcrLine, OcrResult

_OPTION = re.compile(r"^\s*([A-H])\s*[\.、．:]\s*(.+)$", re.IGNORECASE)
_USER_ANSWER = re.compile(
    r"(?:你的答案|我的答案|用户答案|作答)\s*[：:]?\s*([A-H](?:\s*[,，、/;]?\s*[A-H])*|未作答|未答)",
    re.IGNORECASE,
)
_OFFICIAL_ANSWER = re.compile(
    r"(?:正确答案|参考答案|官方答案)\s*[：:]?\s*([A-H](?:\s*[,，、/;]?\s*[A-H])*)",
    re.IGNORECASE,
)
_EXPLANATION = re.compile(r"(?:官方解析|答案解析|解析)\s*[：:]?\s*(.*)$")


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    image_path: str
    line_indexes: tuple[int, ...]
    boxes: tuple[BoundingBox, ...]

    def to_dict(self) -> dict[str, object]:
        return {"image": self.image_path, "line_indexes": list(self.line_indexes), "bboxes": list(self.boxes)}


@dataclass(slots=True)
class ParsedQuestionDraft:
    stem_md: str = ""
    options: dict[str, str] = field(default_factory=dict)
    # None = not captured; [] = explicitly recognized as unanswered.
    user_answer: list[str] | None = None
    official_answer: list[str] | None = None
    official_explanation_md: str = ""
    ocr_confidence: float = 0.0
    field_confidence: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, list[FieldEvidence]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reviewed: bool = False

    @property
    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.stem_md:
            missing.append("stem_md")
        # An explicitly recognized “未作答” is a valid user-answer state even
        # though its normalized answer list is empty.
        if "user_answer" not in self.evidence:
            missing.append("user_answer")
        if not self.official_answer:
            missing.append("official_answer")
        if not self.official_explanation_md:
            missing.append("official_explanation_md")
        return missing

    @property
    def verification_status(self) -> str:
        if self.missing_required_fields:
            return "needs_review"
        return "verified" if self.reviewed else "pending_review"

    def to_dict(self) -> dict[str, object]:
        return {
            "stem_md": self.stem_md,
            "options": [{"label": label, "content_md": value} for label, value in self.options.items()],
            "user_answer": self.user_answer,
            "official_answer": self.official_answer,
            "official_explanation_md": self.official_explanation_md,
            "ocr_confidence": self.ocr_confidence,
            "field_confidence": self.field_confidence,
            "verification_status": self.verification_status,
            "reviewed": self.reviewed,
            "missing_required_fields": self.missing_required_fields,
            "warnings": self.warnings,
            "evidence": {key: [item.to_dict() for item in values] for key, values in self.evidence.items()},
        }


def parse_question_fields(results: OcrResult | Iterable[OcrResult]) -> ParsedQuestionDraft:
    """Extract fields without ever inventing a missing official value."""

    pages = [results] if isinstance(results, OcrResult) else list(results)
    draft = ParsedQuestionDraft()
    stem_lines: list[str] = []
    explanation_lines: list[str] = []
    in_explanation = False

    for page in pages:
        draft.warnings.extend(page.warnings)
        for index, line in enumerate(page.lines):
            text = _clean(line.text)
            if not text:
                continue
            user_match = _USER_ANSWER.search(text)
            official_match = _OFFICIAL_ANSWER.search(text)
            explanation_match = _EXPLANATION.search(text)
            option_match = _OPTION.match(text)
            if user_match:
                draft.user_answer = parse_choice_answers(user_match.group(1))
                if draft.user_answer is None and user_match.group(1).strip() in {"未作答", "未答"}:
                    draft.user_answer = []
                _record(draft, "user_answer", page, index, line)
                continue
            if official_match:
                draft.official_answer = parse_choice_answers(official_match.group(1))
                _record(draft, "official_answer", page, index, line)
                continue
            if explanation_match:
                in_explanation = True
                remainder = explanation_match.group(1).strip()
                if remainder:
                    explanation_lines.append(remainder)
                _record(draft, "official_explanation_md", page, index, line)
                continue
            if in_explanation:
                explanation_lines.append(text)
                _record(draft, "official_explanation_md", page, index, line)
            elif option_match:
                draft.options[option_match.group(1).upper()] = option_match.group(2).strip()
                _record(draft, "options", page, index, line)
            elif not _looks_like_ui_chrome(text):
                stem_lines.append(text)
                _record(draft, "stem_md", page, index, line)

    draft.stem_md = "\n".join(stem_lines).strip()
    draft.official_explanation_md = "\n".join(explanation_lines).strip()
    all_lines = [line for page in pages for line in page.lines]
    draft.ocr_confidence = (
        sum(line.confidence for line in all_lines) / len(all_lines) if all_lines else 0.0
    )
    if "user_answer" not in draft.evidence:
        draft.warnings.append("缺少用户答案；不得用正确答案代填。")
    if not draft.official_answer:
        draft.warnings.append("缺少粉笔正确答案；不得猜测。")
    if not draft.official_explanation_md:
        draft.warnings.append("缺少粉笔官方解析；该题不能标记完成。")
    return draft


def _record(draft: ParsedQuestionDraft, field_name: str, page: OcrResult, index: int, line: OcrLine) -> None:
    evidence = FieldEvidence(
        image_path=str(page.image_path),
        line_indexes=(index,),
        boxes=(line.bbox,) if line.bbox else (),
    )
    draft.evidence.setdefault(field_name, []).append(evidence)
    existing = draft.field_confidence.get(field_name)
    draft.field_confidence[field_name] = line.confidence if existing is None else min(existing, line.confidence)


def _clean(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def _looks_like_ui_chrome(value: str) -> bool:
    return bool(re.fullmatch(r"(?:收藏|纠错|笔记|上一题|下一题|查看解析|答题卡|退出)", value))
