"""Model adapters used by P5.

All adapters share a tiny ``complete`` boundary.  The default adapters are
offline (mock/callable); the HTTP adapter is deliberately limited to a local
endpoint by default and never accepts or persists an API key.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import AIAdapterError, AIConfigurationError, AIResponse, AIUsage


@runtime_checkable
class AIModelAdapter(Protocol):
    """Minimal model boundary.

    Implementations may return a mapping/list, a JSON string, or an
    :class:`AIResponse`.  Keeping the response unopinionated lets local
    models, deterministic test doubles, and HTTP servers use the same service.
    """

    model: str

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AIResponse | Mapping[str, object] | str: ...


# Friendly aliases used by integrations which call this operation generate.
AIModel = AIModelAdapter


def coerce_response(value: object, *, model: str | None = None) -> AIResponse:
    """Normalize an adapter return value into :class:`AIResponse`."""

    if isinstance(value, AIResponse):
        return value if value.model is not None or model is None else AIResponse(
            content=value.content,
            model=model,
            usage=value.usage,
            raw=value.raw,
            request_id=value.request_id,
        )
    if isinstance(value, Mapping):
        # Permit an already-enveloped response, while treating all other
        # mapping values as the model's structured content.
        if "content" in value or "output" in value or "response" in value:
            content = value.get("content", value.get("output", value.get("response")))
            usage = AIUsage.from_value(value.get("usage", value.get("metrics")))
            return AIResponse(
                content=content,
                model=str(value.get("model", model)) if value.get("model", model) is not None else None,
                usage=usage,
                raw=value,
                request_id=(str(value["id"]) if value.get("id") is not None else None),
            )
        return AIResponse(content=dict(value), model=model, raw=value)
    return AIResponse(content=value, model=model, raw=value)


class MockAIModelAdapter:
    """Deterministic offline adapter for tests and local demos.

    ``response`` may be a mapping, JSON string, :class:`AIResponse`, or a
    callable.  A callable receives ``prompt`` and keyword arguments.  When
    ``responses`` is supplied, keys are selected by ``metadata['analysis_kind']``
    (with ``default`` as fallback).
    """

    def __init__(
        self,
        response: object | Callable[..., object] | None = None,
        *,
        model: str = "mock-p5",
        responses: Mapping[str, object] | None = None,
        usage: AIUsage | Mapping[str, object] | None = None,
    ) -> None:
        self.model = str(model)
        self.response = response if response is not None else {}
        self.responses = dict(responses or {})
        self.usage = AIUsage.from_value(usage)
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AIResponse:
        metadata_dict = dict(metadata or {})
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "metadata": metadata_dict,
        })
        kind = str(metadata_dict.get("analysis_kind", ""))
        selected = self.responses.get(kind, self.responses.get("default", self.response))
        result = _invoke_callable(selected, prompt, system_prompt=system_prompt, metadata=metadata_dict)
        response = coerce_response(result, model=self.model)
        if response.usage == AIUsage() and self.usage != AIUsage():
            response = AIResponse(
                content=response.content,
                model=response.model or self.model,
                usage=self.usage,
                raw=response.raw,
                request_id=response.request_id,
            )
        return response

    generate = complete
    analyze = complete


# Short names are useful when this package is used from a notebook.
MockAIAdapter = MockAIModelAdapter
FakeAIModelAdapter = MockAIModelAdapter


class CallableAIModelAdapter:
    """Adapter around a user-provided local callable.

    The callable is never serialized.  It is therefore suitable for a local
    model runner and for tests without introducing a network dependency.
    """

    def __init__(self, callback: Callable[..., object], *, model: str = "callable") -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self.callback = callback
        self.model = str(model)
        self.calls: int = 0

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AIResponse:
        self.calls += 1
        result = _invoke_callable(
            self.callback,
            prompt,
            system_prompt=system_prompt,
            metadata=dict(metadata or {}),
        )
        return coerce_response(result, model=self.model)

    generate = complete
    analyze = complete


CallableAIAdapter = CallableAIModelAdapter


class LocalHTTPAIModelAdapter:
    """Optional local HTTP model adapter.

    It sends only JSON ``model``, ``prompt`` and ``system`` fields.  No
    authorization header, token, cookie, or secret is accepted.  To avoid
    accidental data exfiltration, non-loopback endpoints require the explicit
    ``allow_remote=True`` opt-in.
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        *,
        model: str = "local",
        timeout: float = 60.0,
        opener: Callable[..., Any] | None = None,
        allow_remote: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.endpoint = str(endpoint)
        self.model = str(model)
        self.timeout = max(0.1, float(timeout))
        self.opener = opener or urlopen
        self.allow_remote = bool(allow_remote)
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AIConfigurationError("local HTTP endpoint must be an http(s) URL")
        if not self.allow_remote and not _is_loopback_host(parsed.hostname):
            raise AIConfigurationError(
                "HTTP adapter is local-only; pass allow_remote=True explicitly for a remote endpoint"
            )
        path = (parsed.path or "/").rstrip("/") or "/"
        if path not in {"/api/generate", "/api/chat", "/v1/chat/completions"}:
            raise AIConfigurationError("local HTTP endpoint path is not an allowed model API")
        # Only content negotiation headers are permitted.  This explicitly
        # prevents accidental API-key/auth header persistence.
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            forbidden = {"authorization", "cookie", "x-api-key", "api-key", "token"}
            for key, value in headers.items():
                if str(key).lower() in forbidden or "key" in str(key).lower() or "token" in str(key).lower():
                    raise AIConfigurationError("HTTP adapter does not accept credentials or API keys")
                # User agents and harmless tracing headers are okay, but never
                # permit a value that resembles a secret field.
                self.headers[str(key)] = str(value)

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AIResponse:
        payload: dict[str, object] = {"model": self.model, "prompt": prompt, "stream": False}
        if system_prompt:
            payload["system"] = system_prompt
        if metadata:
            # Metadata is intentionally restricted to non-sensitive scalar
            # labels, keeping it safe to inspect in local server logs.
            payload["metadata"] = _safe_metadata(metadata)
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise AIAdapterError(f"local model request failed: {exc}") from exc
        if int(status) >= 400:
            raise AIAdapterError(f"local model returned HTTP {status}")
        try:
            body = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (TypeError, ValueError) as exc:
            raise AIAdapterError("local model returned invalid JSON") from exc
        response = coerce_response(body, model=self.model)
        usage = response.usage
        if usage.latency_ms is None:
            usage = AIUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                cost_usd=usage.cost_usd,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        return AIResponse(
            content=response.content,
            model=response.model or self.model,
            usage=usage,
            raw=response.raw,
            request_id=response.request_id,
        )

    generate = complete
    analyze = complete


HTTPAIModelAdapter = LocalHTTPAIModelAdapter
HttpAIModelAdapter = LocalHTTPAIModelAdapter
LocalHTTPAdapter = LocalHTTPAIModelAdapter
LocalHttpAIAdapter = LocalHTTPAIModelAdapter


def _invoke_callable(
    callback: object,
    prompt: str,
    *,
    system_prompt: str | None,
    metadata: Mapping[str, object],
) -> object:
    if not callable(callback):
        return callback
    # Prefer the explicit keyword shape, then progressively support simple
    # one-argument and two-argument lambdas used in tests/notebooks.
    try:
        return callback(prompt=prompt, system_prompt=system_prompt, metadata=metadata)
    except TypeError as first:
        try:
            return callback(prompt, system_prompt, metadata)
        except TypeError:
            try:
                return callback(prompt, system_prompt)
            except TypeError:
                try:
                    return callback(prompt)
                except TypeError:
                    raise first


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _safe_metadata(value: object, key: str | None = None) -> object:
    if key and any(token in key.lower() for token in ("key", "token", "password", "secret", "cookie", "auth")):
        return None
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            safe = _safe_metadata(raw_value, str(raw_key))
            if safe is not None:
                result[str(raw_key)] = safe
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

