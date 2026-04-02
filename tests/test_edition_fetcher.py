from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.editions.fetcher import EditionFetcher, EditionFetcherConfig
from quran_mcp.lib.editions.fetcher.base import _build_ayah_conditions
from quran_mcp.lib.editions.fetcher.goodmem import _build_edition_filter


@dataclass
class MockMemory:
    content: str
    metadata: dict


def _entry_factory(ayah: str, text: str, meta: dict) -> dict:
    return {"ayah": ayah, "text": text}


def _make_config(**overrides) -> EditionFetcherConfig:
    defaults = dict(
        edition_type="quran",
        goodmem_space="quran",
        entry_factory=_entry_factory,
    )
    defaults.update(overrides)
    return EditionFetcherConfig(**defaults)


def _make_ctx(memories: list[MockMemory] | None = None) -> AppContext:
    if memories is None:
        return AppContext(goodmem_cli=None)
    mock_goodmem = AsyncMock()
    mock_goodmem.search_memories = AsyncMock(return_value=memories)
    return AppContext(goodmem_cli=mock_goodmem)


# ---------------------------------------------------------------------------
# _build_ayah_conditions
# ---------------------------------------------------------------------------


def test_build_ayah_conditions_consecutive_range():
    conditions = _build_ayah_conditions(["2:255", "2:256", "2:257"])
    assert len(conditions) == 1
    assert ">= 255" in conditions[0]
    assert "<= 257" in conditions[0]


def test_build_ayah_conditions_single_ayah():
    conditions = _build_ayah_conditions(["2:255"])
    assert len(conditions) == 1
    assert "= 255" in conditions[0]
    assert ">=" not in conditions[0]


def test_build_ayah_conditions_non_consecutive():
    conditions = _build_ayah_conditions(["2:255", "2:260"])
    assert len(conditions) == 2


def test_build_ayah_conditions_cross_surah():
    conditions = _build_ayah_conditions(["2:255", "2:256", "3:1", "3:2"])
    assert len(conditions) == 2


def test_build_ayah_conditions_empty():
    assert _build_ayah_conditions([]) == []


# ---------------------------------------------------------------------------
# _build_edition_filter
# ---------------------------------------------------------------------------


def test_build_edition_filter_includes_edition_type_and_id():
    config = _make_config(edition_type="tafsir")
    result = _build_edition_filter(config, "en-ibn-kathir", ["2:255"])
    assert "tafsir" in result
    assert "en-ibn-kathir" in result


def test_build_edition_filter_empty_ayahs():
    config = _make_config()
    result = _build_edition_filter(config, "ar-uthmani", [])
    assert "ar-uthmani" in result
    assert "OR" not in result


# ---------------------------------------------------------------------------
# fetch — happy path
# ---------------------------------------------------------------------------


async def test_fetch_single_ayah():
    memories = [
        MockMemory(content="Bismillah", metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    fetcher = EditionFetcher(_make_config())
    result = await fetcher.fetch(ctx, "1:1", "ar-uthmani")
    assert "ar-uthmani" in result.data
    assert len(result.data["ar-uthmani"]) == 1
    assert result.data["ar-uthmani"][0]["ayah"] == "1:1"
    assert result.data["ar-uthmani"][0]["text"] == "Bismillah"
    assert result.gaps is None


async def test_fetch_range_returns_entries_in_order():
    memories = [
        MockMemory(content="v257", metadata={"ayah_key": "2:257", "edition_id": "ar-uthmani", "edition_type": "quran"}),
        MockMemory(content="v255", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"}),
        MockMemory(content="v256", metadata={"ayah_key": "2:256", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    fetcher = EditionFetcher(_make_config())
    result = await fetcher.fetch(ctx, "2:255-257", "ar-uthmani")
    ayahs = [e["ayah"] for e in result.data["ar-uthmani"]]
    assert ayahs == ["2:255", "2:256", "2:257"]


# ---------------------------------------------------------------------------
# fetch — partial results / gaps
# ---------------------------------------------------------------------------


async def test_fetch_partial_results_with_gaps():
    memories = [
        MockMemory(content="text-a", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    config = _make_config()
    fetcher = EditionFetcher(config)
    result = await fetcher.fetch(ctx, ["2:255", "2:256"], ["ar-uthmani"])
    assert "ar-uthmani" in result.data
    assert len(result.data["ar-uthmani"]) == 1
    assert result.gaps is not None
    assert any(g.edition_id == "ar-uthmani" and "2:256" in g.missing_ayahs for g in result.gaps)


async def test_fetch_one_edition_full_one_empty():
    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [MockMemory(content="found", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"})]
        return []

    mock_goodmem = AsyncMock()
    mock_goodmem.search_memories = AsyncMock(side_effect=_side_effect)
    ctx = AppContext(goodmem_cli=mock_goodmem)
    fetcher = EditionFetcher(_make_config())
    result = await fetcher.fetch(ctx, "2:255", ["ar-uthmani", "ar-simple"])
    assert "ar-uthmani" in result.data
    assert "ar-simple" not in result.data
    assert result.gaps is not None
    assert any(g.edition_id == "ar-simple" for g in result.gaps)


# ---------------------------------------------------------------------------
# fetch — error paths
# ---------------------------------------------------------------------------


async def test_fetch_all_editions_missing_raises_data_not_found():
    ctx = _make_ctx(memories=[])
    fetcher = EditionFetcher(_make_config())
    with pytest.raises(DataNotFoundError):
        await fetcher.fetch(ctx, "2:255", "ar-uthmani")


async def test_fetch_exceeding_max_ayahs_raises_value_error():
    ctx = _make_ctx(memories=[])
    fetcher = EditionFetcher(_make_config())
    ayahs = [f"2:{i}" for i in range(1, 302)]
    with pytest.raises(ValueError, match="300"):
        await fetcher.fetch(ctx, ayahs, "ar-uthmani")


async def test_fetch_no_goodmem_client_raises_data_store_error():
    ctx = _make_ctx(None)
    fetcher = EditionFetcher(_make_config())
    with pytest.raises(DataStoreError):
        await fetcher.fetch(ctx, "2:255", "ar-uthmani")


async def test_fetch_goodmem_exception_raises_data_store_error():
    mock_goodmem = AsyncMock()
    mock_goodmem.search_memories = AsyncMock(side_effect=RuntimeError("connection lost"))
    ctx = AppContext(goodmem_cli=mock_goodmem)
    fetcher = EditionFetcher(_make_config())
    with pytest.raises(DataStoreError, match="connection lost"):
        await fetcher.fetch(ctx, "2:255", "ar-uthmani")


# ---------------------------------------------------------------------------
# fetch — unresolved editions
# ---------------------------------------------------------------------------


async def test_fetch_unresolved_edition_tracked():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    fetcher = EditionFetcher(_make_config())
    result = await fetcher.fetch(ctx, "2:255", ["ar-uthmani", "nonexistent-xyz-123"])
    assert result.unresolved is not None
    assert any(u.selector == "nonexistent-xyz-123" for u in result.unresolved)


async def test_fetch_all_unresolved_returns_empty_data():
    ctx = _make_ctx(memories=[])
    fetcher = EditionFetcher(_make_config())
    result = await fetcher.fetch(ctx, "2:255", "xyz")
    assert result.data == {}
    assert result.unresolved is not None
