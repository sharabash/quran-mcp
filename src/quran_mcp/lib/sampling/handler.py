"""Compatibility facade over sampling provider helpers and runtime ownership.

This module is intentionally thin. Runtime construction and provider assembly
live in ``sampling.runtime``; provider adapters and payload helpers live in
``sampling.providers``. Import from here only when an older call site still
expects the pre-split surface.
"""

from __future__ import annotations

from quran_mcp.lib.sampling.providers import (
    AnthropicMessagesSamplingHandler,
    GeminiGenerativeSamplingHandler,
    OpenAIResponsesSamplingHandler,
    OpenRouterChatCompletionsSamplingHandler,
)
from quran_mcp.lib.sampling.runtime import (
    DynamicSamplingHandler,
    HandlerConfig,
    apply_runtime_sampling_overrides,
    build_handler_from_runtime_overrides,
    get_dynamic_handler,
    sampling_handler,
)


__all__ = [
    "AnthropicMessagesSamplingHandler",
    "DynamicSamplingHandler",
    "GeminiGenerativeSamplingHandler",
    "HandlerConfig",
    "OpenAIResponsesSamplingHandler",
    "OpenRouterChatCompletionsSamplingHandler",
    "apply_runtime_sampling_overrides",
    "build_handler_from_runtime_overrides",
    "get_dynamic_handler",
    "sampling_handler",
]
