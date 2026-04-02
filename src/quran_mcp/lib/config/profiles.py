"""Profile resolution for server component visibility.

Resolves the active tag set and relay enabled state from settings,
supporting named profiles, explicit tag overrides, and relay switches.
"""

from __future__ import annotations

from quran_mcp.lib.config.settings import Settings

# Profile → lifecycle tag set mapping.
# None means "no filtering" (all components visible).
PROFILES: dict[str, set[str] | None] = {
    "public": {"ga"},
    "dev": {"ga", "preview", "internal"},
    "full": None,
}


def resolve_active_tags(settings: Settings) -> set[str] | None:
    """Resolve the effective tag set from settings.

    Returns:
        A set of lifecycle tags to filter by, or None if no filtering
        should be applied (full profile with no expose_tags override).
    """
    if settings.server.expose_tags:
        return set(settings.server.expose_tags)
    tags = PROFILES.get(settings.server.profile)
    return set(tags) if tags is not None else None


def resolve_relay_enabled(settings: Settings) -> bool:
    """Resolve whether the relay system should be active.

    Uses 3-tier precedence:
    1. Explicit ``relay.enabled`` setting (highest priority)
    2. Derived from effective tag set (``preview`` in tags → ON)
    3. Derived from profile default (``public`` → OFF, others → ON)
    """
    if settings.relay.enabled is not None:
        return settings.relay.enabled
    active_tags = resolve_active_tags(settings)
    if active_tags is None:
        return True  # full profile → relay on
    return "preview" in active_tags
