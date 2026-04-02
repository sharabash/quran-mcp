"""Runtime ownership and provider assembly for sampling fallback."""

from __future__ import annotations

import asyncio
import contextvars
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from anthropic import Anthropic
from fastmcp.client.sampling import SamplingHandler
from google import genai
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import CreateMessageResult, SamplingMessage
from openai import OpenAI

from quran_mcp.lib.config.settings import SamplingSettings, get_settings
from quran_mcp.lib.sampling.providers import (
    ANTHROPIC_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENROUTER_DEFAULT_MODEL,
    AnthropicMessagesSamplingHandler,
    GeminiGenerativeSamplingHandler,
    OpenAIResponsesSamplingHandler,
    OpenRouterChatCompletionsSamplingHandler,
)

logger = logging.getLogger(__name__)

_handler_override: contextvars.ContextVar[SamplingHandler | None] = contextvars.ContextVar(
    "_handler_override",
    default=None,
)


@dataclass(frozen=True)
class HandlerConfig:
    """Provider assembly result used by runtime ownership."""

    provider: str
    handler: SamplingHandler
    default_model: str


class DynamicSamplingHandler:
    """Proxy that wraps a SamplingHandler and enables hot-swap."""

    def __init__(self, handler: SamplingHandler | None) -> None:
        self._handler = handler
        self._lock = asyncio.Lock()

    def __bool__(self) -> bool:
        return self._handler is not None or _handler_override.get(None) is not None

    @property
    def current_handler(self) -> SamplingHandler | None:
        return self._handler

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: Any,
    ) -> CreateMessageResult:
        handler = _handler_override.get(None)
        if handler is None:
            handler = self._handler
        if handler is None:
            raise RuntimeError("No sampling handler configured")
        return await handler(messages, params, context)

    async def update_handler(self, new_handler: SamplingHandler) -> SamplingHandler | None:
        """Swap the global handler. Returns the previous handler for rollback."""
        async with self._lock:
            previous = self._handler
            self._handler = new_handler
            return previous

    def set_context_override(self, handler: SamplingHandler) -> None:
        """Set a per-async-task handler override (for comparison runs)."""
        _handler_override.set(handler)

    def clear_context_override(self) -> None:
        """Clear the per-async-task handler override."""
        _handler_override.set(None)


_active_dynamic_handler: contextvars.ContextVar[DynamicSamplingHandler | None] = contextvars.ContextVar(
    "_active_dynamic_handler",
    default=None,
)


def get_dynamic_handler() -> DynamicSamplingHandler | None:
    """Get the DynamicSamplingHandler bound to the current context."""
    return _active_dynamic_handler.get()


def load_first(values: tuple[str | None, ...]) -> str | None:
    """Return the first non-empty string from a precedence list."""
    for value in values:
        if value:
            return value
    return None


def _configure_openrouter(
    sampling: "SamplingSettings",
    model_override: str | None,
) -> HandlerConfig | None:
    api_key = load_first((
        sampling.openrouter_api_key.get_secret_value(),
        sampling.api_key.get_secret_value(),
    ))
    if not api_key:
        logger.debug("Missing OpenRouter API key; sampling fallback disabled")
        return None

    base_url = load_first((sampling.openrouter_base_url, sampling.base_url)) or "https://openrouter.ai/api/v1"
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={
            "HTTP-Referer": "https://mcp.quran.ai",
            "X-Title": "quran-mcp",
        },
    )
    model = sampling.openrouter_model or model_override or OPENROUTER_DEFAULT_MODEL
    handler = OpenRouterChatCompletionsSamplingHandler(client=client, default_model=model)
    return HandlerConfig(provider="openrouter", handler=handler, default_model=model)


def _configure_openai(
    sampling: "SamplingSettings",
    model_override: str | None,
) -> HandlerConfig | None:
    api_key = load_first((
        sampling.openai_api_key.get_secret_value(),
        sampling.api_key.get_secret_value(),
    ))
    if not api_key:
        logger.debug("Missing OpenAI API key; sampling fallback disabled")
        return None

    kwargs: dict[str, object] = {"api_key": api_key}
    base_url = load_first((sampling.openai_base_url, sampling.base_url))
    if base_url:
        kwargs["base_url"] = base_url
    if sampling.openai_org:
        kwargs["organization"] = sampling.openai_org

    client = OpenAI(**kwargs)
    model = sampling.openai_model or model_override or OPENAI_DEFAULT_MODEL
    handler = OpenAIResponsesSamplingHandler(client=client, default_model=model)
    return HandlerConfig(provider="openai", handler=handler, default_model=model)


