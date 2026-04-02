"""Turn lifecycle management for the relay system.

Manages the mapping from W3C traceparent trace-id to relay turns.
Uses in-memory LRU cache with DB as source of truth (cache-aside pattern).
Per-key asyncio.Lock serializes turn creation decisions.

Turn is the top-level entity (no session table). See spec 0031.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

UTC = timezone.utc

# Max cached turns before LRU eviction
_MAX_CACHED_TURNS = 500


def _jsonb_or_none(obj: Any) -> str | None:
    """Serialize to JSON string for asyncpg JSONB params, or None if obj is None."""
    return json.dumps(obj) if obj is not None else None


@dataclass
class TurnState:
    """In-memory state for one turn's relay tracking."""

    turn_id: UUID
    call_index: int
    last_completed_at: datetime | None
    started_at: datetime
    origin: str  # 'explicit' or 'inferred'
    ended: bool
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TurnManager:
    """Manages relay turns keyed by trace-id or context-id.

    Thread-safe via per-key asyncio.Lock + global creation lock.
    DB is source of truth; in-memory OrderedDict is an LRU cache that
    hydrates on miss and evicts oldest entries beyond _MAX_CACHED_TURNS.
    """

    def __init__(self, max_cached: int = _MAX_CACHED_TURNS) -> None:
        self._turns: OrderedDict[str, TurnState] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._max_cached = max_cached

    def _get_key_lock(self, key: str) -> asyncio.Lock:
        """Get or create a per-key lock (under global lock is not needed here
        since Python dict ops are atomic for single statements)."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_or_create_turn(
        self,
        pool: asyncpg.Pool,
        *,
        trace_id: str | None = None,
        context_id: str | None = None,
        provider_continuity_token: str | None = None,
        client_info: dict[str, Any] | None = None,
        turn_gap_seconds: int = 60,
        max_turn_seconds: int = 1800,
        origin_hint: str = "inferred",
    ) -> TurnState:
        """Get or create a TurnState for the given trace_id or context_id.

        Path A (trace_id provided): keyed by trace_id, staleness via max_turn_seconds.
        Path B (no trace_id): keyed by context_id with time-gap inference.
        Path B is best-effort: it assumes the MCP session ID stays consistent
        across all tool calls in a logical turn. This is **not** guaranteed —
        multi-tenant distributed clients (e.g. OpenAI's MCP gateway) may rotate
        session IDs across load-balanced nodes, causing spurious new turns.

        Args:
            pool: Async PostgreSQL pool used for turn persistence
            trace_id: W3C traceparent trace-id (32 hex chars). Primary key path.
            context_id: Fallback key (typically mcp_session_id). Used when trace_id absent.
            provider_continuity_token: Passive continuity token from provider headers.
            client_info: Client info dict (from MCP initialize handshake).
            turn_gap_seconds: Inactivity gap before creating a new turn (Path B).
            max_turn_seconds: Max turn age before staleness (Path A).
            origin_hint: 'explicit' for start_turn tool, 'inferred' for normal calls.
        """
        # TODO(relay): Revisit whether this trace-id / context-gap heuristic is
        # the best way to determine turn scope. We may need to tighten the
        # current false-split / false-merge behavior, incorporate stronger
        # provider-specific signals, or simplify the model for performance.
        if trace_id:
            return await self._path_a_trace_id(
                pool,
                trace_id=trace_id,
                provider_continuity_token=provider_continuity_token,
                client_info=client_info,
                max_turn_seconds=max_turn_seconds,
                origin_hint=origin_hint,
            )
        else:
            cache_key = f"ctx:{context_id or 'unknown'}"
            return await self._path_b_fallback(
                pool,
                cache_key=cache_key,
                provider_continuity_token=provider_continuity_token,
                client_info=client_info,
                turn_gap_seconds=turn_gap_seconds,
                max_turn_seconds=max_turn_seconds,
                origin_hint=origin_hint,
            )

    async def _path_a_trace_id(
        self,
        pool: asyncpg.Pool,
        *,
        trace_id: str,
        provider_continuity_token: str | None,
        client_info: dict[str, Any] | None,
        max_turn_seconds: int,
        origin_hint: str,
    ) -> TurnState:
        """Path A: trace_id provided — keyed by trace_id, staleness guard."""
        key_lock = self._get_key_lock(trace_id)
        async with key_lock:
            now = datetime.now(UTC)

            # Check cache
            if trace_id in self._turns:
                state = self._turns[trace_id]
                age = (now - state.started_at).total_seconds()
                if age < max_turn_seconds and not state.ended:
                    self._turns.move_to_end(trace_id)
                    return state
                # Stale — close old turn and fall through
                if not state.ended:
                    await self._close_turn(pool, state)
                del self._turns[trace_id]

            # Cache miss — single query fetches turn + max call_index together,
            # eliminating the second DB round-trip (_max_call_index) inside the lock.
            row = await pool.fetchrow(
                "SELECT t.turn_id, t.started_at, t.origin, t.ended_at, "
                "COALESCE(MAX(tc.call_index), 0) AS max_call_index "
                "FROM quran_mcp.turn t "
                "LEFT JOIN quran_mcp.tool_call tc ON tc.turn_id = t.turn_id "
                "WHERE t.trace_id = $1 "
                "AND t.started_at > NOW() - make_interval(secs := $2) "
                "GROUP BY t.turn_id, t.started_at, t.origin, t.ended_at "
                "ORDER BY t.started_at DESC LIMIT 1",
                trace_id,
                float(max_turn_seconds),
            )

            if row and row["ended_at"] is None:
                state = TurnState(
                    turn_id=row["turn_id"],
                    call_index=row["max_call_index"],
                    last_completed_at=None,
                    started_at=row["started_at"],
                    origin=row["origin"],
                    ended=False,
                )
                self._turns[trace_id] = state
                self._evict_if_needed()
                return state

            # Not found or all stale — create new turn
            return await self._insert_turn(
                pool,
                cache_key=trace_id,
                trace_id=trace_id,
                provider_continuity_token=provider_continuity_token,
                client_info=client_info,
                origin=origin_hint,
            )

    async def _path_b_fallback(
        self,
        pool: asyncpg.Pool,
        *,
        cache_key: str,
        provider_continuity_token: str | None,
        client_info: dict[str, Any] | None,
        turn_gap_seconds: int,
        max_turn_seconds: int,
        origin_hint: str,
    ) -> TurnState:
        """Path B: no trace_id — time-gap inference keyed by context_id.

        Assumption: the MCP session ID (context_id) remains stable across all
        tool calls within a single logical turn. If the client rotates session
        IDs (e.g. load-balanced multi-node MCP gateways), this path will create
        spurious new turns. Path A (traceparent) does not have this fragility.
        """
        key_lock = self._get_key_lock(cache_key)
        async with key_lock:
            now = datetime.now(UTC)

            if cache_key in self._turns:
                state = self._turns[cache_key]
                age = (now - state.started_at).total_seconds()

                if state.ended or age > max_turn_seconds:
                    if not state.ended:
                        await self._close_turn(pool, state)
                    del self._turns[cache_key]
                elif state.last_completed_at is not None:
                    gap = (now - state.last_completed_at).total_seconds()
                    if gap > turn_gap_seconds and state.origin != "explicit":
                        # Inferred turn exceeded gap — close and create new
                        await self._close_turn(pool, state)
                        del self._turns[cache_key]
                    else:
                        self._turns.move_to_end(cache_key)
                        return state
                else:
                    self._turns.move_to_end(cache_key)
                    return state

            return await self._insert_turn(
                pool,
                cache_key=cache_key,
                trace_id=None,
                provider_continuity_token=provider_continuity_token,
                client_info=client_info,
                origin=origin_hint,
            )

    async def _insert_turn(
        self,
        pool: asyncpg.Pool,
        *,
        cache_key: str,
        trace_id: str | None,
        provider_continuity_token: str | None,
        client_info: dict[str, Any] | None,
        origin: str,
    ) -> TurnState:
        """INSERT a new turn row and cache the state."""
        now = datetime.now(UTC)
        turn_id = await pool.fetchval(
            "INSERT INTO quran_mcp.turn (trace_id, provider_continuity_token, client_info, origin, started_at) "
            "VALUES ($1, $2, $3::jsonb, $4, $5) RETURNING turn_id",
            trace_id,
            provider_continuity_token,
            _jsonb_or_none(client_info),
            origin,
            now,
        )
        state = TurnState(
            turn_id=turn_id,
            call_index=0,
            last_completed_at=None,
            started_at=now,
            origin=origin,
            ended=False,
        )
        self._turns[cache_key] = state
        self._evict_if_needed()
        return state

    async def _close_turn(self, pool: asyncpg.Pool, state: TurnState) -> None:
        """Close a turn in DB and mark state as ended."""
        await pool.execute(
            "UPDATE quran_mcp.turn SET ended_at = NOW(), end_origin = 'inferred' "
            "WHERE turn_id = $1 AND ended_at IS NULL",
            state.turn_id,
        )
        state.ended = True

    async def _max_call_index(self, pool: asyncpg.Pool, turn_id: UUID) -> int:
        """Get the max call_index for a turn (for DB hydration)."""
        val = await pool.fetchval(
            "SELECT COALESCE(MAX(call_index), 0) FROM quran_mcp.tool_call WHERE turn_id = $1",
            turn_id,
        )
        return val or 0

    def assign_call_index(self, state: TurnState) -> int:
        """Increment and return the next call_index. Must be called under state.lock."""
        state.call_index += 1
        return state.call_index

    async def mark_call_completed(self, state: TurnState) -> None:
        """Update last_completed_at under the turn's lock."""
        async with state.lock:
            state.last_completed_at = datetime.now(UTC)

    async def promote_turn(
        self,
        pool: asyncpg.Pool,
        state: TurnState,
        *,
        interpreted_intent: str | None = None,
        pre_turn_expectations: dict[str, Any] | None = None,
    ) -> None:
        """Promote current turn to explicit (called by start_turn tool)."""
        async with state.lock:
            await pool.execute(
                "UPDATE quran_mcp.turn SET origin = 'explicit', "
                "interpreted_intent = COALESCE($2, interpreted_intent), "
                "pre_turn_expectations = COALESCE($3::jsonb, pre_turn_expectations) "
                "WHERE turn_id = $1",
                state.turn_id,
                interpreted_intent,
                _jsonb_or_none(pre_turn_expectations),
            )
            state.origin = "explicit"

    async def complete_turn(
        self,
        pool: asyncpg.Pool,
        state: TurnState,
        *,
        post_turn_reflection: dict[str, Any] | None = None,
        overall_satisfaction: int | None = None,
        tool_effectiveness: list[dict[str, Any]] | None = None,
        improvement_suggestions: str | None = None,
    ) -> None:
        """Complete current turn with reflection and absorbed session fields."""
        async with state.lock:
            await pool.execute(
                "UPDATE quran_mcp.turn SET "
                "ended_at = NOW(), end_origin = 'explicit', "
                "post_turn_reflection = COALESCE($2::jsonb, post_turn_reflection), "
                "overall_satisfaction = COALESCE($3, overall_satisfaction), "
                "tool_effectiveness = COALESCE($4::jsonb, tool_effectiveness), "
                "improvement_suggestions = COALESCE($5, improvement_suggestions) "
                "WHERE turn_id = $1 AND ended_at IS NULL",
                state.turn_id,
                _jsonb_or_none(post_turn_reflection),
                overall_satisfaction,
                _jsonb_or_none(tool_effectiveness),
                improvement_suggestions,
            )
            state.ended = True

    def find_state_by_turn_id(self, turn_id: UUID) -> TurnState | None:
        """Look up a cached TurnState by its turn_id."""
        for state in self._turns.values():
            if state.turn_id == turn_id:
                return state
        return None

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        while len(self._turns) > self._max_cached:
            evicted_key, _ = self._turns.popitem(last=False)
            self._locks.pop(evicted_key, None)
            logger.debug(f"Evicted turn cache entry: {evicted_key}")

    def clear_cache(self) -> None:
        """Clear the in-memory turn cache. Useful for testing."""
        self._turns.clear()
        self._locks.clear()


def build_turn_manager() -> TurnManager:
    """Create an isolated turn manager instance."""
    return TurnManager()


def get_or_create_turn_manager(owner: Any) -> TurnManager:
    """Return owner-scoped turn manager state, creating it on first access."""
    if owner is None:
        raise ValueError("owner is required for turn manager ownership")
    manager = getattr(owner, "turn_manager", None)
    if manager is None:
        manager = build_turn_manager()
        setattr(owner, "turn_manager", manager)
    return manager


def reset_turn_manager(owner: Any) -> None:
    """Reset owner-scoped turn manager state."""
    if owner is None:
        raise ValueError("owner is required for turn manager ownership")
    setattr(owner, "turn_manager", build_turn_manager())
