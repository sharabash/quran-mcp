"""Query layer for fetch_quran_metadata.

Each query mode has a dedicated async function that:
1. Validates parameter ranges
2. Executes a single SQL query with DB-side aggregation
3. Assembles a QuranMetadataResponse

All queries use the quran_com schema (static reference data).
"""

from __future__ import annotations

import asyncpg

from quran_mcp.lib.metadata.types import (
    AyahPoint,
    AyahRange,
    NumericPoint,
    NumericRange,
    QuranMetadataResponse,
    RukuPoint,
    SajdahInfo,
    SurahInfo,
)


# ---------------------------------------------------------------------------
# SQL: ayah point query (surah + ayah)
# ---------------------------------------------------------------------------

_AYAH_POINT_SQL = """
SELECT
    v.verse_key, v.verse_number, v.words_count,
    v.juz_number, v.hizb_number, v.rub_el_hizb_number,
    v.page_number, v.ruku_number, v.surah_ruku_number,
    v.manzil_number, v.sajdah_type, v.sajdah_number,
    c.chapter_id, c.name_arabic, c.name_simple,
    c.revelation_place, c.revelation_order, c.verses_count, c.bismillah_pre
FROM quran_com.verse v
JOIN quran_com.chapter c ON c.chapter_id = v.chapter_id
WHERE v.chapter_id = $1 AND v.verse_number = $2
"""


