from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_surah_ikhlas_returns_ibn_kathir_commentary(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_tafsir", {"ayahs": "112:1", "editions": "en-ibn-kathir"}
    )
    payload = result.structured_content

    entries = payload["results"]["en-ibn-kathir"]
    assert len(entries) >= 1

    first = entries[0]
    assert "112:1" in first["ayahs"]
    assert len(first["text"]) > 20


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_tafsir_text_is_non_empty(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_tafsir", {"ayahs": "2:255", "editions": "en-ibn-kathir"}
    )
    payload = result.structured_content

    entries = payload["results"]["en-ibn-kathir"]
    assert entries
    for entry in entries:
        assert entry["text"].strip()
        assert entry["range"]
        assert entry["ayahs"]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_tafsir_dedup_collapses_grouped_verses(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_tafsir", {"ayahs": "31:13-15", "editions": "en-ibn-kathir"}
    )
    payload = result.structured_content

    entries = payload["results"]["en-ibn-kathir"]
    total_ayahs_covered = sum(len(e["ayahs"]) for e in entries)
    assert total_ayahs_covered >= 3
    # Dedup must collapse 3 ayahs into fewer entries
    assert len(entries) < 3, f"Expected dedup to collapse 3 ayahs, got {len(entries)} entries"
    # At least one entry must span multiple ayahs
    multi = [e for e in entries if len(e["ayahs"]) > 1]
    assert len(multi) >= 1, "Expected at least one multi-ayah entry from dedup"
    assert "-" in multi[0]["range"]
