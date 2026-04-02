"""Stable editions package exports."""
from __future__ import annotations

from .loader import load_editions_by_type
from .registry import (
    get_by_edition_id,
    resolve_ids,
    resolve_ids_with_unresolved,
    ResolveResult,
    list_editions,
    list_edition_summaries,
    filter_editions,
    get_edition_list,
)
from .types import (
    EDITION_TYPES,
    EditionInfoRecord,
    EditionRecord,
    EditionType,
    project_edition_info,
    SummaryPromptConfig,
)

from .errors import DataNotFoundError, DataStoreError, DataGap, UnresolvedEdition
from .flags import (
    get_all_flags,
    goodmem_native_override,
    reset_goodmem_native_overrides,
    set_goodmem_native,
    use_goodmem_native,
)

__all__ = [
    # Loader
    "load_editions_by_type",
    # Registry
    "get_by_edition_id",
    "resolve_ids",
    "resolve_ids_with_unresolved",
    "ResolveResult",
    "list_editions",
    "list_edition_summaries",
    "filter_editions",
    "get_edition_list",
    # Types
    "EDITION_TYPES",
    "EditionType",
    "SummaryPromptConfig",
    "EditionRecord",
    "EditionInfoRecord",
    "project_edition_info",
    # Error types and data structures
    "DataNotFoundError",
    "DataStoreError",
    "DataGap",
    "UnresolvedEdition",
    # Feature flags
    "goodmem_native_override",
    "reset_goodmem_native_overrides",
    "use_goodmem_native",
    "set_goodmem_native",
    "get_all_flags",
]
