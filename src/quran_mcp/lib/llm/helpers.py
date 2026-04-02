"""Shared utilities for LLM providers."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, TypeVar

from .core import (
    AuthenticationError,
    ContextWindowExceededError,
    NetworkError,
    ProviderError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

def validate_prompt(prompt: str) -> None:
    """Reject empty or whitespace-only prompts."""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty or whitespace-only")


def truncate_response(text: str, max_len: int = 1000) -> str:
    """Truncate text for error messages."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# Patterns for detecting context window errors across providers
# Each provider has its own error message format
_CONTEXT_WINDOW_PATTERNS = (
    # OpenAI patterns
    re.compile(r"context_length_exceeded", re.IGNORECASE),
    re.compile(r"maximum context length", re.IGNORECASE),
    # Tightened: require "tokens" or "prompt" or "context" near "reduce the length"
    re.compile(r"reduce the length.{0,30}(tokens?|prompt|context|messages?)", re.IGNORECASE),
    re.compile(r"(tokens?|prompt|context|messages?).{0,30}reduce the length", re.IGNORECASE),
    re.compile(r"too many tokens", re.IGNORECASE),
    # Anthropic patterns
    re.compile(r"prompt is too long", re.IGNORECASE),
    re.compile(r"exceeds.*token limit", re.IGNORECASE),
    re.compile(r"too many tokens in", re.IGNORECASE),  # Added: Anthropic variant
    # Google patterns
    re.compile(r"RESOURCE_EXHAUSTED.*tokens", re.IGNORECASE),
    re.compile(r"input.*too long", re.IGNORECASE),
    # Generic patterns
    re.compile(r"context window", re.IGNORECASE),
    re.compile(r"token limit exceeded", re.IGNORECASE),
)


def is_context_window_error(error: Exception) -> bool:
    """Return ``True`` when an exception looks like a context window error."""
    error_str = str(error)
    return any(pattern.search(error_str) for pattern in _CONTEXT_WINDOW_PATTERNS)


def extract_max_tokens_from_error(error: Exception) -> int | None:
    """Extract a token limit from a context-window error, if present."""
    error_str = str(error)

    # Patterns that capture numbers with optional commas
    # Using [\d,]+ to match "128,000" or "4096"
    patterns = [
        # "maximum context length is 4,096" or "maximum context length is 4096"
        re.compile(r"maximum.*?([\d,]{3,})"),
        # "max_tokens: 4096" or "max tokens: 128,000"
        re.compile(r"max[_\s]tokens[:\s]+([\d,]+)", re.IGNORECASE),
        # "limit of 100,000 tokens" or "limit is 4096 tokens"
        re.compile(r"limit.*?([\d,]{3,})\s*tokens", re.IGNORECASE),
        # "context length is 4096" (without maximum)
        re.compile(r"context length.*?([\d,]{3,})", re.IGNORECASE),
    ]

    for pattern in patterns:
        match = pattern.search(error_str)
        if match:
            try:
                # Remove commas before converting to int
                number_str = match.group(1).replace(",", "")
                return int(number_str)
            except ValueError:
                logger.debug("Could not parse token limit from regex match: %s", match.group(0), exc_info=True)
                continue

    return None


@dataclass(frozen=True)
class ProviderExceptions:
    """Maps provider-specific SDK exception classes for error translation.

    Used by providers whose SDKs follow the OpenAI-style exception taxonomy
    (AuthenticationError, RateLimitError, APIConnectionError, etc.).
    Google uses a different taxonomy and is not covered.
    """

    auth: type[Exception]
    rate_limit: type[Exception]
    connection: type[Exception]
    timeout: type[Exception]
    bad_request: type[Exception]
    api_base: type[Exception]


async def translate_provider_errors(
    provider: str,
    coro: Awaitable[T],
    timeout: float,
    exc: ProviderExceptions,
) -> T:
    """Execute a provider API call, translating SDK exceptions to our hierarchy."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as e:
        raise NetworkError(provider, cause=e) from e
    except exc.auth as e:
        raise AuthenticationError(provider, cause=e) from e
    except exc.rate_limit as e:
        retry_after = None
        if hasattr(e, "response") and e.response is not None:
            retry_header = e.response.headers.get("retry-after")
            if retry_header:
                try:
                    retry_after = float(retry_header)
                except ValueError:
                    logger.debug("Non-numeric retry-after header: %s", retry_header)
        raise RateLimitError(provider, retry_after=retry_after, cause=e) from e
    except exc.connection as e:
        raise NetworkError(provider, cause=e) from e
    except exc.timeout as e:
        raise NetworkError(provider, cause=e) from e
    except exc.bad_request as e:
        if is_context_window_error(e):
            max_tokens_val = extract_max_tokens_from_error(e)
            raise ContextWindowExceededError(
                provider, max_tokens=max_tokens_val, cause=e
            ) from e
        raise ProviderError(str(e), provider, cause=e) from e
    except exc.api_base as e:
        raise ProviderError(str(e), provider, cause=e) from e
    except Exception as e:
        raise ProviderError(f"Unexpected error: {e}", provider, cause=e) from e


__all__ = [
    "ProviderExceptions",
    "translate_provider_errors",
    "validate_prompt",
    "truncate_response",
    "is_context_window_error",
    "extract_max_tokens_from_error",
]
