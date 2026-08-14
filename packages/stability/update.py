"""HTTPS + SHA-256 update discovery and atomic installer download."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _secure_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _version_tuple(value: str) -> tuple[int, ...]:
    core = value.strip().lstrip("v").split("-", 1)[0]
    try:
        return tuple(int(part) for part in core.split("."))
    except ValueError as exc:
        raise ValueError(f"无效版本号：{value}") from exc


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    installer_url: str
    sha256: str
    release_notes: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "UpdateManifest":
        result = cls(
            version=str(value["version"]),
            installer_url=str(value["installer_url"]),
            sha256=str(value["sha256"]).lower(),
            release_notes=str(value.get("release_notes", "")),
        )
        _version_tuple(result.version)
        if not _secure_url(result.installer_url):
            raise ValueError("更新安装包必须使用 HTTPS（仅本机回环地址可使用 HTTP）")
        if len(result.sha256) != 64 or any(char not in "0123456789abcdef" for char in result.sha256):
            raise ValueError("更新清单中的 SHA-256 无效")
        return result


def fetch_update_manifest(
    manifest_url: str,
    *,
    opener: Callable[..., object] = urlopen,
    timeout: float = 15.0,
) -> UpdateManifest:
    if not _secure_url(manifest_url):
        raise ValueError("更新清单必须使用 HTTPS（仅本机回环地址可使用 HTTP）")
    request = Request(manifest_url, headers={"Accept": "application/json", "User-Agent": "FenbiStudyUpdater/1"})
    with opener(request, timeout=timeout) as response:
        if int(getattr(response, "status", 200)) >= 400:
            raise RuntimeError(f"更新服务器返回 HTTP {response.status}")
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError("更新清单超过 1 MiB 限制")
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("更新清单必须是 JSON 对象")
    return UpdateManifest.from_dict(document)


def update_available(current_version: str, manifest: UpdateManifest) -> bool:
    return _version_tuple(manifest.version) > _version_tuple(current_version)


def download_update(
    manifest: UpdateManifest,
    destination: str | Path,
    *,
    opener: Callable[..., object] = urlopen,
    timeout: float = 120.0,
    max_bytes: int = 1024 * 1024 * 1024,
) -> Path:
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(manifest.installer_url, headers={"Accept": "application/octet-stream", "User-Agent": "FenbiStudyUpdater/1"})
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".download", dir=output.parent)
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as target, opener(request, timeout=timeout) as response:
            if int(getattr(response, "status", 200)) >= 400:
                raise RuntimeError(f"更新服务器返回 HTTP {response.status}")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("更新安装包超过大小限制")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if digest.hexdigest() != manifest.sha256:
            raise ValueError("更新安装包 SHA-256 校验失败")
        Path(temporary).replace(output)
        return output
    finally:
        Path(temporary).unlink(missing_ok=True)


__all__ = ["UpdateManifest", "download_update", "fetch_update_manifest", "update_available"]
