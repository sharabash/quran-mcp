"""Relay feedback tools registered directly on the parent MCP server.

All tools are prefixed with `relay_` when visible to clients.
The middleware skips logging these tools to avoid recursion.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import (  # noqa: F401, E402
    turn_start,
    usage_gap,
    turn_end,
    user_feedback,
)

__all__ = ["register"]


def register(parent_mcp: FastMCP) -> None:
    """Register relay feedback tools on the parent MCP server."""
    turn_start.register(parent_mcp)
    usage_gap.register(parent_mcp)
    turn_end.register(parent_mcp)
    user_feedback.register(parent_mcp)
