"""Shared HTTP context extraction for middleware and utilities.

Consolidates request identity resolution, HTTP header access, and
provider continuity token extraction used by rate_limit, grounding_gate,
relay, and client_hint modules.

Notes in this module reflect quran-mcp grounding smoke observations from
March 2026. They describe the best observed scope of certain headers in
our traces; they are not provider-guaranteed identity contracts.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
import logging
import re
import secrets
from typing import Any, cast

from fastmcp.server.middleware import MiddlewareContext

from quran_mcp.lib.context.types import AppContext

logger = logging.getLogger(__name__)

# Regex for W3C traceparent: version-traceid-parentid-traceflags
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")
_RELAY_WRITE_TOKEN_HEADERS = ("x-relay-token",)
_RELAY_TURN_ID_CTX: ContextVar[str | None] = ContextVar("relay_turn_id", default=None)


def get_http_headers() -> dict[str, str] | None:
    """Get HTTP headers from the current FastMCP request context.

    Returns None when called outside an HTTP request (e.g., STDIO transport)
    or if the dependency is unavailable.
    """
    try:
        from fastmcp.server.dependencies import get_http_headers as _get

        return _get(include_all=True)
    except Exception:
        return None


def extract_trace_id(headers: dict[str, str] | None) -> str | None:
    """Parse trace-id from W3C traceparent header.

    Returns the 32-hex-char trace-id, or None if header is missing/invalid/all-zeros.
    """
    if not headers:
        return None
    traceparent = headers.get("traceparent")
    if not traceparent:
        return None
    match = _TRACEPARENT_RE.match(traceparent.strip().lower())
    if not match:
        return None
    trace_id = match.group(1)
    if trace_id == "0" * 32:
        return None
    return trace_id


def extract_client_info(fastmcp_ctx: Any) -> dict[str, str] | None:
    """Extract clientInfo from the MCP initialize handshake."""
    try:
        client_params = fastmcp_ctx.session._client_params
        if client_params and client_params.clientInfo:
            client_info = client_params.clientInfo
            return {"name": client_info.name, "version": client_info.version}
    except AttributeError:
        # Intentional: clientInfo is optional in MCP handshake
        logger.debug("clientInfo not available on context (missing session or _client_params)")
    return None


def extract_provider_continuity_token(headers: dict[str, str] | None) -> str | None:
    """Extract the best available provider continuity token for this request.

    This token may be durable (e.g. OpenAI session) or narrow/trace-like
    (e.g. Claude baggage trace), depending on provider behavior.

    Checks (in order):
    1. ``x-openai-session`` (OpenAI/ChatGPT)
    2. ``baggage`` header's ``sentry-trace_id`` key (Claude/Anthropic)

    For ChatGPT traffic, ``x-openai-session`` was the strongest observed
    session/conversation surrogate in 0058 smoke testing.

    For Claude traffic, ``sentry-trace_id`` was only a narrow trace-like
    token in our traces, often scoped to a turn or burst rather than a
    true end-user conversation. The helper name is historical; callers
    should not assume the Claude branch returns a durable conversation ID.
    """
    token, _source = _extract_provider_continuity_token_detail(headers)
    return token


def extract_relay_write_token(headers: dict[str, str] | None) -> str | None:
    """Extract relay write token from accepted auth headers.

    Accepted header:
      - ``x-relay-token`` (dedicated relay-write credential)
    """
    if not headers:
        return None
    for header_name in _RELAY_WRITE_TOKEN_HEADERS:
        token = headers.get(header_name)
        if token:
            cleaned = token.strip()
            if cleaned:
                return cleaned
    return None


def evaluate_relay_write_authorization(
    *,
    headers: dict[str, str] | None,
    active_tags: set[str] | None,
    relay_write_token: str,
) -> str | None:
    """Return a relay-write authorization error message, or ``None`` if allowed.

    Policy:
    - preview/full surfaces are relay-authorized without token checks.
    - non-preview filtered surfaces require token auth.
    - relay writes require a dedicated relay token; HEALTH_TOKEN is not accepted.
    """
    if active_tags is None or "preview" in active_tags:
        return None

    configured = relay_write_token.strip()

    if not configured:
        return (
            "Relay write access denied — relay.write_token (RELAY_WRITE_TOKEN) is not configured."
        )

    provided = extract_relay_write_token(headers)
    if not provided or not secrets.compare_digest(provided, configured):
        return "Relay write access denied — missing or invalid X-Relay-Token."
    return None


def set_active_relay_turn_id(turn_id: str | None) -> Token[str | None]:
    """Set active relay turn id in request-local context."""
    return _RELAY_TURN_ID_CTX.set(turn_id)


def get_active_relay_turn_id() -> str | None:
    """Get active relay turn id from request-local context."""
    return _RELAY_TURN_ID_CTX.get()


def reset_active_relay_turn_id(token: Token[str | None]) -> None:
    """Reset active relay turn id using token from ``set_active_relay_turn_id``."""
    _RELAY_TURN_ID_CTX.reset(token)


def resolve_client_identity(
    context: MiddlewareContext | None = None,
    *,
    headers: dict[str, str] | None = None,
    session_id: str | None = None,
    fallback: str = "unknown",
) -> str:
    """Resolve the best available request identity key for grounding retention.

    Identity hierarchy (first match wins):
      1. ``openai-conv:<id>`` from ``x-openai-session``
      2. ``claude-trace:<id>`` from ``baggage`` ``sentry-trace_id``
      3. ``claude-cc:<ip>`` as a weak network fallback for Claude Code when
         ``cf-connecting-ip`` exists
      4. ``claude-ai:<ip>`` as a weak network fallback for Claude.ai when
         ``cf-connecting-ip`` exists
      5. ``ip:<ip>`` as a weak network fallback for other HTTP traffic with
         ``cf-connecting-ip``
      6. Caller-provided fallback when no retained identity can be derived

    Observed scope classes from the 0058 cross-client smoke work:
      - ``x-openai-session`` was the strongest observed ChatGPT
        session/conversation surrogate.
      - Claude trace-like headers such as ``baggage.sentry-trace_id``,
        ``traceparent``, and ``x-cloud-trace-context`` behaved like narrow
        turn/burst candidates in our traces. Only ``sentry-trace_id`` is
        actively consulted by the current resolver today.
      - ``cf-warp-tag-id`` was broad and stable across multiple Claude
        surfaces in the test environment, so it is documented as a future
        continuity hint only, never as a primary identity key.
      - ``cf-connecting-ip`` rotated frequently and remains only a weak
        network fallback.

    These notes are empirical and intentionally conservative. This helper
    does not implement a Claude bridge, continuity cache, or TTL policy
    change beyond the existing header precedence below.

    ``session_id`` is accepted for caller compatibility, but it is only used
    when the caller explicitly passes it via ``fallback``. It is intentionally
    not promoted into a retained provider-aware identity by default.
    """
    if context is not None and headers is None:
        headers = get_http_headers()

    token, source = _extract_provider_continuity_token_detail(headers)
    if token:
        if source == "openai":
            return f"openai-conv:{token}"
        if source == "claude":
            return f"claude-trace:{token}"

    user_agent = headers.get("user-agent", "") if headers else ""
    cf_ip = headers.get("cf-connecting-ip") if headers else None
    if cf_ip:
        if user_agent.startswith("claude-code/"):
            return f"claude-cc:{cf_ip}"
        if user_agent == "Claude-User":
            return f"claude-ai:{cf_ip}"
        return f"ip:{cf_ip}"

    return fallback


def get_lifespan_context(owner: Any) -> AppContext | None:
    """Return the current FastMCP lifespan context from a request-like owner."""
    request_context = getattr(owner, "request_context", None)
    if request_context is None:
        return None
    lifespan_context = getattr(request_context, "lifespan_context", None)
    if lifespan_context is None:
        return None
    return cast(AppContext, lifespan_context)


def _extract_provider_continuity_token_detail(
    headers: dict[str, str] | None,
) -> tuple[str | None, str | None]:
    """Return the best provider continuity token and its source label."""
    if not headers:
        return None, None

    openai_session = headers.get("x-openai-session")
    if openai_session:
        return openai_session.strip(), "openai"

    baggage = headers.get("baggage")
    if baggage:
        for pair in baggage.split(","):
            pair = pair.strip()
            if pair.startswith("sentry-trace_id="):
                val = pair.split("=", 1)[1].strip()
                if val:
                    return val, "claude"

    return None, None
