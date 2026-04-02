"""Shared runtime context resolution for MCP tool handlers."""
from __future__ import annotations

from typing import NoReturn, cast

from fastmcp import Context
from fastmcp.exceptions import ToolError

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.presentation.pagination import ContinuationError
from quran_mcp.mcp.tools._tool_errors import invalid_request_error


def resolve_app_context(ctx: Context | None) -> AppContext:
    """Extract the typed AppContext from a FastMCP Context.

    All tool handlers need to reach the lifespan-scoped AppContext.
    This helper centralizes the three-step drill-down and the error
    message so callers don't repeat the same getattr chain.
    """
    if ctx is None:
        raise invalid_request_error("runtime context is required")

    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        raise invalid_request_error("runtime context is required")

    app_ctx = getattr(request_context, "lifespan_context", None)
    if app_ctx is None:
        raise invalid_request_error("runtime context is required")

    return cast(AppContext, app_ctx)


def raise_continuation_error(exc: ContinuationError) -> NoReturn:
    """Translate a ContinuationError into a ToolError with a stable contract prefix."""
    raise ToolError(f"[continuation_{exc.reason}] {exc.message}") from exc
