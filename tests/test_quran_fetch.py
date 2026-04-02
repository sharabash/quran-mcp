from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.quran.fetch import (
    QuranEntry,
    QuranFetchResult,
    fetch_quran,
    resolve_quran_edition_ids,
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


# ---------------------------------------------------------------------------
# resolve_quran_edition_ids (static registry, no mocking needed)
# ---------------------------------------------------------------------------


def test_resolve_by_exact_id():
    result = resolve_quran_edition_ids("ar-uthmani")
    assert "ar-uthmani" in result


def test_resolve_by_code():
    result = resolve_quran_edition_ids("uthmani")
    assert "ar-uthmani" in result


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve_quran_edition_ids("nonexistent-quran-xyz-999")


# ---------------------------------------------------------------------------
# fetch_quran — happy path
# ---------------------------------------------------------------------------


async def test_fetch_single_ayah():
    memories = [
        MockMemory(
            content="Bismillah ar-Rahman ar-Raheem",
            metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"},
        ),
    ]
    ctx = _make_ctx(memories)
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        result = await fetch_quran(ctx, "1:1", "ar-uthmani")
    assert isinstance(result, QuranFetchResult)
    assert "ar-uthmani" in result.data
    entry = result.data["ar-uthmani"][0]
    assert isinstance(entry, QuranEntry)
    assert entry.ayah == "1:1"
    assert entry.text == "Bismillah ar-Rahman ar-Raheem"


async def test_fetch_range_returns_sorted_entries():
    memories = [
        MockMemory(content="v3", metadata={"ayah_key": "1:3", "edition_id": "ar-uthmani", "edition_type": "quran"}),
        MockMemory(content="v1", metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"}),
        MockMemory(content="v2", metadata={"ayah_key": "1:2", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        result = await fetch_quran(ctx, "1:1-3", "ar-uthmani")
    ayahs = [e.ayah for e in result.data["ar-uthmani"]]
    assert ayahs == ["1:1", "1:2", "1:3"]


# ---------------------------------------------------------------------------
# fetch_quran — gaps
# ---------------------------------------------------------------------------


async def test_fetch_missing_data_returns_gaps():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        result = await fetch_quran(ctx, "2:255-256", "ar-uthmani")
    assert result.gaps is not None
    assert "2:256" in result.gaps[0].missing_ayahs


# ---------------------------------------------------------------------------
# fetch_quran — error paths
# ---------------------------------------------------------------------------


async def test_fetch_all_missing_raises_data_not_found():
    ctx = _make_ctx(memories=[])
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        with pytest.raises(DataNotFoundError):
            await fetch_quran(ctx, "2:255", "ar-uthmani")


async def test_fetch_exceeding_300_raises_value_error():
    ctx = _make_ctx(memories=[])
    ayahs = [f"2:{i}" for i in range(1, 302)]
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        with pytest.raises(ValueError, match="300"):
            await fetch_quran(ctx, ayahs, "ar-uthmani")


async def test_fetch_no_goodmem_raises_data_store_error():
    ctx = _make_ctx(None)
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        with pytest.raises(DataStoreError):
            await fetch_quran(ctx, "2:255", "ar-uthmani")


# ---------------------------------------------------------------------------
# fetch_quran — unresolved editions
# ---------------------------------------------------------------------------


async def test_fetch_unresolved_edition_tracked():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ]
    ctx = _make_ctx(memories)
    with patch("quran_mcp.lib.quran.fetch._get_config") as mock_cfg:
        from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
        mock_cfg.return_value = EditionFetcherConfig(
            edition_type="quran",
            goodmem_space="quran",
            entry_factory=lambda ayah, text, meta: QuranEntry(ayah=ayah, text=text),
        )
        result = await fetch_quran(ctx, "2:255", ["ar-uthmani", "nonexistent-xyz-123"])
    assert result.unresolved is not None
    assert any(u.selector == "nonexistent-xyz-123" for u in result.unresolved)
