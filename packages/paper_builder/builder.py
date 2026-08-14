"""Build blank practice papers, answer sheets and provenance-aware books.

The builder produces self-contained HTML (always available) and can render the
same document to PDF through :mod:`packages.exporters.pdf_exporter`.  It only
reads official fields from ``Question``; no answer is inferred while building
an artifact.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.analysis.analyzer import (
    filter_repeated_wrong_questions,
    filter_risk_questions,
    filter_special_questions,
    filter_wrong_questions,
    resolve_questions,
)
from packages.core.models import Paper, PipelineStatus, Question
from packages.core.repository import SQLiteRepository


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _answer(value: list[str] | None) -> str:
    if value is None:
        return "未采集"
    if not value:
        return "未作答"
    return ", ".join(value)


def _status(question: Question) -> tuple[str, bool]:
    verified = question.verification_status in {PipelineStatus.VERIFIED, PipelineStatus.EXPORTED}
    return question.verification_status.value, verified


def _page(title: str, body: str, *, paper: Paper | None = None) -> str:
    paper_title = paper.title if paper else title
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="generator" content="fenbi-study-pipeline P3">
<title>{title}</title>
<style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; color: #1f2937; line-height: 1.55; }}
h1 {{ border-bottom: 2px solid #111827; padding-bottom: .2em; }}
h2 {{ margin-top: 1.6em; color: #111827; }}
.meta {{ color: #4b5563; font-size: .9em; }}
.question {{ break-inside: avoid; border-bottom: 1px solid #d1d5db; padding: 0 0 1em; margin: 0 0 1em; }}
.option {{ margin-left: 1.5em; }}
.answer-box {{ display: inline-block; min-width: 3.2em; height: 1.25em; border: 1px solid #374151; margin: 0 .25em; vertical-align: middle; }}
.answer-line {{ border-bottom: 1px solid #6b7280; display: inline-block; min-width: 75%; height: 1.4em; }}
.warning {{ border: 1px solid #d97706; background: #fffbeb; padding: .6em; }}
.official {{ border-left: 4px solid #2563eb; padding-left: .8em; }}
.unverified {{ border-left-color: #d97706; }}
.small {{ font-size: .86em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #d1d5db; padding: .35em .5em; text-align: left; }}
th {{ background: #f3f4f6; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">试卷：{paper_title}</p>
{body}
</body>
</html>
""".format(title=_esc(title), paper_title=_esc(paper_title), body=body)


def _question_content(question: Question, *, include_answer_line: bool = True) -> str:
    options = "".join(
        f'<div class="option"><strong>{_esc(option.label)}.</strong> {_esc(option.content_md)}</div>'
        for option in question.options
    )
    line = '<p>作答：<span class="answer-line"></span></p>' if include_answer_line else ""
    return (
        f'<article class="question" data-question-id="{_esc(question.id)}">'
        f"<h2>{question.sequence}. {_esc(question.section or '')}</h2>"
        f"<p>{_esc(question.stem_md or '（题干未采集）')}</p>{options}{line}</article>"
    )


def render_wrong_paper_html(paper: Paper, questions: Iterable[Question]) -> str:
    values = filter_wrong_questions(questions)
    body = (
        f'<p class="meta">共 {len(values)} 道错题。此卷为空白练习卷，不展示粉笔正确答案和官方解析。</p>'
        + ("".join(_question_content(q) for q in values) or "<p>没有明确判定为错误的题目。</p>")
    )
    return _page("错题空白卷", body, paper=paper)


