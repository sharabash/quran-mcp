"""Dispatch tests for EditionFetcher — DB first, GoodMem fallback, error."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.editions.errors import DataStoreError
from quran_mcp.lib.editions.fetcher import EditionFetcher, EditionFetcherConfig
import quran_mcp.lib.editions.fetcher.db as db_mod


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


def _mock_fetch_from_db(results: dict[str, dict[str, tuple[str, dict]] | None]):
    """Create a mock for fetch_from_db that returns per-edition results.

    results: mapping of edition_id -> return value (dict or None).
    """
    async def _mock(pool, edition_type, edition_id, ayah_list):
        return results.get(edition_id)
    return _mock


def _make_goodmem_ctx(memories: list[MockMemory]) -> AsyncMock:
    mock = AsyncMock()
    mock.search_memories = AsyncMock(return_value=memories)
    return mock


# ---------------------------------------------------------------------------
# DB has data → DB used, GoodMem NOT called
# ---------------------------------------------------------------------------


async def test_db_has_data_uses_db_skips_goodmem(monkeypatch):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": {"1:1": ("Bismillah", {"ayah_key": "1:1"})}}),
    )
    mock_goodmem = _make_goodmem_ctx([])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    result = await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert "ar-uthmani" in result.data
    assert result.data["ar-uthmani"][0]["text"] == "Bismillah"
    mock_goodmem.search_memories.assert_not_called()


# ---------------------------------------------------------------------------
# DB returns None → GoodMem fallback
# ---------------------------------------------------------------------------


async def test_db_no_data_falls_back_to_goodmem(monkeypatch):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": None}),
    )
    mock_goodmem = _make_goodmem_ctx([
        MockMemory(content="Bismillah", metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    result = await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert "ar-uthmani" in result.data
    assert result.data["ar-uthmani"][0]["text"] == "Bismillah"
    mock_goodmem.search_memories.assert_called_once()


# ---------------------------------------------------------------------------
# DB only (goodmem_cli=None), DB has data → works
# ---------------------------------------------------------------------------


async def test_db_only_no_goodmem_works(monkeypatch):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": {"1:1": ("Bismillah", {"ayah_key": "1:1"})}}),
    )
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=None)

    result = await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert "ar-uthmani" in result.data


# ---------------------------------------------------------------------------
# GoodMem only (db_pool=None) → existing behavior preserved
# ---------------------------------------------------------------------------


async def test_goodmem_only_no_db_works():
    mock_goodmem = _make_goodmem_ctx([
        MockMemory(content="Bismillah", metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ])
    ctx = AppContext(db_pool=None, goodmem_cli=mock_goodmem)

    result = await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert "ar-uthmani" in result.data
    assert result.data["ar-uthmani"][0]["text"] == "Bismillah"


# ---------------------------------------------------------------------------
# Neither → DataStoreError
# ---------------------------------------------------------------------------


async def test_neither_backend_raises_data_store_error():
    ctx = AppContext(db_pool=None, goodmem_cli=None)

    with pytest.raises(DataStoreError, match="No data backend available"):
        await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")


# ---------------------------------------------------------------------------
# Partial DB hit → DataGap, NO GoodMem supplementation
# ---------------------------------------------------------------------------


async def test_partial_db_hit_returns_gap_no_goodmem(monkeypatch):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": {"2:255": ("Ayat al-Kursi", {"ayah_key": "2:255"})}}),
    )
    mock_goodmem = _make_goodmem_ctx([])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    result = await EditionFetcher(_make_config()).fetch(ctx, ["2:255", "2:256"], "ar-uthmani")

    assert "ar-uthmani" in result.data
    assert len(result.data["ar-uthmani"]) == 1
    assert result.gaps is not None
    assert any(g.edition_id == "ar-uthmani" and "2:256" in g.missing_ayahs for g in result.gaps)
    mock_goodmem.search_memories.assert_not_called()


# ---------------------------------------------------------------------------
# Mixed-source editions: A in DB, B not → A from DB, B from GoodMem
# ---------------------------------------------------------------------------


async def test_mixed_source_editions(monkeypatch):
    # ar-uthmani in DB, ar-simple NOT in DB (returns None → fallback)
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({
            "ar-uthmani": {"2:255": ("DB-text", {"ayah_key": "2:255"})},
            "ar-simple": None,
        }),
    )
    mock_goodmem = _make_goodmem_ctx([
        MockMemory(content="GM-text", metadata={"ayah_key": "2:255", "edition_id": "ar-simple", "edition_type": "quran"}),
    ])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    result = await EditionFetcher(_make_config()).fetch(ctx, "2:255", ["ar-uthmani", "ar-simple"])

    assert result.data["ar-uthmani"][0]["text"] == "DB-text"
    assert result.data["ar-simple"][0]["text"] == "GM-text"


# ---------------------------------------------------------------------------
# Edition exists in DB but ayahs don't → empty + DataGap, NOT fallback
# ---------------------------------------------------------------------------


async def test_edition_exists_but_ayahs_missing_no_fallback(monkeypatch):
    # DB returns empty dict (edition exists but no matching ayahs)
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": {}}),
    )
    mock_goodmem = _make_goodmem_ctx([])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    # Single edition, all ayahs missing → DataNotFoundError
    from quran_mcp.lib.editions.errors import DataNotFoundError
    with pytest.raises(DataNotFoundError):
        await EditionFetcher(_make_config()).fetch(ctx, "99:1", "ar-uthmani")

    mock_goodmem.search_memories.assert_not_called()


# ---------------------------------------------------------------------------
# Logging assertions
# ---------------------------------------------------------------------------


async def test_db_fetch_logs_info(monkeypatch, caplog):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": {"1:1": ("text", {"ayah_key": "1:1"})}}),
    )
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=None)

    with caplog.at_level(logging.INFO, logger="quran_mcp.lib.editions.fetcher"):
        await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert any("DB fetch:" in r.message for r in caplog.records)


async def test_fallback_logs_warning(monkeypatch, caplog):
    monkeypatch.setattr(
        db_mod, "fetch_from_db",
        _mock_fetch_from_db({"ar-uthmani": None}),
    )
    mock_goodmem = _make_goodmem_ctx([
        MockMemory(content="text", metadata={"ayah_key": "1:1", "edition_id": "ar-uthmani", "edition_type": "quran"}),
    ])
    ctx = AppContext(db_pool=AsyncMock(), goodmem_cli=mock_goodmem)

    with caplog.at_level(logging.WARNING, logger="quran_mcp.lib.editions.fetcher"):
        await EditionFetcher(_make_config()).fetch(ctx, "1:1", "ar-uthmani")

    assert any("DB fetch skipped" in r.message and "falling back" in r.message for r in caplog.records)
