"""turn_start - promote current inferred turn to explicit with intent/expectations."""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from quran_mcp.mcp.tools.relay.helpers import (
    ensure_relay_write_authorized,
    get_pool,
    load_or_create_turn_state,
)
from quran_mcp.mcp.tools.relay.models import TurnExpectations, TurnStartResponse
from quran_mcp.lib.relay.turns import get_relay_turn_manager


async def _turn_start_impl(
    ctx: Context,
    interpreted_intent: Annotated[
        str | None,
        Field(
            max_length=500,
            description="What the user is trying to accomplish in this turn. Max 500 characters.",
        ),
    ] = None,
    pre_turn_expectations: TurnExpectations | None = None,
) -> TurnStartResponse:
    """Promote the current turn or create a new explicit one."""
    ensure_relay_write_authorized(ctx)
    pool = get_pool(ctx)
    state = await load_or_create_turn_state(ctx, pool)

    mgr = get_relay_turn_manager(ctx)

    # Serialize typed model to dict for JSONB storage
    expectations_dict = (
        pre_turn_expectations.model_dump() if pre_turn_expectations else None
    )

    await mgr.promote_turn(
        pool,
        state,
        interpreted_intent=interpreted_intent,
        pre_turn_expectations=expectations_dict,
    )

    return TurnStartResponse(
        turn_id=str(state.turn_id),
        origin="explicit",
        interpreted_intent=interpreted_intent,
    )


def register(mcp: FastMCP) -> None:
    """Register relay_turn_start directly on the parent MCP server."""

    @mcp.tool(
        name="relay_turn_start",
        title="Relay AI Feedback: Start Turn",
        description=(
            "Only call when the user has consented to telemetry/feedback sharing. "
            "Declare the start of a new intentional turn within the current session. "
            "Call this when beginning a distinct user request or task. "
            "If the current turn is already closed, a new explicit turn is created. "
            "If an open turn exists, it will be promoted from inferred to explicit "
            "with the provided intent and expectations."
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
    async def relay_turn_start(
        ctx: Context,
        interpreted_intent: Annotated[
            str | None,
            Field(
                max_length=500,
                description="What the user is trying to accomplish in this turn. Max 500 characters.",
            ),
        ] = None,
        pre_turn_expectations: TurnExpectations | None = None,
    ) -> TurnStartResponse:
        return await _turn_start_impl(
            ctx,
            interpreted_intent=interpreted_intent,
            pre_turn_expectations=pre_turn_expectations,
        )
