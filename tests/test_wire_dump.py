"""Tests for quran_mcp.middleware.wire_dump.

Covers:
  - Non-HTTP scopes (e.g., websocket) pass through without dumping
  - HTTP requests: captures request body, response body, writes JSONL
  - MCP method extraction from JSON request body
  - Error handling: exceptions propagate and are recorded in the dump
"""

from __future__ import annotations

import json
from unittest.mock import patch

from quran_mcp.middleware.wire_dump import WireDumpASGIMiddleware


# ---------------------------------------------------------------------------
# ASGI test helpers
# ---------------------------------------------------------------------------


def _make_receive(body: bytes = b""):
    """Create an ASGI receive callable that yields a single request body."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body}
        return {"type": "http.disconnect"}

    return receive


class _SendCollector:
    """Collect ASGI send messages."""

    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message: dict):
        self.messages.append(message)


def _http_scope(method: str = "POST", path: str = "/mcp") -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"user-agent", b"test-client/1.0"),
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNonHttpPassthrough:
    async def test_websocket_scope_passes_through(self):
        """Non-HTTP scopes should be forwarded to the inner app without dumping."""
        calls = []

        async def inner_app(scope, receive, send):
            calls.append(scope["type"])

        mw = WireDumpASGIMiddleware(inner_app)
        await mw({"type": "websocket"}, _make_receive(), _SendCollector())
        assert calls == ["websocket"]


class TestHttpCapture:
    async def test_captures_request_and_response(self, tmp_path):
        dump_file = tmp_path / "wire.jsonl"

        async def inner_app(scope, receive, send):
            # Read request body
            await receive()
            # Send response
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b'{"result": "ok"}'})

        mw = WireDumpASGIMiddleware(inner_app)
        body = json.dumps({"method": "tools/call", "params": {"name": "fetch_quran"}}).encode()

        with patch("quran_mcp.middleware.wire_dump._resolve_dump_file", return_value=dump_file):
            send = _SendCollector()
            await mw(_http_scope(), _make_receive(body), send)

        # JSONL file should have one entry
        lines = dump_file.read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["mcp_method"] == "tools/call"
        assert entry["request"]["method"] == "POST"
        assert entry["request"]["path"] == "/mcp"
        assert entry["response"]["status"] == 200
        assert entry["response"]["body"]["result"] == "ok"
        assert "elapsed_ms" in entry
        assert "error" not in entry

    async def test_non_json_request_body(self, tmp_path):
        dump_file = tmp_path / "wire.jsonl"

        async def inner_app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"plain text"})

        mw = WireDumpASGIMiddleware(inner_app)

        with patch("quran_mcp.middleware.wire_dump._resolve_dump_file", return_value=dump_file):
            await mw(_http_scope(), _make_receive(b"not json"), _SendCollector())

        entry = json.loads(dump_file.read_text().strip())
        assert entry["mcp_method"] is None  # can't extract method from non-JSON
        assert isinstance(entry["request"]["body"], str)


class TestErrorCapture:
    async def test_exception_recorded_in_dump(self, tmp_path):
        dump_file = tmp_path / "wire.jsonl"

        async def inner_app(scope, receive, send):
            await receive()
            raise RuntimeError("boom")

        mw = WireDumpASGIMiddleware(inner_app)

        with patch("quran_mcp.middleware.wire_dump._resolve_dump_file", return_value=dump_file):
            try:
                await mw(_http_scope(), _make_receive(b"{}"), _SendCollector())
            except RuntimeError:
                pass

        entry = json.loads(dump_file.read_text().strip())
        assert entry["error"] == "RuntimeError: boom"


class TestMcpMethodExtraction:
    async def test_extracts_method_from_json_body(self, tmp_path):
        dump_file = tmp_path / "wire.jsonl"

        async def inner_app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        mw = WireDumpASGIMiddleware(inner_app)
        body = json.dumps({"method": "resources/read"}).encode()

        with patch("quran_mcp.middleware.wire_dump._resolve_dump_file", return_value=dump_file):
            await mw(_http_scope(), _make_receive(body), _SendCollector())

        entry = json.loads(dump_file.read_text().strip())
        assert entry["mcp_method"] == "resources/read"

    async def test_creates_parent_directory_for_configured_dump_file(self, tmp_path):
        dump_file = tmp_path / "nested" / "wire.jsonl"

        async def inner_app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        mw = WireDumpASGIMiddleware(inner_app)

        with patch("quran_mcp.middleware.wire_dump._resolve_dump_file", return_value=dump_file):
            await mw(_http_scope(), _make_receive(b"{}"), _SendCollector())

        assert dump_file.exists()
