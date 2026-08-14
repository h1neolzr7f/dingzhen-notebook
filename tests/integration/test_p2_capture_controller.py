from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from apps.desktop.capture_controller import (
    CaptureController,
    CaptureStatus,
    NoDeviceError,
)
from apps.desktop import main as desktop_main


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0"
    b"\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeAdb:
    """Deterministic ADB-shaped service; no subprocess or network access."""

    def __init__(self, frames: list[bytes] | None = None, *, block: bool = False) -> None:
        self.frames = frames or [PNG_1X1, PNG_1X1]
        self.block = block
        self.started = threading.Event()
        self.release = threading.Event()
        self.paused = threading.Event()
        self.stopped = threading.Event()

    def start(self, on_frame):
        self.started.set()
        for sequence, data in enumerate(self.frames):
            if self.stopped.is_set():
                break
            while self.paused.is_set() and not self.stopped.is_set():
                time.sleep(0.001)
            if self.block:
                self.release.wait(timeout=2)
            if self.stopped.is_set():
                break
            on_frame({"sequence": sequence, "data": data, "metadata": {"device": "fake-adb"}})
        return None

    def pause(self):
        self.paused.set()

    def resume(self):
        self.paused.clear()

    def stop(self):
        self.stopped.set()
        self.release.set()
        self.paused.clear()


def test_fake_adb_end_to_end_saves_raw_frames_and_completes(tmp_path: Path) -> None:
    service = FakeAdb([PNG_1X1, PNG_1X1])
    updates = []
    controller = CaptureController(service, output_dir=tmp_path / "raw", on_status=updates.append)

    snapshot = controller.start(wait=True)

    assert snapshot.status is CaptureStatus.COMPLETED
    assert snapshot.frames_captured == 2
    assert [frame.path for frame in controller.frames] == [tmp_path / "raw" / "000000.png", tmp_path / "raw" / "000001.png"]
    assert all(path and path.read_bytes() == PNG_1X1 for path in (frame.path for frame in controller.frames))
    assert updates[0].status is CaptureStatus.CONNECTING
    assert updates[-1].status is CaptureStatus.COMPLETED


def test_pause_resume_stop_are_forwarded_to_injected_service(tmp_path: Path) -> None:
    service = FakeAdb([PNG_1X1, PNG_1X1], block=True)
    controller = CaptureController(service, output_dir=tmp_path / "raw")
    controller.start(wait=False)
    assert service.started.wait(timeout=1)

    assert controller.pause().status is CaptureStatus.PAUSED
    assert controller.resume().status is CaptureStatus.RUNNING
    assert controller.stop(wait=False).status is CaptureStatus.STOPPING
    controller.wait(timeout=2)
    assert controller.status is CaptureStatus.STOPPED
    assert service.stopped.is_set()


def test_no_device_is_actionable_and_does_not_raise(tmp_path: Path) -> None:
    class NoDevice:
        def start(self, on_frame):
            raise NoDeviceError("未检测到可用 Android 设备")

    controller = CaptureController(NoDevice(), output_dir=tmp_path / "raw")
    snapshot = controller.start(wait=True)

    assert snapshot.status is CaptureStatus.NO_DEVICE
    assert "未检测到" in snapshot.message
    assert snapshot.error == snapshot.message


def test_capture_cli_can_be_exercised_with_fake_adb(monkeypatch, tmp_path: Path, capsys) -> None:
    service = FakeAdb([PNG_1X1])

    class FakeServiceFactory:
        def __init__(self, **kwargs):
            self._service = service

        def start(self, on_frame):
            return self._service.start(on_frame)

        def pause(self):
            return self._service.pause()

        def resume(self):
            return self._service.resume()

        def stop(self):
            return self._service.stop()

    monkeypatch.setattr(desktop_main, "AdbCaptureService", FakeServiceFactory)
    code = desktop_main.main(["capture", "--capture-output", str(tmp_path / "raw"), "--max-frames", "1"])

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["status"] == CaptureStatus.COMPLETED.value
    assert output["frames_captured"] == 1
    assert Path(output["frames"][0]).read_bytes() == PNG_1X1
