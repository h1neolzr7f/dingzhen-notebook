import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from packages.capture import (
    EMPTY_SHA256,
    LanReceiveServer,
    format_pairing_code,
    is_allowed_lan_endpoint,
    parse_pairing_code,
    sign_lan_request,
)
from packages.core import __version__


def _post(base: str, secret: str, path: str, body: bytes, timestamp: int | None = None):
    checksum = hashlib.sha256(body).hexdigest()
    ts = int(time.time()) if timestamp is None else timestamp
    signature = sign_lan_request(secret.encode("utf-8"), "POST", path, ts, checksum)
    request = urllib.request.Request(
        base + path,
        data=body,
        method="POST",
        headers={
            "X-Checksum-SHA256": checksum,
            "X-Fenbi-Timestamp": str(ts),
            "X-Fenbi-Signature": signature,
        },
    )
    return urllib.request.urlopen(request, timeout=3)


def test_pairing_code_roundtrip() -> None:
    code = format_pairing_code("http://192.168.1.8:17831/", "correct-horse-battery")
    parsed = parse_pairing_code(code)
    assert parsed == ("http://192.168.1.8:17831", "correct-horse-battery")
    assert is_allowed_lan_endpoint("http://192.168.1.8:17831")
    assert is_allowed_lan_endpoint("http://127.0.0.1:17831")
    assert not is_allowed_lan_endpoint("http://8.8.8.8:17831")
    assert is_allowed_lan_endpoint("https://example.com")


def test_lan_server_accepts_signed_frame_and_complete(tmp_path: Path) -> None:
    finished: list[tuple[str, list[Path]]] = []
    server = LanReceiveServer(
        tmp_path / "inbox",
        secret="correct-horse-battery",
        host="127.0.0.1",
        port=0,
        on_complete=lambda task_id, paths: finished.append((task_id, paths)),
    )
    server.start()
    try:
        base = f"http://127.0.0.1:{server.actual_port}"
        health = json.loads(urllib.request.urlopen(base + "/health", timeout=3).read().decode("utf-8"))
        assert health["ok"] is True
        assert health["version"] == __version__
        body = b"\x89PNG-frame"
        response = _post(base, server.secret, "/capture/task-a/0", body)
        assert response.headers["X-Checksum-SHA256"] == hashlib.sha256(body).hexdigest()
        saved = tmp_path / "inbox" / "task-a" / "000000.png"
        assert saved.read_bytes() == body
        _post(base, server.secret, "/capture/task-a/complete", b"")
        assert finished and finished[0][0] == "task-a"
        assert finished[0][1] == [saved]
        assert (tmp_path / "inbox" / "task-a" / "COMPLETE.json").is_file()
        assert hashlib.sha256(b"").hexdigest() == EMPTY_SHA256
    finally:
        server.stop()


def test_lan_server_rejects_bad_signature(tmp_path: Path) -> None:
    server = LanReceiveServer(tmp_path / "inbox", secret="correct-horse-battery", host="127.0.0.1", port=0)
    server.start()
    try:
        base = f"http://127.0.0.1:{server.actual_port}"
        request = urllib.request.Request(
            base + "/capture/task-a/0",
            data=b"nope",
            method="POST",
            headers={
                "X-Checksum-SHA256": hashlib.sha256(b"nope").hexdigest(),
                "X-Fenbi-Timestamp": str(int(time.time())),
                "X-Fenbi-Signature": "00" * 32,
            },
        )
        try:
            urllib.request.urlopen(request, timeout=3)
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.stop()
