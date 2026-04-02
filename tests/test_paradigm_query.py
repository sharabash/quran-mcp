"""Unit tests for lib/morphology/paradigm_query.py — lemma/root resolution."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from quran_mcp.lib.morphology.paradigm_query import (
    resolve_lemma_by_text,
    resolve_root_by_text,
    get_word_visible_segments,
)


def _mock_pool(fetchrow_return=None, fetchrow_side_effect=None, fetch_return=None):
    pool = AsyncMock()
    if fetchrow_side_effect:
        pool.fetchrow.side_effect = fetchrow_side_effect
    else:
        pool.fetchrow.return_value = fetchrow_return
    pool.fetch.return_value = fetch_return or []
    return pool


async def test_resolve_lemma_by_text_exact():
    pool = _mock_pool(fetchrow_return={
        "dict_lemma_id": 42, "value": "عَلِمَ", "clean": "علم", "gloss_en": "to know",
    })
    result = await resolve_lemma_by_text(pool, "عَلِمَ")
    assert result["dict_lemma_id"] == 42


async def test_resolve_lemma_by_text_normalized_fallback():
    call_count = 0
    async def _side_effect(sql, text):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return {"dict_lemma_id": 42, "value": "علم", "clean": "علم", "gloss_en": "to know"}

    pool = _mock_pool(fetchrow_side_effect=_side_effect)
    result = await resolve_lemma_by_text(pool, "عِلْم")
    assert result["dict_lemma_id"] == 42


async def test_resolve_lemma_not_found_raises():
    pool = _mock_pool(fetchrow_return=None)
    with pytest.raises(ValueError, match="Lemma not found"):
        await resolve_lemma_by_text(pool, "nonexistent")


async def test_resolve_root_by_text_strips_spaces():
    pool = _mock_pool(fetchrow_return={"dict_root_id": 10, "root_value": "علم"})
    result = await resolve_root_by_text(pool, root_text="ع ل م")
    assert result["dict_root_id"] == 10
    args = pool.fetchrow.call_args[0]
    assert "علم" in args


async def test_resolve_root_by_text_not_found_raises():
    pool = _mock_pool(fetchrow_return=None)
    with pytest.raises(ValueError, match="Root not found"):
        await resolve_root_by_text(pool, root_text="xyz")


async def test_get_word_visible_segments():
    segments = [
        {"part_of_speech_key": "V", "part_of_speech_name": "verb",
         "pos_tags": "PERF", "verb_form": "I"},
    ]
    pool = _mock_pool(fetch_return=segments)
    result = await get_word_visible_segments(pool, word_id=1)
    assert len(result) == 1
    assert result[0]["part_of_speech_key"] == "V"
