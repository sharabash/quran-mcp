from __future__ import annotations

from contextlib import contextmanager
import logging
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

from quran_mcp.lib.config.profiles import resolve_active_tags
from quran_mcp.lib.config.settings import Settings, get_settings
from quran_mcp.lib.context.lifespan import build_lifespan_context_manager
from quran_mcp.lib.db.pool import create_pool
from quran_mcp.lib.sampling.handler import sampling_handler
from quran_mcp.lib.site import mount_public_routes
from quran_mcp.mcp.prompts import register_all_core_prompts
from quran_mcp.mcp.resources import register_all_core_resources
from quran_mcp.mcp.tools import register_all_core_tools
from quran_mcp.mcp.tools.relay import register as register_relay
from quran_mcp.middleware.stack import create_middleware_stack

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def relay_db_pool():
    """Real DB pool for observable persistence assertions."""
    settings = get_settings()
    db = settings.database
    if not db.password:
        pytest.skip("Database password not configured")

    pool = await create_pool(db, None)
    if pool is None:
        pytest.skip("Database not available")

    yield pool
    await pool.close()


@pytest_asyncio.fixture(loop_scope="session")
async def relay_mcp_server() -> FastMCP:
    """Build a relay-enabled server via the real composition path."""
    settings = get_settings()
    mcp = FastMCP(
        name="quran.ai MCP relay integration",
        version="0.1.0",
        middleware=create_middleware_stack(settings, relay_enabled=True),
        lifespan=build_lifespan_context_manager(settings=settings),
        sampling_handler=sampling_handler(),
        sampling_handler_behavior="fallback",
    )
    register_all_core_resources(mcp)
    register_all_core_prompts(mcp)
    register_all_core_tools(mcp)
    register_relay(mcp)

    active_tags = resolve_active_tags(settings)
    if active_tags is not None:
        mcp.enable(tags=active_tags, only=True)
        if "preview" not in active_tags:
            mcp.enable(
                names={
                    "relay_turn_start",
                    "relay_turn_end",
                    "relay_usage_gap",
                    "relay_user_feedback",
                }
            )

    # Keep HTTP composition in parity with the real server boot sequence.
    mount_public_routes(
        mcp=mcp,
        settings=settings,
        logger=logging.getLogger("tests.integration.relay"),
    )

    return mcp


def _build_trace_headers(*, trace_id: str, continuity_token: str, relay_token: str | None = None) -> dict[str, str]:
    headers = {
        "traceparent": f"00-{trace_id}-{uuid4().hex[:16]}-01",
        "x-openai-session": continuity_token,
    }
    if relay_token is not None:
        headers["x-relay-token"] = relay_token
    return headers


def _patch_headers(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]) -> None:
    monkeypatch.setattr(
        "quran_mcp.middleware.relay.get_http_headers",
        lambda: headers,
    )
    monkeypatch.setattr(
        "quran_mcp.mcp.tools.relay.helpers.get_http_headers",
        lambda: headers,
    )


@contextmanager
def _override_relay_guard_settings(
    *,
    active_tags: list[str] | None,
    relay_write_token: str,
    health_token: str = "",
):
    settings: Settings = get_settings()
    old_tags = settings.server.expose_tags
    old_token = settings.health.token
    old_relay_token = settings.relay.write_token
    old_relay_enabled = settings.relay.enabled
    try:
        settings.server.expose_tags = active_tags
        settings.relay.write_token = SecretStr(relay_write_token)
        settings.health.token = SecretStr(health_token)
        settings.relay.enabled = True
        yield
    finally:
        settings.server.expose_tags = old_tags
        settings.relay.write_token = old_relay_token
        settings.health.token = old_token
        settings.relay.enabled = old_relay_enabled


