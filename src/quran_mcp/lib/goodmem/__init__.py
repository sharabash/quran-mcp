"""Public GoodMem facade.

This package exposes the adapter surface used by the rest of the codebase
while keeping the low-level SDK wiring, filter DSL, and stream normalization
helpers in bounded submodules.
"""

from __future__ import annotations

from .client import GoodMemClient, GoodMemConfig, GoodMemMemory, with_retry
from .filters import FilterTerm, build_filter_expression, build_metadata_filter_expression, combine_filter_expressions, escape_literal, parse_filter_string
from .sdk import GoodMemSDKClients, build_sdk_clients
from .streaming import normalize_sdk_content, stream_search_memories

__all__ = [
    "GoodMemConfig",
    "GoodMemMemory",
    "GoodMemClient",
    "GoodMemSDKClients",
    "build_sdk_clients",
    "normalize_sdk_content",
    "stream_search_memories",
    "with_retry",
    "FilterTerm",
    "escape_literal",
    "parse_filter_string",
    "build_filter_expression",
    "combine_filter_expressions",
    "build_metadata_filter_expression",
]
