"""Tests for quran_mcp.lib.llm.anthropic — error mapping and response parsing.

Mocks AsyncAnthropic.beta.messages.parse() to test the error → ProviderError
mapping and response shape handling without hitting the real API.

Covers:
  - SDK exceptions → correct ProviderError subclass
  - Timeout → NetworkError
  - Refusal stop_reason → ContentFilteredError
  - No parsed_output → InvalidResponseError
  - Successful parse → returns model instance
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import BaseModel

import anthropic
from quran_mcp.lib.llm import (
    AuthenticationError,
    ContentFilteredError,
    ContextWindowExceededError,
    InvalidResponseError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from quran_mcp.lib.llm.anthropic import AnthropicProvider


class Answer(BaseModel):
    text: str


def _make_provider() -> AnthropicProvider:
    provider = AnthropicProvider(api_key="test-key")
    provider.client = MagicMock()
    provider.client.beta.messages.parse = AsyncMock()
    return provider


def _fake_response(*, parsed_output=None, stop_reason="end_turn", content=None):
    resp = MagicMock()
    resp.parsed_output = parsed_output
    resp.stop_reason = stop_reason
    resp.content = content or []
    return resp


def _httpx_response(status: int = 400, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )


class TestAnthropicErrorMapping:
    async def test_timeout_raises_network_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = asyncio.TimeoutError()
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer, timeout=0.001)

    async def test_auth_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.AuthenticationError(
            "invalid key", response=_httpx_response(401), body=None,
        )
        with pytest.raises(AuthenticationError):
            await provider.complete("hello", Answer)

    async def test_rate_limit_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.RateLimitError(
            "rate limited", response=_httpx_response(429), body=None,
        )
        with pytest.raises(RateLimitError):
            await provider.complete("hello", Answer)

    async def test_rate_limit_extracts_retry_after(self):
        provider = _make_provider()
        resp = _httpx_response(429, headers={"retry-after": "30"})
        provider.client.beta.messages.parse.side_effect = anthropic.RateLimitError(
            "rate limited", response=resp, body=None,
        )
        with pytest.raises(RateLimitError) as exc_info:
            await provider.complete("hello", Answer)
        assert exc_info.value.retry_after == 30.0

    async def test_connection_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://api.anthropic.com"),
        )
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer)

    async def test_api_timeout_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.APITimeoutError(
            request=httpx.Request("POST", "https://api.anthropic.com"),
        )
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer)

    async def test_bad_request_context_window(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.BadRequestError(
            "prompt is too long: 100000 tokens",
            response=_httpx_response(400), body=None,
        )
        with pytest.raises(ContextWindowExceededError):
            await provider.complete("hello", Answer)

    async def test_bad_request_other(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.BadRequestError(
            "invalid parameter",
            response=_httpx_response(400), body=None,
        )
        with pytest.raises(ProviderError):
            await provider.complete("hello", Answer)

    async def test_generic_api_error(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.side_effect = anthropic.APIError(
            "internal",
            request=httpx.Request("POST", "https://api.anthropic.com"),
            body=None,
        )
        with pytest.raises(ProviderError):
            await provider.complete("hello", Answer)

    async def test_empty_prompt_raises_value_error(self):
        provider = _make_provider()
        with pytest.raises(ValueError):
            await provider.complete("", Answer)


class TestAnthropicResponseParsing:
    async def test_successful_parse(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.beta.messages.parse.return_value = _fake_response(
            parsed_output=answer,
        )
        result = await provider.complete("what is 6*7?", Answer)
        assert result.text == "42"

    async def test_max_tokens_forwards_to_sdk(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.beta.messages.parse.return_value = _fake_response(
            parsed_output=answer,
        )
        await provider.complete("what is 6*7?", Answer, max_tokens=77)
        _, kwargs = provider.client.beta.messages.parse.call_args
        assert kwargs["max_tokens"] == 77

    async def test_refusal_raises_content_filtered(self):
        provider = _make_provider()
        block = MagicMock()
        block.text = "I cannot answer that"
        provider.client.beta.messages.parse.return_value = _fake_response(
            stop_reason="refusal", content=[block],
        )
        with pytest.raises(ContentFilteredError) as exc_info:
            await provider.complete("hello", Answer)
        assert exc_info.value.reason == "I cannot answer that"

    async def test_no_parsed_output_raises_invalid_response(self):
        provider = _make_provider()
        provider.client.beta.messages.parse.return_value = _fake_response(
            parsed_output=None,
        )
        with pytest.raises(InvalidResponseError):
            await provider.complete("hello", Answer)
