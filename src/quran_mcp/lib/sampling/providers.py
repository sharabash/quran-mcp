"""Provider-specific sampling fallback adapters and configuration."""

from __future__ import annotations

import asyncio
import copy
import logging
import random
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

import httpx
from google.genai import types as genai_types
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    AudioContent,
    CreateMessageResult,
    ImageContent,
    ModelPreferences,
    SamplingMessage,
    TextContent,
)
from openai import APIStatusError

if TYPE_CHECKING:
    from anthropic import Anthropic
    from google import genai
    from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_DEFAULT_MODEL = "gpt-5.1"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
GEMINI_DEFAULT_MODEL = "gemini-3-pro-preview"
OPENROUTER_DEFAULT_MODEL = "deepseek/deepseek-v3.2:nitro"
RETRYABLE_STATUS_CODES = {502, 503, 429}

OPENAI_IMAGE_DETAILS = {"low", "high", "auto"}
AUDIO_MIME_TO_FORMAT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/x-wave": "wav",
}


def iter_model_preferences(
    model_preferences: ModelPreferences | str | Sequence[str] | None,
) -> Iterable[str]:
    if model_preferences is None:
        return ()

    if isinstance(model_preferences, str):
        return (model_preferences,)

    if isinstance(model_preferences, Sequence):
        return tuple(model for model in model_preferences if isinstance(model, str) and model)

    hints = model_preferences.hints or []
    return tuple(hint.name for hint in hints if getattr(hint, "name", None))


def require_text_content(message: SamplingMessage) -> str:
    content = message.content
    if not isinstance(content, TextContent):
        raise TypeError("Sampling fallback currently supports only text content payloads.")
    return content.text


def ensure_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def deep_update(target: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in overrides.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, Mapping):
            target[key] = deep_update(target[key].copy(), value)
        else:
            target[key] = value
    return target


def apply_meta_overrides(
    base: dict[str, Any],
    meta: Mapping[str, Any] | None,
    scope: str,
) -> dict[str, Any]:
    mapping = ensure_mapping(meta)
    if not mapping:
        return base

    override_key = f"openai_responses_{scope}"
    override_value = mapping.get(override_key)
    if isinstance(override_value, Mapping):
        return copy.deepcopy(dict(override_value))

    overrides_key = f"{override_key}_overrides"
    overrides_value = mapping.get(overrides_key)
    if isinstance(overrides_value, Mapping):
        updated = copy.deepcopy(base)
        return deep_update(updated, overrides_value)

    return base


def determine_image_detail(meta: Mapping[str, Any] | None) -> str:
    mapping = ensure_mapping(meta)
    if mapping:
        candidate = mapping.get("openai_image_detail") or mapping.get("image_detail") or mapping.get("detail")
        if candidate is not None:
            detail = str(candidate).lower()
            if detail not in OPENAI_IMAGE_DETAILS:
                raise ValueError(
                    "Unsupported image detail '%s'; expected one of %s" % (detail, sorted(OPENAI_IMAGE_DETAILS))
                )
            return detail
    return "auto"


def determine_audio_format(audio: AudioContent, meta: Mapping[str, Any] | None) -> str:
    mapping = ensure_mapping(meta)
    if mapping:
        candidate = mapping.get("openai_audio_format") or mapping.get("audio_format")
        if candidate is not None:
            fmt = str(candidate).lower()
            if fmt in {"mp3", "wav"}:
                return fmt
            raise ValueError("Unsupported audio format override '%s'; expected 'mp3' or 'wav'." % fmt)

    mime_type = getattr(audio, "mimeType", "").lower()
    fmt = AUDIO_MIME_TO_FORMAT.get(mime_type)
    if fmt:
        return fmt
    raise ValueError(
        "Unsupported audio MIME type '%s'; supply base64 audio using mp3 or wav, or set meta['openai_audio_format']."
        % mime_type
    )


def text_content_to_openai(content: TextContent) -> dict[str, Any]:
    base = {"type": "input_text", "text": content.text}
    return apply_meta_overrides(base, ensure_mapping(getattr(content, "meta", None)), "content")


def image_content_to_openai(content: ImageContent) -> dict[str, Any]:
    meta = ensure_mapping(getattr(content, "meta", None))
    base = {
        "type": "input_image",
        "detail": determine_image_detail(meta),
        "image_url": f"data:{content.mimeType};base64,{content.data}",
    }
    return apply_meta_overrides(base, meta, "content")


