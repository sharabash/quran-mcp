"""usage_gap - AI reports a retrieval or capability gap."""

from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from quran_mcp.mcp.tools.relay.helpers import (
    ensure_relay_write_authorized,
    get_pool,
    load_or_create_turn_state,
)
from quran_mcp.mcp.tools.relay.models import UsageGapResponse


async def _usage_gap_impl(
    ctx: Context,
    gap_type: Literal[
        "missing_content",
        "incomplete_result",
        "relevance_mismatch",
        "tool_limitation",
        "parameter_confusion",
        "missing_tooling",
        "other",
    ],
    description: Annotated[
        str,
        Field(
            max_length=1000,
            description="Description of the gap encountered. Max 1000 characters.",
        ),
    ],
    severity: int = 3,
    expected: Annotated[
        str | None,
        Field(
            max_length=500,
            description="What was expected. Max 500 characters.",
        ),
    ] = None,
    actual: Annotated[
        str | None,
        Field(
            max_length=500,
            description="What was actually returned. Max 500 characters.",
        ),
    ] = None,
    tool_name: str | None = None,
) -> UsageGapResponse:
    """Insert an identified_gap row linked to the current turn."""
    if not 1 <= severity <= 5:
        severity = max(1, min(5, severity))

    ensure_relay_write_authorized(ctx)
    pool = get_pool(ctx)
    state = await load_or_create_turn_state(ctx, pool)

    gap_id = await pool.fetchval(
        "INSERT INTO quran_mcp.identified_gap "
        "(turn_id, gap_type, description, expected, actual, severity, tool_name) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING gap_id",
        state.turn_id,
        gap_type,
        description,
        expected,
        actual,
        severity,
        tool_name,
    )

    return UsageGapResponse(
        gap_id=str(gap_id),
        turn_id=str(state.turn_id),
        gap_type=gap_type,
        severity=severity,
    )


def register(mcp: FastMCP) -> None:
    """Register relay_usage_gap directly on the parent MCP server."""

    @mcp.tool(
        name="relay_usage_gap",
        title="Relay AI Feedback: Usage Gap",
        description=(
            "Only call when the user has consented to telemetry/feedback sharing. "
            "Report a gap in retrieval quality, missing content, or capability limitation. "
            "Call this when a tool returned incomplete, irrelevant, or missing results "
            "compared to what the user needed. "
            "If the gap was that an entire tool or toolset was missing, select "
            "`missing_tooling` and describe the tool(s) you envision. "
            "Severity scale: 1=minor, 2=noticeable, 3=significant, 4=major, 5=critical."
        ),
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        version="0.1.1",
        tags={"ga"},
    )
    async def relay_usage_gap(
        ctx: Context,
        gap_type: Literal[
            "missing_content",
            "incomplete_result",
            "relevance_mismatch",
            "tool_limitation",
            "parameter_confusion",
            "missing_tooling",
            "other",
        ],
        description: Annotated[
            str,
            Field(
                max_length=1000,
                description="Description of the gap encountered. Max 1000 characters.",
            ),
        ],
        severity: int = 3,
        expected: Annotated[
            str | None,
            Field(
                max_length=500,
                description="What was expected. Max 500 characters.",
            ),
        ] = None,
        actual: Annotated[
            str | None,
            Field(
                max_length=500,
                description="What was actually returned. Max 500 characters.",
            ),
        ] = None,
        tool_name: str | None = None,
    ) -> UsageGapResponse:
        return await _usage_gap_impl(
            ctx,
            gap_type,
            description,
            severity,
            expected,
            actual,
            tool_name,
        )
