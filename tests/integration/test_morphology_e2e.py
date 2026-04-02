from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_morphology_known_verse(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_morphology", {"ayah_key": "2:255", "word_position": 1}
    )
    payload = result.structured_content

    assert payload["ayah_key"] == "2:255"
    words = payload["words"]
    assert len(words) == 1

    word = words[0]
    assert word["position"] == 1
    assert word["text_uthmani"].strip()
    assert word["root"] is not None
    assert word["lemma"] is not None
    assert word["grammatical_features"] is not None
    assert "part_of_speech" in word["grammatical_features"]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_morphology_full_verse(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_morphology", {"ayah_key": "1:1"}
    )
    payload = result.structured_content

    assert payload["ayah_key"] == "1:1"
    words = payload["words"]
    assert len(words) >= 3

    for word in words:
        assert word["text_uthmani"].strip()
        assert word["position"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_morphology_by_word(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_morphology", {"word": "\u0627\u0644\u0644\u0651\u064e\u0647\u0650"}
    )
    payload = result.structured_content

    assert payload["ayah_key"]
    assert payload["input_mode"] == "word_text"
    words = payload["words"]
    assert len(words) >= 1
    assert payload["other_occurrences_count"] is not None
    assert payload["other_occurrences_count"] > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_paradigm_for_verb(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_paradigm", {"ayah_key": "2:255", "word_position": 7}
    )
    payload = result.structured_content

    if payload["paradigm_available"]:
        assert payload["paradigm"] is not None
        assert isinstance(payload["paradigm"], dict)
        assert payload["root"] is not None
        assert payload["lemma"] is not None
    else:
        assert payload["paradigm_unavailable_reason"] is not None


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_paradigm_for_non_verb(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_paradigm", {"ayah_key": "1:1", "word_position": 1}
    )
    payload = result.structured_content

    assert payload["paradigm_available"] is False
    assert payload["paradigm_unavailable_reason"] is not None


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_concordance_known_root(mcp_client):
    result = await mcp_client.call_tool(
        "fetch_word_concordance",
        {"root": "\u0643 \u062a \u0628", "rerank_from": "false"},
    )
    payload = result.structured_content

    assert payload["total_verses"] > 0
    assert payload["match_by"] in ("all", "root")

    results = payload["results"]
    assert len(results) > 0

    first = results[0]
    assert first["ayah_key"]
    assert first["verse_text"].strip()
    assert len(first["matched_words"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_word_concordance_pagination(mcp_client):
    page1 = await mcp_client.call_tool(
        "fetch_word_concordance",
        {"root": "\u0643 \u062a \u0628", "page": 1, "page_size": 3, "rerank_from": "false"},
    )
    page2 = await mcp_client.call_tool(
        "fetch_word_concordance",
        {"root": "\u0643 \u062a \u0628", "page": 2, "page_size": 3, "rerank_from": "false"},
    )
    p1 = page1.structured_content
    p2 = page2.structured_content

    assert p1["page"] == 1
    assert p2["page"] == 2
    assert p1["page_size"] == 3
    assert p2["page_size"] == 3
    assert len(p1["results"]) == 3

    p1_keys = {r["ayah_key"] for r in p1["results"]}
    p2_keys = {r["ayah_key"] for r in p2["results"]}
    assert p1_keys.isdisjoint(p2_keys)
