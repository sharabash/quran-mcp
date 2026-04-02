"""Relay middleware — auto-logs tool calls to PostgreSQL.

Architecture
~~~~~~~~~~~~
The relay system has two data paths:

  Path 1 (automatic):  Every tool call → middleware logs it transparently
  Path 2 (voluntary):  AI client calls relay_* tools for feedback

Both paths write to the same PostgreSQL tables. The middleware uses a
**correlation-only** path for relay_* tools: it upserts the turn
and injects relay.turn_id, but does NOT insert a tool_call row (anti-recursion).

    ┌──────────────────────────────────────────────────────────────┐
    │                           AI Client                          │
    │                (e.g., Claude, GPT, Gemini)                   │
    └─────────┬──────────────────────────────┬─────────────────────┘
              │                              │
              │  calls any tool              │  calls relay_*
              │  (search_quran, etc.)        │  tools (voluntary)
              │                              │
              ▼                              ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  RelayMiddleware  (this file)                                │
    │  ── intercepts on_call_tool (best-effort) ──                 │
    │                                                              │
    │  Path 1 (non-relay tools):           Path 2 (relay_* tools): │
    │  • get/create turn ──────────────── get/create turn          │
    │  • INSERT tool_call row ──────────┐ (correlation only —      │
    │  • inject relay.turn_id             │  NO tool_call INSERT)  │
    │  • call_next → tool executes      │ inject relay.turn_id     │
    │  • fire-and-forget UPDATE ────────┤ call_next → tool runs    │
    │                                   │                          │
    │  Turn Correlation                 │                          │
    │  ┌─────────────────────────────┐  │                          │
    │  │ Path A: traceparent header  │  │                          │
    │  │  → keyed by trace_id (32h)  │  │                          │
    │  │  → staleness via max_turn   │  │                          │
    │  │                             │  │                          │
    │  │ Path B: no traceparent      │  │                          │
    │  │  → keyed by shared provider │  │                          │
    │  │    identity seam            │  │                          │
    │  │  → session_id only as final │  │                          │
    │  │    fallback + time-gap      │  │                          │
    │  └─────────────────────────────┘  │                          │
    │                                   │                          │
    │  TurnManager (turn_manager.py)    │                          │
    │  ┌─────────────────────────────┐  │                          │
    │  │ • in-memory LRU (max 500)   │  │                          │
    │  │ • DB hydrate on cache miss  │  │                          │
    │  │ • asyncio.Lock per turn key │  │                          │
    │  └────────────┬────────────────┘  │                          │
    │               │                   │                          │
    │           writes to DB:           │                          │
    │           INSERT turn ◄───────────┘                          │
    │           UPDATE turn (close)                                │
    └───────────────┬──────────────────────────────────────────────┘
                    │
                    │   relay.turn_id is injected into the parent Context
                    │   and is visible to relay_ tools registered on the
                    │   parent MCP server.
                    │
                    │              ┌───────────────────────────────┐
                    │              │                               │
                    ▼              ▼                               │
    ┌──────────────────────────────────────────────────────────────┐
    │                                                              │
    │  Relay Tools (parent-registered, called by AI)               │
    │  tools/relay/                                                │
    │                                                              │
    │  turn_start ─────────── UPDATE turn (promote to explicit)    │
    │  usage_gap ──────────── INSERT identified_gap                │
    │  turn_end ───────────── UPDATE turn (close w/ reflection,    │
    │                          satisfaction, effectiveness)        │
    │                                                              │
    │  (use shared relay turn seam: relay.turn_id → shared         │
    │   TurnManager.get_or_create_turn with same correlation keys) │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌────────────────────────────────────────────────────────────────┐
    │  PostgreSQL  (quran_mcp schema)                                │
    │                                                                │
    │  Automatic (Path 1):     Voluntary (Path 2):                   │
    │  ┌───────────────────┐     ┌─────────────────────────┐         │
    │  │ turn    (INSERT)  │     │ turn (UPDATE — intent,  │         │
    │  │ tool_call (INSERT │     │   reflection, close,    │         │
    │  │   + UPDATE)       │     │   satisfaction)         │         │
    │  └───────────────────┘     │ identified_gap (INSERT) │         │
    │                            └─────────────────────────┘         │
    │  Views (migrations 002–004):                                   │
    │    high_struggle_turns · gap_frequency · gap_frequency_by_tool │
    │    retry_patterns · tool_effectiveness · daily_stats           │
    └────────────────────────────────────────────────────────────────┘

Lifecycle
~~~~~~~~~
• Startup:  lifespan_context_manager (context.py) creates db_pool → middleware reads it
• Runtime:  every tool call flows through on_call_tool
• Shutdown: lifespan calls owner-scoped drain_pending(app_ctx) → close_pool()

Turn Gap Timing
~~~~~~~~~~~~~~~
Turn boundaries are measured from the *previous* call's ``completed_at`` to
the *current* call's ``called_at`` — not start-to-start. This avoids false
turn splits when a long-running tool (e.g. tafsir fetch) exceeds the gap
threshold while still executing.

Diagnostic Logging
~~~~~~~~~~~~~~~~~~
When ``relay.log_turn_identity_event`` is enabled, turn identity diagnostics
write once per unique context_id to ``logs/turn_identity_diagnostic.jsonl``.
Useful for debugging turn correlation with real provider requests.

Limitations
~~~~~~~~~~~
• Path B is still best-effort. When provider continuity headers are absent it
  falls back to session-local/request-local identity, which can still split
  turns if the upstream client rotates transport/session identifiers.
  Path A (traceparent) remains the strongest correlation path.
• Orphan turns (inferred turns that never close) are not auto-closed.

Design specs: codev/specs/0030-relay.md, codev/specs/0031-session-correlation.md
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import uuid as _uuid
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import asyncpg
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from mcp.types import CallToolRequestParams, CallToolResult

from quran_mcp.lib.config.profiles import resolve_active_tags
from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.context.request import (
    evaluate_relay_write_authorization,
    get_lifespan_context,
    get_http_headers,
)
from quran_mcp.lib.relay.diagnostics import (
    HEADER_ALLOWLIST as _HEADER_ALLOWLIST,
    write_turn_identity_diagnostic_event as _write_turn_identity_diagnostic_event,
)
from quran_mcp.lib.relay.metadata import extract_result_metadata as _extract_result_metadata
from quran_mcp.lib.relay.runtime import (
    register_relay_middleware,
    drain_pending as _drain_pending,
    reset_relay_runtime_state as _reset_relay_runtime_state,
)
from quran_mcp.lib.relay.turns import (
    RelayTurnContext,
    activate_relay_turn,
    build_relay_turn_context,
    get_relay_db_pool,
    get_relay_turn_manager,
    resolve_relay_turn_state,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quran_mcp.lib.db.turn_manager import TurnManager

UTC = timezone.utc

# Prefix used by relay tools registered on the parent MCP server
_RELAY_TOOL_PREFIX = "relay_"

def _relay_service_unavailable_error(message: str = "Database not available") -> ToolError:
    """Return a relay-scoped service-unavailable ToolError without importing tool helpers."""
    return ToolError(f"[service_unavailable] {message}")


async def drain_pending(owner: Any, timeout: float = 5.0) -> None:
    """Compatibility wrapper that drains one owner-scoped relay runtime registry."""
    await _drain_pending(owner, timeout=timeout)


def reset_relay_runtime_state(owner: Any) -> None:
    """Compatibility wrapper that resets one owner-scoped relay runtime registry."""
    _reset_relay_runtime_state(owner)


class RelayMiddleware(Middleware):
    """Auto-logs tool calls to PostgreSQL for relay."""

    _MAX_DIAGNOSED_CONTEXTS = 10_000

    def __init__(self, turn_gap_seconds: int = 60, max_turn_seconds: int = 1800) -> None:
        super().__init__()
        self.turn_gap_seconds = turn_gap_seconds
        self.max_turn_seconds = max_turn_seconds
        self._log_turn_identity_enabled: bool | None = None  # lazy-loaded from settings
        self._pending_tasks: set[asyncio.Task] = set()
        self._diagnosed_contexts: set[str] = set()

    def _tracked_fire_and_forget(
        self,
        coro: Awaitable[object],
        description: str = "db write",
    ) -> None:
        """Create a tracked background task owned by this middleware instance."""

        async def _wrapper():
            try:
                await coro
            except Exception:
                logger.warning(f"Relay {description} failed", exc_info=True)

        task = asyncio.create_task(_wrapper())
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _drain_pending_local(self, timeout: float = 5.0) -> None:
        """Drain this middleware instance's pending background writes."""
        if not self._pending_tasks:
            return
        logger.info("Draining %s pending relay writes...", len(self._pending_tasks))
        _, pending = await asyncio.wait(self._pending_tasks, timeout=timeout)
        if pending:
            logger.warning("%s relay writes did not complete in %ss", len(pending), timeout)

    @staticmethod
    def _check_log_turn_identity_setting(app_context: AppContext | None = None) -> bool:
        """Check relay.log_turn_identity_event from settings (lazy, once)."""
        try:
            runtime_settings = app_context.settings if app_context and app_context.settings else get_settings()
            return runtime_settings.relay.log_turn_identity_event
        except Exception:
            logger.debug("Failed to check log_turn_identity_event setting", exc_info=True)
            return False

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext,
    ) -> CallToolResult:
        """Intercept tool calls to log them in the relay DB."""
        tool_name = context.message.name
        fastmcp_ctx = context.fastmcp_context
        pool = get_relay_db_pool(fastmcp_ctx)

        if pool is None:
            if tool_name.startswith(_RELAY_TOOL_PREFIX):
                logger.warning("Relay DB unavailable for %s; failing closed", tool_name)
                raise _relay_service_unavailable_error("Database not available")
            return await call_next(context)

        if fastmcp_ctx is None:
            return await call_next(context)

        app_context = get_lifespan_context(fastmcp_ctx)
        if app_context is None:
            return await call_next(context)

        register_relay_middleware(app_context, self)

        headers = get_http_headers()
        if self._relay_write_guard_denies(headers=headers, app_context=app_context):
            return await call_next(context)

        # Extract correlation data from the shared relay turn seam.
        turn_context = build_relay_turn_context(fastmcp_ctx, headers=headers)

        # Opt-in diagnostic JSONL log (once per context_id)
        if self._log_turn_identity_enabled is None:
            self._log_turn_identity_enabled = self._check_log_turn_identity_setting(app_context)
        if self._log_turn_identity_enabled:
            self._log_turn_identity_diagnostic_event(
                context_id=turn_context.context_id,
                trace_id=turn_context.trace_id,
                provider_continuity_token=turn_context.provider_continuity_token,
                client_info=turn_context.client_info,
                headers=headers,
                tool_name=tool_name,
            )

        mgr = get_relay_turn_manager(fastmcp_ctx)

        if tool_name.startswith(_RELAY_TOOL_PREFIX):
            # Correlation-only path: upsert turn, inject state, no tool_call row
            return await self._correlation_only_path(
                context, call_next, pool, mgr,
                turn_context=turn_context,
                tool_name=tool_name,
            )

        # Full path: get/create turn, INSERT tool_call, execute, UPDATE
        return await self._full_logging_path(
            context, call_next, pool, mgr,
            turn_context=turn_context,
            tool_name=tool_name,
        )

    @staticmethod
    def _relay_write_guard_denies(
        *,
        headers: dict[str, str] | None,
        app_context: AppContext | None = None,
    ) -> bool:
        """Return True when relay write guard blocks this request.

        Uses shared relay context/auth seam in quran_mcp.lib (no tool-layer import).
        """
        try:
            settings = app_context.settings if app_context and app_context.settings else get_settings()
            error = evaluate_relay_write_authorization(
                headers=headers,
                active_tags=resolve_active_tags(settings),
                relay_write_token=settings.relay.write_token.get_secret_value(),
            )
        except Exception:
            logger.debug("Relay write guard evaluation failed; denying relay middleware write", exc_info=True)
            return True
        if error:
            logger.debug("Relay write guard denied middleware correlation write: %s", error)
            return True
        return False

    def _log_turn_identity_diagnostic_event(
        self,
        *,
        context_id: str,
        trace_id: str | None,
        provider_continuity_token: str | None,
        client_info: dict[str, str] | None,
        headers: dict[str, str] | None,
        tool_name: str,
    ) -> None:
        """Write turn correlation diagnostic once per context id per process lifetime."""
        if context_id in self._diagnosed_contexts:
            return
        if len(self._diagnosed_contexts) >= self._MAX_DIAGNOSED_CONTEXTS:
            self._diagnosed_contexts.clear()
        self._diagnosed_contexts.add(context_id)

        safe_headers = (
            {k: v for k, v in headers.items() if k.lower() in _HEADER_ALLOWLIST}
            if headers
            else None
        )
        _write_turn_identity_diagnostic_event(
            diagnostic_payload={
                "ts": datetime.now(UTC).isoformat(),
                "event": "turn_identity_diagnostic",
                "context_id": context_id,
                "trace_id": trace_id,
                "provider_continuity_token": provider_continuity_token,
                "client_info": client_info,
                "first_tool": tool_name,
                "http_headers": safe_headers,
            }
        )

    async def _correlation_only_path(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext,
        pool: asyncpg.Pool,
        mgr: TurnManager,
        *,
        turn_context: RelayTurnContext,
        tool_name: str,
    ) -> CallToolResult:
        """Relay tools: upsert turn and inject relay.turn_id, but no tool_call row."""
        # For start_turn, hint explicit origin so the turn is created as explicit
        origin_hint = "explicit" if tool_name == "relay_turn_start" else "inferred"

        try:
            state = await resolve_relay_turn_state(
                context.fastmcp_context,
                pool,
                turn_gap_seconds=self.turn_gap_seconds,
                max_turn_seconds=self.max_turn_seconds,
                origin_hint=origin_hint,
                prefer_bound_state=False,
                turn_context=turn_context,
                mgr=mgr,
            )
        except (asyncpg.PostgresError, OSError, RuntimeError) as exc:
            logger.warning("Relay correlation-only path failed: %s", exc, exc_info=True)
            raise _relay_service_unavailable_error("Database not available") from exc

        async with activate_relay_turn(context.fastmcp_context, state.turn_id):
            return await call_next(context)

    async def _full_logging_path(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext,
        pool: asyncpg.Pool,
        mgr: TurnManager,
        *,
        turn_context: RelayTurnContext,
        tool_name: str,
    ) -> CallToolResult:
        """Non-relay tools: full logging with tool_call INSERT + UPDATE."""
        # Get or create turn
        try:
            state = await resolve_relay_turn_state(
                context.fastmcp_context,
                pool,
                turn_gap_seconds=self.turn_gap_seconds,
                max_turn_seconds=self.max_turn_seconds,
                prefer_bound_state=False,
                turn_context=turn_context,
                mgr=mgr,
            )
        except (asyncpg.PostgresError, OSError) as exc:
            logger.warning("Relay turn setup failed: %s", exc, exc_info=True)
            return await call_next(context)

        # Assign call index under lock
        async with state.lock:
            call_index = mgr.assign_call_index(state)

        # INSERT tool_call row (pre-execution).
        # UUID generated client-side — no RETURNING needed, id is known immediately.
        # INSERT stays synchronous (execute, not fire-and-forget) to guarantee the
        # row exists before the post-execution UPDATE fires, eliminating the
        # UPDATE-before-INSERT ordering race that would silently update 0 rows.
        params = context.message.arguments or {}
        tool_call_id = _uuid.uuid4()
        called_at = datetime.now(UTC)
        try:
            await pool.execute(
                "INSERT INTO quran_mcp.tool_call "
                "(tool_call_id, turn_id, call_index, tool_name, parameters, called_at) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6)",
                tool_call_id,
                state.turn_id,
                call_index,
                tool_name,
                _json_dumps(params),
                called_at,
            )
        except (asyncpg.PostgresError, OSError) as exc:
            logger.warning("Relay tool_call INSERT failed: %s", exc, exc_info=True)
            tool_call_id = None  # don't attempt UPDATE on unconfirmed row

        async with activate_relay_turn(context.fastmcp_context, state.turn_id):
            # Execute actual tool
            try:
                result = await call_next(context)
            except Exception as exc:
                await mgr.mark_call_completed(state)
                if tool_call_id is not None:
                    completed_at = datetime.now(UTC)
                    duration_ms = int((completed_at - called_at).total_seconds() * 1000)
                    self._tracked_fire_and_forget(
                        pool.execute(
                            "UPDATE quran_mcp.tool_call SET completed_at=$1, duration_ms=$2, "
                            "success=FALSE, error_message=$3 WHERE tool_call_id=$4",
                            completed_at,
                            duration_ms,
                            str(exc)[:1000],
                            tool_call_id,
                        ),
                        "error update",
                    )
                raise

            # Tool succeeded — fire-and-forget result metadata update
            await mgr.mark_call_completed(state)
            if tool_call_id is not None:
                meta = _extract_result_metadata(result)
                completed_at = datetime.now(UTC)
                duration_ms = int((completed_at - called_at).total_seconds() * 1000)
                self._tracked_fire_and_forget(
                    pool.execute(
                        "UPDATE quran_mcp.tool_call SET completed_at=$1, duration_ms=$2, "
                        "success=$3, result_count=$4, result_keys=$5, result_summary=$6 "
                        "WHERE tool_call_id=$7",
                        completed_at,
                        duration_ms,
                        meta["success"],
                        meta["result_count"],
                        meta["result_keys"],
                        meta["result_summary"],
                        tool_call_id,
                    ),
                    "result update",
                )

            return result

def _json_dumps(obj: object) -> str:
    """JSON serialize for asyncpg JSONB parameters."""
    return _json.dumps(obj, default=str)
