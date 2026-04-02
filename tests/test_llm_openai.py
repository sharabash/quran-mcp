"""Tests for quran_mcp.lib.llm.openai — error mapping and response parsing.

Mocks AsyncOpenAI.beta.chat.completions.parse() to test error → ProviderError
mapping and response shape handling.

Covers:
  - SDK exceptions → correct ProviderError subclass
  - Empty choices → InvalidResponseError
  - Refusal → ContentFilteredError
  - No parsed content → InvalidResponseError
  - Successful parse → returns model instance
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import BaseModel

import openai
from quran_mcp.lib.llm import (
    AuthenticationError,
    ContentFilteredError,
    ContextWindowExceededError,
    InvalidResponseError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from quran_mcp.lib.llm.openai import OpenAIProvider


class Answer(BaseModel):
    text: str


def _make_provider() -> OpenAIProvider:
    provider = OpenAIProvider(api_key="test-key")
    provider.client = MagicMock()
    provider.client.beta.chat.completions.parse = AsyncMock()
    return provider


def _httpx_response(status: int = 400, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )


def _fake_response(*, parsed=None, refusal=None, content="raw", choices=True):
    msg = MagicMock()
    msg.parsed = parsed
    msg.refusal = refusal
    msg.content = content

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice] if choices else []
    return resp


class TestOpenAIErrorMapping:
    async def test_timeout_raises_network_error(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = asyncio.TimeoutError()
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer, timeout=0.001)

    async def test_auth_error(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.AuthenticationError(
            "invalid key", response=_httpx_response(401), body=None,
        )
        with pytest.raises(AuthenticationError):
            await provider.complete("hello", Answer)

    async def test_rate_limit_error(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.RateLimitError(
            "rate limited", response=_httpx_response(429), body=None,
        )
        with pytest.raises(RateLimitError):
            await provider.complete("hello", Answer)

    async def test_connection_error(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com"),
        )
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer)

    async def test_api_timeout_error(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.APITimeoutError(
            request=httpx.Request("POST", "https://api.openai.com"),
        )
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer)

    async def test_bad_request_context_window(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.BadRequestError(
            "maximum context length is 4096 tokens",
            response=_httpx_response(400), body=None,
        )
        with pytest.raises(ContextWindowExceededError) as exc_info:
            await provider.complete("hello", Answer)
        assert exc_info.value.max_tokens == 4096

    async def test_bad_request_other(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.side_effect = openai.BadRequestError(
            "invalid parameter",
            response=_httpx_response(400), body=None,
        )
        with pytest.raises(ProviderError):
            await provider.complete("hello", Answer)

    async def test_empty_prompt_raises_value_error(self):
        provider = _make_provider()
        with pytest.raises(ValueError):
            await provider.complete("", Answer)


class TestOpenAIResponseParsing:
    async def test_successful_parse(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.beta.chat.completions.parse.return_value = _fake_response(
            parsed=answer,
        )
        result = await provider.complete("what is 6*7?", Answer)
        assert result.text == "42"

    async def test_max_tokens_forwards_to_sdk(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.beta.chat.completions.parse.return_value = _fake_response(
            parsed=answer,
        )
        await provider.complete("what is 6*7?", Answer, max_tokens=77)
        _, kwargs = provider.client.beta.chat.completions.parse.call_args
        assert kwargs["max_tokens"] == 77

    async def test_empty_choices_raises_invalid_response(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.return_value = _fake_response(
            choices=False,
        )
        with pytest.raises(InvalidResponseError):
            await provider.complete("hello", Answer)

    async def test_refusal_raises_content_filtered(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.return_value = _fake_response(
            refusal="I can't help with that",
        )
        with pytest.raises(ContentFilteredError) as exc_info:
            await provider.complete("hello", Answer)
        assert exc_info.value.reason == "I can't help with that"

    async def test_no_parsed_raises_invalid_response(self):
        provider = _make_provider()
        provider.client.beta.chat.completions.parse.return_value = _fake_response(
            parsed=None, refusal=None,
        )
        with pytest.raises(InvalidResponseError):
            await provider.complete("hello", Answer)
