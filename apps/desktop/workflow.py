"""UI-independent import/OCR workflow used by both GUI and CLI."""

from __future__ import annotations

import json
from dataclasses import replace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from packages.image_processing import ImportedImage, assign_group, import_images
from packages.ocr import OcrEngine, ParsedQuestionDraft, parse_question_fields


@dataclass(slots=True)
class DesktopWorkflow:
    engine: OcrEngine
    images: list[ImportedImage] = field(default_factory=list)
    drafts: dict[str, ParsedQuestionDraft] = field(default_factory=dict)

    def import_paths(self, paths: Iterable[str | Path], destination: str | Path | None = None) -> list[ImportedImage]:
        self.images = import_images(paths, destination)
        return self.images

    def assign(self, indexes: Iterable[int], group_id: str, page_kind: str) -> None:
        self.images = assign_group(self.images, indexes, group_id, page_kind)

    def move(self, index: int, offset: int) -> int:
        """Move a screenshot in the review order and return its new index."""

        target = max(0, min(len(self.images) - 1, index + offset))
        if not self.images or target == index:
            return index
        self.images[index], self.images[target] = self.images[target], self.images[index]
        self.images = [replace(image, order=position) for position, image in enumerate(self.images)]
        return target

    def recognize_group(self, group_id: str) -> ParsedQuestionDraft:
        selected = sorted(
            (image for image in self.images if image.group_id == group_id),
            key=lambda image: image.order,
        )
        if not selected:
            raise ValueError(f"No screenshots assigned to group {group_id!r}")
        result = parse_question_fields(self.engine.recognize(image.path) for image in selected)
        self.drafts[group_id] = result
        return result

    def save_draft(self, group_id: str, destination: str | Path) -> Path:
        draft = self.drafts[group_id]
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "group_id": group_id,
            "screenshots": [image.to_dict() for image in self.images if image.group_id == group_id],
            "question": draft.to_dict(),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
