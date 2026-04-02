"""Resource: document://grounding_rules.md — grounding rules for AI agents.

Exposes the complete GROUNDING_RULES.md so that any client connecting to the
MCP server can discover the grounding policy via resources/list.
"""

from __future__ import annotations

from fastmcp import FastMCP

from quran_mcp.lib.assets import grounding_rules_markdown


def register(mcp: FastMCP) -> None:
    """Register grounding rules resource."""

    @mcp.resource(
        "document://grounding_rules.md",
        name="GROUNDING_RULES.md",
        description=(
            "Grounding rules for AI agents: citation requirements, attribution "
            "policy, decision rules for when to fetch vs use existing context, "
            "and the applied reasoning disclaimer."
        ),
        mime_type="text/markdown",
        version="0.1.1",
        tags={"ga"},
    )
    async def grounding_rules() -> str:
        return grounding_rules_markdown()
