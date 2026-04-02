from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fatiha_returns_seven_ayahs_with_arabic_text(mcp_client):
    result = await mcp_client.call_tool("fetch_quran", {"ayahs": "1:1-7"})
    payload = result.structured_content

    entries = payload["results"]["ar-simple-clean"]
    assert len(entries) == 7

    ayah_keys = [e["ayah"] for e in entries]
    assert ayah_keys == [f"1:{v}" for v in range(1, 8)]

    for entry in entries:
        assert entry["text"].strip()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_default_edition_is_ar_simple_clean(mcp_client):
    result = await mcp_client.call_tool("fetch_quran", {"ayahs": "2:255"})
    payload = result.structured_content

    assert "ar-simple-clean" in payload["results"]
    entries = payload["results"]["ar-simple-clean"]
    assert len(entries) == 1
    assert entries[0]["ayah"] == "2:255"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_pagination_metadata_present(mcp_client):
    result = await mcp_client.call_tool("fetch_quran", {"ayahs": "1:1-7"})
    payload = result.structured_content

    pagination = payload["pagination"]
    assert "has_more" in pagination
    assert "total_items" in pagination
    assert isinstance(pagination["has_more"], bool)
    assert isinstance(pagination["total_items"], int)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_grounding_rules_present_without_nonce(mcp_client):
    result = await mcp_client.call_tool("fetch_quran", {"ayahs": "112:1"})
    payload = result.structured_content

    rules = payload["grounding_rules"]
    assert isinstance(rules, str)
    assert len(rules) > 100
    assert "grounding" in rules.lower()
    assert "citation" in rules.lower() or "attribute" in rules.lower()
