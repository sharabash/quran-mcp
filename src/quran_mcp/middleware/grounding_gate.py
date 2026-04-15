"""Grounding gate middleware for field-based grounding enforcement.

Field-enforced tools receive the full ``GROUNDING_RULES.md`` payload in their
``grounding_rules`` response field until the caller explicitly acknowledges the
rules by calling ``fetch_grounding_rules``. A single ``GroundingWarning`` is
added alongside that payload when the response model exposes ``warnings``.

Acknowledgment is tracked per retained provider-aware identity for one hour.
Requests without a retained identity fall back to an unstable per-call key and
therefore continue receiving the grounding payload until a stronger identity is
available.
"""

from __future__ import annotations

import asyncio
import logging
import time
import secrets
import uuid
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from quran_mcp.lib.assets import grounding_rules_markdown
from quran_mcp.lib.presentation.warnings import GroundingWarning

logger = logging.getLogger(__name__)

# Tools that serve canonical Quran data — require grounding rules first
GATED_TOOLS: frozenset[str] = frozenset({
    "fetch_quran",
    "search_quran",
    "fetch_translation",
    "search_translation",
    "fetch_tafsir",
    "search_tafsir",
})

# Tools whose structured output should carry the field-based grounding tax
# until the client explicitly calls fetch_grounding_rules.
GROUNDING_FIELD_TOOLS: frozenset[str] = GATED_TOOLS | frozenset({
    "list_editions",
    "fetch_mushaf",
})

_MAX_TRACKED = 10_000
_RETAINED_IDENTITY_TTL_SECONDS = 3600
_NONCE_TTL_SECONDS = 3600
_RETAINED_IDENTITY_PREFIXES = (
    "openai-conv:",
    "claude-trace:",
    "claude-cc:",
    "claude-ai:",
    "ip:",
)

_GROUNDING_WARNING_DICT: dict[str, str] = GroundingWarning().model_dump()
_MAX_NONCES = 10_000

_NONCE_FOOTER_TEMPLATE = (
    "\n\n---\n"
    "GROUNDING_NONCE: {nonce}\n"
    "<grounding_nonce>{nonce}</grounding_nonce>\n\n"
    "Echo the nonce value (not the tags) as `grounding_nonce` to acknowledge "
    "the rules and save tokens on subsequent calls."
)


def _is_retained_identity(identity: str) -> bool:
    """Return True when the identity should retain grounding acknowledgment."""
    return identity.startswith(_RETAINED_IDENTITY_PREFIXES)


@lru_cache(maxsize=1)
def _grounding_rules_payload() -> str:
    """Load grounding rules lazily on first use instead of at import time."""
    return grounding_rules_markdown()


