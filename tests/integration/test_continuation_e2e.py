from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from quran_mcp.lib.config.settings import get_settings


def _skip_unless_goodmem():
    settings = get_settings()
    if not settings.goodmem.api_key.get_secret_value():
        pytest.skip("requires GoodMem API key")


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_quran_continuation_round_trip(mcp_client):
    p1 = await mcp_client.call_tool("fetch_quran", {"ayahs": "2:1-50"})
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("2:1-50 fits in a single page")

    token = p1_data["pagination"]["continuation"]
    assert token is not None

    p2 = await mcp_client.call_tool("fetch_quran", {"continuation": token})
    p2_data = p2.structured_content

    p1_ayahs = set(p1_data["ayahs"])
    p2_ayahs = set(p2_data["ayahs"])
    assert p1_ayahs.isdisjoint(p2_ayahs)
    assert len(p2_ayahs) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_translation_continuation_round_trip(mcp_client):
    p1 = await mcp_client.call_tool(
        "fetch_translation", {"ayahs": "2:1-50", "editions": "en-abdel-haleem"}
    )
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("2:1-50 fits in a single page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("fetch_translation", {"continuation": token})
    p2_data = p2.structured_content

    p1_ayahs = set(p1_data["ayahs"])
    p2_ayahs = set(p2_data["ayahs"])
    assert p1_ayahs.isdisjoint(p2_ayahs)
    assert len(p2_ayahs) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_search_quran_continuation_round_trip(mcp_client):
    _skip_unless_goodmem()

    p1 = await mcp_client.call_tool(
        "search_quran", {"query": "mercy and forgiveness"}
    )
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("search_quran returned all results in one page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("search_quran", {"continuation": token})
    p2_data = p2.structured_content

    p1_keys = {r["ayah_key"] for r in p1_data["results"]}
    p2_keys = {r["ayah_key"] for r in p2_data["results"]}
    assert p1_keys.isdisjoint(p2_keys)
    assert len(p2_data["results"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_search_translation_continuation_round_trip(mcp_client):
    _skip_unless_goodmem()

    p1 = await mcp_client.call_tool(
        "search_translation", {"query": "patience in adversity"}
    )
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("search_translation returned all results in one page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("search_translation", {"continuation": token})
    p2_data = p2.structured_content

    p1_keys = {(r["ayah_key"], r["edition"]["edition_id"]) for r in p1_data["results"]}
    p2_keys = {(r["ayah_key"], r["edition"]["edition_id"]) for r in p2_data["results"]}
    assert p1_keys.isdisjoint(p2_keys)
    assert len(p2_data["results"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_search_tafsir_continuation_round_trip(mcp_client):
    _skip_unless_goodmem()

    p1 = await mcp_client.call_tool(
        "search_tafsir", {"query": "throne verse explanation"}
    )
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("search_tafsir returned all results in one page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("search_tafsir", {"continuation": token})
    p2_data = p2.structured_content

    p1_keys = {(r["ayah_key"], r["citation"]["edition_id"]) for r in p1_data["results"]}
    p2_keys = {(r["ayah_key"], r["citation"]["edition_id"]) for r in p2_data["results"]}
    assert p1_keys.isdisjoint(p2_keys)
    assert len(p2_data["results"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_exhausted_continuation_walks_to_end(mcp_client):
    p1 = await mcp_client.call_tool("fetch_quran", {"ayahs": "2:1-50"})
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("2:1-50 fits in a single page")

    # Walk pages until exhausted
    current = p1_data
    seen_ayahs = set(current["ayahs"])
    while current["pagination"]["has_more"]:
        token = current["pagination"]["continuation"]
        result = await mcp_client.call_tool("fetch_quran", {"continuation": token})
        current = result.structured_content
        new_ayahs = set(current["ayahs"])
        assert seen_ayahs.isdisjoint(new_ayahs)
        seen_ayahs.update(new_ayahs)

    # Now we're on the last page — continuation should be None
    assert current["pagination"]["continuation"] is None
    assert current["pagination"]["has_more"] is False


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_tafsir_continuation_preserves_edition(mcp_client):
    requested_editions = {"en-ibn-kathir", "ar-tabari"}
    p1 = await mcp_client.call_tool(
        "fetch_tafsir",
        {"ayahs": "2:1-20", "editions": list(requested_editions)},
    )
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("fetch_tafsir 2:1-20 with two editions fits in one page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("fetch_tafsir", {"continuation": token})
    p2_data = p2.structured_content

    p2_editions = set(p2_data["results"].keys())
    assert p2_editions, "Page 2 must have at least one edition"
    assert p2_editions.issubset(requested_editions)

    p1_ayahs = set(p1_data["ayahs"])
    p2_ayahs = set(p2_data["ayahs"])
    assert p1_ayahs.isdisjoint(p2_ayahs)

    # Page 2 metadata must be correct
    assert isinstance(p2_data["pagination"]["has_more"], bool)
    assert p2_data["pagination"]["total_items"] > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_page2_pagination_metadata_correct(mcp_client):
    p1 = await mcp_client.call_tool("fetch_quran", {"ayahs": "2:1-50"})
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("2:1-50 fits in a single page")

    token = p1_data["pagination"]["continuation"]
    p2 = await mcp_client.call_tool("fetch_quran", {"continuation": token})
    p2_data = p2.structured_content

    assert "has_more" in p2_data["pagination"]
    assert "total_items" in p2_data["pagination"]
    assert isinstance(p2_data["pagination"]["has_more"], bool)
    assert p2_data["pagination"]["total_items"] == p1_data["pagination"]["total_items"]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_continuation_token_raises_tool_error(mcp_client):
    with pytest.raises(ToolError, match="(?i)continuation"):
        await mcp_client.call_tool(
            "fetch_quran", {"continuation": "not-a-valid-token.garbage"}
        )


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_wrong_tool_continuation_raises_tool_error(mcp_client):
    p1 = await mcp_client.call_tool("fetch_quran", {"ayahs": "2:1-50"})
    p1_data = p1.structured_content

    if not p1_data["pagination"]["has_more"]:
        pytest.skip("2:1-50 fits in a single page")

    token = p1_data["pagination"]["continuation"]
    with pytest.raises(ToolError, match="(?i)continuation"):
        await mcp_client.call_tool("fetch_translation", {"continuation": token})
