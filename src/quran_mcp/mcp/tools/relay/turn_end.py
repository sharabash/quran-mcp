"""turn_end - AI annotates current turn with post-turn reflection."""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from quran_mcp.mcp.tools.relay.helpers import (
    ensure_relay_write_authorized,
    get_pool,
    load_or_create_turn_state,
)
from quran_mcp.mcp.tools.relay.models import (
    ToolEffectiveness,
    TurnEndResponse,
    TurnReflection,
)
from quran_mcp.lib.relay.turns import get_relay_turn_manager


async def _turn_end_impl(
    ctx: Context,
    post_turn_reflection: TurnReflection,
    overall_satisfaction: int | None = None,
    tool_effectiveness: list[ToolEffectiveness] | None = None,
    improvement_suggestions: Annotated[
        str | None,
        Field(
            max_length=1000,
            description="Free-text suggestions for improvement. Max 1000 characters.",
        ),
    ] = None,
) -> TurnEndResponse:
    """Close the current turn with a post-turn reflection."""
    if overall_satisfaction is not None:
        overall_satisfaction = max(1, min(5, overall_satisfaction))

    ensure_relay_write_authorized(ctx)
    pool = get_pool(ctx)
    state = await load_or_create_turn_state(ctx, pool)

    mgr = get_relay_turn_manager(ctx)

    # Serialize typed models to dicts for JSONB storage
    reflection_dict = post_turn_reflection.model_dump()
    effectiveness_dict = (
        [e.model_dump() for e in tool_effectiveness]
        if tool_effectiveness
        else None
    )

    await mgr.complete_turn(
        pool,
        state,
        post_turn_reflection=reflection_dict,
        overall_satisfaction=overall_satisfaction,
        tool_effectiveness=effectiveness_dict,
        improvement_suggestions=improvement_suggestions,
    )

    return TurnEndResponse(
        turn_id=str(state.turn_id),
        status="completed",
        overall_satisfaction=overall_satisfaction,
    )


def register(mcp: FastMCP) -> None:
    """Register relay_turn_end directly on the parent MCP server."""

    @mcp.tool(
        name="relay_turn_end",
        title="Relay AI Feedback: End Turn",
        description=(
            "Only call when the user has consented to telemetry/feedback sharing. "
            "Report a reflection on the current turn after completing it. "
            "Call this after finishing a user request to record what was found, "
            "what was missing, and the overall quality of the interaction. "
            "Closes the current turn; coupled with relay_turn_start."
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
    async def relay_turn_end(
        ctx: Context,
        post_turn_reflection: TurnReflection,
        overall_satisfaction: int | None = None,
        tool_effectiveness: list[ToolEffectiveness] | None = None,
        improvement_suggestions: Annotated[
            str | None,
            Field(
                max_length=1000,
                description="Free-text suggestions for improvement. Max 1000 characters.",
            ),
        ] = None,
    ) -> TurnEndResponse:
        return await _turn_end_impl(
            ctx,
            post_turn_reflection,
            overall_satisfaction,
            tool_effectiveness,
            improvement_suggestions,
        )
