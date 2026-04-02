"""Shared helpers for relay tools."""

from __future__ import annotations

import asyncpg
from fastmcp import Context

from quran_mcp.lib.config.profiles import resolve_active_tags
from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.context.request import (
    evaluate_relay_write_authorization,
    get_http_headers,
)
from quran_mcp.lib.db.turn_manager import TurnState
from quran_mcp.lib.relay.turns import get_relay_db_pool, resolve_relay_turn_state
from quran_mcp.mcp.tools._tool_errors import (
    invalid_request_error,
    service_unavailable_error,
)


def get_pool(ctx: Context) -> asyncpg.Pool:
    """Get the DB pool from the tool context.

    Failure contract:
        `[service_unavailable]` if the application context or DB pool is missing.
    """
    pool = get_relay_db_pool(ctx)

    if pool is None:
        raise service_unavailable_error("Database not available")
    return pool


def ensure_relay_write_authorized(_ctx: Context) -> None:
    """Enforce relay write authorization.

    Policy:
    - If preview tools are exposed, relay writes are allowed without extra token.
    - If preview is not exposed but relay writes are reachable, require a shared
      secret header (`X-Relay-Token`) that matches configured
      `RELAY_WRITE_TOKEN`.

    Failure contract:
        `[service_unavailable]` when relay.write_token is not configured on a
        restricted surface, `[invalid_request]` when the caller omits or sends
        the wrong `X-Relay-Token`.
    """
    settings = get_settings()
    error = evaluate_relay_write_authorization(
        headers=get_http_headers(),
        active_tags=resolve_active_tags(settings),
        relay_write_token=settings.relay.write_token.get_secret_value(),
    )
    if error:
        if "relay.write_token" in error:
            raise service_unavailable_error(error)
        raise invalid_request_error(error)


async def load_or_create_turn_state(ctx: Context, pool: asyncpg.Pool) -> TurnState:
    """Load the current TurnState or create one when not yet attached."""
    try:
        return await resolve_relay_turn_state(ctx, pool)
    except RuntimeError as exc:
        raise service_unavailable_error(str(exc)) from exc
