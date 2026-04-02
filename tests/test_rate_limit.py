"""Tests for quran_mcp.middleware.rate_limit.

Covers:
  - LeakyBucket algorithm (pure, injectable clock)
  - RateLimitMiddleware: metered vs non-metered passthrough,
    per-client daily caps, global daily caps, leaky bucket throttling,
    day rollover resets, health-token bypass, global slot refund on
    per-client rejection
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext

from quran_mcp.middleware.rate_limit import (
    LeakyBucket,
    RateLimitMiddleware,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESOLVE_IDENTITY_PATCH = "quran_mcp.lib.context.request.resolve_client_identity"
_GET_HEADERS_PATCH = "quran_mcp.lib.context.request.get_http_headers"


@dataclass
class FakeMessage:
    name: str = ""
    arguments: dict[str, Any] | None = None


def _ctx(tool_name: str, *, session_id: str | None = None) -> MiddlewareContext:
    fastmcp_context = None
    if session_id is not None:
        fastmcp_context = SimpleNamespace(session_id=session_id)
    return MiddlewareContext(message=FakeMessage(name=tool_name), fastmcp_context=fastmcp_context)


async def _ok_next(context: MiddlewareContext):
    """Passthrough that returns a simple text result."""
    from fastmcp.tools import ToolResult

    return ToolResult(content="ok")


# ---------------------------------------------------------------------------
# LeakyBucket — pure algorithm
# ---------------------------------------------------------------------------


class TestLeakyBucket:
    def test_fresh_bucket_allows_up_to_capacity(self):
        clock = _FakeClock()
        bucket = LeakyBucket(capacity=3, refill_interval=10.0, _clock=clock)

        for _ in range(3):
            allowed, retry = bucket.try_consume()
            assert allowed is True
            assert retry == 0.0

        # 4th should fail
        allowed, retry = bucket.try_consume()
        assert allowed is False
        assert retry > 0

    def test_refill_after_interval(self):
        clock = _FakeClock()
        bucket = LeakyBucket(capacity=1, refill_interval=5.0, _clock=clock)

        allowed, _ = bucket.try_consume()
        assert allowed is True

        # Immediately: no tokens
        allowed, retry = bucket.try_consume()
        assert allowed is False

        # Advance past one refill interval
        clock.advance(5.1)
        allowed, _ = bucket.try_consume()
        assert allowed is True

    def test_partial_refill_not_enough(self):
        clock = _FakeClock()
        bucket = LeakyBucket(capacity=1, refill_interval=10.0, _clock=clock)

        bucket.try_consume()  # drain

        # Half-interval: not enough for a full token
        clock.advance(4.9)
        allowed, retry = bucket.try_consume()
        assert allowed is False
        assert retry > 0

    def test_tokens_never_exceed_capacity(self):
        clock = _FakeClock()
        bucket = LeakyBucket(capacity=2, refill_interval=1.0, _clock=clock)

        # Wait a very long time — tokens should cap at capacity
        clock.advance(1000)
        bucket.try_consume()  # refills internally

        assert bucket.tokens <= bucket.capacity

    def test_retry_after_is_sane(self):
        clock = _FakeClock()
        bucket = LeakyBucket(capacity=1, refill_interval=10.0, _clock=clock)

        bucket.try_consume()  # drain
        _, retry = bucket.try_consume()

        # retry_after should be at most one full interval
        assert 0 < retry <= 10.0


# ---------------------------------------------------------------------------
# RateLimitMiddleware — metered vs non-metered
# ---------------------------------------------------------------------------


class TestRateLimitPassthrough:
    async def test_non_metered_tool_passes_through(self):
        mw = _make_mw(metered={"summarize_tafsir"})
        result = await mw.on_call_tool(_ctx("fetch_quran"), _ok_next)

        assert result.content[0].text == "ok"

    async def test_metered_tool_allowed_when_under_limits(self):
        mw = _make_mw(metered={"summarize_tafsir"})

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            result = await mw.on_call_tool(_ctx("summarize_tafsir"), _ok_next)

        assert result.content[0].text == "ok"


# ---------------------------------------------------------------------------
# Identity resolution boundary behavior
# ---------------------------------------------------------------------------


class TestIdentityResolutionBoundary:
    async def test_distinct_resolved_identities_have_independent_client_caps(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=1)

        with patch(_RESOLVE_IDENTITY_PATCH, side_effect=["client-1", "client-2"]):
            first = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            second = await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        assert first.content[0].text == "ok"
        assert second.content[0].text == "ok"

    async def test_unknown_identity_falls_back_to_session_id(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=1)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="unknown"):
            first = await mw.on_call_tool(_ctx("tool_a", session_id="session-1"), _ok_next)
            second = await mw.on_call_tool(_ctx("tool_a", session_id="session-2"), _ok_next)

        assert first.content[0].text == "ok"
        assert second.content[0].text == "ok"

    async def test_unknown_identity_without_session_uses_shared_fallback(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=1)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="unknown"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Client daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)


# ---------------------------------------------------------------------------
# Per-client daily cap
# ---------------------------------------------------------------------------


class TestPerClientDailyCap:
    async def test_rejects_after_per_client_daily_cap(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=2)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Client daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

    async def test_different_clients_have_independent_caps(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=1)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-2"):
            # Second client should still be allowed
            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"


# ---------------------------------------------------------------------------
# Global daily cap
# ---------------------------------------------------------------------------


class TestGlobalDailyCap:
    async def test_rejects_after_global_daily_cap(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=100, daily_global=2)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Global daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

    async def test_global_cap_spans_clients(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=100, daily_global=2)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-2"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-3"):
            with pytest.raises(ToolError, match="Global daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)


# ---------------------------------------------------------------------------
# Global slot refund on per-client rejection
# ---------------------------------------------------------------------------


class TestGlobalSlotRefund:
    async def test_global_count_refunded_on_per_client_rejection(self):
        """When per-client cap rejects, the pre-reserved global slot must be returned."""
        mw = _make_mw(
            metered={"tool_a"},
            daily_per_client=1,
            daily_global=2,
            bucket_size=100,
        )

        # Client-1 exhausts its per-client cap
        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Client daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        # Global count should be 1, not 2 — the rejected call's slot was refunded.
        # Verify by allowing client-2 to use the remaining global slot.
        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-2"):
            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"

    async def test_global_count_refunded_on_bucket_rejection(self):
        """When leaky bucket rejects, the pre-reserved global slot must be returned."""
        mw = _make_mw(
            metered={"tool_a"},
            daily_per_client=100,
            daily_global=2,
            bucket_size=1,
            refill_seconds=9999,  # effectively never refills
        )

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)  # drains bucket

            with pytest.raises(ToolError, match="Rate limited"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        # Global slot refunded — client-2 should succeed
        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-2"):
            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"


# ---------------------------------------------------------------------------
# Leaky bucket integration with middleware
# ---------------------------------------------------------------------------


class TestBucketThrottling:
    async def test_bucket_rejects_burst_beyond_capacity(self):
        mw = _make_mw(
            metered={"tool_a"},
            bucket_size=2,
            refill_seconds=9999,
        )

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Rate limited"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)


# ---------------------------------------------------------------------------
# Health token bypass
# ---------------------------------------------------------------------------


class TestHealthTokenBypass:
    async def test_health_token_bypasses_rate_limit(self):
        mw = _make_mw(
            metered={"tool_a"},
            daily_per_client=1,
            daily_global=1,
            health_token="secret-token",
        )

        # Exhaust limits
        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"), patch(
            _GET_HEADERS_PATCH,
            return_value={},
        ):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        # Health request bypasses entirely
        with patch(
            _GET_HEADERS_PATCH,
            return_value={"x-health-token": "secret-token"},
        ):
            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"

    async def test_invalid_health_header_does_not_bypass_limits(self):
        mw = _make_mw(
            metered={"tool_a"},
            daily_per_client=1,
            health_token="secret-token",
        )

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"), patch(
            _GET_HEADERS_PATCH,
            return_value={},
        ):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"), patch(
            _GET_HEADERS_PATCH,
            return_value={"x-health-token": "wrong-token"},
        ):
            with pytest.raises(ToolError, match="Client daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)


# ---------------------------------------------------------------------------
# Day rollover resets
# ---------------------------------------------------------------------------


class TestDayRollover:
    async def test_per_client_cap_resets_on_new_day(self):
        mw = _make_mw(metered={"tool_a"}, daily_per_client=1)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Client daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            # Simulate day change
            mw._clients["client-1"].daily_reset_date = "1999-01-01"

            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"

    async def test_global_cap_resets_on_new_day(self):
        mw = _make_mw(metered={"tool_a"}, daily_global=1)

        with patch(_RESOLVE_IDENTITY_PATCH, return_value="client-1"):
            await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            with pytest.raises(ToolError, match="Global daily limit"):
                await mw.on_call_tool(_ctx("tool_a"), _ok_next)

            # Simulate day change
            mw._global_daily_date = "1999-01-01"

            result = await mw.on_call_tool(_ctx("tool_a"), _ok_next)
            assert result.content[0].text == "ok"


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


class _FakeClock:
    """Deterministic clock for LeakyBucket tests."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float):
        self._now += seconds


def _make_mw(
    *,
    metered: set[str],
    bucket_size: int = 10,
    refill_seconds: float = 1.0,
    daily_per_client: int = 100,
    daily_global: int = 500,
    health_token: str = "",
) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        metered_tools=metered,
        bucket_size=bucket_size,
        refill_seconds=refill_seconds,
        daily_per_client=daily_per_client,
        daily_global=daily_global,
        health_token=health_token,
    )
