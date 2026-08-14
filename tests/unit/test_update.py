import hashlib
import json
from pathlib import Path

import pytest

from packages.stability.update import download_update, fetch_update_manifest, update_available


class Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        value = self.body[self.offset : self.offset + size]
        self.offset += len(value)
        return value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_https_manifest_and_atomic_verified_download(tmp_path: Path) -> None:
    installer = b"signed installer payload"
    manifest_body = json.dumps(
        {
            "version": "1.1.0",
            "installer_url": "https://updates.example/FenbiStudy-Setup.exe",
            "sha256": hashlib.sha256(installer).hexdigest(),
        }
    ).encode()

    def opener(request, timeout):
        return Response(installer if request.full_url.endswith(".exe") else manifest_body)

    manifest = fetch_update_manifest("https://updates.example/manifest.json", opener=opener)
    assert update_available("1.0.0", manifest)
    output = download_update(manifest, tmp_path / "setup.exe", opener=opener)
    assert output.read_bytes() == installer


def test_insecure_remote_update_and_wrong_checksum_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        fetch_update_manifest("http://192.168.1.2/manifest.json")
    body = json.dumps(
        {"version": "2.0.0", "installer_url": "https://example/setup.exe", "sha256": "0" * 64}
    ).encode()
    manifest = fetch_update_manifest("https://example/manifest.json", opener=lambda *a, **k: Response(body))
    with pytest.raises(ValueError, match="SHA-256"):
        download_update(manifest, tmp_path / "bad.exe", opener=lambda *a, **k: Response(b"bad"))
    assert not (tmp_path / "bad.exe").exists()