def audio_content_to_openai(content: AudioContent) -> dict[str, Any]:
    meta = ensure_mapping(getattr(content, "meta", None))
    base = {
        "type": "input_audio",
        "input_audio": {"data": content.data, "format": determine_audio_format(content, meta)},
    }
    return apply_meta_overrides(base, meta, "content")


def convert_to_openai_content(content: TextContent | ImageContent | AudioContent) -> dict[str, Any]:
    if isinstance(content, TextContent):
        return text_content_to_openai(content)
    if isinstance(content, ImageContent):
        return image_content_to_openai(content)
    if isinstance(content, AudioContent):
        return audio_content_to_openai(content)
    raise TypeError(f"Unsupported message content type '{type(content)!r}' for OpenAI Responses handler")


def normalize_role(role: str) -> str:
    if role == "system":
        return "developer"
    return role


def build_openai_message(
    role: str,
    content: TextContent | ImageContent | AudioContent,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_role = normalize_role(role)
    base = {"role": normalized_role, "type": "message", "content": [convert_to_openai_content(content)]}
    return apply_meta_overrides(base, meta, "message")


def extract_openai_config(metadata: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    mapping = ensure_mapping(metadata)
    if not mapping:
        return None

    for key in ("openai_responses", "openai"):
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
    return None


def apply_input_overrides(
    payload: list[Mapping[str, Any]],
    openai_config: Mapping[str, Any] | None,
) -> str | list[Mapping[str, Any]]:
    if not isinstance(openai_config, Mapping):
        return payload

    if "input" in openai_config:
        custom_input = openai_config["input"]
        if isinstance(custom_input, str):
            return custom_input
        if isinstance(custom_input, Sequence) and not isinstance(custom_input, (str, bytes, Mapping)):
            return list(custom_input)
        raise TypeError("openai_responses.input must be a string or a sequence of input items")

    result = list(payload)

    prefix = openai_config.get("input_prefix")
    if isinstance(prefix, Sequence) and not isinstance(prefix, (str, bytes, Mapping)):
        result = list(prefix) + result

    suffix = openai_config.get("input_suffix")
    if isinstance(suffix, Sequence) and not isinstance(suffix, (str, bytes, Mapping)):
        result = result + list(suffix)

    return result


def normalize_usage_payload(usage: Any) -> dict[str, Any] | None:
    """Project provider-specific usage objects into a JSON-safe payload."""
    if usage is None:
        return None

    if isinstance(usage, Mapping):
        return dict(usage)

    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, Mapping):
            return dict(dumped)

    to_dict = getattr(usage, "to_dict", None)
    if callable(to_dict):
        dumped = to_dict()
        if isinstance(dumped, Mapping):
            return dict(dumped)

    payload: dict[str, Any] = {}
    for field_name in (
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "cached_content_token_count",
    ):
        value = getattr(usage, field_name, None)
        if value is not None:
            payload[field_name] = value

    return payload or None


def build_sampling_result(
    *,
    provider: str,
    model: str,
    response_model: str,
    text: str,
    usage: Any = None,
) -> CreateMessageResult:
    """Build a typed fallback result without mutating private SDK attributes."""
    result_meta = normalize_usage_payload(usage)
    return CreateMessageResult(
        content=TextContent(
            type="text",
            text=text,
            _meta={"fallbackProvider": provider, "fallbackModel": model},
        ),
        role="assistant",
        model=response_model,
        _meta={"usage": result_meta} if result_meta is not None else None,
    )


class BaseSamplingHandler:
    def __init__(self, default_model: str) -> None:
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        return self._default_model

    def _select_model(self, preferences: ModelPreferences | str | Sequence[str] | None) -> str:
        for candidate in iter_model_preferences(preferences):
            if candidate:
                return candidate
        return self._default_model


class OpenAIResponsesSamplingHandler(BaseSamplingHandler):
    """Invoke the OpenAI Responses API."""

    def __init__(self, client: OpenAI, default_model: str) -> None:
        super().__init__(default_model)
        self._client = client

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult:
        openai_config = extract_openai_config(params.metadata)
        payload = self._build_message_payload(messages=messages)
        input_payload = apply_input_overrides(payload, openai_config)

        request_kwargs = self._build_request_kwargs(params, openai_config)
        model = self._select_model(params.modelPreferences)
        if isinstance(openai_config, Mapping) and "model" in openai_config:
            model = str(openai_config["model"])

        instructions = params.systemPrompt
        override_instructions = request_kwargs.pop("instructions", None)
        if override_instructions is not None:
            instructions = override_instructions

        max_tokens = params.maxTokens
        try:
            if hasattr(context, "info"):
                context.info(f"Sampling fallback: provider=openai model={model} max_tokens={max_tokens}")
            else:  # pragma: no cover
                logger.info("Sampling fallback: provider=openai model=%s max_tokens=%s", model, max_tokens)
        except Exception:  # pragma: no cover
            logger.debug("Failed to emit fallback visibility log for OpenAI", exc_info=True)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "input": input_payload,
            **request_kwargs,
        }
        if instructions is not None:
            create_kwargs["instructions"] = instructions
        create_kwargs["max_output_tokens"] = params.maxTokens

        response = await asyncio.to_thread(
            self._client.responses.create,
            **create_kwargs,
        )

        try:
            text = response.output_text
        except AttributeError as exc:  # pragma: no cover
            raise ValueError("OpenAI responses payload missing output_text") from exc

        if not text:
            logger.error(
                "Empty output_text. status=%s, incomplete_details=%r, usage=%r",
                getattr(response, "status", "unknown"),
                getattr(response, "incomplete_details", None),
                getattr(response, "usage", None),
            )
            raise ValueError("OpenAI responses payload returned empty output_text")

        return build_sampling_result(
            provider="openai",
            model=model,
            response_model=getattr(response, "model", model),
            text=text,
            usage=getattr(response, "usage", None),
        )

    @staticmethod
    def _build_message_payload(
        messages: Sequence[SamplingMessage],
    ) -> list[Mapping[str, object]]:
        return [
            build_openai_message(
                role=message.role,
                content=message.content,
                meta=ensure_mapping(getattr(message, "meta", None)),
            )
            for message in messages
        ]

    @staticmethod
    def _build_request_kwargs(
        params: SamplingParams,
        openai_config: Mapping[str, Any] | None,
    ) -> dict[str, object]:
        kwargs: dict[str, object] = {"max_output_tokens": params.maxTokens}
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.stopSequences:
            kwargs["stop"] = params.stopSequences

        if isinstance(openai_config, Mapping):
            overrides = openai_config.get("request")
            if isinstance(overrides, Mapping):
                kwargs = deep_update(kwargs, overrides)

        return kwargs


