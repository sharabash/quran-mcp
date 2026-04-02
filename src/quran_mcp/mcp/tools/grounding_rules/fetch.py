"""Tool that returns grounding rules for AI assistants using quran-mcp.

Concise summary of citation requirements, attribution policy, and decision
rules for when to fetch vs use existing context. Complements the full
skill guide (fetch_skill_guide) with a focused grounding-only reference.
"""

from __future__ import annotations

from fastmcp import FastMCP

from quran_mcp.lib.assets import grounding_rules_markdown


def register(mcp: FastMCP) -> None:
    """Register the fetch_grounding_rules tool with the MCP server."""

    @mcp.tool(
        name="fetch_grounding_rules",
        title="Fetch Grounding Rules",
        description=(
            "Returns the grounding rules for quran-mcp: citation requirements, "
            "attribution policy, decision rules for when to fetch vs use existing "
            "context, and the applied reasoning disclaimer. Also returns a "
            "grounding_nonce — pass it to subsequent tool calls to save tokens. "
            "This tool MUST be called before any other quran-mcp tool in a "
            "conversation — other tools depend on the rules returned here. "
            "For the full operational guide including tool selection and workflows, "
            "use fetch_skill_guide instead."
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        version="0.1.1",
        tags={"ga"},
        output_schema=None,
    )
    def fetch_grounding_rules() -> str:
        return grounding_rules_markdown()
