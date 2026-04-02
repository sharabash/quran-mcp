from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.presentation.summary import build_summary_messages_for_sampling
from quran_mcp.lib.translation.fetch import (
    TRANSLATION_SUMMARY_PROMPTS,
    TranslationEntry,
    TranslationFetchResult,
    fetch_translation,
    resolve_translation_edition_ids,
)


@dataclass
class MockMemory:
    content: str
    metadata: dict


def _make_ctx(memories: list[MockMemory] | None = None) -> AppContext:
    if memories is None:
        return AppContext(goodmem_cli=None)
    mock_goodmem = AsyncMock()
    mock_goodmem.search_memories = AsyncMock(return_value=memories)
    return AppContext(goodmem_cli=mock_goodmem)


def _patch_config():
    from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
    return patch(
        "quran_mcp.lib.translation.fetch._get_config",
        return_value=EditionFetcherConfig(
            edition_type="translation",
            goodmem_space="translation",
            entry_factory=lambda ayah_key, text, meta: TranslationEntry(ayah_key=ayah_key, text=text),
        ),
    )


# ---------------------------------------------------------------------------
# resolve_translation_edition_ids (static registry)
# ---------------------------------------------------------------------------


def test_resolve_by_exact_id():
    result = resolve_translation_edition_ids("en-sahih-international")
    assert "en-sahih-international" in result


def test_resolve_by_language():
    result = resolve_translation_edition_ids("en")
    assert len(result) > 0
    assert all("en-" in eid or eid.startswith("en") for eid in result)


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve_translation_edition_ids("nonexistent-translation-xyz-999")


# ---------------------------------------------------------------------------
# fetch_translation — happy path
# ---------------------------------------------------------------------------


async def test_fetch_single_ayah():
    memories = [
        MockMemory(
            content="In the name of Allah",
            metadata={"ayah_key": "1:1", "edition_id": "en-sahih-international", "edition_type": "translation"},
        ),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_translation(ctx, "1:1", "en-sahih-international")
    assert isinstance(result, TranslationFetchResult)
    assert "en-sahih-international" in result.data
    entry = result.data["en-sahih-international"][0]
    assert isinstance(entry, TranslationEntry)
    assert entry.ayah_key == "1:1"
    assert entry.ayah == "1:1"
    assert entry.text == "In the name of Allah"


async def test_fetch_range_returns_sorted_entries():
    memories = [
        MockMemory(content="v3", metadata={"ayah_key": "1:3", "edition_id": "en-sahih-international", "edition_type": "translation"}),
        MockMemory(content="v1", metadata={"ayah_key": "1:1", "edition_id": "en-sahih-international", "edition_type": "translation"}),
        MockMemory(content="v2", metadata={"ayah_key": "1:2", "edition_id": "en-sahih-international", "edition_type": "translation"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_translation(ctx, "1:1-3", "en-sahih-international")
    ayahs = [e.ayah for e in result.data["en-sahih-international"]]
    assert ayahs == ["1:1", "1:2", "1:3"]


# ---------------------------------------------------------------------------
# fetch_translation — gaps
# ---------------------------------------------------------------------------


async def test_fetch_missing_data_returns_gaps():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "en-sahih-international", "edition_type": "translation"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_translation(ctx, "2:255-256", "en-sahih-international")
    assert result.gaps is not None
    assert "2:256" in result.gaps[0].missing_ayahs


# ---------------------------------------------------------------------------
# fetch_translation — error paths
# ---------------------------------------------------------------------------


async def test_fetch_all_missing_raises_data_not_found():
    ctx = _make_ctx(memories=[])
    with _patch_config():
        with pytest.raises(DataNotFoundError):
            await fetch_translation(ctx, "2:255", "en-sahih-international")


async def test_fetch_exceeding_300_raises_value_error():
    ctx = _make_ctx(memories=[])
    ayahs = [f"2:{i}" for i in range(1, 302)]
    with _patch_config():
        with pytest.raises(ValueError, match="300"):
            await fetch_translation(ctx, ayahs, "en-sahih-international")


async def test_fetch_no_goodmem_raises_data_store_error():
    ctx = _make_ctx(None)
    with _patch_config():
        with pytest.raises(DataStoreError):
            await fetch_translation(ctx, "2:255", "en-sahih-international")


# ---------------------------------------------------------------------------
# fetch_translation — unresolved editions
# ---------------------------------------------------------------------------


async def test_fetch_unresolved_edition_tracked():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "en-sahih-international", "edition_type": "translation"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_translation(ctx, "2:255", ["en-sahih-international", "nonexistent-xyz-123"])
    assert result.unresolved is not None
    assert any(u.selector == "nonexistent-xyz-123" for u in result.unresolved)


def test_translation_summary_wrappers_forward_source_names():
    messages = build_summary_messages_for_sampling(
        ayah_key="2:255",
        segments={"en-sahih-international": [{"ayah": "2:255", "text": "Allah - there is no deity..."}]},
        config=TRANSLATION_SUMMARY_PROMPTS,
        sources=["en-sahih-international"],
        source_names={"en-sahih-international": "Sahih International"},
    )

    assert "source_legend: en-sahih-international = Sahih International" in messages[1]["content"]
    assert "--- SOURCE: Sahih International [en-sahih-international] ---" in messages[1]["content"]
