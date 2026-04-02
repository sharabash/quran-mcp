"""Tests for quran_mcp.middleware.http_debug.

Covers:
  - _sanitize_header_value: sensitive headers masked, normal headers preserved
  - _format_headers: bulk sanitization
  - HttpDebugMiddleware: gated by settings.logging.debug (enabled/disabled)
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from fastmcp.server.middleware import MiddlewareContext

from quran_mcp.middleware.http_debug import (
    HttpDebugMiddleware,
    _format_headers,
    _sanitize_header_value,
)


# ---------------------------------------------------------------------------
# _sanitize_header_value
# ---------------------------------------------------------------------------


class TestSanitizeHeaderValue:
    def test_normal_header_unchanged(self):
        assert _sanitize_header_value("content-type", "application/json") == "application/json"

    def test_authorization_masked(self):
        result = _sanitize_header_value("authorization", "Bearer sk-1234567890abcdef")
        assert result == "Bear...cdef"

    def test_cookie_masked(self):
        result = _sanitize_header_value("cookie", "session=abcdefghijklmnop")
        assert result == "sess...mnop"

    def test_short_sensitive_value_unchanged(self):
        """Values <= 8 chars are too short to meaningfully mask."""
        result = _sanitize_header_value("authorization", "short")
        assert result == "short"

    def test_case_insensitive_matching(self):
        result = _sanitize_header_value("Authorization", "Bearer sk-1234567890abcdef")
        assert "..." in result

    def test_x_api_key_masked(self):
        result = _sanitize_header_value("x-api-key", "my-secret-api-key-value")
        assert result.startswith("my-s")
        assert result.endswith("alue")
        assert "..." in result


# ---------------------------------------------------------------------------
# _format_headers
# ---------------------------------------------------------------------------


class TestFormatHeaders:
    def test_mixed_headers(self):
        headers = {
            "content-type": "text/html",
            "authorization": "Bearer long-secret-token-value",
            "user-agent": "test/1.0",
        }
        result = _format_headers(headers)
        assert result["content-type"] == "text/html"
        assert result["user-agent"] == "test/1.0"
        assert "..." in result["authorization"]

    def test_empty_headers(self):
        assert _format_headers({}) == {}


# ---------------------------------------------------------------------------
# HttpDebugMiddleware — enable/disable gate
# ---------------------------------------------------------------------------


@dataclass
class FakeMessage:
    name: str = ""
    method: str = ""


def _ctx() -> MiddlewareContext:
    return MiddlewareContext(message=FakeMessage())


async def _ok_next(context):
    return "result"


class TestHttpDebugMiddlewareGate:
    async def test_disabled_passes_through_without_logging(self, caplog):
        mw = HttpDebugMiddleware()

        with patch("quran_mcp.middleware.http_debug._is_http_debug_enabled", return_value=False):
            result = await mw.on_message(_ctx(), _ok_next)

        assert result == "result"
        # No log records when disabled
        assert not any("MCP" in r.message for r in caplog.records)

    async def test_enabled_logs_and_passes_through(self, caplog):
        import logging

        mw = HttpDebugMiddleware()

        with caplog.at_level(logging.DEBUG, logger="quran_mcp.middleware.http_debug"), \
             patch("quran_mcp.middleware.http_debug._is_http_debug_enabled", return_value=True), \
             patch("quran_mcp.middleware.http_debug.get_http_request", side_effect=RuntimeError("no HTTP")):
            result = await mw.on_message(_ctx(), _ok_next)

        assert result == "result"
        # Should log even without HTTP context (falls back to MCP-only log)
        assert any("MCP" in r.message for r in caplog.records)
