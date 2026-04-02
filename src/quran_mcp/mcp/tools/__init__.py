"""Helpers for registering the reusable core MCP tool surface."""

from __future__ import annotations

from collections.abc import Iterable

from fastmcp import FastMCP

from quran_mcp.mcp.tools.grounding_rules import fetch as grounding_rules_tool
from quran_mcp.mcp.tools.skill_guide import fetch as skill_guide_tool
from quran_mcp.mcp.tools.editions import list as editions_list_tool
from quran_mcp.mcp.tools.metadata import fetch as metadata_fetch_tool
from quran_mcp.mcp.tools.morphology import concordance as morphology_concordance_tool
from quran_mcp.mcp.tools.morphology import fetch as morphology_fetch_tool
from quran_mcp.mcp.tools.morphology import paradigm as morphology_paradigm_tool
from quran_mcp.mcp.tools.mushaf import fetch as mushaf_fetch_tool
from quran_mcp.mcp.tools.mushaf import show as mushaf_show_tool
from quran_mcp.mcp.tools.quran import fetch as quran_fetch_tool
from quran_mcp.mcp.tools.quran import search as quran_search_tool
from quran_mcp.mcp.tools.tafsir import fetch as tafsir_fetch_tool
from quran_mcp.mcp.tools.tafsir import search as tafsir_search_tool
from quran_mcp.mcp.tools.translation import fetch as translation_fetch_tool
from quran_mcp.mcp.tools.translation import search as translation_search_tool

_GA_TOOL_MODULES = (
    editions_list_tool,
    quran_fetch_tool,
    translation_fetch_tool,
    tafsir_fetch_tool,
    quran_search_tool,
    translation_search_tool,
    tafsir_search_tool,
    skill_guide_tool,
    grounding_rules_tool,
    morphology_fetch_tool,
    morphology_paradigm_tool,
    morphology_concordance_tool,
)

_NON_GA_TOOL_MODULES = (
    mushaf_show_tool,
    mushaf_fetch_tool,
    metadata_fetch_tool,
)


def _register_modules(mcp: FastMCP, modules: Iterable[object]) -> None:
    for module in modules:
        module.register(mcp)


def register_all_core_tools(mcp: FastMCP, *, include_non_ga: bool = True) -> None:
    """Register the reusable first-party tool surface on ``mcp``.

    Relay tools are intentionally excluded. They are registered directly on
    the parent server by the relay composition layer and depend on runtime
    consent/configuration, so they are not part of the reusable core tool
    contract for sibling services such as quran-mcp-auth.
    """

    _register_modules(mcp, _GA_TOOL_MODULES)
    if include_non_ga:
        _register_modules(mcp, _NON_GA_TOOL_MODULES)


__all__ = ["register_all_core_tools"]
