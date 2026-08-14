"""Human-readable, AI-oriented Markdown export with official provenance."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from packages.core.models import Paper, PipelineStatus, Question
from packages.core.repository import SQLiteRepository

from ._resolve import resolve_paper


def _yaml_string(value: object) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _answer(value: list[str] | None) -> str:
    if value is None:
        return "未采集"
    if not value:
        return "未作答"
    return "、".join(value)


def _media_path(path: str, assets_prefix: str | None) -> str:
    posix = PurePosixPath(path.replace("\\", "/"))
    return str(PurePosixPath(assets_prefix) / posix.name) if assets_prefix else str(posix)


def render_paper_markdown(
    paper: Paper, questions: Iterable[Question], *, assets_prefix: str | None = None
) -> str:
    ordered = sorted(questions, key=lambda q: (q.sequence, q.id))
    verified = bool(ordered) and all(
        q.verification_status in {PipelineStatus.VERIFIED, PipelineStatus.EXPORTED} for q in ordered
    )
    lines = [
        "---",
        "schema_version: 1",
        f"platform: {_yaml_string(paper.platform)}",
        f"paper_id: {_yaml_string(paper.id)}",
        f"title: {_yaml_string(paper.title)}",
        f"subject: {_yaml_string(paper.subject)}",
        f"total_questions: {paper.total_questions}",
        f"answered_questions: {paper.answered_questions}",
        f"correct_questions: {paper.correct_questions}",
        f"score: {'null' if paper.score is None else paper.score}",
        f"verified: {str(verified).lower()}",
        "---",
        "",
        "# 试卷基本信息",
        "",
        f"- 试卷：{paper.title}",
        f"- 完成时间：{paper.completed_at.isoformat() if paper.completed_at else '未知'}",
        f"- 总题数：{paper.total_questions}",
        f"- 正确题数：{paper.correct_questions}",
        f"- 总分：{paper.score if paper.score is not None else '未知'}",
    ]
    for q in ordered:
        lines += [
            "",
            f"# 第{q.sequence}题",
            "",
            "## 基本信息",
            "",
            f"- 模块：{q.section or '未识别'}",
            f"- 知识点：{'、'.join(q.official_knowledge_points) or '未识别'}",
            f"- 题型：{q.question_type.value}",
            f"- 用户答案：{_answer(q.user_answer)}",
            f"- 粉笔正确答案：{_answer(q.official_answer)}",
            f"- 作答结果：{'正确' if q.is_correct is True else '错误' if q.is_correct is False else '未知'}",
            f"- 作答时间：{str(q.duration_seconds) + '秒' if q.duration_seconds is not None else '未知'}",
            f"- 校对状态：{q.verification_status.value}",
            "",
            "## 题干",
            "",
            q.stem_md or "（未识别）",
        ]
        if q.options:
            lines += ["", "## 选项", ""]
            lines += [f"{option.label}. {option.content_md}" for option in q.options]
        lines += [
            "",
            "## 粉笔官方解析",
            "",
            q.official_explanation_md or "（未采集；NEEDS_REVIEW）",
            "",
            "## 粉笔标注知识点",
            "",
        ]
        lines += [f"- {point}" for point in q.official_knowledge_points] or ["- 未识别"]
        lines += ["", "## AI分析预留区", "", "尚未分析。", "", "## 原始证据", ""]
        paths = [*q.evidence.question_frames, *q.evidence.analysis_frames]
        lines += [f"- `{_media_path(path, assets_prefix)}`" for path in paths] or ["- 缺少证据（NEEDS_REVIEW）"]
    return "\n".join(lines) + "\n"


def export_paper_markdown(
    paper_or_repository: Paper | SQLiteRepository,
    questions_or_paper_id: Iterable[Question] | str,
    destination: str | Path,
    *,
    assets_prefix: str | None = None,
) -> Path:
    paper, questions = resolve_paper(paper_or_repository, questions_or_paper_id)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_paper_markdown(paper, questions, assets_prefix=assets_prefix), encoding="utf-8")
    return output


export_markdown = export_paper_markdown