async def query_ayah_point(
    pool: asyncpg.Pool, surah: int, ayah: int
) -> QuranMetadataResponse:
    """Fetch structural metadata for a single ayah."""
    if not 1 <= surah <= 114:
        raise ValueError(f"surah must be 1-114, got {surah}")
    if ayah < 1:
        raise ValueError(f"ayah must be >= 1, got {ayah}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_AYAH_POINT_SQL, surah, ayah)

    if not row:
        raise ValueError(f"Verse {surah}:{ayah} not found")

    sajdah: list[SajdahInfo] = []
    if row["sajdah_type"] is not None:
        sajdah.append(
            SajdahInfo(
                verse_key=row["verse_key"],
                type=row["sajdah_type"],
                number=row["sajdah_number"],
            )
        )

    return QuranMetadataResponse(
        query_type="ayah",
        surah=[
            SurahInfo(
                number=row["chapter_id"],
                name_arabic=row["name_arabic"],
                name_simple=row["name_simple"],
                revelation_place=row["revelation_place"],
                revelation_order=row["revelation_order"],
                verses_count=row["verses_count"],
                bismillah_pre=row["bismillah_pre"],
            )
        ],
        ayah=AyahPoint(
            verse_key=row["verse_key"],
            number=row["verse_number"],
            words_count=row["words_count"],
        ),
        juz=NumericPoint(number=row["juz_number"]),
        hizb=NumericPoint(number=row["hizb_number"]),
        rub_el_hizb=NumericPoint(number=row["rub_el_hizb_number"]),
        page=NumericPoint(number=row["page_number"]),
        ruku=RukuPoint(
            number=row["ruku_number"],
            surah_ruku_number=row["surah_ruku_number"],
        ),
        manzil=NumericPoint(number=row["manzil_number"]),
        sajdah=sajdah,
    )


# ---------------------------------------------------------------------------
# SQL: span query helper — aggregates structural dimensions from a verse set
# ---------------------------------------------------------------------------

_SPAN_AGGREGATE_SQL = """
SELECT
    MIN(v.juz_number) AS juz_start, MAX(v.juz_number) AS juz_end,
    MIN(v.hizb_number) AS hizb_start, MAX(v.hizb_number) AS hizb_end,
    MIN(v.rub_el_hizb_number) AS rub_start, MAX(v.rub_el_hizb_number) AS rub_end,
    MIN(v.page_number) AS page_start, MAX(v.page_number) AS page_end,
    MIN(v.ruku_number) AS ruku_start, MAX(v.ruku_number) AS ruku_end,
    MIN(v.manzil_number) AS manzil_start, MAX(v.manzil_number) AS manzil_end,
    COUNT(*) AS verse_count
FROM quran_com.verse v
WHERE v.verse_id >= $1 AND v.verse_id <= $2
"""

_SPAN_SURAHS_SQL = """
SELECT DISTINCT ON (c.chapter_id)
    c.chapter_id, c.name_arabic, c.name_simple,
    c.revelation_place, c.revelation_order, c.verses_count, c.bismillah_pre
FROM quran_com.verse v
JOIN quran_com.chapter c ON c.chapter_id = v.chapter_id
WHERE v.verse_id >= $1 AND v.verse_id <= $2
ORDER BY c.chapter_id
"""

_SPAN_AYAH_BOUNDS_SQL = """
SELECT v.verse_key
FROM quran_com.verse v
WHERE v.verse_id = $1 OR v.verse_id = $2
ORDER BY v.verse_id
"""

_SPAN_SAJDAH_SQL = """
SELECT v.verse_key, v.sajdah_type, v.sajdah_number
FROM quran_com.verse v
WHERE v.verse_id >= $1 AND v.verse_id <= $2
  AND v.sajdah_type IS NOT NULL
ORDER BY v.verse_id
"""


async def _build_span_response(
    pool: asyncpg.Pool,
    query_type: str,
    first_verse_id: int,
    last_verse_id: int,
) -> QuranMetadataResponse:
    """Shared builder for all span query modes."""
    async with pool.acquire() as conn:
        agg_row = await conn.fetchrow(
            _SPAN_AGGREGATE_SQL, first_verse_id, last_verse_id
        )
        surah_rows = await conn.fetch(
            _SPAN_SURAHS_SQL, first_verse_id, last_verse_id
        )
        bound_rows = await conn.fetch(
            _SPAN_AYAH_BOUNDS_SQL, first_verse_id, last_verse_id
        )
        sajdah_rows = await conn.fetch(
            _SPAN_SAJDAH_SQL, first_verse_id, last_verse_id
        )

    surahs = [
        SurahInfo(
            number=r["chapter_id"],
            name_arabic=r["name_arabic"],
            name_simple=r["name_simple"],
            revelation_place=r["revelation_place"],
            revelation_order=r["revelation_order"],
            verses_count=r["verses_count"],
            bismillah_pre=r["bismillah_pre"],
        )
        for r in surah_rows
    ]

    if not bound_rows:
        raise ValueError(
            f"Could not find verse bounds for verse IDs "
            f"{first_verse_id}-{last_verse_id}"
        )
    start_vk = bound_rows[0]["verse_key"]
    end_vk = bound_rows[-1]["verse_key"]

    sajdah = [
        SajdahInfo(
            verse_key=r["verse_key"],
            type=r["sajdah_type"],
            number=r["sajdah_number"],
        )
        for r in sajdah_rows
    ]

    return QuranMetadataResponse(
        query_type=query_type,
        surah=surahs,
        ayah=AyahRange(
            start_verse_key=start_vk,
            end_verse_key=end_vk,
            count=agg_row["verse_count"],
        ),
        juz=NumericRange(start=agg_row["juz_start"], end=agg_row["juz_end"]),
        hizb=NumericRange(start=agg_row["hizb_start"], end=agg_row["hizb_end"]),
        rub_el_hizb=NumericRange(start=agg_row["rub_start"], end=agg_row["rub_end"]),
        page=NumericRange(start=agg_row["page_start"], end=agg_row["page_end"]),
        ruku=NumericRange(start=agg_row["ruku_start"], end=agg_row["ruku_end"]),
        manzil=NumericRange(
            start=agg_row["manzil_start"], end=agg_row["manzil_end"]
        ),
        sajdah=sajdah,
    )


# ---------------------------------------------------------------------------
# Surah span query
# ---------------------------------------------------------------------------

_SURAH_VERSE_BOUNDS_SQL = """
SELECT MIN(v.verse_id) AS first_id, MAX(v.verse_id) AS last_id
FROM quran_com.verse v
WHERE v.chapter_id = $1
"""


async def query_surah_span(
    pool: asyncpg.Pool, surah: int
) -> QuranMetadataResponse:
    """Fetch structural metadata spanning an entire surah."""
    if not 1 <= surah <= 114:
        raise ValueError(f"surah must be 1-114, got {surah}")

    async with pool.acquire() as conn:
        bounds = await conn.fetchrow(_SURAH_VERSE_BOUNDS_SQL, surah)

    if not bounds or bounds["first_id"] is None:
        raise ValueError(f"Surah {surah} not found")

    return await _build_span_response(
        pool, "surah", bounds["first_id"], bounds["last_id"]
    )


# ---------------------------------------------------------------------------
# Juz span query
# ---------------------------------------------------------------------------

_JUZ_BOUNDS_SQL = """
SELECT dj.first_verse_id, dj.last_verse_id
FROM quran_com.division_juz dj
WHERE dj.juz_number = $1
"""


async def query_juz_span(pool: asyncpg.Pool, juz: int) -> QuranMetadataResponse:
    """Fetch structural metadata spanning a juz."""
    if not 1 <= juz <= 30:
        raise ValueError(f"juz must be 1-30, got {juz}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_JUZ_BOUNDS_SQL, juz)

    if not row:
        raise ValueError(f"Juz {juz} not found")

    return await _build_span_response(
        pool, "juz", row["first_verse_id"], row["last_verse_id"]
    )


# ---------------------------------------------------------------------------
# Page span query
# ---------------------------------------------------------------------------

_PAGE_VERSE_BOUNDS_SQL = """
SELECT MIN(v.verse_id) AS first_id, MAX(v.verse_id) AS last_id
FROM quran_com.verse v
WHERE v.page_number = $1
"""


async def query_page_span(pool: asyncpg.Pool, page: int) -> QuranMetadataResponse:
    """Fetch structural metadata for all verses on a mushaf page."""
    if not 1 <= page <= 604:
        raise ValueError(f"page must be 1-604, got {page}")

    async with pool.acquire() as conn:
        bounds = await conn.fetchrow(_PAGE_VERSE_BOUNDS_SQL, page)

    if not bounds or bounds["first_id"] is None:
        raise ValueError(f"Page {page} not found")

    return await _build_span_response(
        pool, "page", bounds["first_id"], bounds["last_id"]
    )


# ---------------------------------------------------------------------------
# Hizb span query
# ---------------------------------------------------------------------------

_HIZB_BOUNDS_SQL = """
SELECT dh.first_verse_id, dh.last_verse_id
FROM quran_com.division_hizb dh
WHERE dh.hizb_number = $1
"""


async def query_hizb_span(pool: asyncpg.Pool, hizb: int) -> QuranMetadataResponse:
    """Fetch structural metadata spanning a hizb."""
    if not 1 <= hizb <= 60:
        raise ValueError(f"hizb must be 1-60, got {hizb}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_HIZB_BOUNDS_SQL, hizb)

    if not row:
        raise ValueError(f"Hizb {hizb} not found")

    return await _build_span_response(
        pool, "hizb", row["first_verse_id"], row["last_verse_id"]
    )


# ---------------------------------------------------------------------------
# Ruku span query
# ---------------------------------------------------------------------------

_RUKU_BOUNDS_SQL = """
SELECT dr.first_verse_id, dr.last_verse_id
FROM quran_com.division_ruku dr
WHERE dr.ruku_number = $1
"""


async def query_ruku_span(pool: asyncpg.Pool, ruku: int) -> QuranMetadataResponse:
    """Fetch structural metadata spanning a ruku."""
    if not 1 <= ruku <= 558:
        raise ValueError(f"ruku must be 1-558, got {ruku}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_RUKU_BOUNDS_SQL, ruku)

    if not row:
        raise ValueError(f"Ruku {ruku} not found")

    return await _build_span_response(
        pool, "ruku", row["first_verse_id"], row["last_verse_id"]
    )


# ---------------------------------------------------------------------------
# Manzil span query
# ---------------------------------------------------------------------------

_MANZIL_BOUNDS_SQL = """
SELECT dm.first_verse_id, dm.last_verse_id
FROM quran_com.division_manzil dm
WHERE dm.manzil_number = $1
"""


async def query_manzil_span(
    pool: asyncpg.Pool, manzil: int
) -> QuranMetadataResponse:
    """Fetch structural metadata spanning a manzil."""
    if not 1 <= manzil <= 7:
        raise ValueError(f"manzil must be 1-7, got {manzil}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_MANZIL_BOUNDS_SQL, manzil)

    if not row:
        raise ValueError(f"Manzil {manzil} not found")

    return await _build_span_response(
        pool, "manzil", row["first_verse_id"], row["last_verse_id"]
    )
