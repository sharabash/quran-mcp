"""Relay runtime ownership helpers.

This package owns relay process/runtime coordination primitives that are
shared by lifespan startup/shutdown and the relay middleware.
"""

from quran_mcp.lib.relay.diagnostics import (
    HEADER_ALLOWLIST,
    write_turn_identity_diagnostic_event,
)
from quran_mcp.lib.relay.metadata import extract_result_metadata
from quran_mcp.lib.relay.runtime import (
    drain_pending,
    peek_relay_runtime_state,
    register_relay_middleware,
    reset_relay_runtime_state,
)
from quran_mcp.lib.relay.turns import (
    RelayTurnContext,
    activate_relay_turn,
    build_relay_turn_context,
    get_bound_relay_turn_state,
    resolve_relay_turn_state,
)

__all__ = [
    "HEADER_ALLOWLIST",
    "RelayTurnContext",
    "activate_relay_turn",
    "build_relay_turn_context",
    "drain_pending",
    "extract_result_metadata",
    "get_bound_relay_turn_state",
    "peek_relay_runtime_state",
    "register_relay_middleware",
    "resolve_relay_turn_state",
    "reset_relay_runtime_state",
    "write_turn_identity_diagnostic_event",
]
