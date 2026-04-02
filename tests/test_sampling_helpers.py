"""Tests for quran_mcp.lib.sampling.handler — helper and provider fallback logic.

These tests cover the pure content-to-OpenAI conversion helpers, role
normalization, override logic, model selection, and hermetic provider-handler
behavior using fake SDK clients.

Covers:
  - _iter_model_preferences: preference parsing (string, list, ModelPreferences)
  - _deep_update: recursive dict merge
  - _normalize_role: system → developer
  - _determine_image_detail: validation of image detail settings
  - _determine_audio_format: MIME-to-format and override detection
  - _text_content_to_openai: TextContent → OpenAI format
  - _build_openai_message: full message construction
  - _extract_openai_config: config extraction from metadata
  - _apply_input_overrides: input prefix/suffix/replace
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp.types import AudioContent, ImageContent, ModelPreferences, SamplingMessage, TextContent
from openai import APIStatusError

from quran_mcp.lib.sampling.providers import (
    apply_input_overrides as _apply_input_overrides,
    build_openai_message as _build_openai_message,
    build_sampling_result as _build_sampling_result,
    deep_update as _deep_update,
    determine_audio_format as _determine_audio_format,
    determine_image_detail as _determine_image_detail,
    extract_openai_config as _extract_openai_config,
    iter_model_preferences as _iter_model_preferences,
    normalize_role as _normalize_role,
    normalize_usage_payload as _normalize_usage_payload,
    require_text_content as _require_text_content,
    text_content_to_openai as _text_content_to_openai,
)
from quran_mcp.lib.sampling.handler import (
    AnthropicMessagesSamplingHandler,
    build_handler_from_runtime_overrides,
    GeminiGenerativeSamplingHandler,
    OpenAIResponsesSamplingHandler,
    OpenRouterChatCompletionsSamplingHandler,
)
from quran_mcp.lib.config.settings import SamplingSettings
import quran_mcp.lib.sampling.runtime as sampling_runtime_mod


# ---------------------------------------------------------------------------
# _iter_model_preferences
# ---------------------------------------------------------------------------


class TestIterModelPreferences:
    def test_none_returns_empty(self):
        assert tuple(_iter_model_preferences(None)) == ()

    def test_string_returns_single(self):
        assert tuple(_iter_model_preferences("gpt-4")) == ("gpt-4",)

    def test_list_returns_all(self):
        assert tuple(_iter_model_preferences(["gpt-4", "claude-3"])) == ("gpt-4", "claude-3")

    def test_empty_strings_filtered(self):
        result = tuple(_iter_model_preferences(["gpt-4", "", "claude-3"]))
        assert result == ("gpt-4", "claude-3")

    def test_model_preferences_with_hints(self):
        from mcp.types import ModelHint
        prefs = ModelPreferences(hints=[ModelHint(name="gpt-4"), ModelHint(name="claude-3")])
        result = tuple(_iter_model_preferences(prefs))
        assert result == ("gpt-4", "claude-3")


# ---------------------------------------------------------------------------
# _deep_update
# ---------------------------------------------------------------------------


class TestDeepUpdate:
    def test_simple_merge(self):
        target = {"a": 1}
        result = _deep_update(target, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overwrite_scalar(self):
        target = {"a": 1}
        result = _deep_update(target, {"a": 2})
        assert result == {"a": 2}

    def test_nested_merge(self):
        target = {"a": {"x": 1, "y": 2}}
        result = _deep_update(target, {"a": {"y": 3, "z": 4}})
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_nested_replaced_by_scalar(self):
        target = {"a": {"x": 1}}
        result = _deep_update(target, {"a": "replaced"})
        assert result == {"a": "replaced"}


# ---------------------------------------------------------------------------
# _normalize_role
# ---------------------------------------------------------------------------


class TestNormalizeRole:
    def test_system_becomes_developer(self):
        assert _normalize_role("system") == "developer"

    def test_user_unchanged(self):
        assert _normalize_role("user") == "user"

    def test_assistant_unchanged(self):
        assert _normalize_role("assistant") == "assistant"


# ---------------------------------------------------------------------------
# _determine_image_detail
# ---------------------------------------------------------------------------


class TestDetermineImageDetail:
    def test_default_auto(self):
        assert _determine_image_detail(None) == "auto"

    def test_explicit_high(self):
        assert _determine_image_detail({"openai_image_detail": "high"}) == "high"

    def test_explicit_low(self):
        assert _determine_image_detail({"image_detail": "low"}) == "low"

    def test_case_insensitive(self):
        assert _determine_image_detail({"detail": "HIGH"}) == "high"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Unsupported image detail"):
            _determine_image_detail({"detail": "ultra"})

    def test_empty_meta(self):
        assert _determine_image_detail({}) == "auto"


# ---------------------------------------------------------------------------
# _determine_audio_format
# ---------------------------------------------------------------------------


class TestDetermineAudioFormat:
    def test_mp3_from_mime(self):
        audio = AudioContent(type="audio", data="base64data", mimeType="audio/mpeg")
        assert _determine_audio_format(audio, None) == "mp3"

    def test_wav_from_mime(self):
        audio = AudioContent(type="audio", data="base64data", mimeType="audio/wav")
        assert _determine_audio_format(audio, None) == "wav"

    def test_override_from_meta(self):
        audio = AudioContent(type="audio", data="base64data", mimeType="audio/mpeg")
        assert _determine_audio_format(audio, {"openai_audio_format": "wav"}) == "wav"

    def test_unsupported_mime_raises(self):
        audio = AudioContent(type="audio", data="base64data", mimeType="audio/ogg")
        with pytest.raises(ValueError, match="Unsupported audio MIME"):
            _determine_audio_format(audio, None)

    def test_unsupported_override_raises(self):
        audio = AudioContent(type="audio", data="base64data", mimeType="audio/mpeg")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            _determine_audio_format(audio, {"audio_format": "ogg"})


# ---------------------------------------------------------------------------
# _text_content_to_openai
# ---------------------------------------------------------------------------


class TestTextContentToOpenai:
    def test_basic_conversion(self):
        tc = TextContent(type="text", text="Hello world")
        result = _text_content_to_openai(tc)
        assert result["type"] == "input_text"
        assert result["text"] == "Hello world"


# ---------------------------------------------------------------------------
# _build_openai_message
# ---------------------------------------------------------------------------


class TestBuildOpenaiMessage:
    def test_user_message(self):
        tc = TextContent(type="text", text="Hello")
        result = _build_openai_message("user", tc)
        assert result["role"] == "user"
        assert result["type"] == "message"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Hello"

    def test_system_normalized_to_developer(self):
        tc = TextContent(type="text", text="Instructions")
        result = _build_openai_message("system", tc)
        assert result["role"] == "developer"


# ---------------------------------------------------------------------------
# _extract_openai_config
# ---------------------------------------------------------------------------


class TestExtractOpenaiConfig:
    def test_none_metadata(self):
        assert _extract_openai_config(None) is None

    def test_openai_responses_key(self):
        meta = {"openai_responses": {"model": "gpt-4", "temperature": 0.5}}
        result = _extract_openai_config(meta)
        assert result["model"] == "gpt-4"

    def test_openai_key_fallback(self):
        meta = {"openai": {"model": "gpt-4"}}
        result = _extract_openai_config(meta)
        assert result["model"] == "gpt-4"

    def test_no_matching_key(self):
        assert _extract_openai_config({"other": "value"}) is None


# ---------------------------------------------------------------------------
# _apply_input_overrides
# ---------------------------------------------------------------------------


class TestApplyInputOverrides:
    def test_no_config_returns_payload(self):
        payload = [{"role": "user", "content": "hi"}]
        result = _apply_input_overrides(payload, None)
        assert result == payload

    def test_custom_input_string(self):
        result = _apply_input_overrides(
            [{"msg": "original"}],
            {"input": "custom string input"},
        )
        assert result == "custom string input"

    def test_custom_input_list(self):
        custom = [{"role": "user", "content": "custom"}]
        result = _apply_input_overrides([{"msg": "original"}], {"input": custom})
        assert result == custom

    def test_prefix(self):
        payload = [{"msg": "original"}]
        config = {"input_prefix": [{"msg": "prefix"}]}
        result = _apply_input_overrides(payload, config)
        assert result == [{"msg": "prefix"}, {"msg": "original"}]

    def test_suffix(self):
        payload = [{"msg": "original"}]
        config = {"input_suffix": [{"msg": "suffix"}]}
        result = _apply_input_overrides(payload, config)
        assert result == [{"msg": "original"}, {"msg": "suffix"}]


# ---------------------------------------------------------------------------
# Usage normalization / result shaping
# ---------------------------------------------------------------------------


@dataclass
class _UsageObject:
    input_tokens: int = 3
    output_tokens: int = 5


class TestNormalizeUsagePayload:
    def test_mapping_passed_through(self):
        assert _normalize_usage_payload({"input_tokens": 2}) == {"input_tokens": 2}

    def test_object_attrs_projected(self):
        assert _normalize_usage_payload(_UsageObject()) == {
            "input_tokens": 3,
            "output_tokens": 5,
        }


class TestBuildSamplingResult:
    def test_usage_stored_in_result_meta(self):
        result = _build_sampling_result(
            provider="openai",
            model="gpt-test",
            response_model="gpt-test",
            text="hello",
            usage={"input_tokens": 2, "output_tokens": 4},
        )
        assert result.meta == {"usage": {"input_tokens": 2, "output_tokens": 4}}
        assert result.content.meta == {
            "fallbackProvider": "openai",
            "fallbackModel": "gpt-test",
        }


class TestProviderRequestShaping:
    def test_anthropic_request_kwargs_maps_stop_sequences(self):
        params = SimpleNamespace(
            temperature=0.4,
            stopSequences=["done"],
        )

        kwargs = AnthropicMessagesSamplingHandler._build_request_kwargs(params)

        assert kwargs == {"temperature": 0.4, "stop_sequences": ["done"]}

    def test_openai_request_kwargs_merge_overrides(self):
        params = SimpleNamespace(
            maxTokens=128,
            temperature=0.2,
            stopSequences=["END"],
        )

        kwargs = OpenAIResponsesSamplingHandler._build_request_kwargs(
            params,
            {"request": {"temperature": 0.7, "reasoning": {"effort": "low"}}},
        )

        assert kwargs["max_output_tokens"] == 128
        assert kwargs["temperature"] == 0.7
        assert kwargs["stop"] == ["END"]
        assert kwargs["reasoning"] == {"effort": "low"}

    def test_gemini_generation_config_and_contents(self):
        params = SimpleNamespace(
            systemPrompt="You are helpful.",
            temperature=0.3,
            stopSequences=("done",),
            maxTokens=64,
        )
        config = GeminiGenerativeSamplingHandler._build_generation_config(params)
        assert config is not None
        assert config.system_instruction == "You are helpful."
        assert config.temperature == 0.3
        assert config.stop_sequences == ["done"]
        assert config.max_output_tokens == 64

        contents = GeminiGenerativeSamplingHandler._build_contents(
            [
                SamplingMessage(role="user", content=TextContent(type="text", text="hello")),
                SamplingMessage(role="assistant", content=TextContent(type="text", text="world")),
            ]
        )
        assert [content.role for content in contents] == ["user", "model"]
        assert [part.text for part in contents[0].parts] == ["hello"]

    def test_openrouter_messages_include_system_prompt(self):
        messages = OpenRouterChatCompletionsSamplingHandler._build_messages(
            [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))],
            system_prompt="Use plain language.",
        )
        assert messages[0] == {"role": "system", "content": "Use plain language."}
        assert messages[1] == {"role": "user", "content": "hello"}


class TestRuntimeProviderSelection:
    def test_build_handler_from_runtime_overrides_selects_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        sentinel = object()
        calls: list[tuple[str, str | None]] = []

        def _config_factory(provider: str):
            def _config(_sampling, model_override):
                calls.append((provider, model_override))
                return SimpleNamespace(provider=provider, handler=sentinel, default_model=model_override)

            return _config

        monkeypatch.setattr(sampling_runtime_mod, "_configure_openai", _config_factory("openai"))
        monkeypatch.setattr(sampling_runtime_mod, "_configure_anthropic", _config_factory("anthropic"))
        monkeypatch.setattr(sampling_runtime_mod, "_configure_gemini", _config_factory("gemini"))
        monkeypatch.setattr(sampling_runtime_mod, "_configure_openrouter", _config_factory("openrouter"))

        handler = build_handler_from_runtime_overrides(
            {"active_provider": "claude", "active_model": "gpt-5"},
            sampling=SamplingSettings(),
        )

        assert handler is sentinel
        assert calls == [("anthropic", "gpt-5")]


class _FakeOpenAIResponsesClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeOpenAIClient:
    def __init__(self, response):
        self.responses = _FakeOpenAIResponsesClient(response)


class _FakeAnthropicMessagesClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeAnthropicMessagesClient(response)


class _FakeGeminiModelsClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeGeminiClient:
    def __init__(self, response):
        self.models = _FakeGeminiModelsClient(response)


class _FakeOpenRouterChatCompletionsClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._outcomes:
            raise AssertionError("OpenRouter fake client exhausted unexpectedly")

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeOpenRouterClient:
    def __init__(self, outcomes):
        self.chat = SimpleNamespace(
            completions=_FakeOpenRouterChatCompletionsClient(outcomes)
        )


def _retryable_status_error(status_code: int) -> APIStatusError:
    request = httpx.Request(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
    )
    response = httpx.Response(status_code, request=request)
    return APIStatusError("retryable status", response=response, body=None)


class TestProviderHandlers:
    @pytest.mark.asyncio
    async def test_openai_handler_uses_metadata_override_and_shapes_result(self):
        response = SimpleNamespace(output_text="openai answer", model="openai-response", usage={"input_tokens": 7})
        handler = OpenAIResponsesSamplingHandler(_FakeOpenAIClient(response), default_model="gpt-default")
        params = SimpleNamespace(
            maxTokens=64,
            temperature=0.2,
            stopSequences=["END"],
            systemPrompt="Be brief.",
            metadata={
                "openai_responses": {
                    "model": "gpt-metadata",
                    "request": {
                        "temperature": 0.7,
                        "reasoning": {"effort": "low"},
                    },
                }
            },
            modelPreferences=["gpt-4.1"],
        )
        context_messages: list[str] = []
        context = SimpleNamespace(info=context_messages.append)
        messages = [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))]

        result = await handler(messages, params, context)

        call = handler._client.responses.calls[0]
        assert call["model"] == "gpt-metadata"
        assert call["max_output_tokens"] == 64
        assert call["instructions"] == "Be brief."
        assert call["temperature"] == 0.7
        assert call["reasoning"] == {"effort": "low"}
        assert call["input"][0]["content"][0]["text"] == "hello"
        assert result.content.text == "openai answer"
        assert result.content.meta == {"fallbackProvider": "openai", "fallbackModel": "gpt-metadata"}
        assert result.meta == {"usage": {"input_tokens": 7}}
        assert context_messages

    @pytest.mark.asyncio
    async def test_anthropic_handler_is_hermetic_and_shapes_result(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(text="anthropic answer")],
            model="claude-response",
            usage={"output_tokens": 11},
        )
        handler = AnthropicMessagesSamplingHandler(_FakeAnthropicClient(response), default_model="claude-default")
        params = SimpleNamespace(
            maxTokens=42,
            temperature=0.5,
            stopSequences=["STOP"],
            systemPrompt="Stay concise.",
            modelPreferences="claude-3.7",
        )
        context_messages: list[str] = []
        context = SimpleNamespace(info=context_messages.append)
        messages = [SamplingMessage(role="user", content=TextContent(type="text", text="question"))]

        result = await handler(messages, params, context)

        call = handler._client.messages.calls[0]
        assert call["model"] == "claude-3.7"
        assert call["max_tokens"] == 42
        assert call["messages"][0]["content"][0]["text"] == "question"
        assert call["system"] == "Stay concise."
        assert result.content.text == "anthropic answer"
        assert result.content.meta == {"fallbackProvider": "anthropic", "fallbackModel": "claude-3.7"}
        assert result.meta == {"usage": {"output_tokens": 11}}
        assert context_messages

    @pytest.mark.asyncio
    async def test_gemini_handler_is_hermetic_and_shapes_result(self):
        response = SimpleNamespace(text="gemini answer", model="gemini-response", usage_metadata={"total_tokens": 13})
        handler = GeminiGenerativeSamplingHandler(_FakeGeminiClient(response), default_model="gemini-default")
        params = SimpleNamespace(
            maxTokens=48,
            temperature=0.3,
            stopSequences=("END",),
            systemPrompt="Be precise.",
            modelPreferences=None,
        )
        context_messages: list[str] = []
        context = SimpleNamespace(info=context_messages.append)
        messages = [SamplingMessage(role="user", content=TextContent(type="text", text="hello gemini"))]

        result = await handler(messages, params, context)

        call = handler._client.models.calls[0]
        assert call["model"] == "gemini-default"
        assert call["contents"][0].parts[0].text == "hello gemini"
        assert call["config"].max_output_tokens == 48
        assert call["config"].system_instruction == "Be precise."
        assert result.content.text == "gemini answer"
        assert result.content.meta == {"fallbackProvider": "gemini", "fallbackModel": "gemini-default"}
        assert result.meta == {"usage": {"total_tokens": 13}}
        assert context_messages

    @pytest.mark.asyncio
    async def test_openai_handler_rejects_empty_output_text(self):
        response = SimpleNamespace(output_text="", model="openai-response")
        handler = OpenAIResponsesSamplingHandler(_FakeOpenAIClient(response), default_model="gpt-default")
        params = SimpleNamespace(
            maxTokens=16,
            temperature=None,
            stopSequences=(),
            systemPrompt=None,
            metadata=None,
            modelPreferences=None,
        )

        with pytest.raises(ValueError, match="empty output_text"):
            await handler(
                [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))],
                params,
                SimpleNamespace(),
            )

    @pytest.mark.asyncio
    async def test_anthropic_handler_rejects_empty_content(self):
        response = SimpleNamespace(content=[], model="claude-response", usage=None)
        handler = AnthropicMessagesSamplingHandler(_FakeAnthropicClient(response), default_model="claude-default")
        params = SimpleNamespace(
            maxTokens=16,
            temperature=None,
            stopSequences=(),
            systemPrompt=None,
            modelPreferences=None,
        )

        with pytest.raises(ValueError, match="no content"):
            await handler(
                [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))],
                params,
                SimpleNamespace(),
            )

    @pytest.mark.asyncio
    async def test_gemini_handler_rejects_empty_text(self):
        response = SimpleNamespace(text="", model="gemini-response", usage_metadata=None)
        handler = GeminiGenerativeSamplingHandler(_FakeGeminiClient(response), default_model="gemini-default")
        params = SimpleNamespace(
            maxTokens=16,
            temperature=None,
            stopSequences=(),
            systemPrompt=None,
            modelPreferences=None,
        )

        with pytest.raises(ValueError, match="empty"):
            await handler(
                [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))],
                params,
                SimpleNamespace(),
            )

    @pytest.mark.asyncio
    async def test_openrouter_handler_retries_retryable_status_then_succeeds(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="openrouter answer"))],
            model="router-response",
            usage={"total_tokens": 9},
        )
        handler = OpenRouterChatCompletionsSamplingHandler(
            _FakeOpenRouterClient([_retryable_status_error(429), response]),
            default_model="router-default",
            max_retries=1,
            retry_base_delay=0.0,
        )
        params = SimpleNamespace(
            maxTokens=32,
            temperature=0.1,
            stopSequences=["STOP"],
            systemPrompt="Use concise answers.",
            metadata=None,
            modelPreferences=["router-hint"],
        )
        context_messages: list[str] = []
        context = SimpleNamespace(info=context_messages.append)

        with patch("quran_mcp.lib.sampling.providers.random.uniform", return_value=0.0), patch(
            "quran_mcp.lib.sampling.providers.asyncio.sleep",
            new=AsyncMock(),
        ):
            result = await handler(
                [SamplingMessage(role="user", content=TextContent(type="text", text="hello"))],
                params,
                context,
            )

        call_client = handler._client.chat.completions
        assert len(call_client.calls) == 2
        assert call_client.calls[0]["model"] == "router-hint"
        assert call_client.calls[0]["messages"][0]["role"] == "system"
        assert result.content.text == "openrouter answer"
        assert result.content.meta == {"fallbackProvider": "openrouter", "fallbackModel": "router-hint"}
        assert result.meta == {"usage": {"total_tokens": 9}}
        assert context_messages


# ---------------------------------------------------------------------------
# _require_text_content
# ---------------------------------------------------------------------------


class TestRequireTextContent:
    def test_extracts_text_from_text_content(self):
        from mcp.types import SamplingMessage
        msg = SamplingMessage(role="user", content=TextContent(type="text", text="hello"))
        assert _require_text_content(msg) == "hello"

    def test_raises_on_image_content(self):
        from mcp.types import SamplingMessage
        msg = SamplingMessage(role="user", content=ImageContent(type="image", data="base64", mimeType="image/png"))
        with pytest.raises(TypeError, match="text content"):
            _require_text_content(msg)
