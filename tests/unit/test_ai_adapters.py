from __future__ import annotations

import json

import pytest

from packages.ai import (
    AIConfigurationError,
    AIResponse,
    AIUsage,
    CallableAIModelAdapter,
    LocalHTTPAIModelAdapter,
    MockAIModelAdapter,
)


def test_mock_adapter_is_deterministic_and_records_prompt() -> None:
    adapter = MockAIModelAdapter(
        {"ai_fields": {"error_labels": ["MISSED_CONDITION"], "error_cause": "漏看限定条件"}},
        usage={"prompt_tokens": 12, "completion_tokens": 8},
    )
    response = adapter.complete("hello", system_prompt="rules", metadata={"analysis_kind": "question_error"})
    assert isinstance(response, AIResponse)
    assert response.content["ai_fields"]["error_labels"] == ["MISSED_CONDITION"]
    assert response.usage.total_tokens == 20
    assert adapter.calls[0]["metadata"]["analysis_kind"] == "question_error"


def test_callable_adapter_accepts_simple_one_argument_callback() -> None:
    adapter = CallableAIModelAdapter(lambda prompt: {"ai_fields": {"echo": prompt}}, model="fake-local")
    response = adapter.complete("prompt")
    assert response.model == "fake-local"
    assert response.content["ai_fields"]["echo"] == "prompt"
    assert adapter.calls == 1


class _HTTPResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_HTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_local_http_adapter_has_no_auth_header_and_parses_ollama_shape() -> None:
    seen = {}

    def opener(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return _HTTPResponse({"response": "{\"ai_fields\":{\"ok\":true}}", "prompt_eval_count": 3, "eval_count": 4})

    adapter = LocalHTTPAIModelAdapter(opener=opener)
    response = adapter.complete("hello")
    assert response.content == '{"ai_fields":{"ok":true}}'
    assert "Authorization" not in seen["request"].headers
    assert "api" not in " ".join(seen["request"].headers).lower()


def test_local_http_adapter_rejects_remote_endpoint_and_credentials() -> None:
    with pytest.raises(AIConfigurationError):
        LocalHTTPAIModelAdapter("https://example.invalid/model")
    with pytest.raises(AIConfigurationError):
        LocalHTTPAIModelAdapter(headers={"Authorization": "secret"})

