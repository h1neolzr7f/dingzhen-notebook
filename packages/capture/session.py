"""Durable, secret-free state for an ADB capture run.

The session model intentionally stores only progress and evidence paths.  It
does not keep an arbitrary transport/configuration dictionary, so passwords,
cookies, access tokens and similar credentials cannot accidentally be written
to a checkpoint.  Checkpoints are written atomically to make interruption
safe on Windows as well as POSIX systems.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class CaptureSessionStatus(StrEnum):
    """State machine for a capture session."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


# A compatibility alias makes the state type convenient for callers that use
# the shorter name.
CaptureStatus = CaptureSessionStatus


class CaptureStateError(RuntimeError):
    """Raised when an invalid session transition is requested."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: object, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return fallback or _now()


_SECRET_KEY = re.compile(
    r"(?:^|[_-])(token|access[_-]?token|refresh[_-]?token|password|passwd|secret|cookie|authorization|credential|account|username|login|auth|api[_-]?key|session)s?$",
    re.IGNORECASE,
)


def _safe_metadata(value: object, key: str | None = None) -> object:
    """Return JSON-compatible metadata without credential-like fields.

    Metadata is useful for harmless labels (for example an app version), but
    allowing an arbitrary mapping to be persisted has historically been a
    source of accidental credential leaks.  Credential keys are omitted and
    nested mappings/lists are traversed recursively.
    """

    if key is not None and _SECRET_KEY.search(key):
        return None
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            name = str(raw_key)
            if _SECRET_KEY.search(name):
                continue
            safe = _safe_metadata(raw_value, name)
            if safe is not None:
                result[name] = safe
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class SessionCheckpoint:
    """Small immutable progress snapshot suitable for UI status displays."""

    session_id: str
    status: CaptureSessionStatus
    current_question: int
    current_step: str
    frame_count: int
    last_screenshot_hash: str | None
    consecutive_unchanged: int
    updated_at: datetime

    @property
    def unchanged_count(self) -> int:
        return self.consecutive_unchanged

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "current_question": self.current_question,
            "current_step": self.current_step,
            "frame_count": self.frame_count,
            "last_screenshot_hash": self.last_screenshot_hash,
            "consecutive_unchanged": self.consecutive_unchanged,
            "updated_at": _iso(self.updated_at),
        }


@dataclass(slots=True)
class CaptureSession:
    """Persistable capture progress.

    ``state_path`` is optional: callers can keep a session in memory for a
    short-lived run, or pass a path to get atomic checkpoint writes after each
    frame.  ``root`` points at the session directory containing ``raw/`` and
    is persisted as a relative path where possible.
    """

    session_id: str = field(default_factory=lambda: f"capture_{uuid.uuid4().hex[:12]}")
    state_path: Path | None = None
    root: Path | None = None
    device_serial: str | None = None
    status: CaptureSessionStatus = CaptureSessionStatus.CREATED
    current_question: int = 0
    current_step: str = "start"
    frame_count: int = 0
    screenshot_hashes: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)
    last_screenshot_hash: str | None = None
    consecutive_unchanged: int = 0
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.state_path is not None:
            self.state_path = Path(self.state_path).expanduser()
        if self.root is not None:
            self.root = Path(self.root).expanduser()
        self.status = CaptureSessionStatus(self.status)
        self.created_at = _parse_datetime(self.created_at)
        self.updated_at = _parse_datetime(self.updated_at, self.created_at)
        self.current_question = max(0, int(self.current_question))
        self.frame_count = max(0, int(self.frame_count))
        self.consecutive_unchanged = max(0, int(self.consecutive_unchanged))

    @classmethod
    def create(
        cls,
        session_id: str | None = None,
        *,
        root: str | Path | None = None,
        state_path: str | Path | None = None,
        device_serial: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "CaptureSession":
        root_path = Path(root).expanduser() if root is not None else None
        state = Path(state_path).expanduser() if state_path is not None else None
        if state is None and root_path is not None:
            state = root_path / "manifest.json"
        return cls(
            session_id=session_id or f"capture_{uuid.uuid4().hex[:12]}",
            root=root_path,
            state_path=state,
            device_serial=device_serial,
            metadata=dict(metadata or {}),
        )

    @property
    def paused(self) -> bool:
        return self.status == CaptureSessionStatus.PAUSED

    @property
    def active(self) -> bool:
        return self.status in (CaptureSessionStatus.CREATED, CaptureSessionStatus.RUNNING)

    @property
    def checkpoint(self) -> SessionCheckpoint:
        return SessionCheckpoint(
            session_id=self.session_id,
            status=self.status,
            current_question=self.current_question,
            current_step=self.current_step,
            frame_count=self.frame_count,
            last_screenshot_hash=self.last_screenshot_hash,
            consecutive_unchanged=self.consecutive_unchanged,
            updated_at=self.updated_at,
        )

    @property
    def checkpoint_path(self) -> Path | None:
        """Compatibility name used by persistence/UI callers."""

        return self.state_path

    @property
    def state_file(self) -> Path | None:
        return self.state_path

    @state_file.setter
    def state_file(self, value: str | Path | None) -> None:
        self.state_path = Path(value).expanduser() if value is not None else None

    def start(self) -> "CaptureSession":
        if self.status not in (CaptureSessionStatus.CREATED, CaptureSessionStatus.PAUSED):
            raise CaptureStateError(f"cannot start a {self.status.value} session")
        self.status = CaptureSessionStatus.RUNNING
        self.error = None
        self.touch()
        return self

    def pause(self) -> "CaptureSession":
        if self.status == CaptureSessionStatus.CREATED:
            # A pause before the first frame is useful for a UI that creates a
            # task before the user connects a device.
            self.status = CaptureSessionStatus.PAUSED
        elif self.status == CaptureSessionStatus.RUNNING:
            self.status = CaptureSessionStatus.PAUSED
        elif self.status != CaptureSessionStatus.PAUSED:
            raise CaptureStateError(f"cannot pause a {self.status.value} session")
        self.touch()
        return self

    def resume(self) -> "CaptureSession":
        if self.status not in (CaptureSessionStatus.PAUSED, CaptureSessionStatus.CREATED):
            raise CaptureStateError(f"cannot resume a {self.status.value} session")
        self.status = CaptureSessionStatus.RUNNING
        self.error = None
        self.touch()
        return self

    def stop(self, reason: str | None = None) -> "CaptureSession":
        if self.status in (CaptureSessionStatus.COMPLETED, CaptureSessionStatus.ERROR):
            return self
        self.status = CaptureSessionStatus.STOPPED
        if reason:
            self.error = str(reason)
        self.touch()
        return self

    def complete(self) -> "CaptureSession":
        if self.status == CaptureSessionStatus.ERROR:
            raise CaptureStateError("cannot complete a failed session")
        self.status = CaptureSessionStatus.COMPLETED
        self.error = None
        self.touch()
        return self

    def fail(self, error: object) -> "CaptureSession":
        self.status = CaptureSessionStatus.ERROR
        self.error = str(error)[:2000]
        self.touch()
        return self

    def touch(self) -> None:
        self.updated_at = _now()

    def set_progress(
        self,
        *,
        current_question: int | None = None,
        current_step: str | None = None,
    ) -> "CaptureSession":
        if current_question is not None:
            self.current_question = max(0, int(current_question))
        if current_step is not None:
            self.current_step = str(current_step)
        self.touch()
        return self

    def record_screenshot(
        self,
        screenshot_hash: str,
        path: str | Path | None = None,
        *,
        changed: bool | None = None,
    ) -> "CaptureSession":
        """Record one raw screenshot and update stable-page progress.

        ``changed`` can be supplied by a detector.  If omitted, the stable
        hash is compared with the previous frame.
        """

        value = str(screenshot_hash)
        previous = self.last_screenshot_hash
        if changed is None:
            changed = previous is None or previous != value
        self.frame_count += 1
        self.screenshot_hashes.append(value)
        if path is not None:
            self.screenshot_paths.append(str(path))
        self.last_screenshot_hash = value
        self.consecutive_unchanged = 0 if changed else self.consecutive_unchanged + 1
        self.touch()
        return self

    def to_dict(self) -> dict[str, object]:
        # Keep this allow-list explicit.  In particular, transport command
        # lines and arbitrary caller metadata are never serialized wholesale.
        safe_metadata = _safe_metadata(self.metadata)
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "root": str(self.root) if self.root is not None else None,
            "device_serial": self.device_serial,
            "status": self.status.value,
            "current_question": self.current_question,
            "current_step": self.current_step,
            "frame_count": self.frame_count,
            "screenshot_hashes": list(self.screenshot_hashes),
            "screenshot_paths": list(self.screenshot_paths),
            "last_screenshot_hash": self.last_screenshot_hash,
            "consecutive_unchanged": self.consecutive_unchanged,
            "error": self.error,
            "metadata": safe_metadata if isinstance(safe_metadata, dict) else {},
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, state_path: str | Path | None = None) -> "CaptureSession":
        """Load known fields while ignoring forward-compatible unknown keys."""

        status_raw = payload.get("status", CaptureSessionStatus.CREATED.value)
        try:
            status = CaptureSessionStatus(str(status_raw))
        except ValueError:
            status = CaptureSessionStatus.CREATED
        return cls(
            session_id=str(payload.get("session_id") or f"capture_{uuid.uuid4().hex[:12]}"),
            state_path=state_path,
            root=payload.get("root"),
            device_serial=(str(payload["device_serial"]) if payload.get("device_serial") else None),
            status=status,
            current_question=int(payload.get("current_question", 0) or 0),
            current_step=str(payload.get("current_step", "start")),
            frame_count=int(payload.get("frame_count", 0) or 0),
            screenshot_hashes=[str(item) for item in payload.get("screenshot_hashes", []) if item],
            screenshot_paths=[str(item) for item in payload.get("screenshot_paths", []) if item],
            last_screenshot_hash=(str(payload["last_screenshot_hash"]) if payload.get("last_screenshot_hash") else None),
            consecutive_unchanged=int(payload.get("consecutive_unchanged", payload.get("unchanged_count", 0)) or 0),
            error=(str(payload["error"]) if payload.get("error") else None),
            metadata=dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {},
            created_at=_parse_datetime(payload.get("created_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
        )

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path).expanduser() if path is not None else self.state_path
        if destination is None:
            if self.root is None:
                raise ValueError("a state path or session root is required")
            destination = self.root / "manifest.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.state_path = destination
        data = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        # NamedTemporaryFile is used instead of an in-place write so an
        # interrupted process cannot leave a half-written JSON checkpoint.
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.",
                suffix=".tmp", delete=False
            ) as stream:
                temp_name = stream.name
                stream.write(data)
                stream.flush()
            Path(temp_name).replace(destination)
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
        return destination

    # Explicit method aliases keep checkpoint call-sites readable and make it
    # obvious that ``checkpoint`` (the property above) is an in-memory view.
    save_checkpoint = save
    persist = save

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> "CaptureSession":
        source = Path(path).expanduser()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("capture session state must be a JSON object")
        return cls.from_dict(payload, state_path=source)

    from_json_file = load


def save_capture_session(session: CaptureSession, path: str | Path | None = None) -> Path:
    return session.save(path)


def load_capture_session(path: str | Path) -> CaptureSession:
    return CaptureSession.load(path)


__all__ = [
    "CaptureSession",
    "CaptureSessionStatus",
    "CaptureStatus",
    "CaptureStateError",
    "SessionCheckpoint",
    "load_capture_session",
    "save_capture_session",
]
