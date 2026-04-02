"""Tests for quran_mcp.lib.context.request.

Covers:
  - resolve_client_identity: 6-tier header hierarchy
    (openai-session → claude-trace → claude-cc → claude-ai → ip → fallback)
  - extract_provider_continuity_token: openai-session → baggage sentry-trace_id
"""

from __future__ import annotations

from types import SimpleNamespace

from quran_mcp.lib.context.request import (
    extract_relay_write_token,
    extract_provider_continuity_token,
    get_lifespan_context,
    resolve_client_identity,
)


# ---------------------------------------------------------------------------
# resolve_client_identity — with explicit headers (no HTTP context needed)
# ---------------------------------------------------------------------------


class TestResolveClientIdentity:
    def test_openai_session_highest_priority(self):
        headers = {
            "x-openai-session": "sess-abc123",
            "baggage": "sentry-trace_id=trace-xyz",
            "cf-connecting-ip": "1.2.3.4",
        }
        assert resolve_client_identity(headers=headers) == "openai-conv:sess-abc123"

    def test_claude_trace_from_baggage(self):
        headers = {"baggage": "sentry-trace_id=trace-xyz"}
        assert resolve_client_identity(headers=headers) == "claude-trace:trace-xyz"

    def test_claude_code_user_agent_with_cf_ip(self):
        headers = {
            "user-agent": "claude-code/1.0",
            "cf-connecting-ip": "10.0.0.1",
        }
        assert resolve_client_identity(headers=headers) == "claude-cc:10.0.0.1"

    def test_claude_ai_user_agent_with_cf_ip(self):
        headers = {
            "user-agent": "Claude-User",
            "cf-connecting-ip": "10.0.0.2",
        }
        assert resolve_client_identity(headers=headers) == "claude-ai:10.0.0.2"

    def test_generic_ip_fallback(self):
        headers = {
            "user-agent": "some-other-client/1.0",
            "cf-connecting-ip": "10.0.0.3",
        }
        assert resolve_client_identity(headers=headers) == "ip:10.0.0.3"

    def test_fallback_when_no_headers(self):
        assert resolve_client_identity(headers=None) == "unknown"

    def test_custom_fallback(self):
        assert resolve_client_identity(headers=None, fallback="anon") == "anon"

    def test_empty_headers_returns_fallback(self):
        assert resolve_client_identity(headers={}) == "unknown"

    def test_openai_session_whitespace_stripped(self):
        headers = {"x-openai-session": "  sess-abc  "}
        assert resolve_client_identity(headers=headers) == "openai-conv:sess-abc"

    def test_baggage_with_multiple_pairs(self):
        headers = {"baggage": "sentry-release=v1, sentry-trace_id=trace-123, other=val"}
        assert resolve_client_identity(headers=headers) == "claude-trace:trace-123"

    def test_baggage_without_sentry_trace_falls_through(self):
        headers = {
            "baggage": "sentry-release=v1",
            "cf-connecting-ip": "1.1.1.1",
        }
        assert resolve_client_identity(headers=headers) == "ip:1.1.1.1"

    def test_claude_code_without_cf_ip_falls_to_fallback(self):
        """claude-code UA without cf-connecting-ip can't produce an identity."""
        headers = {"user-agent": "claude-code/1.0"}
        assert resolve_client_identity(headers=headers) == "unknown"

    def test_claude_user_without_cf_ip_falls_to_fallback(self):
        headers = {"user-agent": "Claude-User"}
        assert resolve_client_identity(headers=headers) == "unknown"


# ---------------------------------------------------------------------------
# extract_provider_continuity_token
# ---------------------------------------------------------------------------


class TestExtractProviderContinuityToken:
    def test_openai_session(self):
        headers = {"x-openai-session": "conv-abc123"}
        assert extract_provider_continuity_token(headers) == "conv-abc123"

    def test_baggage_sentry_trace_id(self):
        headers = {"baggage": "sentry-trace_id=trace-456"}
        assert extract_provider_continuity_token(headers) == "trace-456"

    def test_openai_priority_over_baggage(self):
        headers = {
            "x-openai-session": "conv-abc",
            "baggage": "sentry-trace_id=trace-456",
        }
        assert extract_provider_continuity_token(headers) == "conv-abc"

    def test_none_headers(self):
        assert extract_provider_continuity_token(None) is None

    def test_empty_headers(self):
        assert extract_provider_continuity_token({}) is None

    def test_baggage_without_sentry_trace(self):
        headers = {"baggage": "other-key=value"}
        assert extract_provider_continuity_token(headers) is None

    def test_whitespace_stripped(self):
        headers = {"x-openai-session": "  conv-abc  "}
        assert extract_provider_continuity_token(headers) == "conv-abc"

    def test_empty_sentry_trace_skipped(self):
        headers = {"baggage": "sentry-trace_id="}
        assert extract_provider_continuity_token(headers) is None


class TestExtractRelayWriteToken:
    def test_x_relay_token_is_extracted(self):
        headers = {"x-relay-token": " relay-secret "}
        assert extract_relay_write_token(headers) == "relay-secret"

    def test_x_health_token_is_not_treated_as_relay_auth(self):
        headers = {"x-health-token": "health-secret"}
        assert extract_relay_write_token(headers) is None


def test_get_lifespan_context_reads_nested_request_context():
    lifespan_context = object()
    owner = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=lifespan_context))

    assert get_lifespan_context(owner) is lifespan_context
