"""Tests for quran_mcp.middleware.mcp_call_logger.

Covers:
  - Pure utility functions: _safe_serialize, _format_size, _truncate_args
  - Middleware verbosity modes: minimal skips logging, normal/verbose/debug emit
  - Error logging always fires (even at minimal verbosity)
  - JSON vs pretty output format
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult

from quran_mcp.middleware.mcp_call_logger import (
    McpCallLoggerMiddleware,
    _format_size,
    _safe_serialize,
    _truncate_args,
)

_LOGGER_NAME = "quran_mcp.mcp_calls"


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestSafeSerialize:
    def test_simple_dict(self):
        raw, size = _safe_serialize({"a": 1})
        assert json.loads(raw) == {"a": 1}
        assert size == len(raw)

    def test_truncates_large_payload(self):
        big = {"data": "x" * 100_000}
        raw, size = _safe_serialize(big)
        assert len(raw) <= 65536
        assert size is None  # truncated → size unknown

    def test_handles_unserializable_with_default_str(self):
        """default=str means object() becomes a string repr, not an error."""
        raw, size = _safe_serialize(object())
        assert raw.startswith('"<object')
        assert size is not None

    def test_handles_none(self):
        raw, size = _safe_serialize(None)
        assert raw == "null"
        assert size == 4


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500B"

    def test_kilobytes(self):
        assert _format_size(2048) == "2.0KB"

    def test_none_means_truncated(self):
        assert _format_size(None) == ">64KB"

    def test_zero(self):
        assert _format_size(0) == "0B"

    def test_boundary(self):
        assert _format_size(1023) == "1023B"
        assert _format_size(1024) == "1.0KB"


class TestTruncateArgs:
    def test_empty_args(self):
        assert _truncate_args(None) == ""
        assert _truncate_args({}) == ""

    def test_simple_args(self):
        result = _truncate_args({"ayahs": "2:255"})
        assert 'ayahs="2:255"' in result

    def test_long_value_truncated(self):
        result = _truncate_args({"data": "x" * 200}, max_per_param=20)
        assert "..." in result
        assert len(result) < 200

    def test_multiple_params(self):
        result = _truncate_args({"a": "1", "b": "2"})
        assert "a=" in result
        assert "b=" in result
        assert ", " in result


# ---------------------------------------------------------------------------
# Middleware behavior — verbosity modes
# ---------------------------------------------------------------------------


@dataclass
class FakeMessage:
    name: str = ""
    arguments: dict[str, Any] | None = None


def _ctx(tool_name: str = "fetch_quran", args: dict | None = None) -> MiddlewareContext:
    return MiddlewareContext(message=FakeMessage(name=tool_name, arguments=args))


async def _ok_next(context: MiddlewareContext) -> ToolResult:
    return ToolResult(content="ok")


async def _error_next(context: MiddlewareContext):
    raise ValueError("test explosion")


class TestMinimalVerbosity:
    async def test_minimal_skips_success_logging(self):
        mw = McpCallLoggerMiddleware(verbosity="minimal", fmt="pretty")
        result = await mw.on_call_tool(_ctx(), _ok_next)
        assert result.content[0].text == "ok"

    async def test_minimal_still_logs_errors(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="minimal", fmt="pretty")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME), \
             patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            try:
                await mw.on_call_tool(_ctx(), _error_next)
            except ValueError:
                pass
        assert any("ERROR" in r.message for r in caplog.records)


class TestNormalVerbosity:
    async def test_normal_logs_success(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME), \
             patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            await mw.on_call_tool(_ctx(), _ok_next)
        assert any("fetch_quran" in r.message and "OK" in r.message for r in caplog.records)

    async def test_normal_does_not_show_preview(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME), \
             patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            await mw.on_call_tool(_ctx(), _ok_next)
        assert not any("╰─" in r.message for r in caplog.records)


class TestVerboseMode:
    async def test_verbose_shows_preview(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="verbose", fmt="pretty")
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME), \
             patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            await mw.on_call_tool(_ctx(), _ok_next)
        assert any("╰─" in r.message for r in caplog.records)


class TestJsonFormat:
    async def test_json_format_outputs_to_stderr(self, capsys):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="json")
        with patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            await mw.on_call_tool(_ctx(), _ok_next)
        captured = capsys.readouterr()
        record = json.loads(captured.err.strip())
        assert record["type"] == "tool"
        assert record["name"] == "fetch_quran"
        assert record["status"] == "ok"

    async def test_json_error_format(self, capsys):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="json")
        with patch("quran_mcp.lib.config.logging.get_request_id", return_value="req_1"):
            try:
                await mw.on_call_tool(_ctx(), _error_next)
            except ValueError:
                pass
        captured = capsys.readouterr()
        record = json.loads(captured.err.strip())
        assert record["status"] == "error"
        assert "ValueError" in record["error"]


class TestListHooks:
    async def test_list_tools_logs_count(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")

        async def _list_next(ctx):
            return [{"name": "fetch_quran"}, {"name": "fetch_tafsir"}]

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            await mw.on_list_tools(_ctx(), _list_next)
        assert any("2 tools" in r.message for r in caplog.records)

    async def test_minimal_skips_list_logging(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="minimal", fmt="pretty")

        async def _list_next(ctx):
            return [{"name": "a"}]

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            result = await mw.on_list_tools(_ctx(), _list_next)
        assert len(result) == 1
        assert not any("META" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Client hint line tests
# ---------------------------------------------------------------------------

_CLIENT_PATCHES = {
    "quran_mcp.middleware.mcp_call_logger.detect_client_hint": lambda ctx: {
        "host": "chatgpt",
        "platform": "desktop",
    },
    "quran_mcp.middleware.mcp_call_logger.get_http_headers": lambda: {
        "cf-connecting-ip": "203.0.113.42",
    },
    "quran_mcp.middleware.mcp_call_logger.resolve_client_identity": lambda **kw: "openai-conv:sess-abc",
    "quran_mcp.lib.config.logging.get_request_id": lambda: "req_1",
}


def _apply_client_patches():
    """Stack patches for client hint functions."""
    return [patch(k, v) for k, v in _CLIENT_PATCHES.items()]


class TestClientHintPretty:
    async def test_success_emits_client_line(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
                await mw.on_call_tool(_ctx(), _ok_next)
            client_records = [r for r in caplog.records if "client:" in r.message]
            assert len(client_records) == 1
            client_data = json.loads(client_records[0].message.split("client: ", 1)[1])
            assert client_data["host"] == "chatgpt"
            assert client_data["platform"] == "desktop"
            assert client_data["ip"] == "203.0.113.42"
            assert client_data["id"] == "openai-conv:sess-abc"
            assert client_records[0].levelno == logging.INFO
        finally:
            for p in patches:
                p.stop()

    async def test_error_emits_client_line_at_error_level(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
                try:
                    await mw.on_call_tool(_ctx(), _error_next)
                except ValueError:
                    pass
            client_records = [r for r in caplog.records if "client:" in r.message]
            assert len(client_records) == 1
            assert client_records[0].levelno == logging.ERROR

        finally:
            for p in patches:
                p.stop()

    async def test_minimal_success_suppresses_client_line(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="minimal", fmt="pretty")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
                await mw.on_call_tool(_ctx(), _ok_next)
            assert not any("client:" in r.message for r in caplog.records)
        finally:
            for p in patches:
                p.stop()

    async def test_minimal_error_emits_client_line(self, caplog):
        mw = McpCallLoggerMiddleware(verbosity="minimal", fmt="pretty")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
                try:
                    await mw.on_call_tool(_ctx(), _error_next)
                except ValueError:
                    pass
            assert any("client:" in r.message for r in caplog.records)
        finally:
            for p in patches:
                p.stop()


class TestClientHintJson:
    async def test_success_includes_client_key(self, capsys):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="json")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            await mw.on_call_tool(_ctx(), _ok_next)
            record = json.loads(capsys.readouterr().err.strip())
            assert "client" in record
            assert record["client"]["host"] == "chatgpt"
            assert record["client"]["ip"] == "203.0.113.42"
        finally:
            for p in patches:
                p.stop()

    async def test_error_includes_client_key(self, capsys):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="json")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:
            try:
                await mw.on_call_tool(_ctx(), _error_next)
            except ValueError:
                pass
            record = json.loads(capsys.readouterr().err.strip())
            assert "client" in record
            assert record["client"]["host"] == "chatgpt"
        finally:
            for p in patches:
                p.stop()


class TestClientHintNonTool:
    async def test_resource_has_no_client_line(self, caplog):
        """Non-tool calls should NOT emit client hint lines."""
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="pretty")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:

            async def _list_next(ctx):
                return [{"name": "a"}]

            with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
                await mw.on_list_tools(_ctx(), _list_next)
            assert not any("client:" in r.message for r in caplog.records)
        finally:
            for p in patches:
                p.stop()

    async def test_meta_json_has_no_client_key(self, capsys):
        mw = McpCallLoggerMiddleware(verbosity="normal", fmt="json")
        patches = _apply_client_patches()
        for p in patches:
            p.start()
        try:

            async def _list_next(ctx):
                return [{"name": "a"}]

            await mw.on_list_tools(_ctx(), _list_next)
            record = json.loads(capsys.readouterr().err.strip())
            assert "client" not in record
        finally:
            for p in patches:
                p.stop()
