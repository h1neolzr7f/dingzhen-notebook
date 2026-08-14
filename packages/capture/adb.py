"""ADB transport, screenshot and page-change primitives.

No part of this module assumes that a handset is connected.  Tests and the
desktop UI can inject :class:`FakeAdbTransport`; :class:`RealAdbTransport`
invokes a configured executable through ``subprocess.run`` with an argument
list (never a shell command string).
"""

from __future__ import annotations

import hashlib
import re
import struct
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from PIL import Image

from .session import CaptureSession, CaptureSessionStatus


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class AdbError(RuntimeError):
    """An ADB command failed or returned an invalid result."""

    def __init__(self, message: str, *, command: Sequence[str] | None = None,
                 returncode: int | None = None, stderr: str | None = None) -> None:
        super().__init__(message)
        self.command = tuple(command or ())
        self.returncode = returncode
        self.stderr = stderr or ""


class CaptureError(RuntimeError):
    """A screenshot/capture invariant was violated."""


class DeviceState(str):
    """String constants used in ``adb devices`` output."""

    DEVICE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    NO_PERMISSIONS = "no permissions"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ScreenSize:
    width: int
    height: int

    def __iter__(self):
        yield self.width
        yield self.height

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> int:
        return (self.width, self.height)[index]

    def as_tuple(self) -> tuple[int, int]:
        return self.width, self.height

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ScreenSize):
            return self.width == other.width and self.height == other.height
        if isinstance(other, (tuple, list)) and len(other) == 2:
            return (self.width, self.height) == (int(other[0]), int(other[1]))
        return NotImplemented


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    serial: str
    state: str = DeviceState.UNKNOWN
    product: str | None = None
    model: str | None = None
    device: str | None = None
    transport_id: str | None = None
    screen_size: ScreenSize | None = None
    density: int | None = None

    @property
    def available(self) -> bool:
        return self.state == DeviceState.DEVICE

    @property
    def connected(self) -> bool:
        return self.available

    def with_display(self, size: ScreenSize | None, density: int | None) -> "DeviceInfo":
        return replace(self, screen_size=size, density=density)

    def to_dict(self) -> dict[str, object]:
        return {
            "serial": self.serial,
            "state": self.state,
            "product": self.product,
            "model": self.model,
            "device": self.device,
            "transport_id": self.transport_id,
            "screen_size": list(self.screen_size.as_tuple()) if self.screen_size else None,
            "density": self.density,
        }


class AdbTransport(Protocol):
    """Minimal injectable boundary around ADB subprocess I/O."""

    def run(self, args: Sequence[str], *, serial: str | None = None,
            timeout: float | None = None) -> bytes: ...


