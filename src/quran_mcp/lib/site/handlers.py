"""Request dispatch for the public browser/docs HTTP surface.

Routes are declared in manifest.py as a single routes dict. This
module turns those declarations into HTTP responses. Each classification
has a handler function. Special routes (health check, documentation JSON)
that aren't asset-backed stay as explicit cases here.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from fastmcp import FastMCP

from quran_mcp.lib.config.paths import HEALTH_PATH
from quran_mcp.lib.config.settings import Settings
from quran_mcp.lib.documentation.generator import render_docs_json
from quran_mcp.lib.documentation.runtime import get_or_create_documentation_runtime_state
from quran_mcp.lib.site.health import (
    get_or_create_health_runtime_state,
    health_check_handler,
)
from quran_mcp.lib.site.manifest import routes

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_public_route(
    scope: "Scope",
    receive: "Receive",
    send: "Send",
    *,
    mcp: "FastMCP",
    settings: "Settings",
    logger: logging.Logger,
) -> bool:
    """Handle a browser/public route and return True when consumed.

    Dispatch order:
    1. Static files (exact path match)
    2. Downloads (exact path match, Content-Disposition: attachment)
    3. Directory mounts (longest prefix match)
    4. HTML pages (exact path match, except "/" which has accept-header logic)
    5. /documentation/data.json (generated, not in manifest)
    6. /.health (generated, not in manifest)
    7. Landing page at "/" (only for browser requests, not SSE/MCP)

    Generated routes are not in routes because they aren't
    asset-backed — they produce dynamic responses at request time.
    """
    path = scope["path"]
    method = scope["method"]

    # 1. Static files
    entry = routes.get("static", {}).get(path)
    if entry is not None:
        response = _static_file_response(entry)
        if response is not None:
            await response(scope, receive, send)
            return True

    # 2. Downloads
    entry = routes.get("downloads", {}).get(path)
    if entry is not None:
        await _download_response(scope, receive, send, path=path, entry=entry)
        return True

    # 3. Directory mounts — longest prefix wins so /documentation/assets/
    #    matches before /documentation/ regardless of dict order.
    for prefix, dir_entry in sorted(
        routes.get("dirs", {}).items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if path.startswith(prefix):
            response = _dir_response(dir_entry, path, prefix)
            if response is not None:
                await response(scope, receive, send)
                return True

    # 4. HTML pages (skip "/" — handled as landing page below)
    if path != "/":
        entry = routes.get("pages", {}).get(path)
        if entry is not None:
            logger.info("%s %s from %s", method, path, _real_ip(scope))
            await _page_response(scope, receive, send, entry=entry)
            return True

    # 5. Documentation data endpoint (generated, not in manifest)
    if path == "/documentation/data.json":
        await _documentation_json_response(scope, receive, send, mcp=mcp, logger=logger)
        return True

    # 6. Health check (generated, not in manifest)
    if path == HEALTH_PATH:
        await health_check_handler(
            scope,
            receive,
            send,
            settings,
            runtime_state=get_or_create_health_runtime_state(mcp),
        )
        return True

    # 7. Landing page — only for browser GET/HEAD, not SSE/MCP clients
    if _should_serve_landing(scope):
        landing = routes.get("pages", {}).get("/")
        if landing is not None:
            logger.info("%s / (landing) from %s", method, _real_ip(scope))
            await _page_response(scope, receive, send, entry=landing)
            return True

    return False


# ---------------------------------------------------------------------------
# Response builders — one per classification.
# ---------------------------------------------------------------------------


def _static_file_response(entry: dict[str, Any]) -> Response | None:
    """Build a FileResponse for a static file entry."""
    file_path: Path = entry["file"]
    if file_path.is_file():
        return FileResponse(
            file_path,
            media_type=entry.get("type"),
            headers=entry.get("headers", {"Cache-Control": "public, max-age=3600"}),
        )
    if entry.get("required", True):
        return PlainTextResponse(
            f"Required public asset missing: {file_path}",
            status_code=500,
        )
    return None


async def _download_response(
    scope: "Scope",
    receive: "Receive",
    send: "Send",
    *,
    path: str,
    entry: dict[str, Any],
) -> None:
    """Serve a file as a download (Content-Disposition: attachment)."""
    file_path: Path = entry["file"]
    filename = entry.get("filename", path.lstrip("/"))

    if not file_path.is_file():
        response = PlainTextResponse(f"{filename} not found", status_code=404)
        await response(scope, receive, send)
        return

    response = FileResponse(
        file_path,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-store",
        },
    )
    await response(scope, receive, send)


def _dir_response(entry: dict[str, Any], request_path: str, prefix: str) -> Response | None:
    """Resolve a file under a directory mount and return a FileResponse.

    Path traversal is blocked by resolving to an absolute path and
    verifying it stays within the base directory.
    """
    base_dir: Path = entry["dir"].resolve()
    relative = request_path.removeprefix(prefix).lstrip("/")

    if not relative:
        return None

    candidate = (base_dir / relative).resolve()
    if not candidate.is_relative_to(base_dir):
        return None

    if not candidate.is_file():
        return None

    media_type = entry.get("types", {}).get(candidate.suffix.lower())
    if media_type is None:
        return None

    return FileResponse(
        candidate,
        media_type=media_type,
        headers=entry.get("headers", {"Cache-Control": "public, max-age=3600"}),
    )


async def _page_response(
    scope: "Scope",
    receive: "Receive",
    send: "Send",
    *,
    entry: dict[str, Any],
) -> None:
    """Read an HTML file and serve it as an HTMLResponse."""
    text = _read_text_file(entry["file"])

    if text is None:
        message = entry.get("missing", "Required public page asset missing.")
        status = 500 if entry.get("required", True) else entry.get("missing_status_code", 503)
        response = PlainTextResponse(message, status_code=status)
        await response(scope, receive, send)
        return

    response = HTMLResponse(text, headers=entry.get("headers", {"Cache-Control": "public, max-age=3600"}))
    await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Special routes (generated, not asset-backed — not in manifest).
# ---------------------------------------------------------------------------


async def _documentation_json_response(
    scope: "Scope",
    receive: "Receive",
    send: "Send",
    *,
    mcp: "FastMCP",
    logger: logging.Logger,
) -> None:
    try:
        json_str = await render_docs_json(
            mcp,
            runtime_state=get_or_create_documentation_runtime_state(mcp),
        )
        response = Response(
            json_str,
            media_type="application/json",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception:
        logger.exception("Failed to render /documentation/data.json")
        response = Response(
            '{"error": "Failed to generate docs data"}',
            media_type="application/json",
            status_code=500,
        )

    await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _read_text_file(path: Path) -> str | None:
    """Read a file as UTF-8 text. Cached for the lifetime of the process.

    This means rebuilt assets (e.g. landing.html after a Svelte build)
    won't be picked up until the server restarts. Acceptable in production
    where deploys restart the process.
    """
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _real_ip(scope: "Scope") -> str:
    """Extract client IP for logging. Trusts cf-connecting-ip (behind Cloudflare)."""
    for name, value in scope.get("headers", []):
        if name == b"cf-connecting-ip":
            return value.decode("latin-1")
    client = scope.get("client")
    return client[0] if client else "unknown"


def _should_serve_landing(scope: "Scope") -> bool:
    """Serve the landing page for browser requests to /.

    MCP clients send Accept: text/event-stream for SSE transport.
    Browsers send Accept: text/html. We serve the landing page for
    everything EXCEPT SSE clients, so MCP traffic falls through to
    the inner transport app.
    """
    if scope["path"] != "/" or scope["method"] not in {"GET", "HEAD"}:
        return False

    for header_name, header_value in scope.get("headers", []):
        if header_name == b"accept":
            accept = header_value.decode("latin-1", errors="replace")
            if "text/event-stream" in accept:
                return False
    return True
