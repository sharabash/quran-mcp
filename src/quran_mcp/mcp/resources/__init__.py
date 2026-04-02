"""Helpers for registering the reusable core MCP resource surface."""

from __future__ import annotations

from collections.abc import Iterable

from fastmcp import FastMCP

from quran_mcp.mcp.resources.app import mushaf as mushaf_resource
from quran_mcp.mcp.resources.doc import grounding_rules as grounding_rules_resource
from quran_mcp.mcp.resources.doc import skill_guide as skill_guide_resource

_GA_RESOURCE_MODULES = (
    grounding_rules_resource,
    skill_guide_resource,
)

_NON_GA_RESOURCE_MODULES = (
    mushaf_resource,
)


def _register_modules(mcp: FastMCP, modules: Iterable[object]) -> None:
    for module in modules:
        module.register(mcp)


def register_all_core_resources(mcp: FastMCP, *, include_non_ga: bool = True) -> None:
    """Register the reusable first-party resource surface on ``mcp``."""

    _register_modules(mcp, _GA_RESOURCE_MODULES)
    if include_non_ga:
        _register_modules(mcp, _NON_GA_RESOURCE_MODULES)


__all__ = ["register_all_core_resources"]
