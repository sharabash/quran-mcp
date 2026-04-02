"""Documentation site data generator — serves /documentation/data.json for the Svelte SPA."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from quran_mcp.lib.documentation.catalog import (
    QUICKSTART_CONFIG,
    QUICKSTART_CONFIG_HTML,
    is_public_docs_tool,
    tool_sort_key,
)
from quran_mcp.lib.documentation.context import (
    build_editions_context,
    build_flat_tools_context,
    build_groups_context,
    build_usage_examples_context,
    load_example_fixtures,
    visible_fixture_subset,
)
from quran_mcp.lib.documentation.runtime import DocumentationRuntimeState
from quran_mcp.lib.editions.loader import load_editions_by_type


async def list_public_docs_tools(mcp: FastMCP) -> list[Any]:
    """Return tools that belong in the public docs regardless of test-only re-enables."""
    tools = await mcp.list_tools()
    return [tool for tool in sorted(tools, key=tool_sort_key) if is_public_docs_tool(tool)]


async def render_docs_json(
    mcp: FastMCP,
    *,
    runtime_state: DocumentationRuntimeState,
) -> str:
    """Return the docs context as a JSON string for the Svelte docs app."""
    tools = await list_public_docs_tools(mcp)
    visible_names = {tool.name for tool in tools}
    fixtures = visible_fixture_subset(load_example_fixtures(), visible_names)

    cache_key = tuple(tool.name for tool in tools)
    if runtime_state.json_cache and runtime_state.json_cache[0] == cache_key:
        return runtime_state.json_cache[1]

    groups = build_groups_context(tools, fixtures)
    flat_tools = build_flat_tools_context(groups)
    edition_groups = build_editions_context()
    usage_examples = build_usage_examples_context(include_showcase_html=True)

    payload = {
        "groups": groups,
        "flat_tools": flat_tools,
        "edition_groups": edition_groups,
        "usage_examples": usage_examples,
        "tool_count": len(tools),
        "group_count": len(groups),
        "tafsir_count": len(load_editions_by_type("tafsir")),
        "quickstart_config": QUICKSTART_CONFIG,
        "quickstart_config_html": QUICKSTART_CONFIG_HTML,
    }
    rendered = json.dumps(payload, ensure_ascii=False)
    runtime_state.json_cache = (cache_key, rendered)
    return rendered


__all__ = [
    "list_public_docs_tools",
    "render_docs_json",
]
