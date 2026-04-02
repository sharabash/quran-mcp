"""Top-level package exports for quran_mcp."""

from __future__ import annotations

from quran_mcp.server import build_mcp, get_or_create_mcp, peek_mcp

__all__ = ["build_mcp", "get_or_create_mcp", "peek_mcp"]
