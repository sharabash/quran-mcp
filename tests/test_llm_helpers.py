"""Tests for quran_mcp.lib.llm — helpers and exception hierarchy.

The provider implementations (openai.py, anthropic.py, google.py) hit
real APIs and are not tested for live calls here. These tests cover the
pure utility functions, exception construction, and the shared
completion-signature contract.

Covers:
  - validate_prompt: empty/whitespace rejection
  - truncate_response: text truncation
  - is_context_window_error: multi-provider pattern matching
  - extract_max_tokens_from_error: token count extraction
  - Exception hierarchy: construction and repr
"""

from __future__ import annotations

from inspect import signature

import pytest

import quran_mcp.lib.llm as llm
import quran_mcp.lib.llm.core as llm_core
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
from quran_mcp.lib.llm.google import GoogleProvider
from quran_mcp.lib.llm.openai import OpenAIProvider
from quran_mcp.lib.llm.helpers import (
    extract_max_tokens_from_error,
    is_context_window_error,
    truncate_response,
    validate_prompt,
)


# ---------------------------------------------------------------------------
# validate_prompt
# ---------------------------------------------------------------------------


class TestValidatePrompt:
    def test_valid_prompt(self):
        validate_prompt("Summarize this tafsir")  # no exception

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_prompt("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_prompt("   \n\t  ")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            validate_prompt(None)


# ---------------------------------------------------------------------------
# truncate_response
# ---------------------------------------------------------------------------


class TestTruncateResponse:
    def test_short_text_unchanged(self):
        assert truncate_response("hello") == "hello"

    def test_exact_max_len(self):
        text = "x" * 1000
        assert truncate_response(text) == text

    def test_truncated_with_ellipsis(self):
        text = "x" * 1500
        result = truncate_response(text, max_len=1000)
        assert len(result) == 1000
        assert result.endswith("...")

    def test_custom_max_len(self):
        text = "x" * 100
        result = truncate_response(text, max_len=50)
        assert len(result) == 50


# ---------------------------------------------------------------------------
# is_context_window_error
# ---------------------------------------------------------------------------


class TestIsContextWindowError:
    def test_openai_context_length_exceeded(self):
        err = Exception("This model's maximum context length is 4096 tokens")
        assert is_context_window_error(err) is True

    def test_openai_reduce_length(self):
        err = Exception("Please reduce the length of the messages or prompt tokens")
        assert is_context_window_error(err) is True

    def test_anthropic_prompt_too_long(self):
        err = Exception("prompt is too long: 100000 tokens > 80000 max")
        assert is_context_window_error(err) is True

    def test_anthropic_exceeds_token_limit(self):
        err = Exception("Request exceeds maximum token limit")
        assert is_context_window_error(err) is True

    def test_google_resource_exhausted(self):
        err = Exception("RESOURCE_EXHAUSTED: too many tokens in prompt")
        assert is_context_window_error(err) is True

    def test_generic_context_window(self):
        err = Exception("context window overflow")
        assert is_context_window_error(err) is True

    def test_generic_token_limit(self):
        err = Exception("token limit exceeded")
        assert is_context_window_error(err) is True

    def test_unrelated_error_not_detected(self):
        assert is_context_window_error(Exception("connection refused")) is False

    def test_empty_error(self):
        assert is_context_window_error(Exception("")) is False

    def test_reduce_length_without_tokens_context(self):
        """'reduce the length' alone is NOT enough — needs tokens/prompt/context nearby."""
        assert is_context_window_error(Exception("Please reduce the length of your essay")) is False


# ---------------------------------------------------------------------------
# extract_max_tokens_from_error
# ---------------------------------------------------------------------------


class TestExtractMaxTokensFromError:
    def test_openai_format(self):
        err = Exception("This model's maximum context length is 4096 tokens")
        assert extract_max_tokens_from_error(err) == 4096

    def test_comma_separated_number(self):
        err = Exception("maximum context length is 128,000 tokens")
        assert extract_max_tokens_from_error(err) == 128000

    def test_max_tokens_format(self):
        err = Exception("max_tokens: 4096")
        assert extract_max_tokens_from_error(err) == 4096

    def test_limit_format(self):
        err = Exception("limit of 100,000 tokens")
        assert extract_max_tokens_from_error(err) == 100000

    def test_no_number_returns_none(self):
        assert extract_max_tokens_from_error(Exception("something failed")) is None

    def test_empty_error_returns_none(self):
        assert extract_max_tokens_from_error(Exception("")) is None


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_provider_error_attributes(self):
        err = ProviderError("msg", "openai", cause=ValueError("inner"))
        assert err.provider == "openai"
        assert err.cause is not None
        assert "openai" in repr(err)

    def test_rate_limit_error(self):
        err = RateLimitError("anthropic", retry_after=30.0)
        assert err.retry_after == 30.0
        assert isinstance(err, ProviderError)

    def test_invalid_response_error(self):
        err = InvalidResponseError("openai", "Summary", raw_response="x" * 2000)
        assert err.model_name == "Summary"
        assert len(err.raw_response) <= 1000  # truncated

    def test_authentication_error(self):
        err = AuthenticationError("google")
        assert "google" in str(err)
        assert isinstance(err, ProviderError)

    def test_network_error(self):
        err = NetworkError("openai")
        assert isinstance(err, ProviderError)

    def test_content_filtered_error(self):
        err = ContentFilteredError("anthropic", reason="safety")
        assert err.reason == "safety"
        assert "safety" in str(err)

    def test_context_window_exceeded_error(self):
        err = ContextWindowExceededError("openai", max_tokens=4096)
        assert err.max_tokens == 4096
        assert "4096" in str(err)

    def test_all_inherit_from_provider_error(self):
        for cls in [
            RateLimitError,
            InvalidResponseError,
            AuthenticationError,
            NetworkError,
            ContentFilteredError,
            ContextWindowExceededError,
        ]:
            assert issubclass(cls, ProviderError)


class TestPackageSurface:
    def test_root_reexports_core_api(self):
        assert llm.ProviderError is llm_core.ProviderError
        assert llm.RateLimitError is llm_core.RateLimitError
        assert llm.__all__ == llm_core.__all__


# ---------------------------------------------------------------------------
# Shared provider contract
# ---------------------------------------------------------------------------


def test_complete_signature_matches_across_providers():
    expected = list(signature(OpenAIProvider.complete).parameters)
    assert list(signature(AnthropicProvider.complete).parameters) == expected
    assert list(signature(GoogleProvider.complete).parameters) == expected
