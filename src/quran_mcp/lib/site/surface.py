"""Compose the outer public HTTP surface around FastMCP's inner transport app."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware import Middleware as StarletteMiddleware
from starlette.middleware.cors import CORSMiddleware as StarletteCORS

from quran_mcp.lib.site.handlers import handle_public_route
from quran_mcp.lib.config.settings import Settings
from quran_mcp.lib.site.manifest import validate_required_assets

from fastmcp import FastMCP

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


def mount_public_routes(
    *,
    mcp: "FastMCP",
    settings: "Settings",
    logger: logging.Logger,
) -> None:
    """Replace ``mcp.http_app`` with a factory for the outer public HTTP app.

    FastMCP starts with an ``mcp.http_app`` factory that builds only the inner
    MCP transport app. This function replaces that factory with one that builds
    an outer ASGI app with three responsibilities:

    1. Serve browser-facing routes such as `/`, `/documentation`, and assets.
    2. Apply CORS to that whole outer surface so browser hosts can call it.
    3. Fall through to the original inner MCP transport app for MCP traffic.
    """

    # Validate required assets once at startup. Missing required assets
    # fail loudly here instead of becoming surprise 404s later.
    missing = validate_required_assets()
    if missing:
        joined = "\n".join(f"- {item}" for item in missing)
        raise RuntimeError(
            "Public HTTP manifest references missing required assets:\n"
            f"{joined}"
        )

    # `mcp.http_app` is not the built ASGI app object yet. It is the factory
    # FastMCP/Uvicorn will call later to materialize that app. Capture the
    # original factory here so the new outer public app can delegate to it.
    build_inner_transport_http_app = mcp.http_app

    def build_outer_public_http_app(**kwargs):
        # After `mount_public_routes()` runs, this nested function
        # becomes the new `mcp.http_app` factory. When FastMCP/Uvicorn later
        # calls `mcp.http_app(...)`, it will build the full outer public app,
        # not just the raw inner MCP transport app.

        # FastMCP accepts optional ASGI middleware when it materializes the app.
        # We apply those to the outer composite app, not only to the inner MCP
        # transport app, so debugging and wrappers see the same surface clients see.
        extra_middleware = list(kwargs.pop("middleware", None) or [])

        # This is the original FastMCP HTTP app: the inner transport app that
        # knows how to handle MCP protocol traffic such as tool/resource/prompt
        # requests. It does not know about landing pages or static assets.
        inner_transport_http_app = build_inner_transport_http_app(**kwargs)

        async def outer_public_http_app(scope: "Scope", receive: "Receive", send: "Send") -> None:
            # Non-HTTP scopes (for example lifespan) bypass the public-route
            # wrapper completely and go straight to FastMCP's inner app.
            if scope["type"] != "http":
                await inner_transport_http_app(scope, receive, send)
                return

            handled = await handle_public_route(
                scope,
                receive,
                send,
                mcp=mcp,
                settings=settings,
                logger=logger,
            )
            if handled:
                return

            await inner_transport_http_app(scope, receive, send)

        outer_public_http_app.state = inner_transport_http_app.state  # type: ignore[attr-defined]  # ASGI app .state is runtime-set by Starlette

        cors_wrapped_public_http_app = StarletteCORS(
            outer_public_http_app,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["mcp-session-id"],
        )
        cors_wrapped_public_http_app.state = inner_transport_http_app.state  # type: ignore[attr-defined]  # ASGI app .state is runtime-set by Starlette

        return _apply_asgi_middleware(
            cors_wrapped_public_http_app,
            extra_middleware,
            state=inner_transport_http_app.state,
        )

    mcp.http_app = build_outer_public_http_app  # type: ignore[assignment]  # monkey-patch FastMCP's app factory for public route injection


def _apply_asgi_middleware(app: Any, middleware: list[StarletteMiddleware], *, state: Any) -> Any:
    wrapped_app = app
    for entry in reversed(middleware):
        wrapped_app = entry.cls(wrapped_app, *entry.args, **entry.kwargs)
    wrapped_app.state = state  # type: ignore[attr-defined]  # ASGI app .state is runtime-set by Starlette
    return wrapped_app
