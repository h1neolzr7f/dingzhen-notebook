"""Lossless screenshot importing with deterministic ordering and deduplication."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True, slots=True)
class ImportedImage:
    """Metadata for one immutable raw screenshot."""

    path: Path
    source_path: Path
    checksum_sha256: str
    width: int
    height: int
    captured_at: datetime
    order: int
    group_id: str = "unassigned"
    page_kind: str = "unassigned"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "source_path": str(self.source_path),
            "checksum_sha256": self.checksum_sha256,
            "width": self.width,
            "height": self.height,
            "captured_at": self.captured_at.isoformat(),
            "order": self.order,
            "group_id": self.group_id,
            "page_kind": self.page_kind,
        }


def natural_sort_key(path: str | Path) -> tuple[object, ...]:
    """Sort human-style so ``shot2`` precedes ``shot10``."""

    value = Path(path).name.casefold()
    return tuple(int(piece) if piece.isdigit() else piece for piece in re.split(r"(\d+)", value))


def scan_images(paths: Iterable[str | Path]) -> list[Path]:
    """Expand files/directories into a unique, naturally sorted image list."""

    found: dict[Path, None] = {}
    for raw_path in paths:
        candidate = Path(raw_path).expanduser()
        if candidate.is_dir():
            entries = candidate.rglob("*")
        else:
            entries = (candidate,)
        for entry in entries:
            if entry.is_file() and entry.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS:
                found[entry.resolve()] = None
    return sorted(found, key=natural_sort_key)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _captured_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def import_images(
    paths: Iterable[str | Path],
    destination: str | Path | None = None,
) -> list[ImportedImage]:
    """Import screenshots, deduplicating by content hash.

    If *destination* is supplied, files are copied under ``raw/`` with a
    checksum-prefixed name. Existing files are reused and never overwritten.
    """

    sources = scan_images(paths)
    target_root = Path(destination).expanduser().resolve() / "raw" if destination else None
    if target_root:
        target_root.mkdir(parents=True, exist_ok=True)

    imported: list[ImportedImage] = []
    seen: set[str] = set()
    for source in sources:
        checksum = _sha256(source)
        if checksum in seen:
            continue
        seen.add(checksum)
        target = source
        if target_root:
            target = target_root / f"{checksum[:12]}_{source.name}"
            if not target.exists():
                shutil.copy2(source, target)
            # Keep deterministic Mock OCR fixtures usable after import.
            sidecar = Path(f"{source}.ocr.json")
            target_sidecar = Path(f"{target}.ocr.json")
            if sidecar.exists() and not target_sidecar.exists():
                shutil.copy2(sidecar, target_sidecar)
        with Image.open(target) as image:
            width, height = image.size
        imported.append(
            ImportedImage(
                path=target,
                source_path=source,
                checksum_sha256=checksum,
                width=width,
                height=height,
                captured_at=_captured_at(source),
                order=len(imported),
            )
        )
    return imported


def assign_group(
    images: Iterable[ImportedImage],
    indexes: Iterable[int],
    group_id: str,
    page_kind: str = "unassigned",
) -> list[ImportedImage]:
    """Return a new list with selected rows assigned to a logical question."""

    selected = set(indexes)
    return [
        replace(image, group_id=group_id, page_kind=page_kind) if index in selected else image
        for index, image in enumerate(images)
    ]
