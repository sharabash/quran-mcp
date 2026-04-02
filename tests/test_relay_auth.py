"""Authorization boundary tests for relay write auth seam."""

from __future__ import annotations

from quran_mcp.lib.context.request import (
    evaluate_relay_write_authorization,
    extract_relay_write_token,
)


def test_preview_surface_does_not_require_token():
    error = evaluate_relay_write_authorization(
        headers={},
        active_tags={"ga", "preview"},
        relay_write_token="secret",
    )
    assert error is None


def test_full_surface_does_not_require_token():
    error = evaluate_relay_write_authorization(
        headers={},
        active_tags=None,
        relay_write_token="secret",
    )
    assert error is None


def test_ga_only_requires_configured_token():
    error = evaluate_relay_write_authorization(
        headers={},
        active_tags={"ga"},
        relay_write_token="",
    )
    assert error is not None
    assert "relay.write_token" in error


def test_ga_only_rejects_missing_or_invalid_token():
    error = evaluate_relay_write_authorization(
        headers={"x-relay-token": "wrong"},
        active_tags={"ga"},
        relay_write_token="secret",
    )
    assert error is not None
    assert "missing or invalid X-Relay-Token" in error


def test_ga_only_accepts_matching_relay_token():
    error = evaluate_relay_write_authorization(
        headers={"x-relay-token": "secret"},
        active_tags={"ga"},
        relay_write_token="secret",
    )
    assert error is None


def test_ga_only_rejects_health_header_fallback():
    error = evaluate_relay_write_authorization(
        headers={"x-health-token": "secret"},
        active_tags={"ga"},
        relay_write_token="secret",
    )
    assert error is not None
    assert "missing or invalid X-Relay-Token" in error


def test_extract_relay_write_token_prefers_x_relay_token():
    token = extract_relay_write_token(
        {"x-relay-token": "relay-token", "x-health-token": "health-token"}
    )
    assert token == "relay-token"


def test_extract_relay_write_token_ignores_health_token_only():
    token = extract_relay_write_token({"x-health-token": "health-token"})
    assert token is None


def test_extract_relay_write_token_strips_whitespace():
    token = extract_relay_write_token({"x-relay-token": "  secret  "})
    assert token == "secret"
