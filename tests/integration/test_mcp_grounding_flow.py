from __future__ import annotations

import re

import pytest

from quran_mcp.lib.config.settings import get_settings

_NONCE_RE = re.compile(r"GROUNDING_NONCE:\s*(gnd-[A-Za-z0-9]+)")


def _extract_nonce(result) -> str:
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            match = _NONCE_RE.search(text)
            if match is not None:
                return match.group(1)
    raise AssertionError("fetch_grounding_rules did not return a grounding nonce")


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_grounded_nonce_flow_fetches_and_searches_translation(mcp_client) -> None:
    settings = get_settings()
    if not settings.goodmem.api_key.get_secret_value():
        pytest.skip("live MCP integration requires GOODMEM_API_KEY")

    tool_names = {tool.name for tool in await mcp_client.list_tools()}
    assert {
        "fetch_grounding_rules",
        "list_editions",
        "fetch_translation",
        "search_translation",
    } <= tool_names

    grounding_rules = await mcp_client.call_tool("fetch_grounding_rules", {})
    nonce = _extract_nonce(grounding_rules)

    editions = await mcp_client.call_tool(
        "list_editions",
        {"edition_type": "tafsir", "grounding_nonce": nonce},
    )
    editions_payload = editions.structured_content

    translation = await mcp_client.call_tool(
        "fetch_translation",
        {
            "ayahs": "2:255",
            "editions": "en-abdel-haleem",
            "grounding_nonce": nonce,
        },
    )
    translation_payload = translation.structured_content

    search = await mcp_client.call_tool(
        "search_translation",
        {
            "query": "the Ever-Living, the Sustainer",
            "grounding_nonce": nonce,
        },
    )
    search_payload = search.structured_content

    assert nonce.startswith("gnd-")

    assert editions_payload["edition_types"] == ["tafsir"]
    assert editions_payload["editions"]
    assert editions_payload["grounding_rules"] is None

    entries = translation_payload["results"]["en-abdel-haleem"]
    assert entries
    assert entries[0]["ayah"] == "2:255"
    assert translation_payload["grounding_rules"] is None
    assert translation_payload["warnings"] is None

    assert search_payload["results"]
    assert search_payload["results"][0]["ayah_key"] == "2:255"
    assert search_payload["grounding_rules"] is None
