"""Tests for quran_mcp.lib.metadata.query — input validation.

The actual SQL queries need a real PostgreSQL instance with quran_com schema
and belong in tests/integration/. These tests cover the pure validation logic
that runs before any DB access.

Covers:
  - query_ayah_point: surah 1-114, ayah >= 1
  - query_surah_span: surah 1-114
  - query_juz_span: juz 1-30
  - query_page_span: page 1-604
  - query_hizb_span: hizb 1-60
  - query_ruku_span: ruku 1-558
  - query_manzil_span: manzil 1-7
"""

from __future__ import annotations

import pytest

from quran_mcp.lib.metadata.query import (
    query_ayah_point,
    query_hizb_span,
    query_juz_span,
    query_manzil_span,
    query_page_span,
    query_ruku_span,
    query_surah_span,
)


# A sentinel pool — validation fires before pool is used, so None works.
_NO_POOL = None


class TestAyahPointValidation:
    async def test_surah_below_range(self):
        with pytest.raises(ValueError, match="surah must be 1-114"):
            await query_ayah_point(_NO_POOL, 0, 1)

    async def test_surah_above_range(self):
        with pytest.raises(ValueError, match="surah must be 1-114"):
            await query_ayah_point(_NO_POOL, 115, 1)

    async def test_ayah_below_range(self):
        with pytest.raises(ValueError, match="ayah must be >= 1"):
            await query_ayah_point(_NO_POOL, 1, 0)

    async def test_ayah_negative(self):
        with pytest.raises(ValueError, match="ayah must be >= 1"):
            await query_ayah_point(_NO_POOL, 1, -5)


class TestSurahSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="surah must be 1-114"):
            await query_surah_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="surah must be 1-114"):
            await query_surah_span(_NO_POOL, 115)


class TestJuzSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="juz must be 1-30"):
            await query_juz_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="juz must be 1-30"):
            await query_juz_span(_NO_POOL, 31)


class TestPageSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="page must be 1-604"):
            await query_page_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="page must be 1-604"):
            await query_page_span(_NO_POOL, 605)


class TestHizbSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="hizb must be 1-60"):
            await query_hizb_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="hizb must be 1-60"):
            await query_hizb_span(_NO_POOL, 61)


class TestRukuSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="ruku must be 1-558"):
            await query_ruku_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="ruku must be 1-558"):
            await query_ruku_span(_NO_POOL, 559)


class TestManzilSpanValidation:
    async def test_below_range(self):
        with pytest.raises(ValueError, match="manzil must be 1-7"):
            await query_manzil_span(_NO_POOL, 0)

    async def test_above_range(self):
        with pytest.raises(ValueError, match="manzil must be 1-7"):
            await query_manzil_span(_NO_POOL, 8)
