"""Resource: document://skill_guide.md — usage guide for AI agents.

Exposes the complete SKILL.md so that any client connecting to the
MCP server can discover the usage guide via resources/list.
"""

from __future__ import annotations

from fastmcp import FastMCP

from quran_mcp.lib.assets import skill_guide_markdown


def register(mcp: FastMCP) -> None:
    """Register skill guide resource."""

    @mcp.resource(
        "document://skill_guide.md",
        name="SKILL.md",
        description=(
            "Complete usage guide for AI agents: grounding rules, tool selection, "
            "search strategies, edition awareness, tafsir summarization patterns, "
            "workflow recipes, response formatting, and anti-patterns."
        ),
        mime_type="text/markdown",
        version="0.1.1",
        tags={"ga"},
    )
    async def skill_guide() -> str:
        return skill_guide_markdown()