def render_answer_sheet_html(paper: Paper, questions: Iterable[Question]) -> str:
    values = sorted(list(questions), key=lambda q: (q.sequence, q.id))
    rows = []
    for question in values:
        labels = "".join('<span class="answer-box"></span>' for _ in (question.options or [None]))
        rows.append(
            f'<tr data-question-id="{_esc(question.id)}"><td>{question.sequence}</td>'
            f"<td>{_esc(getattr(question.question_type, 'value', question.question_type))}</td><td>{labels}</td></tr>"
        )
    body = (
        f"<p class=\"meta\">试卷题数：{len(values)}。答题卡不包含任何预填答案。</p>"
        '<table><thead><tr><th>题号</th><th>题型</th><th>作答</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )
    return _page("答题卡", body, paper=paper)


def render_explanation_book_html(paper: Paper, questions: Iterable[Question]) -> str:
    """Render official answer/explanation with an explicit review boundary."""

    blocks: list[str] = []
    for question in sorted(list(questions), key=lambda q: (q.sequence, q.id)):
        status, verified = _status(question)
        css = "official" if verified else "official unverified"
        warning = "" if verified else '<p class="warning">该题尚未验证（NEEDS_REVIEW 或其他状态），以下内容不能视为已核验结论。</p>'
        points = ", ".join(question.official_knowledge_points) or "未采集"
        # Values below are deliberately read directly from Question.  The
        # ``data-source`` markers make this invariant straightforward to test
        # in exported HTML.
        official_answer = _answer(question.official_answer)
        explanation = question.official_explanation_md or "未采集"
        blocks.append(
            f'<article class="question" data-question-id="{_esc(question.id)}">'
            f"<h2>{question.sequence}. {_esc(question.section or '')}</h2>"
            f"<p>{_esc(question.stem_md or '（题干未采集）')}</p>"
            f"<p>用户答案：{_esc(_answer(question.user_answer))}</p>"
            f'<div class="{css}" data-source="Question.official_answer">'
            f"<p><strong>粉笔正确答案：</strong>{_esc(official_answer)}</p>"
            f'<p data-source="Question.official_explanation_md"><strong>粉笔官方解析：</strong><br>{_esc(explanation)}</p>'
            f"<p>知识点：{_esc(points)}</p><p class=\"small\">状态：{_esc(status)}；verified={str(verified).lower()}</p>"
            f"</div>{warning}</article>"
        )
    return _page("答案解析册", "".join(blocks) or "<p>暂无题目。</p>", paper=paper)


def render_special_paper_html(paper: Paper, questions: Iterable[Question], *, title: str = "专项训练卷") -> str:
    values = list(questions)
    body = f'<p class="meta">共 {len(values)} 道题，按筛选条件生成的空白训练卷。</p>' + (
        "".join(_question_content(q) for q in values) or "<p>筛选结果为空。</p>"
    )
    return _page(title, body, paper=paper)


@dataclass(slots=True)
class PaperBuildResult:
    """Paths and HTML strings produced by :func:`build_paper_bundle`."""

    wrong_paper: Path | None = None
    answer_sheet: Path | None = None
    explanation_book: Path | None = None
    special_paper: Path | None = None
    html: dict[str, str] | None = None

    def paths(self) -> list[Path]:
        return [path for path in (self.wrong_paper, self.answer_sheet, self.explanation_book, self.special_paper) if path]


def _write_document(content: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".pdf":
        from packages.exporters.pdf_exporter import html_to_pdf

        html_to_pdf(content, destination)
    else:
        destination.write_text(content, encoding="utf-8")
    return destination


def build_paper_bundle(
    paper_or_repository: Paper | SQLiteRepository,
    questions_or_paper_id: Iterable[Question] | str,
    destination: str | Path,
    *,
    formats: Iterable[str] = ("pdf",),
    special_knowledge_points: Iterable[str] | None = None,
    special_section: str | None = None,
    special_tags: Iterable[str] | None = None,
) -> PaperBuildResult:
    """Create all P3 artifacts in ``destination``.

    ``formats`` can contain ``pdf`` and/or ``html``.  For PDF-only output the
    returned paths are PDFs; HTML strings are returned as well for callers that
    want to preview or verify provenance.
    """

    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required to build a paper bundle")
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    wrong = render_wrong_paper_html(paper, values)
    sheet = render_answer_sheet_html(paper, values)
    explanation = render_explanation_book_html(paper, values)
    special_values = filter_special_questions(
        values,
        knowledge_points=special_knowledge_points,
        section=special_section,
        tags=special_tags,
    )
    special = render_special_paper_html(paper, special_values)
    html_map = {"wrong_paper": wrong, "answer_sheet": sheet, "explanation_book": explanation, "special_paper": special}
    wanted = {str(fmt).lower().lstrip(".") for fmt in formats}
    result = PaperBuildResult(html=html_map)
    if "pdf" in wanted:
        result.wrong_paper = _write_document(wrong, root / "01_wrong_paper.pdf")
        result.answer_sheet = _write_document(sheet, root / "02_answer_sheet.pdf")
        result.explanation_book = _write_document(explanation, root / "03_explanation_book.pdf")
        result.special_paper = _write_document(special, root / "04_special_paper.pdf")
    if "html" in wanted:
        _write_document(wrong, root / "01_wrong_paper.html")
        _write_document(sheet, root / "02_answer_sheet.html")
        _write_document(explanation, root / "03_explanation_book.html")
        _write_document(special, root / "04_special_paper.html")
    return result


def build_wrong_paper(paper_or_repository: Paper | SQLiteRepository, questions_or_paper_id: Iterable[Question] | str, destination: str | Path) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    return _write_document(render_wrong_paper_html(paper, values), Path(destination))


def build_answer_sheet(paper_or_repository: Paper | SQLiteRepository, questions_or_paper_id: Iterable[Question] | str, destination: str | Path) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    return _write_document(render_answer_sheet_html(paper, values), Path(destination))


def build_explanation_book(paper_or_repository: Paper | SQLiteRepository, questions_or_paper_id: Iterable[Question] | str, destination: str | Path) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    return _write_document(render_explanation_book_html(paper, values), Path(destination))


def build_special_paper(
    paper_or_repository: Paper | SQLiteRepository,
    questions_or_paper_id: Iterable[Question] | str,
    destination: str | Path,
    *,
    knowledge_points: Iterable[str] | None = None,
    section: str | None = None,
    tags: Iterable[str] | None = None,
) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    selected = filter_special_questions(values, knowledge_points=knowledge_points, section=section, tags=tags)
    return _write_document(render_special_paper_html(paper, selected), Path(destination))


def build_risk_paper(paper_or_repository: Paper | SQLiteRepository, questions_or_paper_id: Iterable[Question] | str, destination: str | Path) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    return _write_document(render_special_paper_html(paper, filter_risk_questions(values), title="风险题训练卷"), Path(destination))


def build_repeated_wrong_paper(paper_or_repository: Paper | SQLiteRepository, questions_or_paper_id: Iterable[Question] | str, destination: str | Path) -> Path:
    paper, values = resolve_questions(paper_or_repository, questions_or_paper_id)
    if paper is None:
        raise TypeError("a Paper or repository is required")
    return _write_document(render_special_paper_html(paper, filter_repeated_wrong_questions(values), title="重复错题训练卷"), Path(destination))


__all__ = [
    "PaperBuildResult",
    "build_answer_sheet",
    "build_explanation_book",
    "build_paper_bundle",
    "build_repeated_wrong_paper",
    "build_risk_paper",
    "build_special_paper",
    "build_wrong_paper",
    "render_answer_sheet_html",
    "render_explanation_book_html",
    "render_special_paper_html",
    "render_wrong_paper_html",
]
