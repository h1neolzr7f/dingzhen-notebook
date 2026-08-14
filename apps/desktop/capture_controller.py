"""Desktop capture orchestration and an injectable ADB service.

The controller deliberately lives at the application boundary.  The capture
implementation can therefore be replaced by an Android companion, a real ADB
adapter, or a deterministic fake in tests without changing the OCR workflow.
No account credentials or network calls are made by this module.
"""

from __future__ import annotations

import inspect
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from packages.capture import AdbCaptureAdapter, AdbError, RealAdbTransport


class CaptureStatus(str, Enum):
    """User-visible state of a capture session."""

    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    NO_DEVICE = "no_device"
    ERROR = "error"


class NoDeviceError(RuntimeError):
    """Raised when ADB cannot find an authorized device."""


@dataclass(frozen=True, slots=True)
class CaptureFrame:
    """One raw screenshot delivered by a capture service."""

    sequence: int
    path: Path | None = None
    data: bytes | None = None
    question_id: str | None = None
    page_kind: str = "unassigned"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CaptureSnapshot:
    """Immutable status payload sent to CLI, GUI, and tests."""

    status: CaptureStatus
    frames_captured: int = 0
    current_question: str | None = None
    message: str = ""
    error: str | None = None
    device: str | None = None


FrameCallback = Callable[[CaptureFrame], None]
StatusCallback = Callable[[CaptureSnapshot], None]


