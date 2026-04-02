"""Rate limiting middleware — leaky bucket with provider-aware keying.

Protects against cost-amplification attacks on metered tools
(for example, any tool that triggers server-side inference or other costly work).

Architecture
~~~~~~~~~~~~
Three layers of protection:

  1. Leaky bucket (per-client, per-tool-tier)
     - Limits burst rate: ``bucket_size`` tokens, refills at ``1/refill_seconds``
     - Keyed on provider-aware HTTP identity first, then MCP session fallback

  2. Daily per-client cap
     - Hard ceiling on metered calls per client per UTC day

  3. Daily global cap
     - Hard ceiling across all clients — bounds total cost exposure

Identity Hierarchy
~~~~~~~~~~~~~~~~~~
  1. provider-aware HTTP identity via ``resolve_client_identity()``
  2. MCP session ID fallback for header-poor transports
  3. shared ``unknown`` fallback only when neither signal is available

Identity resolution caveat
~~~~~~~~~~~~~~~~~~~~~~~~~~
The current client-identity hierarchy is useful but not yet proven as a final,
fully trustworthy correlation strategy across all MCP hosts and transports.
Treat it as a practical heuristic that may need future tightening,
normalization, or replacement after more production validation.

Design spec: see bead quran-mcp-yal
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, NoReturn

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from mcp.types import CallToolRequestParams, CallToolResult

logger = logging.getLogger(__name__)

UTC = timezone.utc


@dataclass
class LeakyBucket:
    """Token bucket that refills at a fixed rate."""

    capacity: int
    refill_interval: float  # seconds per token
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = self._clock()

    def try_consume(self) -> tuple[bool, float]:
        """Try to consume one token.

        Returns:
            (allowed, retry_after_seconds)
            If allowed=True, retry_after is 0.
            If allowed=False, retry_after is seconds until next token.
        """
        now = self._clock()
        elapsed = now - self.last_refill
        refilled = elapsed / self.refill_interval
        self.tokens = min(self.capacity, self.tokens + refilled)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0

        deficit = 1.0 - self.tokens
        retry_after = deficit * self.refill_interval
        return False, retry_after


@dataclass
class ClientState:
    """Per-client rate limiting state."""

    bucket: LeakyBucket
    daily_count: int = 0
    daily_reset_date: str = ""  # ISO date string for reset tracking
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimitMiddleware(Middleware):
    """Leaky bucket rate limiter with per-client and global daily caps."""

    def __init__(
        self,
        *,
        metered_tools: set[str],
        bucket_size: int = 2,
        refill_seconds: float = 10.0,
        daily_per_client: int = 50,
        daily_global: int = 200,
        clock: Callable[[], float] = time.monotonic,
        health_token: str = "",
    ) -> None:
        super().__init__()
        self._metered_tools = metered_tools
        self._bucket_size = bucket_size
        self._refill_seconds = refill_seconds
        self._daily_per_client = daily_per_client
        self._daily_global = daily_global
        self._clock = clock
        self._health_token = health_token

        # State
        self._clients: dict[str, ClientState] = {}
        self._global_daily_count: int = 0
        self._global_daily_date: str = ""
        self._global_lock = asyncio.Lock()

    def _today(self) -> str:
        """Current UTC date as ISO string."""
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _reset_global_window(self, today: str) -> None:
        """Reset the global daily counter when the UTC day changes."""
        if self._global_daily_date != today:
            self._global_daily_count = 0
            self._global_daily_date = today

    def _reserve_global_slot(self, today: str, tool_name: str) -> None:
        """Reserve a global daily slot or raise if the cap is exhausted."""
        self._reset_global_window(today)
        if self._global_daily_count >= self._daily_global:
            logger.warning(
                "Rate limit: global daily cap reached (%d/%d)",
                self._global_daily_count, self._daily_global,
            )
            _reject(
                tool_name,
                f"Global daily limit reached ({self._daily_global} calls/day). "
                "Resets at midnight UTC.",
            )
        self._global_daily_count += 1

    async def _refund_global_slot(self) -> None:
        """Return a previously reserved global slot."""
        async with self._global_lock:
            self._global_daily_count -= 1

    @staticmethod
    def _reset_client_window(client: ClientState, today: str) -> None:
        """Reset a client's daily counter when the UTC day changes."""
        if client.daily_reset_date != today:
            client.daily_count = 0
            client.daily_reset_date = today

    def _enforce_client_daily_cap(self, client: ClientState, identity: str, tool_name: str) -> None:
        """Raise if the client's daily cap has been exhausted."""
        if client.daily_count >= self._daily_per_client:
            logger.warning(
                "Rate limit: client %s daily cap reached (%d/%d)",
                identity, client.daily_count, self._daily_per_client,
            )
            _reject(
                tool_name,
                f"Client daily limit reached ({self._daily_per_client} calls/day). "
                "Resets at midnight UTC.",
            )

    def _enforce_bucket(self, client: ClientState, identity: str, tool_name: str) -> None:
        """Consume a bucket token or raise with retry guidance."""
        allowed, retry_after = client.bucket.try_consume()
        if not allowed:
            logger.info(
                "Rate limit: client %s bucket empty for %s (retry in %.1fs)",
                identity, tool_name, retry_after,
            )
            _reject(
                tool_name,
                f"Rate limited — retry in {retry_after:.0f} seconds.",
            )

    def _get_or_create_client(self, identity: str) -> ClientState:
        """Get or create client state for an identity."""
        if identity not in self._clients:
            self._clients[identity] = ClientState(
                bucket=LeakyBucket(
                    capacity=self._bucket_size,
                    refill_interval=self._refill_seconds,
                    _clock=self._clock,
                ),
            )
        return self._clients[identity]

    @staticmethod
    def _resolve_identity(context: MiddlewareContext) -> str:
        """Extract client identity, keeping session fallback local to rate limiting.

        This identity strategy is intentionally isolated here because it is still
        heuristic. We rely on it today, but we have not yet validated that it is
        the best long-term correlation model across all clients/transports.
        """
        from quran_mcp.lib.context.request import resolve_client_identity

        identity = resolve_client_identity(context)
        if identity != "unknown":
            return identity

        fastmcp_ctx = context.fastmcp_context
        if fastmcp_ctx and fastmcp_ctx.session_id:
            return f"mcp-session:{fastmcp_ctx.session_id}"

        return identity

    def _is_health_request(self) -> bool:
        """Check if current request has a valid health token header."""
        from quran_mcp.lib.context.request import get_http_headers

        headers = get_http_headers()
        if not headers:
            return False
        token = headers.get("x-health-token", "")
        return hmac.compare_digest(token, self._health_token)

    def _should_skip_rate_limit(self) -> bool:
        """Return True when the current request bypasses rate limiting entirely."""
        return bool(self._health_token and self._is_health_request())

    def _is_metered_tool(self, tool_name: str) -> bool:
        """Return True when the tool is subject to rate limiting."""
        return tool_name in self._metered_tools

    async def _reserve_metered_call(self, today: str, tool_name: str) -> None:
        """Reserve a global slot before per-client policy checks."""
        async with self._global_lock:
            self._reserve_global_slot(today, tool_name)

    async def _apply_client_policy(self, identity: str, today: str, tool_name: str) -> ClientState:
        """Apply per-client window reset, daily cap, and bucket enforcement."""
        client = self._get_or_create_client(identity)
        async with client.lock:
            self._reset_client_window(client, today)
            self._enforce_client_daily_cap(client, identity, tool_name)
            self._enforce_bucket(client, identity, tool_name)
            client.daily_count += 1
        return client

    async def _refund_reserved_slot(self) -> None:
        """Refund the pre-reserved global slot after a local policy rejection."""
        await self._refund_global_slot()

    def _log_allowed_call(self, tool_name: str, identity: str, client: ClientState) -> None:
        """Log an allowed metered call after all policy checks succeed."""
        logger.debug(
            "Rate limit: %s allowed for %s (client daily: %d, global: %d)",
            tool_name, identity, client.daily_count, self._global_daily_count,
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext,
    ) -> CallToolResult:
        """Intercept metered tool calls and apply rate limiting."""
        if self._should_skip_rate_limit():
            return await call_next(context)

        tool_name = context.message.name

        if not self._is_metered_tool(tool_name):
            return await call_next(context)

        identity = self._resolve_identity(context)
        today = self._today()

        await self._reserve_metered_call(today, tool_name)

        try:
            client = await self._apply_client_policy(identity, today, tool_name)
        except BaseException:
            await self._refund_reserved_slot()
            raise

        self._log_allowed_call(tool_name, identity, client)

        return await call_next(context)


def _reject(tool_name: str, message: str) -> NoReturn:
    """Raise a ToolError for rate-limited requests.

    FastMCP catches ToolError and converts it to a proper MCP error response
    with isError=True.
    """
    raise ToolError(f"[Rate Limited] {tool_name}: {message}")
