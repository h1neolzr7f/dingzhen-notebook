"""End-to-end bridge from raw capture frames to reviewable study artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from packages.analysis import analyze_paper
from packages.core import PipelineStatus, SQLiteRepository, safe_paper_id
from packages.exporters import export_analysis_json, export_analysis_markdown
from packages.ocr import OcrEngine, OcrResult, classify_ocr_text
from packages.paper_builder import build_paper_bundle

from .persistence import SavedArtifacts, persist_group
from .workflow import DesktopWorkflow


class CachingOcrEngine:
    def __init__(self, inner: OcrEngine) -> None:
        self.inner = inner
        self.cache: dict[Path, OcrResult] = {}

    def recognize(self, image_path: Path) -> OcrResult:
        key = Path(image_path).resolve()
        if key not in self.cache:
            self.cache[key] = self.inner.recognize(Path(image_path))
        return self.cache[key]


@dataclass(frozen=True, slots=True)
class CaptureProcessingResult:
    database: Path
    paper_json: Path
    paper_markdown: Path
    analysis_json: Path
    analysis_markdown: Path
    explanation_book: Path
    paper_bundle: Path
    questions: int
    review_count: int
    groups: tuple[str, ...]
    workflow: DesktopWorkflow


@dataclass(frozen=True, slots=True)
class StudyOutputResult:
    analysis_json: Path
    analysis_markdown: Path
    explanation_book: Path
    paper_bundle: Path
    questions: int
    review_count: int


def rebuild_paper_outputs(
    database: str | Path,
    paper_id: str,
    *,
    export_root: str | Path = "exports",
) -> StudyOutputResult:
    """Regenerate deterministic analysis and printable papers from SQLite."""

    repository = SQLiteRepository(database)
    repository.create_schema()
    paper_id = safe_paper_id(paper_id)
    paper = repository.get_paper(paper_id)
    if paper is None:
        raise KeyError(f"试卷不存在：{paper_id}")
    questions = repository.list_questions(paper_id)
    report = analyze_paper(paper, questions)
    output = Path(export_root) / paper_id
    analysis_json = export_analysis_json(report, output / "analysis.json")
    analysis_markdown = export_analysis_markdown(report, output / "analysis_ai.md")
    bundle_dir = output / "paper_bundle"
    bundle = build_paper_bundle(paper, questions, bundle_dir, formats=("pdf", "html"))
    if bundle.explanation_book is None:
        raise RuntimeError("答案解析册生成失败")
    return StudyOutputResult(
        analysis_json=analysis_json,
        analysis_markdown=analysis_markdown,
        explanation_book=bundle.explanation_book,
        paper_bundle=bundle_dir,
        questions=len(questions),
        review_count=sum(q.verification_status == PipelineStatus.NEEDS_REVIEW for q in questions),
    )


def auto_assign_captured_images(workflow: DesktopWorkflow) -> tuple[str, ...]:
    """Group pages by OCR; one question keeps its stem and analysis frames together."""

    current = 1
    previous_complete = False
    group_ids: list[str] = []
    assigned = []
    for image in sorted(workflow.images, key=lambda item: item.order):
        page = classify_ocr_text(workflow.engine.recognize(image.path).text)
        if page.skip:
            continue
        if page.question_number is not None:
            current = page.question_number
        elif previous_complete and page.page_kind == "question":
            current += 1
        group_id = f"q{current:03d}"
        if group_id not in group_ids:
            group_ids.append(group_id)
        assigned.append(replace(image, group_id=group_id, page_kind=page.page_kind))
        previous_complete = page.complete or page.paper_ended
    workflow.images = assigned
    return tuple(group_ids)


def classify_and_persist(
    workflow: DesktopWorkflow,
    *,
    database: str | Path,
    export_root: str | Path,
    paper_id: str,
    paper_title: str,
) -> CaptureProcessingResult:
    """OCR → 分题 → 完整性检查 → SQLite → 组卷. Mutates *workflow* drafts."""

    paper_id = safe_paper_id(paper_id)
    if not workflow.images:
        raise ValueError("没有可识别的截图")
    cached = workflow.engine if isinstance(workflow.engine, CachingOcrEngine) else CachingOcrEngine(workflow.engine)
    workflow.engine = cached
    groups = auto_assign_captured_images(workflow)
    if not groups:
        raise ValueError("OCR 没有识别出题目。请确认截图是已完成、带解析的试卷。")
    saved: list[SavedArtifacts] = []
    for group_id in groups:
        workflow.recognize_group(group_id)
        saved.append(
            persist_group(
                workflow,
                group_id,
                database=database,
                export_root=export_root,
                paper_id=paper_id,
                paper_title=paper_title,
            )
        )
    outputs = rebuild_paper_outputs(database, paper_id, export_root=export_root)
    review_count = sum(item.status == PipelineStatus.NEEDS_REVIEW for item in saved)
    return CaptureProcessingResult(
        database=Path(database),
        paper_json=saved[-1].json,
        paper_markdown=saved[-1].markdown,
        analysis_json=outputs.analysis_json,
        analysis_markdown=outputs.analysis_markdown,
        explanation_book=outputs.explanation_book,
        paper_bundle=outputs.paper_bundle,
        questions=outputs.questions,
        review_count=max(review_count, outputs.review_count),
        groups=groups,
        workflow=workflow,
    )


def process_capture_frames(
    frames: Iterable[str | Path],
    *,
    engine: OcrEngine,
    workspace: str | Path = ".",
    database: str | Path | None = None,
    paper_id: str = "paper_adb_capture",
    paper_title: str = "ADB 整卷采集",
) -> CaptureProcessingResult:
    """Run import → OCR → grouping → integrity → SQLite → analysis/PDF."""

    paper_id = safe_paper_id(paper_id)
    root = Path(workspace).resolve()
    database_path = Path(database) if database is not None else root / "data" / "fenbi-study.db"
    export_root = root / "exports"
    workflow = DesktopWorkflow(CachingOcrEngine(engine))
    imported = workflow.import_paths(frames, root / "data" / "imports" / paper_id)
    if not imported:
        raise ValueError("没有可处理的采集截图")
    return classify_and_persist(
        workflow,
        database=database_path,
        export_root=export_root,
        paper_id=paper_id,
        paper_title=paper_title,
    )


__all__ = [
    "CachingOcrEngine",
    "CaptureProcessingResult",
    "StudyOutputResult",
    "auto_assign_captured_images",
    "classify_and_persist",
    "process_capture_frames",
    "rebuild_paper_outputs",
]