class AnthropicMessagesSamplingHandler(BaseSamplingHandler):
    """Invoke Anthropic's Messages API."""

    def __init__(self, client: Anthropic, default_model: str) -> None:
        super().__init__(default_model)
        self._client = client

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult:
        payload = self._build_messages(messages)
        kwargs = self._build_request_kwargs(params)
        model = self._select_model(params.modelPreferences)
        if params.systemPrompt:
            kwargs["system"] = params.systemPrompt

        max_tokens = params.maxTokens or 4096
        try:
            if hasattr(context, "info"):
                context.info(f"Sampling fallback: provider=anthropic model={model} max_tokens={max_tokens}")
            else:  # pragma: no cover
                logger.info("Sampling fallback: provider=anthropic model=%s max_tokens=%s", model, max_tokens)
        except Exception:  # pragma: no cover
            logger.debug("Failed to emit fallback visibility log for Anthropic", exc_info=True)

        response = await asyncio.to_thread(
            self._client.messages.create,
            model=model,
            messages=payload,
            max_tokens=max_tokens,
            timeout=httpx.Timeout(600.0, connect=30.0),
            **kwargs,
        )

        if not response.content:
            raise ValueError("Anthropic response contained no content")

        first = response.content[0]
        try:
            text = first.text
        except AttributeError as exc:  # pragma: no cover
            raise ValueError("Anthropic response content missing text") from exc

        if not text:
            raise ValueError("Anthropic response text is empty")

        return build_sampling_result(
            provider="anthropic",
            model=model,
            response_model=getattr(response, "model", model),
            text=text,
            usage=getattr(response, "usage", None),
        )

    @staticmethod
    def _build_messages(messages: Sequence[SamplingMessage]) -> list[Mapping[str, object]]:
        return [
            {
                "role": message.role,
                "content": [{"type": "text", "text": require_text_content(message)}],
            }
            for message in messages
        ]

    @staticmethod
    def _build_request_kwargs(params: SamplingParams) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.stopSequences:
            kwargs["stop_sequences"] = params.stopSequences
        return kwargs


