"""Helpers for registering the reusable core MCP prompt surface.

The public server does not currently expose any first-party prompts, but we
keep the package-level registrar so server bootstrap stays symmetric across
tools, resources, and prompts as the surface evolves.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register_all_core_prompts(mcp: FastMCP) -> None:
    """Register the reusable first-party prompt surface on ``mcp``."""

    # Intentional no-op placeholder until the prompt surface exists.
    return None


__all__ = ["register_all_core_prompts"]
