from __future__ import annotations

import json
import subprocess
from io import BytesIO

from PIL import Image

from packages.capture import (
    AdbCaptureAdapter,
    CaptureSession,
    CaptureSessionStatus,
    DeviceInfo,
    FakeAdbTransport,
    PageChangeDetector,
    RealAdbTransport,
    detect_page_change,
    parse_devices_output,
    parse_wm_density,
    parse_wm_size,
    stable_image_hash,
)


def png(color: str, size: tuple[int, int] = (4, 3)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format="PNG")
    return stream.getvalue()


def test_fake_transport_discovery_display_and_input_calls():
    fake = FakeAdbTransport(
        devices=[DeviceInfo("abc", state="device", model="Pixel")],
        frames=[png("red")],
        screen_size=(1080, 2400),
        density=420,
    )
    adapter = AdbCaptureAdapter(fake)

    assert adapter.discover_devices() == [DeviceInfo("abc", state="device", model="Pixel")]
    assert adapter.wm_size("abc") == (1080, 2400)
    assert adapter.wm_density("abc") == 420
    adapter.tap("abc", 10, 20)
    adapter.swipe("abc", 10, 20, 10, 400, duration_ms=500)
    assert ("abc", ("shell", "input", "tap", "10", "20")) in fake.calls
    assert ("abc", ("shell", "input", "swipe", "10", "20", "10", "400", "500")) in fake.calls


def test_parsers_accept_standard_adb_output():
    devices = parse_devices_output(
        "List of devices attached\nabc\tdevice product:foo model:Pixel_8 device:shiba transport_id:2\noff\toffline\n"
    )
    assert devices[0].serial == "abc"
    assert devices[0].model == "Pixel_8"
    assert devices[1].state == "offline"
    assert parse_wm_size("Physical size: 1080x2400\nOverride size: 720x1600\n") == (720, 1600)
    assert parse_wm_density("Physical density: 440\nOverride density: 420\n") == 420


def test_stable_hash_ignores_png_container_and_detector_stops_after_three_repeats():
    first = png("red")
    second = png("red")
    third = png("blue")
    assert stable_image_hash(first) == stable_image_hash(second)
    assert detect_page_change(first, second) is False
    assert detect_page_change(first, third) is True
    detector = PageChangeDetector(max_unchanged=3)
    assert detector.observe(first).changed is True
    assert detector.observe(second).should_stop is False
    assert detector.observe(second).should_stop is False
    assert detector.observe(second).should_stop is True


def test_capture_session_is_atomic_resumable_and_secret_free(tmp_path):
    session = CaptureSession.create(
        "s1",
        root=tmp_path / "s1",
        device_serial="abc",
        metadata={"account": "alice", "token": "do-not-save", "label": "offline"},
    )
    session.start().record_screenshot("hash-1", "raw/000001.png")
    path = session.save()
    raw = path.read_text(encoding="utf-8")
    assert "do-not-save" not in raw and "alice" not in raw
    loaded = CaptureSession.load(path)
    assert loaded.status == CaptureSessionStatus.RUNNING
    assert loaded.frame_count == 1
    loaded.pause().save()
    resumed = CaptureSession.load(path)
    assert resumed.paused
    resumed.resume()
    assert resumed.status == CaptureSessionStatus.RUNNING


def test_adapter_capture_persists_png_and_safely_stops_on_unchanged(tmp_path):
    fake = FakeAdbTransport(frames=[png("red")])
    adapter = AdbCaptureAdapter(fake, session_root=tmp_path, max_unchanged=3)
    session = adapter.start_session("demo", serial="FAKE-DEVICE")
    frames = adapter.run(session, max_frames=10)

    assert len(frames) == 4  # first frame + three unchanged observations
    assert session.status == CaptureSessionStatus.STOPPED
    assert session.consecutive_unchanged == 3
    assert len(list((tmp_path / "demo" / "raw").glob("*.png"))) == 4
    assert json.loads((tmp_path / "demo" / "manifest.json").read_text(encoding="utf-8"))["frame_count"] == 4


def test_adapter_run_turns_transport_errors_into_error_state(tmp_path):
    fake = FakeAdbTransport(frames=[png("red")])
    fake.fail_next(("screencap", "-p"))
    adapter = AdbCaptureAdapter(fake, session_root=tmp_path)
    session = adapter.start_session("failed", serial="FAKE-DEVICE")
    assert adapter.run(session, max_frames=1) == []
    assert session.status == CaptureSessionStatus.ERROR
    assert "fake failure" in (session.error or "")


def test_real_transport_uses_injected_executable_without_shell():
    seen: list[list[str]] = []

    def runner(command, **kwargs):
        seen.append(command)
        if command[1:] == ["devices", "-l"]:
            return subprocess.CompletedProcess(command, 0, b"List of devices attached\nabc\tdevice\n", b"")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    transport = RealAdbTransport("custom-adb", runner=runner)
    assert transport.devices()[0].serial == "abc"
    assert seen == [["custom-adb", "devices", "-l"]]
