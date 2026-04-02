"""Relay turn resolution shared by middleware and relay tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Mapping
from uuid import UUID

import asyncpg

from quran_mcp.lib.context.request import (
    extract_client_info,
    extract_provider_continuity_token,
    extract_trace_id,
    get_lifespan_context,
    get_active_relay_turn_id,
    get_http_headers,
    reset_active_relay_turn_id,
    resolve_client_identity,
    set_active_relay_turn_id,
)
from quran_mcp.lib.db.turn_manager import TurnState, get_or_create_turn_manager

if TYPE_CHECKING:
    from quran_mcp.lib.db.turn_manager import TurnManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelayTurnContext:
    """Correlation inputs used to resolve or create a relay turn."""

    trace_id: str | None
    provider_continuity_token: str | None
    context_id: str
    client_info: dict[str, str] | None


def get_relay_db_pool(owner: Any) -> asyncpg.Pool | None:
    """Return the relay DB pool from the current ownership boundary, if any."""
    try:
        direct_pool = getattr(owner, "db_pool", None)
        if direct_pool is not None:
            return direct_pool

        app_context = get_lifespan_context(owner)
    except AttributeError:
        return None

    if app_context is None:
        return None
    return getattr(app_context, "db_pool", None)


def get_relay_turn_manager(owner: Any) -> TurnManager:
    """Return the owner-scoped relay turn manager."""
    app_context = get_lifespan_context(owner)
    if app_context is None:
        raise RuntimeError("Relay application context not available")
    manager = getattr(app_context, "turn_manager", None)
    if manager is None:
        manager = get_or_create_turn_manager(app_context)
    return manager


def build_relay_turn_context(
    ctx: Any,
    *,
    headers: Mapping[str, str] | None = None,
) -> RelayTurnContext:
    """Build the shared relay correlation context from one FastMCP request."""
    resolved_headers = dict(headers) if headers is not None else get_http_headers()
    trace_id = extract_trace_id(resolved_headers)
    session_id = getattr(ctx, "session_id", None)
    context_id = session_id or "unknown"
    if trace_id is None:
        context_id = resolve_client_identity(
            headers=resolved_headers,
            session_id=session_id,
            fallback=context_id,
        )
    return RelayTurnContext(
        trace_id=trace_id,
        provider_continuity_token=extract_provider_continuity_token(resolved_headers),
        context_id=context_id,
        client_info=extract_client_info(ctx),
    )


async def get_bound_relay_turn_state(
    ctx: Any,
    *,
    mgr: TurnManager | None = None,
) -> TurnState | None:
    """Return an already-bound turn state from request state/context vars, if any."""
    manager = mgr or get_relay_turn_manager(ctx)
    turn_id = await _get_bound_relay_turn_id(ctx)
    if not turn_id:
        return None
    try:
        return manager.find_state_by_turn_id(UUID(turn_id))
    except (TypeError, ValueError, AttributeError):
        logger.debug("Ignoring invalid bound relay turn id: %r", turn_id)
        return None


async def resolve_relay_turn_state(
    ctx: Any,
    pool: asyncpg.Pool,
    *,
    turn_gap_seconds: int = 60,
    max_turn_seconds: int = 1800,
    origin_hint: str = "inferred",
    prefer_bound_state: bool = True,
    headers: Mapping[str, str] | None = None,
    turn_context: RelayTurnContext | None = None,
    mgr: TurnManager | None = None,
) -> TurnState:
    """Resolve the current relay turn or create one from shared correlation inputs."""
    if pool is None:
        raise RuntimeError("Relay database not available")

    manager = mgr or get_relay_turn_manager(ctx)

    if prefer_bound_state:
        bound_state = await get_bound_relay_turn_state(ctx, mgr=manager)
        if bound_state is not None:
            return bound_state

    resolved_turn_context = turn_context or build_relay_turn_context(ctx, headers=headers)
    logger.debug(
        "Resolving relay turn via shared seam (trace_id=%s, context_id=%s, origin=%s)",
        resolved_turn_context.trace_id,
        resolved_turn_context.context_id,
        origin_hint,
    )
    return await manager.get_or_create_turn(
        pool,
        trace_id=resolved_turn_context.trace_id,
        context_id=resolved_turn_context.context_id,
        provider_continuity_token=resolved_turn_context.provider_continuity_token,
        client_info=resolved_turn_context.client_info,
        turn_gap_seconds=turn_gap_seconds,
        max_turn_seconds=max_turn_seconds,
        origin_hint=origin_hint,
    )


@asynccontextmanager
async def activate_relay_turn(ctx: Any, turn_id: UUID | str) -> AsyncIterator[None]:
    """Bind a turn ID to the current request for middleware and relay tools."""
    turn_id_str = str(turn_id)
    token = set_active_relay_turn_id(turn_id_str)
    try:
        await _set_relay_turn_state(ctx, turn_id_str)
        yield
    finally:
        reset_active_relay_turn_id(token)


async def _get_bound_relay_turn_id(ctx: Any) -> str | None:
    """Resolve a relay turn ID from request state first, then request-local context."""
    try:
        turn_id = await ctx.get_state("relay.turn_id")
    except Exception:
        logger.debug("Could not read relay.turn_id from context state", exc_info=True)
        turn_id = None
    return turn_id or get_active_relay_turn_id()


async def _set_relay_turn_state(ctx: Any, turn_id: str) -> None:
    """Best-effort state injection for FastMCP contexts."""
    try:
        await ctx.set_state("relay.turn_id", turn_id)
    except Exception:
        logger.debug("Could not inject relay.turn_id state", exc_info=True)
