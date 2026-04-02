from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_ayat_al_kursi_returns_translation(mcp_client):
    result = await mcp_client.call_tool("fetch_translation", {"ayahs": "2:255"})
    payload = result.structured_content

    entries = payload["results"]["en-abdel-haleem"]
    assert len(entries) == 1
    assert entries[0]["ayah"] == "2:255"
    assert entries[0]["text"].strip()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_default_edition_is_en_abdel_haleem(mcp_client):
    result = await mcp_client.call_tool("fetch_translation", {"ayahs": "1:1"})
    payload = result.structured_content

    assert "en-abdel-haleem" in payload["results"]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_translation_text_is_non_empty_english(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_translation", {"ayahs": "2:255", "editions": "en-abdel-haleem"}
    )
    payload = result.structured_content

    text = payload["results"]["en-abdel-haleem"][0]["text"]
    assert len(text) > 50
    # Ayat al-Kursi translation must contain recognizable English words
    text_lower = text.lower()
    assert "god" in text_lower or "allah" in text_lower or "throne" in text_lower
