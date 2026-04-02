"""Tests for quran_mcp.lib.llm.google — error mapping and content filter detection.

Mocks google.genai Client to test error → ProviderError mapping, FinishReason
detection, and response parsing.

Covers:
  - ClientError → AuthenticationError, ContextWindowExceededError, RateLimitError
  - ServerError → NetworkError
  - FinishReason.SAFETY → ContentFilteredError
  - No parsed output → InvalidResponseError
  - Successful parse → returns model instance
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from google.genai.errors import ClientError, ServerError
from google.genai.types import FinishReason
from quran_mcp.lib.llm import (
    AuthenticationError,
    ContentFilteredError,
    ContextWindowExceededError,
    InvalidResponseError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from quran_mcp.lib.llm.google import GoogleProvider


class Answer(BaseModel):
    text: str


def _make_provider() -> GoogleProvider:
    provider = GoogleProvider(api_key="test-key", max_retries=0, retry_base_delay=0.0)
    provider.client = MagicMock()
    provider.client.aio.models.generate_content = AsyncMock()
    return provider


def _fake_response(*, parsed=None, finish_reason=FinishReason.STOP, finish_message=None, has_candidates=True):
    candidate = MagicMock()
    candidate.finish_reason = finish_reason
    candidate.finish_message = finish_message
    candidate.content = MagicMock()
    candidate.content.parts = []

    resp = MagicMock()
    resp.parsed = parsed
    resp.candidates = [candidate] if has_candidates else []
    return resp


class TestGoogleErrorMapping:
    async def test_timeout_raises_network_error(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = asyncio.TimeoutError()
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer, timeout=0.001)

    async def test_auth_error_401(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ClientError(401, {})
        with pytest.raises(AuthenticationError):
            await provider.complete("hello", Answer)

    async def test_auth_error_403(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ClientError(403, {})
        with pytest.raises(AuthenticationError):
            await provider.complete("hello", Answer)

    async def test_context_window_error(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ClientError(
            400, {"error": "RESOURCE_EXHAUSTED: too many tokens in prompt"}
        )
        with pytest.raises(ContextWindowExceededError):
            await provider.complete("hello", Answer)

    async def test_rate_limit_429(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ClientError(429, {})
        with pytest.raises(RateLimitError):
            await provider.complete("hello", Answer)

    async def test_server_error_raises_network_error(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ServerError(500, {})
        with pytest.raises(NetworkError):
            await provider.complete("hello", Answer)

    async def test_generic_client_error(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.side_effect = ClientError(400, {"error": "bad param"})
        with pytest.raises(ProviderError):
            await provider.complete("hello", Answer)

    async def test_empty_prompt_raises_value_error(self):
        provider = _make_provider()
        with pytest.raises(ValueError):
            await provider.complete("", Answer)


class TestGoogleContentFilter:
    async def test_safety_finish_reason(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.return_value = _fake_response(
            finish_reason=FinishReason.SAFETY,
        )
        with pytest.raises(ContentFilteredError) as exc_info:
            await provider.complete("hello", Answer)
        assert "SAFETY" in exc_info.value.reason

    async def test_prohibited_content_finish_reason(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.return_value = _fake_response(
            finish_reason=FinishReason.PROHIBITED_CONTENT,
        )
        with pytest.raises(ContentFilteredError):
            await provider.complete("hello", Answer)

    async def test_blocklist_finish_reason(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.return_value = _fake_response(
            finish_reason=FinishReason.BLOCKLIST,
        )
        with pytest.raises(ContentFilteredError):
            await provider.complete("hello", Answer)


class TestGoogleResponseParsing:
    async def test_successful_parse(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.aio.models.generate_content.return_value = _fake_response(
            parsed=answer,
        )
        result = await provider.complete("what is 6*7?", Answer)
        assert result.text == "42"

    async def test_max_tokens_forwards_to_sdk(self):
        provider = _make_provider()
        answer = Answer(text="42")
        provider.client.aio.models.generate_content.return_value = _fake_response(
            parsed=answer,
        )
        await provider.complete("what is 6*7?", Answer, max_tokens=77)
        _, kwargs = provider.client.aio.models.generate_content.call_args
        assert kwargs["config"].max_output_tokens == 77

    async def test_no_parsed_raises_invalid_response(self):
        provider = _make_provider()
        provider.client.aio.models.generate_content.return_value = _fake_response(
            parsed=None,
        )
        with pytest.raises(InvalidResponseError):
            await provider.complete("hello", Answer)
