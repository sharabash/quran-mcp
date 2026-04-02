"""Runtime ownership seam for the public documentation feature."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quran_mcp.lib.assets import asset_path

if TYPE_CHECKING:
    from fastmcp import FastMCP

_DOCS_STATE_ATTR = "_quran_mcp_docs_runtime_state"


@dataclass
class DocumentationRuntimeState:
    """Per-server runtime state for documentation rendering."""

    json_cache: tuple[tuple[str, ...], str] | None = None


def build_documentation_runtime_state() -> DocumentationRuntimeState:
    """Create an isolated documentation runtime state container."""
    return DocumentationRuntimeState()


def documentation_page_path() -> Path:
    """Return the built documentation SPA shell path."""
    return asset_path("documentation.html")


def documentation_usage_examples_dir() -> Path:
    """Return the docs-owned example asset directory."""
    return Path(__file__).resolve().parent / "data" / "usage-examples"


def get_or_create_documentation_runtime_state(mcp: "FastMCP") -> DocumentationRuntimeState:
    """Return per-server documentation runtime state, creating it on first access."""
    state = getattr(mcp, _DOCS_STATE_ATTR, None)
    if state is None:
        state = build_documentation_runtime_state()
        setattr(mcp, _DOCS_STATE_ATTR, state)
    return state
