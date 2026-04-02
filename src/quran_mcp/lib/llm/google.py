"""Google (Gemini) provider with structured output support.

Uses the google.genai SDK with response_schema for Pydantic model parsing.

SDK verification (interactive inspection, March 23, 2026):
- google-genai==1.68.0
- Client.__init__(..., api_key=..., vertexai=..., http_options=...)
- client.aio.models.generate_content(model=..., contents=..., config=...) -> GenerateContentResponse
- GenerateContentConfig(..., response_schema=type[BaseModel], response_mime_type="application/json")
- GenerateContentConfig accepts max_output_tokens for response token caps
- GenerateContentResponse.parsed attribute is present
- FinishReason: STOP, SAFETY, PROHIBITED_CONTENT, BLOCKLIST, etc.
"""

from __future__ import annotations

import asyncio
from typing import Type, TypeVar

from google.genai import Client
from google.genai.errors import APIError, ClientError, ServerError
from google.genai.types import FinishReason, GenerateContentConfig
from pydantic import BaseModel

from .core import (
    AuthenticationError,
    ContentFilteredError,
    ContextWindowExceededError,
    InvalidResponseError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from .helpers import extract_max_tokens_from_error, is_context_window_error, validate_prompt

T = TypeVar("T", bound=BaseModel)

# Provider name for exception messages
_PROVIDER = "google"

# FinishReason values that indicate content filtering
_CONTENT_FILTERED_REASONS = {
    FinishReason.SAFETY,
    FinishReason.PROHIBITED_CONTENT,
    FinishReason.BLOCKLIST,
    FinishReason.SPII,
    FinishReason.IMAGE_SAFETY,
    FinishReason.IMAGE_PROHIBITED_CONTENT,
}


class GoogleProvider:
    """Google (Gemini) provider with structured output support."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gemini-2.0-flash",
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ):
        """Initialize Google provider.

        Args:
            api_key: Google AI API key.
            default_model: Default model to use. Defaults to gemini-2.0-flash.
            max_retries: Max retries on rate limit errors. Defaults to 3.
            retry_base_delay: Base delay in seconds for exponential backoff. Defaults to 1.0.
        """
        self.client = Client(api_key=api_key)
        self.default_model = default_model
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

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
        """Parse prompt into response_model via generate_content with response_schema."""
        validate_prompt(prompt)

        config_kwargs: dict = {
            "response_schema": response_model,
            "response_mime_type": "application/json",
        }
        if system:
            config_kwargs["system_instruction"] = system
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        config = GenerateContentConfig(**config_kwargs)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model or self.default_model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=timeout,
                )
                break  # Success, exit retry loop
            except asyncio.TimeoutError as e:
                raise NetworkError(_PROVIDER, cause=e) from e
            except ClientError as e:
                # Google SDK uses 'code' attribute, not 'status'
                status_code = getattr(e, "code", None)
                error_str = str(e)

                if status_code in (401, 403) or "API_KEY" in error_str.upper():
                    raise AuthenticationError(_PROVIDER, cause=e) from e

                # Check for context window errors BEFORE rate limiting
                # (both may use RESOURCE_EXHAUSTED, but context window has specific patterns)
                if is_context_window_error(e):
                    max_tokens = extract_max_tokens_from_error(e)
                    raise ContextWindowExceededError(
                        _PROVIDER, max_tokens=max_tokens, cause=e
                    ) from e

                if status_code == 429 or "RESOURCE_EXHAUSTED" in error_str.upper():
                    last_error = e
                    if attempt < self.max_retries:
                        # Exponential backoff: 1s, 2s, 4s, ...
                        delay = self.retry_base_delay * (2**attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise RateLimitError(_PROVIDER, cause=e) from e

                raise ProviderError(str(e), _PROVIDER, cause=e) from e
            except ServerError as e:
                raise NetworkError(_PROVIDER, cause=e) from e
            except APIError as e:
                raise ProviderError(str(e), _PROVIDER, cause=e) from e
            except Exception as e:
                if "connect" in str(e).lower() or "timeout" in str(e).lower():
                    raise NetworkError(_PROVIDER, cause=e) from e
                raise ProviderError(f"Unexpected error: {e}", _PROVIDER, cause=e) from e
        else:
            # All retries exhausted (shouldn't reach here normally)
            if last_error:
                raise RateLimitError(_PROVIDER, cause=last_error) from last_error

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.finish_reason in _CONTENT_FILTERED_REASONS:
                reason = f"Content blocked: {candidate.finish_reason.name}"
                if candidate.finish_message:
                    reason = candidate.finish_message
                raise ContentFilteredError(_PROVIDER, reason=reason)

        if response.parsed is None:
            raw = "No parsed output"
            if response.candidates and response.candidates[0].content:
                parts = response.candidates[0].content.parts
                if parts:
                    texts = [p.text for p in parts if hasattr(p, "text") and p.text]
                    if texts:
                        raw = " ".join(texts)[:1000]
            raise InvalidResponseError(
                _PROVIDER,
                response_model.__name__,
                raw_response=raw,
            )

        return response.parsed


__all__ = ["GoogleProvider"]
