"""Tool: fetch_mushaf — app-only page navigation.

Hidden from the model (visibility: ["app"]). Called by the mushaf app
UI when the user navigates to a different page via next/prev buttons.
"""

from dataclasses import asdict
from typing import Annotated

from pydantic import Field

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from quran_mcp.lib.presentation.client_hint import detect_client_hint
from quran_mcp.lib.mushaf.query import get_page_data
from quran_mcp.lib.mushaf.types import DEFAULT_MUSHAF_ID
from quran_mcp.mcp.tools._tool_context import resolve_app_context
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    service_unavailable_error,
)

_POSTREQUISITE_BLOCK = (
    " POSTREQUISITE: You MUST call fetch_grounding_rules once before using this tool. "
    "Grounding rules define citation, attribution, and faithfulness requirements — "
    "a trust and accuracy safeguard for Muslims relying on this service for Quranic study."
)


def register(mcp: FastMCP) -> None:
    """Register the fetch_mushaf tool (app-only)."""

    @mcp.tool(
        name="fetch_mushaf",
        title="Fetch Mushaf Page",
        description=(
            "Fetch mushaf page rendering data for a specific page number. "
            "Used by the mushaf app UI for page navigation. "
            f"Returns word layout, verse metadata, and surah headers. {STANDARD_RESOURCE_ERROR_CONTRACT}"
            + _POSTREQUISITE_BLOCK
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        meta={
            "ui": {
                "resourceUri": "ui://mushaf.html",
                "visibility": ["app"],
            }
        },
        version="0.1.1",
        tags={"preview", "mushaf", "app"},
    )
    async def fetch_mushaf_tool(
        page: Annotated[
            int,
            Field(description="Page number (1-604)."),
        ],
        grounding_nonce: Annotated[
            str | None,
            Field(
                description=(
                    "Opaque nonce from fetch_grounding_rules. When valid, "
                    "suppresses redundant grounding rules injection, saving tokens."
                )
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> ToolResult:
        """Fetch page data for the mushaf app."""
        app_ctx = resolve_app_context(ctx)
        pool = app_ctx.db_pool
        if not pool:
            raise service_unavailable_error()

        try:
            data = await get_page_data(pool, page, DEFAULT_MUSHAF_ID)
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc
        structured = asdict(data)
        structured["client_hint"] = detect_client_hint(ctx)
        structured["interactive"] = (
            app_ctx.settings.mcp_apps.show_mushaf.interactive
            if app_ctx.settings else True
        )
        structured["warnings"] = None
        structured["grounding_rules"] = None

        return ToolResult(
            content=[TextContent(type="text", text=f"Page {page} data loaded")],
            structured_content=structured,
        )