class GeminiGenerativeSamplingHandler(BaseSamplingHandler):
    """Invoke Google Gemini models using the google-genai SDK."""

    def __init__(self, client: genai.Client, default_model: str) -> None:
        super().__init__(default_model)
        self._client = client

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult:
        model_name = self._select_model(params.modelPreferences)
        config = self._build_generation_config(params)
        contents = self._build_contents(messages)

        max_tokens = config.max_output_tokens if config else None
        try:
            if hasattr(context, "info"):
                context.info(f"Sampling fallback: provider=gemini model={model_name} max_tokens={max_tokens}")
            else:  # pragma: no cover
                logger.info("Sampling fallback: provider=gemini model=%s max_tokens=%s", model_name, max_tokens)
        except Exception:  # pragma: no cover
            logger.debug("Failed to emit fallback visibility log for Gemini", exc_info=True)

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=model_name,
            contents=contents,
            config=config,
        )

        try:
            text = response.text
        except AttributeError as exc:  # pragma: no cover
            raise ValueError("Gemini response missing text") from exc

        if not text:
            raise ValueError("Gemini response text is empty")

        return build_sampling_result(
            provider="gemini",
            model=model_name,
            response_model=getattr(response, "model", model_name),
            text=text,
            usage=getattr(response, "usage_metadata", None),
        )

    @staticmethod
    def _build_contents(messages: Sequence[SamplingMessage]) -> list[genai_types.Content]:
        role_map = {"user": "user", "assistant": "model"}
        return [
            genai_types.Content(
                role=role_map.get(message.role, message.role),
                parts=[genai_types.Part(text=require_text_content(message))],
            )
            for message in messages
        ]

    @staticmethod
    def _build_generation_config(params: SamplingParams) -> genai_types.GenerateContentConfig | None:
        kwargs: dict[str, Any] = {}
        if params.systemPrompt:
            kwargs["system_instruction"] = params.systemPrompt
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.stopSequences:
            kwargs["stop_sequences"] = list(params.stopSequences)
        if params.maxTokens:
            kwargs["max_output_tokens"] = params.maxTokens

        if not kwargs:
            return None
        return genai_types.GenerateContentConfig(**kwargs)


class OpenRouterChatCompletionsSamplingHandler(BaseSamplingHandler):
    """Invoke OpenRouter (or any OpenAI-compatible) Chat Completions API."""

    def __init__(
        self,
        client: OpenAI,
        default_model: str,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        super().__init__(default_model)
        self._client = client
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult:
        chat_messages = self._build_messages(messages, params.systemPrompt)
        model = self._select_model(params.modelPreferences)

        max_tokens = params.maxTokens
        try:
            if hasattr(context, "info"):
                context.info(f"Sampling fallback: provider=openrouter model={model} max_tokens={max_tokens}")
            else:
                logger.info("Sampling fallback: provider=openrouter model=%s max_tokens=%s", model, max_tokens)
        except Exception:
            logger.debug("Failed to emit fallback visibility log for OpenRouter", exc_info=True)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if params.temperature is not None:
            create_kwargs["temperature"] = params.temperature
        if params.stopSequences:
            create_kwargs["stop"] = list(params.stopSequences)

        extra = getattr(params, "_extra_openrouter", None)
        if extra:
            create_kwargs["extra_body"] = extra

        response = await self._call_with_retry(**create_kwargs)

        text = response.choices[0].message.content if response.choices else ""
        if not text:
            logger.error(
                "Empty Chat Completions response. model=%s, choices=%r, usage=%r",
                model,
                getattr(response, "choices", None),
                getattr(response, "usage", None),
            )
            raise ValueError("Chat Completions response returned empty content")

        return build_sampling_result(
            provider="openrouter",
            model=model,
            response_model=getattr(response, "model", model),
            text=text,
            usage=getattr(response, "usage", None),
        )

    async def _call_with_retry(self, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._client.chat.completions.create,
                    **kwargs,
                )
            except APIStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS_CODES:
                    raise
                last_error = exc
                if attempt < self._max_retries:
                    delay = self._retry_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        "OpenRouter %d error (attempt %d/%d), retrying in %.1fs",
                        exc.response.status_code,
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
        if last_error is None:  # pragma: no cover
            raise RuntimeError("OpenRouter retry loop exhausted without capturing an error")
        raise last_error

    @staticmethod
    def _build_messages(
        messages: Sequence[SamplingMessage],
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        chat_messages: list[dict[str, str]] = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            chat_messages.append({
                "role": msg.role,
                "content": require_text_content(msg),
            })
        return chat_messages

__all__ = [
    "AnthropicMessagesSamplingHandler",
    "BaseSamplingHandler",
    "GeminiGenerativeSamplingHandler",
    "OpenAIResponsesSamplingHandler",
    "OpenRouterChatCompletionsSamplingHandler",
    "OPENAI_DEFAULT_MODEL",
    "ANTHROPIC_DEFAULT_MODEL",
    "GEMINI_DEFAULT_MODEL",
    "OPENROUTER_DEFAULT_MODEL",
]
