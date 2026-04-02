"""Tests for quran_mcp.lib.db.turn_manager — pure cache/state operations.

Full turn lifecycle (DB INSERT/UPDATE, Path A/B routing) requires PostgreSQL
and belongs in tests/integration/. These tests cover the in-memory LRU cache,
call index assignment, state lookup, and serialization helpers.

Covers:
  - _jsonb_or_none: serialization helper
  - TurnManager LRU eviction with configurable max_cached
  - assign_call_index: monotonic increment
  - find_state_by_turn_id: cache lookup by UUID
  - mark_call_completed: updates last_completed_at
  - clear_cache: full reset
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from quran_mcp.lib.db.turn_manager import (
    build_turn_manager,
    TurnManager,
    TurnState,
    get_or_create_turn_manager,
    reset_turn_manager,
    _jsonb_or_none,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# _jsonb_or_none
# ---------------------------------------------------------------------------


class TestJsonbOrNone:
    def test_dict_serialized(self):
        result = _jsonb_or_none({"key": "value"})
        assert result == '{"key": "value"}'

    def test_none_returns_none(self):
        assert _jsonb_or_none(None) is None

    def test_list_serialized(self):
        result = _jsonb_or_none([1, 2, 3])
        assert result == "[1, 2, 3]"


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def _make_state(origin: str = "inferred") -> TurnState:
    return TurnState(
        turn_id=uuid4(),
        call_index=0,
        last_completed_at=None,
        started_at=datetime.now(UTC),
        origin=origin,
        ended=False,
    )


class TestLRUEviction:
    def test_evicts_oldest_when_over_max(self):
        mgr = TurnManager(max_cached=3)
        states = {}

        for i in range(4):
            key = f"key-{i}"
            state = _make_state()
            mgr._turns[key] = state
            states[key] = state
            mgr._locks[key] = asyncio.Lock()

        mgr._evict_if_needed()

        # Oldest (key-0) should be evicted
        assert "key-0" not in mgr._turns
        assert "key-0" not in mgr._locks
        assert len(mgr._turns) == 3

    def test_no_eviction_when_under_max(self):
        mgr = TurnManager(max_cached=10)
        for i in range(5):
            mgr._turns[f"key-{i}"] = _make_state()

        mgr._evict_if_needed()
        assert len(mgr._turns) == 5

    def test_evicts_multiple_to_reach_max(self):
        mgr = TurnManager(max_cached=2)
        for i in range(5):
            mgr._turns[f"key-{i}"] = _make_state()

        mgr._evict_if_needed()
        assert len(mgr._turns) == 2
        # Should keep the most recent (key-3, key-4)
        assert "key-3" in mgr._turns
        assert "key-4" in mgr._turns


# ---------------------------------------------------------------------------
# assign_call_index
# ---------------------------------------------------------------------------


class TestAssignCallIndex:
    def test_increments_monotonically(self):
        mgr = TurnManager()
        state = _make_state()

        assert mgr.assign_call_index(state) == 1
        assert mgr.assign_call_index(state) == 2
        assert mgr.assign_call_index(state) == 3

    def test_starts_from_current_value(self):
        mgr = TurnManager()
        state = _make_state()
        state.call_index = 10

        assert mgr.assign_call_index(state) == 11


# ---------------------------------------------------------------------------
# find_state_by_turn_id
# ---------------------------------------------------------------------------


class TestFindStateByTurnId:
    def test_finds_cached_state(self):
        mgr = TurnManager()
        state = _make_state()
        mgr._turns["some-key"] = state

        found = mgr.find_state_by_turn_id(state.turn_id)
        assert found is state

    def test_returns_none_for_unknown_id(self):
        mgr = TurnManager()
        assert mgr.find_state_by_turn_id(uuid4()) is None

    def test_finds_among_multiple(self):
        mgr = TurnManager()
        states = [_make_state() for _ in range(5)]
        for i, s in enumerate(states):
            mgr._turns[f"key-{i}"] = s

        target = states[3]
        found = mgr.find_state_by_turn_id(target.turn_id)
        assert found is target


# ---------------------------------------------------------------------------
# mark_call_completed
# ---------------------------------------------------------------------------


class TestMarkCallCompleted:
    async def test_updates_last_completed_at(self):
        mgr = TurnManager()
        state = _make_state()
        assert state.last_completed_at is None

        await mgr.mark_call_completed(state)
        assert state.last_completed_at is not None
        assert isinstance(state.last_completed_at, datetime)

    async def test_subsequent_calls_update_timestamp(self):
        mgr = TurnManager()
        state = _make_state()

        await mgr.mark_call_completed(state)
        first = state.last_completed_at

        await asyncio.sleep(0.01)  # tiny delay so timestamps differ

        await mgr.mark_call_completed(state)
        assert state.last_completed_at > first


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


class TestClearCache:
    def test_clears_turns_and_locks(self):
        mgr = TurnManager()
        mgr._turns["a"] = _make_state()
        mgr._locks["a"] = asyncio.Lock()

        mgr.clear_cache()
        assert len(mgr._turns) == 0
        assert len(mgr._locks) == 0


class TestOwnerScopedGetter:
    def test_get_or_create_turn_manager_is_owner_scoped(self):
        first_owner = SimpleNamespace()
        second_owner = SimpleNamespace()

        first = get_or_create_turn_manager(first_owner)
        second = get_or_create_turn_manager(second_owner)

        assert first is not second
        assert first_owner.turn_manager is first
        assert second_owner.turn_manager is second

    def test_reset_turn_manager_replaces_owner_state(self):
        owner = SimpleNamespace()
        first = get_or_create_turn_manager(owner)
        first._turns["seed"] = _make_state()

        reset_turn_manager(owner)

        second = get_or_create_turn_manager(owner)
        assert first is not second
        assert second._turns == {}
        assert second._locks == {}

    def test_build_turn_manager_returns_fresh_instance(self):
        first = build_turn_manager()
        second = build_turn_manager()

        assert isinstance(first, TurnManager)
        assert isinstance(second, TurnManager)
        assert first is not second