def _decode(value: bytes | bytearray | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8", errors="replace")


def _as_bytes(value: bytes | bytearray | memoryview | str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    return value.encode("utf-8")


class RealAdbTransport:
    """Run ADB commands without a shell.

    ``runner`` is injectable for unit tests and follows the subset of the
    ``subprocess.run`` signature used here.  The default remains the standard
    library implementation and therefore performs no network I/O itself.
    """

    def __init__(self, adb_path: str | Path = "adb", *, timeout: float = 30.0,
                 runner: Callable[..., Any] | None = None,
                 adb_executable: str | Path | None = None,
                 subprocess_runner: Callable[..., Any] | None = None) -> None:
        # ``adb_executable``/``subprocess_runner`` are explicit aliases that
        # make dependency injection discoverable without breaking the concise
        # ``adb_path``/``runner`` spelling.
        self.adb_path = str(adb_executable if adb_executable is not None else adb_path)
        self.timeout = float(timeout)
        self.runner = runner or subprocess_runner or subprocess.run

    def _command(self, args: Sequence[str], serial: str | None) -> list[str]:
        command = [self.adb_path]
        if serial:
            command.extend(("-s", str(serial)))
        command.extend(str(item) for item in args)
        return command

    def run(self, args: Sequence[str], *, serial: str | None = None,
            timeout: float | None = None) -> bytes:
        command = self._command(args, serial)
        try:
            result = self.runner(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout if timeout is None else timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdbError(f"unable to execute adb: {exc}", command=command) from exc
        returncode = int(getattr(result, "returncode", 0) or 0)
        stdout = getattr(result, "stdout", b"")
        stderr = _decode(getattr(result, "stderr", b""))
        if returncode != 0:
            detail = stderr.strip() or f"exit code {returncode}"
            raise AdbError(
                f"adb command failed: {detail}", command=command,
                returncode=returncode, stderr=stderr,
            )
        return _as_bytes(stdout)

    execute = run

    def devices(self, *, timeout: float | None = None) -> list[DeviceInfo]:
        return parse_devices_output(self.run(("devices", "-l"), timeout=timeout))

    list_devices = devices

    def shell(self, serial: str, *args: str, timeout: float | None = None) -> bytes:
        return self.run(("shell", *args), serial=serial, timeout=timeout)

    def exec_out(self, serial: str, *args: str, timeout: float | None = None) -> bytes:
        return self.run(("exec-out", *args), serial=serial, timeout=timeout)

    def screencap(self, serial: str, *, timeout: float | None = None) -> bytes:
        return self.exec_out(serial, "screencap", "-p", timeout=timeout)

    screencap_png = screencap

    def wm_size(self, serial: str, *, timeout: float | None = None) -> tuple[int, int]:
        output = _decode(self.shell(serial, "wm", "size", timeout=timeout))
        return parse_wm_size(output).as_tuple()

    get_wm_size = wm_size

    def wm_density(self, serial: str, *, timeout: float | None = None) -> int:
        output = _decode(self.shell(serial, "wm", "density", timeout=timeout))
        return parse_wm_density(output)

    get_wm_density = wm_density

    def input_swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int,
                    duration_ms: int = 300, *, timeout: float | None = None) -> bytes:
        return self.shell(
            serial, "input", "swipe", str(int(x1)), str(int(y1)),
            str(int(x2)), str(int(y2)), str(max(0, int(duration_ms))), timeout=timeout,
        )

    swipe = input_swipe

    def input_tap(self, serial: str, x: int, y: int, *, timeout: float | None = None) -> bytes:
        return self.shell(serial, "input", "tap", str(int(x)), str(int(y)), timeout=timeout)

    tap = input_tap


def parse_devices_output(output: bytes | str) -> list[DeviceInfo]:
    """Parse both ``adb devices`` and ``adb devices -l`` output."""

    rows: list[DeviceInfo] = []
    for line in _decode(_as_bytes(output)).splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices attached"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        serial, state = fields[0], fields[1]
        attr_start = 2
        if state == "no" and len(fields) > 2 and fields[2].lower() == "permissions":
            state = DeviceState.NO_PERMISSIONS
            attr_start = 3
        attrs: dict[str, str] = {}
        for field_value in fields[attr_start:]:
            if ":" in field_value:
                key, value = field_value.split(":", 1)
                attrs[key] = value
        rows.append(
            DeviceInfo(
                serial=serial,
                state=state,
                product=attrs.get("product"),
                model=attrs.get("model"),
                device=attrs.get("device"),
                transport_id=attrs.get("transport_id"),
            )
        )
    return rows


def parse_wm_size(output: bytes | str) -> ScreenSize:
    text = _decode(_as_bytes(output))
    # Prefer the active override when one is present, then physical size.  A
    # single regex also handles OEM variants that omit the ``Physical`` label.
    override = re.findall(r"(?im)^\s*override\s+size\s*:\s*([0-9]+)\s*[xX×]\s*([0-9]+)", text)
    physical = re.findall(r"(?im)^\s*physical\s+size\s*:\s*([0-9]+)\s*[xX×]\s*([0-9]+)", text)
    generic = re.findall(r"(?im)([0-9]+)\s*[xX×]\s*([0-9]+)", text)
    matches = override or physical or generic
    if not matches:
        raise AdbError("unable to parse adb wm size output")
    selected = matches[-1] if override else matches[0]
    return ScreenSize(int(selected[0]), int(selected[1]))


def parse_wm_density(output: bytes | str) -> int:
    text = _decode(_as_bytes(output))
    override = re.findall(r"(?im)^\s*override\s+density\s*:\s*([0-9]+)", text)
    physical = re.findall(r"(?im)^\s*physical\s+density\s*:\s*([0-9]+)", text)
    generic = re.findall(r"(?im)\bdensity\s*[:=]\s*([0-9]+)", text)
    matches = override or physical or generic
    if not matches:
        raise AdbError("unable to parse adb wm density output")
    return int(matches[-1])


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise CaptureError("adb screencap did not return a PNG")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception as exc:  # Pillow raises several format-specific errors.
        raise CaptureError(f"invalid PNG screenshot: {exc}") from exc


def stable_image_hash(image: bytes | bytearray | memoryview | str | Path) -> str:
    """Hash decoded pixels rather than PNG container metadata.

    PNGs produced by different Android versions can differ in compression or
    ancillary chunks while showing exactly the same page.  Canonical RGBA
    bytes plus dimensions provide a stable, deterministic page fingerprint.
    """

    if isinstance(image, (str, Path)):
        data = Path(image).read_bytes()
    else:
        data = _as_bytes(image)
    _png_dimensions(data)
    with Image.open(BytesIO(data)) as decoded:
        rgba = decoded.convert("RGBA")
        payload = rgba.tobytes()
        header = struct.pack(">II", int(rgba.width), int(rgba.height))
    return hashlib.sha256(header + payload).hexdigest()


stable_png_hash = stable_image_hash
stable_screenshot_hash = stable_image_hash
screenshot_hash = stable_image_hash


@dataclass(frozen=True, slots=True)
class Screenshot:
    """One immutable screenshot and its stable page fingerprint."""

    png: bytes
    sha256: str
    width: int
    height: int
    serial: str | None = None
    path: Path | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int | None = None

    @property
    def data(self) -> bytes:
        return self.png

    @property
    def hash(self) -> str:
        return self.sha256

    @property
    def stable_hash(self) -> str:
        return self.sha256

    @property
    def changed_key(self) -> str:
        return self.sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "serial": self.serial,
            "path": str(self.path) if self.path else None,
            "captured_at": self.captured_at.astimezone(timezone.utc).isoformat(),
            "sequence": self.sequence,
        }


def make_screenshot(data: bytes | bytearray | memoryview, *, serial: str | None = None,
                    path: str | Path | None = None, sequence: int | None = None) -> Screenshot:
    png = _as_bytes(data)
    width, height = _png_dimensions(png)
    return Screenshot(
        png=png,
        sha256=stable_image_hash(png),
        width=width,
        height=height,
        serial=serial,
        path=Path(path) if path is not None else None,
        sequence=sequence,
    )


def capture_screenshot(transport: AdbTransport, serial: str, *, output_path: str | Path | None = None,
                       sequence: int | None = None) -> Screenshot:
    """Capture one PNG through an injected transport."""

    if hasattr(transport, "screencap"):
        try:
            data = getattr(transport, "screencap")(serial)
        except TypeError:
            data = getattr(transport, "screencap")()
    elif hasattr(transport, "exec_out"):
        try:
            data = getattr(transport, "exec_out")(serial, "screencap", "-p")
        except TypeError:
            data = getattr(transport, "exec_out")("screencap", "-p")
    else:
        data = transport.run(("exec-out", "screencap", "-p"), serial=serial)
    screenshot = make_screenshot(data, serial=serial, sequence=sequence)
    if output_path is not None:
        destination = Path(output_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".tmp")
        temp.write_bytes(screenshot.png)
        temp.replace(destination)
        screenshot = replace(screenshot, path=destination)
    return screenshot


@dataclass(frozen=True, slots=True)
class PageChange:
    frame_index: int
    current_hash: str
    previous_hash: str | None
    changed: bool
    consecutive_unchanged: int
    should_stop: bool

    @property
    def unchanged_count(self) -> int:
        return self.consecutive_unchanged

    @property
    def stable(self) -> bool:
        return not self.changed


class PageChangeDetector:
    """Stable hash based page change detector with a safety stop threshold."""

    def __init__(self, *, max_unchanged: int = 3, stop_after: int | None = None) -> None:
        threshold = stop_after if stop_after is not None else max_unchanged
        if int(threshold) < 1:
            raise ValueError("max_unchanged must be at least one")
        self.max_unchanged = int(threshold)
        self.reset()

    def reset(self) -> None:
        self.frame_index = 0
        self.previous_hash: str | None = None
        self.consecutive_unchanged = 0

    def observe(self, image: Screenshot | bytes | bytearray | memoryview | str | Path) -> PageChange:
        current = image.sha256 if isinstance(image, Screenshot) else stable_image_hash(image)
        previous = self.previous_hash
        changed = previous is None or current != previous
        self.frame_index += 1
        self.consecutive_unchanged = 0 if changed else self.consecutive_unchanged + 1
        self.previous_hash = current
        return PageChange(
            frame_index=self.frame_index,
            current_hash=current,
            previous_hash=previous,
            changed=changed,
            consecutive_unchanged=self.consecutive_unchanged,
            should_stop=self.consecutive_unchanged >= self.max_unchanged,
        )

    update = observe
    check = observe

    def is_changed(self, image: Screenshot | bytes | bytearray | memoryview | str | Path) -> bool:
        return self.observe(image).changed

    has_changed = is_changed


def detect_page_change(previous: Screenshot | bytes | bytearray | memoryview | str | Path | None,
                       current: Screenshot | bytes | bytearray | memoryview | str | Path) -> bool:
    """Return whether two screenshots represent a different page."""

    if previous is None:
        return True
    old_hash = previous.sha256 if isinstance(previous, Screenshot) else stable_image_hash(previous)
    new_hash = current.sha256 if isinstance(current, Screenshot) else stable_image_hash(current)
    return old_hash != new_hash


is_page_changed = detect_page_change


class FakeAdbTransport:
    """Deterministic in-memory transport used by offline tests and demos."""

    def __init__(
        self,
        devices: Iterable[DeviceInfo | Mapping[str, object] | str] | None = None,
        frames: Iterable[bytes] | Mapping[str, Iterable[bytes] | bytes] | bytes | None = None,
        *,
        device_serial: str | None = None,
        screenshots: Iterable[bytes] | Mapping[str, Iterable[bytes] | bytes] | bytes | None = None,
        screen_frames: Iterable[bytes] | Mapping[str, Iterable[bytes] | bytes] | bytes | None = None,
        screen_size: tuple[int, int] = (1080, 2400),
        density: int = 440,
    ) -> None:
        if frames is None:
            frames = screenshots if screenshots is not None else screen_frames
        if devices is None and device_serial:
            devices = [device_serial]
        if devices is None:
            devices = [DeviceInfo("FAKE-DEVICE", state=DeviceState.DEVICE)]
        parsed: list[DeviceInfo] = []
        for item in devices:
            if isinstance(item, DeviceInfo):
                parsed.append(item)
            elif isinstance(item, str):
                parsed.append(DeviceInfo(item, state=DeviceState.DEVICE))
            elif isinstance(item, Mapping):
                parsed.append(DeviceInfo(
                    serial=str(item.get("serial", "FAKE-DEVICE")),
                    state=str(item.get("state", DeviceState.DEVICE)),
                    product=(str(item["product"]) if item.get("product") else None),
                    model=(str(item["model"]) if item.get("model") else None),
                ))
        self._devices = parsed
        self.screen_sizes: dict[str, tuple[int, int]] = {
            device.serial: tuple(map(int, screen_size)) for device in parsed
        }
        self.densities: dict[str, int] = {device.serial: int(density) for device in parsed}
        self._frames: dict[str, list[bytes]] = {}
        self._frame_index: dict[str, int] = {}
        self._errors: dict[tuple[str, ...], Exception] = {}
        self.calls: list[tuple[str | None, tuple[str, ...]]] = []
        self.commands: list[list[str]] = []
        default_serial = parsed[0].serial if parsed else "FAKE-DEVICE"
        if isinstance(frames, Mapping):
            for serial, values in frames.items():
                self.set_frames(str(serial), values)
        elif frames is not None:
            self.set_frames(default_serial, frames)

    @property
    def devices_list(self) -> list[DeviceInfo]:
        return list(self._devices)

    def devices(self, *, timeout: float | None = None) -> list[DeviceInfo]:
        self.calls.append((None, ("devices", "-l")))
        return list(self._devices)

    list_devices = devices

    def set_devices(self, devices: Iterable[DeviceInfo]) -> None:
        self._devices = list(devices)

    def set_frames(self, serial: str, frames: Iterable[bytes] | bytes) -> None:
        values = [frames] if isinstance(frames, (bytes, bytearray, memoryview)) else list(frames)
        if not values:
            raise ValueError("at least one fake PNG frame is required")
        self._frames[str(serial)] = [_as_bytes(item) for item in values]
        self._frame_index[str(serial)] = 0

    def enqueue_frame(self, serial: str, frame: bytes) -> None:
        self._frames.setdefault(str(serial), []).append(_as_bytes(frame))

    def set_screen(self, serial: str, *, size: tuple[int, int] | None = None,
                   density: int | None = None) -> None:
        if size is not None:
            self.screen_sizes[str(serial)] = tuple(map(int, size))
        if density is not None:
            self.densities[str(serial)] = int(density)

    def fail_next(self, command: Sequence[str] | str, error: Exception | None = None) -> None:
        key = (command,) if isinstance(command, str) else tuple(str(item) for item in command)
        self._errors[key] = error or AdbError(f"fake failure: {' '.join(key)}")

    def _record(self, serial: str | None, args: Sequence[str]) -> None:
        normalized = tuple(str(item) for item in args)
        self.calls.append((serial, normalized))
        self.commands.append([*([] if serial is None else ["-s", serial]), *normalized])

    def _maybe_fail(self, args: Sequence[str]) -> None:
        key = tuple(str(item) for item in args)
        error = self._errors.pop(key, None)
        if error is not None:
            raise error

    def run(self, args: Sequence[str], *, serial: str | None = None,
            timeout: float | None = None) -> bytes:
        normalized = tuple(str(item) for item in args)
        self._record(serial, normalized)
        self._maybe_fail(normalized)
        if normalized[:2] == ("devices", "-l") or normalized == ("devices",):
            lines = ["List of devices attached"]
            for device in self._devices:
                attrs = []
                for key, value in (("product", device.product), ("model", device.model),
                                    ("device", device.device), ("transport_id", device.transport_id)):
                    if value:
                        attrs.append(f"{key}:{value}")
                lines.append(" ".join([device.serial, device.state, *attrs]))
            return ("\n".join(lines) + "\n").encode("utf-8")
        if normalized[:1] == ("shell",):
            command = normalized[1:]
            if command[:2] == ("wm", "size"):
                width, height = self.screen_sizes.get(serial or "", (1080, 2400))
                return f"Physical size: {width}x{height}\n".encode()
            if command[:2] == ("wm", "density"):
                density = self.densities.get(serial or "", 440)
                return f"Physical density: {density}\n".encode()
            return b""
        if normalized[:2] == ("exec-out", "screencap"):
            return self.screencap(serial or "")
        if normalized[:2] == ("exec-out",) and normalized[2:] == ("screencap", "-p"):
            return self.screencap(serial or "")
        return b""

    def shell(self, serial: str, *args: str, timeout: float | None = None) -> bytes:
        return self.run(("shell", *args), serial=serial, timeout=timeout)

    def exec_out(self, serial: str, *args: str, timeout: float | None = None) -> bytes:
        return self.run(("exec-out", *args), serial=serial, timeout=timeout)

    def screencap(self, serial: str | None = None, *, timeout: float | None = None) -> bytes:
        if serial is None:
            serial = self._devices[0].serial if self._devices else "FAKE-DEVICE"
        self._record(serial, ("screencap", "-p"))
        self._maybe_fail(("screencap", "-p"))
        self._maybe_fail(("exec-out", "screencap", "-p"))
        values = self._frames.get(serial)
        if not values:
            raise AdbError(f"no fake frame configured for {serial}")
        index = self._frame_index.get(serial, 0)
        self._frame_index[serial] = min(index + 1, len(values) - 1)
        return values[index]

    screencap_png = screencap

    def wm_size(self, serial: str, *, timeout: float | None = None) -> tuple[int, int]:
        self._record(serial, ("wm", "size"))
        return self.screen_sizes.get(serial, (1080, 2400))

    get_wm_size = wm_size

    def wm_density(self, serial: str, *, timeout: float | None = None) -> int:
        self._record(serial, ("wm", "density"))
        return self.densities.get(serial, 440)

    get_wm_density = wm_density

    def input_swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int,
                    duration_ms: int = 300, *, timeout: float | None = None) -> bytes:
        return self.shell(serial, "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms), timeout=timeout)

    swipe = input_swipe

    def input_tap(self, serial: str, x: int, y: int, *, timeout: float | None = None) -> bytes:
        return self.shell(serial, "input", "tap", str(x), str(y), timeout=timeout)

    tap = input_tap


def _call_optional(transport: AdbTransport, names: Sequence[str], *args: Any, **kwargs: Any) -> Any:
    for name in names:
        method = getattr(transport, name, None)
        if callable(method):
            try:
                return method(*args, **kwargs)
            except TypeError:
                # A minimal test double may not accept timeout keyword args.
                kwargs.pop("timeout", None)
                return method(*args, **kwargs)
    raise AttributeError(f"transport does not implement any of {tuple(names)!r}")


class AdbCaptureAdapter:
    """High-level device/screenshot/input adapter.

    It does not OCR or infer question boundaries.  It only records immutable
    raw frames and page-change progress, leaving content interpretation to the
    P1 parser and a future OCR-driven controller.
    """

    def __init__(self, transport: AdbTransport | None = None, *, adb_path: str | Path = "adb",
                 session_root: str | Path | None = None, max_unchanged: int = 3) -> None:
        self.transport: AdbTransport = transport or RealAdbTransport(adb_path)
        self.session_root = Path(session_root).expanduser() if session_root is not None else None
        self.max_unchanged = int(max_unchanged)

    def discover_devices(self, *, include_unavailable: bool = True) -> list[DeviceInfo]:
        try:
            devices = _call_optional(self.transport, ("devices", "list_devices"))
        except AttributeError:
            raw = self.transport.run(("devices", "-l"))
            devices = parse_devices_output(raw)
        if isinstance(devices, (bytes, bytearray, str)):
            result = parse_devices_output(devices)
        else:
            result = [item if isinstance(item, DeviceInfo) else DeviceInfo(**item) for item in devices]
        return result if include_unavailable else [item for item in result if item.available]

    list_devices = discover_devices

    def connected_devices(self) -> list[DeviceInfo]:
        return self.discover_devices(include_unavailable=False)

    def device_info(self, serial: str, *, include_display: bool = True) -> DeviceInfo:
        found = next((item for item in self.discover_devices() if item.serial == serial), None)
        if found is None:
            raise AdbError(f"ADB device not found: {serial}")
        if not include_display:
            return found
        try:
            size = self.wm_size(serial)
            density = self.wm_density(serial)
        except Exception:
            return found
        return found.with_display(ScreenSize(*size), density)

    def wm_size(self, serial: str) -> tuple[int, int]:
        try:
            result = _call_optional(self.transport, ("wm_size", "get_wm_size"), serial)
        except AttributeError:
            result = self.transport.run(("shell", "wm", "size"), serial=serial)
        if isinstance(result, ScreenSize):
            return result.as_tuple()
        if isinstance(result, (tuple, list)) and len(result) == 2:
            return int(result[0]), int(result[1])
        return parse_wm_size(result).as_tuple()

    get_wm_size = wm_size

    def wm_density(self, serial: str) -> int:
        try:
            result = _call_optional(self.transport, ("wm_density", "get_wm_density"), serial)
        except AttributeError:
            result = self.transport.run(("shell", "wm", "density"), serial=serial)
        return int(result) if isinstance(result, (int, float)) else parse_wm_density(result)

    get_wm_density = wm_density

    def tap(self, serial: str, x: int, y: int) -> None:
        try:
            _call_optional(self.transport, ("input_tap", "tap"), serial, int(x), int(y))
        except AttributeError:
            self.transport.run(("shell", "input", "tap", str(int(x)), str(int(y))), serial=serial)

    input_tap = tap

    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300) -> None:
        try:
            _call_optional(
                self.transport, ("input_swipe", "swipe"), serial,
                int(x1), int(y1), int(x2), int(y2), int(duration_ms),
            )
        except AttributeError:
            self.transport.run(("shell", "input", "swipe", str(int(x1)), str(int(y1)),
                                str(int(x2)), str(int(y2)), str(max(0, int(duration_ms)))), serial=serial)

    input_swipe = swipe

    def screenshot(self, serial: str | CaptureSession, *, output_path: str | Path | None = None,
                   sequence: int | None = None) -> Screenshot:
        if isinstance(serial, CaptureSession):
            return self.capture_frame(serial)
        return capture_screenshot(self.transport, serial, output_path=output_path, sequence=sequence)

    capture_screenshot = screenshot

    def start_session(self, session_id: str | None = None, *, serial: str | None = None,
                      root: str | Path | None = None) -> CaptureSession:
        target_root = Path(root).expanduser() if root is not None else self.session_root
        if target_root is not None and session_id:
            target_root = target_root / session_id
        session = CaptureSession.create(session_id, root=target_root, device_serial=serial)
        if target_root is not None:
            target_root.mkdir(parents=True, exist_ok=True)
            (target_root / "raw").mkdir(parents=True, exist_ok=True)
            session.save()
        return session

    def _frame_path(self, session: CaptureSession) -> Path | None:
        if session.root is None:
            return None
        raw = session.root / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        return raw / f"{session.frame_count + 1:06d}.png"

    def capture_frame(self, session: CaptureSession, *, serial: str | None = None) -> Screenshot:
        if session.status == CaptureSessionStatus.CREATED:
            session.start()
        if session.status != CaptureSessionStatus.RUNNING:
            raise CaptureError(f"session is not running ({session.status.value})")
        chosen_serial = serial or session.device_serial
        if not chosen_serial:
            devices = self.connected_devices()
            if not devices:
                session.fail("no connected ADB device")
                session.save()
                raise AdbError("no connected ADB device")
            chosen_serial = devices[0].serial
            session.device_serial = chosen_serial
        try:
            screenshot = self.screenshot(chosen_serial, output_path=self._frame_path(session), sequence=session.frame_count + 1)
            change = PageChangeDetector(max_unchanged=self.max_unchanged)
            # Continue from persisted progress without requiring a full frame
            # history.  The session has the previous stable hash already.
            change.previous_hash = session.last_screenshot_hash
            change.consecutive_unchanged = session.consecutive_unchanged
            change.frame_index = session.frame_count
            observed = change.observe(screenshot)
            session.record_screenshot(screenshot.sha256, screenshot.path, changed=observed.changed)
            session.device_serial = chosen_serial
            if observed.should_stop:
                session.stop("page unchanged for safety threshold")
            session.save() if session.state_path or session.root else None
            return screenshot
        except Exception as exc:
            session.fail(exc)
            if session.state_path or session.root:
                session.save()
            raise

    capture = capture_frame

    def pause(self, session: CaptureSession) -> CaptureSession:
        session.pause()
        if session.state_path or session.root:
            session.save()
        return session

    def resume(self, session: CaptureSession) -> CaptureSession:
        session.resume()
        if session.state_path or session.root:
            session.save()
        return session

    def stop(self, session: CaptureSession, reason: str | None = None) -> CaptureSession:
        session.stop(reason)
        if session.state_path or session.root:
            session.save()
        return session

    def run(
        self,
        session: CaptureSession,
        *,
        serial: str | None = None,
        max_frames: int = 100,
        max_unchanged: int | None = None,
        action_provider: Callable[[int, Screenshot, CaptureSession], Any] | None = None,
        actions: Iterable[Any] | None = None,
        stop_on_unchanged: bool = True,
    ) -> list[Screenshot]:
        """Capture until an action provider ends the run or safety stops it.

        A provider may return ``None`` (capture again), ``False`` (stop), or
        an input tuple/dict: ``("swipe", x1, y1, x2, y2, duration_ms)`` or
        ``("tap", x, y)``.  Exceptions are recorded and stop the session;
        they are re-raised only by the direct ``capture_frame`` API.
        """

        threshold = int(max_unchanged if max_unchanged is not None else self.max_unchanged)
        if threshold < 1:
            raise ValueError("max_unchanged must be at least one")
        detector = PageChangeDetector(max_unchanged=threshold)
        detector.previous_hash = session.last_screenshot_hash
        detector.consecutive_unchanged = session.consecutive_unchanged
        detector.frame_index = session.frame_count
        frames: list[Screenshot] = []
        if session.status == CaptureSessionStatus.CREATED:
            session.start()
        if session.status != CaptureSessionStatus.RUNNING:
            return frames
        action_iterator = iter(actions) if actions is not None else None
        try:
            for _ in range(max(0, int(max_frames))):
                if session.status != CaptureSessionStatus.RUNNING:
                    break
                screenshot = self.screenshot(serial or session.device_serial or self._default_serial(),
                                              output_path=self._frame_path(session), sequence=session.frame_count + 1)
                observed = detector.observe(screenshot)
                session.record_screenshot(screenshot.sha256, screenshot.path, changed=observed.changed)
                frames.append(screenshot)
                if session.state_path or session.root:
                    session.save()
                if stop_on_unchanged and observed.should_stop:
                    session.stop("page unchanged for safety threshold")
                    if session.state_path or session.root:
                        session.save()
                    break
                if action_provider:
                    action = action_provider(len(frames) - 1, screenshot, session)
                elif action_iterator is not None:
                    try:
                        action = next(action_iterator)
                    except StopIteration:
                        action = False
                else:
                    action = None
                if action is False:
                    session.stop("stopped by action provider")
                    break
                self._apply_action(serial or session.device_serial or self._default_serial(), action)
            else:
                # Hitting max_frames is a normal bounded stop, not an error.
                if session.status == CaptureSessionStatus.RUNNING:
                    session.stop("capture frame limit reached")
            if session.state_path or session.root:
                session.save()
            return frames
        except Exception as exc:
            session.fail(exc)
            if session.state_path or session.root:
                session.save()
            return frames

    collect = run
    run_capture = run
    capture_all = run

    def _default_serial(self) -> str:
        devices = self.connected_devices()
        if not devices:
            raise AdbError("no connected ADB device")
        return devices[0].serial

    def _apply_action(self, serial: str, action: Any) -> None:
        if action is None or action is True:
            return
        if isinstance(action, Mapping):
            kind = str(action.get("type", action.get("action", ""))).lower()
            if kind == "tap":
                self.tap(serial, int(action["x"]), int(action["y"]))
            elif kind == "swipe":
                self.swipe(serial, int(action["x1"]), int(action["y1"]), int(action["x2"]),
                           int(action["y2"]), int(action.get("duration_ms", 300)))
            return
        if isinstance(action, (tuple, list)) and action:
            kind = str(action[0]).lower()
            if kind == "tap" and len(action) >= 3:
                self.tap(serial, int(action[1]), int(action[2]))
            elif kind == "swipe" and len(action) >= 5:
                self.swipe(serial, int(action[1]), int(action[2]), int(action[3]), int(action[4]),
                           int(action[5]) if len(action) > 5 else 300)


AdbCaptureController = AdbCaptureAdapter
CaptureController = AdbCaptureAdapter
AdbDevice = DeviceInfo
ADBDevice = DeviceInfo
ScreenshotArtifact = Screenshot
AdbCapture = AdbCaptureAdapter


__all__ = [
    "AdbCaptureAdapter",
    "AdbCaptureController",
    "AdbCapture",
    "AdbDevice",
    "ADBDevice",
    "CaptureController",
    "AdbError",
    "AdbTransport",
    "CaptureError",
    "DeviceInfo",
    "DeviceState",
    "FakeAdbTransport",
    "PageChange",
    "PageChangeDetector",
    "RealAdbTransport",
    "ScreenSize",
    "Screenshot",
    "ScreenshotArtifact",
    "capture_screenshot",
    "detect_page_change",
    "is_page_changed",
    "make_screenshot",
    "parse_devices_output",
    "parse_wm_density",
    "parse_wm_size",
    "stable_image_hash",
    "stable_png_hash",
    "stable_screenshot_hash",
    "screenshot_hash",
]
