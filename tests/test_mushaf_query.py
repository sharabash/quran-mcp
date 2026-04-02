from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quran_mcp.lib.mushaf.query import get_page_data, resolve_page
from quran_mcp.lib.mushaf.types import DEFAULT_MUSHAF_ID


def _make_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


def _word_row(
    word_id=1,
    verse_id=1,
    text="بِسْمِ",
    char_type_name="word",
    line_number=1,
    position_in_line=1,
    position_in_verse=1,
    glyph_text=None,
    verse_key="1:1",
    chapter_id=1,
    verse_number=1,
    name_arabic="الفاتحة",
    name_simple="Al-Fatihah",
    bismillah_pre=True,
):
    return {
        "word_id": word_id,
        "verse_id": verse_id,
        "text": text,
        "char_type_name": char_type_name,
        "line_number": line_number,
        "position_in_line": position_in_line,
        "position_in_verse": position_in_verse,
        "glyph_text": glyph_text,
        "verse_key": verse_key,
        "chapter_id": chapter_id,
        "verse_number": verse_number,
        "name_arabic": name_arabic,
        "name_simple": name_simple,
        "bismillah_pre": bismillah_pre,
    }


class TestGetPageData:
    @pytest.mark.asyncio
    async def test_returns_page_data_structure(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(word_id=1, line_number=1, position_in_line=1, verse_number=1),
            _word_row(word_id=2, line_number=1, position_in_line=2, verse_number=1),
            _word_row(word_id=3, line_number=2, position_in_line=1, verse_number=1),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=1)

        assert result.page_number == 1
        assert result.mushaf_edition_id == DEFAULT_MUSHAF_ID
        assert result.total_pages == 604
        assert len(result.lines) == 2
        assert len(result.lines[0].words) == 2
        assert len(result.lines[1].words) == 1

    @pytest.mark.asyncio
    async def test_verses_populated(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(word_id=1, verse_id=10, verse_key="1:1", verse_number=1),
            _word_row(word_id=2, verse_id=11, verse_key="1:2", verse_number=2),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=1)

        assert len(result.verses) == 2
        assert result.verses[0].verse_key == "1:1"
        assert result.verses[1].verse_key == "1:2"

    @pytest.mark.asyncio
    async def test_surah_header_detected(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(
                word_id=1,
                verse_number=1,
                chapter_id=2,
                name_arabic="البقرة",
                name_simple="Al-Baqarah",
                bismillah_pre=True,
                line_number=3,
            ),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=2)

        assert len(result.surah_headers) == 1
        assert result.surah_headers[0].chapter_id == 2
        assert result.surah_headers[0].name_arabic == "البقرة"
        assert result.surah_headers[0].name_simple == "Al-Baqarah"
        assert result.surah_headers[0].bismillah_pre is True
        assert result.surah_headers[0].appears_before_line == 3

    @pytest.mark.asyncio
    async def test_chapter_names_populated(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(word_id=1, chapter_id=1, name_simple="Al-Fatihah"),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=1)

        assert result.chapter_names == {1: "Al-Fatihah"}

    @pytest.mark.asyncio
    async def test_no_surah_header_when_not_verse_one(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(word_id=1, verse_number=5, chapter_id=2),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=10)

        assert result.surah_headers == []

    @pytest.mark.asyncio
    async def test_glyph_text_passed_through(self):
        pool, conn = _make_pool()
        rows = [
            _word_row(word_id=1, glyph_text="\uFD3E"),
        ]
        conn.fetch = AsyncMock(return_value=rows)

        result = await get_page_data(pool, page_number=1)

        assert result.lines[0].words[0].glyph_text == "\uFD3E"

    @pytest.mark.asyncio
    async def test_invalid_page_zero(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Page number must be 1-604"):
            await get_page_data(pool, page_number=0)

    @pytest.mark.asyncio
    async def test_invalid_page_negative(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Page number must be 1-604"):
            await get_page_data(pool, page_number=-1)

    @pytest.mark.asyncio
    async def test_invalid_page_exceeds_max(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Page number must be 1-604"):
            await get_page_data(pool, page_number=605)

    @pytest.mark.asyncio
    async def test_empty_result_raises(self):
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="No data found"):
            await get_page_data(pool, page_number=1)


class TestResolvePageDirect:
    @pytest.mark.asyncio
    async def test_direct_page_number(self):
        pool, _ = _make_pool()
        result = await resolve_page(pool, page=42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_page_one_boundary(self):
        pool, _ = _make_pool()
        result = await resolve_page(pool, page=1)
        assert result == 1

    @pytest.mark.asyncio
    async def test_page_max_boundary(self):
        pool, _ = _make_pool()
        result = await resolve_page(pool, page=604)
        assert result == 604

    @pytest.mark.asyncio
    async def test_page_zero_invalid(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Page must be 1-604"):
            await resolve_page(pool, page=0)

    @pytest.mark.asyncio
    async def test_page_exceeds_max(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Page must be 1-604"):
            await resolve_page(pool, page=605)

    @pytest.mark.asyncio
    async def test_defaults_to_page_one(self):
        pool, _ = _make_pool()
        result = await resolve_page(pool)
        assert result == 1


class TestResolveVerse:
    @pytest.mark.asyncio
    async def test_surah_ayah_resolved(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"page_number": 50})

        result = await resolve_page(pool, surah=2, ayah=255)

        assert result == 50

    @pytest.mark.asyncio
    async def test_surah_alone_resolved(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"page_number": 1})

        result = await resolve_page(pool, surah=1)

        assert result == 1

    @pytest.mark.asyncio
    async def test_surah_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Surah 114 not found"):
            await resolve_page(pool, surah=114)

    @pytest.mark.asyncio
    async def test_verse_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Verse 2:999 not found"):
            await resolve_page(pool, surah=2, ayah=999)

    @pytest.mark.asyncio
    async def test_surah_out_of_range(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Surah must be 1-114"):
            await resolve_page(pool, surah=0)

    @pytest.mark.asyncio
    async def test_surah_above_114(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Surah must be 1-114"):
            await resolve_page(pool, surah=115)

    @pytest.mark.asyncio
    async def test_ayah_zero_invalid(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Ayah must be >= 1"):
            await resolve_page(pool, surah=1, ayah=0)


class TestResolveJuz:
    @pytest.mark.asyncio
    async def test_juz_resolved(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"page_number": 22})

        result = await resolve_page(pool, juz=2)

        assert result == 22

    @pytest.mark.asyncio
    async def test_juz_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Juz 30 not found"):
            await resolve_page(pool, juz=30)

    @pytest.mark.asyncio
    async def test_juz_zero_invalid(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Juz must be 1-30"):
            await resolve_page(pool, juz=0)

    @pytest.mark.asyncio
    async def test_juz_above_30_invalid(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="Juz must be 1-30"):
            await resolve_page(pool, juz=31)


class TestMutualExclusivity:
    @pytest.mark.asyncio
    async def test_page_and_surah_exclusive(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="mutually exclusive"):
            await resolve_page(pool, page=1, surah=1)

    @pytest.mark.asyncio
    async def test_page_and_juz_exclusive(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="mutually exclusive"):
            await resolve_page(pool, page=1, juz=1)

    @pytest.mark.asyncio
    async def test_surah_and_juz_exclusive(self):
        pool, _ = _make_pool()
        with pytest.raises(ValueError, match="mutually exclusive"):
            await resolve_page(pool, surah=1, juz=1)
