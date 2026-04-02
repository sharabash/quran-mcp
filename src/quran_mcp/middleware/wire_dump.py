"""ASGI middleware: dump full HTTP request + response to a JSONL debug log.

Captures the ACTUAL HTTP wire traffic — request headers, request body,
response headers, and response body — at the ASGI level, OUTSIDE FastMCP's
transport layer. This shows exactly what the client sends and receives.

Enable via config.yml: logging.wire_dump: true
Default output path: .log/mcp-wire-dump.jsonl
Override with: QURAN_MCP_WIRE_DUMP_PATH=/custom/path.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_DEFAULT_DUMP_FILE = Path(".log/mcp-wire-dump.jsonl")


def _resolve_dump_file() -> Path:
    """Return the configured wire-dump path for this process."""
    configured = os.environ.get("QURAN_MCP_WIRE_DUMP_PATH")
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DUMP_FILE


class WireDumpASGIMiddleware:
    """ASGI middleware that logs full HTTP request/response to JSONL."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ts = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()

        # --- Request ---
        req_headers = dict(scope.get("headers", []))
        # Decode header bytes to str
        req_headers_str = {}
        for k, v in req_headers.items():
            try:
                req_headers_str[k.decode("latin-1")] = v.decode("latin-1")
            except (AttributeError, UnicodeDecodeError):
                req_headers_str[str(k)] = str(v)

        # Capture request body
        req_body_chunks: list[bytes] = []

        async def receive_wrapper() -> dict:
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                req_body_chunks.append(body)
            return message

        # --- Response ---
        resp_status: int | None = None
        resp_headers_str: dict[str, str] = {}
        resp_body_chunks: list[bytes] = []

        async def send_wrapper(message: dict) -> None:
            nonlocal resp_status
            if message["type"] == "http.response.start":
                resp_status = message.get("status")
                for k, v in message.get("headers", []):
                    try:
                        resp_headers_str[k.decode("latin-1")] = v.decode("latin-1")
                    except (AttributeError, UnicodeDecodeError):
                        resp_headers_str[str(k)] = str(v)
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    resp_body_chunks.append(body)
            await send(message)

        # --- Execute ---
        error_str: str | None = None
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception as e:
            error_str = f"{type(e).__name__}: {e}"
            raise
        finally:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

            # Parse request body as JSON if possible
            req_body_raw = b"".join(req_body_chunks)
            try:
                req_body = json.loads(req_body_raw) if req_body_raw else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                req_body = req_body_raw.decode("utf-8", errors="replace")[:2000]

            # Parse response body — may be SSE or JSON
            resp_body_raw = b"".join(resp_body_chunks)
            resp_body: Any = None
            if resp_body_raw:
                try:
                    resp_body = json.loads(resp_body_raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Might be SSE or plain text — decode the full payload for debugging.
                    resp_body = resp_body_raw.decode("utf-8", errors="replace")

            # Extract MCP method from request body
            mcp_method = None
            if isinstance(req_body, dict):
                mcp_method = req_body.get("method")

            entry: dict[str, Any] = {
                "timestamp": ts,
                "elapsed_ms": elapsed_ms,
                "mcp_method": mcp_method,
                "request": {
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "query_string": scope.get("query_string", b"").decode("latin-1", errors="replace"),
                    "headers": req_headers_str,
                    "body": req_body,
                },
                "response": {
                    "status": resp_status,
                    "headers": resp_headers_str,
                    "body": resp_body,
                },
            }
            if error_str:
                entry["error"] = error_str

            try:
                dump_file = _resolve_dump_file()
                dump_file.parent.mkdir(parents=True, exist_ok=True)
                with dump_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
            except Exception as dump_err:
                logger.warning(f"Wire dump write failed: {dump_err}")
