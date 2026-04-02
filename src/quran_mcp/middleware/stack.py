"""Shared FastMCP middleware stack construction."""

from __future__ import annotations

from quran_mcp.middleware.grounding_gate import GroundingGatekeeperMiddleware
from quran_mcp.middleware.http_debug import HttpDebugMiddleware
from quran_mcp.middleware.mcp_call_logger import McpCallLoggerMiddleware
from quran_mcp.middleware.rate_limit import RateLimitMiddleware
from quran_mcp.middleware.relay import RelayMiddleware
from quran_mcp.middleware.tool_instructions import ToolInstructionsMiddleware

from fastmcp.server.middleware import Middleware

from quran_mcp.lib.config.settings import Settings


def create_middleware_stack(
    settings: Settings,
    *,
    relay_enabled: bool,
) -> list[Middleware]:
    """Create the standard middleware stack for core and sibling servers."""

    middleware: list[Middleware] = [
        McpCallLoggerMiddleware(
            verbosity=settings.logging.log_level,
            fmt=settings.logging.format,
        ),
        ToolInstructionsMiddleware(),
    ]
    if settings.logging.debug:
        middleware.append(HttpDebugMiddleware())
    if relay_enabled:
        middleware.insert(
            0,
            RelayMiddleware(
                turn_gap_seconds=settings.relay.turn_gap_seconds,
                max_turn_seconds=settings.relay.max_turn_minutes * 60,
            ),
        )
    if settings.rate_limit.enabled:
        middleware.insert(
            0,
            RateLimitMiddleware(
                metered_tools=set(settings.rate_limit.metered_tools),
                bucket_size=settings.rate_limit.bucket_size,
                refill_seconds=settings.rate_limit.refill_seconds,
                daily_per_client=settings.rate_limit.daily_per_client,
                daily_global=settings.rate_limit.daily_global,
                health_token=settings.health.token.get_secret_value(),
            ),
        )
    # Keep grounding innermost by appending it here. FastMCP builds the chain
    # in reverse order, so the last middleware in this list runs closest to the
    # tool/resource implementation. That is what we want for grounding because
    # it mutates the finished tool result after the handler runs, and then
    # outer middleware (instructions/logging/etc.) can observe the grounded
    # payload that will actually be returned.
    middleware.append(
        GroundingGatekeeperMiddleware(
            authority_a_enabled=settings.grounding.authority_a_enabled,
        )
    )
    return middleware
