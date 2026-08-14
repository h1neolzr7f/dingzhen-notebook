"""Local HMAC-authenticated receiver for Android companion frames."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from packages.core.version import __version__

from .lan_auth import EMPTY_SHA256, is_private_lan_host, verify_lan_request

_TASK_RE = re.compile(r"^/capture/([A-Za-z0-9._-]{1,80})/(\d+|complete)$")
_MAX_BODY = 8 * 1024 * 1024
_TIMESTAMP_SKEW = 300
DEFAULT_PORT = 17831


def local_ipv4_addresses() -> list[str]:
    found: list[str] = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.168.2.1", 80))
        candidate = probe.getsockname()[0]
        probe.close()
        if is_private_lan_host(candidate):
            found.append(candidate)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if is_private_lan_host(ip) and ip not in found:
                found.append(ip)
    except OSError:
        pass
    if "127.0.0.1" not in found:
        found.append("127.0.0.1")
    return found


def make_pairing_secret() -> str:
    return secrets.token_urlsafe(18)


def format_pairing_code(url: str, secret: str) -> str:
    return f"FENBI1|{url.rstrip('/')}|{secret}"


def parse_pairing_code(raw: str) -> tuple[str, str] | None:
    text = (raw or "").strip()
    if not text.startswith("FENBI1|"):
        return None
    parts = text.split("|", 2)
    if len(parts) != 3 or not parts[1] or len(parts[2].encode("utf-8")) < 16:
        return None
    return parts[1], parts[2]


class LanReceiveServer:
    def __init__(
        self,
        inbox: str | Path,
        *,
        secret: str | None = None,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        now_epoch: Callable[[], int] | None = None,
        on_frame: Callable[[str, Path, int], None] | None = None,
        on_complete: Callable[[str, list[Path]], None] | None = None,
    ) -> None:
        self.inbox = Path(inbox)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.secret = secret or make_pairing_secret()
        self.host = host
        self.port = port
        self._now_epoch = now_epoch
        self.on_frame = on_frame
        self.on_complete = on_complete
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.received: dict[str, list[Path]] = {}
        self.completed: set[str] = set()

    def pairing_codes(self) -> list[str]:
        port = self.actual_port
        return [format_pairing_code(f"http://{ip}:{port}", self.secret) for ip in local_ipv4_addresses()]

    @property
    def actual_port(self) -> int:
        if self._httpd is not None:
            return int(self._httpd.server_address[1])
        return self.port

    def start(self) -> None:
        if self._httpd is not None:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

            def do_GET(self) -> None:  # noqa: N802
                if urlparse(self.path).path == "/health":
                    self._send_json(200, {"ok": True, "version": __version__})
                    return
                self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                server._handle_post(self)

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="fenbi-lan-receive", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        match = _TASK_RE.match(urlparse(handler.path).path)
        if match is None:
            handler.send_error(404, "not_found")
            return
        task_id, item = match.group(1), match.group(2)
        length = int(handler.headers.get("Content-Length") or 0)
        if length < 0 or length > _MAX_BODY:
            handler.send_error(413, "payload_too_large")
            return
        body = handler.rfile.read(length) if length else b""
        checksum = (handler.headers.get("X-Checksum-SHA256") or "").strip().lower()
        timestamp_raw = handler.headers.get("X-Fenbi-Timestamp") or ""
        signature = handler.headers.get("X-Fenbi-Signature") or ""
        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            handler.send_error(401, "bad_timestamp")
            return
        now = self._now_epoch() if self._now_epoch is not None else time.time()
        if abs(int(now) - timestamp) > _TIMESTAMP_SKEW:
            handler.send_error(401, "timestamp_skew")
            return
        path = f"/capture/{task_id}/{item}"
        if not verify_lan_request(self.secret.encode("utf-8"), signature, "POST", path, timestamp, checksum):
            handler.send_error(401, "bad_signature")
            return
        digest = hashlib.sha256(body).hexdigest()
        if digest != checksum:
            handler.send_error(400, "checksum_mismatch")
            return
        folder = self.inbox / task_id
        folder.mkdir(parents=True, exist_ok=True)
        if item == "complete":
            if checksum != EMPTY_SHA256:
                handler.send_error(400, "checksum_mismatch")
                return
            with self._lock:
                self.completed.add(task_id)
                frames = list(self.received.get(task_id, []))
            (folder / "COMPLETE.json").write_text(
                json.dumps({"task_id": task_id, "frames": [str(path) for path in frames]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            handler.send_response(200)
            handler.send_header("X-Checksum-SHA256", checksum)
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"ok")
            if self.on_complete is not None:
                self.on_complete(task_id, frames)
            return
        destination = folder / f"{int(item):06d}.png"
        destination.write_bytes(body)
        with self._lock:
            frames = self.received.setdefault(task_id, [])
            if destination not in frames:
                frames.append(destination)
                frames.sort()
        handler.send_response(200)
        handler.send_header("X-Checksum-SHA256", checksum)
        handler.send_header("Content-Length", "2")
        handler.end_headers()
        handler.wfile.write(b"ok")
        if self.on_frame is not None:
            self.on_frame(task_id, destination, int(item))
