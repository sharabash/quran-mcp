from __future__ import annotations

from quran_mcp.lib.config.profiles import resolve_active_tags, resolve_relay_enabled
from quran_mcp.lib.config.settings import Settings


def test_expose_tags_override_profile_defaults() -> None:
    settings = Settings(
        server={"profile": "public", "expose_tags": ["ga", "preview"]},
        relay={"enabled": None},
    )

    assert resolve_active_tags(settings) == {"ga", "preview"}
    assert resolve_relay_enabled(settings) is True


def test_public_profile_without_expose_tags_disables_relay() -> None:
    settings = Settings(
        server={"profile": "public", "expose_tags": None},
        relay={"enabled": None},
    )

    assert resolve_active_tags(settings) == {"ga"}
    assert resolve_relay_enabled(settings) is False


def test_full_profile_without_explicit_relay_keeps_everything_visible() -> None:
    settings = Settings(
        server={"profile": "full", "expose_tags": None},
        relay={"enabled": None},
    )

    assert resolve_active_tags(settings) is None
    assert resolve_relay_enabled(settings) is True


def test_explicit_relay_setting_wins_over_profile_and_tags() -> None:
    settings = Settings(
        server={"profile": "public", "expose_tags": ["ga"]},
        relay={"enabled": True},
    )

    assert resolve_active_tags(settings) == {"ga"}
    assert resolve_relay_enabled(settings) is True
