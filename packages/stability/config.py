"""Versioned, data-only adaptation settings for devices and page variants."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class DeviceProfile(BaseModel):
    name: str
    reference_width: int = Field(default=1080, ge=1)
    reference_height: int = Field(default=2400, ge=1)
    reference_density: int = Field(default=440, ge=1)
    safe_margin: int = Field(default=16, ge=0)

    def scale_bbox(
        self,
        bbox: tuple[int, int, int, int],
        actual_width: int,
        actual_height: int,
    ) -> tuple[int, int, int, int]:
        """Scale a reference-screen region and clamp it to the actual screen."""

        sx = max(1, actual_width) / self.reference_width
        sy = max(1, actual_height) / self.reference_height
        x1, y1, x2, y2 = bbox
        left = max(0, min(actual_width, round(x1 * sx)))
        top = max(0, min(actual_height, round(y1 * sy)))
        right = max(left, min(actual_width, round(x2 * sx)))
        bottom = max(top, min(actual_height, round(y2 * sy)))
        return left, top, right, bottom


class PageProfile(BaseModel):
    name: str
    question_markers: list[str] = Field(default_factory=list)
    analysis_markers: list[str] = Field(default_factory=list)
    next_button_markers: list[str] = Field(default_factory=list)
    default_question_bbox: tuple[int, int, int, int] | None = None
    default_analysis_bbox: tuple[int, int, int, int] | None = None


class StabilityConfig(BaseModel):
    schema_version: int = 1
    ocr_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
    max_workers: int = Field(default=2, ge=1, le=32)
    max_unchanged_frames: int = Field(default=3, ge=1, le=20)
    device_profiles: list[DeviceProfile] = Field(default_factory=list)
    page_profiles: list[PageProfile] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "StabilityConfig":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return destination