class GroundingGatekeeperMiddleware(Middleware):
    """Track explicit grounding acknowledgment for retained identities only."""

    def __init__(self, *, authority_a_enabled: bool = False) -> None:
        super().__init__()
        self._explicit_grounding: OrderedDict[str, float] = OrderedDict()
        # Nonces are now bound to identity: nonce -> (issued_at, identity)
        self._valid_nonces: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._authority_a_enabled = authority_a_enabled
        self._lock = asyncio.Lock()

    def _clean_expired_nonces(self) -> None:
        """Remove expired nonces from the store."""
        now = time.monotonic()
        while self._valid_nonces:
            oldest_key, (oldest_ts, _identity) = next(iter(self._valid_nonces.items()))
            if (now - oldest_ts) <= _NONCE_TTL_SECONDS:
                break
            self._valid_nonces.popitem(last=False)

    def _clean_expired_identities(self) -> None:
        """Remove expired identity acknowledgments from the store."""
        now = time.monotonic()
        while self._explicit_grounding:
            oldest_key, oldest_ts = next(iter(self._explicit_grounding.items()))
            if (now - oldest_ts) <= _RETAINED_IDENTITY_TTL_SECONDS:
                break
            self._explicit_grounding.popitem(last=False)

    @staticmethod
    def _mark(store: OrderedDict[str, float], identity: str) -> None:
        """Mark a retained identity as having acknowledged the rules."""
        if not _is_retained_identity(identity):
            return

        now = time.monotonic()
        # Proactive cleanup: evict expired entries at the head of the OrderedDict.
        while store:
            oldest_key, oldest_ts = next(iter(store.items()))
            if (now - oldest_ts) <= _RETAINED_IDENTITY_TTL_SECONDS:
                break
            store.popitem(last=False)

        store[identity] = now
        store.move_to_end(identity)
        while len(store) > _MAX_TRACKED:
            store.popitem(last=False)

    @staticmethod
    def _has(store: OrderedDict[str, float], identity: str) -> bool:
        """Return True when the retained identity is still acknowledged."""
        if not _is_retained_identity(identity):
            return False

        ts = store.get(identity)
        if ts is None:
            return False
        if (time.monotonic() - ts) > _RETAINED_IDENTITY_TTL_SECONDS:
            del store[identity]
            return False
        return True

    def _issue_nonce(self, identity: str) -> str:
        """Mint a cryptographically random nonce bound to the requesting identity."""
        self._clean_expired_nonces()
        nonce = f"gnd-{secrets.token_hex(16)}"
        self._valid_nonces[nonce] = (time.monotonic(), identity)
        self._valid_nonces.move_to_end(nonce)
        while len(self._valid_nonces) > _MAX_NONCES:
            self._valid_nonces.popitem(last=False)
        return nonce

    @staticmethod
    def _sanitize_nonce(raw: str) -> str:
        """Strip XML wrapper and whitespace from a nonce value.

        AIs may copy the XML tag verbatim as the parameter value, e.g.
        ``<grounding_nonce>gnd-abc123</grounding_nonce>``.
        """
        raw = raw.strip()
        if raw.startswith("<grounding_nonce>") and raw.endswith("</grounding_nonce>"):
            raw = raw[17:-18].strip()
        return raw

    def _validate_nonce(self, nonce: object, identity: str) -> bool:
        """Return True if the nonce is valid and bound to the given identity."""
        if not isinstance(nonce, str) or not nonce:
            return False
        entry = self._valid_nonces.get(nonce)
        if entry is None:
            return False
        issued_at, bound_identity = entry
        if (time.monotonic() - issued_at) > _NONCE_TTL_SECONDS:
            try:
                del self._valid_nonces[nonce]
            except KeyError:
                pass
            return False
        if bound_identity != identity:
            return False
        return True

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Inject grounding payloads unless a valid suppression authority exists."""
        tool_name = getattr(context.message, "name", "")

        from quran_mcp.lib.context.request import resolve_client_identity

        identity = resolve_client_identity(
            context,
            fallback=f"unknown:{uuid.uuid4().hex[:8]}",
        )

        if tool_name == "fetch_grounding_rules":
            result = await call_next(context)
            # Issue nonce (Authority B) and append to text content — only if
            # a text block exists (otherwise the client can't see the nonce)
            nonce_issued = False
            if result.content:
                for block in result.content:
                    if hasattr(block, "text"):
                        async with self._lock:
                            nonce = self._issue_nonce(identity)
                        block.text += _NONCE_FOOTER_TEMPLATE.format(nonce=nonce)
                        nonce_issued = True
                        break
            if nonce_issued:
                logger.info("Grounding gate: nonce issued (%s)", identity[:24])
            else:
                logger.warning(
                    "Grounding gate: no text block in fetch_grounding_rules — nonce not issued"
                )

            # Authority A: also mark identity if enabled
            if self._authority_a_enabled:
                async with self._lock:
                    self._mark(self._explicit_grounding, identity)

            return result

        result = await call_next(context)

        if tool_name not in GROUNDING_FIELD_TOOLS:
            return result

        suppressed = False

        # Authority A: identity-based retained ACK (if enabled)
        if self._authority_a_enabled:
            async with self._lock:
                if self._has(self._explicit_grounding, identity):
                    suppressed = True
                    logger.info(
                        "Grounding gate: suppressed via identity for %s (%s)",
                        tool_name,
                        identity[:24],
                    )

        # Authority B: nonce-based
        if not suppressed:
            args = getattr(context.message, "arguments", None) or {}
            nonce = args.get("grounding_nonce")
            if isinstance(nonce, str) and nonce:
                nonce = self._sanitize_nonce(nonce)
                async with self._lock:
                    nonce_valid = self._validate_nonce(nonce, identity)
                if nonce_valid:
                    suppressed = True
                    logger.info(
                        "Grounding gate: suppressed via nonce for %s (%s)",
                        tool_name,
                        identity[:24],
                    )
                else:
                    logger.info(
                        "Grounding gate: invalid nonce for %s (%s)",
                        tool_name,
                        identity[:24],
                    )
            else:
                logger.info(
                    "Grounding gate: no nonce for %s (%s)",
                    tool_name,
                    identity[:24],
                )

        if not suppressed:
            _set_grounding_field(result, _grounding_rules_payload())

        return result


def _set_grounding_field(result: Any, text: str) -> None:
    """Populate ``grounding_rules`` and add exactly one grounding warning."""
    sc = getattr(result, "structured_content", None)
    if sc is None or not isinstance(sc, dict):
        return

    sc["grounding_rules"] = text

    if "warnings" not in sc:
        return

    warnings = sc["warnings"]
    if warnings is None:
        sc["warnings"] = [_GROUNDING_WARNING_DICT.copy()]
        return

    if not isinstance(warnings, list):
        return

    has_grounding_warning = any(
        isinstance(item, dict) and item.get("type") == "grounding"
        for item in warnings
    )
    if not has_grounding_warning:
        warnings.append(_GROUNDING_WARNING_DICT.copy())
