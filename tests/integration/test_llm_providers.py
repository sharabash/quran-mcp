"""Integration tests for LLM provider wrappers — real API calls.

Hits real Anthropic, OpenAI, and Google APIs with tiny prompts and cheap
models. Each successful call costs a fraction of a penny (~10-50 tokens).

Covers per provider:
  - Successful structured output parse (tiny prompt, cheapest model)
  - Authentication error with bad API key (free — no tokens consumed)
  - Empty prompt validation (free — no API call)

Skips gracefully if API key is not configured.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.llm import AuthenticationError
from quran_mcp.lib.llm.anthropic import AnthropicProvider
from quran_mcp.lib.llm.google import GoogleProvider
from quran_mcp.lib.llm.openai import OpenAIProvider

# All tests share the session event loop (same as other integration tests)
pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Tiny response model — minimal tokens
# ---------------------------------------------------------------------------


class TinyAnswer(BaseModel):
    value: int


# ---------------------------------------------------------------------------
# Fixtures — real providers with cheapest models
# ---------------------------------------------------------------------------

_SETTINGS = get_settings()
_SAM = _SETTINGS.sampling


def _has_anthropic_key() -> bool:
    return bool(_SAM.anthropic_api_key.get_secret_value())


def _has_openai_key() -> bool:
    return bool(_SAM.openai_api_key.get_secret_value())


def _has_google_key() -> bool:
    return bool(_SAM.google_api_key.get_secret_value() or _SAM.gemini_api_key.get_secret_value())


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    async def test_successful_structured_parse(self):
        if not _has_anthropic_key():
            pytest.skip("Anthropic API key not configured")

        provider = AnthropicProvider(
            api_key=_SAM.anthropic_api_key.get_secret_value(),
            default_model="claude-haiku-4-5-20251001",
            default_max_tokens=64,
        )
        result = await provider.complete(
            "What is 2+2? Reply with just the number.",
            TinyAnswer,
            timeout=30.0,
        )
        assert isinstance(result, TinyAnswer)
        assert result.value == 4

    async def test_bad_api_key_raises_auth_error(self):
        provider = AnthropicProvider(
            api_key="sk-ant-INVALID-KEY-00000000",
            default_model="claude-haiku-4-5-20251001",
            default_max_tokens=64,
        )
        with pytest.raises(AuthenticationError) as exc_info:
            await provider.complete("hello", TinyAnswer, timeout=10.0)
        assert exc_info.value.provider == "anthropic"

    async def test_empty_prompt_raises_value_error(self):
        if not _has_anthropic_key():
            pytest.skip("Anthropic API key not configured")

        provider = AnthropicProvider(
            api_key=_SAM.anthropic_api_key.get_secret_value(),
        )
        with pytest.raises(ValueError):
            await provider.complete("", TinyAnswer)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    async def test_successful_structured_parse(self):
        if not _has_openai_key():
            pytest.skip("OpenAI API key not configured")

        provider = OpenAIProvider(
            api_key=_SAM.openai_api_key.get_secret_value(),
            default_model="gpt-5-nano",
        )
        result = await provider.complete(
            "What is 2+2? Reply with just the number.",
            TinyAnswer,
            timeout=30.0,
        )
        assert isinstance(result, TinyAnswer)
        assert result.value == 4

    async def test_bad_api_key_raises_auth_error(self):
        provider = OpenAIProvider(
            api_key="sk-INVALID-KEY-00000000",
            default_model="gpt-5-nano",
        )
        with pytest.raises(AuthenticationError) as exc_info:
            await provider.complete("hello", TinyAnswer, timeout=10.0)
        assert exc_info.value.provider == "openai"

    async def test_empty_prompt_raises_value_error(self):
        if not _has_openai_key():
            pytest.skip("OpenAI API key not configured")

        provider = OpenAIProvider(
            api_key=_SAM.openai_api_key.get_secret_value(),
        )
        with pytest.raises(ValueError):
            await provider.complete("", TinyAnswer)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


class TestGoogleProvider:
    async def test_successful_structured_parse(self):
        if not _has_google_key():
            pytest.skip("Google API key not configured")

        key = _SAM.google_api_key.get_secret_value() or _SAM.gemini_api_key.get_secret_value()
        provider = GoogleProvider(
            api_key=key,
            default_model="gemini-2.0-flash",
        )
        result = await provider.complete(
            "What is 2+2? Reply with just the number.",
            TinyAnswer,
            timeout=30.0,
        )
        assert isinstance(result, TinyAnswer)
        assert result.value == 4

    async def test_bad_api_key_raises_auth_error(self):
        provider = GoogleProvider(
            api_key="INVALID-KEY-00000000",
            default_model="gemini-2.0-flash",
        )
        with pytest.raises(AuthenticationError) as exc_info:
            await provider.complete("hello", TinyAnswer, timeout=10.0)
        assert exc_info.value.provider == "google"

    async def test_empty_prompt_raises_value_error(self):
        if not _has_google_key():
            pytest.skip("Google API key not configured")

        key = _SAM.google_api_key.get_secret_value() or _SAM.gemini_api_key.get_secret_value()
        provider = GoogleProvider(api_key=key)
        with pytest.raises(ValueError):
            await provider.complete("", TinyAnswer)
