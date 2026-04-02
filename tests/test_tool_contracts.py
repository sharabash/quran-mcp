from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from quran_mcp.mcp.tools import register_all_core_tools

EXPECTED_TOOL_COUNT = 15

ANNOTATION_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

GATED_TOOLS = (
    "fetch_quran",
    "fetch_translation",
    "fetch_tafsir",
    "search_quran",
    "search_translation",
    "search_tafsir",
)

SEARCH_TOOLS = (
    "search_quran",
    "search_translation",
    "search_tafsir",
)

FETCH_TOOLS = (
    "fetch_quran",
    "fetch_translation",
    "fetch_tafsir",
)

RESOURCE_CONTRACT_TOOLS = (
    "fetch_quran_metadata",
    "fetch_word_morphology",
    "fetch_word_paradigm",
    "fetch_word_concordance",
)

TOOLS_WITHOUT_OUTPUT_SCHEMA = {
    "fetch_grounding_rules",
    "show_mushaf",
    "fetch_mushaf",
}


@pytest.fixture()
def mcp() -> FastMCP:
    server = FastMCP("contract-test")
    register_all_core_tools(server)
    return server


@pytest.mark.asyncio
async def test_tool_count(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert len(tools) == EXPECTED_TOOL_COUNT


@pytest.mark.asyncio
async def test_no_duplicate_tool_names(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_all_tools_have_annotations(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        assert tool.annotations is not None, f"{tool.name} missing annotations"
        for hint in ANNOTATION_HINTS:
            value = getattr(tool.annotations, hint)
            assert value is not None, f"{tool.name} missing {hint}"


@pytest.mark.asyncio
async def test_ga_tools_have_version(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        meta = tool.meta or {}
        fastmcp = meta.get("fastmcp", {})
        tags = fastmcp.get("tags", [])
        if "ga" not in tags:
            continue
        version = fastmcp.get("version")
        assert version is not None, f"{tool.name} tagged ga but missing version"
        assert isinstance(version, str), f"{tool.name} version must be a string"


@pytest.mark.asyncio
async def test_gated_tools_mention_prerequisite(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in GATED_TOOLS:
        tool = by_name[name]
        desc = tool.description or ""
        assert "PREREQUISITE" in desc, f"{name} description missing PREREQUISITE"
        assert "fetch_grounding_rules" in desc, (
            f"{name} description missing fetch_grounding_rules reference"
        )


@pytest.mark.asyncio
async def test_search_tools_publish_failure_contract(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in SEARCH_TOOLS:
        desc = by_name[name].description or ""
        assert "[invalid_request]" in desc, f"{name} missing invalid_request contract"
        assert "[search_backend_failure]" in desc, (
            f"{name} missing search_backend_failure contract"
        )


@pytest.mark.asyncio
async def test_fetch_tools_publish_not_found_contract(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in FETCH_TOOLS:
        desc = by_name[name].description or ""
        assert "[invalid_request]" in desc, f"{name} missing invalid_request contract"
        assert "[not_found]" in desc, f"{name} missing not_found contract"
        assert "[service_unavailable]" in desc, f"{name} missing service_unavailable contract"


@pytest.mark.asyncio
async def test_resource_tools_publish_failure_contract(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in RESOURCE_CONTRACT_TOOLS:
        desc = by_name[name].description or ""
        assert "[invalid_request]" in desc, f"{name} missing invalid_request contract"
        assert "[service_unavailable]" in desc, (
            f"{name} missing service_unavailable contract"
        )


@pytest.mark.asyncio
async def test_output_schemas_present(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        if tool.name in TOOLS_WITHOUT_OUTPUT_SCHEMA:
            continue
        assert tool.outputSchema is not None, f"{tool.name} missing outputSchema"


@pytest.mark.asyncio
async def test_fetch_tafsir_editions_required(mcp: FastMCP):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    # fetch_tafsir's editions param must NOT mention a default (it's required)
    tafsir = by_name["fetch_tafsir"]
    tafsir_desc = tafsir.inputSchema["properties"]["editions"]["description"].lower()
    assert "defaults to" not in tafsir_desc, (
        "fetch_tafsir editions should not have a default — it's required"
    )
    # fetch_quran and fetch_translation have edition defaults
    for name in ("fetch_quran", "fetch_translation"):
        tool = by_name[name]
        desc = tool.inputSchema["properties"]["editions"]["description"].lower()
        assert "defaults to" in desc, (
            f"{name} editions parameter should mention a default"
        )
