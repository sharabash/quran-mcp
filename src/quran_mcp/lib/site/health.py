"""Health check endpoint with recursive MCP self-test.

Connects to the server's own MCP endpoint as a client to validate
the full protocol path — the same path external hosts (Claude/ChatGPT) use.

Spec: codev/specs/0049-health-check-endpoint.md
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from quran_mcp.lib.config.settings import Settings

logger = logging.getLogger(__name__)
_HEALTH_STATE_ATTR = "_quran_mcp_health_runtime_state"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_KEY = "default"
_NONCE_LINE_RE = re.compile(r"GROUNDING_NONCE:\s*(gnd-[A-Za-z0-9]+)")
_NONCE_TAG_RE = re.compile(r"<grounding_nonce>\s*(gnd-[^<\s]+)\s*</grounding_nonce>")
_TRANSLATION_AYAH = "2:255"
_TRANSLATION_EDITION = "en-abdel-haleem"
_EDITION_TYPE = "tafsir"

# ---------------------------------------------------------------------------
# Cache and rate limiting — app-owned runtime state
# ---------------------------------------------------------------------------


@dataclass
class HealthRuntimeState:
    """Per-app runtime state for the health endpoint."""

    cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    last_request_time: float = 0.0


def build_health_runtime_state() -> HealthRuntimeState:
    """Create an isolated health runtime state container."""
    return HealthRuntimeState()


def get_or_create_health_runtime_state(owner: Any) -> HealthRuntimeState:
    """Return app-scoped health runtime state, creating it on first access."""
    state = getattr(owner, _HEALTH_STATE_ATTR, None)
    if state is None:
        state = build_health_runtime_state()
        setattr(owner, _HEALTH_STATE_ATTR, state)
    return state


def _get_cached(
    key: str,
    *,
    runtime_state: HealthRuntimeState,
) -> dict[str, Any] | None:
    entry = runtime_state.cache.get(key)
    if entry is None:
        return None
    expiry, result = entry
    if time.monotonic() > expiry:
        runtime_state.cache.pop(key, None)
        return None
    return result


def _set_cache(
    key: str,
    result: dict[str, Any],
    ttl: float,
    *,
    runtime_state: HealthRuntimeState,
) -> None:
    runtime_state.cache[key] = (time.monotonic() + ttl, result)


def clear_cache(*, runtime_state: HealthRuntimeState) -> None:
    """Clear the health check cache and rate limit state."""
    runtime_state.cache.clear()
    runtime_state.last_request_time = 0.0


# ---------------------------------------------------------------------------
# Endpoint rate limit — 1 request per RATE_LIMIT_SECONDS
# ---------------------------------------------------------------------------

RATE_LIMIT_SECONDS = 60.0  # 1 minute


# ---------------------------------------------------------------------------
# Core health check logic
# ---------------------------------------------------------------------------

def _extract_grounding_nonce(text: str) -> str | None:
    """Extract the issued grounding nonce from fetch_grounding_rules text."""
    line_match = _NONCE_LINE_RE.search(text)
    if line_match is not None:
        return line_match.group(1)

    tag_match = _NONCE_TAG_RE.search(text)
    if tag_match is not None:
        return tag_match.group(1)

    return None


def _first_text_block(result: Any) -> str:
    """Return the first text block from a CallToolResult, or an empty string."""
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    return ""


def _grounding_suppressed(structured_content: Any) -> bool:
    """Return True when grounding payloads were suppressed by a valid nonce."""
    if not isinstance(structured_content, dict):
        return False
    return structured_content.get("grounding_rules") is None and structured_content.get("warnings") is None


async def _call_tool(client: Any, tool_name: str, args: dict[str, Any], timeout: float) -> tuple[Any, int]:
    """Invoke a single tool and return its result plus elapsed time in ms."""
    t0 = time.monotonic()
    async with asyncio.timeout(timeout):
        result = await client.call_tool(tool_name, args)
    latency_ms = round((time.monotonic() - t0) * 1000)
    return result, latency_ms


def _fail_check(error: str, latency_ms: int | None = None) -> dict[str, Any]:
    """Build a standardized failing check payload."""
    payload: dict[str, Any] = {"status": "fail", "error": error}
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    return payload


def _unhealthy_response(checks: dict[str, Any]) -> dict[str, Any]:
    """Build a standardized unhealthy response with current timestamp."""
    return {
        "status": "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "checks": checks,
    }


async def _run_health_check(settings: Settings) -> dict[str, Any]:
    """Run a single grounded-session health probe against the live MCP server."""
    checks: dict[str, Any] = {}

    url = settings.health.url or f"http://localhost:{settings.server.port}/"
    token = settings.health.token.get_secret_value()
    tool_timeout = settings.health.tool_timeout_s

    # Prepare auth headers for rate limit exemption
    headers: dict[str, str] = {}
    if token:
        headers["X-Health-Token"] = token

    # Tier 0: Connect + list tools (connection timeout only covers handshake)
    try:
        transport = StreamableHttpTransport(url, headers=headers or None)
        client = Client(
            transport,
            client_info={"name": "quran-mcp-health", "version": "0.1.0"},  # type: ignore[arg-type]  # FastMCP Client accepts dict but typed as ClientInfo
        )
        async with client:
            grounding_result, grounding_latency = await _call_tool(
                client,
                "fetch_grounding_rules",
                {},
                tool_timeout,
            )
            nonce = _extract_grounding_nonce(_first_text_block(grounding_result))
            if nonce is None:
                checks["fetch_grounding_rules"] = _fail_check(
                    "grounding nonce missing from fetch_grounding_rules response text",
                    grounding_latency,
                )
                return _unhealthy_response(checks)
            checks["fetch_grounding_rules"] = {
                "status": "pass",
                "latency_ms": grounding_latency,
                "nonce_extracted": True,
            }

            editions_result, editions_latency = await _call_tool(
                client,
                "list_editions",
                {"edition_type": _EDITION_TYPE, "grounding_nonce": nonce},
                tool_timeout,
            )
            editions_payload = getattr(editions_result, "structured_content", None)
            if not isinstance(editions_payload, dict):
                checks["list_editions"] = _fail_check(
                    "list_editions returned no structured content",
                    editions_latency,
                )
                return _unhealthy_response(checks)
            checks["list_editions"] = {
                "status": "pass" if _grounding_suppressed(editions_payload) else "fail",
                "latency_ms": editions_latency,
                "count": editions_payload.get("count"),
                "grounding_suppressed": _grounding_suppressed(editions_payload),
            }
            if checks["list_editions"]["status"] == "fail":
                checks["list_editions"]["error"] = "grounding payload was not suppressed after nonce reuse"
                return _unhealthy_response(checks)

            translation_result, translation_latency = await _call_tool(
                client,
                "fetch_translation",
                {
                    "ayahs": _TRANSLATION_AYAH,
                    "editions": _TRANSLATION_EDITION,
                    "grounding_nonce": nonce,
                },
                tool_timeout,
            )
            translation_payload = getattr(translation_result, "structured_content", None)
            if not isinstance(translation_payload, dict):
                checks["fetch_translation"] = _fail_check(
                    "fetch_translation returned no structured content",
                    translation_latency,
                )
                return _unhealthy_response(checks)

            results = translation_payload.get("results", {})
            entries = results.get(_TRANSLATION_EDITION, []) if isinstance(results, dict) else []
            if not entries:
                checks["fetch_translation"] = _fail_check(
                    f"fetch_translation returned no entries for {_TRANSLATION_EDITION}",
                    translation_latency,
                )
                return _unhealthy_response(checks)

            checks["fetch_translation"] = {
                "status": "pass" if _grounding_suppressed(translation_payload) else "fail",
                "latency_ms": translation_latency,
                "ayah": entries[0].get("ayah"),
                "grounding_suppressed": _grounding_suppressed(translation_payload),
            }
            if checks["fetch_translation"]["status"] == "fail":
                checks["fetch_translation"]["error"] = "grounding payload was not suppressed after nonce reuse"
                return _unhealthy_response(checks)

    except Exception as exc:
        checks["overall"] = _fail_check(str(exc)[:200])
        return _unhealthy_response(checks)

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# ASGI handler
# ---------------------------------------------------------------------------

async def health_check_handler(
    scope: Scope,
    receive: Receive,
    send: Send,
    settings: Settings,
    *,
    runtime_state: HealthRuntimeState,
) -> None:
    """ASGI handler for GET /health."""
    # Serve cached responses before rate limiting so burst callers benefit from
    # the cache instead of getting throttled away from it.
    cached = _get_cached(_CACHE_KEY, runtime_state=runtime_state)
    if cached is not None:
        result = {**cached, "cached": True}
        status_code = 200 if result["status"] != "unhealthy" else 503
        response = JSONResponse(result, status_code=status_code)
        await response(scope, receive, send)
        return

    # Endpoint rate limit (1 call per 2 minutes)
    now = time.monotonic()
    elapsed = now - runtime_state.last_request_time
    if elapsed < RATE_LIMIT_SECONDS:
        retry_after = int(RATE_LIMIT_SECONDS - elapsed)
        response = JSONResponse(
            {"error": f"rate limited — retry in {retry_after}s", "retry_after_s": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)
        return
    runtime_state.last_request_time = now

    # Run health check with overall timeout
    try:
        async with asyncio.timeout(settings.health.max_timeout_s):
            result = await _run_health_check(settings)
    except TimeoutError:
        result = _unhealthy_response({"overall": {"status": "fail", "error": "overall timeout exceeded"}})
    except Exception as exc:
        logger.exception("Health check failed unexpectedly")
        result = _unhealthy_response({"overall": {"status": "fail", "error": str(exc)[:200]}})

    # Cache the result
    _set_cache(
        _CACHE_KEY,
        result,
        settings.health.tier0_cache_ttl_s,
        runtime_state=runtime_state,
    )

    status_code = 200 if result["status"] != "unhealthy" else 503
    response = JSONResponse(result, status_code=status_code)
    await response(scope, receive, send)