async def _cleanup_trace(pool: asyncpg.Pool, trace_id: str) -> None:
    rows = await pool.fetch(
        "SELECT turn_id FROM quran_mcp.turn WHERE trace_id = $1",
        trace_id,
    )
    if not rows:
        return

    turn_ids = [row["turn_id"] for row in rows]
    await pool.execute(
        "DELETE FROM quran_mcp.user_feedback WHERE turn_id = ANY($1::uuid[])",
        turn_ids,
    )
    await pool.execute(
        "DELETE FROM quran_mcp.identified_gap WHERE turn_id = ANY($1::uuid[])",
        turn_ids,
    )
    await pool.execute(
        "DELETE FROM quran_mcp.turn WHERE turn_id = ANY($1::uuid[])",
        turn_ids,
    )


async def _relay_tool_names(client: Client) -> set[str]:
    return {tool.name for tool in await client.list_tools() if tool.name.startswith("relay_")}


def _tool_payload(result) -> dict:
    payload = result.structured_content or {}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


async def test_relay_registered_tools_persist_turn_and_feedback(
    relay_mcp_server: FastMCP,
    relay_db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_id = uuid4().hex
    headers = _build_trace_headers(
        trace_id=trace_id,
        continuity_token=f"relay-int-{uuid4().hex[:10]}",
    )
    _patch_headers(monkeypatch, headers)
    with _override_relay_guard_settings(active_tags=["ga", "preview"], relay_write_token="", health_token="unused"):
        try:
            async with Client(relay_mcp_server) as client:
                assert await _relay_tool_names(client) == {
                    "relay_turn_start",
                    "relay_turn_end",
                    "relay_usage_gap",
                    "relay_user_feedback",
                }

                await client.call_tool(
                    "list_editions",
                    {"edition_type": "translation", "lang": "en"},
                )

                started = await client.call_tool(
                    "relay_turn_start",
                    {"interpreted_intent": "Validate relay tool registration behavior"},
                )
                started_payload = _tool_payload(started)
                turn_id = started_payload["turn_id"]
                assert started_payload["origin"] == "explicit"

                gap = await client.call_tool(
                    "relay_usage_gap",
                    {
                        "gap_type": "tool_limitation",
                        "description": "Integration probe for registered relay path",
                        "severity": 4,
                        "tool_name": "list_editions",
                    },
                )
                gap_payload = _tool_payload(gap)
                assert gap_payload["turn_id"] == turn_id
                assert gap_payload["severity"] == 4

                feedback = await client.call_tool(
                    "relay_user_feedback",
                    {
                        "feedback_type": "feature_request",
                        "message": "Need clearer relay consent indicators",
                        "severity": 3,
                        "tool_name": "relay_turn_start",
                    },
                )
                feedback_payload = _tool_payload(feedback)
                assert feedback_payload["turn_id"] == turn_id

                ended = await client.call_tool(
                    "relay_turn_end",
                    {
                        "post_turn_reflection": {
                            "found": "Relay writes persisted",
                            "missing": "None",
                            "quality": 5,
                        },
                        "overall_satisfaction": 5,
                        "improvement_suggestions": "Keep the registered relay contract explicit",
                    },
                )
                ended_payload = _tool_payload(ended)
                assert ended_payload["turn_id"] == turn_id
                assert ended_payload["status"] == "completed"

            turn_row = await relay_db_pool.fetchrow(
                "SELECT turn_id, provider_continuity_token, origin, interpreted_intent, "
                "ended_at, end_origin, overall_satisfaction "
                "FROM quran_mcp.turn WHERE trace_id = $1 "
                "ORDER BY started_at DESC LIMIT 1",
                trace_id,
            )
            assert turn_row is not None
            assert str(turn_row["turn_id"]) == turn_id
            assert turn_row["provider_continuity_token"] == headers["x-openai-session"]
            assert turn_row["origin"] == "explicit"
            assert turn_row["interpreted_intent"] == "Validate relay tool registration behavior"
            assert turn_row["ended_at"] is not None
            assert turn_row["end_origin"] == "explicit"
            assert turn_row["overall_satisfaction"] == 5

            activity_row = await relay_db_pool.fetchrow(
                "SELECT turn_provider_continuity_token FROM quran_mcp.turn_activity_log "
                "WHERE turn_id = $1 LIMIT 1",
                turn_row["turn_id"],
            )
            assert activity_row is not None
            assert activity_row["turn_provider_continuity_token"] == headers["x-openai-session"]

            tool_names = [
                row["tool_name"]
                for row in await relay_db_pool.fetch(
                    "SELECT tool_name FROM quran_mcp.tool_call WHERE turn_id = $1 ORDER BY call_index",
                    turn_row["turn_id"],
                )
            ]
            assert "list_editions" in tool_names
            assert not any(name.startswith("relay_") for name in tool_names)

            gap_count = await relay_db_pool.fetchval(
                "SELECT COUNT(*) FROM quran_mcp.identified_gap WHERE turn_id = $1",
                turn_row["turn_id"],
            )
            assert gap_count == 1

            feedback_count = await relay_db_pool.fetchval(
                "SELECT COUNT(*) FROM quran_mcp.user_feedback WHERE turn_id = $1",
                turn_row["turn_id"],
            )
            assert feedback_count == 1
        finally:
            await _cleanup_trace(relay_db_pool, trace_id)


async def test_relay_guard_blocks_unauthorized_write_through_registered_tools(
    relay_mcp_server: FastMCP,
    relay_db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_id = uuid4().hex
    headers = _build_trace_headers(
        trace_id=trace_id,
        continuity_token=f"relay-unauth-{uuid4().hex[:10]}",
    )
    _patch_headers(monkeypatch, headers)
    with _override_relay_guard_settings(active_tags=["ga"], relay_write_token="relay-secret"):
        try:
            async with Client(relay_mcp_server) as client:
                with pytest.raises(ToolError, match=r"^\[invalid_request\] "):
                    await client.call_tool(
                        "relay_turn_start",
                        {"interpreted_intent": "Unauthorized relay write"},
                    )

            turn_count = await relay_db_pool.fetchval(
                "SELECT COUNT(*) FROM quran_mcp.turn WHERE trace_id = $1",
                trace_id,
            )
            assert turn_count == 0
        finally:
            await _cleanup_trace(relay_db_pool, trace_id)


async def test_relay_guard_allows_authorized_write_through_registered_tools(
    relay_mcp_server: FastMCP,
    relay_db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_id = uuid4().hex
    headers = _build_trace_headers(
        trace_id=trace_id,
        continuity_token=f"relay-auth-{uuid4().hex[:10]}",
        relay_token="relay-secret",
    )
    _patch_headers(monkeypatch, headers)
    with _override_relay_guard_settings(active_tags=["ga"], relay_write_token="relay-secret"):
        try:
            async with Client(relay_mcp_server) as client:
                started = await client.call_tool(
                    "relay_turn_start",
                    {"interpreted_intent": "Authorized relay write"},
                )
                payload = _tool_payload(started)
                assert payload["origin"] == "explicit"

                await client.call_tool(
                    "relay_turn_end",
                    {"post_turn_reflection": {"quality": 4}, "overall_satisfaction": 4},
                )

            turn_row = await relay_db_pool.fetchrow(
                "SELECT turn_id, origin, ended_at, end_origin FROM quran_mcp.turn WHERE trace_id = $1",
                trace_id,
            )
            assert turn_row is not None
            assert str(turn_row["turn_id"]) == payload["turn_id"]
            assert turn_row["origin"] == "explicit"
            assert turn_row["ended_at"] is not None
            assert turn_row["end_origin"] == "explicit"

            relay_tool_calls = await relay_db_pool.fetchval(
                "SELECT COUNT(*) FROM quran_mcp.tool_call WHERE turn_id = $1 AND tool_name LIKE 'relay_%'",
                turn_row["turn_id"],
            )
            assert relay_tool_calls == 0
        finally:
            await _cleanup_trace(relay_db_pool, trace_id)