def _configure_anthropic(
    sampling: "SamplingSettings",
    model_override: str | None,
) -> HandlerConfig | None:
    api_key = load_first((
        sampling.anthropic_api_key.get_secret_value(),
        sampling.api_key.get_secret_value(),
    ))
    if not api_key:
        logger.debug("Missing Anthropic API key; sampling fallback disabled")
        return None

    client_kwargs: dict[str, object] = {"api_key": api_key}
    base_url = load_first((sampling.anthropic_base_url, sampling.base_url))
    if base_url:
        client_kwargs["base_url"] = base_url

    client = Anthropic(**client_kwargs)
    model = sampling.anthropic_model or model_override or ANTHROPIC_DEFAULT_MODEL
    handler = AnthropicMessagesSamplingHandler(client=client, default_model=model)
    return HandlerConfig(provider="anthropic", handler=handler, default_model=model)


def _configure_gemini(
    sampling: "SamplingSettings",
    model_override: str | None,
) -> HandlerConfig | None:
    api_key = load_first((
        sampling.google_api_key.get_secret_value(),
        sampling.gemini_api_key.get_secret_value(),
        sampling.api_key.get_secret_value(),
    ))
    if not api_key:
        logger.debug("Missing Gemini API key; sampling fallback disabled")
        return None

    client = genai.Client(api_key=api_key)
    model = sampling.gemini_model or model_override or GEMINI_DEFAULT_MODEL
    handler = GeminiGenerativeSamplingHandler(client=client, default_model=model)
    return HandlerConfig(provider="gemini", handler=handler, default_model=model)


def resolve_handler_config(
    sampling: "SamplingSettings",
    *,
    provider: str | None = None,
    model_override: str | None = None,
) -> HandlerConfig | None:
    """Resolve the configured provider into a concrete handler assembly."""
    selected_provider = (provider if provider is not None else sampling.provider).strip().lower()

    if selected_provider in {"", "openai"}:
        return _configure_openai(sampling, model_override)
    if selected_provider in {"anthropic", "claude"}:
        return _configure_anthropic(sampling, model_override)
    if selected_provider in {"google", "gemini"}:
        return _configure_gemini(sampling, model_override)
    if selected_provider == "openrouter":
        return _configure_openrouter(sampling, model_override)

    logger.warning("Unsupported sampling provider '%s'; fallback disabled", selected_provider)
    return None


def build_handler_from_runtime_overrides(
    overrides: Mapping[str, Any],
    *,
    sampling: "SamplingSettings",
) -> SamplingHandler | None:
    """Build a concrete SamplingHandler from runtime DB overrides."""
    provider = str(overrides.get("active_provider") or "").strip()
    model = str(overrides.get("active_model") or "").strip()
    if not provider or not model:
        return None

    config = resolve_handler_config(
        sampling,
        provider=provider,
        model_override=model,
    )
    return config.handler if config else None


async def apply_runtime_sampling_overrides(
    dynamic_handler: DynamicSamplingHandler,
    overrides: Mapping[str, Any],
    *,
    sampling: "SamplingSettings",
) -> bool:
    """Apply runtime DB overrides to an already-owned dynamic handler."""
    handler = build_handler_from_runtime_overrides(overrides, sampling=sampling)
    if handler is None:
        provider = str(overrides.get("active_provider") or "").strip() or "<unset>"
        model = str(overrides.get("active_model") or "").strip() or "<unset>"
        logger.warning(
            "Ignored runtime_config sampling overrides (provider=%s, model=%s)",
            provider,
            model,
        )
        return False

    await dynamic_handler.update_handler(handler)
    return True


def sampling_handler(
    sampling: "SamplingSettings | None" = None,
    *,
    register_active: bool = False,
) -> DynamicSamplingHandler:
    """Instantiate a DynamicSamplingHandler wrapping the configured provider.

    Provider assembly is pure by default. Callers that want an ambient handler
    for the current execution context must opt in explicitly.
    """
    if sampling is None:
        sampling = get_settings().sampling

    provider = sampling.provider.strip().lower()
    config = resolve_handler_config(sampling, model_override=sampling.model)

    inner = config.handler if config else None
    if config:
        logger.info(
            "Sampling fallback enabled with provider=%s model='%s'",
            config.provider,
            config.default_model,
        )
    else:
        logger.warning("Sampling fallback disabled for provider '%s'", provider or "openai")

    proxy = DynamicSamplingHandler(inner)
    if register_active:
        activate_dynamic_handler(proxy)
    return proxy


def activate_dynamic_handler(dynamic_handler: DynamicSamplingHandler) -> DynamicSamplingHandler:
    """Bind one DynamicSamplingHandler to the current execution context."""
    _active_dynamic_handler.set(dynamic_handler)
    return dynamic_handler
