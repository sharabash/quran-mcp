"""Integration tests for DB modules: pool, runtime_config, turn_manager.

These hit a real PostgreSQL instance using the project's configured credentials.
The fixture uses the standard pool bootstrap path, so pending migrations are
applied before the tests run. Individual tests create and clean up their own
rows and do not mutate schema objects directly.

Covers:
  - runtime_config.py: load_runtime_config, save_runtime_config (upsert)
  - turn_manager.py: get_or_create_turn Path A (trace_id), Path B (context_id),
    assign_call_index, promote_turn, complete_turn, stale turn creation
  - pool.py: run_retention_cleanup
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.db.pool import _quote_schema_identifier, create_pool, run_retention_cleanup
from quran_mcp.lib.db.runtime_config import load_runtime_config, save_runtime_config
from quran_mcp.lib.db.turn_manager import TurnManager

# All tests in this module share the session-scoped event loop so the
# asyncpg pool (created once) stays on the same loop as every test function.
pytestmark = pytest.mark.asyncio(loop_scope="session")

UTC = timezone.utc
_SCHEMA = "quran_mcp"

# Unique prefix per test run to isolate test data
_RUN_ID = uuid4().hex[:8]


def _test_key(name: str) -> str:
    """Generate a test-unique key to avoid collisions."""
    return f"_test_{_RUN_ID}_{name}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pool():
    """Create a pool using real settings. Skip if DB unavailable."""
    settings = get_settings()
    db = settings.database

    if not db.password:
        pytest.skip("Database password not configured")

    p = await create_pool(db, None)
    if p is None:
        pytest.skip("Database not available")

    yield p

    # Cleanup: remove test rows created during this run
    async with p.acquire() as conn:
        await conn.execute(
            "DELETE FROM runtime_config WHERE scope LIKE $1",
            f"_test_{_RUN_ID}%",
        )
        await conn.execute(
            "DELETE FROM turn WHERE trace_id LIKE $1",
            f"_test_{_RUN_ID}%",
        )
    await p.close()


@pytest.fixture
def turn_mgr():
    """Fresh TurnManager for each test."""
    return TurnManager(max_cached=100)


# ---------------------------------------------------------------------------
# runtime_config.py
# ---------------------------------------------------------------------------


class TestSchemaIdentifierValidation:
    async def test_accepts_simple_schema_names(self):
        assert _quote_schema_identifier("quran_mcp") == '"quran_mcp"'

    async def test_rejects_unsafe_schema_names(self):
        with pytest.raises(ValueError):
            _quote_schema_identifier("quran_mcp; DROP SCHEMA public;")


class TestRuntimeConfig:
    async def test_save_and_load(self, pool):
        scope = _test_key("scope-1")
        await save_runtime_config(pool, scope, "key1", {"enabled": True}, updated_by="test")

        result = await load_runtime_config(pool, scope)
        assert "key1" in result
        # asyncpg returns JSONB as raw JSON string — parse to compare
        import json
        assert json.loads(result["key1"]) == {"enabled": True}

    async def test_upsert_overwrites(self, pool):
        scope = _test_key("scope-2")
        await save_runtime_config(pool, scope, "key2", "v1")
        await save_runtime_config(pool, scope, "key2", "v2")

        result = await load_runtime_config(pool, scope)
        import json
        assert json.loads(result["key2"]) == "v2"

    async def test_different_scopes_isolated(self, pool):
        scope_a = _test_key("scope-a")
        scope_b = _test_key("scope-b")
        await save_runtime_config(pool, scope_a, "shared-key", "a-value")
        await save_runtime_config(pool, scope_b, "shared-key", "b-value")

        a = await load_runtime_config(pool, scope_a)
        b = await load_runtime_config(pool, scope_b)
        import json
        assert json.loads(a["shared-key"]) == "a-value"
        assert json.loads(b["shared-key"]) == "b-value"

    async def test_empty_scope_returns_empty_dict(self, pool):
        result = await load_runtime_config(pool, _test_key("nonexistent"))
        assert result == {}


# ---------------------------------------------------------------------------
# turn_manager.py — Path A (trace_id)
# ---------------------------------------------------------------------------


class TestTurnManagerPathA:
    async def test_creates_new_turn(self, pool, turn_mgr):
        trace_id = _test_key("trace-a1")

        state = await turn_mgr.get_or_create_turn(
            pool,
            trace_id=trace_id,
            context_id="ctx-1",
            provider_continuity_token="conv-1",
            client_info={"name": "test"},
            max_turn_seconds=300,
        )

        assert state.turn_id is not None
        assert state.call_index == 0
        assert state.origin == "inferred"
        assert state.ended is False

        turn_row = await pool.fetchrow(
            "SELECT provider_continuity_token FROM quran_mcp.turn WHERE turn_id = $1",
            state.turn_id,
        )
        assert turn_row is not None
        assert turn_row["provider_continuity_token"] == "conv-1"

        activity_row = await pool.fetchrow(
            "SELECT turn_provider_continuity_token FROM quran_mcp.turn_activity_log "
            "WHERE turn_id = $1 LIMIT 1",
            state.turn_id,
        )
        assert activity_row is not None
        assert activity_row["turn_provider_continuity_token"] == "conv-1"

    async def test_reuses_existing_turn(self, pool, turn_mgr):
        trace_id = _test_key("trace-a2")

        state1 = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)
        state2 = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)

        assert state1.turn_id == state2.turn_id

    async def test_stale_turn_creates_new(self, pool, turn_mgr):
        trace_id = _test_key("trace-a3")

        state1 = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)

        # Artificially age the turn past max_turn_seconds
        state1.started_at = datetime.now(UTC) - timedelta(seconds=600)

        state2 = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)

        assert state2.turn_id != state1.turn_id


# ---------------------------------------------------------------------------
# turn_manager.py — Path B (context_id, no trace_id)
# ---------------------------------------------------------------------------


class TestTurnManagerPathB:
    async def test_creates_new_turn(self, pool, turn_mgr):
        state = await turn_mgr.get_or_create_turn(
            pool,
            context_id=_test_key("ctx-b1"),
            turn_gap_seconds=60,
        )

        assert state.turn_id is not None
        assert state.origin == "inferred"

    async def test_reuses_within_gap(self, pool, turn_mgr):
        ctx_id = _test_key("ctx-b2")

        state1 = await turn_mgr.get_or_create_turn(pool, context_id=ctx_id, turn_gap_seconds=60)
        state2 = await turn_mgr.get_or_create_turn(pool, context_id=ctx_id, turn_gap_seconds=60)

        assert state1.turn_id == state2.turn_id

    async def test_new_turn_after_gap(self, pool, turn_mgr):
        ctx_id = _test_key("ctx-b3")

        state1 = await turn_mgr.get_or_create_turn(pool, context_id=ctx_id, turn_gap_seconds=1)

        # Simulate completed call in the past
        state1.last_completed_at = datetime.now(UTC) - timedelta(seconds=5)

        state2 = await turn_mgr.get_or_create_turn(pool, context_id=ctx_id, turn_gap_seconds=1)

        assert state2.turn_id != state1.turn_id


# ---------------------------------------------------------------------------
# turn_manager.py — promote and complete
# ---------------------------------------------------------------------------


class TestTurnManagerPromoteAndComplete:
    async def test_promote_turn_to_explicit(self, pool, turn_mgr):
        trace_id = _test_key("trace-p1")
        state = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)
        assert state.origin == "inferred"

        await turn_mgr.promote_turn(
            pool, state,
            interpreted_intent="User wants tafsir of 2:255",
        )
        assert state.origin == "explicit"

        row = await pool.fetchrow(
            "SELECT origin, interpreted_intent FROM turn WHERE turn_id = $1",
            state.turn_id,
        )
        assert row["origin"] == "explicit"
        assert row["interpreted_intent"] == "User wants tafsir of 2:255"

    async def test_complete_turn(self, pool, turn_mgr):
        trace_id = _test_key("trace-c1")
        state = await turn_mgr.get_or_create_turn(pool, trace_id=trace_id, max_turn_seconds=300)

        await turn_mgr.complete_turn(
            pool, state,
            overall_satisfaction=4,
            improvement_suggestions="Faster response times",
        )
        assert state.ended is True

        row = await pool.fetchrow(
            "SELECT ended_at, end_origin, overall_satisfaction, improvement_suggestions "
            "FROM turn WHERE turn_id = $1",
            state.turn_id,
        )
        assert row["ended_at"] is not None
        assert row["end_origin"] == "explicit"
        assert row["overall_satisfaction"] == 4
        assert row["improvement_suggestions"] == "Faster response times"


# ---------------------------------------------------------------------------
# pool.py — retention cleanup
# ---------------------------------------------------------------------------


class TestRetentionCleanup:
    async def test_deletes_old_turns(self, pool):
        old_time = datetime.now(UTC) - timedelta(days=100)
        trace_id = _test_key("trace-old")
        turn_id = await pool.fetchval(
            "INSERT INTO turn (trace_id, origin, started_at) "
            "VALUES ($1, 'inferred', $2) RETURNING turn_id",
            trace_id,
            old_time,
        )

        await run_retention_cleanup(pool, _SCHEMA, retention_days=30)

        row = await pool.fetchrow("SELECT * FROM turn WHERE turn_id = $1", turn_id)
        assert row is None

    async def test_keeps_recent_turns(self, pool):
        recent_time = datetime.now(UTC) - timedelta(days=1)
        trace_id = _test_key("trace-recent")
        turn_id = await pool.fetchval(
            "INSERT INTO turn (trace_id, origin, started_at) "
            "VALUES ($1, 'inferred', $2) RETURNING turn_id",
            trace_id,
            recent_time,
        )

        await run_retention_cleanup(pool, _SCHEMA, retention_days=30)

        row = await pool.fetchrow("SELECT * FROM turn WHERE turn_id = $1", turn_id)
        assert row is not None
