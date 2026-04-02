"""Unit tests for mcp/tools/relay/user_feedback.py — input validation and DB insert."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError

from quran_mcp.mcp.tools.relay.user_feedback import _user_feedback_impl


@dataclass
class MockTurnState:
    turn_id: str
    trace_id: str


async def test_user_feedback_raises_when_pool_missing():
    ctx = AsyncMock()
    with patch("quran_mcp.mcp.tools.relay.user_feedback.ensure_relay_write_authorized"), \
         patch("quran_mcp.mcp.tools.relay.user_feedback.get_pool", side_effect=ToolError("[service_unavailable] Database not available")):
        with pytest.raises(ToolError, match="service_unavailable"):
            await _user_feedback_impl(ctx, feedback_type="praise", message="Great")


async def test_user_feedback_inserts_and_returns_response():
    ctx = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value="fb-uuid-123")

    with patch("quran_mcp.mcp.tools.relay.user_feedback.ensure_relay_write_authorized"), \
         patch("quran_mcp.mcp.tools.relay.user_feedback.get_pool", return_value=mock_pool), \
         patch("quran_mcp.mcp.tools.relay.user_feedback.load_or_create_turn_state", return_value=MockTurnState("turn-1", "trace-1")):
        result = await _user_feedback_impl(
            ctx, feedback_type="bug_report", message="Something broke", severity=4,
        )
    assert result.feedback_id == "fb-uuid-123"
    assert result.feedback_type == "bug_report"
    assert result.severity == 4


async def test_user_feedback_clamps_severity():
    ctx = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value="id")

    with patch("quran_mcp.mcp.tools.relay.user_feedback.ensure_relay_write_authorized"), \
         patch("quran_mcp.mcp.tools.relay.user_feedback.get_pool", return_value=mock_pool), \
         patch("quran_mcp.mcp.tools.relay.user_feedback.load_or_create_turn_state", return_value=MockTurnState("t", "t")):
        result = await _user_feedback_impl(
            ctx, feedback_type="praise", message="test", severity=99,
        )
    assert result.severity == 5
