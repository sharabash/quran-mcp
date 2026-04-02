"""E2E: fetch tools smoke test through full MCP stack.

Verifies that fetch tools return non-empty data after the dispatch
logic change. The data source (DB or GoodMem) depends on what's
loaded in the test environment — these tests do not assert which
backend served the response.
"""
import pytest

pytestmark = pytest.mark.integration


async def test_fetch_quran_returns_data(mcp_client):
    """fetch_quran returns non-empty data for Al-Fatiha ayah 1."""
    result = await mcp_client.call_tool(
        "fetch_quran", {"ayahs": "1:1", "editions": "ar-simple-clean"},
    )
    assert result is not None
    text = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert len(text) > 0


async def test_fetch_translation_returns_data(mcp_client):
    """fetch_translation returns non-empty data for Ayat al-Kursi."""
    result = await mcp_client.call_tool(
        "fetch_translation", {"ayahs": "2:255", "editions": "en-sahih-international"},
    )
    assert result is not None
    text = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert len(text) > 0


async def test_fetch_tafsir_returns_data(mcp_client):
    """fetch_tafsir returns non-empty data for Ibn Kathir on 2:255."""
    result = await mcp_client.call_tool(
        "fetch_tafsir", {"ayahs": "2:255", "editions": "en-ibn-kathir"},
    )
    assert result is not None
    text = result[0].text if hasattr(result[0], "text") else str(result[0])
    assert len(text) > 0
