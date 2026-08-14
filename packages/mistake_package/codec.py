"""今知错题本 `jinzhi-mistake-package` v1 兼容编解码。

对照 https://www.jinzhi.fun/correction/download 官网 SPA 中的
错题包制作器 schema 实现。本地优先：不上传云端，仅 ZIP + manifest.json。
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from packages.core.models import (
    AttemptState,
    MediaItem,
    Option,
    Paper,
    PipelineStatus,
    Question,
    QuestionType,
)

PACKAGE_FORMAT = "jinzhi-mistake-package"
SCHEMA_VERSION = 1
_MEDIA_RE = re.compile(r"^media/[^/\\]+$")
_MAX_ZIP_ENTRIES = 2000
_MAX_ZIP_FILE = 20 * 1024 * 1024
_MAX_ZIP_TOTAL = 200 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _content_block(text: str = "", images: list[str] | None = None, audio: list[str] | None = None) -> dict[str, Any]:
    return {"text": text or "", "images": list(images or []), "audio": list(audio or [])}


def _answer_text(values: list[str] | None) -> str:
    if not values:
        return ""
    return "".join(values)


def _parse_answers(text: str) -> list[str]:
    raw = re.split(r"[ ,，、;；|/]+", (text or "").strip().upper())
    return [item for item in raw if item]


def validate_package(document: Mapping[str, Any]) -> list[str]:
    """Return human-readable validation errors; empty means OK."""

    errors: list[str] = []
    if document.get("format") != PACKAGE_FORMAT:
        errors.append(f"format 必须是 {PACKAGE_FORMAT}")
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION}")
    folders = document.get("folders")
    mistakes = document.get("mistakes")
    if not isinstance(folders, list) or not folders:
        errors.append("folders 不能为空")
    if not isinstance(mistakes, list) or not mistakes:
        errors.append("至少包含一道错题")
    folder_ids = set()
    for folder in folders or []:
        if not isinstance(folder, Mapping):
            errors.append("folder 必须是对象")
            continue
        fid = str(folder.get("id") or "")
        if not fid:
            errors.append("folder.id 必填")
        if fid in folder_ids:
            errors.append(f"folder.id 重复: {fid}")
        folder_ids.add(fid)
    media_refs: set[str] = set()
    for index, mistake in enumerate(mistakes or [], start=1):
        if not isinstance(mistake, Mapping):
            errors.append(f"第 {index} 题不是对象")
            continue
        mid = str(mistake.get("id") or f"第{index}题")
        kind = str(mistake.get("kind") or "legacy")
        if kind not in {"legacy", "interactive"}:
            errors.append(f"{mid}: kind 仅支持 legacy/interactive")
        folder_id = str(mistake.get("folder_id") or "")
        if folder_ids and folder_id not in folder_ids:
            errors.append(f"{mid}: folder_id 不存在: {folder_id}")
        for field in ("question", "standard_answer", "user_solution"):
            block = mistake.get(field) or {}
            if not isinstance(block, Mapping):
                errors.append(f"{mid}.{field} 必须是对象")
                continue
            images = block.get("images") or []
            audio = block.get("audio") or []
            if not isinstance(images, list) or not isinstance(audio, list):
                errors.append(f"{mid}.{field} images/audio 必须是数组")
                continue
            for path in [*images, *audio]:
                path_s = str(path)
                if not _MEDIA_RE.match(path_s) or ".." in path_s:
                    errors.append(f"{mid}: 媒体路径必须 media/文件名，收到 {path_s}")
                else:
                    media_refs.add(path_s)
            text = str(block.get("text") or "").strip()
            if field == "question" and not text and not images and not audio:
                errors.append(f"{mid}: 题目内容为空")
        if kind == "legacy" and mistake.get("interaction") is not None:
            errors.append(f"{mid}: 普通错题不能包含 interaction")
        if kind == "interactive":
            interaction = mistake.get("interaction") or {}
            if not isinstance(interaction, Mapping):
                errors.append(f"{mid}: interaction 必须是对象")
            else:
                itype = str(interaction.get("type") or "")
                if itype not in {"single", "multiple", "judge", "blank", "subjective"}:
                    errors.append(f"{mid}: interaction.type 不受支持: {itype}")
    return errors


def package_from_questions(
    paper: Paper,
    questions: Iterable[Question],
    *,
    title: str | None = None,
    only_wrong: bool = True,
) -> dict[str, Any]:
    """Build a jinzhi-compatible package document from Fenbi domain models."""

    folder_id = "default"
    mistakes: list[dict[str, Any]] = []
    for question in questions:
        if only_wrong and question.is_correct is True:
            continue
        kind = "interactive" if question.options else "legacy"
        q_images = [f"media/{Path(item.path).name}" for item in question.media if item.type == "image"]
        # Prefer original evidence frames if media list empty.
        if not q_images:
            for frame in question.evidence.question_frames[:4]:
                q_images.append(f"media/{Path(frame).name}")
        analysis_images = [f"media/{Path(frame).name}" for frame in question.evidence.analysis_frames[:4]]
        options = [
            {
                "key": option.label,
                "text": option.content_md,
                "is_correct": option.label in (question.official_answer or []),
            }
            for option in question.options
        ]
        interaction = None
        if kind == "interactive":
            qtype = question.question_type
            if qtype is QuestionType.MULTIPLE_CHOICE:
                itype = "multiple"
            elif qtype is QuestionType.TRUE_FALSE:
                itype = "judge"
            else:
                itype = "single"
            interaction = {
                "type": itype,
                "options": options,
                "answer": _answer_text(question.official_answer),
                "analysis": question.official_explanation_md or "",
                "passage": None,
            }
        mistake = {
            "id": question.id,
            "kind": kind,
            "folder_id": folder_id,
            "question": _content_block(question.stem_md, q_images),
            "standard_answer": _content_block(
                _answer_text(question.official_answer),
                analysis_images if not interaction else [],
            ),
            "user_solution": _content_block(_answer_text(question.user_answer)),
            "note": "",
            "tags": ["粉笔导入", paper.subject or paper.platform],
            "knowledge_points": list(question.official_knowledge_points),
            "created_at": _now_iso(),
            "source": {
                "provider": "fenbi-study-pipeline",
                "paper_id": paper.id,
                "sequence": question.sequence,
                "is_correct": question.is_correct,
                "verification_status": question.verification_status.value,
            },
        }
        if interaction is not None:
            mistake["interaction"] = interaction
            if question.official_explanation_md:
                mistake["standard_answer"] = _content_block(question.official_explanation_md, analysis_images)
        mistakes.append(mistake)

    return {
        "format": PACKAGE_FORMAT,
        "schema_version": SCHEMA_VERSION,
        "title": title or paper.title or "粉笔错题包",
        "created_at": _now_iso(),
        "folders": [{"id": folder_id, "name": paper.title or "导入错题", "parent_id": None}],
        "mistakes": mistakes,
        "media": [],
        "meta": {
            "paper_id": paper.id,
            "platform": paper.platform,
            "exported_by": "fenbi-study-pipeline",
        },
    }


def questions_from_package(
    document: Mapping[str, Any],
    *,
    paper_id: str | None = None,
    paper_title: str | None = None,
) -> tuple[Paper, list[Question]]:
    """Convert package document into Fenbi Paper + Questions."""

    errors = validate_package(document)
    if errors:
        raise ValueError("; ".join(errors))

    title = paper_title or str(document.get("title") or "导入错题包")
    pid = paper_id or f"pkg_{uuid4().hex[:12]}"
    folders = {str(item.get("id")): item for item in document.get("folders") or [] if isinstance(item, Mapping)}
    questions: list[Question] = []
    for sequence, mistake in enumerate(document.get("mistakes") or [], start=1):
        if not isinstance(mistake, Mapping):
            continue
        kind = str(mistake.get("kind") or "legacy")
        q_block = mistake.get("question") or {}
        a_block = mistake.get("standard_answer") or {}
        u_block = mistake.get("user_solution") or {}
        stem = str(q_block.get("text") or "")
        images = [str(path) for path in (q_block.get("images") or [])]
        media = [MediaItem(type="image", path=path) for path in images]
        options: list[Option] = []
        official: list[str] | None = None
        explanation = str(a_block.get("text") or "") or None
        interaction = mistake.get("interaction")
        qtype = QuestionType.OTHER
        if kind == "interactive" and isinstance(interaction, Mapping):
            itype = str(interaction.get("type") or "single")
            if itype == "multiple":
                qtype = QuestionType.MULTIPLE_CHOICE
            elif itype == "judge":
                qtype = QuestionType.TRUE_FALSE
            else:
                qtype = QuestionType.SINGLE_CHOICE
            for option in interaction.get("options") or []:
                if not isinstance(option, Mapping):
                    continue
                options.append(
                    Option(
                        label=str(option.get("key") or option.get("label") or "").strip().upper() or "?",
                        content_md=str(option.get("text") or ""),
                    )
                )
            official = _parse_answers(str(interaction.get("answer") or ""))
            analysis = str(interaction.get("analysis") or "").strip()
            if analysis:
                explanation = analysis
        else:
            official = _parse_answers(str(a_block.get("text") or "")) or None
        user = _parse_answers(str(u_block.get("text") or ""))
        user_answer: list[str] | None = user if user else None
        is_correct = None
        if user_answer is not None and official is not None:
            is_correct = sorted(user_answer) == sorted(official)
        folder = folders.get(str(mistake.get("folder_id") or ""))
        section = str(folder.get("name")) if isinstance(folder, Mapping) else None
        qid = str(mistake.get("id") or f"import_{sequence}")
        questions.append(
            Question(
                id=qid,
                paper_id=pid,
                sequence=sequence,
                section=section,
                question_type=qtype,
                stem_md=stem,
                options=options,
                media=media,
                user_answer=user_answer,
                official_answer=official,
                is_correct=is_correct,
                attempt_state=AttemptState.ANSWERED if user_answer is not None else AttemptState.UNKNOWN,
                official_explanation_md=explanation,
                official_knowledge_points=[str(x) for x in (mistake.get("knowledge_points") or []) if str(x).strip()],
                source="jinzhi-mistake-package",
                verification_status=PipelineStatus.PARSED,
            )
        )
    paper = Paper(
        id=pid,
        title=title,
        platform="jinzhi-import",
        total_questions=len(questions),
        answered_questions=sum(1 for q in questions if q.user_answer is not None),
        correct_questions=sum(1 for q in questions if q.is_correct is True),
        capture_status=PipelineStatus.PARSED,
    )
    return paper, questions


def export_mistake_package(
    paper: Paper,
    questions: Iterable[Question],
    output_zip: str | Path,
    *,
    media_roots: Iterable[str | Path] | None = None,
    only_wrong: bool = True,
    title: str | None = None,
) -> Path:
    """Write a jinzhi-compatible ZIP: manifest.json + optional media/*."""

    document = package_from_questions(paper, questions, title=title, only_wrong=only_wrong)
    errors = validate_package(document)
    if errors:
        raise ValueError("; ".join(errors))

    output = Path(output_zip)
    output.parent.mkdir(parents=True, exist_ok=True)
    roots = [Path(item) for item in (media_roots or [])]
    # Collect referenced media basenames.
    needed: set[str] = set()
    for mistake in document["mistakes"]:
        for field in ("question", "standard_answer", "user_solution"):
            block = mistake.get(field) or {}
            for path in [*block.get("images", []), *block.get("audio", [])]:
                needed.add(Path(str(path)).name)

    written: set[str] = set()
    media_files: list[tuple[str, Path]] = []
    for name in sorted(needed):
        source: Path | None = None
        for root in roots:
            candidate = root / name
            if candidate.is_file():
                source = candidate
                break
            matches = list(root.rglob(name)) if root.is_dir() else []
            if matches:
                source = matches[0]
                break
        if source is None:
            continue
        arcname = f"media/{name}"
        if arcname in written:
            continue
        written.add(arcname)
        media_files.append((arcname, source))
    document["media"] = sorted(written)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        )
        for arcname, source in media_files:
            archive.write(source, arcname)
    return output


def import_mistake_package(
    package_zip: str | Path,
    *,
    extract_media_to: str | Path | None = None,
    paper_id: str | None = None,
) -> tuple[Paper, list[Question], Path | None]:
    """Read ZIP and return paper/questions; optionally extract media files."""

    path = Path(package_zip)
    media_dir: Path | None = Path(extract_media_to) if extract_media_to else None
    if media_dir is not None:
        media_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ZIP_ENTRIES:
            raise ValueError("错题包文件过多")
        total = sum(max(0, int(item.file_size)) for item in infos)
        if total > _MAX_ZIP_TOTAL:
            raise ValueError("错题包解压后超过 200MB 限制")
        names = set(archive.namelist())
        manifest_name = "manifest.json" if "manifest.json" in names else next(
            (name for name in names if name.endswith("manifest.json")),
            "",
        )
        if not manifest_name:
            raise ValueError("ZIP 中缺少 manifest.json")
        document = json.loads(_read_zip_member(archive, manifest_name).decode("utf-8"))
        if media_dir is not None:
            for name in names:
                if not name.startswith("media/") or name.endswith("/"):
                    continue
                target = media_dir / Path(name).name
                target.write_bytes(_read_zip_member(archive, name))
    paper, questions = questions_from_package(document, paper_id=paper_id)
    if media_dir is not None:
        for question in questions:
            rewritten: list[MediaItem] = []
            for item in question.media:
                local = media_dir / Path(item.path).name
                rewritten.append(MediaItem(type=item.type, path=str(local)))
            question.media = rewritten
    return paper, questions, media_dir


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > _MAX_ZIP_FILE:
        raise ValueError(f"错题包内文件过大：{name}")
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError(f"错题包路径不合法：{name}")
    return archive.read(name)
