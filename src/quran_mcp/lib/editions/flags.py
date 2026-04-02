"""
Feature flags for GoodMem-native retrieval.

Note: EditionFetcher now uses GoodMem-native retrieval by default.
These flags are retained for potential future use but are currently
always enabled.

Environment Variables:
    GOODMEM_NATIVE_QURAN: Enable for quran (default: true)
    GOODMEM_NATIVE_TAFSIR: Enable for tafsir (default: true)
    GOODMEM_NATIVE_TRANSLATION: Enable for translation (default: true)
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .types import EDITION_TYPES, EditionType

# Env var name mapping for each edition type
_GOODMEM_NATIVE_ENV_VARS: dict[str, str] = {
    "quran": "GOODMEM_NATIVE_QURAN",
    "tafsir": "GOODMEM_NATIVE_TAFSIR",
    "translation": "GOODMEM_NATIVE_TRANSLATION",
}

__all__ = [
    "use_goodmem_native",
    "set_goodmem_native",
    "reset_goodmem_native_overrides",
    "goodmem_native_override",
    "get_all_flags",
]

# Context-local overrides for tests and scoped runtime tweaks.
#
# The previous implementation used a process-wide mutable dict, which could leak
# overrides across unrelated test runs. ContextVar keeps override state local to
# the current execution context while preserving the same public lookup API.
_GOODMEM_NATIVE_OVERRIDES: ContextVar[dict[str, bool] | None] = ContextVar(
    "goodmem_native_overrides",
    default=None,
)


def _get_goodmem_native_overrides() -> dict[str, bool]:
    overrides = _GOODMEM_NATIVE_OVERRIDES.get()
    if overrides is None:
        return {}
    return overrides


def _set_goodmem_native_overrides(overrides: dict[str, bool] | None) -> None:
    _GOODMEM_NATIVE_OVERRIDES.set(None if overrides is None else dict(overrides))


def use_goodmem_native(edition_type: EditionType) -> bool:
    """Check if GoodMem-native retrieval is enabled for edition_type.

    Reads os.environ dynamically on each call so that environment
    changes are reflected without restarting the process.
    Test overrides via set_goodmem_native() take precedence.

    Args:
        edition_type: "quran", "tafsir", or "translation"

    Returns:
        True if GoodMem-native is enabled, False to use cache-aside fallback.
    """
    overrides = _get_goodmem_native_overrides()
    if edition_type in overrides:
        return overrides[edition_type]
    env_var = _GOODMEM_NATIVE_ENV_VARS.get(edition_type)
    if env_var is None:
        return False
    return os.environ.get(env_var, "true").lower() == "true"


def set_goodmem_native(edition_type: EditionType, enabled: bool) -> None:
    """Set feature flag for testing purposes (context-local override).

    Prefer goodmem_native_override() context manager for scoped changes.

    Args:
        edition_type: "quran", "tafsir", or "translation"
        enabled: Whether to enable GoodMem-native retrieval.
    """
    overrides = dict(_get_goodmem_native_overrides())
    overrides[edition_type] = enabled
    _set_goodmem_native_overrides(overrides)


def reset_goodmem_native_overrides(edition_type: EditionType | None = None) -> None:
    """Reset one or all context-local test overrides.

    Args:
        edition_type: Specific edition type to clear. If omitted, clears all
            overrides in the current context.
    """
    overrides = dict(_get_goodmem_native_overrides())
    if edition_type is None:
        overrides.clear()
    else:
        overrides.pop(edition_type, None)
    _set_goodmem_native_overrides(overrides or None)


@contextmanager
def goodmem_native_override(edition_type: EditionType, enabled: bool) -> Iterator[None]:
    """Temporarily override an edition flag in the current context.

    This is the preferred way to scope test-only flag changes because the
    previous value is restored automatically.
    """
    previous = _GOODMEM_NATIVE_OVERRIDES.get()
    overrides = dict(previous) if previous is not None else {}
    overrides[edition_type] = enabled
    token = _GOODMEM_NATIVE_OVERRIDES.set(overrides)
    try:
        yield
    finally:
        _GOODMEM_NATIVE_OVERRIDES.reset(token)


def get_all_flags() -> dict[str, bool]:
    """Get a snapshot of all feature flags (for debugging/logging).

    Returns:
        Dictionary of edition_type -> enabled status.
    """
    return {edition_type: use_goodmem_native(edition_type) for edition_type in EDITION_TYPES}
