import anthropic
import httpx
import pytest

from rah_packager.claude_client import validate_api_key
from rah_packager.errors import (
    ClaudeAPIError,
    ClaudeAuthenticationError,
    ClaudeConnectionError,
    ClaudeRateLimitedError,
)


def _request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages/count_tokens")


def _response(status_code):
    return httpx.Response(status_code, request=_request())


class _FakeMessages:
    def __init__(self, exc):
        self._exc = exc

    def count_tokens(self, **kwargs):
        if self._exc is not None:
            raise self._exc


class _FakeClient:
    def __init__(self, exc):
        self.messages = _FakeMessages(exc)


def _patch_client(monkeypatch, exc):
    monkeypatch.setattr(
        "rah_packager.claude_client.anthropic.Anthropic",
        lambda api_key: _FakeClient(exc),
    )


def test_valid_key_raises_nothing(monkeypatch):
    _patch_client(monkeypatch, None)
    validate_api_key("sk-ant-fake")  # must not raise


def test_authentication_error_mapped(monkeypatch):
    exc = anthropic.AuthenticationError("invalid x-api-key", response=_response(401), body=None)
    _patch_client(monkeypatch, exc)

    with pytest.raises(ClaudeAuthenticationError) as exc_info:
        validate_api_key("sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-AUTHENTICATION-FAILED"


def test_rate_limit_error_mapped(monkeypatch):
    exc = anthropic.RateLimitError("rate limited", response=_response(429), body=None)
    _patch_client(monkeypatch, exc)

    with pytest.raises(ClaudeRateLimitedError) as exc_info:
        validate_api_key("sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-RATE-LIMITED"


def test_connection_error_mapped(monkeypatch):
    exc = anthropic.APIConnectionError(request=_request())
    _patch_client(monkeypatch, exc)

    with pytest.raises(ClaudeConnectionError) as exc_info:
        validate_api_key("sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-CONNECTION-FAILED"


def test_generic_api_status_error_mapped(monkeypatch):
    exc = anthropic.APIStatusError("server error", response=_response(500), body=None)
    _patch_client(monkeypatch, exc)

    with pytest.raises(ClaudeAPIError) as exc_info:
        validate_api_key("sk-ant-fake")
    assert exc_info.value.code == "PKG-CLAUDE-API-ERROR"
