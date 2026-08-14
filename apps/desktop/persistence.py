"""Bridge reviewed OCR drafts into the durable question bank and exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from packages.core import (
    AttemptState,
    Evidence,
    EvidenceRegion,
    Option,
    Paper,
    PipelineStatus,
    Question,
    QuestionType,
    SQLiteRepository,
    safe_paper_id,
)
from packages.exporters import export_paper_json, export_paper_markdown

from .workflow import DesktopWorkflow


@dataclass(frozen=True, slots=True)
class SavedArtifacts:
    database: Path
    json: Path
    markdown: Path
    question_id: str
    status: PipelineStatus


def persist_group(
    workflow: DesktopWorkflow,
    group_id: str,
    *,
    database: str | Path = Path("data") / "fenbi-study.db",
    export_root: str | Path = "exports",
    paper_id: str = "paper_manual_import",
    paper_title: str = "手工截图导入试卷",
) -> SavedArtifacts:
    """Persist one reviewed group and refresh JSON/Markdown paper exports."""

    paper_id = safe_paper_id(paper_id)
    draft = workflow.drafts[group_id]
    frames = sorted(
        (image for image in workflow.images if image.group_id == group_id),
        key=lambda image: image.order,
    )
    if not frames:
        raise ValueError(f"No screenshots assigned to group {group_id!r}")

    sequence_match = re.search(r"\d+", group_id)
    sequence = int(sequence_match.group()) if sequence_match else 1
    options = [Option(label=label, content_md=content) for label, content in draft.options.items()]
    question_paths = [str(item.path) for item in frames if item.page_kind != "analysis"]
    analysis_paths = [str(item.path) for item in frames if item.page_kind == "analysis"]
    # Field-level OCR evidence is authoritative when page boundaries were not
    # manually marked. This links official content back to its source image.
    for field in ("official_answer", "official_explanation_md"):
        analysis_paths.extend(item.image_path for item in draft.evidence.get(field, []))
    if not question_paths:
        question_paths = [str(item.path) for item in frames]
    if not analysis_paths and draft.official_explanation_md:
        analysis_paths = [str(item.path) for item in frames]

    field_regions: dict[str, list[EvidenceRegion]] = {}
    for field_name, items in draft.evidence.items():
        regions: list[EvidenceRegion] = []
        for item in items:
            if item.boxes:
                regions.extend(
                    EvidenceRegion(
                        image=item.image_path,
                        bbox=box,
                        confidence=draft.field_confidence.get(field_name),
                    )
                    for box in item.boxes
                )
            else:
                regions.append(
                    EvidenceRegion(
                        image=item.image_path,
                        bbox=None,
                        confidence=draft.field_confidence.get(field_name),
                    )
                )
        field_regions[field_name] = regions

    question = Question(
        id=Question.stable_id("fenbi", paper_id, sequence, draft.stem_md, options),
        paper_id=paper_id,
        sequence=sequence,
        question_type=QuestionType.OTHER,
        stem_md=draft.stem_md,
        options=options,
        user_answer=draft.user_answer if "user_answer" in draft.evidence else None,
        official_answer=draft.official_answer or None,
        is_correct=(set(draft.user_answer) == set(draft.official_answer))
        if "user_answer" in draft.evidence and draft.official_answer
        else None,
        attempt_state=AttemptState.UNANSWERED
        if "user_answer" in draft.evidence and not draft.user_answer
        else AttemptState.ANSWERED
        if "user_answer" in draft.evidence
        else AttemptState.UNKNOWN,
        official_explanation_md=draft.official_explanation_md or None,
        # A manually reviewed field without OCR confidence is unknown, not 0.
        # Persisting 0 would incorrectly keep a fully corrected record in the
        # low-confidence queue forever.
        ocr_confidence=draft.ocr_confidence or None,
        parse_confidence=min(draft.field_confidence.values()) if draft.field_confidence else None,
        evidence=Evidence(
            question_frames=list(dict.fromkeys(question_paths)),
            analysis_frames=list(dict.fromkeys(analysis_paths)),
            field_regions=field_regions,
        ),
    )

    database_path = Path(database)
    repository = SQLiteRepository(database_path)
    repository.create_schema()
    paper = repository.get_paper(paper_id) or Paper(id=paper_id, title=paper_title)
    repository.upsert_paper(paper)
    repository.upsert_question(question)

    questions = repository.list_questions(paper_id)
    paper.total_questions = len(questions)
    paper.answered_questions = sum(q.user_answer is not None for q in questions)
    paper.correct_questions = sum(q.is_correct is True for q in questions)
    paper.capture_status = (
        PipelineStatus.VERIFIED
        if questions and all(q.verification_status == PipelineStatus.VERIFIED for q in questions)
        else PipelineStatus.NEEDS_REVIEW
    )
    repository.upsert_paper(paper)

    output = Path(export_root) / paper_id
    json_path = export_paper_json(repository, paper_id, output / "paper.json")
    markdown_path = export_paper_markdown(repository, paper_id, output / "paper_ai.md")
    return SavedArtifacts(database_path, json_path, markdown_path, question.id, question.verification_status)
