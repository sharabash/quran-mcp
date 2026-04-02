"""Shared public-tool error helpers for consistent MCP contracts."""

from __future__ import annotations

import asyncpg
from fastmcp import Context
from fastmcp.exceptions import ToolError

from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError

FETCH_TOOL_ERROR_CONTRACT = (
    "Failure contract: `[invalid_request]` for malformed inputs, "
    "`[not_found]` when requested canonical data is absent, "
    "`[service_unavailable]` when the required runtime resource is unavailable, "
    "`[continuation_invalid|tampered|expired|conflict|exhausted|legacy]` for bad continuation "
    "tokens."
)
STANDARD_RESOURCE_ERROR_CONTRACT = (
    "Failure contract: `[invalid_request]` for malformed or mutually incompatible inputs, "
    "and `[service_unavailable]` when the required runtime resource is unavailable."
)
RELAY_WRITE_ERROR_CONTRACT = (
    "Failure contract: `[service_unavailable]` when relay storage or relay-write configuration "
    "is unavailable, and `[invalid_request]` when the caller omits or sends an invalid "
    "`X-Relay-Token` on restricted surfaces."
)


def invalid_request_error(message: str) -> ToolError:
    """Return a stable invalid-request ToolError."""
    return ToolError(f"[invalid_request] {message}")


def not_found_error(message: str = "Requested data not found") -> ToolError:
    """Return a stable not-found ToolError."""
    return ToolError(f"[not_found] {message}")


def service_unavailable_error(message: str = "Database not available") -> ToolError:
    """Return a stable service-unavailable ToolError."""
    return ToolError(f"[service_unavailable] {message}")


def require_db_pool(ctx: Context | None) -> asyncpg.Pool:
    """Require the shared database pool from the attached application context."""
    from quran_mcp.mcp.tools._tool_context import resolve_app_context

    app_ctx = resolve_app_context(ctx)
    pool = app_ctx.db_pool
    if pool is None:
        raise service_unavailable_error()
    return pool


def translate_fetch_domain_error(exc: DataNotFoundError | DataStoreError) -> ToolError:
    """Translate edition-fetch domain errors into public MCP ToolError contracts."""
    if isinstance(exc, DataNotFoundError):
        return not_found_error(str(exc))
    if isinstance(exc, DataStoreError):
        return service_unavailable_error()
    raise TypeError(f"Unsupported fetch domain error: {type(exc)!r}")
