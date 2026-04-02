"""OpenAI provider with structured output support.

Uses the beta.chat.completions.parse() API for Pydantic model parsing.

SDK verification (interactive inspection, March 23, 2026):
- openai==2.29.0
- AsyncOpenAI.__init__(..., organization=..., project=..., base_url=..., timeout=...)
- client.beta.chat.completions.parse(..., response_format=type[BaseModel]) -> ParsedChatCompletion
- client.beta.chat.completions.parse accepts max_tokens / max_completion_tokens
"""

from __future__ import annotations

from typing import Type, TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

from .core import (
    ContentFilteredError,
    InvalidResponseError,
)
from .helpers import ProviderExceptions, translate_provider_errors, validate_prompt

T = TypeVar("T", bound=BaseModel)

# Provider name for exception messages
_PROVIDER = "openai"

_EXCEPTIONS = ProviderExceptions(
    auth=openai.AuthenticationError,
    rate_limit=openai.RateLimitError,
    connection=openai.APIConnectionError,
    timeout=openai.APITimeoutError,
    bad_request=openai.BadRequestError,
    api_base=openai.APIError,
)


class OpenAIProvider:
    """OpenAI provider with structured output support."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        organization: str | None = None,
        default_model: str = "gpt-4o",
    ):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key.
            base_url: Optional custom base URL (for proxies/self-hosted).
            organization: Optional organization ID.
            default_model: Default model to use. Defaults to gpt-4o.
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
        )
        self.default_model = default_model

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
        """Parse prompt into response_model via beta.chat.completions.parse."""
        validate_prompt(prompt)

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": model or self.default_model,
            "messages": messages,
            "response_format": response_model,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = await translate_provider_errors(
            _PROVIDER,
            self.client.beta.chat.completions.parse(**kwargs),
            timeout,
            _EXCEPTIONS,
        )

        if not response.choices:
            raise InvalidResponseError(
                _PROVIDER,
                response_model.__name__,
                raw_response="Empty choices array",
            )

        message = response.choices[0].message

        if message.refusal:
            raise ContentFilteredError(_PROVIDER, reason=message.refusal)

        if message.parsed is None:
            raw = message.content[:1000] if message.content else "No content"
            raise InvalidResponseError(
                _PROVIDER,
                response_model.__name__,
                raw_response=raw,
            )

        return message.parsed


__all__ = ["OpenAIProvider"]
