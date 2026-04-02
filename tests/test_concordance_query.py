"""Unit tests for lib/morphology/concordance_query.py — text resolution and ID lookup."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from quran_mcp.lib.morphology.concordance_query import (
    get_word_linguistic_ids,
    resolve_root_id,
    _resolve_dict_id,
)


def _mock_pool(fetchrow_return=None, fetchrow_side_effect=None):
    pool = AsyncMock()
    if fetchrow_side_effect:
        pool.fetchrow.side_effect = fetchrow_side_effect
    else:
        pool.fetchrow.return_value = fetchrow_return
    return pool


async def test_get_word_linguistic_ids_returns_dict():
    pool = _mock_pool(fetchrow_return={
        "dict_root_id": 10, "dict_lemma_id": 20, "dict_stem_id": 30,
    })
    result = await get_word_linguistic_ids(pool, word_id=1)
    assert result == {"dict_root_id": 10, "dict_lemma_id": 20, "dict_stem_id": 30}


async def test_get_word_linguistic_ids_none_row():
    pool = _mock_pool(fetchrow_return=None)
    result = await get_word_linguistic_ids(pool, word_id=999)
    assert result == {"dict_root_id": None, "dict_lemma_id": None, "dict_stem_id": None}


async def test_resolve_root_id_strips_spaces():
    pool = _mock_pool(fetchrow_return={"dict_root_id": 42})
    await resolve_root_id(pool, "ع ل م")
    pool.fetchrow.assert_called_once()
    args = pool.fetchrow.call_args[0]
    assert "علم" in args


async def test_resolve_dict_id_normalization_fallback():
    call_count = 0

    async def _side_effect(sql, text):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return {"test_id": 99}

    pool = _mock_pool(fetchrow_side_effect=_side_effect)
    result = await _resolve_dict_id(pool, "SELECT 1", "test_id", "عِلم", "Test")
    assert result == 99
    assert call_count == 2


async def test_resolve_dict_id_not_found_raises():
    pool = _mock_pool(fetchrow_return=None)
    with pytest.raises(ValueError, match="not found"):
        await _resolve_dict_id(pool, "SELECT 1", "test_id", "xyz", "Test")