class CaptureService(Protocol):
    """Small protocol accepted by :class:`CaptureController`.

    ``start`` may be synchronous and return an iterable of frames, or invoke
    the callback while it runs.  This intentionally accommodates the Android
    bridge and a tiny FakeAdb without imposing a package-level dependency.
    """

    def start(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...

    def stop(self) -> None:
        ...


class AdbCaptureService:
    """Minimal direct-ADB screenshot service.

    It only uses the documented ``adb devices`` and ``screencap`` commands.
    Scrolling is intentionally opt-in through ``swipe_after_frame`` and never
    guesses a page transition; a production adapter can provide richer page
    detection while retaining this controller contract.
    """

    def __init__(
        self,
        *,
        output_dir: str | Path = Path("data") / "captures",
        serial: str | None = None,
        max_frames: int | None = None,
        interval_seconds: float = 0.45,
        adb_command: str = "adb",
        swipe_after_frame: bool = False,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.serial = serial
        self.max_frames = max_frames
        self.interval_seconds = max(0.0, interval_seconds)
        self.adb_command = adb_command
        self.swipe_after_frame = swipe_after_frame
        self._pause = threading.Event()
        self._stop = threading.Event()
        # Keep all device I/O and page fingerprinting in the canonical P2
        # adapter.  The service remains a small GUI/CLI protocol wrapper.
        self._adapter = AdbCaptureAdapter(
            RealAdbTransport(adb_command), session_root=self.output_dir, max_unchanged=3
        )
        self._session = None

    def _run(self, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.adb_command, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def list_devices(self) -> list[str]:
        try:
            devices = self._adapter.discover_devices()
        except (AdbError, FileNotFoundError, OSError) as exc:
            raise NoDeviceError("未找到 adb。请安装 Android platform-tools 并将 adb 加入 PATH。") from exc
        return [device.serial for device in devices if device.available]

    def _selected_serial(self) -> str:
        devices = self.list_devices()
        if self.serial and self.serial in devices:
            return self.serial
        if not devices:
            raise NoDeviceError("未检测到可用 Android 设备。请连接手机、开启 USB 调试并在手机上允许授权。")
        if self.serial:
            raise NoDeviceError(f"未找到指定设备 {self.serial!r}。可用设备：{', '.join(devices)}")
        self.serial = devices[0]
        return self.serial

    def start(self, on_frame: FrameCallback | None = None, **_: Any) -> list[CaptureFrame]:
        serial = self._selected_serial()
        self._pause.clear()
        self._stop.clear()
        frames: list[CaptureFrame] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._session = self._adapter.start_session(root=self.output_dir, serial=serial)
        display: dict[str, Any] = {"device": serial}
        try:
            info = self._adapter.device_info(serial)
            if info.screen_size:
                display["screen_size"] = list(info.screen_size.as_tuple())
            if info.density is not None:
                display["density"] = info.density
        except Exception:
            # Display metadata is useful but must not prevent raw capture.
            pass
        sequence = 0
        while not self._stop.is_set() and (self.max_frames is None or sequence < self.max_frames):
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.05)
            if self._stop.is_set():
                break
            try:
                screenshot = self._adapter.capture_frame(self._session, serial=serial)
                raw = screenshot.png
            except AdbError as exc:
                raise NoDeviceError(f"ADB 采集失败：{exc}") from exc
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError(f"ADB 截图失败：{exc}") from exc
            path = screenshot.path or self.output_dir / "raw" / f"{sequence + 1:06d}.png"
            frame = CaptureFrame(
                sequence=sequence, path=path, data=raw,
                metadata={**display, "sha256": screenshot.sha256},
            )
            frames.append(frame)
            if on_frame:
                on_frame(frame)
            sequence += 1
            if self._session.consecutive_unchanged >= self._adapter.max_unchanged:
                self._adapter.stop(self._session, "页面不再变化，本卷采集结束")
                break
            if self.swipe_after_frame and not self._stop.is_set():
                self._adapter.swipe(serial, 540, 1500, 540, 500, duration_ms=350)
            if self.interval_seconds and not self._stop.is_set():
                time.sleep(self.interval_seconds)
        if self._session is not None and self._session.active:
            self._adapter.stop(self._session, "stopped by user" if self._stop.is_set() else "frame limit reached")
        return frames

    def pause(self) -> None:
        self._pause.set()
        if self._session is not None and self._session.active:
            self._adapter.pause(self._session)

    def resume(self) -> None:
        self._pause.clear()
        if self._session is not None and self._session.paused:
            self._adapter.resume(self._session)

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()
        if self._session is not None and self._session.active:
            self._adapter.stop(self._session, "stopped by user")


class CaptureController:
    """Own a capture session and expose safe lifecycle controls.

    The controller is thread-safe from the caller's perspective.  ``start``
    waits by default (ideal for CLI/tests); the GUI passes ``wait=False`` so
    the window remains responsive.  All state transitions are published to
    ``on_status`` and every frame is published to ``on_frame``.
    """

    def __init__(
        self,
        service: CaptureService,
        *,
        output_dir: str | Path | None = None,
        on_status: StatusCallback | None = None,
        on_frame: FrameCallback | None = None,
    ) -> None:
        self.service = service
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.on_status = on_status
        self.on_frame = on_frame
        self._lock = threading.RLock()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = CaptureSnapshot(CaptureStatus.IDLE)
        self.frames: list[CaptureFrame] = []

    @property
    def snapshot(self) -> CaptureSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def status(self) -> CaptureStatus:
        return self.snapshot.status

    def _publish(self, snapshot: CaptureSnapshot) -> CaptureSnapshot:
        with self._lock:
            self._snapshot = snapshot
        if self.on_status:
            self.on_status(snapshot)
        return snapshot

    def _set_status(
        self,
        status: CaptureStatus,
        *,
        message: str = "",
        error: str | None = None,
        current_question: str | None = None,
        device: str | None = None,
    ) -> CaptureSnapshot:
        previous = self.snapshot
        return self._publish(
            CaptureSnapshot(
                status=status,
                frames_captured=len(self.frames),
                current_question=current_question if current_question is not None else previous.current_question,
                message=message,
                error=error,
                device=device if device is not None else previous.device,
            )
        )

    def _normalise_frame(self, value: Any) -> CaptureFrame:
        if isinstance(value, CaptureFrame):
            frame = value
        elif isinstance(value, (str, Path)):
            frame = CaptureFrame(sequence=len(self.frames), path=Path(value))
        elif isinstance(value, (bytes, bytearray)):
            frame = CaptureFrame(sequence=len(self.frames), data=bytes(value))
        elif isinstance(value, dict):
            payload = dict(value)
            payload.setdefault("sequence", len(self.frames))
            if payload.get("path") is not None:
                payload["path"] = Path(payload["path"])
            frame = CaptureFrame(**payload)
        else:
            path = getattr(value, "path", None)
            data = getattr(value, "data", None)
            frame = CaptureFrame(
                sequence=int(getattr(value, "sequence", len(self.frames))),
                path=Path(path) if path is not None else None,
                data=data,
                question_id=getattr(value, "question_id", None),
                page_kind=getattr(value, "page_kind", "unassigned"),
            )
        if frame.data is not None and frame.path is None:
            output = self.output_dir or Path("data") / "captures"
            output.mkdir(parents=True, exist_ok=True)
            frame = CaptureFrame(
                sequence=frame.sequence,
                path=output / f"{frame.sequence:06d}.png",
                data=frame.data,
                question_id=frame.question_id,
                page_kind=frame.page_kind,
                metadata=frame.metadata,
            )
            frame.path.write_bytes(frame.data)
        return frame

    def _handle_frame(self, value: Any) -> None:
        frame = self._normalise_frame(value)
        with self._lock:
            self.frames.append(frame)
        if self.on_frame:
            self.on_frame(frame)
        current = frame.question_id
        device = frame.metadata.get("device") if isinstance(frame.metadata, dict) else None
        if self.status is CaptureStatus.CONNECTING:
            self._set_status(CaptureStatus.RUNNING, message="正在采集", current_question=current, device=device)
        else:
            self._set_status(self.status, current_question=current, device=device)

    def _handle_service_status(self, value: Any) -> None:
        if isinstance(value, CaptureSnapshot):
            self._publish(value)
            return
        raw = getattr(value, "status", value)
        try:
            status = raw if isinstance(raw, CaptureStatus) else CaptureStatus(str(raw).lower())
        except ValueError:
            return
        message = getattr(value, "message", "")
        self._set_status(status, message=message)

    def _invoke_start(self) -> Any:
        start = getattr(self.service, "start", None) or getattr(self.service, "run", None)
        if start is None:
            raise TypeError("capture service must implement start() or run()")
        # Prefer keyword callbacks, then positional callback, then no args for
        # simple fakes.  A TypeError from inside the service is not swallowed:
        # only signature binding failures trigger a fallback.
        try:
            signature = inspect.signature(start)
            parameters = signature.parameters
            kwargs: dict[str, Any] = {}
            if "on_frame" in parameters:
                kwargs["on_frame"] = self._handle_frame
            if "frame_callback" in parameters:
                kwargs["frame_callback"] = self._handle_frame
            if "on_status" in parameters:
                kwargs["on_status"] = self._handle_service_status
            if kwargs:
                return start(**kwargs)
        except (TypeError, ValueError):
            pass
        for args in ((self._handle_frame,), ()):
            try:
                return start(*args)
            except TypeError:
                if args:
                    continue
                raise
        return None

    def _run(self) -> None:
        try:
            delivered_before = len(self.frames)
            result = self._invoke_start()
            delivered_by_callback = len(self.frames) - delivered_before
            if isinstance(result, dict) and isinstance(result.get("frames"), Iterable) and not isinstance(result.get("frames"), (str, bytes, bytearray)):
                for item in list(result["frames"])[delivered_by_callback:]:
                    self._handle_frame(item)
            elif isinstance(result, (CaptureFrame, str, bytes, bytearray, Path)):
                self._handle_frame(result)
            elif isinstance(result, dict) and ("path" in result or "data" in result):
                self._handle_frame(result)
            elif result is not None and not isinstance(result, dict):
                try:
                    for item in list(result)[delivered_by_callback:]:
                        self._handle_frame(item)
                except TypeError:
                    # A service may return a single opaque result; that is not
                    # an error as long as it delivered frames through callback.
                    pass
            if self.status not in {CaptureStatus.STOPPING, CaptureStatus.STOPPED, CaptureStatus.ERROR, CaptureStatus.NO_DEVICE}:
                self._set_status(CaptureStatus.COMPLETED, message="采集完成")
            elif self.status is CaptureStatus.STOPPING:
                self._set_status(CaptureStatus.STOPPED, message="已停止")
        except NoDeviceError as exc:
            self._set_status(CaptureStatus.NO_DEVICE, message=str(exc), error=str(exc))
        except Exception as exc:  # capture boundary: surface an actionable UI error
            # Adapters may expose their own exception type (for example
            # packages.capture.AdbError).  Preserve the friendly no-device
            # state when the error is clearly a connection/authorization
            # failure instead of forcing callers to import that type here.
            text = str(exc)
            lowered = text.lower()
            no_device_markers = ("no connected adb device", "no device", "device not found", "unauthorized", "未检测到", "未找到设备")
            if any(marker in lowered or marker in text for marker in no_device_markers):
                self._set_status(CaptureStatus.NO_DEVICE, message=text, error=text)
            else:
                self._set_status(CaptureStatus.ERROR, message=f"采集失败：{exc}", error=text)
        finally:
            self._done.set()

    def start(self, *, wait: bool = True) -> CaptureSnapshot:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self._snapshot
            self.frames.clear()
            self._done.clear()
            self._set_status(CaptureStatus.CONNECTING, message="正在检测设备")
            self._thread = threading.Thread(target=self._run, name="fenbi-capture", daemon=True)
            self._thread.start()
        if wait:
            self.wait()
        return self.snapshot

    def pause(self) -> CaptureSnapshot:
        if self.status not in {CaptureStatus.RUNNING, CaptureStatus.CONNECTING}:
            return self.snapshot
        try:
            self.service.pause()
        except AttributeError:
            self._set_status(CaptureStatus.ERROR, message="当前采集服务不支持暂停", error="pause unsupported")
            return self.snapshot
        return self._set_status(CaptureStatus.PAUSED, message="已暂停")

    def resume(self) -> CaptureSnapshot:
        if self.status is not CaptureStatus.PAUSED:
            return self.snapshot
        try:
            self.service.resume()
        except AttributeError:
            self._set_status(CaptureStatus.ERROR, message="当前采集服务不支持恢复", error="resume unsupported")
            return self.snapshot
        return self._set_status(CaptureStatus.RUNNING, message="继续采集")

    def stop(self, *, wait: bool = True) -> CaptureSnapshot:
        if self.status in {CaptureStatus.IDLE, CaptureStatus.COMPLETED, CaptureStatus.STOPPED, CaptureStatus.NO_DEVICE, CaptureStatus.ERROR}:
            return self.snapshot
        self._set_status(CaptureStatus.STOPPING, message="正在停止")
        try:
            self.service.stop()
        except AttributeError:
            pass
        if wait:
            self.wait()
        return self.snapshot

    def wait(self, timeout: float | None = None) -> CaptureSnapshot:
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        return self.snapshot


__all__ = [
    "AdbCaptureService",
    "CaptureController",
    "CaptureFrame",
    "CaptureService",
    "CaptureSnapshot",
    "CaptureStatus",
    "NoDeviceError",
]
