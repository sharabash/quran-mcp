"""Anthropic provider with structured output support.

Uses the beta.messages.parse() API for Pydantic model parsing.

SDK verification (interactive inspection, March 23, 2026):
- anthropic==0.86.0
- AsyncAnthropic.__init__(..., api_key=..., base_url=..., timeout=...)
- client.beta.messages.parse(..., output_format=type[BaseModel]) -> ParsedBetaMessage
- Parsed response attribute: parsed_output
- StopReason: 'end_turn', 'max_tokens', 'stop_sequence', 'tool_use', 'pause_turn', 'refusal'

Note: Structured output (output_format) requires Claude 4.5+ models.
Older models (Claude 4, 3.5, 3) do not support this feature.
"""

from __future__ import annotations

from typing import Type, TypeVar

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from .core import (
    ContentFilteredError,
    InvalidResponseError,
)
from .helpers import ProviderExceptions, translate_provider_errors, validate_prompt

T = TypeVar("T", bound=BaseModel)

# Provider name for exception messages
_PROVIDER = "anthropic"

_EXCEPTIONS = ProviderExceptions(
    auth=anthropic.AuthenticationError,
    rate_limit=anthropic.RateLimitError,
    connection=anthropic.APIConnectionError,
    timeout=anthropic.APITimeoutError,
    bad_request=anthropic.BadRequestError,
    api_base=anthropic.APIError,
)


class AnthropicProvider:
    """Anthropic provider with structured output support."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        default_model: str = "claude-sonnet-4-5-20250929",
        default_max_tokens: int = 4096,
    ):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key.
            base_url: Optional custom base URL (for proxies/self-hosted).
            default_model: Default model to use. Defaults to claude-sonnet-4-5-20250929.
            default_max_tokens: Default max tokens for responses. Defaults to 4096.
        """
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
        )
        self.default_model = default_model
        self.default_max_tokens = default_max_tokens

    async def complete(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float = 120.0,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Parse prompt into response_model via beta.messages.parse (requires Claude 4.5+)."""
        validate_prompt(prompt)

        messages: list[dict] = [{"role": "user", "content": prompt}]

        # max_tokens is required for Anthropic (not optional like OpenAI)
        kwargs: dict = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "output_format": response_model,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await translate_provider_errors(
            _PROVIDER,
            self.client.beta.messages.parse(**kwargs),
            timeout,
            _EXCEPTIONS,
        )

        if response.stop_reason == "refusal":
            reason = None
            if response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        reason = block.text
                        break
            raise ContentFilteredError(_PROVIDER, reason=reason)

        if response.parsed_output is None:
            raw = "No parsed output"
            if response.content:
                texts = []
                for block in response.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                if texts:
                    raw = " ".join(texts)[:1000]
            raise InvalidResponseError(
                _PROVIDER,
                response_model.__name__,
                raw_response=raw,
            )

        return response.parsed_output


__all__ = ["AnthropicProvider"]
