"""Unit tests for lib/morphology/query.py — verse/word resolution."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


from quran_mcp.lib.morphology.query import (
    resolve_verse_by_key,
    resolve_word_by_text,
)


def _mock_pool(fetchrow_return=None, fetchrow_side_effect=None):
    pool = AsyncMock()
    if fetchrow_side_effect:
        pool.fetchrow.side_effect = fetchrow_side_effect
    else:
        pool.fetchrow.return_value = fetchrow_return
    return pool


async def test_resolve_verse_by_key_valid():
    pool = _mock_pool(fetchrow_return={
        "verse_id": 100, "chapter_id": 2, "verse_number": 255,
        "verse_key": "2:255", "text_uthmani": "ayah text", "text_imlaei_simple": "simple",
    })
    result = await resolve_verse_by_key(pool, "2:255")
    assert result["verse_id"] == 100


async def test_resolve_verse_by_key_invalid_format():
    pool = _mock_pool()
    with pytest.raises(ValueError, match="Invalid ayah_key format"):
        await resolve_verse_by_key(pool, "invalid")


async def test_resolve_verse_by_key_non_numeric():
    pool = _mock_pool()
    with pytest.raises(ValueError, match="non-numeric"):
        await resolve_verse_by_key(pool, "abc:def")


async def test_resolve_verse_by_key_not_found():
    pool = _mock_pool(fetchrow_return=None)
    with pytest.raises(ValueError, match="Verse not found"):
        await resolve_verse_by_key(pool, "999:999")


async def test_resolve_word_by_text_exact_match():
    word_row = {"word_id": 1, "verse_id": 10, "position": 3,
                "text_uthmani": "بِسْمِ", "text_imlaei_simple": "بسم",
                "en_transliteration": "bismi", "verse_key": "1:1"}
    count_row = {"cnt": 5}

    call_count = 0
    async def _side_effect(sql, text):
        nonlocal call_count
        call_count += 1
        if "COUNT" in sql:
            return count_row
        return word_row

    pool = _mock_pool(fetchrow_side_effect=_side_effect)
    row, total = await resolve_word_by_text(pool, "بِسْمِ")
    assert row["word_id"] == 1
    assert total == 5
