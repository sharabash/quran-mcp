"""Tool that returns the quran-mcp skill guide markdown.

Some MCP hosts are tool-only (or do not reliably surface resources/skills). This
tool provides an intuitive way to retrieve the canonical guidance directly.
"""

from __future__ import annotations

from fastmcp import FastMCP

from quran_mcp.lib.assets import skill_guide_markdown


def register(mcp: FastMCP) -> None:
    """Register the fetch_skill_guide tool with the MCP server."""

    @mcp.tool(
        name="fetch_skill_guide",
        title="Fetch Skill Guide",
        description=(
            "Return the complete quran-mcp skill guide as markdown (grounding rules, "
            "tool selection, search/fetch patterns, tafsir grounding discipline, and "
            "common workflows). Use to teach yourself the skills coupled with this MCP service "
            "— search/fetch retrieval patterns and tool usage examples."
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        version="0.1.1",
        tags={"ga"},
    )
    def fetch_skill_guide() -> str:
        return skill_guide_markdown()
