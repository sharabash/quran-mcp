"""Unit tests for fetch_from_db — the PostgreSQL fetch backend."""
from __future__ import annotations

import asyncpg
import pytest
from unittest.mock import AsyncMock

from quran_mcp.lib.editions.errors import DataStoreError
from quran_mcp.lib.editions.fetcher.db import fetch_from_db


def _mock_pool(*, fetchval_return=None, fetchval_side_effect=None,
               fetch_return=None, fetch_side_effect=None):
    pool = AsyncMock(spec=asyncpg.Pool)
    if fetchval_side_effect:
        pool.fetchval.side_effect = fetchval_side_effect
    else:
        pool.fetchval.return_value = fetchval_return
    if fetch_side_effect:
        pool.fetch.side_effect = fetch_side_effect
    else:
        pool.fetch.return_value = fetch_return or []
    return pool


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_db_returns_rows_with_correct_shape():
    rows = [
        {"ayah_key": "1:1", "content": "بِسْمِ اللَّهِ", "metadata": {"edition_type": "quran", "edition_id": "ar-simple-clean", "surah": 1, "ayah": 1, "ayah_key": "1:1"}},
        {"ayah_key": "1:2", "content": "الْحَمْدُ لِلَّهِ", "metadata": {"edition_type": "quran", "edition_id": "ar-simple-clean", "surah": 1, "ayah": 2, "ayah_key": "1:2"}},
    ]
    pool = _mock_pool(fetchval_return=True, fetch_return=rows)

    result = await fetch_from_db(pool, "quran", "ar-simple-clean", ["1:1", "1:2"])

    assert result is not None
    assert len(result) == 2
    assert "1:1" in result
    assert "1:2" in result
    assert result["1:1"][0] == "بِسْمِ اللَّهِ"
    assert result["1:1"][1]["edition_id"] == "ar-simple-clean"


async def test_tafsir_metadata_preserved_through_jsonb():
    rows = [
        {
            "ayah_key": "2:255-257",
            "content": "<p>Tafsir of Ayat al-Kursi</p>",
            "surah": 2,
            "ayah_start": 255,
            "ayah_end": 257,
            "metadata": {
                "edition_type": "tafsir",
                "edition_id": "en-ibn-kathir",
                "surah": 2,
                "ayah_key": "2:255-257",
                "citation_url": "https://quran.com/2:255/tafsirs",
                "passage_ayah_range": "2:255-257",
                "tafsir_row_id": 12345,
            },
        },
    ]
    pool = _mock_pool(fetchval_return=True, fetch_return=rows)

    result = await fetch_from_db(pool, "tafsir", "en-ibn-kathir", ["2:255", "2:256"])

    assert result is not None
    # Range passage remapped to individual requested ayah keys
    assert "2:255" in result
    assert "2:256" in result
    meta = result["2:255"][1]
    assert meta["citation_url"] == "https://quran.com/2:255/tafsirs"
    assert meta["passage_ayah_range"] == "2:255-257"
    assert meta["tafsir_row_id"] == 12345
    # Both ayah keys point to the same content
    assert result["2:255"][0] == result["2:256"][0]


# ---------------------------------------------------------------------------
# Fallback signals (return None)
# ---------------------------------------------------------------------------


async def test_table_missing_returns_none():
    pool = _mock_pool(fetchval_side_effect=asyncpg.UndefinedTableError("relation does not exist"))

    result = await fetch_from_db(pool, "quran", "ar-simple-clean", ["1:1"])

    assert result is None


async def test_edition_not_in_db_returns_none():
    pool = _mock_pool(fetchval_return=False)

    result = await fetch_from_db(pool, "quran", "nonexistent-edition", ["1:1"])

    assert result is None
    pool.fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


async def test_connection_error_raises_data_store_error():
    pool = _mock_pool(fetchval_side_effect=asyncpg.ConnectionDoesNotExistError("connection lost"))

    with pytest.raises(DataStoreError, match="connection lost"):
        await fetch_from_db(pool, "quran", "ar-simple-clean", ["1:1"])
