"""Tests for quran_mcp.lib.site.health — pure helpers and cache logic.

The full health probe (_run_health_check, health_check_handler) connects
to a live MCP server and belongs in tests/integration/. These tests cover
the pure utility functions, nonce extraction, and in-memory cache ops.

Covers:
  - _extract_grounding_nonce: regex extraction from text
  - _first_text_block: attribute extraction from result objects
  - _grounding_suppressed: dict shape check
  - _fail_check: error payload builder
  - Cache: _get_cached, _set_cache, clear_cache
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from quran_mcp.lib.site.health import (
    _CACHE_KEY,
    HealthRuntimeState,
    _extract_grounding_nonce,
    _fail_check,
    _first_text_block,
    _get_cached,
    _grounding_suppressed,
    _set_cache,
    build_health_runtime_state,
    clear_cache,
    health_check_handler,
)


# ---------------------------------------------------------------------------
# _extract_grounding_nonce
# ---------------------------------------------------------------------------


class TestExtractGroundingNonce:
    def test_line_format(self):
        text = "Some preamble.\nGROUNDING_NONCE: gnd-abc123def456\nMore text."
        assert _extract_grounding_nonce(text) == "gnd-abc123def456"

    def test_xml_tag_format(self):
        text = "Rules here\n<grounding_nonce>gnd-abc123def456</grounding_nonce>"
        assert _extract_grounding_nonce(text) == "gnd-abc123def456"

    def test_line_format_preferred_over_tag(self):
        """Line format is checked first."""
        text = "GROUNDING_NONCE: gnd-line123\n<grounding_nonce>gnd-tag456</grounding_nonce>"
        assert _extract_grounding_nonce(text) == "gnd-line123"

    def test_no_nonce_returns_none(self):
        assert _extract_grounding_nonce("No nonce here at all.") is None

    def test_empty_string(self):
        assert _extract_grounding_nonce("") is None

    def test_nonce_with_whitespace_in_tag(self):
        text = "<grounding_nonce> gnd-abc123 </grounding_nonce>"
        assert _extract_grounding_nonce(text) == "gnd-abc123"


# ---------------------------------------------------------------------------
# _first_text_block
# ---------------------------------------------------------------------------


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeResult:
    content: list | None = None


class TestFirstTextBlock:
    def test_extracts_first_text(self):
        result = FakeResult(content=[FakeTextBlock("hello"), FakeTextBlock("world")])
        assert _first_text_block(result) == "hello"

    def test_empty_content(self):
        assert _first_text_block(FakeResult(content=[])) == ""

    def test_none_content(self):
        assert _first_text_block(FakeResult(content=None)) == ""

    def test_no_content_attr(self):
        assert _first_text_block(object()) == ""

    def test_non_text_blocks_skipped(self):
        @dataclass
        class ImageBlock:
            data: bytes = b""

        result = FakeResult(content=[ImageBlock(), FakeTextBlock("found")])
        assert _first_text_block(result) == "found"


# ---------------------------------------------------------------------------
# _grounding_suppressed
# ---------------------------------------------------------------------------


class TestGroundingSuppressed:
    def test_both_none_means_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": None, "warnings": None}) is True

    def test_grounding_rules_present_means_not_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": "some rules", "warnings": None}) is False

    def test_warnings_present_means_not_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": None, "warnings": [{"type": "grounding"}]}) is False

    def test_non_dict_returns_false(self):
        assert _grounding_suppressed("not a dict") is False
        assert _grounding_suppressed(None) is False

    def test_missing_keys_means_suppressed(self):
        """Keys absent from dict: .get() returns None → both None → suppressed."""
        assert _grounding_suppressed({"data": "value"}) is True


# ---------------------------------------------------------------------------
# _fail_check
# ---------------------------------------------------------------------------


class TestFailCheck:
    def test_basic_failure(self):
        result = _fail_check("connection refused")
        assert result["status"] == "fail"
        assert result["error"] == "connection refused"
        assert "latency_ms" not in result

    def test_with_latency(self):
        result = _fail_check("timeout", latency_ms=1500)
        assert result["latency_ms"] == 1500


# ---------------------------------------------------------------------------
# Cache operations
# ---------------------------------------------------------------------------


class TestCache:
    def setup_method(self):
        self.runtime_state = build_health_runtime_state()

    def test_set_and_get(self):
        _set_cache("key", {"status": "healthy"}, ttl=60, runtime_state=self.runtime_state)
        assert _get_cached("key", runtime_state=self.runtime_state) == {"status": "healthy"}

    def test_missing_key(self):
        assert _get_cached("nonexistent", runtime_state=self.runtime_state) is None

    def test_expired_entry(self):
        # Use a fake monotonic clock to simulate expiry
        with patch("quran_mcp.lib.site.health.time.monotonic", return_value=1000.0):
            _set_cache("key", {"status": "healthy"}, ttl=10, runtime_state=self.runtime_state)

        with patch("quran_mcp.lib.site.health.time.monotonic", return_value=1011.0):
            assert _get_cached("key", runtime_state=self.runtime_state) is None

    def test_not_expired_within_ttl(self):
        with patch("quran_mcp.lib.site.health.time.monotonic", return_value=1000.0):
            _set_cache("key", {"status": "healthy"}, ttl=60, runtime_state=self.runtime_state)

        with patch("quran_mcp.lib.site.health.time.monotonic", return_value=1050.0):
            assert _get_cached("key", runtime_state=self.runtime_state) == {"status": "healthy"}

    def test_clear_cache_removes_all(self):
        _set_cache("a", {"v": 1}, ttl=60, runtime_state=self.runtime_state)
        _set_cache("b", {"v": 2}, ttl=60, runtime_state=self.runtime_state)
        clear_cache(runtime_state=self.runtime_state)
        assert _get_cached("a", runtime_state=self.runtime_state) is None
        assert _get_cached("b", runtime_state=self.runtime_state) is None


async def _call_health_handler(
    settings: object,
    *,
    runtime_state: HealthRuntimeState | None = None,
) -> tuple[int, dict]:
    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/health",
        "headers": [],
    }
    await health_check_handler(
        scope,
        receive,
        send,
        settings,
        runtime_state=runtime_state,
    )  # type: ignore[arg-type]
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(body.decode("utf-8"))


class TestHealthHandler:
    def setup_method(self):
        self.runtime_state = build_health_runtime_state()

    @pytest.mark.asyncio
    async def test_cached_response_bypasses_rate_limit(self):
        runtime_state = HealthRuntimeState()
        cached_result = {
            "status": "healthy",
            "timestamp": "2026-03-23T12:00:00+00:00",
            "cached": False,
            "checks": {"overall": {"status": "pass"}},
        }
        _set_cache(_CACHE_KEY, cached_result, ttl=60.0, runtime_state=runtime_state)
        settings = SimpleNamespace(
            health=SimpleNamespace(
                max_timeout_s=1.0,
                tier0_cache_ttl_s=10.0,
            )
        )

        runtime_state.last_request_time = 1000.0
        with patch("quran_mcp.lib.site.health.time.monotonic", return_value=1000.5):
            status_code, payload = await _call_health_handler(
                settings,
                runtime_state=runtime_state,
            )

        assert status_code == 200
        assert payload["status"] == "healthy"
        assert payload["cached"] is True
