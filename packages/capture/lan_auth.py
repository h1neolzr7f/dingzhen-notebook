"""HMAC pairing used by the Android companion and the desktop receiver."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from urllib.parse import urlparse

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def sign_lan_request(secret: bytes, method: str, path: str, timestamp: int, checksum: str) -> str:
    message = f"{method.upper()}\n{path}\n{timestamp}\n{checksum}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_lan_request(
    secret: bytes,
    signature: str,
    method: str,
    path: str,
    timestamp: int,
    checksum: str,
) -> bool:
    expected = sign_lan_request(secret, method, path, timestamp, checksum).encode("ascii")
    actual = (signature or "").strip().lower().encode("ascii")
    return hmac.compare_digest(expected, actual)


def is_private_lan_host(host: str) -> bool:
    value = (host or "").strip().lower().strip("[]")
    if value in {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}:
        return True
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


def is_allowed_lan_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() == "https":
        return bool(parsed.hostname)
    if parsed.scheme.lower() != "http":
        return False
    return is_private_lan_host(parsed.hostname or "")
