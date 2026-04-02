"""user_feedback - AI relays explicit user feedback about quran-mcp."""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from quran_mcp.mcp.tools.relay.helpers import (
    ensure_relay_write_authorized,
    get_pool,
    load_or_create_turn_state,
)
from quran_mcp.mcp.tools.relay.models import UserFeedbackResponse


async def _user_feedback_impl(
    ctx: Context,
    feedback_type: Annotated[
        str,
        Field(description=(
            "One of: feature_request, bug_report, content_gap, "
            "wrong_answer, praise, complaint, other. "
            "Unknown values accepted for forward compatibility."
        )),
    ],
    message: Annotated[
        str,
        Field(
            max_length=1000,
            description="Your paraphrase of the user's intent. Max 1000 characters.",
        ),
    ],
    user_quote: Annotated[
        str | None,
        Field(
            max_length=500,
            description=(
                "Verbatim user text, ONLY when the user explicitly asks to submit "
                "their own words as feedback. Never proactively extract or offer to "
                "capture user quotes. Max 500 characters."
            ),
        ),
    ] = None,
    severity: int = 3,
    tool_name: str | None = None,
) -> UserFeedbackResponse:
    """Insert a user_feedback row linked to the current turn."""
    severity = max(1, min(5, severity))

    if user_quote is not None:
        user_quote = user_quote[:500]

    ensure_relay_write_authorized(ctx)
    pool = get_pool(ctx)
    state = await load_or_create_turn_state(ctx, pool)

    feedback_id = await pool.fetchval(
        "INSERT INTO quran_mcp.user_feedback "
        "(turn_id, feedback_type, message, user_quote, severity, tool_name) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING feedback_id",
        state.turn_id,
        feedback_type,
        message,
        user_quote,
        severity,
        tool_name,
    )

    return UserFeedbackResponse(
        feedback_id=str(feedback_id),
        turn_id=str(state.turn_id),
        feedback_type=feedback_type,
        severity=severity,
    )


def register(mcp: FastMCP) -> None:
    """Register relay_user_feedback directly on the parent MCP server."""

    @mcp.tool(
        name="relay_user_feedback",
        title="Relay User Feedback",
        description=(
            "Only call when the user has consented to telemetry/feedback sharing. "
            "Relay explicit user feedback about quran-mcp's quality, features, or content. "
            "Call this only when the user explicitly provides feedback - for example, "
            "'I wish you had Ibn Ashur tafsir' or 'that translation was wrong'. "
            "Do not use this for your own internal quality observations - "
            "use relay_usage_gap instead."
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
    async def relay_user_feedback(
        ctx: Context,
        feedback_type: Annotated[
            str,
            Field(description=(
                "One of: feature_request, bug_report, content_gap, "
                "wrong_answer, praise, complaint, other. "
                "Unknown values accepted for forward compatibility."
            )),
        ],
        message: Annotated[
            str,
            Field(
                max_length=1000,
                description="Your paraphrase of the user's intent. Max 1000 characters.",
            ),
        ],
        user_quote: Annotated[
            str | None,
            Field(
                max_length=500,
                description=(
                    "Verbatim user text, ONLY when the user explicitly asks to submit "
                    "their own words as feedback. Never proactively extract or offer to "
                    "capture user quotes. Max 500 characters."
                ),
            ),
        ] = None,
        severity: int = 3,
        tool_name: str | None = None,
    ) -> UserFeedbackResponse:
        return await _user_feedback_impl(
            ctx,
            feedback_type,
            message,
            user_quote,
            severity,
            tool_name,
        )
