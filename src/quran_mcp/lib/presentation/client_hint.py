"""Client detection from HTTP headers and MCP handshake.

Produces a lightweight hint dict for MCP App UIs that need to adapt
their behaviour to the host (ChatGPT vs Claude) and platform (mobile
vs desktop).  Detection mirrors the relay middleware's header inspection
(see middleware/relay.py) but returns a simplified, UI-friendly shape.
"""

from __future__ import annotations

import re
from fastmcp import Context

from quran_mcp.lib.context.request import extract_client_info, get_http_headers

_MOBILE_RE = re.compile(r"Mobi|Android", re.IGNORECASE)


def detect_client_hint(ctx: Context | None) -> dict[str, str]:
    """Detect host and platform from the current request context.

    Returns ``{"host": "chatgpt"|"claude"|"unknown",
               "platform": "mobile"|"desktop"|"unknown"}``.
    """
    headers = get_http_headers()
    client_info = extract_client_info(ctx) if ctx is not None else None

    host = _detect_host(headers, client_info)
    platform = _detect_platform(headers)

    return {"host": host, "platform": platform}


def _detect_host(
    headers: dict[str, str] | None,
    client_info: dict | None,
) -> str:
    """Identify the MCP host application.

    Priority:
    1. ``x-openai-session`` header → chatgpt
    2. ``baggage`` header with ``sentry-trace_id`` → claude
    3. MCP handshake ``clientInfo.name`` keyword match
    4. Fallback → unknown
    """
    if headers:
        if headers.get("x-openai-session"):
            return "chatgpt"
        baggage = headers.get("baggage", "")
        if "sentry-trace_id=" in baggage:
            return "claude"

    if client_info:
        name = (client_info.get("name") or "").lower()
        if "chatgpt" in name or "openai" in name:
            return "chatgpt"
        if "claude" in name:
            return "claude"

    return "unknown"


def _detect_platform(headers: dict[str, str] | None) -> str:
    """Detect mobile vs desktop from the User-Agent header."""
    if not headers:
        return "unknown"
    ua = headers.get("user-agent", "")
    if not ua:
        return "unknown"
    if _MOBILE_RE.search(ua):
        return "mobile"
    return "desktop"
