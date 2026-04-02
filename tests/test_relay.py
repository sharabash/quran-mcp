"""Tests for quran_mcp.middleware.relay — pure utility functions only.

The full relay middleware path (turn creation, tool_call INSERT/UPDATE)
requires PostgreSQL and belongs in tests/integration/. These tests cover
the pure, side-effect-free functions that parse headers and extract metadata.

Covers:
  - extract_trace_id: W3C traceparent parsing + edge cases
  - extract_result_metadata: never-raises contract, field extraction
  - drain_pending: graceful shutdown of background tasks
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

from quran_mcp.lib.context.request import extract_trace_id
from quran_mcp.lib.relay.metadata import extract_result_metadata
from quran_mcp.middleware.relay import (
    RelayMiddleware,
    drain_pending,
    reset_relay_runtime_state,
)
from quran_mcp.lib.relay.runtime import register_relay_middleware
import quran_mcp.mcp.tools.relay as relay_tools


# ---------------------------------------------------------------------------
# extract_trace_id — W3C traceparent parsing
# ---------------------------------------------------------------------------


class TestExtractTraceId:
    def test_valid_traceparent(self):
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        assert extract_trace_id(headers) == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_unsampled_flag(self):
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"}
        assert extract_trace_id(headers) == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_all_zeros_trace_id_returns_none(self):
        headers = {"traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"}
        assert extract_trace_id(headers) is None

    def test_missing_header_returns_none(self):
        assert extract_trace_id({"other": "val"}) is None

    def test_none_headers_returns_none(self):
        assert extract_trace_id(None) is None

    def test_empty_headers_returns_none(self):
        assert extract_trace_id({}) is None

    def test_malformed_traceparent_returns_none(self):
        assert extract_trace_id({"traceparent": "garbage"}) is None

    def test_too_short_returns_none(self):
        assert extract_trace_id({"traceparent": "00-abc-def-01"}) is None

    def test_uppercase_normalized(self):
        headers = {"traceparent": "00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01"}
        assert extract_trace_id(headers) == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_whitespace_stripped(self):
        headers = {"traceparent": "  00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01  "}
        assert extract_trace_id(headers) == "4bf92f3577b34da6a3ce929d0e0e4736"


# ---------------------------------------------------------------------------
# extract_result_metadata — never-raises contract
# ---------------------------------------------------------------------------


@dataclass
class FakeResult:
    content: list | None = None
    isError: bool = False
    structuredContent: dict | None = None


class FakeTextContent:
    def __init__(self, text: str):
        self.text = text


class TestExtractResultMetadata:
    def test_successful_result_with_text(self):
        result = FakeResult(content=[FakeTextContent("hello world")])
        meta = extract_result_metadata(result)
        assert meta["success"] is True
        assert meta["result_count"] == 1
        assert "hello world" in meta["result_summary"]

    def test_error_result(self):
        result = FakeResult(content=[], isError=True)
        meta = extract_result_metadata(result)
        assert meta["success"] is False

    def test_none_result_treated_as_empty_success(self):
        """None result → content=[], isError=False, so success=True, count=0."""
        meta = extract_result_metadata(None)
        assert meta["success"] is True
        assert meta["result_count"] == 0

    def test_empty_content(self):
        result = FakeResult(content=[])
        meta = extract_result_metadata(result)
        assert meta["result_count"] == 0
        assert meta["result_summary"] is None

    def test_structured_content_keys_extracted(self):
        result = FakeResult(
            content=[],
            structuredContent={"ayah": "...", "edition": "..."},
        )
        meta = extract_result_metadata(result)
        assert meta["result_keys"] == ["ayah", "edition"]

    def test_no_structured_content(self):
        result = FakeResult(content=[FakeTextContent("x")])
        meta = extract_result_metadata(result)
        assert meta["result_keys"] is None

    def test_summary_truncated_at_500_chars(self):
        long_text = "x" * 1000
        result = FakeResult(content=[FakeTextContent(long_text)])
        meta = extract_result_metadata(result)
        assert len(meta["result_summary"]) <= 500

    def test_max_three_items_in_summary(self):
        items = [FakeTextContent(f"item-{i}") for i in range(10)]
        result = FakeResult(content=items)
        meta = extract_result_metadata(result)
        # Should contain at most 3 items separated by " | "
        assert meta["result_summary"].count(" | ") <= 2


# ---------------------------------------------------------------------------
# drain_pending — graceful shutdown
# ---------------------------------------------------------------------------


class TestDrainPending:
    async def test_drain_with_no_pending_tasks(self):
        """drain_pending should be a no-op when nothing is pending."""
        owner = SimpleNamespace()
        await drain_pending(owner, timeout=1.0)  # should not raise

    async def test_drain_waits_for_tasks(self):
        """drain_pending should wait for in-flight tasks to complete."""
        owner = SimpleNamespace()
        reset_relay_runtime_state(owner)
        middleware = RelayMiddleware()
        completed = []

        async def _slow_task():
            await asyncio.sleep(0.05)
            completed.append(True)

        middleware._tracked_fire_and_forget(_slow_task(), "test write")
        assert len(middleware._pending_tasks) == 1
        register_relay_middleware(owner, middleware)

        await drain_pending(owner, timeout=2.0)
        assert len(completed) == 1


class TestRelayDbBoundary:
    async def test_non_relay_tool_passes_when_relay_db_missing(self):
        middleware = RelayMiddleware()
        calls = 0

        async def _call_next(_context):
            nonlocal calls
            calls += 1
            from fastmcp.tools import ToolResult

            return ToolResult(content="ok")

        context = SimpleNamespace(
            message=SimpleNamespace(name="search_quran"),
            fastmcp_context=SimpleNamespace(
                request_context=SimpleNamespace(
                    lifespan_context=SimpleNamespace(db_pool=None)
                )
            ),
        )

        result = await middleware.on_call_tool(context, _call_next)

        assert calls == 1
        assert result.content[0].text == "ok"

    async def test_relay_tool_fails_closed_when_relay_db_missing(self):
        middleware = RelayMiddleware()

        async def _call_next(_context):
            from fastmcp.tools import ToolResult

            return ToolResult(content="ok")

        context = SimpleNamespace(
            message=SimpleNamespace(name="relay_turn_start"),
            fastmcp_context=SimpleNamespace(
                request_context=SimpleNamespace(
                    lifespan_context=SimpleNamespace(db_pool=None)
                )
            ),
        )

        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            await middleware.on_call_tool(context, _call_next)

    async def test_non_relay_tool_skips_automatic_logging_when_write_guard_denies(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        middleware = RelayMiddleware()
        full_logging_called = False

        async def _call_next(_context):
            from fastmcp.tools import ToolResult

            return ToolResult(content="ok")

        async def _full_logging_path(*_args, **_kwargs):
            nonlocal full_logging_called
            full_logging_called = True
            from fastmcp.tools import ToolResult

            return ToolResult(content="logged")

        monkeypatch.setattr("quran_mcp.middleware.relay.get_http_headers", lambda: {})
        monkeypatch.setattr(middleware, "_full_logging_path", _full_logging_path)

        context = SimpleNamespace(
            message=SimpleNamespace(name="search_quran"),
            fastmcp_context=SimpleNamespace(
                request_context=SimpleNamespace(
                    lifespan_context=SimpleNamespace(
                        db_pool=object(),
                        settings=SimpleNamespace(
                            server=SimpleNamespace(profile="public", expose_tags=["ga"]),
                            relay=SimpleNamespace(
                                write_token=SecretStr("relay-secret"),
                                log_turn_identity_event=False,
                            ),
                        ),
                    )
                )
            ),
        )

        result = await middleware.on_call_tool(context, _call_next)

        assert full_logging_called is False
        assert result.content[0].text == "ok"


class TestRelayPackageSurface:
    def test_register_surface_remains_public(self):
        assert callable(relay_tools.register)
