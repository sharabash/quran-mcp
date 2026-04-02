"""Centralized asset path resolution and text loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ASSETS_DIR: Path = Path(__file__).resolve().parent.parent / "assets"
_GROUNDING_RULES_FALLBACK = "(file not found: GROUNDING_RULES.md)"
_SKILL_GUIDE_FALLBACK = "(file not found: SKILL.md)"


def asset_path(name: str) -> Path:
    """Return the absolute path to an asset file."""
    return _ASSETS_DIR / name


@lru_cache(maxsize=32)
def asset_text(name: str, *, fallback: str | None = None) -> str:
    """Load an asset file as UTF-8 text, with optional fallback.

    Results are cached so the same file is only read once per process.
    """
    p = _ASSETS_DIR / name
    if p.is_file():
        return p.read_text(encoding="utf-8")
    if fallback is not None:
        return fallback
    raise FileNotFoundError(f"Asset not found: {p}")


def grounding_rules_markdown() -> str:
    """Load the grounding rules markdown."""
    return asset_text("GROUNDING_RULES.md", fallback=_GROUNDING_RULES_FALLBACK)


def skill_guide_markdown() -> str:
    """Load the skill guide markdown."""
    return asset_text("SKILL.md", fallback=_SKILL_GUIDE_FALLBACK)
