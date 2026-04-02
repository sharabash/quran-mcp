from __future__ import annotations

from quran_mcp.lib.config.settings import Settings
from quran_mcp.middleware.stack import create_middleware_stack


def _settings(*, debug: bool, rate_limit: bool, relay: bool) -> Settings:
    return Settings(
        logging={
            "debug": debug,
            "log_level": "normal",
            "format": "pretty",
        },
        rate_limit={
            "enabled": rate_limit,
            "metered_tools": ["fetch_translation"],
            "bucket_size": 3,
            "refill_seconds": 7,
            "daily_per_client": 11,
            "daily_global": 22,
        },
        relay={
            "enabled": relay,
            "turn_gap_seconds": 12,
            "max_turn_minutes": 5,
        },
        health={"token": "health-secret"},
        grounding={"authority_a_enabled": True},
    )


def test_create_middleware_stack_base_shape() -> None:
    middleware = create_middleware_stack(
        _settings(debug=False, rate_limit=False, relay=False),
        relay_enabled=False,
    )

    assert [type(entry).__name__ for entry in middleware] == [
        "McpCallLoggerMiddleware",
        "ToolInstructionsMiddleware",
        "GroundingGatekeeperMiddleware",
    ]


def test_create_middleware_stack_includes_optional_layers_in_expected_order() -> None:
    middleware = create_middleware_stack(
        _settings(debug=True, rate_limit=True, relay=True),
        relay_enabled=True,
    )

    assert [type(entry).__name__ for entry in middleware] == [
        "RateLimitMiddleware",
        "RelayMiddleware",
        "McpCallLoggerMiddleware",
        "ToolInstructionsMiddleware",
        "HttpDebugMiddleware",
        "GroundingGatekeeperMiddleware",
    ]

    rate_limit = middleware[0]
    relay = middleware[1]
    grounding = middleware[-1]

    assert rate_limit._metered_tools == {"fetch_translation"}
    assert rate_limit._health_token == "health-secret"
    assert relay.turn_gap_seconds == 12
    assert relay.max_turn_seconds == 300
    assert grounding._authority_a_enabled is True
